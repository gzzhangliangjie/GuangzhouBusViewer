#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 坐标重建（干净版）：
#   锚 = 线路矢量端点×端站(地理定向) + 单共享线对交点(仿射引导选点)
#   变换 = TPS；放置 = 贴本线几何 + 贴唯一字形（每字形至多一站，防坍塌之根）
#   校验 = 同线异站 ≥6px + 逐线沿线保序（容许环线/短支松弛）
import json, math, re
import xml.etree.ElementTree as ET
from collections import defaultdict
import numpy as np

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

def line_geom(gname):
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
GEOM = {ref: line_geom(g) for g, ref in GROUP.items()}

glyphs = []
for el in find_g('站点').iter():
    t = el.tag.replace(NS, '')
    if t == 'circle': glyphs.append((float(el.get('cx')), float(el.get('cy'))))
    elif t == 'path':
        m = re.match(r'M\s*(-?[\d.]+)[ ,](-?[\d.]+)', el.get('d', '').strip() or '')
        if m: glyphs.append((float(m.group(1)), float(m.group(2))))
glyph_used = {}   # glyph index -> station id

data = json.load(open(SRC, encoding='utf-8-sig'))
st = {s['id']: s for s in data['stations']}
lines = {l['ref']: l for l in data['lines']}
def seqs_of(l): return [l['stations']] + l.get('branches', [])

def geo_xy(lat, lon):
    kx = 111320.0 * math.cos(math.radians(23.15))
    return (lon * kx, -lat * 110540.0)
def gpos(sid): return geo_xy(st[sid]['lat'], st[sid]['lon'])

def seg_int(a, b):
    x1, y1, x2, y2 = a; x3, y3, x4, y4 = b
    d = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if abs(d) < 1e-9: return None
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / d
    u = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / d
    if -0.05 <= t <= 1.05 and -0.05 <= u <= 1.05:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None

def dist_seg(px, py, s):
    x1, y1, x2, y2 = s
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    t = 0 if L2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

def snap_line(px, py, ref):
    best, bq = 1e18, (px, py)
    for s in GEOM[ref]:
        x1, y1, x2, y2 = s
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        t = 0 if L2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
        qx, qy = x1 + t * dx, y1 + t * dy
        d = math.hypot(px - qx, py - qy)
        if d < best: best, bq = d, (qx, qy)
    return bq, best

def v_ends(ref):
    occ = defaultdict(int)
    for x1, y1, x2, y2 in GEOM[ref]:
        occ[(x1, y1)] += 1; occ[(x2, y2)] += 1
    return [p for p, n in occ.items() if n == 1]

# ---------- 1) 端点锚 ----------
anchors = []
for ref, l in lines.items():
    if ref not in GEOM: continue
    ends = v_ends(ref)
    terms = []
    seen = set()
    for seq in seqs_of(l):
        for sid in (seq[0], seq[-1]):
            if sid not in seen: seen.add(sid); terms.append(sid)
    if len(ends) != 2 or len(terms) < 2: continue
    g0, gN = gpos(terms[0]), gpos(terms[-1])
    e0, e1 = ends
    cross = (gN[0]-g0[0])*(e1[1]-e0[1]) - (gN[1]-g0[1])*(e1[0]-e0[0])
    if cross < 0: e0, e1 = e1, e0
    anchors.append((*gpos(terms[0]), *e0, terms[0]))
    anchors.append((*gpos(terms[-1]), *e1, terms[-1]))
print(f'端点锚 {len(anchors)}')

# ---------- 2) 仿射拟合(端点锚) 引导 单共享线对交点锚 ----------
def fit_affine(pts):
    P = np.array([[a[0], a[1], 1] for a in pts])
    Q = np.array([[a[2], a[3]] for a in pts])
    W, *_ = np.linalg.lstsq(P, Q, rcond=None)   # W: (3,2)
    return lambda p: (float(np.dot(W[:, 0], [p[0], p[1], 1])), float(np.dot(W[:, 1], [p[0], p[1], 1])))
aff = fit_affine(anchors)
pair_list = []
for r1 in lines:
    for r2 in lines:
        if r1 < r2:
            sh = set(lines[r1]['stations']) & set(lines[r2]['stations'])
            if len(sh) == 1: pair_list.append((r1, r2, next(iter(sh))))
n_int = 0
for r1, r2, sid in pair_list:
    if r1 not in GEOM or r2 not in GEOM: continue
    its = []
    for a in GEOM[r1]:
        for b in GEOM[r2]:
            p = seg_int(a, b)
            if p: its.append(p)
    if not its: continue
    gx, gy = aff(gpos(sid))
    px, py = min(its, key=lambda q: math.hypot(q[0]-gx, q[1]-gy))
    if math.hypot(px-gx, py-gy) < 150:
        anchors.append((*gpos(sid), px, py, sid)); n_int += 1
print(f'交点锚 +{n_int} (共 {len(anchors)})')

# ---------- 3) TPS ----------
def fit_tps(P, Q, reg=1e-3):
    n = len(P)
    def U(r):
        r = max(r, 1e-9); return r * r * math.log(r)
    K = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            K[i, j] = U(np.linalg.norm(P[i] - P[j]))
    K += reg * np.eye(n)
    L = np.zeros((n + 3, n + 3))
    L[:n, :n] = K
    L[:n, n:] = np.hstack([P, np.ones((n, 1))])
    L[n:, :n] = np.hstack([P, np.ones((n, 1))]).T
    Y = np.zeros((n + 3, 2)); Y[:n] = Q
    W = np.linalg.solve(L, Y)
    P = np.asarray(P)
    def warp(pt):
        pt = np.asarray(pt, dtype=float)
        k = np.array([U(np.linalg.norm(pt - p)) for p in P])
        return k @ W[:n] + np.array([pt[0], pt[1], 1]) @ W[n:]
    return warp
# 鲁棒两轮
cur = list(anchors)
for _ in range(2):
    warp = fit_tps(np.array([[a[0], a[1]] for a in cur]), np.array([[a[2], a[3]] for a in cur]))
    cur = [a for a in cur if math.hypot(*(warp((a[0], a[1])) - np.array([a[2], a[3]]))) < 60]
warp = fit_tps(np.array([[a[0], a[1]] for a in cur]), np.array([[a[2], a[3]] for a in cur]))
print(f'TPS 锚 {len(cur)}/{len(anchors)}')

# ---------- 4) 全站放置：贴线 + 唯一字形 ----------
result = {}
def try_glyph(q, sid, rad=30):
    best_i, best_d = None, 1e18
    for i, g in enumerate(glyphs):
        d = math.hypot(g[0]-q[0], g[1]-q[1])
        if d < best_d: best_d, best_i = d, i
    if best_d > rad: return None
    if best_i in glyph_used: return None
    _, ld = snap_line(glyphs[best_i][0], glyphs[best_i][1], st[sid]['lines'][0])
    if ld > 8: return None
    return best_i

order = sorted(data['stations'], key=lambda s: (len(s['lines']), s['id']), reverse=True)  # 换乘优先
for s in order:
    sid = s['id']
    wx, wy = warp(gpos(sid))
    # 候选线：贴得最近的
    ranked = sorted(s['lines'], key=lambda r: snap_line(wx, wy, r)[1] if r in GEOM else 1e9)
    q, d0 = snap_line(wx, wy, ranked[0])
    gi = try_glyph(q, sid)
    if gi is not None:
        glyph_used[gi] = sid
        result[sid] = [round(glyphs[gi][0], 1), round(glyphs[gi][1], 1), 0.0]
    else:
        result[sid] = [round(q[0], 1), round(q[1], 1), round(d0, 1)]
errs = [v[2] for v in result.values()]
snap_n = len(glyph_used)
print(f'放置: 字形锁定 {snap_n}/314, 未锁中位偏移 {np.median(errs):.1f}px')

# ---------- 5) 校验：同线异站 ≥6px ----------
bad = []
for l in lines.values():
    seq = [s for sq in seqs_of(l) for s in sq]
    uniq = list(dict.fromkeys(seq))
    for i in range(len(uniq)):
        for j in range(i + 1, len(uniq)):
            a, b = result[uniq[i]], result[uniq[j]]
            if math.hypot(a[0]-b[0], a[1]-b[1]) < 6:
                bad.append((l['ref'], uniq[i], uniq[j]))
print('同线 <6px 对:', len(bad), bad[:8])

json.dump(result, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print('输出完成')
