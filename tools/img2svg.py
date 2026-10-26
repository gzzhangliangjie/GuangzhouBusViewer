#!/usr/bin/env python3
"""位图地铁线路图 → SVG 矢量化 + OCR 文字还原 + 本地微调页。

传入任意位图 (png/jpg/bmp/webp):
  1. 预处理: 贴白底 → 自动校斜 → 照片模式自动判定 (flat-field 照明校正+拍白)
     → 海报彩框四点透视矫正 → 裁内容白边;
  2. 线路走廊/站圆/色块 → vtracer (cutout 无叠压) 描摹, trace-layer 内按色
     分组建层 (色彩≈线路色);
  3. 文字区域走 OCR (rapidocr, 离线中文; 照片模式 2 倍分辨率提升小号编号牌),
     抹除后以真实 <text> 回填原位 (字号按本机字体实测匹配原尺寸);
  4. 生成 <输出名>.svg.tune.html 微调页: 滚轮缩放/拖拽平移/拖动改位/改字
     改字号改色/增删文字/一键导出 SVG。
OCR 引擎未安装时自动退化为纯描摹 (文字走轮廓), 提示 pip install。

用法:
  python tools/img2svg.py 图片.png                 # 输出 X.svg + X.svg.tune.html
  python tools/img2svg.py a.png b.jpg --compare    # 批量 + 出"原图|矢量"对照图
  python tools/img2svg.py 图.png --no-ocr          # 跳过 OCR, 文字走轮廓描摹
  python tools/img2svg.py 线稿.png --binary 160    # 黑白线稿二值描摹
  python tools/img2svg.py 网图.jpg --colors 16     # JPEG 噪点重的图收紧量化

参数:
  --colors N       描摹前颜色量化档数 (默认 32, 0=关闭; 越少越干净, 细节越少)
  --flatten-white T 照片模式阈值 (缺省=自动判定; 0=强制关闭; 数值=强制开启, 建议 180-210)
  --no-deskew      跳过自动校斜
  --mode M         spline=平滑曲线(默认) / polygon=多边形 / none=像素块
  --binary T       黑白二值描摹, T=墨色阈值 0-255 (指定后忽略 --colors)
  --upscale F      描摹前放大倍数 (默认自动: 边<400→4倍, <600→3倍, <1200→2倍, 0=禁止)
  --speckle N      去斑点强度 px (默认 8)
  --layer-diff N   相邻色层合并阈值 (默认 16)
  --precision N    路径坐标小数位 (默认 2, 与全库坐标口径一致)
  --ocr-score F    OCR 置信度下限 (默认 0.45)
  --no-ocr         不做 OCR, 文字随图形一起描成轮廓
  --no-tune        不生成微调页
  --max-side N     预览/对照图最长边 px (默认 1400)
  --compare        额外输出 <输出名>.compare.png: 左原图右矢量渲染
"""
import argparse
import math
import os
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

import numpy as np
import vtracer
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDGE = r'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
NS = 'http://www.w3.org/2000/svg'
MAX_TRACE_SIDE = 4000   # 放大后超过此边长描摹会非常慢, 自动收敛倍数
FONT_STACK = '"Microsoft YaHei","PingFang SC","Noto Sans CJK SC",sans-serif'
_ocr_engine = None      # 进程级缓存: 批量多图不重复加载模型


def get_ocr():
    global _ocr_engine
    if _ocr_engine == 'missing':
        return None
    if _ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            _ocr_engine = 'missing'
            return None
        # 不传 kwargs: 1.2.x 的配置更新器吃不动; 分块 1200 > det 默认 736(min 型) 本就不缩
        _ocr_engine = RapidOCR()
    return _ocr_engine


def auto_deskew(im):
    """Hough 主方向加权投票估全局倾角; 0.8°~20° 才转, 屏幕截图/平图自动跳过。"""
    try:
        import cv2
    except ImportError:
        return im, 0.0
    g = cv2.cvtColor(np.asarray(im.convert('RGB')), cv2.COLOR_RGB2GRAY)
    g = cv2.GaussianBlur(g, (3, 3), 0)
    edges = cv2.Canny(g, 60, 160)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=90,
                            minLineLength=max(g.shape) // 14, maxLineGap=35)
    if lines is None:
        return im, 0.0
    votes = []
    for x0, y0, x1, y1 in lines.reshape(-1, 4):  # cv2 4.x (N,1,4) / 5.x (N,4) 通吃
        ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
        # 全部线参与投票 (横平/竖直/45°斜线都携带同一全局倾角), 模 90 归一。
        # 分布双峰 {倾角θ, θ-45}: 中位数落在横平桶→正确校斜; 落在斜线桶→
        # |skew|>20° 被下方安全阀拒绝 → 宁可不转也不会转错。
        votes.append((math.hypot(x1 - x0, y1 - y0), (ang + 45.0) % 90.0 - 45.0))
    votes.sort(key=lambda t: t[1])
    wsum = sum(v for v, _ in votes)
    acc, skew = 0.0, 0.0
    for v, ang in votes:  # 长度加权中位数: 单条噪声线拉不动
        acc += v
        if acc >= wsum / 2:
            skew = ang
            break
    # 亚度级精化: 中位数邻域 ±2.5° 内加权均值 (小倾角散在相邻桶里, 中位数取整会丢)
    near = [(v, ang) for v, ang in votes if abs(ang - skew) <= 2.5]
    if near:
        w2 = sum(v for v, _ in near)
        skew = sum(v * ang for v, ang in near) / w2
    if not (0.8 <= abs(skew) <= 20.0):
        return im, 0.0
    out = im.rotate(skew, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255))
    return out, skew


def detect_photo_mode(im):
    """边缘环带近白占比 < 60% → 判为实拍/带环境图 (屏幕截图边缘齐白)。"""
    a = np.asarray(im.convert('RGB')).astype(np.int16)
    h, w = a.shape[:2]
    m = max(2, min(h, w) // 50)
    border = np.concatenate([a[:m].reshape(-1, 3), a[-m:].reshape(-1, 3),
                             a[:, :m].reshape(-1, 3), a[:, -m:].reshape(-1, 3)])
    return float((border >= 235).all(axis=1).mean()) < 0.60


def flatten_photo(im, thresh):
    """flat-field 照明校正: 大半径高斯估照明场, 逐通道 a/bg 归一——同一条线的
    亮段/暗段色值归到同档; 再把近中性亮像素拍平成纯白杀残余背景。"""
    from PIL import ImageFilter
    radius = max(im.size) / 12.0
    a = np.asarray(im).astype(np.float32)
    bg = np.asarray(im.filter(ImageFilter.GaussianBlur(radius))).astype(np.float32)
    bg = np.maximum(bg, 60.0)
    a = np.clip(a / bg * 245.0, 0, 255).astype(np.uint8)
    a[(a >= thresh).all(axis=2)] = 255
    return Image.fromarray(a)


def dewarp_legend(im):
    """褶皱去弯: 底部图例带用线路色块自身当标轨 — 色块中心相对理想行列网格的
    残差拟合成分段线性位移场 dx(x)/dy(x), cv2.remap 把整条带(图例/促销/底框/
    符号列)统一搬正; 色块不足 12 块或残差可忽略时原样返回。"""
    try:
        import cv2
    except ImportError:
        return im, '', None
    a = np.asarray(im)
    h, w = a.shape[:2]
    hsv = cv2.cvtColor(a, cv2.COLOR_RGB2HSV)
    mask = ((hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 60)).astype(np.uint8) * 255
    n, _, stats, cent = cv2.connectedComponentsWithStats(mask, 8)
    band_y = h * 0.70  # 图例带下限: 再高会把地图底部的彩色元素混进标轨
    chips = []
    for i in range(1, n):
        x, y, sw, sh, area = stats[i]
        cx, cy = cent[i]
        if cy < band_y or not (30 <= sw <= 180) or not (12 <= sh <= 70):
            continue
        if sh >= sw or area < 0.55 * sw * sh:  # 色块 = 横向实心矩形
            continue
        chips.append((cx, cy, x, y, sw, sh))
    if len(chips) < 12:
        return im, '', None
    chips.sort(key=lambda t: t[1])
    rows, cur = [], [chips[0]]
    for c in chips[1:]:
        if c[1] - cur[-1][1] > 45:
            rows.append(cur)
            cur = []
        cur.append(c)
    rows.append(cur)
    rows = [r for r in rows if len(r) >= 3]  # 色块行至少 3 块, 孤点不入轨
    if len(rows) < 2:
        return im, '', None
    rows.sort(key=lambda r: sorted(c[1] for c in r)[len(r) // 2])
    row_y = [sorted(c[1] for c in r)[len(r) // 2] for r in rows]
    if max(b - a for a, b in zip(row_y, row_y[1:])) > 240:  # 行距异常 → 检测不可靠
        return im, '', None
    xs = sorted(c[0] for r in rows for c in r)
    cols, cur = [], [xs[0]]
    for x in xs[1:]:
        if x - cur[-1] > 90:
            cols.append(sorted(cur)[len(cur) // 2])
            cur = []
        cur.append(x)
    cols.append(sorted(cur)[len(cur) // 2])
    if len(cols) < 4:
        return im, '', None
    dxs, dys = [], []
    for r, ry in zip(rows, row_y):
        for c in r:
            k = min(range(len(cols)), key=lambda t: abs(cols[t] - c[0]))
            dxs.append((k, c[0] - cols[k]))
            dys.append((k, c[1] - ry))
    dx = np.array([sorted(e for kk, e in dxs if kk == k)[len([1 for kk, e in dxs if kk == k]) // 2]
                   for k in range(len(cols))])
    dy = np.array([sorted(e for kk, e in dys if kk == k)[len([1 for kk, e in dys if kk == k]) // 2]
                   for k in range(len(cols))])
    if float(np.abs(dx).max() + np.abs(dy).max()) < 6:
        return im, '', None
    cols_a = np.array(cols, dtype=np.float32)
    band_top = max(0, int(min(c[1] for r in rows for c in r) - 160))
    xs_line = np.arange(w, dtype=np.float32)
    dx_line = np.interp(xs_line, cols_a, dx).astype(np.float32)
    dy_line = np.interp(xs_line, cols_a, dy).astype(np.float32)
    map_x = np.tile(xs_line, (h - band_top, 1)) - dx_line[None, :]
    map_y = (np.arange(band_top, h, dtype=np.float32)[:, None]
             - dy_line[None, :] * np.ones((1, w), dtype=np.float32))
    out = cv2.remap(a, map_x, map_y, cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
    full = np.full_like(a, 255)
    full[:band_top] = a[:band_top]
    full[band_top:] = out
    # 标轨 (去皱后坐标): 行轴/列轴 + 色块中位尺寸 — 供组装期逐格合成图例
    rails_rows = []
    for r, ry in zip(rows, row_y):
        ks = [min(range(len(cols)), key=lambda t: abs(cols[t] - c[0])) for c in r]
        k = max(set(ks), key=ks.count)
        rails_rows.append(ry - dy[k])
    rails_cols = [cols[k] - dx[k] for k in range(len(cols))]
    rails = (sorted(rails_rows), sorted(rails_cols),
             int(np.median([c[4] for c in chips])), int(np.median([c[5] for c in chips])))
    return Image.fromarray(full), '图例带去皱(Δx≤%d Δy≤%dpx)' % (
        int(np.abs(dx).max()), int(np.abs(dy).max())), rails


def rectify_poster(im):
    """海报四点透视矫正: 地铁线网图统一彩框, 用饱和色边框环做四角检测,
    兜底近白大四边形。检测不到 / 面积占比异常 / 已基本摆正(<1.2°)时原样返回。"""
    try:
        import cv2
    except ImportError:
        return im, ''
    a = np.asarray(im)
    h, w = a.shape[:2]
    hsv = cv2.cvtColor(a, cv2.COLOR_RGB2HSV)
    white = ((a >= 200).all(axis=2).astype(np.uint8) * 255)
    quad = None
    for mask in (cv2.inRange(hsv, (35, 60, 60), (95, 255, 255)), white):
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            continue
        c = max(cnts, key=cv2.contourArea)
        area = cv2.contourArea(c)
        if area < 0.12 * h * w or area > 0.97 * h * w:
            continue
        ap = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        quad = ap.reshape(-1, 2).astype(np.float32) if len(ap) == 4 \
            else cv2.boxPoints(cv2.minAreaRect(c))
        if quad is not None:
            break
    if quad is None:
        return im, ''
    s = quad.sum(axis=1)
    d = (quad[:, 0] - quad[:, 1])
    tl, br = quad[s.argmin()], quad[s.argmax()]
    tr, bl = quad[d.argmax()], quad[d.argmin()]  # tr: x−y 最大; bl: 最小
    Wa = max(np.hypot(*(tr - tl)), np.hypot(*(br - bl)))
    Ha = max(np.hypot(*(bl - tl)), np.hypot(*(br - tr)))
    if min(Wa, Ha) < 300 or min(Wa, Ha) / max(Wa, Ha) < 0.3:
        return im, ''

    def dev(p, q):
        ang = abs(math.degrees(math.atan2(q[1] - p[1], q[0] - p[0])))
        return min(ang, 90.0 - ang) if ang <= 90 else min(ang - 90.0, 180.0 - ang)

    # 倾角 = 四边对最近轴偏差的最大值 (混着平均横竖边会得出 44° 这类鬼数)
    tilt = max(dev(tl, tr), dev(bl, br), dev(tl, bl), dev(tr, br))
    if not (1.2 <= tilt <= 20.0):
        return im, ''
    m = cv2.getPerspectiveTransform(np.float32([tl, tr, br, bl]),
                                    np.float32([[0, 0], [Wa, 0], [Wa, Ha], [0, Ha]]))
    out = cv2.warpPerspective(a, m, (int(Wa), int(Ha)), flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
    return Image.fromarray(out), '透视矫正%.1f°' % tilt


def trim_content(im, pad=12, thresh=245):
    """裁掉四周纯白留白到内容 bbox (含 pad); 无有效裁剪原样返回。"""
    g = np.asarray(im.convert('L'))
    mask = g < thresh
    if not mask.any() or mask.mean() > 0.995:
        return im
    ys, xs = np.where(mask)
    x0, y0 = max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad)
    x1, y1 = min(im.width, int(xs.max()) + pad), min(im.height, int(ys.max()) + pad)
    if (x1 - x0) * (y1 - y0) > 0.98 * im.width * im.height:
        return im
    return im.crop((x0, y0, x1, y1))


def prep_image(src, colors, binary, upscale, flatten_white=None, no_deskew=False):
    """读图 → 贴白底 → 自动校斜 → 照片模式(自动判: 照明校正+拍白) → 裁内容边
    → (放大) → (量化/二值化)。返回 (work图, 原始尺寸, 实际倍数, 预处理日志)。"""
    im = Image.open(src)
    im.load()
    orig_size = im.size
    if im.mode == 'RGBA':
        base = Image.new('RGB', im.size, (255, 255, 255))
        base.paste(im, mask=im.getchannel('A'))
        im = base
    else:
        im = im.convert('RGB')

    log = []
    rails_dw = None
    if not no_deskew:
        im, skew = auto_deskew(im)
        if skew:
            log.append('校斜%.1f°' % skew)
    if flatten_white is None:
        flatten_white = 200 if detect_photo_mode(im) else 0
    if flatten_white:
        im = flatten_photo(im, flatten_white)
        log.append('照片模式(flat-field+拍白%d)' % flatten_white)
        im2, msg = rectify_poster(im)
        if msg:
            im = im2
            log.append(msg)
        im2, msg, rails_dw = dewarp_legend(im)
        if msg:
            im = im2
            log.append(msg)
    cut = trim_content(im)
    if cut.size != im.size:
        log.append('裁边%dx%d→%dx%d' % (im.width, im.height, cut.width, cut.height))
        im = cut

    factor = upscale
    if factor is None:
        m = max(im.size)
        factor = 4 if m < 400 else (3 if m < 600 else (2 if m < 1200 else 0))
    if factor and factor > 1:
        factor = min(factor, MAX_TRACE_SIDE / max(im.size))
        if factor > 1.05:
            im = im.resize((round(im.width * factor), round(im.height * factor)), Image.LANCZOS)
        else:
            factor = 0
    else:
        factor = 0

    if binary is not None:
        im = im.convert('L').point(lambda x: 0 if x < binary else 255).convert('RGB')
        palette = None
    elif colors:
        # dither 必须关: 默认 Floyd-Steinberg 会把纯色块抖成渐变杂色, path 数爆炸
        q = im.quantize(colors=colors, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
        pal = q.getpalette()
        palette = [tuple(pal[i:i + 3]) for i in range(0, colors * 3, 3)]
        im = q.convert('RGB')
    else:
        palette = None
    return im, orig_size, (factor if factor > 1 else 0), ' + '.join(log), palette, rails_dw


def _quad_metrics(quad):
    """四角点 → (cx, cy, w, h, angle)。angle=上边方向角(度)。"""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = quad
    cx = sum(p[0] for p in quad) / 4
    cy = sum(p[1] for p in quad) / 4
    w = (math.hypot(x1 - x0, y1 - y0) + math.hypot(x3 - x2, y3 - y2)) / 2
    h = (math.hypot(x3 - x0, y3 - y0) + math.hypot(x2 - x1, y2 - y1)) / 2
    ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
    return cx, cy, w, h, ang


def _median_color(arr, mask):
    px = arr[mask]
    if len(px) == 0:
        return (0, 0, 0)
    return tuple(int(v) for v in np.median(px, axis=0))


def _sample_text_colors(arr, quad, pad):
    """环带中位色=底色; 距底色最远的30%内圈像素主色=文字色 (白字深底/黑字白底通吃)。
    顺带量墨迹像素的实际宽高 (2/98 百分位抗噪) — 供字号匹配原尺寸。"""
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    x0, x1 = int(max(0, min(xs) - pad * 3)), int(min(arr.shape[1], max(xs) + pad * 3))
    y0, y1 = int(max(0, min(ys) - pad * 3)), int(min(arr.shape[0], max(ys) + pad * 3))
    if x1 <= x0 or y1 <= y0:
        return '#333333', '#ffffff', 0.0, 0.0
    win = arr[y0:y1, x0:x1].astype(int)
    cx, cy = sum(xs) / 4 - x0, sum(ys) / 4 - y0
    yy, xx = np.mgrid[0:win.shape[0], 0:win.shape[1]]
    inner = (np.abs(xx - cx) <= (max(xs) - min(xs)) / 2) & (np.abs(yy - cy) <= (max(ys) - min(ys)) / 2)
    ring = ~inner
    bg = _median_color(win, ring)
    dist = np.sqrt(((win - np.array(bg)) ** 2).sum(axis=2))
    ink = dist > np.percentile(dist[inner], 70) if inner.any() else dist > 60
    if ink.sum() < 4:
        ink = dist > 40
    # 主色聚类取墨色: 中位色会被混入的走廊色拉偏, 文字本身是单一主色
    q = (win // 24).astype(np.int64)
    keys2d = q[:, :, 0] * 65536 + q[:, :, 1] * 256 + q[:, :, 2]
    dominant = np.bincount(keys2d[ink]).argmax()
    main = ink & (keys2d == dominant)
    fg = _median_color(win, main)
    # 墨迹尺寸只量主色簇: OCR 框压到走廊/邻图时, 全部 ink 像素会把宽高撑大
    if main.sum() >= 4:
        iy, ix = np.where(main)
        ink_w = float(np.percentile(ix, 98) - np.percentile(ix, 2))
        ink_h = float(np.percentile(iy, 98) - np.percentile(iy, 2))
    else:
        ink_w = ink_h = 0.0
    return '#%02x%02x%02x' % fg, '#%02x%02x%02x' % bg, ink_w, ink_h


_fit_font = None  # 进程级缓存


def _fit_font_size(text, ink_w, ink_h):
    """用本机 YaHei 字体量测, 让回填文字的墨迹宽高都贴近原尺寸; 宽高约束取小者
    (不超出原占位)。字体不可用退回 0.92×框高经验值。"""
    global _fit_font
    fallback = ink_h * 0.92 if ink_h else 16.0
    if _fit_font is None:
        from PIL import ImageFont
        _fit_font = False
        for p in (r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\simhei.ttf'):
            try:
                _fit_font = ImageFont.truetype(p, 100)
                break
            except Exception:
                continue
    if not _fit_font:
        return fallback
    bx = _fit_font.getbbox(text)
    bw, bh = bx[2] - bx[0], bx[3] - bx[1]
    cands = [100.0 * ink_w / bw] if bw > 0 else []
    if bh > 0:
        cands.append(100.0 * ink_h / bh)
    cands = [c for c in cands if c > 0]
    return min(cands) if cands else fallback


def _clean_text(s):
    """剥掉尾部未配对的开括号/识别噪声字 (如「广州塔（」「广州塔〇」)。"""
    s = s.strip()
    while s and s[-1] in '（(【[〔｛《〈「『〇':
        s = s[:-1].rstrip()
    return s


def _bbox(quad):
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    return (min(xs), min(ys), max(xs), max(ys))


def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if not inter:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


def ocr_regions(img, score, scale=1):
    """分块 OCR (大图整图喂 det 会被内部 limit_side_len 压缩丢小字)。
    scale>1 时先放大再检测识别 (照片小号编号牌必需), 坐标全部折回原生空间。
    返回 [{text, quad, cx, cy, w, h, angle, score, fs, fill, bg}]。"""
    engine = get_ocr()
    if engine is None:
        return None
    scale = scale or 1
    rgb = np.asarray(img)  # 原生空间: 取色/量字号都在这里做
    if scale > 1:
        big = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
        arr = np.ascontiguousarray(np.asarray(big)[:, :, ::-1])
    else:
        arr = np.ascontiguousarray(rgb[:, :, ::-1])  # BGR 副本: rapidocr 走 cv2 口径
    H, W = arr.shape[:2]
    TILE, OVERLAP = 1200, 140
    found = {}
    t0 = time.time()
    for y0 in range(0, H, TILE - OVERLAP):
        for x0 in range(0, W, TILE - OVERLAP):
            tile = np.ascontiguousarray(arr[y0:y0 + TILE, x0:x0 + TILE])
            res, _ = engine(tile)
            for box, text, sc in (res or []):
                if float(sc) < score or not text.strip():
                    continue
                quad = [((px + x0) / scale, (py + y0) / scale) for px, py in box]
                cx, cy, w, h, ang = _quad_metrics(quad)
                key = (text, round(cx / 12), round(cy / 12))
                if key in found:
                    continue
                found[key] = dict(text=text, quad=quad, cx=cx, cy=cy, w=w, h=h,
                                  angle=ang, score=float(sc))
    out = []
    for r in found.values():
        pad = max(2, int(r['h'] * 0.12))
        fill, bg, ink_w, ink_h = _sample_text_colors(rgb, r['quad'], pad)
        r['fill'], r['bg'] = fill, bg
        # 倾斜文字的墨迹是轴对齐测量, 按倾角还原到基线方向再匹配字号
        if abs(r['angle']) > 2.5:
            s = max(0.5, abs(math.cos(math.radians(r['angle']))))
            ink_w, ink_h = ink_w / s, ink_h / s
        r['fs'] = _fit_font_size(r['text'], ink_w, ink_h)
        out.append(r)
    # 二次去重: 瓦片重叠区同一文字两次识别文本常不同 (全角/半角括号),
    # 键去重拦不住, 按框 IoU>0.5 留高置信度那条
    out.sort(key=lambda r: -r['score'])
    kept = []
    for r in out:
        bb = _bbox(r['quad'])
        if not any(_iou(bb, _bbox(k['quad'])) > 0.5 for k in kept):
            kept.append(r)
    for r in kept:
        r['text'] = _clean_text(r['text'])
    kept = [r for r in kept if r['text']]
    kept.sort(key=lambda r: (r['cy'], r['cx']))
    print('  OCR: %d 条文字, %.1fs' % (len(kept), time.time() - t0))
    return kept


def mask_text(img, regions):
    """把文字块从底图抹除 (按四角点外扩画底色多边形), 抹完再描摹, 文字不再变轮廓。
    图例带内抹字框加宽 (重采样后字形光晕更散, 抹窄了会留残迹配出重影)。"""
    im = img.copy()
    d = ImageDraw.Draw(im)
    band_y = img.height * 0.70
    for r in regions:
        factor = 0.30 if r['cy'] > band_y else 0.18
        pad = max(3, r['h'] * factor)
        cx, cy = r['cx'], r['cy']
        poly = []
        for px, py in r['quad']:
            vx, vy = px - cx, py - cy
            n = math.hypot(vx, vy) or 1
            poly.append((px + vx / n * pad, py + vy / n * pad))
        d.polygon(poly, fill=r['bg'] if isinstance(r['bg'], tuple) else tuple(int(r['bg'][i:i + 2], 16) for i in (1, 3, 5)))
    return im


def trace_svg_text(im, out, mode, speckle, layer_diff, precision):
    fd, tmp = tempfile.mkstemp(suffix='.png')
    os.close(fd)
    try:
        im.save(tmp)
        vtracer.convert_image_to_svg_py(
            tmp, out,
            colormode='binary' if mode == 'binary' else 'color',
            # cutout: 各 path 裁到自己的可见区域, 互不叠压 → assemble_svg 才能安全按色重组
            hierarchical='cutout', mode=mode if mode != 'binary' else 'spline',
            filter_speckle=speckle, color_precision=6, layer_difference=layer_diff,
            corner_threshold=60, length_threshold=4.0, max_iterations=10,
            splice_threshold=45, path_precision=precision)
    finally:
        os.remove(tmp)
    with open(out, 'r', encoding='utf-8') as f:
        return f.read()


def _esc(s):
    return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def _snap_fill(hex_color, palette):
    """描摹聚类平均色 → 吸附到量化调色板最近色: 同一线路的各区域色归并同层。"""
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    p = min(palette, key=lambda c: (c[0] - r) ** 2 + (c[1] - g) ** 2 + (c[2] - b) ** 2)
    return '#%02X%02X%02X' % p


_LINE_TABLE = None


def _line_table():
    """广州线路色表 {颜色大写: 线名}, 来自 data/quiz-network-data.js; 缺文件给空表。"""
    global _LINE_TABLE
    if _LINE_TABLE is None:
        _LINE_TABLE = {}
        try:
            js = open(os.path.join(ROOT, 'data', 'quiz-network-data.js'), encoding='utf-8').read()
            for m in re.finditer(r'\{"name": "([^"]+)", "disp": "[^"]*", "color": "(#[0-9A-Fa-f]{6})"\}', js):
                _LINE_TABLE[m.group(2).upper()] = m.group(1)
        except OSError:
            pass
    return _LINE_TABLE


def _line_name(hex_color, tol_sq=None):
    """最近线路色查线名 (量化吸附有色差, 精确匹配会大面积落空), 容差外不给名。
    tol_sq 缺省宽松 (注 data-line 用); 图例色块候选应传紧容差防灰牌撞色。"""
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    tol = tol_sq if tol_sq is not None else 3 * 28 ** 2
    best, bd = None, 1 << 30
    for cs, name in _line_table().items():
        d = ((int(cs[1:3], 16) - r) ** 2 + (int(cs[3:5], 16) - g) ** 2
             + (int(cs[5:7], 16) - b) ** 2)
        if d < bd:
            best, bd = name, d
    return best if bd <= tol else None


def _text_kind(t):
    """OCR 文本分类: 站点序号 / 线路徽标 / 站名文字。"""
    t = t.strip()
    if re.fullmatch(r'[0-9]{1,4}(?:-[0-9]{1,4})?', t):
        return 'code'
    if '号线' in t or (t.endswith('线') and len(t) <= 5) or re.fullmatch(r'(GF|APM|THZ?[0-9]?)', t):
        return 'badge'
    return 'name'


def _regularize_legend(chips, regions, H):
    """图例带统一规整: 纸张褶皱造成图例局部变形 (透视矫正救不了非刚性)。
    色块 → 行聚类 + 列聚类 → 等距节距网格重排: 行列间距一致、行列对齐、
    形状统一为全图中位尺寸; 图例文字贴行轴、强制水平。
    行一致性守卫: 以块数最多的行作列锚, 其余行 ≥3 块且 ≥60% 落列才接纳——
    地图边缘撞线路色的杂牌小件退回原位, 不产生幽灵网格块。
    返回 (rect串, 落选色块, 网格参数 or None); 落选件由调用方回普通分类。"""
    rejected = []
    if len(chips) < 8:
        return [], chips, None
    # 尺寸基准从面积上半区取: 候选池常混小杂牌, 全体中位会被拉偏,
    # 真图例块 (大件) 反而被尺寸过滤误杀
    areas = sorted((bb[2] - bb[0]) * (bb[3] - bb[1]) for _, _, bb in chips)
    area_floor = areas[len(areas) // 2]
    big = [(p, k, bb) for p, k, bb in chips
           if (bb[2] - bb[0]) * (bb[3] - bb[1]) >= area_floor]
    medh = sorted(bb[3] - bb[1] for _, _, bb in big)[len(big) // 2]
    medw = sorted(bb[2] - bb[0] for _, _, bb in big)[len(big) // 2]
    keep = []
    for p, k, bb in chips:
        if (abs((bb[3] - bb[1]) - medh) <= medh * 0.55
                and abs((bb[2] - bb[0]) - medw) <= medw * 0.55):
            keep.append((p, k, bb))
        else:
            rejected.append((p, k, bb))
    chips = keep
    if len(chips) < 8:
        return [], rejected + chips, None

    def med(vals):
        return sorted(vals)[len(vals) // 2]

    def cluster(vals, tol):
        vals = sorted(vals)
        out, cur = [], [vals[0]]
        for v in vals[1:]:
            if v - cur[-1] > tol:
                out.append(med(cur))
                cur = []
            cur.append(v)
        out.append(med(cur))
        return out

    # 行聚类; <3 块的行不可能是图例行 (杂牌), 整行退回
    chips.sort(key=lambda t: (t[2][1] + t[2][3]) / 2)
    rows, cur = [], [chips[0]]
    for item in chips[1:]:
        c = (item[2][1] + item[2][3]) / 2
        if c - (cur[-1][2][1] + cur[-1][2][3]) / 2 > max(12, medh * 0.9):
            rows.append(cur)
            cur = []
        cur.append(item)
    if cur:
        rows.append(cur)
    solid = [r for r in rows if len(r) >= 3]
    for r in rows:
        if len(r) < 3:
            rejected.extend(r)
    if len(solid) < 2:
        return [], rejected, None

    # 列锚 = 最大行 (真图例行); 其余行 60% 落列才接纳
    solid.sort(key=lambda r: -len(r))
    seed = solid[0]
    cols = cluster([bb[0] for _, _, bb in seed], medw * 0.6)
    accepted = [seed]
    for row in solid[1:]:
        inl = sum(1 for _, _, bb in row
                  if min(abs(bb[0] - c) for c in cols) <= medw * 0.6)
        if len(row) >= 3 and inl >= 0.6 * len(row):
            accepted.append(row)
            cols = cluster([bb[0] for acc_row in accepted for _, _, bb in acc_row],
                           medw * 0.6)
        else:
            rejected.extend(row)
    if len(accepted) < 2 or len(cols) < 2:
        return [], rejected, None

    accepted.sort(key=lambda r: med([(bb[1] + bb[3]) / 2 for _, _, bb in r]))
    row_c = [med([(bb[1] + bb[3]) / 2 for _, _, bb in r]) for r in accepted]
    if len(row_c) > 1:
        pr = med([b - a for a, b in zip(row_c, row_c[1:])])
        row_c = [row_c[0] + i * pr for i in range(len(row_c))]
    pitch = med([b - a for a, b in zip(cols, cols[1:])])
    cols = [cols[0] + i * pitch for i in range(len(cols))]

    def near_col(x):
        return min(cols, key=lambda c: abs(c - x))

    rects = []
    for ri, row in enumerate(accepted):
        for p, key, bb in row:
            fill = re.search(r'fill="(#[0-9a-fA-F]{3,8})"', p)
            rects.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" rx="%.2f" '
                         'fill="%s" data-legend="1"/>'
                         % (near_col(bb[0]), row_c[ri] - medh / 2, medw, medh,
                            medh * 0.22, fill.group(1) if fill else key))
    # 图例文字: 只贴行轴 + 强制水平, x 保持原位 (透视矫正后水平位移仅数像素,
    # 原位不会压块; 启发式搬移文字反而会配错行/挤叠, 不做)
    for r in regions or []:
        ri = min(range(len(row_c)), key=lambda i: abs(row_c[i] - r['cy']), default=None)
        if ri is None or abs(row_c[ri] - r['cy']) > medh * 0.9:
            continue
        r['cy'] = row_c[ri]
        r['angle'] = 0.0
    return rects, rejected, (row_c, cols, medw, medh, pitch)


def _path_bbox(p):
    """path 包围盒: vtracer 输出为绝对坐标 + translate(x,y), 首点 M0 0。"""
    m = re.search(r'translate\(([-\d.]+)[,\s]+([-\d.]+)\)', p)
    tx, ty = (float(m.group(1)), float(m.group(2))) if m else (0.0, 0.0)
    dm = re.search(r'\sd="([^"]+)"', p)
    if not dm:
        return None
    nums = [float(v) for v in re.findall(r'-?\d+(?:\.\d+)?', dm.group(1))]
    if len(nums) < 4:
        return None
    xs, ys = nums[0::2], nums[1::2]
    return (tx + min(xs), ty + min(ys), tx + max(xs), ty + max(ys))


def assemble_svg(traced, regions, work_size, orig_size, palette=None, rails=None):
    """work 空间 = viewBox; 显示尺寸 = 原图像素。
    元件分层 (对齐全库 SVG 组织习惯):
      lines  路线走廊: 长路径按吸附调色板后的颜色分组 (≈每线一层, 挂 data-line)
      misc   其他: 认不到归属的小图形 (站圆/图例块/QR 点等)
      badges 线路徽标: 含"号线/线/GF/APM"的文字 + 压在其上的牌底图形
      codes  站点序号: 纯数字编号文字 + 压在其上的牌底图形
      text   站名文字 (置顶)
    cutout 模式保证 path 无叠压, 重组不破坏渲染。"""
    traced = re.sub(r'^<\?xml[^>]*\?>\s*', '', traced)
    traced = re.sub(r'<!--.*?-->', '', traced, flags=re.S)
    if 'viewBox' not in traced:
        traced = re.sub(r'<svg\b', '<svg viewBox="0 0 %d %d"' % work_size, traced, count=1)
    traced = re.sub(r'(<svg[^>]*?)\swidth="[^"]*"',
                    lambda m: m.group(1) + ' width="%d"' % orig_size[0], traced, count=1)
    traced = re.sub(r'(<svg[^>]*?)\sheight="[^"]*"',
                    lambda m: m.group(1) + ' height="%d"' % orig_size[1], traced, count=1)
    open_end = traced.index('>') + 1
    root = traced[:open_end]

    def qbox(r):
        xs = [p[0] for p in r['quad']]
        ys = [p[1] for p in r['quad']]
        pad = max(6.0, r['h'] * 0.3)
        return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)

    kind_boxes = {'badge': [], 'code': []}
    for r in regions or []:
        k = _text_kind(r['text'])
        if k in kind_boxes:
            kind_boxes[k].append(qbox(r))

    def hits(bb, boxes):
        return any(bb[0] < b[2] and bb[2] > b[0] and bb[1] < b[3] and bb[3] > b[1]
                   for b in boxes)

    small = max(work_size) * 0.025
    Hw = work_size[1]
    groups, order = {}, []
    gfx = {'badge': [], 'code': [], 'misc': []}

    def classify(p, key, bb):
        w = bb[2] - bb[0] if bb else 0
        h = bb[3] - bb[1] if bb else 0
        # 长路径 or 细长碎片(长宽比>4) 都是走廊件; 紧凑小件才按文字归属分类
        compact = bb and max(w, h) <= small and max(w, h) / max(1e-6, min(w, h)) <= 4
        if not compact:
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(re.sub(r'\s*fill="[^"]*"', '', p))
            return
        kind = 'misc'
        if bb:
            for k in ('badge', 'code'):
                if hits(bb, kind_boxes[k]):
                    kind = k
                    break
        gfx[kind].append(p)

    allitems = []
    for p in re.findall(r'<path\b[^>]*/>', traced[open_end:]):
        m = re.search(r'fill="(#[0-9a-fA-F]{3,8})"', p)
        if m:
            key = _snap_fill(m.group(1).upper(), palette) if palette else m.group(1).upper()
        else:
            key = '#000000'
        allitems.append((p, key, _path_bbox(p)))

    legend_rects = []
    if rails:
        # 旧坐标微调式图例: 色块保持去皱后的实际位置 (仅压平为轴对齐 rect +
        # cy 对齐行轴 + 行内统一高), 文字保持原 x (贴行轴 + 水平), 不做网格重排
        row_ys = sorted(rails[0])
        medw, medh = rails[2], rails[3]

        def row_of(cy):
            ri = min(range(len(row_ys)), key=lambda i: abs(row_ys[i] - cy), default=None)
            if ri is not None and abs(row_ys[ri] - cy) <= 1.2 * medh:
                return ri
            return None

        by0, by1 = row_ys[0] - 2.4 * medh, row_ys[-1] + 2.4 * medh
        frags = []
        for p, key, bb in allitems:
            if not bb:
                classify(p, key, bb)
                continue
            cy = (bb[1] + bb[3]) / 2
            if by0 < cy < by1:
                ri = row_of(cy)
                if ri is not None and (bb[2] - bb[0]) <= 2.5 * medw \
                        and (bb[3] - bb[1]) <= 1.6 * medh:
                    frags.append([ri, bb, p, key])
                    continue
            classify(p, key, bb)
        # 同行相邻碎片合并 (填充片+描边片间距始终小于块距): 并出整块 bbox,
        # 取色度最高碎片上色 — 否则一个色块画成几条并列色板
        frags.sort(key=lambda f: (f[0], f[1][0]))
        merged = []
        for ri, bb, p, key in frags:
            if merged and merged[-1][0] == ri and bb[0] - merged[-1][1][2] <= 0.35 * medw:
                mb = merged[-1][1]
                merged[-1][1] = (mb[0], min(mb[1], bb[1]), max(mb[2], bb[2]),
                                 max(mb[3], bb[3]))
                merged[-1][2].append((p, key))
            else:
                merged.append([ri, bb, [(p, key)]])
        for ri, (bx0, by0_, bx1, by1_), members in merged:
            best = None
            for p2, key2 in members:
                m2 = re.search(r'fill="(#[0-9a-fA-F]{3,8})"', p2)
                f = (m2.group(1) if m2 else key2).upper()
                r_, g_, b_ = int(f[1:3], 16), int(f[3:5], 16), int(f[5:7], 16)
                ch = max(r_, g_, b_) - min(r_, g_, b_)
                if best is None or ch > best[0]:
                    best = (ch, f)
            legend_rects.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" '
                                'rx="%.2f" fill="%s" data-legend="1"/>'
                                % (bx0, row_ys[ri] - medh / 2, bx1 - bx0, medh,
                                   medh * 0.22, best[1]))
        name2color = {v: k for k, v in _line_table().items()}
        for r in regions or []:
            ri = row_of(r['cy'])
            if ri is None:
                continue
            r['cy'] = row_ys[ri]
            r['angle'] = 0.0
            name = next((nm for nm in sorted(name2color, key=len, reverse=True)
                         if nm in r['text']), None)
            if not name:
                continue
            lx = min(p[0] for p in r['quad'])
            near = [(i, e) for i, e in enumerate(merged) if e[0] == ri
                    and -medw * 0.5 <= lx - e[1][2] <= 1.4 * medw]
            if near:
                i, e = min(near, key=lambda t: lx - t[1][1][2])
                legend_rects[i] = re.sub(r'fill="[^"]*"',
                                         'fill="%s"' % name2color[name],
                                         legend_rects[i])
            else:
                x0 = lx - medw * 0.35 - medw
                legend_rects.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" '
                                    'rx="%.2f" fill="%s" data-legend="1"/>'
                                    % (x0, row_ys[ri] - medh / 2, medw, medh,
                                       medh * 0.22, name2color[name]))
    else:
        cand_chips, others = [], []
        for p, key, bb in allitems:
            # 底部图例带的线路色块: 抽出做网格规整; 紧容差防地图杂牌撞色混入
            if bb and bb[3] > Hw * 0.70 and _line_name(key, 3 * 20 ** 2):
                cand_chips.append((p, key, bb))
                continue
            others.append((p, key, bb))
        legend_rects, rejected, grid = _regularize_legend(cand_chips, regions, Hw)
        for item in rejected:
            classify(*item)
        if not grid:
            for item in others:
                classify(*item)
        else:
            # 网格区内的小残件一律弃用 (合成图例层全权负责)
            row_c, cols, medw, medh, pitch = grid
            gy0, gy1 = row_c[0] - 2.0 * medh, row_c[-1] + 2.0 * medh
            gx0, gx1 = cols[0] - 1.5 * medw, cols[-1] + 0.55 * pitch
            box_right = cols[0] - 1.2 * medw
            best_box = None
            for p, key, bb in others:
                if not bb:
                    classify(p, key, bb)
                    continue
                if bb[1] > gy0 and bb[3] < gy1:
                    if gx0 < bb[0] and bb[2] < gx1:
                        continue
                    if (bb[2] < box_right and bb[2] - bb[0] > 3 * medh
                            and bb[3] - bb[1] > 2 * medh):
                        a = (bb[2] - bb[0]) * (bb[3] - bb[1])
                        if best_box is None or a > best_box[0]:
                            best_box = (a, p, key, bb)
                        continue
                classify(p, key, bb)
            if best_box:
                _, p, key, bb = best_box
                m = re.search(r'fill="(#[0-9a-fA-F]{3,8})"', p)
                legend_rects.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" '
                                    'rx="%.2f" fill="%s" data-box="1"/>'
                                    % (bb[0], bb[1], bb[2] - bb[0], bb[3] - bb[1],
                                       medh * 0.35, m.group(1) if m else key))

    def text_el(r):
        rot = ''
        if abs(r['angle']) > 2.5:  # <2.5° 视为检测框噪声, 水平文字不歪
            rot = ' transform="rotate(%.2f %.2f %.2f)"' % (r['angle'], r['cx'], r['cy'])
        return ('<text x="%.2f" y="%.2f" font-size="%.2f" fill="%s"%s>%s</text>'
                % (r['cx'], r['cy'], r['fs'], r['fill'], rot, _esc(r['text'])))

    ltable = _line_table()
    parts = ['<g id="lines">']
    for k in order:
        ln = _line_name(k)
        parts.append('<g fill="%s" data-color="%s"%s>%s</g>'
                     % (k, k, ' data-line="%s"' % ln if ln else '', ''.join(groups[k])))
    parts.append('</g>')
    parts.append('<g id="misc">%s</g>' % ''.join(gfx['misc']))
    parts.append('<g id="badges" font-family=\'%s\' text-anchor="middle" '
                 'dominant-baseline="central">%s%s</g>'
                 % (FONT_STACK, ''.join(gfx['badge']),
                    ''.join(text_el(r) for r in (regions or [])
                            if _text_kind(r['text']) == 'badge')))
    parts.append('<g id="codes" font-family=\'%s\' text-anchor="middle" '
                 'dominant-baseline="central">%s%s</g>'
                 % (FONT_STACK, ''.join(gfx['code']),
                    ''.join(text_el(r) for r in (regions or [])
                            if _text_kind(r['text']) == 'code')))
    if legend_rects:
        # 图例合成层贴近顶层: 网格区视觉由它全权负责, 杂件残迹不外露
        parts.append('<g id="legend">%s</g>' % ''.join(legend_rects))
    parts.append('<g id="text" font-family=\'%s\' text-anchor="middle" '
                 'dominant-baseline="central">%s</g>'
                 % (FONT_STACK, ''.join(text_el(r) for r in (regions or [])
                                        if _text_kind(r['text']) == 'name')))
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + root + ''.join(parts) + '</svg>'


TUNE_TMPL = """<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>SVG 微调 - __NAME__</title>
<style>
body{margin:0;display:flex;height:100vh;font:13px/1.5 "Microsoft YaHei",sans-serif;background:#f1f5f9}
#stage{flex:1;overflow:auto;padding:16px;background:#fff;position:relative}
#stage.grab{cursor:grabbing}
#stage svg{box-shadow:0 0 0 1px #cbd5e1;display:block}
#stage svg text{cursor:move}
#zbar{position:sticky;top:0;left:0;z-index:9;height:0}
#zbar div{display:inline-flex;background:#0f172aCC;border-radius:6px;margin:10px 0 0 10px;overflow:hidden}
#zbar button{margin:0;border-radius:0;padding:5px 12px;background:transparent;color:#e2e8f0;border:0;
border-right:1px solid #334155;cursor:pointer;font:14px/1.4 inherit}
#zbar button:hover{background:#0ea5e9}
#panel{width:290px;padding:12px 14px;background:#0f172a;color:#e2e8f0;overflow-y:auto;flex-shrink:0}
#panel h3{margin:2px 0 10px;font-size:14px;color:#7dd3fc}
#panel label{display:block;margin:8px 0 2px;color:#94a3b8}
#panel textarea,#panel input{width:100%;box-sizing:border-box;background:#1e293b;color:#e2e8f0;
border:1px solid #334155;border-radius:4px;padding:4px 6px;font:inherit}
#panel textarea{resize:vertical}
#panel .row{display:flex;gap:8px}
#panel button{margin:10px 4px 0 0;padding:5px 12px;border:0;border-radius:4px;cursor:pointer;
background:#0ea5e9;color:#fff;font:inherit}
#panel button.gray{background:#334155}
#panel button.red{background:#dc2626}
#panel button.on{background:#f59e0b;color:#111}
#list{margin-top:12px;max-height:38vh;overflow-y:auto;border-top:1px solid #334155}
#list div{padding:3px 6px;cursor:pointer;border-radius:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#list div:hover{background:#1e293b}
#list div.cur{background:#0ea5e9;color:#fff}
#hint{margin-top:10px;color:#64748b;font-size:12px}
</style></head><body>
<div id="stage"><div id="zbar"><div>
<button data-act="in" title="放大">＋</button><button data-act="out" title="缩小">－</button>
<button data-act="fit" title="整图适配窗口">适应</button><button data-act="one" title="原始像素">1:1</button>
</div></div>__SVG__</div>
<div id="panel">
<h3>文字微调</h3>
<label>内容 (双击画布文字也可聚焦)</label><textarea id="pc" rows="2"></textarea>
<label>字号 <input id="pz" type="number" step="1" style="width:90px">
颜色 <input id="pc2" type="color" style="width:46px;height:26px;padding:0;vertical-align:middle"></label>
<label>X <input id="px" type="number" step="1" style="width:80px">
Y <input id="py" type="number" step="1" style="width:80px"></label>
<button id="badd">＋ 新增文字</button><button id="bdel" class="red">删除</button>
<button id="bexp">导出 SVG</button><button id="bnone" class="gray">取消选中</button>
<div id="list"></div>
<div id="hint">拖动移动 · 方向键微移(Shift×10) · Ctrl+方向键微调字号 · Del 删除 · 导出后用下载文件覆盖同名 .svg</div>
</div>
<script>
const NS='http://www.w3.org/2000/svg';
const svg=document.querySelector('#stage svg');
const layer=svg.querySelector('#text');
const all=()=>[...svg.querySelectorAll('text')];
let cur=null,addMode=false;
const $=id=>document.getElementById(id);
const selbox=document.createElementNS(NS,'rect');
selbox.setAttribute('fill','none');selbox.setAttribute('stroke','#f59e0b');
selbox.setAttribute('stroke-dasharray','5 4');selbox.setAttribute('pointer-events','none');
selbox.style.display='none';
svg.appendChild(selbox);
const st=document.getElementById('stage');
let scale=0;
const vbW=()=>svg.viewBox.baseVal.width, vbH=()=>svg.viewBox.baseVal.height;
function fitScale(){return Math.min((st.clientWidth-32)/vbW(),(st.clientHeight-32)/vbH())}
function applyScale(){svg.style.width=(vbW()*scale)+'px';svg.style.height='auto'}
function zoomAt(f,cx,cy){const base=scale||fitScale();
 scale=Math.min(12,Math.max(0.05,base*f));
 if(cx===undefined){applyScale();return}
 const r=st.getBoundingClientRect();
 const kx=cx-r.left+st.scrollLeft, ky=cy-r.top+st.scrollTop;
 st.scrollLeft=kx*scale/base-(cx-r.left); st.scrollTop=ky*scale/base-(cy-r.top);
 applyScale()}
scale=fitScale();applyScale();
st.addEventListener('wheel',e=>{e.preventDefault();
 zoomAt(Math.exp(-e.deltaY*0.0016),e.clientX,e.clientY)},{passive:false});
document.querySelectorAll('#zbar button').forEach(b=>b.onclick=()=>{
 const act=b.dataset.act;
 if(act==='in')zoomAt(1.25);
 else if(act==='out')zoomAt(0.8);
 else if(act==='fit'){scale=fitScale();applyScale()}
 else{scale=1;applyScale()}});
function drawSel(){if(!cur){selbox.style.display='none';return}
 const b=cur.getBBox();selbox.style.display='';
 selbox.setAttribute('x',b.x-3);selbox.setAttribute('y',b.y-3);
 selbox.setAttribute('width',b.width+6);selbox.setAttribute('height',b.height+6)}
function syncPanel(){const on=!!cur;
 ['pc','pz','pc2','px','py'].forEach(i=>$(i).disabled=!on);
 $('bdel').disabled=!on;
 if(!on)return;
 $('pc').value=cur.textContent;$('pz').value=cur.getAttribute('font-size');
 let f=cur.getAttribute('fill')||'#000';
 if(/^#[0-9a-f]{3}$/i.test(f))f='#'+[...f.slice(1)].map(c=>c+c).join('');
 $('pc2').value=f;$('px').value=(+cur.getAttribute('x')).toFixed(1);$('py').value=(+cur.getAttribute('y')).toFixed(1)}
function buildList(){const l=$('list');l.innerHTML='';
 all().forEach((t,i)=>{const d=document.createElement('div');
  d.textContent=(i+1)+'. '+t.textContent;
  if(t===cur)d.className='cur';
  d.onclick=()=>{select(t);t.scrollIntoView({block:'center',behavior:'smooth'})};l.appendChild(d)})}
function select(t){cur=t;drawSel();syncPanel();buildList();
 if(t)setTimeout(()=>$('pc').focus(),0)}
svg.addEventListener('pointerdown',e=>{
 const t=e.target.closest('text');
 if(t){select(t);
  const sx=e.clientX,sy=e.clientY,ox=+cur.getAttribute('x'),oy=+cur.getAttribute('y');
  const k=svg.viewBox.baseVal.width/svg.getBoundingClientRect().width;
  const mv=ev=>{cur.setAttribute('x',(ox+(ev.clientX-sx)*k).toFixed(2));
   cur.setAttribute('y',(oy+(ev.clientY-sy)*k).toFixed(2));drawSel();syncPanel()};
  const up=()=>{removeEventListener('pointermove',mv);removeEventListener('pointerup',up)};
  addEventListener('pointermove',mv);addEventListener('pointerup',up);e.preventDefault()}
 else if(addMode){const p=svg.createSVGPoint();p.x=e.clientX;p.y=e.clientY;
  const loc=p.matrixTransform(svg.getScreenCTM().inverse());
  const t=document.createElementNS(NS,'text');
  t.setAttribute('x',loc.x.toFixed(2));t.setAttribute('y',loc.y.toFixed(2));
  t.setAttribute('font-size',24);t.setAttribute('fill','#333333');t.textContent='新文字';
  layer.appendChild(t);addMode=false;$('badd').classList.remove('on');select(t)}
 else{const sx0=e.clientX,sy0=e.clientY,sl=st.scrollLeft,stp=st.scrollTop;let panned=false;
  st.classList.add('grab');
  const mv=ev=>{st.scrollLeft=sl-(ev.clientX-sx0);st.scrollTop=stp-(ev.clientY-sy0);
   if(Math.hypot(ev.clientX-sx0,ev.clientY-sy0)>4)panned=true};
  const up=()=>{removeEventListener('pointermove',mv);removeEventListener('pointerup',up);
   st.classList.remove('grab');if(!panned)select(null)};
  addEventListener('pointermove',mv);addEventListener('pointerup',up)}});
$('pc').addEventListener('input',()=>{if(cur){cur.textContent=$('pc').value;drawSel();buildList()}});
$('pz').addEventListener('input',()=>{if(cur){cur.setAttribute('font-size',$('pz').value||24);drawSel()}});
$('pc2').addEventListener('input',()=>{if(cur)cur.setAttribute('fill',$('pc2').value)});
for(const id of['px','py'])$(id).addEventListener('input',()=>{
 if(cur){cur.setAttribute(id,$(id).value||0);drawSel()}});
$('badd').onclick=()=>{addMode=!addMode;$('badd').classList.toggle('on',addMode)};
$('bdel').onclick=()=>{if(cur){cur.remove();select(null)}};
$('bnone').onclick=()=>select(null);
$('bexp').onclick=()=>{const c=svg.cloneNode(true);
 const b=c.querySelector('rect');if(b&&b.getAttribute('pointer-events')==='none')b.remove();
 const s='<?xml version="1.0" encoding="UTF-8"?>\\n'+new XMLSerializer().serializeToString(c);
 const a=document.createElement('a');
 a.href=URL.createObjectURL(new Blob([s],{type:'image/svg+xml'}));
 a.download='__NAME__';a.click();URL.revokeObjectURL(a.href)};
document.addEventListener('keydown',e=>{
 if(/INPUT|TEXTAREA/.test(document.activeElement.tagName))return;
 if(!cur)return;
 const st=e.shiftKey?10:1,ct=e.ctrlKey;
 const mv={ArrowLeft:[-st,0],ArrowRight:[st,0],ArrowUp:[0,-st],ArrowDown:[0,st]}[e.key];
 if(mv){cur.setAttribute('x',(+cur.getAttribute('x')+mv[0]).toFixed(2));
  cur.setAttribute('y',(+cur.getAttribute('y')+mv[1]).toFixed(2));drawSel();syncPanel();e.preventDefault()}
 else if(ct&&(e.key==='+'||e.key==='=')){cur.setAttribute('font-size',+cur.getAttribute('font-size')+1);drawSel();syncPanel();e.preventDefault()}
 else if(ct&&e.key==='-'){cur.setAttribute('font-size',Math.max(4,+cur.getAttribute('font-size')-1));drawSel();syncPanel();e.preventDefault()}
 else if(e.key==='Delete'||e.key==='Backspace'){cur.remove();select(null);e.preventDefault()}
 else if(e.key==='Escape')select(null)});
buildList();syncPanel();
</script></body></html>
"""


def render_preview(svg_text, out_png, max_side):
    """内联 SVG 包装页 + 无头 Edge 截图 (同 verify_card_pixel 渲染链, 无异步加载竞态)。"""
    if not os.path.exists(EDGE):
        raise FileNotFoundError('未找到 Edge: %s' % EDGE)
    ET.register_namespace('', NS)
    root = ET.fromstring(svg_text)
    vb = root.get('viewBox').split()
    w, h = float(vb[2]), float(vb[3])
    scale = min(1.0, max_side / max(w, h))
    W, H = max(1, round(w * scale)), max(1, round(h * scale))
    # vtracer 根节点无 viewBox: 只改 width/height 是裁切不是缩放, 必须补 viewBox
    root.set('viewBox', '0 0 %g %g' % (w, h))
    root.set('width', str(W))
    root.set('height', str(H))
    html_path = os.path.join(tempfile.gettempdir(), '_img2svg-wrap.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write('<!DOCTYPE html><html><head><meta charset="UTF-8"><style>'
                'html,body{margin:0;padding:0;background:#fff;overflow:hidden}</style>'
                '</head><body>%s</body></html>' % ET.tostring(root, encoding='unicode'))
    out_png = os.path.abspath(out_png)
    r = subprocess.run([EDGE, '--headless', '--disable-gpu', '--disable-lcd-text',
                        '--force-color-profile=srgb', '--force-device-scale-factor=1',
                        '--window-size=%d,%d' % (W, H), '--screenshot=%s' % out_png,
                        'file:///%s' % html_path.replace('\\', '/')],
                       capture_output=True, timeout=60)
    if not os.path.exists(out_png):
        raise RuntimeError('Edge 截图未产出 %s: %s' % (out_png, r.stderr.decode('utf-8', 'replace')[-500:]))
    return W, H


def make_compare(src, preview_png, out_png, W, H):
    """左原图右矢量渲染拼对照图。"""
    a = Image.open(src).convert('RGB').resize((W, H), Image.LANCZOS)
    b = Image.open(preview_png).convert('RGB')
    if b.size != (W, H):
        b = b.resize((W, H), Image.LANCZOS)
    gutter = 8
    canvas = Image.new('RGB', (W * 2 + gutter, H), (200, 200, 200))
    canvas.paste(a, (0, 0))
    canvas.paste(b, (W + gutter, 0))
    canvas.save(out_png)


def process(src, args):
    t0 = time.time()
    out = args.out or os.path.splitext(src)[0] + '.svg'
    work, orig_size, factor, prelog, palette, rails = prep_image(
        src, args.colors, args.binary, args.upscale, args.flatten_white, args.no_deskew)
    if prelog:
        print('  预处理: ' + prelog)

    regions = None
    if not args.no_ocr:
        oscale = args.ocr_scale or (2 if '照片模式' in prelog else 1)
        regions = ocr_regions(work, args.ocr_score, oscale)
        if regions is None:
            print('  提示: rapidocr 未安装 (pip install rapidocr_onnxruntime), 退化为文字轮廓描摹')

    trace_src = mask_text(work, regions) if regions else work
    svg = trace_svg_text(trace_src, out, args.mode or ('binary' if args.binary is not None else 'spline'),
                         args.speckle, args.layer_diff, args.precision)
    svg = assemble_svg(svg, regions or [], work.size, orig_size, palette, rails)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(svg)
    paths = svg.count('<path')
    fills = set(re.findall(r'fill="(#[0-9a-fA-F]{3,8})"', svg))
    texts = len(regions) if regions else 0
    print('%s  %dx%dpx%s -> %s  (%.1f KB, %d path, %d 色, %d 文字, %.1fs)'
          % (os.path.basename(src), orig_size[0], orig_size[1],
             ', 放大%d倍' % factor if factor else '', out,
             os.path.getsize(out) / 1024, paths, len(fills), texts, time.time() - t0))

    if texts and not args.no_tune:
        tune = os.path.splitext(out)[0] + '.svg.tune.html'
        html = TUNE_TMPL.replace('__SVG__', svg).replace('__NAME__', os.path.basename(out))
        with open(tune, 'w', encoding='utf-8') as f:
            f.write(html)
        print('  微调页: %s (拖动/改字/增删/导出)' % tune)

    if args.compare:
        preview = os.path.splitext(out)[0] + '.render.png'
        W, H = render_preview(svg, preview, args.max_side)
        cmp_png = os.path.splitext(out)[0] + '.compare.png'
        make_compare(src, preview, cmp_png, W, H)
        print('  对照图: %s (渲染 %dx%d)' % (cmp_png, W, H))


def main():
    ap = argparse.ArgumentParser(description='位图地铁线路图转 SVG (描摹 + OCR 文字 + 微调页)', add_help=True)
    ap.add_argument('images', nargs='+', help='输入图片 (png/jpg/bmp/webp), 可多张')
    ap.add_argument('-o', '--out', help='输出 SVG 路径 (仅单张输入时可用)')
    ap.add_argument('--colors', type=int, default=32, help='颜色量化档数, 0=关闭 (默认 32)')
    ap.add_argument('--mode', choices=['spline', 'polygon', 'none'], help='描摹模式 (默认 spline)')
    ap.add_argument('--binary', type=int, metavar='T', help='黑白二值描摹, T=墨色阈值 0-255')
    ap.add_argument('--upscale', type=float, help='放大倍数 (默认自动, 0=禁止)')
    ap.add_argument('--speckle', type=int, default=8, help='去斑点 px (默认 8)')
    ap.add_argument('--layer-diff', type=int, default=16, help='色层合并阈值 (默认 16)')
    ap.add_argument('--precision', type=int, default=2, help='坐标小数位 (默认 2)')
    ap.add_argument('--flatten-white', type=int, metavar='T', default=None,
                    help='照片模式阈值 (缺省=自动判定; 0=强制关闭; 数值=强制开启, 建议 180-210)')
    ap.add_argument('--no-deskew', action='store_true', help='跳过自动校斜')
    ap.add_argument('--ocr-score', type=float, default=0.45, help='OCR 置信度下限 (默认 0.45)')
    ap.add_argument('--ocr-scale', type=float, help='OCR 检测分辨率倍数 (缺省: 照片模式自动 2, 其余 1)')
    ap.add_argument('--no-ocr', action='store_true', help='不做 OCR, 文字随图形描成轮廓')
    ap.add_argument('--no-tune', action='store_true', help='不生成微调页')
    ap.add_argument('--max-side', type=int, default=1400, help='对照图最长边 (默认 1400)')
    ap.add_argument('--compare', action='store_true', help='输出原图|矢量 对照图')
    a = ap.parse_args()
    if a.out and len(a.images) > 1:
        ap.error('-o 只能配单张输入')
    for p in a.images:
        if not os.path.exists(p):
            print('输入不存在: %s' % p, file=sys.stderr)
            sys.exit(1)
    for p in a.images:
        process(p, a)


if __name__ == '__main__':
    main()
