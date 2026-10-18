# -*- coding: utf-8 -*-
"""矢量PDF字形与胶囊提取
1. 小路径 = 字形(量化指纹聚类)
2. 同行邻近字形+分隔间距 -> 胶囊(线号|序号)
3. 渲染编号种子表(60框/张) 供视觉标定
输出: data/pdf-glyphs.json, assets/_pg-seed-*.png
"""
import json
import pymupdf
import numpy as np
from collections import defaultdict

doc = pymupdf.open('assets/gz-map-2025.pdf')
page = doc[0]
DR = page.get_drawings()

glyphs = []
for d in DR:
    r = d['rect']
    w, h = r.width, r.height
    if 2 < h < 14 and 0.5 < w < 12:
        glyphs.append({'rect': r, 'items': d['items'], 'd': d})
print(f'小路径: {len(glyphs)}')

def q(v):
    return round(v * 2) / 2.0

def fp(d):
    r = d['rect']
    parts = []
    for it in d['items']:
        seg = [it[0]]
        for o in it[1:]:
            if isinstance(o, pymupdf.Point):
                seg += [q(o.x-r.x0), q(o.y-r.y0)]
            elif isinstance(o, pymupdf.Rect):
                seg += [q(o.x0-r.x0), q(o.y0-r.y0), q(o.x1-r.x0), q(o.y1-r.y0)]
            elif isinstance(o, (int, float)):
                seg += [round(o, 1)]
        parts.append(','.join(map(str, seg)))
    return '|'.join(parts)

cls_map = {}   # fp -> cid
classes = []   # cid -> {'fp', 'n'}
for g in glyphs:
    f = fp(g)
    if f not in cls_map:
        cls_map[f] = len(classes)
        classes.append({'fp': f, 'n': 0})
    cid = cls_map[f]
    classes[cid]['n'] += 1
    g['cid'] = cid
print(f'量化指纹类: {len(classes)} (字形 {len(glyphs)})')
top = sorted(classes, key=lambda c: -c['n'])[:15]
print('最大类:', [(c['n'], ) for c in top])

# ---- 行聚簇成胶囊: 同基线(yc差<3), 间隙<5pt, 3-5字 ----
gl = sorted(glyphs, key=lambda g: (g['rect'].y0, g['rect'].x0))
capsules = []
used = [False]*len(gl)
for i, g in enumerate(gl):
    if used[i]:
        continue
    grp = [g]
    used[i] = True
    cur = g
    for j in range(i+1, len(gl)):
        h2 = gl[j]
        if used[j]:
            continue
        if abs(h2['rect'].y0 - g['rect'].y0) > 3.5:
            if h2['rect'].y0 > g['rect'].y0 + 3.5:
                break
            continue
        gap = h2['rect'].x0 - cur['rect'].x1
        if 0 <= gap <= 5.5:
            grp.append(h2)
            used[j] = True
            cur = h2
        elif h2['rect'].x0 > cur['rect'].x1 + 5.5:
            break
    if 3 <= len(grp) <= 5:
        x0 = min(gg['rect'].x0 for gg in grp); x1 = max(gg['rect'].x1 for gg in grp)
        y0 = min(gg['rect'].y0 for gg in grp); y1 = max(gg['rect'].y1 for gg in grp)
        capsules.append({'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1,
                         'cids': [gg['cid'] for gg in sorted(grp, key=lambda z: z['rect'].x0)]})
print(f'胶囊: {len(capsules)}')

json.dump({'nclass': len(classes),
           'classes': [{'n': c['n']} for c in classes],
           'glyphs': [{'cid': g['cid'], 'x0': g['rect'].x0, 'y0': g['rect'].y0,
                       'x1': g['rect'].x1, 'y1': g['rect'].y1} for g in glyphs],
           'capsules': capsules}, open('data/pdf-glyphs.json', 'w'), indent=1)

# ---- 种子表: 每张60框, 带帧号 ----
from PIL import Image, ImageDraw
SC = 6
CW, CH = 300, 150
for s in range(0, min(len(capsules), 240), 60):
    batch = capsules[s:s+60]
    sheet = Image.new('RGB', (6*CW, 10*CH + 24), '#202020')
    dr = ImageDraw.Draw(sheet)
    dr.text((8, 4), 'SHEET %d (#%d-#%d)' % (s//60+1, s, s+len(batch)-1), fill='#ffff00')
    for i, cp in enumerate(batch):
        r, c = divmod(i, 6)
        gx, gy = c*CW, r*CH + 24
        clip = pymupdf.Rect(cp['x0']-3, cp['y0']-3, cp['x1']+3, cp['y1']+3)
        pm = page.get_pixmap(matrix=pymupdf.Matrix(SC, SC), clip=clip)
        img = Image.frombytes('RGB', (pm.width, pm.height), pm.samples)
        sheet.paste(img, (gx+8, gy+22))
        dr.rectangle([gx+2, gy+2, gx+CW-3, gy+CH-3], outline='#ff5050', width=2)
        dr.text((gx+6, gy+4), '#%d' % (s+i), fill='#00ff88')
    sheet.save('assets/_pg-seed-%d.png' % (s//60+1))
    print('sheet', s//60+1, len(batch))
print('done')
