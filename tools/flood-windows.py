# -*- coding: utf-8 -*-
"""锚点泛洪检测全网站窗:
- 锚点=已知站点(带内). 采局部主色 -> 局部色掩码 -> 含锚点连通域 -> 域内数字簇=窗
- 新窗入队 BFS, 经换乘站扩散到全网
输出: data/flood-windows.json [{x,y,x0,y0,x1,y1,anchorLine}]
"""
import json, math, sys
import numpy as np
from PIL import Image
from scipy import ndimage

IMG = 'assets/official-ref.jpg'
ANCHORS0 = [  # 11号线已确认站 (线号, x, y)
    (11, 1752, 2650), (11, 1863, 2652), (11, 2025, 2652), (11, 2185, 2651),
    (11, 2334, 2648), (11, 2715, 2650), (11, 2954, 2647),
]
WIN_W = (22, 75); WIN_H = (11, 36)
CROP = 450          # 每次探索半径

img = Image.open(IMG).convert('RGB')
ARR = np.array(img).astype(int)
H, W, _ = ARR.shape
MX = ARR.max(axis=2); MN = ARR.min(axis=2)

def digit_clusters(crop_dark):
    """小区域内的数字簇: 碎字形(3-20h) -> 行内聚簇 -> 簇级把关"""
    lbl, n = ndimage.label(crop_dark, structure=np.ones((3,3)))
    objs = ndimage.find_objects(lbl)
    glyphs = []
    for sl in objs:
        if sl is None: continue
        y0,y1,x0,x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
        if 3 <= y1-y0 <= 20 and 1 <= x1-x0 <= 20:
            glyphs.append((x0,y0,x1,y1))
    glyphs.sort(key=lambda g:(g[1],g[0]))
    clusters = []
    used=[False]*len(glyphs)
    for i,g in enumerate(glyphs):
        if used[i]: continue
        grp=[g]; used[i]=True
        ch=True
        while ch:
            ch=False
            gx0=min(x[0] for x in grp); gx1=max(x[2] for x in grp)
            gy0=min(x[1] for x in grp); gy1=max(x[3] for x in grp)
            for j,h2 in enumerate(glyphs):
                if used[j]: continue
                ov=min(gy1,h2[3])-max(gy0,h2[1])
                if ov < 0.5*min(gy1-gy0,h2[3]-h2[1]): continue
                if h2[0]-gx1>14 or gx0-h2[2]>14: continue
                grp.append(h2); used[j]=True; ch=True
        if len(grp)>=2:
            x0=min(x[0] for x in grp); x1=max(x[2] for x in grp)
            y0=min(x[1] for x in grp); y1=max(x[3] for x in grp)
            if 14 <= x1-x0 <= 70 and 8 <= y1-y0 <= 34:
                clusters.append((x0,y0,x1,y1,len(grp)))
    return clusters

def dominant_band_color(cx, cy):
    """锚点环带(r22-36)采样, 按饱和度取前30%再中位 -> 排除浅窗污染"""
    pts = []
    for rad in range(22, 49, 2):
        for a in range(0, 360, 20):
            x = int(cx + rad*math.cos(math.radians(a)))
            y = int(cy + rad*math.sin(math.radians(a)))
            if 0 <= x < W and 0 <= y < H: pts.append((x,y))
    px = np.array([ARR[y,x] for x,y in pts])
    mx = px.max(axis=1); mn = px.min(axis=1)
    satmask = (mx - mn > 45) & (mx > 90)
    if satmask.sum() < 20: return None
    sel = px[satmask]
    sats = sel.max(axis=1) - sel.min(axis=1)
    top = sel[np.argsort(sats)[-max(6, len(sel)*3//10):]]
    return tuple(int(v) for v in np.median(top, 0))

def explore(anchor):
    lineNo, cx, cy = anchor
    color = dominant_band_color(cx, cy)
    if color is None: return [], None
    x0,y0 = max(cx-CROP,0), max(cy-CROP,0)
    x1,y1 = min(cx+CROP+1,W), min(cy+CROP+1,H)
    sub = ARR[y0:y1, x0:x1]
    r,g,b = sub[:,:,0],sub[:,:,1],sub[:,:,2]
    mask = np.sqrt((r-color[0])**2+(g-color[1])**2+(b-color[2])**2) < 42
    lbl,n = ndimage.label(mask, structure=np.ones((3,3)))
    # 窗会把带切成多段, 判定窗必须用整体掩码的膨胀
    dil = ndimage.binary_dilation(mask, np.ones((15,15)))
    dark = (sub.max(axis=2) < 115)
    wins = []
    for (gx0,gy0,gx1,gy1,ng) in digit_clusters(dark):
        cxx, cyy = (gx0+gx1)//2, (gy0+gy1)//2
        # 窗判定: 外扩矩形周界被带包夹, 且左右或上下同时有带
        ex0,ey0,ex1,ey1 = gx0-11,gy0-9,gx1+12,gy1+10
        ex0,ey0 = max(ex0,0), max(ey0,0)
        ex1,ey1 = min(ex1,dil.shape[1]-1), min(ey1,dil.shape[0]-1)
        top = [dil[ey0,xx] for xx in range(ex0,ex1+1)]
        bot = [dil[ey1,xx] for xx in range(ex0,ex1+1)]
        lef = [dil[yy,ex0] for yy in range(ey0,ey1+1)]
        rig = [dil[yy,ex1] for yy in range(ey0,ey1+1)]
        tot = np.mean(top+bot+lef+rig) if top+bot+lef+rig else 0
        if tot < 0.25: continue
        if sum(lef)+sum(rig) < 8 and sum(top)+sum(bot) < 8: continue
        if not (WIN_W[0]-4 <= gx1-gx0+12 <= WIN_W[1] and WIN_H[0]-4 <= gy1-gy0+10 <= WIN_H[1]): continue
        wins.append({'x': x0+cxx, 'y': y0+cyy,
                     'x0': x0+gx0-8, 'y0': y0+gy0-6, 'x1': x0+gx1+9, 'y1': y0+gy1+7,
                     'nglyph': ng, 'anchorLine': lineNo, 'color': list(color)})
    return wins, color

# ---- 19线色域扫描播种 ----
import json as _j
linecolors = _j.load(open('data/_line-colors.json'))
seeds = list(ANCHORS0)
for lc in linecolors:
    hexc = lc['color'].lstrip('#')
    cr, cg, cb = int(hexc[0:2],16), int(hexc[2:4],16), int(hexc[4:6],16)
    dist = np.sqrt((ARR[:,:,0]-cr)**2 + (ARR[:,:,1]-cg)**2 + (ARR[:,:,2]-cb)**2)
    m = (dist < 58); m[:600,:] = False
    sl, sn = ndimage.label(m, structure=np.ones((3,3)))
    if not sn: continue
    sizes = ndimage.sum(m, sl, range(1, sn+1))
    for k in np.where(sizes >= 2500)[0]:
        ys, xs = np.where(sl == k+1)
        seeds.append((lc['zh'], int(xs.mean()), int(ys.mean())))
print(f'播种: {len(seeds)} 锚点(含7个已知)')

queue = list(seeds)
allwins = []
seen_anchors = []
guard = 0
while queue and guard < 1200:
    guard += 1
    a = queue.pop(0)
    if any(abs(a[1]-s[1])<28 and abs(a[2]-s[2])<22 for s in seen_anchors): continue
    seen_anchors.append(a)
    wins, color = explore(a)
    for w in wins:
        if not any(abs(w['x']-v['x'])<26 and abs(w['y']-v['y'])<20 for v in allwins):
            allwins.append(w)
            # 离锚点远的窗作为新锚点继续泛洪
            if math.hypot(w['x']-a[1], w['y']-a[2]) > 120:
                queue.append((a[0], w['x'], w['y']))

print(f'BFS {guard} 步, 锚点 {len(seen_anchors)}, 站窗 {len(allwins)}')
allwins.sort(key=lambda w:(w['y'], w['x']))
json.dump(allwins, open('data/flood-windows.json','w'), indent=1)

# 覆盖图
from PIL import ImageDraw
scale = 3
thumb = Image.open(IMG).convert('RGB').resize((W//scale, H//scale))
dr = ImageDraw.Draw(thumb)
for w in allwins:
    dr.rectangle([w['x0']//scale, w['y0']//scale, w['x1']//scale, w['y1']//scale],
                 outline='#ff0000', width=2)
thumb.save('assets/_flood-thumb.png')
print('覆盖图: assets/_flood-thumb.png')
