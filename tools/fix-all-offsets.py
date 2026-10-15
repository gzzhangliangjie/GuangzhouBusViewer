#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 全网字形集中修复：逐站找最近未占用字形（含本线几何校验），
# 好站(≤8px)锁定为锚，坏站按线序在锚间找最近空闲字形
import json, math, re
import xml.etree.ElementTree as ET
from collections import defaultdict

SVG = 'E:/GuangzhouBusViewer/assets/tim-gzfmetro.svg'
RASTER = 'E:/GuangzhouBusViewer/assets/_tim-raster.png'
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
            if math.hypot(x2-x1, y2-y1) > 0.1: segs.append((x1, y1, x2, y2))
        elif t == 'path':
            d = el.get('d', '').strip()
            m = re.match(r'M\s*(-?[\d.]+)[ ,](-?[\d.]+)', d)
            if not m: continue
            mx, my = float(m.group(1)), float(m.group(2))
            ns = [float(v) for v in re.findall(r'-?\d+\.?\d*', d[m.end():])]
            if len(ns) >= 2:
                ex, ey = mx + ns[-2], my + ns[-1]
                if math.hypot(ex-mx, ey-my) > 0.1: segs.append((mx, my, ex, ey))
    return segs
GEOM = {ref: segs_of(g) for g, ref in GROUP.items()}

# 所有字形（圆 + 换乘圆角矩形中心）
glyphs = []
for el in find_g('站点').iter(NS + 'circle'):
    glyphs.append((float(el.get('cx')), float(el.get('cy'))))
for el in find_g('站点').iter(NS + 'path'):
    d = el.get('d', '').strip()
    m = re.match(r'M\s*(-?[\d.]+)[ ,](-?[\d.]+)', d)
    if not m: continue
    vals = [float(v) for v in re.findall(r'-?\d+\.?\d*', d)]
    if len(vals) >= 8:
        xs = vals[0::2]; ys = vals[1::2]
        if max(xs)-min(xs) < 30 and max(ys)-min(ys) < 30:
            glyphs.append(((min(xs)+max(xs))/2, (min(ys)+max(ys))/2))

def dist_seg(px, py, s):
    x1, y1, x2, y2 = s
    dx, dy = x2-x1, y2-y1
    L2 = dx*dx + dy*dy
    t = 0 if L2 == 0 else max(0.0, min(1.0, ((px-x1)*dx + (py-y1)*dy) / L2))
    return math.hypot(px-(x1+t*dx), py-(y1+t*dy))

def near_any_line(x, y, refs, tol=12):
    for r in refs:
        if r not in GEOM: continue
        for s in GEOM[r]:
            if dist_seg(x, y, s) < tol: return True
    return False

def snap_to_line_geometry(px, py, ref):
    best, bq = 1e18, (px, py)
    for s in GEOM.get(ref, []):
        x1, y1, x2, y2 = s
        dx, dy = x2-x1, y2-y1
        L2 = dx*dx + dy*dy
        t = 0 if L2 == 0 else max(0.0, min(1.0, ((px-x1)*dx + (py-y1)*dy) / L2))
        qx, qy = x1+t*dx, y1+t*dy
        d = math.hypot(px-qx, py-qy)
        if d < best: best, bq = d, (qx, qy)
    return bq, best

c = json.load(open(OUT, encoding='utf-8'))
data = json.load(open(SRC, encoding='utf-8-sig'))
st = {s['id']: s for s in data['stations']}

# Phase 1: 好站锁字形
glyph_owner = {}   # (x,y) -> station_id
good = set()
for sid, s in st.items():
    x, y = c[sid][0], c[sid][1]
    near = min(glyphs, key=lambda g: math.hypot(g[0]-x, g[1]-y))
    dd = math.hypot(near[0]-x, near[1]-y)
    if dd <= 8:
        key = (round(near[0], 1), round(near[1], 1))
        if key not in glyph_owner:
            glyph_owner[key] = sid
            good.add(sid)
            c[sid] = [round(near[0], 1), round(near[1], 1), 0.0]  # 精确吸附
print(f'Phase 1 好站锁定: {len(good)}/314')

# Phase 2: 坏站逐线修复（在好锚间找最近未占字形，不限本线几何——共享走廊时归属不唯一）
fixed = 0
for l in data['lines']:
    seq_all = l['stations'] + [s for b in l.get('branches', []) for s in b]
    uniq = list(dict.fromkeys(seq_all))
    bad_in_line = [s for s in uniq if s not in good]
    if not bad_in_line: continue
    # 按站序处理每个坏站
    for sid in bad_in_line:
        s = st[sid]
        x, y = c[sid][0], c[sid][1]
        # 找 80px 内最近未占字形
        candidates = sorted(glyphs, key=lambda g: math.hypot(g[0]-x, g[1]-y))
        placed = False
        for g in candidates:
            dd = math.hypot(g[0]-x, g[1]-y)
            if dd > 90: break
            key = (round(g[0], 1), round(g[1], 1))
            if key in glyph_owner: continue
            # 检查同线其他站不冲突
            conflict = False
            for other in uniq:
                if other == sid or other not in c: continue
                ox, oy = c[other][0], c[other][1]
                if math.hypot(g[0]-ox, g[1]-oy) < 6:
                    conflict = True; break
            if conflict: continue
            c[sid] = [round(g[0], 1), round(g[1], 1), 0.0]
            glyph_owner[key] = sid
            fixed += 1
            placed = True
            break
        if not placed:
            # 兜底：贴本线几何最近点（可能不在字形上但至少在线上）
            q, d0 = snap_to_line_geometry(x, y, s['lines'][0])
            c[sid] = [round(q[0], 1), round(q[1], 1), round(d0, 1)]
print(f'Phase 2 坏站修复: {fixed}')

# Phase 3: 终检
bad_pairs = []
for l in data['lines']:
    seq = l['stations'] + [s for b in l.get('branches', []) for s in b]
    uniq = list(dict.fromkeys(seq))
    for i in range(len(uniq)):
        for j in range(i+1, len(uniq)):
            a, b = c.get(uniq[i]), c.get(uniq[j])
            if a and b and math.hypot(a[0]-b[0], a[1]-b[1]) < 6:
                bad_pairs.append((l['ref'], uniq[i], uniq[j]))
print(f'同线 <6px: {len(bad_pairs)}', bad_pairs[:6])

# 统计最终字形距离
final_off = sum(1 for sid in st if min(math.hypot(g[0]-c[sid][0], g[1]-c[sid][1]) for g in glyphs) > 8)
print(f'最终错位(>8px): {final_off}/314')

json.dump(c, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print('输出完成')
