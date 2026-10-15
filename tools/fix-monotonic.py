#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 全网集中修复 v2：逐线矢量几何路径 → 沿线有序字形 → 保序分配
# 好锚(已对准字形)做校验锚，坏站在锚间找最近空闲字形
import json, math, re, bisect
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

def raw_segs(gname):
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

# 有序路径：线段连接成链（贪心最近端拼接）
def ordered_path(segs):
    if not segs: return []
    remaining = list(segs)
    # 找起点：最左端的点
    all_pts = []
    for x1, y1, x2, y2 in remaining:
        all_pts.append((x1, y1)); all_pts.append((x2, y2))
    start = min(all_pts)
    # 贪心连接
    path = [start]
    cur = start
    used = set()
    while len(used) < len(remaining):
        best_d, best_seg, best_end, best_rev = 1e18, None, None, False
        for i, (x1, y1, x2, y2) in enumerate(remaining):
            if i in used: continue
            d1 = math.hypot(x1-cur[0], y1-cur[1])
            d2 = math.hypot(x2-cur[0], y2-cur[1])
            if d1 < best_d and d1 < 20:
                best_d, best_seg, best_end, best_rev = d1, i, (x2, y2), False
            if d2 < best_d and d2 < 20:
                best_d, best_seg, best_end, best_rev = d2, i, (x1, y1), True
        if best_seg is None: break
        used.add(best_seg)
        path.append(best_end)
        cur = best_end
    return path

def path_arc(path):
    arc = [0.0]
    for i in range(1, len(path)):
        arc.append(arc[-1] + math.hypot(path[i][0]-path[i-1][0], path[i][1]-path[i-1][1]))
    return arc

def proj_path(path, arc, p):
    best, bs = 1e18, 0.0
    for i in range(1, len(path)):
        x1, y1 = path[i-1]; x2, y2 = path[i]
        dx, dy = x2-x1, y2-y1
        L2 = dx*dx + dy*dy
        t = 0 if L2 == 0 else max(0.0, min(1.0, ((p[0]-x1)*dx + (p[1]-y1)*dy) / L2))
        d = math.hypot(p[0]-(x1+t*dx), p[1]-(y1+t*dy))
        if d < best: best, bs = d, arc[i-1] + t * math.hypot(dx, dy)
    return best, bs

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

c = json.load(open(OUT, encoding='utf-8'))
data = json.load(open(SRC, encoding='utf-8-sig'))
st = {s['id']: s for s in data['stations']}

# 全局字形占用
glyph_owner = {}
for sid in st:
    x, y = c[sid][0], c[sid][1]
    near = min(glyphs, key=lambda g: math.hypot(g[0]-x, g[1]-y))
    if math.hypot(near[0]-x, near[1]-y) <= 6:
        key = (round(near[0], 1), round(near[1], 1))
        if key not in glyph_owner:
            glyph_owner[key] = sid
            c[sid] = [round(near[0], 1), round(near[1], 1), 0.0]

total_fixed = 0
for l in data['lines']:
    ref = l['ref']
    if ref not in GROUP: continue
    segs = raw_segs(GROUP[ref])
    path = ordered_path(segs)
    if len(path) < 2: continue
    arc = path_arc(path)
    L = arc[-1]
    if L < 30: continue

    # 走廊附近字形按弧长排序
    near = []
    for g in glyphs:
        d, s = proj_path(path, arc, g)
        if d < 12: near.append((s, g))
    near.sort()

    seq_all = l['stations'] + [s for b in l.get('branches', []) for s in b]
    uniq = list(dict.fromkeys(seq_all))
    if len(uniq) > len(near): continue  # 字形不够

    # 地理累积比例
    geo_d = [0.0]
    for i in range(1, len(uniq)):
        p0, p1 = st[uniq[i-1]], st[uniq[i]]
        geo_d.append(geo_d[-1] + math.hypot((p1['lon']-p0['lon'])*102000, -(p1['lat']-p0['lat'])*110540))
    Lg = geo_d[-1] or 1

    # 保序贪心：已对准的站锁字形位置，坏站在锚间找最近空闲
    used_glyph = set()
    anchor_s = {}  # station -> arc position
    # 先处理好站
    for i, sid in enumerate(uniq):
        x, y = c[sid][0], c[sid][1]
        near_g = min(glyphs, key=lambda g: math.hypot(g[0]-x, g[1]-y))
        if math.hypot(near_g[0]-x, near_g[1]-y) <= 8:
            d, s = proj_path(path, arc, near_g)
            if d < 15:
                key = (round(near_g[0], 1), round(near_g[1], 1))
                used_glyph.add(key)
                anchor_s[i] = s
                c[sid] = [round(near_g[0], 1), round(near_g[1], 1), 0.0]

    # 坏站：在相邻好锚的弧长区间内分配
    fixed_this_line = 0
    sorted_anchors = sorted(anchor_s.items())
    for i, sid in enumerate(uniq):
        if i in anchor_s: continue
        # 找前后好锚
        prev_a = max([(k, v) for k, v in sorted_anchors if k < i], default=(0, 0.0))
        next_a = min([(k, v) for k, v in sorted_anchors if k > i], default=(len(uniq)-1, L))
        lo_s = prev_a[1] if prev_a[0] > 0 or len(prev_a) > 0 else 0
        hi_s = next_a[1] if next_a[0] > 0 or len(next_a) > 0 else L
        if hi_s <= lo_s: hi_s = lo_s + 40
        # 目标弧长
        target = lo_s + (hi_s - lo_s) * (i - prev_a[0]) / max(1, next_a[0] - prev_a[0])
        # 在锚间找最近未占字形
        best_g, best_gap = None, 1e18
        for s, g in near:
            if s < lo_s - 5 or s > hi_s + 5: continue
            key = (round(g[0], 1), round(g[1], 1))
            if key in used_glyph: continue
            gap = abs(s - target)
            if gap < best_gap:
                best_gap, best_g = gap, g
        if best_g and best_gap < 70:
            key = (round(best_g[0], 1), round(best_g[1], 1))
            used_glyph.add(key)
            c[sid] = [round(best_g[0], 1), round(best_g[1], 1), 0.0]
            fixed_this_line += 1
    if fixed_this_line:
        print(f'{ref:3s}: fixed {fixed_this_line}')
        total_fixed += fixed_this_line

print(f'\n总计修复: {total_fixed}')

# 终检
bad_pairs = []
for l in data['lines']:
    seq = l['stations'] + [s for b in l.get('branches', []) for s in b]
    uniq = list(dict.fromkeys(seq))
    for i in range(len(uniq)):
        for j in range(i+1, len(uniq)):
            a, b = c.get(uniq[i]), c.get(uniq[j])
            if a and b and math.hypot(a[0]-b[0], a[1]-b[1]) < 6:
                bad_pairs.append((l['ref'], uniq[i], uniq[j]))
print(f'同线 <6px: {len(bad_pairs)}')

final_off = sum(1 for sid in st if min(math.hypot(g[0]-c[sid][0], g[1]-c[sid][1]) for g in glyphs) > 8)
print(f'最终错位(>8px): {final_off}/314')

json.dump(c, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
