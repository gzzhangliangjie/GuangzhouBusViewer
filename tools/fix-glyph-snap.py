#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 全站字形贴合修复：对每个站，在其所属线的矢量几何 ±8px 范围内找最近未占用字形，
# 将坐标吸附到字形精确位置（消除走廊插值漂移）
import json, math, re
import xml.etree.ElementTree as ET
from collections import defaultdict

SVG = 'E:/GuangzhouBusViewer/assets/tim-gzfmetro.svg'
SRC = 'E:/GuangzhouMetroQuiz/Content/Data/MetroData.json'
OUT = 'E:/GuangzhouBusViewer/assets/tim-coords.json'
NS = '{http://www.w3.org/2000/svg}'
tree = ET.parse(SVG); root = tree.getroot()
def decode(i):
    if not i: return ''
    for x in range(10): i = i.replace(f'_x3{x}_', str(x))
    return i
def find_g(n):
    for g in root.iter(NS + 'g'):
        if decode(g.get('id', '')) == n: return g
GROUP = {'1': '1', '2': '2', '3': '3', '4': '4', '5': '5', '6': '6', '7': '7', '8': '8',
         '9_3_': '9', '10_1_': '10', '11': '11', '12': '12', '13': '13', '14': '14',
         '18': '18', '21': '21', '22': '22', 'GF': 'GF', 'APM_3_': 'APM'}

def segs_of(gname):
    segs = []
    for el in find_g(gname).iter():
        t = el.tag.replace(NS, '')
        if t == 'line':
            x1, y1, x2, y2 = map(float, (el.get('x1'), el.get('y1'), el.get('x2'), el.get('y2')))
            if math.hypot(x2 - x1, y2 - y1) > 0.1: segs.append((x1, y1, x2, y2))
        elif t == 'path':
            d = el.get('d', '').strip()
            m = re.match(r'M\s*(-?[\d.]+)[ ,](-?[\d.]+)', d)
            if not m: continue
            mx, my = float(m.group(1)), float(m.group(2))
            ns = [float(v) for v in re.findall(r'-?\d+\.?\d*', d[m.end():])]
            if len(ns) >= 2:
                ex, ey = mx + ns[-2], my + ns[-1]
                if math.hypot(ex - mx, ey - my) > 0.1: segs.append((mx, my, ex, ey))
    return segs
GEOM = {ref: segs_of(g) for g, ref in GROUP.items()}

def dist_seg(px, py, s):
    x1, y1, x2, y2 = s
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    t = 0 if L2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

def on_line(x, y, ref, tol=8):
    for s in GEOM.get(ref, []):
        if dist_seg(x, y, s) < tol: return True
    return False

glyphs = []
for el in find_g('站点').iter(NS + 'circle'):
    glyphs.append((float(el.get('cx')), float(el.get('cy'))))

c = json.load(open(OUT, encoding='utf-8'))
data = json.load(open(SRC, encoding='utf-8-sig'))
st = {s['id']: s for s in data['stations']}

# 全局唯一字形占用
glyph_owner = {}
def claim(g, sid):
    key = (round(g[0], 1), round(g[1], 1))
    if key in glyph_owner: return False
    glyph_owner[key] = sid
    return True

fixed = 0
for sid, s in st.items():
    x, y = c[sid][0], c[sid][1]
    # 全局最近未占用字形（55px 半径内），不限本线几何——共享走廊时几何归属不唯一
    best_g, best_d = None, 1e9
    for g in glyphs:
        d = math.hypot(g[0] - x, g[1] - y)
        if d < best_d: best_g, best_d = g, d
    if best_g is None or best_d > 55: continue
    key = (round(best_g[0], 1), round(best_g[1], 1))
    if key in glyph_owner:
        if glyph_owner[key] != sid:
            continue  # 已被占, 保持原位
    claim(best_g, sid)
    if best_d > 2:
        c[sid] = [round(best_g[0], 1), round(best_g[1], 1), 0.0]
        fixed += 1

print(f'字形吸附修复 {fixed} 站')

# 验证
bad = []
for l in data['lines']:
    seq = l['stations'] + [s for b in l.get('branches', []) for s in b]
    uniq = list(dict.fromkeys(seq))
    for i in range(len(uniq)):
        for j in range(i + 1, len(uniq)):
            a, b = c[uniq[i]], c[uniq[j]]
            if math.hypot(a[0] - b[0], a[1] - b[1]) < 6:
                bad.append((l['ref'], uniq[i], uniq[j]))
print('同线 <6px:', len(bad), bad[:6])

# 5号线复查
l5 = next(l for l in data['lines'] if l['ref'] == '5')
for s in ['中山八', '西场', '西村', '小北', '淘金', '区庄', '动物园', '五羊邨', '珠江新城']:
    x, y = c[s][:2]
    near = min(glyphs, key=lambda g: math.hypot(g[0] - x, g[1] - y))
    dd = math.hypot(near[0] - x, near[1] - y)
    print(f'  {s}: ({x:.0f},{y:.0f}) 字形距 {dd:.0f}')

json.dump(c, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print('输出完成')
