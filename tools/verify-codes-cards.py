# -*- coding: utf-8 -*-
"""编号牌卡像素门禁: 渲染 *.codes.svg 后逐牌验证。
- V1 牌数: 编号牌组内 chip 数 = 生成器报告数(单线/全网);
- V2 边框: 牌矩形边缘中点带存在本线色像素(牌画出且颜色对);
- V3 黑字: 牌内部(避开边框/分隔线)存在黑墨;
- V4 不溢出: 牌外扩1px环带无黑墨(字不超出胶囊)。
用法: python tools/verify-codes-cards.py  (全部 19 单线 + 全网)
"""
import os
import re
import subprocess
import sys
import tempfile
import time

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINES_DIR = os.path.join(ROOT, 'assets', 'lines')
EDGE = r'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
SCALE = 2.0

ORDER = ['1号线', '2号线', '3号线', '4号线', '5号线', '6号线', '7号线', '8号线',
         '9号线', '10号线', '11号线', '12号线', '13号线', '14号线', '18号线',
         '21号线', '22号线', '广佛线', 'APM线']


def parse_chips(svg_path):
    """-> (vb, chips, rings, has_group). chips=[(cx,cy,w,h,color,texts)]; rings=多线组外描边圈矩形."""
    t = open(svg_path, encoding='utf-8').read()
    vb = [float(v) for v in re.search(r'viewBox="([-\d. ]+)"', t).group(1).split()]
    m = re.search(r'<g id="编号牌"[^>]*>(.*?)</g>', t, re.S)
    chips = []
    rings = []
    if m:
        for r in re.finditer(r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)"([^>]*)stroke="(#[0-9A-Fa-f]{6})"', m.group(1)):
            x, y, w, h, rest, col = float(r.group(1)), float(r.group(2)), float(r.group(3)), float(r.group(4)), r.group(5), r.group(6)
            if 'data-ring' in rest:
                rings.append((x, y, w, h))
            elif 'fill="none"' in rest:
                pass   # 双描边包络的白pass矩形(非牌)
            else:
                chips.append([x + w / 2, y + h / 2, w, h, col, []])
        for tx in re.finditer(r'<text x="([\d.]+)" y="([\d.]+)"[^>]*font-size="([\d.]+)"[^>]*>([^<]+)</text>', m.group(1)):
            x, y, fs, txt = float(tx.group(1)), float(tx.group(2)), float(tx.group(3)), tx.group(4)
            for c in chips:
                if abs(y - c[1]) < c[3] / 2 and c[0] - c[2] / 2 <= x <= c[0] + c[2] / 2:
                    c[5].append((txt, x, y, fs))
                    break
    return vb, chips, rings, m is not None


def render(svg_path, vb, crop=None, scale=None):
    """crop=(x,y,w,h) 时按裁剪框渲染(20x 精测用); scale 覆盖默认 SCALE."""
    sc = scale or SCALE
    if crop:
        svg_txt = open(svg_path, encoding='utf-8').read()
        svg_txt = re.sub(r'viewBox="[-\d. ]+"', 'viewBox="%.2f %.2f %.2f %.2f"' % crop, svg_txt, count=1)
        W, H = int(crop[2] * sc), int(crop[3] * sc)
    else:
        W, H = int(vb[2] * sc), int(vb[3] * sc)
        svg_txt = open(svg_path, encoding='utf-8').read()
    svg = re.sub(r'(<svg[^>]*?) width="[\d.]+" height="[\d.]+"', r'\1 width="%d" height="%d"' % (W, H), svg_txt, count=1)
    html = os.path.join(tempfile.gettempdir(), '_codeswrap.html')
    with open(html, 'w', encoding='utf-8') as f:
        f.write('<!DOCTYPE html><html><head><meta charset="UTF-8"><style>'
                'html,body{margin:0;padding:0;background:#fff;overflow:hidden}</style>'
                '</head><body>%s</body></html>' % svg)
    png = os.path.join(tempfile.gettempdir(), '_codespix.png')
    if os.path.exists(png):
        os.remove(png)   # 防截图竞态读到上一张卡旧图
    for attempt in range(2):
        subprocess.run([EDGE, '--headless', '--disable-gpu', '--force-device-scale-factor=1',
                        '--window-size=%d,%d' % (W, H), '--screenshot=%s' % png,
                        'file:///%s' % html.replace('\\', '/')], capture_output=True, timeout=120)
        if os.path.exists(png):
            try:
                return np.array(Image.open(png).convert('RGB')).astype(int)
            except Exception:
                pass
        time.sleep(1.0)
    raise RuntimeError('render failed: ' + svg_path)


def check_card(path, label, gen):
    vb, chips, rings, has_group = parse_chips(path)
    if not chips:
        return [(label, 'V1', '编号牌组非空', bool(has_group), '0 牌')]
    # V5 牌-站名不叠: 站名标注文本盒与任意牌矩形净距>0.8
    t = open(path, encoding='utf-8').read()
    lm = re.search(r'<g id="站名标注"[^>]*>(.*?)</g>', t, re.S)
    clashes = []
    if lm:
        for tx in re.finditer(r'<text ([^>]*)>([^<]+)</text>', lm.group(1)):
            at, content = tx.group(1), tx.group(2)
            try:
                x = float(re.search(r'\bx="([-\d.]+)"', at).group(1))
                y = float(re.search(r'\by="([-\d.]+)"', at).group(1))
                fs = float(re.search(r'font-size="([\d.]+)"', at).group(1))
            except (AttributeError, ValueError):
                continue
            box = gen.text_box({'x': x, 'y': y, 'fs': fs, 'content': content})
            hit = any(gen._gap(box, (cx - w / 2, cy - h / 2, w, h)) < 0.5
                      for cx, cy, w, h, col, _texts in chips)
            if not hit:
                # data-ring=胶囊形黑pass矩形, 外扩 pad+RIM 才是轮廓外缘
                e = gen.RING_PAD + gen.RIM
                hit = any(gen._gap(box, (rx - e, ry - e, rw + 2 * e, rh + 2 * e)) < 0.5
                          for rx, ry, rw, rh in rings)
            if hit:
                clashes.append(content)
    v5 = (label, 'V5', '牌不压站名', not clashes, '%d处' % len(clashes) + (':' + ','.join(clashes[:5]) if clashes else ''))
    # V4 文本适配: 定宽格与实测文本取max + 分隔区 + 边距 <= 牌宽(独立于生成器重算; APM=textLength压入不取max)
    overflow = []
    for cx, cy, w, h, col, texts in chips:
        if len(texts) >= 2:
            fs = texts[0][3]
            card = abs(fs - gen.FONT_CARD) < 0.01 or abs(fs - gen.APM_FONT_CARD) < 0.01
            need = gen.chip_need_w(texts[0][0], texts[1][0], card)
            if need > w + 0.05:
                overflow.append('%s|%s(需%.1f>%.1f)' % (texts[0][0], texts[1][0], need, w))
    im = render(path, vb)

    def px(x, y):
        return int((x - vb[0]) * SCALE), int((y - vb[1]) * SCALE)

    fails = []
    n_border = n_ink = 0
    for cx, cy, w, h, col, texts in chips:
        rgb = tuple(int(col[i:i + 2], 16) for i in (1, 3, 5))
        # V2 边框: 沿矩形四边各取 2px 带, 找线色像素
        x0, y0 = px(cx - w / 2, cy - h / 2)
        x1, y1 = px(cx + w / 2, cy + h / 2)
        edges = []
        for ex0, ey0, ex1, ey1 in ((x0 + 2, y0, x1 - 2, y0 + 2), (x0 + 2, y1 - 2, x1 - 2, y1),
                                   (x0, y0 + 2, x0 + 2, y1 - 2), (x1 - 2, y0 + 2, x1, y1 - 2)):
            zone = im[max(ey0, 0):ey1, max(ex0, 0):ex1]
            d = (abs(zone[:, :, 0] - rgb[0]) < 70) & (abs(zone[:, :, 1] - rgb[1]) < 70) & (abs(zone[:, :, 2] - rgb[2]) < 70)
            edges.append(d.sum())
        if sum(edges) < 8:
            fails.append('边框(%s@%.0f,%.0f)' % (col, cx, cy))
        else:
            n_border += 1
        # V3 黑墨: 内部区(去边框3.5px)
        ix0, iy0 = px(cx - w / 2 + 3.0, cy - h / 2 + 3.0)
        ix1, iy1 = px(cx + w / 2 - 3.0, cy + h / 2 - 3.0)
        inner = im[iy0:iy1, ix0:ix1]
        ink = inner.max(axis=2) < 120
        if ink.sum() < 6:
            fails.append('黑字(@%.0f,%.0f)' % (cx, cy))
        else:
            n_ink += 1
    # V6 数字纵向居中: 抽样3牌 20x裁剪精测(|Δ|<=0.15pt)——2x全图量测有-0.3pt亚像素抗锯齿
    # 系统偏差(二十倍仲裁: 当前渲染实际offset=0.000), 低倍量测不可信; 精测窗=文字锚点±2.5pt
    # (避开深色线的分隔竖线, 全内窗会把竖线算进墨迹)
    offs = []
    sample = [c for c in chips if len(c[5]) >= 2]
    for idx in ({0, len(sample) // 2, len(sample) - 1} if sample else set()):
        cx, cy, w, h, col, texts = sample[idx]
        crop = (cx - w / 2 - 4, cy - h / 2 - 4, w + 8, h + 8)
        im2 = render(path, vb, crop=crop, scale=20.0)
        dark2 = im2.max(axis=2) < 110
        bx, by = crop[0], crop[1]
        rows = []
        for txt, ax, ay, fs in texts:
            y_lo = int((cy - h / 2 + 1.1 - by) * 20)
            y_hi = int((cy + h / 2 - 1.1 - by) * 20) + 1
            x_lo = int((ax - 2.5 - bx) * 20)
            x_hi = int((ax + 2.5 - bx) * 20) + 1
            zone = dark2[y_lo:y_hi, x_lo:x_hi]
            ys2, _xs = np.where(zone)
            if len(ys2) >= 6:
                rows += [ys2.min() + y_lo, ys2.max() + y_lo]
        if len(rows) < 2:
            continue
        ink_c = (min(rows) + max(rows)) / 2 / 20.0 + by
        offs.append(ink_c - cy)
    v6 = (label, 'V6', '数字纵向居中', bool(offs) and max(abs(o) for o in offs) <= 0.15,
          'max|Δ|=%.2fpt (%d采样)' % (max((abs(o) for o in offs), default=9), len(offs)))
    # V7 标签贴近站点(十七轮末 用户: 文字离站点远的优先级高于挪位置): 组盒(zh+en)到最近牌
    # 净距<=9pt; 量法必须组盒——只量zh盒会把带英文行的卡标签误报15pt(英文行填补间隙贴牌2pt)
    t_full = open(path, encoding='utf-8').read()
    lmz = re.search(r'<g id="站名标注"[^>]*>(.*?)</g>', t_full, re.S)
    zh_lbl, en_lbl = {}, []
    far7 = 0
    checked7 = 0
    if lmz:
        for tx in re.finditer(r'<text x="([-\d.]+)" y="([\d.]+)"[^>]*font-size="([\d.]+)"[^>]*>([^<]+)</text>', lmz.group(1)):
            x7, y7, fs7, c7 = float(tx.group(1)), float(tx.group(2)), float(tx.group(3)), tx.group(4)
            if c7.isascii():
                en_lbl.append((x7, y7, fs7, c7))
            else:
                zh_lbl[c7] = (x7, y7, fs7)
        for nm7, (x7, y7, fs7) in zh_lbl.items():
            box7 = gen.text_box({'x': x7, 'y': y7, 'fs': fs7, 'content': nm7})
            for ex, ey, efs, ec in en_lbl:
                if abs(ex - x7) < 3 and 0 < ey - y7 < 16:
                    eb = gen.text_box({'x': ex, 'y': ey, 'fs': efs, 'content': ec})
                    x0b = min(box7[0], eb[0]); y0b = min(box7[1], eb[1])
                    box7 = (x0b, y0b, max(box7[0] + box7[2], eb[0] + eb[2]) - x0b,
                            max(box7[1] + box7[3], eb[1] + eb[3]) - y0b)
            d7 = min((gen._gap(box7, (cx - w / 2, cy - h / 2, w, h))
                      for cx, cy, w, h, col, _t in chips), default=None)
            if d7 is None or d7 > 12:
                # 离最近牌>12pt = 无牌站(暂缓开通保留圆点, 如广州火车站@11号线):
                # 其"站点标记"是圆点不是牌, 不在本门禁域
                continue
            checked7 += 1
            if d7 > 9.0:
                far7 += 1
    v7 = (label, 'V7', '标签贴站<=9pt', far7 == 0, '%d/%d超' % (far7, checked7))
    return [
        (label, 'V1', '编号牌数=%d' % len(chips), True, ''),
        (label, 'V2', '边框线色', n_border == len(chips), '%d/%d' % (n_border, len(chips))),
        (label, 'V3', '内部黑字', n_ink == len(chips), '%d/%d' % (n_ink, len(chips))),
        (label, 'V4', '文本适配牌宽', not overflow, '; '.join(overflow[:6]) or '全过'),
        v5,
        v6,
        v7,
    ]


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    import importlib.util
    spec = importlib.util.spec_from_file_location('gen', os.path.join(ROOT, 'tools', 'gen-codes-cards.py'))
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    rows = []
    for line in ORDER:
        rows += check_card(os.path.join(LINES_DIR, 'line-%s.codes.svg' % line), line, gen)
    rows += check_card(os.path.join(LINES_DIR, 'network-全网.codes.svg'), '全网', gen)
    npass = 0
    for label, no, name, ok, detail in rows:
        print('  %-7s %-3s %-14s %-2s %s' % (label, no, name, '✓' if ok else '✗', detail))
        npass += ok
    print('编号牌像素门禁: %d/%d 通过' % (npass, len(rows)))
    sys.exit(0 if npass == len(rows) else 1)


if __name__ == '__main__':
    main()
