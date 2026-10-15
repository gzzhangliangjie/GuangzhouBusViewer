#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 坍塌修复（整线走廊版）：
#   每线用矢量几何端点在 1:1 栅格上按线色跟踪完整走廊（不依赖站锚，杜绝坏锚传染）；
#   好站投影走廊得弧长参数（保序），坏站在相邻好锚间按站序插值弧长；
#   位置取走廊点 → 天然互异。分支序列以衔接站为端点同法处理。
import json, math, re, bisect
import xml.etree.ElementTree as ET
from collections import defaultdict
from PIL import Image

SVG = 'E:/GuangzhouBusViewer/assets/tim-gzfmetro.svg'
RASTER = 'E:/GuangzhouBusViewer/assets/_tim-raster.png'
SRC = 'E:/GuangzhouMetroQuiz/Content/Data/MetroData.json'
OUT = 'E:/GuangzhouBusViewer/assets/tim-coords.json'

im = Image.open(RASTER).convert('RGB')
W, H = im.size; px = im.load()
assert W == 2849 and H == 2055

NS = '{http://www.w3.org/2000/svg}'
tree = ET.parse(SVG); svg_root = tree.getroot()
svg_text = open(SVG, encoding='utf-8').read()
cls_colors = dict(re.findall(r'\.(\w+)\{[^}]*?stroke:(#[0-9A-Fa-f]{6})', svg_text))
def decode(i):
    if not i: return ''
    for x in range(10): i = i.replace(f'_x3{x}_', str(x))
    return i
def find_g(n):
    for g in svg_root.iter(NS + 'g'):
        if decode(g.get('id', '')) == n: return g
GROUP = {'1': '1', '2': '2', '3': '3', '4': '4', '5': '5', '6': '6', '7': '7', '8': '8',
         '9_3_': '9', '10_1_': '10', '11': '11', '12': '12', '13': '13', '14': '14',
         '18': '18', '21': '21', '22': '22', 'GF': 'GF', 'APM_3_': 'APM'}
REF2G = {v: k for k, v in GROUP.items()}

def line_color(ref):
    for el in find_g(REF2G[ref]).iter():
        cl = el.get('class')
        if cl and cl in cls_colors:
            h = cls_colors[cl].lstrip('#')
            return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    return None

def vector_ends(ref):
    """该线矢量几何的度-1端点（最多4个，含支线端）"""
    occ = defaultdict(int)
    for el in find_g(REF2G[ref]).iter():
        t = el.tag.replace(NS, '')
        if t == 'line':
            a = (float(el.get('x1')), float(el.get('y1')))
            b = (float(el.get('x2')), float(el.get('y2')))
            if math.hypot(b[0]-a[0], b[1]-a[1]) > 0.1:
                occ[a] += 1; occ[b] += 1
    return [p for p, n in occ.items() if n == 1]

def color_ok(p, rgb, tol=110):
    return abs(p[0]-rgb[0]) + abs(p[1]-rgb[1]) + abs(p[2]-rgb[2]) < tol

def trace(a, b, rgb):
    ax, ay = a; bx, by = b
    L = math.hypot(bx-ax, by-ay)
    if L < 2: return [a, b]
    cur = [ax, ay]; dirx, diry = (bx-ax)/L, (by-ay)/L
    path = [(ax, ay)]
    R = 12; lost = 0
    for _ in range(int(L*1.6)+40):
        if math.hypot(cur[0]-bx, cur[1]-by) < 6: break
        best = None; bs = -2
        for dx in range(-R, R+1, 2):
            for dy in range(-R, R+1, 2):
                xx, yy = int(cur[0]+dx), int(cur[1]+dy)
                if not (0 <= xx < W and 0 <= yy < H): continue
                if color_ok(px[xx, yy], rgb):
                    d = math.hypot(dx, dy)
                    if d < 1.5: continue
                    ux, uy = dx/d, dy/d
                    tx, ty = bx-cur[0], by-cur[1]
                    tl = math.hypot(tx, ty) or 1
                    s = (ux*tx + uy*ty)/tl*0.65 + (ux*dirx + uy*diry)*0.35
                    if s > bs: bs = s; best = (xx, yy)
        if best:
            nx_, ny_ = best[0]-cur[0], best[1]-cur[1]
            nl = math.hypot(nx_, ny_) or 1
            dirx, diry = nx_/nl, ny_/nl
            cur = list(best); path.append(tuple(cur)); lost = 0
        else:
            lost += 1
            if lost > 30: break
            cur = [cur[0]+dirx*2.5, cur[1]+diry*2.5]
            path.append((round(cur[0],1), round(cur[1],1)))
    path.append((bx, by))
    return path

def path_arc(path):
    arc = [0.0]
    for i in range(1, len(path)):
        arc.append(arc[-1] + math.hypot(path[i][0]-path[i-1][0], path[i][1]-path[i-1][1]))
    return arc

def proj_s(path, arc, p):
    best, bs = 1e18, 0.0
    for i in range(1, len(path)):
        x1, y1 = path[i-1]; x2, y2 = path[i]
        dx, dy = x2-x1, y2-y1
        L2 = dx*dx + dy*dy
        t = 0 if L2 == 0 else max(0.0, min(1.0, ((p[0]-x1)*dx + (p[1]-y1)*dy) / L2))
        qx, qy = x1+t*dx, y1+t*dy
        d = math.hypot(p[0]-qx, p[1]-qy)
        if d < best:
            best = d; bs = arc[i-1] + t*math.hypot(dx, dy)
    return best, bs

def point_at(path, arc, s):
    if s <= 0: return path[0]
    if s >= arc[-1]: return path[-1]
    i = bisect.bisect_left(arc, s)
    t = (s - arc[i-1]) / max(1e-9, arc[i] - arc[i-1])
    return (path[i-1][0] + t*(path[i][0]-path[i-1][0]), path[i-1][1] + t*(path[i][1]-path[i-1][1]))

c = json.load(open(OUT, encoding='utf-8'))
data = json.load(open(SRC, encoding='utf-8-sig'))
st = {s['id']: s for s in data['stations']}

def seqs_of(l): return [l['stations']] + l.get('branches', [])

# 坏站 = err>30 或 同线异站 <6px
broken = set()
for l in data['lines']:
    for seq in seqs_of(l):
        uniq = list(dict.fromkeys(seq))
        for i in range(len(uniq)):
            if uniq[i] in c and c[uniq[i]][2] > 30: broken.add(uniq[i])
            for j in range(i+1, len(uniq)):
                a, b = uniq[i], uniq[j]
                if a in c and b in c and math.hypot(c[a][0]-c[b][0], c[a][1]-c[b][1]) < 6:
                    broken.add(a); broken.add(b)
print('坏站:', len(broken))

def sane_corridor(eA, eB, rgb, ref=None):
    """跟踪走廊并做合理性校验：总长在直距 0.8~2.2 倍之间，否则退化为端点弦线；
    端点退化(<20px)时用本线矢量几何包围盒对角线当走廊"""
    chord = math.hypot(eB[0]-eA[0], eB[1]-eA[1])
    if chord < 20 and ref:
        xs, ys = [], []
        for el in find_g(REF2G[ref]).iter():
            t = el.tag.replace(NS, '')
            if t == 'line':
                xs += [float(el.get('x1')), float(el.get('x2'))]
                ys += [float(el.get('y1')), float(el.get('y2'))]
        if xs:
            eA = (min(xs), min(ys)); eB = (max(xs), max(ys))
            chord = math.hypot(eB[0]-eA[0], eB[1]-eA[1])
    path = trace(eA, eB, rgb)
    arc = path_arc(path)
    # 合理性：终点命中 + 空间跨度 + 弧长比例，任一不满足退化为弦线
    end_ok = math.hypot(path[-1][0]-eB[0], path[-1][1]-eB[1]) < 40
    p_xs = [q[0] for q in path]; p_ys = [q[1] for q in path]
    span = math.hypot(max(p_xs)-min(p_xs), max(p_ys)-min(p_ys))
    if (not end_ok) or span < 0.6*chord or not (0.8*chord <= arc[-1] <= 2.2*chord) or arc[-1] < 20:
        n = max(2, int(chord / 8))
        path = [(eA[0] + (eB[0]-eA[0])*k/n, eA[1] + (eB[1]-eA[1])*k/n) for k in range(n+1)]
        arc = path_arc(path)
    return path, arc

def geo_frac_positions(seq):
    total = [0.0]
    for i in range(1, len(seq)):
        p0 = st[seq[i-1]]; p1 = st[seq[i]]
        total.append(total[-1] + math.hypot((p1['lon']-p0['lon'])*102000, -(p1['lat']-p0['lat'])*110540))
    return [t / (total[-1] or 1) for t in total]

def line_ok(seq):
    uniq = list(dict.fromkeys(seq))
    for i in range(len(uniq)):
        for j in range(i+1, len(uniq)):
            a, b = uniq[i], uniq[j]
            if a in c and b in c and math.hypot(c[a][0]-c[b][0], c[a][1]-c[b][1]) < 6:
                return False
    return True

# ---------- 整线走廊重排（只动坏站；每线终检，失败整线弦线重铺） ----------
fixed = 0
for l in data['lines']:
    ref = l['ref']
    if ref not in REF2G: continue
    rgb = line_color(ref)
    if not rgb: continue
    ends = vector_ends(ref)
    if len(ends) < 2: continue
    eA, eB = max(((ends[i], ends[j]) for i in range(len(ends)) for j in range(i+1, len(ends))),
                 key=lambda pr: math.hypot(pr[0][0]-pr[1][0], pr[0][1]-pr[1][1]))
    seq = l['stations']
    if ref in ('APM','9'):
        print(f'[dbg] {ref}: broken数={sum(1 for s in seq if s in broken)}/{len(seq)} ends={len(ends)} rgb={rgb}')
    if not any(s in broken for s in seq): continue
    path, arc = sane_corridor(eA, eB, rgb, ref)
    gv = (st[seq[-1]]['lon']-st[seq[0]]['lon'], -(st[seq[-1]]['lat']-st[seq[0]]['lat']))
    vv = (eB[0]-eA[0], eB[1]-eA[1])
    if gv[0]*vv[0] + gv[1]*vv[1] < 0:
        path = path[::-1]; arc = path_arc(path)
    good = []
    for i, sid in enumerate(seq):
        if sid in c and sid not in broken:
            d, s = proj_s(path, arc, (c[sid][0], c[sid][1]))
            if d < 25: good.append((i, s))
    good.sort()
    if good:
        mono = [good[0]]
        for i, s in good[1:]:
            mono.append((i, max(s, mono[-1][1] + 1)))
        good = mono
    if len(good) >= 2:
        for k in range(len(good)-1):
            i0, s0 = good[k]; i1, s1 = good[k+1]
            for i in range(i0+1, i1):
                sid = seq[i]
                if sid not in broken: continue
                s = s0 + (s1-s0)*(i-i0)/(i1-i0)
                q = point_at(path, arc, s)
                c[sid] = [round(q[0],1), round(q[1],1), 0.0]; fixed += 1
        i0, s0 = good[0]
        for i in range(i0-1, -1, -1):
            sid = seq[i]
            if sid not in broken: break
            s0 -= 40
            q = point_at(path, arc, s0)
            c[sid] = [round(q[0],1), round(q[1],1), 0.0]; fixed += 1
        i1, s1 = good[-1]
        for i in range(i1+1, len(seq)):
            sid = seq[i]
            if sid not in broken: continue
            s1 += 40
            q = point_at(path, arc, s1)
            c[sid] = [round(q[0],1), round(q[1],1), 0.0]; fixed += 1
    # 分支
    for br in l.get('branches', []):
        if not br or not any(s in broken for s in br): continue
        jid = br[0]
        if jid not in c: continue
        jp = (c[jid][0], c[jid][1])
        e = max(ends, key=lambda p2: math.hypot(p2[0]-jp[0], p2[1]-jp[1]))
        bpath, barc = sane_corridor(jp, e, rgb, ref)
        bgood = []
        for i, sid in enumerate(br):
            if sid in c and sid not in broken:
                d, s = proj_s(bpath, barc, (c[sid][0], c[sid][1]))
                if d < 25: bgood.append((i, s))
        bgood.sort()
        if bgood:
            mono = [bgood[0]]
            for i, s in bgood[1:]: mono.append((i, max(s, mono[-1][1]+1)))
            bgood = mono
        else:
            bgood = [(0, 0.0)]
        for k in range(len(bgood)-1):
            i0b, s0b = bgood[k]; i1b, s1b = bgood[k+1]
            for i in range(i0b+1, i1b):
                sid = br[i]
                if sid not in broken: continue
                s = s0b + (s1b-s0b)*(i-i0b)/(i1b-i0b)
                q = point_at(bpath, barc, s)
                c[sid] = [round(q[0],1), round(q[1],1), 0.0]; fixed += 1
        i1b, s1b = bgood[-1]
        for i in range(i1b+1, len(br)):
            sid = br[i]
            if sid not in broken: continue
            s1b += 40
            q = point_at(bpath, barc, s1b)
            c[sid] = [round(q[0],1), round(q[1],1), 0.0]; fixed += 1
    # 每线终检：仍冲突 → 整线（主线）按地理比例在走廊重铺
    if ref in ('APM','9'):
        print(f'[dbg] {ref}: line_ok={line_ok(seq)} arc={arc[-1]:.0f} span={math.hypot(max(q[0] for q in path)-min(q[0] for q in path), max(q[1] for q in path)-min(q[1] for q in path)):.0f}')
    if not line_ok(seq):
        fr = geo_frac_positions(seq)
        for i, sid in enumerate(seq):
            q = point_at(path, arc, arc[-1] * fr[i])
            c[sid] = [round(q[0],1), round(q[1],1), 0.0]
print('走廊重排修复:', fixed)

# ---------- 终校验 ----------
bad = []
for l in data['lines']:
    for seq in seqs_of(l):
        uniq = list(dict.fromkeys(seq))
        for i in range(len(uniq)):
            for j in range(i+1, len(uniq)):
                a, b = uniq[i], uniq[j]
                if a in c and b in c:
                    d = math.hypot(c[a][0]-c[b][0], c[a][1]-c[b][1])
                    if d < 6: bad.append((l['ref'], a, b, round(d,1)))
print('残余冲突:', len(bad), bad[:10])
if bad: raise SystemExit('仍有坍塌')
json.dump(c, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print('OK')
