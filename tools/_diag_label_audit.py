# -*- coding: utf-8 -*-
"""45°站标签方位量测: 每站 -> 入射走廊段方向(度) / 现行标签偏移方位 / 法向该是哪。
用法: python tools/_diag_label_audit.py 卡1:站1,站2 卡2:站3 ..."""
import os, sys, io, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_card import load

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

def seg_dir(segs, x, y):
    """入射段方向: 段上点距圆<3 的段, 方向=沿段两个走向; 返回角度列表"""
    out = []
    for (x1, y1, x2, y2) in segs:
        # 点到线段距离
        vx, vy = x2 - x1, y2 - y1
        L2 = vx * vx + vy * vy or 1.0
        t = max(0.0, min(1.0, ((x - x1) * vx + (y - y1) * vy) / L2))
        if math.hypot(x1 + t * vx - x, y1 + t * vy - y) < 3.0:
            L = math.hypot(vx, vy) or 1.0
            out.append(math.degrees(math.atan2(vy, vx)) % 180)
    return out

for spec in sys.argv[1:]:
    card, sts = spec.rsplit(':', 1)
    c = load('assets/lines/line-%s.svg' % card)
    labels = {lb['nm']: lb for lb in c['labels']}
    import xml.etree.ElementTree as ET
    ns = '{http://www.w3.org/2000/svg}'
    circ_nm = {el.get('data-nm'): (float(el.get('cx')), float(el.get('cy')))
               for g in c['root'].iter(ns + 'g') if g.get('id') == '站圆'
               for el in g.iter(ns + 'circle') if el.get('data-nm')}
    for st in sts.split(','):
        # 找圆点: 站圆与该站标签最近
        lb = labels.get(st)
        if lb is None:
            print('%s %s: 无标签' % (card, st))
            continue
        lcx, lcy = (lb['box'][0] + lb['box'][2]) / 2, (lb['box'][1] + lb['box'][3]) / 2
        bx, by = circ_nm[st]
        dx, dy = lcx - bx, lcy - by
        ang = math.degrees(math.atan2(dy, dx))
        segs = seg_dir(c['segs'], bx, by)
        segs_s = ['%.0f°' % a for a in segs]
        print('%s %-6s 圆(%.0f,%.0f) 标签偏移(%+.0f,%+.0f) %.0f° | 入射段 %s'
              % (card, st, bx, by, dx, dy, ang, ' '.join(segs_s)))
