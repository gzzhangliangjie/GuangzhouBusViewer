#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 端点/支线末端定向修复：终点站放在离其邻站落位最近的线路几何链端，贴字形微调
import json, math, re
import xml.etree.ElementTree as ET
from collections import Counter

SVG = 'E:/GuangzhouBusViewer/assets/tim-gzfmetro.svg'
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

def line_geom(gname):
    g = find_g(gname); segs = []
    for el in g.iter():
        tag = el.tag.replace(NS, '')
        if tag == 'line':
            x1, y1, x2, y2 = map(float, (el.get('x1'), el.get('y1'), el.get('x2'), el.get('y2')))
            if math.hypot(x2 - x1, y2 - y1) > 0.1: segs.append((x1, y1, x2, y2))
        elif tag == 'path':
            dd = el.get('d', '').strip()
            m = re.match(r'M\s*(-?[\d.]+)[ ,](-?[\d.]+)', dd)
            if not m: continue
            mx, my = float(m.group(1)), float(m.group(2))
            ns = [float(v) for v in re.findall(r'-?\d+\.?\d*', dd[m.end():])]
            if len(ns) >= 2:
                ex, ey = mx + ns[-2], my + ns[-1]
                if math.hypot(ex - mx, ey - my) > 0.1: segs.append((mx, my, ex, ey))
    return segs

def endpoints(segs):
    occ = Counter()
    for x1, y1, x2, y2 in segs:
        occ[(x1, y1)] += 1; occ[(x2, y2)] += 1
    return [p for p, n in occ.items() if n == 1]

def near_segs(px, py, segs):
    best = 1e18
    for x1, y1, x2, y2 in segs:
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        t = 0 if L2 == 0 else max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / L2))
        best = min(best, math.hypot(px - (x1 + t * dx), py - (y1 + t * dy)))
    return best

glyphs = []
for el in find_g('站点').iter():
    tag = el.tag.replace(NS, '')
    if tag == 'circle':
        glyphs.append((float(el.get('cx')), float(el.get('cy'))))
    elif tag == 'path':
        m = re.match(r'M\s*(-?[\d.]+)[ ,](-?[\d.]+)', el.get('d', '').strip() or '')
        if m: glyphs.append((float(m.group(1)), float(m.group(2))))

c = json.load(open('E:/GuangzhouBusViewer/assets/tim-coords.json'))
d = json.load(open('E:/GuangzhouMetroQuiz/Content/Data/MetroData.json', encoding='utf-8-sig'))
lines = {l['ref']: l for l in d['lines']}
st = {s['id']: s for s in d['stations']}
GEOM = {ref: line_geom(g) for g, ref in GROUP.items()}

BAD = [(k, v[2]) for k, v in c.items() if v[2] > 30]
print('待修:', len(BAD), [b[0] for b in BAD])
fixed = 0
for sid, err in BAD:
    ref = st[sid]['lines'][0]
    l = lines[ref]
    nb = None
    for seq in [l['stations']] + l.get('branches', []):
        if sid in seq:
            i = seq.index(sid)
            if i == 0 and len(seq) > 1: nb = seq[1]
            elif i == len(seq) - 1: nb = seq[i - 1]
            break
    if not nb or nb not in c: continue
    nx, ny, ne = c[nb]
    if ne > 15: continue
    segs = GEOM.get(ref)
    if not segs: continue
    ends = endpoints(segs)
    if not ends: continue
    ex, ey = min(ends, key=lambda p: math.hypot(p[0] - nx, p[1] - ny))
    if math.hypot(ex - nx, ey - ny) > 160: continue
    q = (ex, ey)
    gb = min(glyphs, key=lambda g: math.hypot(g[0] - q[0], g[1] - q[1]))
    if math.hypot(gb[0] - q[0], gb[1] - q[1]) < 25 and near_segs(gb[0], gb[1], segs) < 6:
        q = gb
    e2 = near_segs(q[0], q[1], segs)
    if e2 < err:
        c[sid] = [round(q[0], 1), round(q[1], 1), round(e2, 1)]
        fixed += 1
        print(f'  {sid}: {err:.0f} -> {e2:.1f} @({q[0]:.0f},{q[1]:.0f})')
json.dump(c, open('E:/GuangzhouBusViewer/assets/tim-coords.json', 'w', encoding='utf-8'), ensure_ascii=False)
errs = [v[2] for v in c.values()]
print(f'修复 {fixed}; 剩余>30px: {sum(1 for e in errs if e > 30)}')
