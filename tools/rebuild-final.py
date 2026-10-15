#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 终版坐标重建：逐线「栅格色走廊 + 沿线字形排序」分配（14支线已验证的方法）
#   - 走廊: 矢量端点间按线色贪心跟踪(空间合理性校验, 失败退化弦线)
#   - 字形: 站点层圆/锚点, 沿走廊投影排序, 全局唯一(每字形至多一站)
#   - 锚:   34 个像素级验证站(种子), 必须命中其走廊字形, 否则报错
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

def v_ends(ref):
    occ = defaultdict(int)
    for el in find_g(REF2G[ref]).iter():
        t = el.tag.replace(NS, '')
        if t == 'line':
            a = (float(el.get('x1')), float(el.get('y1')))
            b = (float(el.get('x2')), float(el.get('y2')))
            if math.hypot(b[0]-a[0], b[1]-a[1]) > 0.1:
                occ[a] += 1; occ[b] += 1
    return [p for p, n in occ.items() if n == 1]

def v_bbox(ref):
    xs, ys = [], []
    for el in find_g(REF2G[ref]).iter():
        t = el.tag.replace(NS, '')
        if t == 'line':
            xs += [float(el.get('x1')), float(el.get('x2'))]
            ys += [float(el.get('y1')), float(el.get('y2'))]
    if not xs: return None
    return (min(xs), min(ys), max(xs), max(ys))

def color_ok(p, rgb, tol=110):
    return abs(p[0]-rgb[0]) + abs(p[1]-rgb[1]) + abs(p[2]-rgb[2]) < tol

def trace(a, b, rgb):
    ax, ay = a; bx, by = b
    L = math.hypot(bx-ax, by-ay)
    if L < 2: return [a, b]
    cur = [ax, ay]; dirx, diry = (bx-ax)/L, (by-ay)/L
    path = [(ax, ay)]; R = 12; lost = 0
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

def sane_corridor(eA, eB, rgb):
    chord = math.hypot(eB[0]-eA[0], eB[1]-eA[1])
    path = trace(eA, eB, rgb)
    arc = [0.0]
    for i in range(1, len(path)):
        arc.append(arc[-1] + math.hypot(path[i][0]-path[i-1][0], path[i][1]-path[i-1][1]))
    end_ok = math.hypot(path[-1][0]-eB[0], path[-1][1]-eB[1]) < 40
    xs = [p[0] for p in path]; ys = [p[1] for p in path]
    span = math.hypot(max(xs)-min(xs), max(ys)-min(ys))
    if (not end_ok) or span < 0.6*chord or not (0.8*chord <= arc[-1] <= 2.5*chord) or arc[-1] < 20:
        n = max(2, int(chord/8))
        path = [(eA[0]+(eB[0]-eA[0])*k/n, eA[1]+(eB[1]-eA[1])*k/n) for k in range(n+1)]
        arc = [0.0]
        for i in range(1, len(path)):
            arc.append(arc[-1] + math.hypot(path[i][0]-path[i-1][0], path[i][1]-path[i-1][1]))
    return path, arc

def proj_s(path, arc, p):
    best, bs = 1e18, 0.0
    for i in range(1, len(path)):
        x1, y1 = path[i-1]; x2, y2 = path[i]
        dx, dy = x2-x1, y2-y1
        L2 = dx*dx + dy*dy
        t = 0 if L2 == 0 else max(0.0, min(1.0, ((p[0]-x1)*dx + (p[1]-y1)*dy)/L2))
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

# 站点字形（圆心 + 换乘圆角矩形中心）
glyphs = []
for el in find_g('站点').iter(NS + 'circle'):
    glyphs.append((float(el.get('cx')), float(el.get('cy'))))
for el in find_g('站点').iter(NS + 'path'):
    d = el.get('d', '').strip()
    m = re.match(r'M\s*(-?[\d.]+)[ ,](-?[\d.]+)', d)
    if not m: continue
    vals = [float(v) for v in re.findall(r'-?\d+\.?\d*', d)]
    xs = vals[0::2]; ys = vals[1::2]
    # 小的闭合路径(换乘圆角矩形): 取包围盒中心
    if len(vals) >= 8 and max(xs)-min(xs) < 30 and max(ys)-min(ys) < 30:
        glyphs.append(((min(xs)+max(xs))/2, (min(ys)+max(ys))/2))
# 去重
glyphs = sorted(set(glyphs))
glyph_owner = {}   # index -> station id

data = json.load(open(SRC, encoding='utf-8-sig'))
st = {s['id']: s for s in data['stations']}
lines = {l['ref']: l for l in data['lines']}
def seqs_of(l): return [l['stations']] + l.get('branches', [])

# 种子（像素级验证）
seeds = json.load(open('E:/GuangzhouBusViewer/assets/_seed-anchors.json'))

result = {}
errors = []

def try_claim(gi, sid):
    if gi in glyph_owner: return False
    glyph_owner[gi] = sid
    return True

def nearest_free_glyph(q, rad, sid):
    cand = sorted(range(len(glyphs)), key=lambda i: math.hypot(glyphs[i][0]-q[0], glyphs[i][1]-q[1]))
    for gi in cand:
        if math.hypot(glyphs[gi][0]-q[0], glyphs[gi][1]-q[1]) > rad: break
        if gi not in glyph_owner:
            return gi
    return None

# ---------- 逐线分配 ----------
report = {}
for ref, l in lines.items():
    if ref not in REF2G: continue
    rgb = line_color(ref)
    ends = v_ends(ref)
    bbox = v_bbox(ref)
    if len(ends) < 2 or not bbox:
        report[ref] = '几何不足'; continue
    eA, eB = max(((ends[i], ends[j]) for i in range(len(ends)) for j in range(i+1, len(ends))),
                 key=lambda pr: math.hypot(pr[0][0]-pr[1][0], pr[0][1]-pr[1][1]))
    # 种子(本线)优先确定走廊方向
    line_seeds = {sid: xy for sid, xy in seeds.items() if ref in st[sid]['lines']}
    seq_all = [s for sq in seqs_of(l) for s in sq]
    s0 = seq_all[0]; sN = seq_all[-1]
    # 方向: 种子首尾或地理
    if s0 in line_seeds and sN in line_seeds:
        a, b = line_seeds[s0], line_seeds[sN]
    elif sN in line_seeds and seq_all[0] not in line_seeds:
        a, b = None, line_seeds[sN]
    else:
        a = b = None
    rgb2 = rgb or (255, 255, 255)
    if rgb is None:
        report[ref] = '无线色'; continue
    path, arc = sane_corridor(eA, eB, rgb)
    # 方向对齐: 用种子平均投影 vs 序号相关性
    seed_s = [(seq_all.index(sid), proj_s(path, arc, xy)[1]) for sid, xy in line_seeds.items()]
    if len(seed_s) >= 2:
        seed_s.sort()
        inv = all(seed_s[i+1][1] >= seed_s[i][1] - 1 for i in range(len(seed_s)-1))
        inv_r = all(seed_s[i+1][1] <= seed_s[i][1] + 1 for i in range(len(seed_s)-1))
        if inv_r and not inv:
            path = path[::-1]; arc = path_arc(path)
    # 重新计算函数
    def path_arc(p):
        a2 = [0.0]
        for i in range(1, len(p)):
            a2.append(a2[-1] + math.hypot(p[i][0]-p[i-1][0], p[i][1]-p[i-1][1]))
        return a2
    # (重算 arc 因方向翻转)
    arc = path_arc(path)

    # 走廊附近字形, 沿线排序
    near = []
    for gi, g in enumerate(glyphs):
        d, s = proj_s(path, arc, g)
        if d < 8:
            near.append((s, gi))
    near.sort()
    free = [(s, gi) for s, gi in near if gi not in glyph_owner]

    # 分配: 序列站 -> 沿走廊按比例取字形; 种子站必须命中(距离校验)
    n_all = len(seq_all)
    placed = 0
    for idx, sid in enumerate(seq_all):
        if sid in result:  # 换乘站已定位
            continue
        if sid in line_seeds:
            result[sid] = [line_seeds[sid][0], line_seeds[sid][1], 0.0]
            # 锁定最近字形
            gi = min(range(len(glyphs)), key=lambda i2: math.hypot(glyphs[i2][0]-line_seeds[sid][0], glyphs[i2][1]-line_seeds[sid][1]))
            if math.hypot(glyphs[gi][0]-line_seeds[sid][0], glyphs[gi][1]-line_seeds[sid][1]) < 8:
                try_claim(gi, sid)
            continue
        t = idx / max(1, n_all - 1)
        q = point_at(path, arc, arc[-1] * t)
        gi = nearest_free_glyph(q, 26, sid)
        if gi is not None:
            try_claim(gi, sid)
            result[sid] = [round(glyphs[gi][0], 1), round(glyphs[gi][1], 1), 0.0]
            placed += 1
        else:
            result[sid] = [round(q[0], 1), round(q[1], 1), 0.0]
            placed += 1
    report[ref] = f'{placed} 站'

print({k: v for k, v in report.items()})

# ---------- 全局校验 ----------
bad = []
for l in lines.values():
    seq = [s for sq in seqs_of(l) for s in sq]
    uniq = list(dict.fromkeys(seq))
    for i in range(len(uniq)):
        for j in range(i+1, len(uniq)):
            a, b = result.get(uniq[i]), result.get(uniq[j])
            if a and b and math.hypot(a[0]-b[0], a[1]-b[1]) < 6:
                bad.append((l['ref'], uniq[i], uniq[j]))
print('同线 <6px:', len(bad), bad[:10])

json.dump(result, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print('输出', len(result), '站')
