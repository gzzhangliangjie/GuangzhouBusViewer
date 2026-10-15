#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 矢量+栅格组合：
#   1) 栅格按线色跟踪走廊（解决共走廊线段散落各组的连通问题）
#   2) 矢量「站点」层的圆心投影到走廊上排序 → 按站序赋名（修复残站）
#   3) 顺带跟踪全部 19 线真实路径 → assets/tim-paths.json（供单线重画）
import json, math, re
import xml.etree.ElementTree as ET
from PIL import Image

RASTER = 'E:/GuangzhouBusViewer/assets/_tim-raster.png'
SVG = 'E:/GuangzhouBusViewer/assets/tim-gzfmetro.svg'
im = Image.open(RASTER).convert('RGB')
W, H = im.size
px = im.load()

c = json.load(open('E:/GuangzhouBusViewer/assets/tim-coords.json'))
d = json.load(open('E:/GuangzhouMetroQuiz/Content/Data/MetroData.json', encoding='utf-8-sig'))
lines = {l['ref']: l for l in d['lines']}

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

def line_color(gname):
    for el in find_g(gname).iter():
        cls = el.get('class')
        if cls and cls in cls_colors:
            h = cls_colors[cls].lstrip('#')
            return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    return None

def color_ok(p, rgb, tol=80):
    return abs(p[0]-rgb[0]) + abs(p[1]-rgb[1]) + abs(p[2]-rgb[2]) < tol

# 矢量站点字形（圆心 + 换乘圆角矩形的角点近似中心）
glyphs = []
stg = find_g('站点')
for el in stg.iter():
    t = el.tag.replace(NS, '')
    if t == 'circle':
        glyphs.append((float(el.get('cx')), float(el.get('cy'))))
    elif t == 'path':
        m = re.match(r'M\s*(-?[\d.]+)[ ,](-?[\d.]+)', el.get('d', '').strip() or '')
        if m: glyphs.append((float(m.group(1)), float(m.group(2))))

# ---- 栅格跟踪 ----
def trace(a, b, rgb, max_steps=None):
    ax, ay = a; bx, by = b
    L = math.hypot(bx-ax, by-ay)
    if L < 2: return [a, b]
    max_steps = max_steps or int(L * 1.8)
    cur = [ax, ay]
    dirx, diry = (bx-ax)/L, (by-ay)/L
    path = [tuple(cur)]
    R = 12
    lost = 0
    for _ in range(max_steps):
        if math.hypot(cur[0]-bx, cur[1]-by) < 6: break
        best = None; best_score = -2
        for dx in range(-R, R+1, 2):
            for dy in range(-R, R+1, 2):
                xx, yy = int(cur[0]+dx), int(cur[1]+dy)
                if not (0 <= xx < W and 0 <= yy < H): continue
                if color_ok(px[xx, yy], rgb):
                    dist = math.hypot(dx, dy)
                    if dist < 1.5 or dist > R: continue
                    ux, uy = dx/dist, dy/dist
                    tx, ty = bx-cur[0], by-cur[1]
                    tl = math.hypot(tx, ty) or 1
                    score = (ux*tx + uy*ty)/tl*0.65 + (ux*dirx + uy*diry)*0.35
                    if score > best_score:
                        best_score = score; best = (xx, yy)
        if best:
            nx_, ny_ = best[0]-cur[0], best[1]-cur[1]
            nl = math.hypot(nx_, ny_) or 1
            dirx, diry = nx_/nl, ny_/nl
            cur = list(best)
            path.append(tuple(cur))
            lost = 0
        else:
            lost += 1
            if lost > 14:  # 丢线：直接沿直线跳到下一个预期点
                t = min(1.0, (len(path) / max(1, L/2.0)) * 0 + lost*0.08)
                cur = [cur[0] + dirx*6, cur[1] + diry*6]
            else:
                cur = [cur[0] + dirx*2.5, cur[1] + diry*2.5]
            path.append((round(cur[0], 1), round(cur[1], 1)))
    path.append((bx, by))
    return path

def path_arclen(path):
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
        t = 0 if L2 == 0 else max(0, min(1, ((p[0]-x1)*dx + (p[1]-y1)*dy)/L2))
        qx, qy = x1+t*dx, y1+t*dy
        dd = math.hypot(p[0]-qx, p[1]-qy)
        if dd < best:
            best = dd; bs = arc[i-1] + t*math.hypot(dx, dy)
    return best, bs

# ---- Part 1: 修复残站（跟踪 + 矢量字形排序） ----
def fix_branch(name, a_st, b_st, targets, gname):
    rgb = line_color(gname)
    a = tuple(c[a_st][:2]); b = tuple(c[b_st][:2])
    path = trace(a, b, rgb)
    arc = path_arclen(path)
    # 竢近路径的字形（排除端点）
    near_glyphs = []
    for g in glyphs:
        dd, s = proj_s(path, arc, g)
        if dd < 7 and 12 < s < arc[-1] - 12:
            near_glyphs.append((s, g))
    near_glyphs.sort()
    # 去重（同站多字形）
    dedup = []
    for s, g in near_glyphs:
        if dedup and math.hypot(g[0]-dedup[-1][1][0], g[1]-dedup[-1][1][1]) < 6:
            continue
        dedup.append((s, g))
    print(f'{name}: 路径{arc[-1]:.0f}px, 字形{len(dedup)}个, 目标{len(targets)}')
    for sid, (s, g) in zip(targets, dedup):
        c[sid] = [round(g[0], 1), round(g[1], 1), 0.0]
        print(f'   {sid} -> ({g[0]:.0f},{g[1]:.0f})')

br14 = ['新和', '红卫', '新南', '枫下', '知识城', '何棠下', '旺村', '汤村', '镇龙北', '镇龙']
fix_branch('14支线西段', '新和', '旺村', br14[1:6], '14')
fix_branch('14支线东段', '旺村', '镇龙', br14[7:9], '14')
fix_branch('3支线', '华师', '天河客运站', ['五山'], '3')
seq11 = lines['11']['stations']
i11 = seq11.index('大金钟路')
fix_branch('11环大金钟路', seq11[i11-1], seq11[(i11+1) % len(seq11)], ['大金钟路'], '11')

json.dump(c, open('E:/GuangzhouBusViewer/assets/tim-coords.json', 'w', encoding='utf-8'), ensure_ascii=False)
bad = [(k, round(v[2])) for k, v in c.items() if v[2] > 30]
print('修复后 >30px:', bad)

# ---- Part 2: 全线真实路径跟踪 → tim-paths.json ----
paths = {}
for ref, l in lines.items():
    gname = GROUP[ref]
    rgb = line_color(gname)
    if not rgb: continue
    polylines = []
    seqs = [l['stations']] + l.get('branches', [])
    for seq in seqs:
        if len(seq) < 2: continue
        a = tuple(c[seq[0]][:2]); b = tuple(c[seq[-1]][:2])
        p = trace(a, b, rgb)
        # 抽稀（每 6px 一点）
        arc = path_arclen(p)
        thinned = [p[0]]
        for i in range(1, len(p)):
            if arc[i] - next((path_arclen([thinned[0], q])[1] for q in [thinned[-1]]), 0) > 6 or i == len(p)-1:
                pass
        # 简化：直接按距离抽稀
        out = [p[0]]
        last = p[0]
        for pt in p[1:]:
            if math.hypot(pt[0]-last[0], pt[1]-last[1]) >= 6:
                out.append(pt); last = pt
        if out[-1] != p[-1]: out.append(p[-1])
        polylines.append([[round(x,1), round(y,1)] for x, y in out])
    paths[ref] = polylines
json.dump(paths, open('E:/GuangzhouBusViewer/assets/tim-paths.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('tim-paths.json:', {k: [len(p) for p in v] for k, v in paths.items()})
