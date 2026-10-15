#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 图上识别（栅格 CV）：按线路颜色贪婪跟踪走线，白色缺口 = 站点，按站序赋位
# 栅格为 1:1 viewBox 坐标（2849×2055 canvas 渲染）
import json, math, re
import xml.etree.ElementTree as ET
from PIL import Image

im = Image.open('E:/GuangzhouBusViewer/assets/_tim-raster.png').convert('RGB')
W, H = im.size
px = im.load()
assert W == 2849 and H == 2055

c = json.load(open('E:/GuangzhouBusViewer/assets/tim-coords.json'))

# ---- 从 SVG 取每条线的实际描边色 ----
SVG = 'E:/GuangzhouBusViewer/assets/tim-gzfmetro.svg'
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
GROUP = {'1': '1', '3': '3', '11': '11', '14': '14'}
def line_color(gname):
    g = find_g(gname)
    for el in g.iter():
        cls = el.get('class')
        if cls and cls in cls_colors:
            h = cls_colors[cls].lstrip('#')
            return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    return None

def hex2rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def color_ok(p, rgb, tol=80):
    return abs(p[0]-rgb[0]) + abs(p[1]-rgb[1]) + abs(p[2]-rgb[2]) < tol

def is_white(p):
    return p[0] > 195 and p[1] > 195 and p[2] > 195

def trace(a, b, rgb, max_steps=None):
    """从 a 跟线走到 b：返回 (路径点列表, 缺口中心列表)"""
    ax, ay = a; bx, by = b
    L = math.hypot(bx-ax, by-ay)
    max_steps = max_steps or int(L * 1.6)
    cur = [ax, ay]
    dirx, diry = (bx-ax)/L, (by-ay)/L   # 动量
    path = []
    gap_run = []
    gaps = []
    R = 12
    for _ in range(max_steps):
        if math.hypot(cur[0]-bx, cur[1]-by) < 6: break
        # 找附近线色像素
        best = None; best_score = -2
        found = False
        for dx in range(-R, R+1, 2):
            for dy in range(-R, R+1, 2):
                xx, yy = int(cur[0]+dx), int(cur[1]+dy)
                if not (0 <= xx < W and 0 <= yy < H): continue
                if color_ok(px[xx, yy], rgb):
                    found = True
                    d = math.hypot(dx, dy)
                    if d < 1.5: continue
                    ux, uy = dx/d, dy/d
                    tx, ty = bx-cur[0], by-cur[1]
                    tl = math.hypot(tx, ty) or 1
                    score = (ux*tx + uy*ty)/tl * 0.65 + (ux*dirx + uy*diry) * 0.35
                    if score > best_score:
                        best_score = score; best = (xx, yy)
        if found and best:
            if len(gap_run) >= 3:
                gaps.append((sum(p[0] for p in gap_run)/len(gap_run),
                             sum(p[1] for p in gap_run)/len(gap_run)))
            gap_run = []
            nx_, ny_ = best[0]-cur[0], best[1]-cur[1]
            nl = math.hypot(nx_, ny_) or 1
            dirx, diry = nx_/nl, ny_/nl
            cur = [best[0], best[1]]
            path.append(tuple(cur))
        else:
            # 缺口：沿动量前进，记录白色样本
            cx_, cy_ = int(cur[0]), int(cur[1])
            if 0 <= cx_ < W and 0 <= cy_ < H and is_white(px[cx_, cy_]):
                gap_run.append((cur[0], cur[1]))
            else:
                if len(gap_run) >= 3:
                    gaps.append((sum(p[0] for p in gap_run)/len(gap_run),
                                 sum(p[1] for p in gap_run)/len(gap_run)))
                gap_run = []
            cur = [cur[0] + dirx*2, cur[1] + diry*2]
    if len(gap_run) >= 3:
        gaps.append((sum(p[0] for p in gap_run)/len(gap_run),
                     sum(p[1] for p in gap_run)/len(gap_run)))
    return path, gaps

def fix_segment(name, a_st, b_st, targets, gname):
    rgb = line_color(gname)
    if not rgb:
        print(f'{name}: 找不到线色, 跳过'); return
    a = tuple(c[a_st][:2]); b = tuple(c[b_st][:2])
    path, gaps = trace(a, b, rgb)
    # 过滤离路径过远的缺口
    print(f'{name}({gname} 色{rgb}): 路径{len(path)}点, 缺口{len(gaps)}个, 目标{len(targets)}: {[g and (round(g[0]),round(g[1])) for g in gaps]}')
    for sid, g in zip(targets, gaps):
        if g is None: continue
        c[sid] = [round(g[0], 1), round(g[1], 1), 0.0]
        print(f'   {sid} -> ({g[0]:.0f},{g[1]:.0f})')

d = json.load(open('E:/GuangzhouMetroQuiz/Content/Data/MetroData.json', encoding='utf-8-sig'))

br = ['新和', '红卫', '新南', '枫下', '知识城', '何棠下', '旺村', '汤村', '镇龙北', '镇龙']
fix_segment('14支线西段', '新和', '旺村', br[1:6], '14')
fix_segment('14支线东段', '旺村', '镇龙', br[7:9], '14')
fix_segment('3支线', '华师', '天河客运站', ['五山'], '3')
l11 = next(l for l in d['lines'] if l['ref'] == '11')
seq = l11['stations']
i = seq.index('大金钟路')
prevS, nextS = seq[i-1], seq[(i+1) % len(seq)]
if c[prevS][2] <= 15 and c[nextS][2] <= 15:
    fix_segment('11环大金钟路', prevS, nextS, ['大金钟路'], '11')

json.dump(c, open('E:/GuangzhouBusViewer/assets/tim-coords.json', 'w', encoding='utf-8'), ensure_ascii=False)
bad = [(k, round(v[2])) for k, v in c.items() if v[2] > 30]
print('剩余>30px:', bad)
