#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_tim_layout.py — 从 Tim 版广佛地铁图 SVG 提取我们 19 线 314 站的示意坐标
管线：线路几何(线段) → 锚点(端点+换乘线线交点) → 地理→SVG 的 TPS 变换 → 贴线投影 → 贴字形微调 → 输出 tim-coords.json
底图版权: Guangzhou-Foshan Metro Diagram by Tim Wu, CC BY-SA 4.0
"""
import xml.etree.ElementTree as ET
import json, math, re, sys
import numpy as np

SVG = 'E:/GuangzhouBusViewer/assets/tim-gzfmetro.svg'
SRC = 'E:/GuangzhouMetroQuiz/Content/Data/MetroData.json'
OUT = 'E:/GuangzhouBusViewer/assets/tim-coords.json'

NS = '{http://www.w3.org/2000/svg}'
tree = ET.parse(SVG)
root = tree.getroot()
parent = {c: p for p in tree.iter() for c in p}

def decode_id(i):
    if not i: return '?'
    for d in range(10): i = i.replace(f'_x3{d}_', str(d))
    return i

def find_group(name):
    for c in root.iter(NS + 'g'):
        if decode_id(c.get('id', '')) == name:
            return c
    return None

data = json.load(open(SRC, encoding='utf-8-sig'))
stations = {s['id']: s for s in data['stations']}
lines = {l['ref']: l for l in data['lines']}

GROUP = {'1': '1', '2': '2', '3': '3', '4': '4', '5': '5', '6': '6', '7': '7',
         '8': '8', '9_3_': '9', '10_1_': '10', '11': '11', '12': '12', '13': '13',
         '14': '14', '18': '18', '21': '21', '22': '22', 'GF': 'GF', 'APM_3_': 'APM'}

# ---------- 1. 线路几何 ----------
def line_geom(gname):
    """返回 [(x1,y1,x2,y2), ...]（圆角 path 以弦近似）"""
    g = find_group(gname)
    segs = []
    for el in g.iter():
        tag = el.tag.replace(NS, '')
        if tag == 'line':
            x1, y1, x2, y2 = map(float, (el.get('x1'), el.get('y1'), el.get('x2'), el.get('y2')))
            if math.hypot(x2 - x1, y2 - y1) > 0.1:
                segs.append((x1, y1, x2, y2))
        elif tag == 'path':
            d = el.get('d', '').strip()
            m = re.match(r'M\s*(-?[\d.]+)[ ,](-?[\d.]+)', d)
            if not m: continue
            mx, my = float(m.group(1)), float(m.group(2))
            nums = [float(x) for x in re.findall(r'-?\d+\.?\d*', d[m.end():])]
            if len(nums) >= 2:
                ex, ey = mx + nums[-2], my + nums[-1]
                if math.hypot(ex - mx, ey - my) > 0.1:
                    segs.append((mx, my, ex, ey))
    return segs

GEOM = {ref: line_geom(g) for g, ref in GROUP.items()}

# ---------- 2. 字形锚点（站点层所有元素的位置） ----------
glyphs = []  # [(x,y)]
st = find_group('站点')
for el in st.iter():
    tag = el.tag.replace(NS, '')
    if tag == 'circle':
        glyphs.append((float(el.get('cx')), float(el.get('cy'))))
    elif tag == 'path':
        m = re.match(r'M\s*(-?[\d.]+)[ ,](-?[\d.]+)', el.get('d', '').strip() or '')
        if m:
            glyphs.append((float(m.group(1)), float(m.group(2))))

# ---------- 3. 几何工具 ----------
def seg_intersect(a, b):
    """线段交点或 None"""
    x1, y1, x2, y2 = a; x3, y3, x4, y4 = b
    d = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if abs(d) < 1e-9: return None
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / d
    u = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / d
    if -0.05 <= t <= 1.05 and -0.05 <= u <= 1.05:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None

def dist_pt_seg(px, py, s):
    x1, y1, x2, y2 = s
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    t = 0 if L2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    qx, qy = x1 + t * dx, y1 + t * dy
    return math.hypot(px - qx, py - qy), (qx, qy)

def snap_to_line(px, py, ref):
    best, bp = 1e18, (px, py)
    for s in GEOM[ref]:
        d, q = dist_pt_seg(px, py, s)
        if d < best: best, bp = d, q
    return bp, best

# ---------- 4. 地理投影（简单墨卡托-like，米制） ----------
def geo_xy(lat, lon):
    kx = 111320.0 * math.cos(math.radians(23.15))
    return (lon * kx, -lat * 110540.0)

# ---------- 5. 锚点 ----------
# 5a. 线路端点: 几何图的度-1节点 <-> 我们该线的端站
def endpoints(ref):
    """几何图端点（近似：线段端点中远离其它段的点）"""
    pts = []
    for s in GEOM[ref]:
        pts.append((s[0], s[1])); pts.append((s[2], s[3]))
    ends = []
    for (x, y) in set(pts):
        cnt = 0
        for s in GEOM[ref]:
            for ex, ey in ((s[0], s[1]), (s[2], s[3])):
                if math.hypot(ex - x, ey - y) < 2.0: cnt += 1
        if cnt == 1: ends.append((x, y))
    return ends

# 5b. 换乘锚: 两线共享站 → 几何交点
pair_shared = {}
for r1, l1 in lines.items():
    for r2, l2 in lines.items():
        if r1 < r2:
            sh = set(l1['stations']) & set(l2['stations'])
            if sh:
                pair_shared[(r1, r2)] = sorted(sh)

anchors = []  # [(gx, gy, sx, sy, station_id)]

# 端点锚
for ref, l in lines.items():
    ends = endpoints(ref)
    terms = []
    seen = set()
    for seq in [l['stations']] + l.get('branches', []):
        for st_id in (seq[0], seq[-1]):
            if st_id not in seen:
                seen.add(st_id); terms.append(st_id)
    if len(ends) != len(terms):
        continue  # 几何端点数对不上, 交给换乘锚
    # 地理上按主方向匹配: 对每组 (term_geo, svg_end) 选全局最优一一对应
    tg = [geo_xy(stations[t]['lat'], stations[t]['lon']) for t in terms]
    if len(ends) == 1:
        anchors.append((tg[0][0], tg[0][1], ends[0][0], ends[0][1], terms[0]))
        continue
    # 穷举小规模排列
    from itertools import permutations
    best_perm, best_err = None, 1e18
    for perm in permutations(range(len(ends))):
        err = 0
        for i, j in enumerate(perm):
            # 端点相对该线质心的方向应与地理一致 → 用相对向量距离
            err += 0  # 占位, 方向匹配放在 TPS 迭代里
        best_perm = perm
        break
    # 简化: 按地理向量与 SVG 向量的方向匹配(线的主轴对齐)
    if len(ends) == 2:
        (gx1, gy1), (gx2, gy2) = tg[0], tg[1]
        (sx1, sy1), (sx2, sy2) = ends[0], ends[1]
        # 地理向量
        gvx, gvy = gx2 - gx1, gy2 - gy1
        svx, svy = sx2 - sx1, sy2 - sy1
        cross = gvx * svy - gvy * svx
        if cross > 0:  # 同向
            pairs = [(terms[0], ends[0]), (terms[1], ends[1])]
        else:
            pairs = [(terms[0], ends[1]), (terms[1], ends[0])]
        for t, (sx, sy) in pairs:
            gx, gy = geo_xy(stations[t]['lat'], stations[t]['lon'])
            anchors.append((gx, gy, sx, sy, t))

# 换乘锚（两线交点 → 共享站; 共享站唯一时直接用, 多个时先粗匹配后筛）
def line_intersections(r1, r2, limit=6):
    pts = []
    for a in GEOM[r1]:
        for b in GEOM[r2]:
            p = seg_intersect(a, b)
            if p: pts.append(p)
    # 去重聚类
    out = []
    for p in pts:
        if all(math.hypot(p[0]-q[0], p[1]-q[1]) > 8 for q in out):
            out.append(p)
    return out[:limit]

for (r1, r2), shared in pair_shared.items():
    its = line_intersections(r1, r2)
    if not its: continue
    if len(shared) == 1:
        gx, gy = geo_xy(stations[shared[0]]['lat'], stations[shared[0]]['lon'])
        # 取离地理锚(由已有锚点粗变换)最近的交点 —— 先用质心启发
        anchors.append((gx, gy, its[0][0], its[0][1], shared[0]))
        continue
    # 多共享站: 需要粗变换后再分配 —— 暂跳过端点/交点歧义, 交给 TPS 迭代
    # 这里先记录, 第二轮用拟合好的 TPS 分配
    pass

print(f'初步锚点: {len(anchors)} 个')

# ---------- 6. TPS ----------
def fit_tps(P, Q, reg=1e-3):
    """P: (N,2) 源, Q: (N,2) 目标; 返回函数"""
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
    Y = np.zeros((n + 3, 2))
    Y[:n] = Q
    W = np.linalg.solve(L, Y)
    P = np.asarray(P)
    def warp(pt):
        pt = np.asarray(pt, dtype=float)
        k = np.array([U(np.linalg.norm(pt - p)) for p in P])
        return k @ W[:n] + np.array([pt[0], pt[1], 1]) @ W[n:]
    return warp

# ---------- 6b. 迭代精化 ----------
# 多共享站对: 用初始 TPS 把每个共享站映射到 SVG, 取该对线路交点中最近者补充为锚点;
# 再做鲁棒拟合(剔除残差>60px 的锚), 共 3 轮
def collect_pair_anchors(warp_fn):
    out = []
    for (r1, r2), shared in pair_shared.items():
        if not shared: continue
        its = line_intersections(r1, r2, limit=10)
        if not its: continue
        used = set()
        for sid in shared:
            gx, gy = geo_xy(stations[sid]['lat'], stations[sid]['lon'])
            wx, wy = warp_fn((gx, gy))
            for i in sorted(range(len(its)), key=lambda k: math.hypot(its[k][0]-wx, its[k][1]-wy)):
                if i not in used:
                    used.add(i)
                    out.append((gx, gy, its[i][0], its[i][1], sid))
                    break
    return out

def robust_fit(pool, rounds=3):
    cur = list(pool)
    warp_fn = None
    for _ in range(rounds):
        P_ = np.array([[a[0], a[1]] for a in cur])
        Q_ = np.array([[a[2], a[3]] for a in cur])
        warp_fn = fit_tps(P_, Q_)
        keep = []
        for a in cur:
            gx, gy = warp_fn((a[0], a[1]))
            if math.hypot(gx - a[2], gy - a[3]) < 60:
                keep.append(a)
        cur = keep
    return warp_fn, cur

anchors = anchors[:200]
P = np.array([[a[0], a[1]] for a in anchors])
Q = np.array([[a[2], a[3]] for a in anchors])
warp0 = fit_tps(P, Q)
pair_anchors = collect_pair_anchors(warp0)
print(f'换乘对锚点补充: {len(pair_anchors)} 个')
warp, kept = robust_fit(anchors + pair_anchors)
print(f'鲁棒拟合保留锚点: {len(kept)}/{len(anchors) + len(pair_anchors)}')

# ---------- 7. 全站变换 + 贴线 + 贴字形 ----------
result = {}
for sid, s in stations.items():
    gx, gy = geo_xy(s['lat'], s['lon'])
    wx, wy = warp((gx, gy))
    # 贴到该站所属线（多线取贴得最近的）
    best_ref, best_d, bp = None, 1e18, (wx, wy)
    for ref in s['lines']:
        if ref not in GEOM: continue
        q, d = snap_to_line(wx, wy, ref)
        if d < best_d: best_d, bp, best_ref = d, q, ref
    # 贴字形（28px 内且仍在本线几何 6px 内，避免贴到邻线站）
    gx_, gy_ = bp
    gb = min(glyphs, key=lambda g: math.hypot(g[0]-gx_, g[1]-gy_))
    if math.hypot(gb[0]-gx_, gb[1]-gy_) < 28:
        _, d2 = snap_to_line(gb[0], gb[1], best_ref)
        if d2 < 6:
            bp = gb
    result[sid] = [round(bp[0], 1), round(bp[1], 1), round(best_d, 1)]

json.dump(result, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print(f'输出 {len(result)} 站 → {OUT}')

# ---------- 7b. 线内可信站插值修复（共享站只在更优时覆盖，避免跨线改坏） ----------
fixed = 0
for ref, l in lines.items():
    if ref not in GEOM: continue
    seqs = [l['stations']] + l.get('branches', [])
    for seq in seqs:
        trust = [(i, result[s][0], result[s][1]) for i, s in enumerate(seq)
                 if s in result and result[s][2] < 15]
        if len(trust) < 2: continue
        (i0, x0, y0), (i1, x1, y1) = trust[0], trust[-1]
        for i, sid in enumerate(seq):
            if i <= i0 or i >= i1 or sid not in result: continue
            err = result[sid][2]
            if err <= 20: continue
            t = (i - i0) / (i1 - i0)
            px, py = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            q, d = snap_to_line(px, py, ref)
            gb = min(glyphs, key=lambda g: math.hypot(g[0] - q[0], g[1] - q[1]))
            if math.hypot(gb[0] - q[0], gb[1] - q[1]) < 20:
                _, d2 = snap_to_line(gb[0], gb[1], ref)
                if d2 < 6: q, d = gb, d2
            if d < err:
                result[sid] = [round(q[0], 1), round(q[1], 1), round(d, 1)]
                fixed += 1

json.dump(result, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
errs = [v[2] for v in result.values()]
print(f'7b 修复 {fixed} 站; TPS 阶段: 中位 {np.median(errs):.1f}px, >30px: {sum(1 for e in errs if e > 30)} 站')

# ---------- 7c. 沿线链式重排 ----------
# 把每条线的 SVG 几何建成"主链+分支"的路径树，好站(err<=15)投影为沿线锚点，
# 坏站按站序在相邻锚点间插值弧长后取链上点位，再贴字形；只在更优时覆盖。
from collections import defaultdict, deque

def line_chains(segs):
    keys = {}
    def key(x, y): return (round(x * 4) / 4, round(y * 4) / 4)
    edges = set()
    for x1, y1, x2, y2 in segs:
        ka, kb = key(x1, y1), key(x2, y2)
        if ka == kb: continue
        edges.add((ka, kb))
        keys.setdefault(ka, (x1, y1)); keys.setdefault(kb, (x2, y2))
    adj = defaultdict(set)
    for a, b in edges: adj[a].add(b); adj[b].add(a)
    if not adj: return None
    def bfs(s):
        dist = {s: 0}; prev = {}
        q = deque([s])
        while q:
            u = q.popleft()
            for v in adj[u]:
                if v not in dist:
                    dist[v] = dist[u] + 1; prev[v] = u; q.append(v)
        far = max(dist, key=dist.get)
        return far, prev
    u1, _ = bfs(next(iter(adj)))
    u2, prev = bfs(u1)
    chain = []
    x = u2
    while x != u1:
        chain.append(x); x = prev[x]
    chain.append(u1); chain.reverse()
    chain_set = set(chain)
    branches = []
    visited = set(chain_set)
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

def chain_geometry(node_list, keys):
    pts = [keys[k] for k in node_list]
    arc = [0.0]
    for i in range(1, len(pts)):
        arc.append(arc[-1] + math.hypot(pts[i][0]-pts[i-1][0], pts[i][1]-pts[i-1][1]))
    return pts, arc

def point_at(pts, arc, s):
    if s <= 0: return pts[0]
    if s >= arc[-1]: return pts[-1]
    import bisect
    i = bisect.bisect_left(arc, s)
    t = (s - arc[i-1]) / max(1e-9, arc[i] - arc[i-1])
    return (pts[i-1][0] + t*(pts[i][0]-pts[i-1][0]), pts[i-1][1] + t*(pts[i][1]-pts[i-1][1]))

def project_s(pts, arc, px, py):
    best, bs = 1e18, 0.0
    for i in range(1, len(pts)):
        x1, y1 = pts[i-1]; x2, y2 = pts[i]
        dx, dy = x2-x1, y2-y1
        L2 = dx*dx + dy*dy
        t = 0 if L2 == 0 else max(0.0, min(1.0, ((px-x1)*dx + (py-y1)*dy) / L2))
        qx, qy = x1+t*dx, y1+t*dy
        d = math.hypot(px-qx, py-qy)
        if d < best: best, bs = d, arc[i-1] + t * math.hypot(dx, dy)
    return bs

def glyph_snap(q, ref):
    gb = min(glyphs, key=lambda g: math.hypot(g[0]-q[0], g[1]-q[1]))
    if math.hypot(gb[0]-q[0], gb[1]-q[1]) < 22:
        _, d2 = snap_to_line(gb[0], gb[1], ref)
        if d2 < 6: return gb
    return q

fixed_c = 0
for ref, l in lines.items():
    if ref not in GEOM: continue
    ch = line_chains(GEOM[ref])
    if not ch: continue
    chain, branches, keys = ch
    pts, arc = chain_geometry(chain, keys)
    L = arc[-1]
    if L < 10: continue

    # 主线：非环线用首末站锚定链两端（方向由好锚投票），环线仅用好锚
    seq = l['stations']
    n = len(seq)
    good = {i: (result[seq[i]][0], result[seq[i]][1])
            for i in range(n) if seq[i] in result and result[seq[i]][2] <= 15}

    def build_anchors(reverse):
        anchors = []
        if not l.get('loop'):
            anchors.append((0, 0.0))
            anchors.append((n - 1, L))
        for i, (px, py) in good.items():
            s = project_s(pts, arc, px, py)
            anchors.append((i, (L - s) if reverse else s))
        anchors.sort()
        # 单调修复：前向扫描取 running max
        fixed_anc = [anchors[0]]
        for a in anchors[1:]:
            fixed_anc.append((a[0], max(a[1], fixed_anc[-1][1])))
        # 评分：锚点分布跨度 + 与好锚自洽
        score = len(fixed_anc)
        if not l.get('loop') and n > 2:
            score += 0  # 首末锚恒有
        return score, fixed_anc

    def orientation_ok(anchors):
        # 首末锚定下看好锚是否大量"逆序"（说明方向错）
        bad_pairs = 0
        ga = [a for a in anchors if a[0] in good]
        for a, b in zip(ga, ga[1:]):
            if b[0] > a[0] + 1 and b[1] < a[1] - 1: bad_pairs += 1
        return bad_pairs <= max(1, len(ga) // 3)

    _, ancA = build_anchors(False)
    _, ancB = build_anchors(True)
    anchors = ancA if orientation_ok(ancA) else (ancB if orientation_ok(ancB) else ancA)

    for k in range(len(anchors) - 1):
        i0, s0 = anchors[k]; i1, s1 = anchors[k + 1]
        if i1 - i0 <= 1: continue
        for i in range(i0 + 1, i1):
            sid = seq[i]
            if sid not in result or result[sid][2] <= 15: continue
            s = s0 + (s1 - s0) * (i - i0) / (i1 - i0)
            q = point_at(pts, arc, s)
            q = glyph_snap(q, ref)
            _, d = snap_to_line(q[0], q[1], ref)
            if d < result[sid][2]:
                result[sid] = [round(q[0], 1), round(q[1], 1), round(d, 1)]
                fixed_c += 1

    # 分线（3号线/14号线支线）：以支线序列各自重排
    for br_seq in l.get('branches', []):
        if not br_seq: continue
        jid = br_seq[0]  # 与主线衔接的站
        if jid not in result: continue
        jp = (result[jid][0], result[jid][1])
        # 找最近的分支路径
        best_br, bd = None, 1e18
        for br in branches:
            b0 = keys[br[0]]
            d = math.hypot(b0[0]-jp[0], b0[1]-jp[1])
            if d < bd: bd, best_br = d, br
        if best_br is None or bd > 25: continue
        bpts, barc = chain_geometry(best_br, keys)
        bseq = br_seq[1:]  # 衔接站已在主线定位
        good_b = [(i, project_s(bpts, barc, result[s][0], result[s][1]))
                  for i, s in enumerate(bseq) if s in result and result[s][2] <= 15]
        if not good_b:
            # 无好锚: 按弧长等分
            good_b = [(len(bseq)-1, barc[-1])]
        anchor_end = good_b[-1]
        for i, sid in enumerate(bseq):
            if sid not in result or result[sid][2] <= 20: continue
            s = barc[-1] * (i + 1) / (anchor_end[0] + 1)
            q = point_at(bpts, barc, s)
            q = glyph_snap(q, ref)
            _, d = snap_to_line(q[0], q[1], ref)
            if d < result[sid][2]:
                result[sid] = [round(q[0],1), round(q[1],1), round(d,1)]
                fixed_c += 1

json.dump(result, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
errs = [v[2] for v in result.values()]
print(f'7c 链式重排修复 {fixed_c} 站; 最终: 中位 {np.median(errs):.1f}px, 均值 {np.mean(errs):.1f}, >30px: {sum(1 for e in errs if e > 30)} 站')

# ---------- 8. 质量报告 ----------
errs = [v[2] for v in result.values()]
print(f'贴线距离: 中位 {np.median(errs):.1f}px, 均值 {np.mean(errs):.1f}, 最大 {np.max(errs):.0f}, >30px: {sum(1 for e in errs if e>30)} 站')

# ---------- 9. 渲染叠加预览 ----------
from PIL import Image, ImageDraw
im = Image.open('E:/GuangzhouBusViewer/assets/_tim-raster.png').convert('RGB')
SC_X = 2561 / 2848.5  # 栅格与 viewBox 比例
SC_Y = 1529 / 2054.25
sc = max(SC_X, SC_Y)
dr = ImageDraw.Draw(im)
for ref, l in lines.items():
    for seq in [l['stations']] + l.get('branches', []):
        pts = [(result[z][0]*SC_X, result[z][1]*SC_Y) for z in seq if z in result]
        if len(pts) >= 2:
            dr.line(pts, fill=l['color'], width=3)
for sid, (x, y, d) in result.items():
    px, py = x*SC_X, y*SC_Y
    r = 4 if d > 15 else 3
    dr.ellipse([px-r, py-r, px+r, py+r], outline=(255,0,0), width=2)
im.save('E:/GuangzhouBusViewer/assets/_tim-overlay-preview.png')
print('预览 → _tim-overlay-preview.png')
