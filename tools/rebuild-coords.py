#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 坐标重建（防坍塌版）：
#   底座 = TPS + 贴线贴字形（build_tim_layout 的 1~7 节）
#   修复 = 端点就近链端 / 支线栅格跟踪，全部带防坍塌守卫（同线异站距离 >= 6px）
#   校验 = 逐线站距检测 + 沿线分布报告，任何坍塌直接报错退出
import json, math, re, bisect, heapq
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
import numpy as np
from PIL import Image

SVG = 'E:/GuangzhouBusViewer/assets/tim-gzfmetro.svg'
RASTER = 'E:/GuangzhouBusViewer/assets/_raster-base.png'   # 由调用方先生成
SRC = 'E:/GuangzhouMetroQuiz/Content/Data/MetroData.json'
OUT = 'E:/GuangzhouBusViewer/assets/tim-coords.json'

NS = '{http://www.w3.org/2000/svg}'
tree = ET.parse(SVG); root = tree.getroot()
svg_text = open(SVG, encoding='utf-8').read()
cls_colors = dict(re.findall(r'\.(\w+)\{[^}]*?stroke:(#[0-9A-Fa-f]{6})', svg_text))
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

data = json.load(open(SRC, encoding='utf-8-sig'))
stations = {s['id']: s for s in data['stations']}
lines = {l['ref']: l for l in data['lines']}

def line_geom(gname):
    g = find_g(gname); segs = []
    for el in g.iter():
        tag = el.tag.replace(NS, '')
        if tag == 'line':
            x1, y1, x2, y2 = map(float, (el.get('x1'), el.get('y1'), el.get('x2'), el.get('y2')))
            if math.hypot(x2 - x1, y2 - y1) > 0.1: segs.append((x1, y1, x2, y2))
        elif tag == 'path':
            d = el.get('d', '').strip()
            m = re.match(r'M\s*(-?[\d.]+)[ ,](-?[\d.]+)', d)
            if not m: continue
            mx, my = float(m.group(1)), float(m.group(2))
            ns = [float(x) for x in re.findall(r'-?\d+\.?\d*', d[m.end():])]
            if len(ns) >= 2:
                ex, ey = mx + ns[-2], my + ns[-1]
                if math.hypot(ex - mx, ey - my) > 0.1: segs.append((mx, my, ex, ey))
    return segs

GEOM = {ref: line_geom(g) for g, ref in GROUP.items()}

glyphs = []
for el in find_g('站点').iter():
    tag = el.tag.replace(NS, '')
    if tag == 'circle': glyphs.append((float(el.get('cx')), float(el.get('cy'))))
    elif tag == 'path':
        m = re.match(r'M\s*(-?[\d.]+)[ ,](-?[\d.]+)', el.get('d', '').strip() or '')
        if m: glyphs.append((float(m.group(1)), float(m.group(2))))

def dist_pt_seg(px, py, s):
    x1, y1, x2, y2 = s
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    t = 0 if L2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

def snap_to_line(px, py, ref):
    best, bp = 1e18, (px, py)
    for s in GEOM[ref]:
        d = dist_pt_seg(px, py, s)
        if d < best: best = d; bp = None
    # 重算投影点
    best = 1e18; bp = (px, py)
    for x1, y1, x2, y2 in GEOM[ref]:
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        t = 0 if L2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
        qx, qy = x1 + t * dx, y1 + t * dy
        d = math.hypot(px - qx, py - qy)
        if d < best: best, bp = d, (qx, qy)
    return bp, best

def geo_xy(lat, lon):
    kx = 111320.0 * math.cos(math.radians(23.15))
    return (lon * kx, -lat * 110540.0)

# ---------- 锚点 ----------
def endpoints(ref):
    occ = defaultdict(int)
    pts = set()
    for s in GEOM[ref]:
        pts.add((s[0], s[1])); pts.add((s[2], s[3]))
        occ[(s[0], s[1])] += 1; occ[(s[2], s[3])] += 1
    return [p for p, n in occ.items() if n == 1]

pair_shared = {}
for r1, l1 in lines.items():
    for r2, l2 in lines.items():
        if r1 < r2:
            sh = set(l1['stations']) & set(l2['stations'])
            if sh: pair_shared[(r1, r2)] = sorted(sh)

def seg_intersect(a, b):
    x1, y1, x2, y2 = a; x3, y3, x4, y4 = b
    d = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if abs(d) < 1e-9: return None
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / d
    u = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / d
    if -0.05 <= t <= 1.05 and -0.05 <= u <= 1.05:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None

def line_intersections(r1, r2, limit=8):
    pts = []
    for a in GEOM[r1]:
        for b in GEOM[r2]:
            p = seg_intersect(a, b)
            if p: pts.append(p)
    out = []
    for p in pts:
        if all(math.hypot(p[0] - q[0], p[1] - q[1]) > 8 for q in out): out.append(p)
    return out[:limit]

anchors = []
for ref, l in lines.items():
    ends = endpoints(ref)
    terms = []
    seen = set()
    for seq in [l['stations']] + l.get('branches', []):
        for st_id in (seq[0], seq[-1]):
            if st_id not in seen: seen.add(st_id); terms.append(st_id)
    if len(ends) != len(terms) or len(ends) != 2: continue
    tg = [geo_xy(stations[t]['lat'], stations[t]['lon']) for t in terms]
    (gx1, gy1), (gx2, gy2) = tg[0], tg[1]
    (sx1, sy1), (sx2, sy2) = ends[0], ends[1]
    cross = (gx2 - gx1) * (sy2 - sy1) - (gy2 - gy1) * (sx2 - sx1)
    pairs = [(terms[0], ends[0]), (terms[1], ends[1])] if cross > 0 else [(terms[0], ends[1]), (terms[1], ends[0])]
    for t, (sx, sy) in pairs:
        gx, gy = geo_xy(stations[t]['lat'], stations[t]['lon'])
        anchors.append((gx, gy, sx, sy, t))

# ---------- TPS ----------
def fit_tps(P, Q, reg=1e-3):
    n = len(P)
    def U(r):
        r = max(r, 1e-9)
        return r * r * math.log(r)
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

def collect_pair_anchors(warp_fn):
    out = []
    for (r1, r2), shared in pair_shared.items():
        if not shared: continue
        its = line_intersections(r1, r2)
        if not its: continue
        used = set()
        for sid in shared:
            gx, gy = geo_xy(stations[sid]['lat'], stations[sid]['lon'])
            wx, wy = warp_fn((gx, gy))
            for i in sorted(range(len(its)), key=lambda k: math.hypot(its[k][0] - wx, its[k][1] - wy)):
                if i not in used:
                    used.add(i); out.append((gx, gy, its[i][0], its[i][1], sid)); break
    return out

def robust_fit(pool, rounds=3):
    cur = list(pool); warp_fn = None
    for _ in range(rounds):
        P_ = np.array([[a[0], a[1]] for a in cur]); Q_ = np.array([[a[2], a[3]] for a in cur])
        warp_fn = fit_tps(P_, Q_)
        cur = [a for a in cur if math.hypot(*(warp_fn((a[0], a[1])) - np.array([a[2], a[3]]))) < 60]
    return warp_fn, cur

warp0 = fit_tps(np.array([[a[0], a[1]] for a in anchors]), np.array([[a[2], a[3]] for a in anchors]))
pair_anchors = collect_pair_anchors(warp0)
warp, kept = robust_fit(anchors + pair_anchors)
print(f'锚点 {len(anchors)}+{len(pair_anchors)} -> 保留 {len(kept)}')

# ---------- 防坍塌守卫 ----------
result = {}
def conflicts(sid, x, y):
    """同线其它已放置站是否 <6px（真换乘同点允许：站名不同即冲突）"""
    ref_lines = set(stations[sid]['lines'])
    for other, (ox, oy, oe) in result.items():
        if other == sid: continue
        if set(stations[other]['lines']) & ref_lines and math.hypot(x - ox, y - oy) < 6:
            return True
    return False

def glyph_snap_guarded(q, ref, sid):
    gb = min(glyphs, key=lambda g: math.hypot(g[0] - q[0], g[1] - q[1]))
    if math.hypot(gb[0] - q[0], gb[1] - q[1]) < 25 and not conflicts(sid, gb[0], gb[1]):
        _, d2 = snap_to_line(gb[0], gb[1], ref)
        if d2 < 6: return gb
    return None if conflicts(sid, q[0], q[1]) else q

# ---------- 全站放置（底座） ----------
for sid, s in stations.items():
    gx, gy = geo_xy(s['lat'], s['lon'])
    wx, wy = warp((gx, gy))
    best_ref, best_d, bp = None, 1e18, (wx, wy)
    for ref in s['lines']:
        if ref not in GEOM: continue
        q, d = snap_to_line(wx, wy, ref)
        if d < best_d: best_d, bp, best_ref = d, q, ref
    g = glyph_snap_guarded(bp, best_ref, sid)
    placed = g if g is not None else None
    if placed is None:
        # 候选字形按距离排序取第一个不冲突的
        cands = sorted(glyphs, key=lambda g2: math.hypot(g2[0] - bp[0], g2[1] - bp[1]))[:8]
        placed = bp
        for g2 in cands:
            if math.hypot(g2[0] - bp[0], g2[1] - bp[1]) > 30: break
            if not conflicts(sid, g2[0], g2[1]):
                _, d2 = snap_to_line(g2[0], g2[1], best_ref)
                if d2 < 6: placed = g2; break
    result[sid] = [round(placed[0], 1), round(placed[1], 1), round(best_d, 1)]

errs = [v[2] for v in result.values()]
print(f'底座: 中位 {np.median(errs):.1f}px, >30px {sum(1 for e in errs if e > 30)}')

# ---------- 端点修复（守卫版） ----------
fixed = 0
from collections import Counter
for sid, err in [(k, v[2]) for k, v in result.items() if v[2] > 30]:
    ref = stations[sid]['lines'][0]
    l = lines[ref]
    nb = None
    for seq in [l['stations']] + l.get('branches', []):
        if sid in seq:
            i = seq.index(sid)
            if i == 0 and len(seq) > 1: nb = seq[1]
            elif i == len(seq) - 1: nb = seq[i - 1]
            break
    if not nb or nb not in result or result[nb][2] > 15: continue
    nx, ny = result[nb][0], result[nb][1]
    ends = endpoints(ref)
    if not ends: continue
    ex, ey = min(ends, key=lambda p: math.hypot(p[0] - nx, p[1] - ny))
    if math.hypot(ex - nx, ey - ny) > 160: continue
    if conflicts(sid, ex, ey): continue
    e2 = dist_pt_seg(ex, ey, GEOM[ref][0]) if GEOM[ref] else 99
    e2 = min(dist_pt_seg(ex, ey, s2) for s2 in GEOM[ref])
    if e2 < err:
        result[sid] = [round(ex, 1), round(ey, 1), round(e2, 1)]; fixed += 1
print(f'端点修复 {fixed}')

# ---------- 沿线分布校验（防坍塌最终关卡） ----------
bad = []
for ref, l in lines.items():
    if ref not in GEOM: continue
    sts = l['stations'] + [s for b in l.get('branches', []) for s in b]
    pts = [(s, result[s][:2]) for s in sts if s in result]
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            d = math.hypot(pts[i][1][0] - pts[j][1][0], pts[i][1][1] - pts[j][1][1])
            if d < 6:
                bad.append((ref, pts[i][0], pts[j][0], round(d, 1)))
print('坍塌冲突:', len(bad), bad[:10])
if bad:
    raise SystemExit('存在坍塌，中止输出')

json.dump(result, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
errs = [v[2] for v in result.values()]
print(f'输出 {len(result)} 站: 中位 {np.median(errs):.1f}px, >30px {sum(1 for e in errs if e > 30)}')
