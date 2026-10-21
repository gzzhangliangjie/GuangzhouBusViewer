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
    c = load(path)
    circles = [(x, y) for (x, y, r) in c['circles']]
    labels = [(lb['nm'], lb['x'], (lb['box'][1] + lb['box'][3]) / 2) for lb in c['labels']]
    chips = []
    for bdx in c['badges']:
        if bdx.get('mode') == 'chip':
            x0, y0, x1, y1 = bdx['box']
            chips.append(((x0 + x1) / 2, (y0 + y1) / 2))
    rows = []
    for ccx, ccy in chips:
        bl, bd = None, 1e9
        for lb in labels:
            d = math.hypot(lb[1] - ccx, lb[2] - ccy)
            if d < bd:
                bd, bl = d, lb
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
    print('== %s: chip%d 违例%d' % (ln, len(rows), len(bad)))
    for r in rows:
        if r[-2] != 'OK':
            print('   %-8s %s %s %s %s' % r)
print('TOTAL违例:', total_bad)
