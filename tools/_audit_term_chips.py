# -*- coding: utf-8 -*-
"""终点徽标方位审计 v2 (约定口径):
每个终点数字块 -> 最近标签 -> 该标签最近站圆;
违例 = 徽标堆叠轴(横/竖) != 文字↔圆点连线轴(横/竖)。
(徽标应在 连线的延长线上、背离圆点一侧、与文字块居中; 横向路线文字轴向时即横排)
用法: python tools/_audit_term_chips.py [线名...]  无参=全部
"""
import os, sys, io, glob, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from verify_card import load  # noqa: E402  实测标签盒口径=门禁

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def audit(path):
    audit.amb = []
    c = load(path)
    circles = [(x, y) for (x, y, r) in c['circles']]
    labels = [(lb['nm'], lb['x'], (lb['box'][1] + lb['box'][3]) / 2) for lb in c['labels']]
    chips = []
    for bdx in c['badges']:
        if bdx.get('mode') == 'chip':
            x0, y0, x1, y1 = bdx['box']
            chips.append(((x0 + x1) / 2, (y0 + y1) / 2))
    # 混淆度量: 每个标签最近的圆必须是自己名字的圆(邻站混淆=地铁图大坑)
    pos = {}
    import xml.etree.ElementTree as ET2
    ns2 = '{http://www.w3.org/2000/svg}'
    for g in c['root'].iter(ns2 + 'g'):
        if g.get('id') == '站圆':
            for el in g.iter(ns2 + 'circle'):
                if el.get('data-nm'):
                    pos[el.get('data-nm')] = (float(el.get('cx')), float(el.get('cy')))
    amb = []
    for lb in c['labels']:
        if lb['nm'] not in pos:
            continue
        ox, oy = pos[lb['nm']]
        bx, by = min(circles, key=lambda p: math.hypot(p[0] - lb['x'], p[1] - (lb['box'][1] + lb['box'][3]) / 2))
        if (round(bx, 1), round(by, 1)) != (round(ox, 1), round(oy, 1)):
            amb.append(lb['nm'])
    rows = []
    for ccx, ccy in chips:
        # 配对=门禁G8同款双口径邻接(竖排x窗/横排y窗±60, |gap-3|最小), 防密集区误配
        box_of = {(lb[0], round(lb[1],1), round(lb[2],1)): None for lb in labels}
        bl, bd = None, 1e9
        for lb in c['labels']:
            lcy = (lb['box'][1] + lb['box'][3]) / 2
            if abs(lb['x'] - ccx) <= 60:
                g1 = ccy + 6.75 - lb['box'][3]
                g2 = lb['box'][1] - (ccy - 6.75)
                if 0 < g1 < 15 or 0 < g2 < 15:
                    d = math.hypot(lb['x'] - ccx, lcy - ccy)
                    if d < bd:
                        bd, bl = d, (lb['nm'], lb['x'], lcy)
            if abs(lcy - ccy) <= 60:
                g1 = ccx + 6.75 - lb['box'][2]
                g2 = lb['box'][0] - (ccx - 6.75)
                if 0 < g1 < 15 or 0 < g2 < 15:
                    d = math.hypot(lb['x'] - ccx, lcy - ccy)
                    if d < bd:
                        bd, bl = d, (lb['nm'], lb['x'], lcy)
        if bl is None or bd > 90:
            rows.append(('?%.0f,%.0f' % (ccx, ccy), '?', '?', '无标签 d=%.0f' % bd, ''))
            continue
        bc, bcd = None, 1e9
        for x, y in circles:
            d = math.hypot(x - bl[1], y - bl[2])
            if d < bcd:
                bcd, bc = d, (x, y)
        ddx, ddy = bl[1] - bc[0], bl[2] - bc[1]
        ratio = max(abs(ddx), abs(ddy)) / max(1e-6, min(abs(ddx), abs(ddy)))
        conn_h = abs(ddx) > abs(ddy)
        ch_h = abs(ccx - bl[1]) > abs(ccy - bl[2])
        if ratio < 1.2:  # 45°对角终点: 两轴皆在刀锋上, 横竖均合法
            verdict = 'OK(斜)'
        else:
            verdict = 'OK' if conn_h == ch_h else '违例'
        rows.append((bl[0], '连线横' if conn_h else '连线竖',
                     '徽标横' if ch_h else '徽标竖', verdict, '圆距%.0f' % bcd))
    return rows

names = sys.argv[1:]
total_bad = 0
for path in sorted(glob.glob(os.path.join(ROOT, 'assets/lines/line-*.svg'))):
    base = os.path.basename(path)
    if base.startswith('line-color') or '-' in base.replace('line-', '').split('.')[0]:
        continue
    ln = base[5:-4]
    if names and ln not in names:
        continue
    rows = audit(path)
    bad = [r for r in rows if r[-2].startswith('违例')]
    total_bad += len(bad)
    print('== %s: chip%d 违例%d 混淆%d %s' % (ln, len(rows), len(bad), len(audit.amb), ' '.join(audit.amb) if audit.amb else ''))
    for r in rows:
        if r[-2] != 'OK':
            print('   %-8s %s %s %s %s' % r)
print('TOTAL违例:', total_bad)
