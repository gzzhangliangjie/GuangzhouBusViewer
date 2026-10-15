#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 支线修复：支线两端衔接站已可信 → 沿支线几何链按站序插值
# 环线修复：坏站取前后邻站中点 → 贴线贴字形
import json, math, re, bisect
import xml.etree.ElementTree as ET
from collections import defaultdict, deque

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

def chains(segs):
    keys = {}
    def key(x, y): return (round(x * 4) / 4, round(y * 4) / 4)
    edges = set()
    for x1, y1, x2, y2 in segs:
        ka, kb = key(x1, y1), key(x2, y2)
        if ka == kb: continue
        edges.add((ka, kb)); keys.setdefault(ka, (x1, y1)); keys.setdefault(kb, (x2, y2))
    adj = defaultdict(set)
    for a, b in edges: adj[a].add(b); adj[b].add(a)
    if not adj: return None
    def bfs(s):
        dist = {s: 0}; prev = {}; q = deque([s])
        while q:
            u = q.popleft()
            for v in adj[u]:
                if v not in dist: dist[v] = dist[u] + 1; prev[v] = u; q.append(v)
        return max(dist, key=dist.get), prev
    u1, _ = bfs(next(iter(adj))); u2, prev = bfs(u1)
    chain = []; x = u2
    while x != u1: chain.append(x); x = prev[x]
    chain.append(u1); chain.reverse()
    cs = set(chain); visited = set(cs); branches = []
    for node in chain:
        for nb in adj[node]:
            if nb in visited: continue
            br = [node, nb]; visited.add(nb); cur = nb
            while True:
                nxts = [v for v in adj[cur] if v not in visited]
                if len(nxts) != 1: break
                cur = nxts[0]; visited.add(cur); br.append(cur)
            branches.append(br)
    return chain, branches, keys

def geom_of(nl, keys):
    pts = [keys[k] for k in nl]; arc = [0.0]
    for i in range(1, len(pts)):
        arc.append(arc[-1] + math.hypot(pts[i][0] - pts[i-1][0], pts[i][1] - pts[i-1][1]))
    return pts, arc

def point_at(pts, arc, s):
    if s <= 0: return pts[0]
    if s >= arc[-1]: return pts[-1]
    i = bisect.bisect_left(arc, s)
    t = (s - arc[i-1]) / max(1e-9, arc[i] - arc[i-1])
    return (pts[i-1][0] + t*(pts[i][0]-pts[i-1][0]), pts[i-1][1] + t*(pts[i][1]-pts[i-1][1]))

def near(px, py, segs):
    best = 1e18
    for x1, y1, x2, y2 in segs:
        dx, dy = x2-x1, y2-y1; L2 = dx*dx + dy*dy
        t = 0 if L2 == 0 else max(0, min(1, ((px-x1)*dx + (py-y1)*dy) / L2))
        best = min(best, math.hypot(px-(x1+t*dx), py-(y1+t*dy)))
    return best

glyphs = []
for el in find_g('站点').iter():
    tag = el.tag.replace(NS, '')
    if tag == 'circle': glyphs.append((float(el.get('cx')), float(el.get('cy'))))
    elif tag == 'path':
        m = re.match(r'M\s*(-?[\d.]+)[ ,](-?[\d.]+)', el.get('d', '').strip() or '')
        if m: glyphs.append((float(m.group(1)), float(m.group(2))))

def glyph_snap(q, segs):
    gb = min(glyphs, key=lambda g: math.hypot(g[0]-q[0], g[1]-q[1]))
    if math.hypot(gb[0]-q[0], gb[1]-q[1]) < 25 and near(gb[0], gb[1], segs) < 6:
        return gb
    return q

c = json.load(open('E:/GuangzhouBusViewer/assets/tim-coords.json'))
d = json.load(open('E:/GuangzhouMetroQuiz/Content/Data/MetroData.json', encoding='utf-8-sig'))
lines = {l['ref']: l for l in d['lines']}
GNAME = {'3': '3', '14': '14'}

# ---- 支线：两端衔接站可信 → 沿支线链插值 ----
for ref in ('3', '14'):
    l = lines[ref]
    segs = line_geom(GNAME[ref])
    ch = chains(segs)
    if not ch: continue
    chain, branches, keys = ch
    for br_seq in l.get('branches', []):
        jp0 = c.get(br_seq[0]); jp1 = c.get(br_seq[-1])
        if not jp0 or not jp1 or jp0[2] > 15 or jp1[2] > 15: continue
        best, bs = None, 1e18
        for br in branches:
            pts, arc = geom_of(br, keys)
            dd = math.hypot(pts[0][0]-jp0[0], pts[0][1]-jp0[1]) + math.hypot(pts[-1][0]-jp1[0], pts[-1][1]-jp1[1])
            dr = math.hypot(pts[0][0]-jp1[0], pts[0][1]-jp1[1]) + math.hypot(pts[-1][0]-jp0[0], pts[-1][1]-jp0[1])
            if min(dd, dr) < bs: bs, best, fwd = min(dd, dr), br, dd <= dr
        if best is None or bs > 60: continue
        pts, arc = geom_of(best, keys)
        if not fwd: pts = pts[::-1]
        pts2 = pts; arc = [0.0]
        for i in range(1, len(pts2)):
            arc.append(arc[-1] + math.hypot(pts2[i][0]-pts2[i-1][0], pts2[i][1]-pts2[i-1][1]))
        n = len(br_seq)
        for i, sid in enumerate(br_seq):
            if sid not in c or c[sid][2] <= 15: continue
            s = arc[-1] * i / (n - 1)
            q = point_at(pts2, arc, s)
            q = glyph_snap(q, segs)
            e2 = near(q[0], q[1], segs)
            if e2 < c[sid][2]:
                print(f'支线 {sid}: {c[sid][2]:.0f} -> {e2:.1f}')
                c[sid] = [round(q[0], 1), round(q[1], 1), round(e2, 1)]

# ---- 11 号线环：坏站取前后邻站中点 ----
segs11 = line_geom('11')
l11 = lines['11']; seq = l11['stations']
for i, sid in enumerate(seq):
    if sid not in c or c[sid][2] <= 15: continue
    p0 = c.get(seq[i-1]); p1 = c.get(seq[(i+1) % len(seq)])
    if not p0 or not p1 or p0[2] > 15 or p1[2] > 15: continue
    q = ((p0[0]+p1[0])/2, (p0[1]+p1[1])/2)
    q = glyph_snap(q, segs11)
    e2 = near(q[0], q[1], segs11)
    if e2 < c[sid][2]:
        print(f'环线 {sid}: {c[sid][2]:.0f} -> {e2:.1f}')
        c[sid] = [round(q[0], 1), round(q[1], 1), round(e2, 1)]

json.dump(c, open('E:/GuangzhouBusViewer/assets/tim-coords.json', 'w', encoding='utf-8'), ensure_ascii=False)
errs = [v[2] for v in c.values()]
bad = [(k, round(v[2])) for k, v in c.items() if v[2] > 30]
print(f'最终 >30px: {len(bad)}', bad)
