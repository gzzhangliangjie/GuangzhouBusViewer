# -*- coding: utf-8 -*-
"""单线卡片像素层验收门禁(T1)：经 8765 服务渲染 + 无头Edge截图 + 像素判定
用法: python tools/verify_card_pixel.py assets/lines/line-2号线.svg
前置: python -m http.server 8765 已在仓库根运行(8765 会死, 先查服务)
门禁: P1 渲染非空(走廊像素量)  P2 逐站文字存在  P3 文字-走廊/徽标不重叠
坑(勿重蹈): pymupdf 不渲 <line>; 蓝色掩码会被文字 ClearType 蓝边污染,
     判重叠必须按"文字行带"与"徽标矩形"分区量测, 不能全图蓝掩码求交。
"""
import os
import re
import sys
import time
import math
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_card import load, text_half_width  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8765
EDGE = r'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
SCALE = 2.0
MIN_TEXT_PX = 40          # 每站文字行最低墨量(2x渲染, 两字小站~165, 阈值按字数缩放后仍取保守值)
GAP_MIN_PX = 2.0          # 文字行带到走廊/徽标的像素净距下限(2x图)


def http_alive():
    try:
        urllib.request.urlopen('http://127.0.0.1:%d/' % PORT, timeout=2)
        return True
    except Exception:
        return False


def render(card_path):
    """内联 SVG 包装页截图: 无 img 异步加载竞速(此前灰图根因), 也不依赖 8765。"""
    NS = 'http://www.w3.org/2000/svg'
    ET.register_namespace('', NS)  # ns0: 前缀在 HTML 内联时整页拒渲, 必须保持默认命名空间
    c = load(card_path)
    vb = c['vb']
    W, H = int(vb[2] * SCALE), int(vb[3] * SCALE)
    nat_w, nat_h = c['root'].get('width'), c['root'].get('height')
    c['root'].set('width', str(W))
    c['root'].set('height', str(H))
    svg = ET.tostring(c['root'], encoding='unicode')
    c['root'].set('width', nat_w)
    c['root'].set('height', nat_h)
    tmpdir = os.path.join(ROOT, 'assets', 'lines', '_pixtmp')
    os.makedirs(tmpdir, exist_ok=True)
    html = os.path.join(tmpdir, '_wrap.html')
    with open(html, 'w', encoding='utf-8') as f:
        f.write('<!DOCTYPE html><html><head><meta charset="UTF-8"><style>'
                'html,body{margin:0;padding:0;background:#fff;overflow:hidden}</style>'
                '</head><body>%s</body></html>' % svg)
    png = os.path.join(tempfile.gettempdir(), '_cardpix.png')
    subprocess.run([EDGE, '--headless', '--disable-gpu', '--disable-lcd-text',
                    '--force-color-profile=srgb', '--force-device-scale-factor=1',
                    '--window-size=%d,%d' % (W, H), '--screenshot=%s' % png,
                    'file:///%s' % html.replace('\\', '/')], capture_output=True, timeout=60)
    im = np.array(Image.open(png).convert('RGB')).astype(int)
    shutil.rmtree(tmpdir, ignore_errors=True)
    return im, c


def _erode(mask, k):
    m = mask.copy()
    pads = [np.pad(m, k, mode='constant')[k + dk:k + m.shape[0] + dk, k + dl:k + m.shape[1] + dl]
            for dk in (-1, 0, 1) for dl in (-1, 0, 1)]
    return np.logical_and.reduce(pads) if k == 1 else _erode(np.logical_and.reduce(pads), k - 1)


def _dilate(mask, k):
    m = mask.copy()
    pads = [np.pad(m, k, mode='constant')[k + dk:k + m.shape[0] + dk, k + dl:k + m.shape[1] + dl]
            for dk in (-1, 0, 1) for dl in (-1, 0, 1)]
    return np.logical_or.reduce(pads) if k == 1 else _dilate(np.logical_or.reduce(pads), k - 1)


def run_gates(card_path):
    im, c = render(card_path)
    vb = c['vb']
    X0, Y0 = vb[0], vb[1]
    R = []

    def add(no, name, ok, detail=''):
        R.append((no, name, bool(ok), detail))

    def sv2px(x, y):
        return int((x - X0) * SCALE), int((y - Y0) * SCALE)

    dark = im.max(axis=2) < 150
    # 线色取走廊 stroke 样式色
    stroke = '#1E88E5'
    for el in c['root'].iter('{http://www.w3.org/2000/svg}line'):
        m = re.search(r'stroke:(#[0-9A-Fa-f]{6})', el.get('style') or '')
        if m:
            stroke = m.group(1)
            break
    rgb = tuple(int(stroke[i:i + 2], 16) for i in (1, 3, 5))
    line_mask = (abs(im[:, :, 0] - rgb[0]) < 60) & (abs(im[:, :, 1] - rgb[1]) < 60) & (abs(im[:, :, 2] - rgb[2]) < 60)
    # 文字 ClearType 亚像素蓝边会混进线色掩码: 走廊笔画2x下14px宽, 腐蚀3px后只剩实心走廊,
    # 再膨胀回去=纯走廊; 文字彩边(1-2px)腐蚀后即灭。
    corridor = _dilate(_erode(line_mask, 3), 3)

    # P1 渲染非空: 走廊像素量级(线色笔画宽7, 2x=14px, 长度~走廊弧长)
    total_line = line_mask.sum()
    seg_len = sum(math.hypot(s[2] - s[0], s[3] - s[1]) for s in c['segs'])
    expect = seg_len * 14 * 0.7
    add('P1', '渲染非空(走廊%.0fpx²)' % expect, total_line > expect * 0.6,
        '实测%.0f' % total_line)

    # P2 逐站文字存在: 标签盒内墨量
    missing = []
    for lb in c['labels']:
        x0, y0, x1, y1 = lb['box']
        px0, py0 = sv2px(x0, y0)
        px1, py1 = sv2px(x1, y1)
        zone = dark[max(py0, 0):py1, max(px0, 0):px1]
        need = MIN_TEXT_PX * max(1, len(lb['nm']) / 4)
        if zone.sum() < need:
            missing.append('%s(%d)' % (lb['nm'], zone.sum()))
    add('P2', '逐站文字墨量', not missing, '; '.join(missing) or '全%d站' % len(c['labels']))

    # P3 文字-走廊不重叠: 文字行带(含2px邻域)不得触及实心走廊笔画
    near = _dilate(corridor, 2)
    clash = []
    for lb in c['labels']:
        rows = [('zh', lb['x'], lb['zy'], 11.0, text_half_width(lb['nm'])),
                ('en', lb['x'], lb['ey'], 5.5, text_half_width(lb['en'], zh=False))]
        if lb.get('ey2') is not None:
            rows.append(('en2', lb['x'], lb['ey2'], 5.5, text_half_width(lb.get('en2', ''), zh=False)))
        for row in rows:
            _, tx, ty, hh, hw = row
            x0, y0, x1, y1 = tx - hw, ty - hh, tx + hw, ty + 1.5
            px0, py0 = sv2px(x0, y0)
            px1, py1 = sv2px(x1, y1)
            if px1 <= px0 or py1 <= py0:
                continue
            band = dark[max(py0, 0):py1, max(px0, 0):px1] & near[max(py0, 0):py1, max(px0, 0):px1]
            if band.size and band.sum() > 12:  # >12px² 扣散点噪声
                clash.append('%s%s行(%d)' % (lb['nm'], row[0], band.sum()))
    add('P3', '文字不压走廊', not clash, '; '.join(clash) or '全过')

    # P4 徽标区纯净: 徽标矩形内不得出现"深色且非徽标底色"的站名墨
    # (深色线色如8号线teal(0,137,123)本身max<150, 必须排除自身底色, 否则假阳性)
    badg = []
    for bd in c['badges']:
        # v7 官方头部徽标自带黑色字形: 纯净区=色块子区(data-chip); 终点chip/旧胶囊=整框
        reg = bd.get('chip') or bd['box']
        px0, py0 = sv2px(*reg[:2])
        px1, py1 = sv2px(reg[2], reg[3])
        zone = im[max(py0, 0):py1, max(px0, 0):px1]
        d = zone.max(axis=2) < 150
        notfill = ((abs(zone[:, :, 0] - rgb[0]) > 60) | (abs(zone[:, :, 1] - rgb[1]) > 60) |
                   (abs(zone[:, :, 2] - rgb[2]) > 60))
        ink = bd.get('ink')  # 亮底胶囊的深字是徽标自身墨色
        if ink and ink != '#FFFFFF':
            ir, ig, ib = int(ink[1:3], 16), int(ink[3:5], 16), int(ink[5:7], 16)
            notfill = notfill & ((abs(zone[:, :, 0] - ir) > 60) | (abs(zone[:, :, 1] - ig) > 60) |
                                 (abs(zone[:, :, 2] - ib) > 60))
        m = d & notfill
        if m.any():
            m = _erode(m, 1)  # ClearType亚像素边滤除(12号线深绿底白字1px彩边, 文档§3同款坑)
        n = int(m.sum())
        if n > 30:
            badg.append('徽标(%.0f,%.0f)内墨%d' % (reg[0], reg[1], n))
    add('P4', '徽标区无站名墨', not badg, '; '.join(badg) or '全过')

    return R


def main():
    if False and not http_alive():
        print('8765 服务未响应: 先在仓库根 `python -m http.server 8765`')
        sys.exit(2)
    R = run_gates(sys.argv[1] if len(sys.argv) > 1 else 'assets/lines/line-2号线.svg')
    npass = 0
    for no, name, ok, detail in R:
        print('  %-3s %-2s %-20s %s' % (no, '✓' if ok else '✗', name, detail))
        npass += ok
    print('像素门禁: %d/%d 通过' % (npass, len(R)))
    sys.exit(0 if npass == len(R) else 1)


if __name__ == '__main__':
    main()
