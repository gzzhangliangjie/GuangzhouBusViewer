# -*- coding: utf-8 -*-
"""站名文字 终版归一化(单一真源=codes SVG, 一次通过):
每站: 交叉轴吸附胶囊组心(居中) + 沿轴间隙归一2pt(同侧阶梯2/1.5/3/1.5/2.5, 对侧2备选)。
合法性全门禁: 胶囊/环0.5、走廊4.5、他文字1.0、徽标0.3。英文行随中文同delta。
不合法保留原位上报。用法: python tools/normalize-labels-final.py
"""
import io, os, re, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import importlib.util
spec = importlib.util.spec_from_file_location('gen', os.path.join(ROOT, 'tools', 'gen-codes-cards.py'))
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

F = 'assets/lines/network-全网.codes.svg'
t = open(F, encoding='utf-8').read()
chips, rings, _ = gen.chip_elements(t)
corridors = gen.corridor_segments(t)
badges = gen.badge_elements(t)
texts = gen.text_elements(t)
zh = [e for e in texts if not e['en']]
en = [e for e in texts if e['en']]

# 胶囊组聚类(中心距<=12) + 组盒(含1.9衬边)
centers = [(c[0] + c[2] / 2, c[1] + c[3] / 2) for c in chips]
groups = []
for c in centers:
    for g in groups:
        if any((c[0] - gc[0]) ** 2 + (c[1] - gc[1]) ** 2 <= 144 for gc in g):
            g.append(c)
            break
    else:
        groups.append([c])
ginfo = []
for g in groups:
    ginfo.append((sum(c[0] for c in g) / len(g),
                  sum(c[1] for c in g) / len(g),
                  min(c[0] for c in g) - 1.9, min(c[1] for c in g) - 1.9,
                  max(c[0] for c in g) + 1.9, max(c[1] for c in g) + 1.9))

def legal_box(box, self_nm):
    if any(gen._gap(box, c) < 0.5 for c in chips + rings):
        return False
    if any(gen.rect_seg_dist(box, s) < 4.5 for s in corridors):
        return False
    if any(gen._gap(box, (b['x'], b['y'], b['w'], b['h'])) < 0.3 for b in badges):
        return False
    for o in texts:
        if o['nm'] == self_nm:
            continue
        if gen._gap(box, o['box']) < 1.0:
            return False
    return True

# 每站: 计算目标位(交叉轴=组心, 沿轴=组边+2), 同侧阶梯+对侧备选, 全门禁
plan = []
for e in zh:
    box = e['box']
    tcx, tcy = box[0] + box[2] / 2, box[1] + box[3] / 2
    best, bg = 9e18, None
    for gi, (gx, gy, gx0, gy0, gx1, gy1) in enumerate(ginfo):
        dd = (tcx - gx) ** 2 + (tcy - gy) ** 2
        if dd < best:
            best, bg = dd, gi
    gx, gy, gx0, gy0, gx1, gy1 = ginfo[bg]
    dx, dy = tcx - gx, tcy - gy
    if abs(dx) >= abs(dy):
        side, ax = ('r' if dx > 0 else 'l'), 0
        cur = abs(dx) - box[2] / 2 - (gx1 - gx0) / 2
    else:
        side, ax = ('b' if dy > 0 else 'a'), 1
        cur = abs(dy) - box[3] / 2 - (gy1 - gy0) / 2
    sgn = 1 if cur > 0 else -1
    placed = None
    # 同侧阶梯(gap 2为基准) -> 对侧2 -> 保留
    for s2, g in [(sgn, 2.0), (sgn, 1.5), (sgn, 2.5), (sgn, 1.0), (sgn, 3.0),
                  (-sgn, 2.0), (-sgn, 3.0), (-sgn, 1.5)]:
        if ax == 0:
            ncx = gx + s2 * ((gx1 - gx0) / 2 + g + box[2] / 2)
            ncy = tcy
        else:
            ncx = tcx
            ncy = gy + s2 * ((gy1 - gy0) / 2 + g + box[3] / 2)
        nbox = (ncx - box[2] / 2, ncy - box[3] / 2, box[2], box[3])
        if legal_box(nbox, e['nm']):
            placed = (ncx, ncy, g, s2)
            break
    if placed:
        ncx, ncy, g, s2 = placed
        ddx, ddy = ncx - tcx, ncy - tcy
        if abs(ddx) > 0.3 or abs(ddy) > 0.3:
            plan.append((e, ncx, ncy, ddx, ddy, side, g, s2))
    else:
        plan.append((e, tcx, tcy, 0.0, 0.0, side, -1, -1))

print('计划: 移动%d 保留%d' % (len([p2 for p2 in plan if abs(p2[3]) + abs(p2[4]) > 0.3]),
                              len([p2 for p2 in plan if abs(p2[3]) + abs(p2[4]) <= 0.3])))
for e, ncx, ncy, ddx, ddy, side, g, s2 in plan:
    if abs(ddx) + abs(ddy) > 0.3:
        print('  %-8s 移(%.1f,%.1f) [%s侧 gap%g]' % (e['nm'], ddx, ddy, side, g))

# 应用: 替换文字元素(x/y在attrs内替换, 防x/y重复), 英文行随动
applied = 0
for e, ncx, ncy, ddx, ddy, side, g, s2 in plan:
    if abs(ddx) + abs(ddy) <= 0.3:
        continue
    new_attrs = re.sub(r'\bx="[-\d.]+"', 'x="%.2f"' % ncx, e['attrs'])
    new_attrs = re.sub(r'\by="[-\d.]+"', 'y="%.2f"' % (ncy + 0.36 * e['fs']), new_attrs)
    t = t.replace(e['el'], '<text %s>%s</text>' % (new_attrs, e['nm']))
    for b in en:
        if abs(b['x'] - e['x']) < 25 and b['y'] > e['y']:
            b_attrs = re.sub(r'\bx="[-\d.]+"', 'x="%.2f"' % (b['x'] + ddx), b['attrs'])
            b_attrs = re.sub(r'\by="[-\d.]+"', 'y="%.2f"' % (b['y'] + ddy), b_attrs)
            t = t.replace(b['el'], '<text %s>%s</text>' % (b_attrs, b['nm']))
    applied += 1
print('已应用:', applied)

import xml.etree.ElementTree as ET
try:
    ET.fromstring(t)
except ET.ParseError as pe:
    print('!! XML损坏拒绝落盘:', pe)
    sys.exit(1)
open(F, 'w', encoding='utf-8').write(t)
print('codes SVG 已更新')
