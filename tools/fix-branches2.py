#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 支线/环线残站修复（基于全网几何并集图）：
#   支线：两衔接站之间 Dijkstra 最短路（共走廊段画在别的线组里，用并集图才能连通）
#   环线：坏站前后邻站间的最短路上的等分点
import json, math, re, bisect, heapq
import xml.etree.ElementTree as ET
from collections import defaultdict

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

# ---- 全网并集图（容差 2px 并点） ----
nodes = []
def nid(x, y):
    for i, (nx, ny) in enumerate(nodes):
        if abs(nx - x) <= 2 and abs(ny - y) <= 2: return i
    nodes.append((x, y)); return len(nodes) - 1

adj = defaultdict(list)   # u -> [(v, w, x, y)]
for g in GROUP:
    for x1, y1, x2, y2 in segs_of(g):
        a, b = nid(x1, y1), nid(x2, y2)
        if a == b: continue
        w = math.hypot(x2 - x1, y2 - y1)
        adj[a].append((b, w, nodes[b][0], nodes[b][1]))
        adj[b].append((a, w, nodes[a][0], nodes[a][1]))
print(f'全网图: {len(nodes)} 节点, {sum(len(v) for v in adj.values()) // 2} 边')

def nearest_node(x, y):
    return min(range(len(nodes)), key=lambda i: math.hypot(nodes[i][0] - x, nodes[i][1] - y))

def dijkstra_path(s, t):
    dist = {s: 0}; prev = {}
    pq = [(0, s)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, 1e18): continue
        if u == t: break
        for v, w, _, _ in adj[u]:
            nd = d + w
            if nd < dist.get(v, 1e18):
                dist[v] = nd; prev[v] = u; heapq.heappush(pq, (nd, v))
    if t not in dist and t != s: return None
    path = [t]; x = t
    while x != s:
        if x not in prev: return None
        x = prev[x]; path.append(x)
    return path[::-1]

def path_pts(path):
    pts = [nodes[i] for i in path]
    arc = [0.0]
    for i in range(1, len(pts)):
        arc.append(arc[-1] + math.hypot(pts[i][0] - pts[i-1][0], pts[i][1] - pts[i-1][1]))
    return pts, arc

def point_at(pts, arc, s):
    if s <= 0: return pts[0]
    if s >= arc[-1]: return pts[-1]
    i = bisect.bisect_left(arc, s)
    t = (s - arc[i-1]) / max(1e-9, arc[i] - arc[i-1])
    return (pts[i-1][0] + t * (pts[i][0] - pts[i-1][0]), pts[i-1][1] + t * (pts[i][1] - pts[i-1][1]))

glyphs = []
for el in find_g('站点').iter():
    t = el.tag.replace(NS, '')
    if t == 'circle': glyphs.append((float(el.get('cx')), float(el.get('cy'))))
    elif t == 'path':
        m = re.match(r'M\s*(-?[\d.]+)[ ,](-?[\d.]+)', el.get('d', '').strip() or '')
        if m: glyphs.append((float(m.group(1)), float(m.group(2))))

c = json.load(open('E:/GuangzhouBusViewer/assets/tim-coords.json'))
d = json.load(open('E:/GuangzhouMetroQuiz/Content/Data/MetroData.json', encoding='utf-8-sig'))
lines = {l['ref']: l for l in d['lines']}

def glyph_snap(q):
    gb = min(glyphs, key=lambda g: math.hypot(g[0] - q[0], g[1] - q[1]))
    if math.hypot(gb[0] - q[0], gb[1] - q[1]) < 25:
        return gb
    return q

def node_near_graph(x, y):
    n = nearest_node(x, y)
    return n if math.hypot(nodes[n][0] - x, nodes[n][1] - y) < 40 else None

# ---- 支线修复 ----
for ref in ('3', '14'):
    l = lines[ref]
    for br in l.get('branches', []):
        jp0, jp1 = c.get(br[0]), c.get(br[-1])
        if not jp0 or not jp1 or jp0[2] > 15 or jp1[2] > 15: continue
        n0 = node_near_graph(jp0[0], jp0[1]); n1 = node_near_graph(jp1[0], jp1[1])
        if n0 is None or n1 is None: continue
        path = dijkstra_path(n0, n1)
        if not path: continue
        pts, arc = path_pts(path)
        L = arc[-1]
        # 支线站数(去掉两端衔接站)与总弧长应大致匹配：每站 40-80px
        n_mid = len(br) - 2
        if n_mid > 0 and (L / n_mid < 25 or L / n_mid > 120):
            print(f'{ref}支线: 路径长度异常 {L:.0f}px / {n_mid} 站, 跳过')
            continue
        print(f'{ref}支线: 路径 {L:.0f}px, {n_mid} 个中段站')
        for i, sid in enumerate(br):
            if i == 0 or i == len(br) - 1: continue
            if sid not in c or c[sid][2] <= 15: continue
            s = L * i / (len(br) - 1)
            q = point_at(pts, arc, s)
            q = glyph_snap(q)
            e2 = min((math.hypot(q[0] - nodes[k][0], q[1] - nodes[k][1]) for k in adj), default=99) if not adj else None
            # 误差用图上距离
            nn = nearest_node(q[0], q[1])
            e2 = math.hypot(q[0] - nodes[nn][0], q[1] - nodes[nn][1])
            if e2 < c[sid][2]:
                print(f'  {sid}: {c[sid][2]:.0f} -> {e2:.1f} @({q[0]:.0f},{q[1]:.0f})')
                c[sid] = [round(q[0], 1), round(q[1], 1), round(e2, 1)]

# ---- 11 号线环上残站：前后邻站最短路等分 ----
l11 = lines['11']; seq = l11['stations']
for i, sid in enumerate(seq):
    if sid not in c or c[sid][2] <= 15: continue
    prevS, nextS = seq[i - 1], seq[(i + 1) % len(seq)]
    p0, p1 = c.get(prevS), c.get(nextS)
    if not p0 or not p1 or p0[2] > 15 or p1[2] > 15: continue
    n0 = node_near_graph(p0[0], p0[1]); n1 = node_near_graph(p1[0], p1[1])
    if n0 is None or n1 is None: continue
    path = dijkstra_path(n0, n1)
    if not path: continue
    pts, arc = path_pts(path)
    q = point_at(pts, arc, arc[-1] / 2)
    q = glyph_snap(q)
    nn = nearest_node(q[0], q[1])
    e2 = math.hypot(q[0] - nodes[nn][0], q[1] - nodes[nn][1])
    if e2 < c[sid][2]:
        print(f'环线 {sid}: {c[sid][2]:.0f} -> {e2:.1f}')
        c[sid] = [round(q[0], 1), round(q[1], 1), round(e2, 1)]

json.dump(c, open('E:/GuangzhouBusViewer/assets/tim-coords.json', 'w', encoding='utf-8'), ensure_ascii=False)
bad = [(k, round(v[2])) for k, v in c.items() if v[2] > 30]
print(f'最终 >30px: {len(bad)}', bad)
