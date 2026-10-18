# -*- coding: utf-8 -*-
"""多路线站点(换乘站)编号框检测器 v4
判据: 编号胶囊 = 一行紧凑窄字形(数字/字母) + 上下横向描边(黑或灰) + 线号|序号之间的分隔竖线。
  同行多个胶囊(2x2换乘)会连成长run, 用语法 (1-2线号字形 + 2序号字形) + 分隔线证据 递归拆分。
输出: data/multibox-stations.json
  [{x, y, boxes: [{x0,y0,x1,y1,cx,cy,nglyph}], nbox}]
"""
import json
import numpy as np
from PIL import Image
from scipy import ndimage

IMG = 'assets/official-ref.jpg'

img = Image.open(IMG).convert('RGB')
arr = np.array(img).astype(int)
H, W, _ = arr.shape

dark = arr.max(axis=2) < 170          # 字形(黑或深灰, 南部区域墨色偏浅)
edge = arr.max(axis=2) < 210          # 胶囊描边(黑/灰/带抗锯齿)
dark[:380, :] = False
edge[:380, :] = False
dark[5460:, :] = False                # 底部图例区
edge[5460:, :] = False
white = arr.min(axis=2) > 200

# ---- 字形组件: 三路来源取并集 ----
# A: <150 组件(标准黑字); B: <170 且不含A像素(南部浅墨); C: 局部对比度墨水(色带混杂区)
darkA = arr.max(axis=2) < 150
darkA[:380, :] = False; darkA[5460:, :] = False
darkB = arr.max(axis=2) < 170
darkB[:380, :] = False; darkB[5460:, :] = False
mx = arr.max(axis=2)
med = ndimage.uniform_filter(mx.astype(np.float32), size=41)
inkC = ((med - mx) > 42) & (med > 185)
inkC[:380, :] = False; inkC[5460:, :] = False
glyphs = []
for mi, mask_list in enumerate((darkA, darkB, inkC)):
    lblg, ng = ndimage.label(mask_list, structure=np.ones((3, 3)))
    for i, sl in enumerate(ndimage.find_objects(lblg)):
        if sl is None:
            continue
        gy0, gy1 = sl[0].start, sl[0].stop-1
        gx0, gx1 = sl[1].start, sl[1].stop-1
        w, h = gx1-gx0+1, gy1-gy0+1
        comp = (lblg[sl] == i+1)
        if 8 <= h <= 22 and 2 <= w <= 12 and comp.sum() >= 6:
            if mi == 1 and darkA[sl][comp].any():
                continue
            if mi == 2 and (darkB[sl][comp].any()):
                continue
            glyphs.append({'x0': gx0, 'y0': gy0, 'x1': gx1, 'y1': gy1, 'yc': (gy0+gy1)//2})
glyphs.sort(key=lambda g: (g['yc'], g['x0']))
dedup = []
for g in glyphs:
    if not any(abs(g['x0']-d['x0']) < 8 and abs(g['yc']-d['yc']) < 8 for d in dedup):
        dedup.append(g)
glyphs = dedup

# ---- 反白字形: 非背景的白色组件(深底白字胶囊, 如广州南站右列) ----
whitem = arr.min(axis=2) > 210
whitem[:380, :] = False; whitem[5460:, :] = False
lblw, nw = ndimage.label(whitem, structure=np.ones((3, 3)))
if nw:
    sizes = ndimage.sum(whitem, lblw, range(1, nw+1))
    bg = int(np.argmax(sizes)) + 1        # 最大白色组件=地图背景
else:
    bg = -1
inv_glyphs = []
for i, sl in enumerate(ndimage.find_objects(lblw)):
    if sl is None or i+1 == bg:
        continue
    gy0, gy1 = sl[0].start, sl[0].stop-1
    gx0, gx1 = sl[1].start, sl[1].stop-1
    w, h = gx1-gx0+1, gy1-gy0+1
    if 8 <= h <= 22 and 2 <= w <= 12 and (lblw[sl] == i+1).sum() >= 6:
        inv_glyphs.append({'x0': gx0, 'y0': gy0, 'x1': gx1, 'y1': gy1, 'yc': (gy0+gy1)//2, 'inv': True})
inv_glyphs.sort(key=lambda g: (g['yc'], g['x0']))
dedup2 = []
for g in inv_glyphs:
    if not any(abs(g['x0']-d['x0']) < 8 and abs(g['yc']-d['yc']) < 8 for d in dedup2):
        dedup2.append(g)
print(f'反白字形: {len(dedup2)}')
print(f'字形组件: {len(glyphs)}')

# ---- 行带分组 ----
glyphs.sort(key=lambda g: (g['yc'], g['x0']))
rows = []
for g in glyphs:
    placed = False
    for r in rows:
        if abs(r['yc'] - g['yc']) <= 6 and not (g['x0'] > r['x1'] + 27):
            r['g'].append(g)
            r['x1'] = max(r['x1'], g['x1'])
            r['x0'] = min(r['x0'], g['x0'])
            r['yc'] = int(np.mean([x['yc'] for x in r['g']]))
            placed = True
            break
    if not placed:
        rows.append({'g': [g], 'x0': g['x0'], 'x1': g['x1'], 'yc': g['yc']})

def split_runs(g):
    g = sorted(g, key=lambda x: x['x0'])
    runs = [[g[0]]]
    for a, b in zip(g, g[1:]):
        if b['x0'] - a['x1'] - 1 <= 26:
            runs[-1].append(b)
        else:
            runs.append([b])
    return runs

def hbar_row(x0, x1, lo, hi):
    best_y, best = -1, 0.0
    for yy in range(lo, hi+1):
        if yy < 0 or yy >= H:
            continue
        cov = edge[yy, x0:x1+1].mean()
        if cov > best:
            best, best_y = cov, yy
    return best_y, best

def vdiv(x_lo, x_hi, y0, y1):
    """[x_lo,x_hi]列区间内竖向描边覆盖(分隔线证据)"""
    best = 0.0
    for xx in range(x_lo, x_hi+1):
        cov = edge[y0:y1+1, xx].mean()
        best = max(best, cov)
    return best

boxes = []
from collections import Counter
stats = Counter()
for r in rows:
    for run in split_runs(r['g']):
        n = len(run)
        if not (3 <= n <= 8):
            continue
        x0 = min(g['x0'] for g in run); x1 = max(g['x1'] for g in run)
        y0 = min(g['y0'] for g in run); y1 = max(g['y1'] for g in run)
        w, h = x1-x0+1, y1-y0+1
        if not (24 <= w <= 175 and 10 <= h <= 26):
            continue
        if max(g['yc'] for g in run) - min(g['yc'] for g in run) > 8:
            continue
        band = white[max(y0-2, 0):y1+3, x0:x1+1]
        if band.size == 0 or band.mean() < 0.15:
            continue
        # 整条run的上下边(粗检)
        _, tb = hbar_row(x0+2, x1-2, max(y0-11, 0), y0-3)
        _, bb = hbar_row(x0+2, x1-2, y1+3, min(y1+11, H-1))
        strong = (tb >= 0.35 and bb >= 0.35)
        if not strong:
            stats['run_weakbars'] += 1
        # ---- 语法拆分: 每框 = 1-2线号 + 2序号, 拆分点须有分隔线, 框自身须有上下边 ----
        def parse_box(gs, i, bar_thr):
            for k in (1, 2):
                j = i + k + 2
                if j > len(gs):
                    continue
                bg = gs[i:j]
                bx0 = min(g['x0'] for g in bg); bx1 = max(g['x1'] for g in bg)
                by0 = min(g['y0'] for g in bg); by1 = max(g['y1'] for g in bg)
                gap_lo = gs[i+k-1]['x1'] - 1
                gap_hi = gs[i+k]['x0'] + 1
                if gap_hi < gap_lo:
                    continue
                dv = max(vdiv(gap_lo, gap_hi, by0, by1),
                         vdiv(gap_lo, gap_hi, by0+3, by1-3))
                if dv < 0.45:
                    continue
                trow, tcov = hbar_row(bx0+2, bx1-2, max(by0-11, 0), by0-3)
                brow, bcov = hbar_row(bx0+2, bx1-2, by1+3, min(by1+11, H-1))
                if tcov < bar_thr or bcov < bar_thr:
                    continue
                return j, {'x0': bx0, 'y0': by0, 'x1': bx1, 'y1': by1,
                           'trow': trow, 'brow': brow, 'dv': round(float(dv), 2),
                           'nglyph': len(bg),
                           'gr': [[g['x0'], g['y0'], g['x1'], g['y1']] for g in bg]}
            return None
        gs = sorted(run, key=lambda g: g['x0'])
        bar_thr = 0.55 if strong else 0.30
        parsed, i = [], 0
        while i < len(gs):
            res = parse_box(gs, i, bar_thr)
            if res is None:
                parsed = None
                break
            i, b = res
            parsed.append(b)
        if not parsed:
            if strong and n <= 4:
                trow, tcov = hbar_row(x0+2, x1-2, max(y0-11, 0), y0-3)
                brow, bcov = hbar_row(x0+2, x1-2, y1+3, min(y1+11, H-1))
                if tcov >= 0.55 and bcov >= 0.55:
                    stats['fallback'] += 1
                    parsed = [{'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1,
                               'trow': trow, 'brow': brow, 'dv': 0, 'nglyph': n,
                               'gr': [[g['x0'], g['y0'], g['x1'], g['y1']] for g in run]}]
            if not parsed:
                stats['parse_fail'] += 1
                continue
        for b in parsed:
            bx0, bx1 = int(b['x0']-6), int(b['x1']+6)
            by0, by1 = int(b['trow']-1), int(b['brow']+1)
            boxes.append({'x0': bx0, 'y0': by0, 'x1': bx1, 'y1': by1,
                          'cx': (bx0+bx1)//2, 'cy': (by0+by1)//2,
                          'nglyph': b['nglyph'], 'dv': b['dv'],
                          'gr': b.get('gr', [])})

# ---- 反白通路: 深底白字胶囊 ----
inv_rows = []
for g in dedup2:
    placed = False
    for r in inv_rows:
        if abs(r['yc'] - g['yc']) <= 6 and not (g['x0'] > r['x1'] + 27):
            r['g'].append(g)
            r['x1'] = max(r['x1'], g['x1']); r['x0'] = min(r['x0'], g['x0'])
            r['yc'] = int(np.mean([x['yc'] for x in r['g']]))
            placed = True
            break
    if not placed:
        inv_rows.append({'g': [g], 'x0': g['x0'], 'x1': g['x1'], 'yc': g['yc']})

def vdiv_inv(x_lo, x_hi, y0, y1):
    best = 0.0
    for xx in range(x_lo, x_hi+1):
        cov = whitem[y0:y1+1, xx].mean()
        best = max(best, cov)
    return best

for r in inv_rows:
    for run in split_runs(r['g']):
        n = len(run)
        if not (3 <= n <= 8):
            continue
        x0 = min(g['x0'] for g in run); x1 = max(g['x1'] for g in run)
        y0 = min(g['y0'] for g in run); y1 = max(g['y1'] for g in run)
        if not (24 <= x1-x0+1 <= 175 and 10 <= y1-y0+1 <= 26):
            continue
        if max(g['yc'] for g in run) - min(g['yc'] for g in run) > 8:
            continue
        gs = sorted(run, key=lambda g: g['x0'])
        def parse_inv(gs, i):
            for k in (1, 2):
                j = i + k + 2
                if j > len(gs):
                    continue
                bg_ = gs[i:j]
                bx0 = min(g['x0'] for g in bg_); bx1 = max(g['x1'] for g in bg_)
                by0 = min(g['y0'] for g in bg_); by1 = max(g['y1'] for g in bg_)
                gap_lo = gs[i+k-1]['x1'] - 1
                gap_hi = gs[i+k]['x0'] + 1
                if gap_hi < gap_lo:
                    continue
                dv = vdiv_inv(gap_lo, gap_hi, by0, by1)
                if dv < 0.4:
                    continue
                # 深色上下边(色带/胶囊底)
                tcov = edge[max(by0-12, 0):by0-2, bx0:bx1+1].mean() if by0 > 2 else 0
                bcov = edge[by1+3:min(by1+13, H-1), bx0:bx1+1].mean()
                if tcov < 0.3 or bcov < 0.3:
                    continue
                return j, {'x0': bx0, 'y0': by0, 'x1': bx1, 'y1': by1, 'dv': dv,
                           'gr': [[g['x0'], g['y0'], g['x1'], g['y1']] for g in bg_]}
            return None
        pi, i = [], 0
        ok = True
        while i < len(gs):
            res = parse_inv(gs, i)
            if res is None:
                ok = False
                break
            i, b = res
            pi.append(b)
        if not ok:
            stats['inv_parse_fail'] += 1
            continue
        for b in pi:
            bx0, bx1 = int(b['x0']-6), int(b['x1']+6)
            by0, by1 = int(b['y0']-6), int(b['y1']+6)
            if not any(abs((bx0+bx1)//2-v['cx']) < 26 and abs((by0+by1)//2-v['cy']) < 22 for v in boxes):
                boxes.append({'x0': bx0, 'y0': by0, 'x1': bx1, 'y1': by1,
                              'cx': (bx0+bx1)//2, 'cy': (by0+by1)//2,
                              'nglyph': len(b['gr']), 'dv': round(float(b['dv']), 2), 'inv': True,
                              'gr': b['gr']})
                stats['inv_box'] += 1

print(f'编号框: {len(boxes)}  stats={dict(stats)}')

# ---- 聚类成站 ----
def near(a, b, gap=13):
    return not (a['x0'] > b['x1']+gap or b['x0'] > a['x1']+gap
                or a['y0'] > b['y1']+gap or b['y0'] > a['y1']+gap)

boxes.sort(key=lambda b: (b['cy'], b['cx']))
groups = []
for b in boxes:
    hit = None
    for g in groups:
        if any(near(o, b) for o in g):
            hit = g
            break
    if hit:
        hit.append(b)
    else:
        groups.append([b])
changed = True
while changed:
    changed = False
    for i in range(len(groups)):
        for j in range(i+1, len(groups)):
            if any(near(p, q) for p in groups[i] for q in groups[j]):
                groups[i] = groups[i] + groups[j]
                groups.pop(j)
                changed = True
                break
        if changed:
            break

stations = []
for g in groups:
    g2 = sorted(g, key=lambda b: (b['cy'], b['cx']))
    stations.append({'x': int(np.mean([b['cx'] for b in g2])),
                     'y': int(np.mean([b['cy'] for b in g2])),
                     'boxes': g2, 'nbox': len(g2)})
stations.sort(key=lambda s: (s['y'], s['x']))
multi = [s for s in stations if s['nbox'] > 1]
print(f'站: {len(stations)}, 多框站: {len(multi)}')
from collections import Counter
print('框数分布:', dict(Counter(s['nbox'] for s in stations)))
for s in multi:
    if s['nbox'] >= 3:
        print(f"  x3+ ({s['x']},{s['y']}) x{s['nbox']}")
json.dump(stations, open('data/multibox-stations.json', 'w'), indent=1)

from PIL import ImageDraw
scale = 3
thumb = img.resize((W//scale, H//scale))
dr = ImageDraw.Draw(thumb)
for s in stations:
    col = '#00ff00' if s['nbox'] == 1 else ('#ffff00' if s['nbox'] == 2 else
                                            ('#ff00ff' if s['nbox'] == 3 else '#ff0000'))
    for b in s['boxes']:
        dr.rectangle([b['x0']//scale, b['y0']//scale, b['x1']//scale, b['y1']//scale],
                     outline=col, width=2)
thumb.save('assets/_multibox-thumb.png')
print('标注图: assets/_multibox-thumb.png')
