# -*- coding: utf-8 -*-
"""每线站表数据: 色走廊 -> 站圆沿走廊弧长排序 = 序号; 与已知线网(站数+走向)定线名
输出 data/gz-line-stations.json: {lineRef: [{seq,name,x,y}], meta}
坐标: Tim SVG viewBox 系
"""
import json
import re
import math
import xml.etree.ElementTree as ET
import numpy as np
from collections import defaultdict

NS = 'http://www.w3.org/2000/svg'
SVG = 'assets/gz-tim-2026.svg'
PNG = r'C:/Users/zlj10/WorkBuddy/2026-10-18-14-11-14/metro/gz_metro_2026_5700px.png'
VBW, VBH = 2848.5, 2054.25
known = json.load(open('data/_metro-known.json'))

tree = ET.parse(SVG)
root = tree.getroot()
CSS = {}
for st in root.iter('{%s}style' % NS):
    for m in re.finditer(r'\.([\w-]+)\{([^}]*)\}', st.text or ''):
        sm = re.search(r'stroke:\s*(#[0-9A-Fa-f]{3,6})', m.group(2))
        CSS[m.group(1)] = sm.group(1) if sm else None

def hex2rgb(h):
    h = h.lstrip('#')
    if len(h) == 3:
        h = ''.join(c*2 for c in h)
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def transform_of(el):
    t = el.get('transform')
    if not t:
        return None
    m = re.match(r'translate\(([-\d.]+)[, ]+([-\d.]+)\)', t)
    if m:
        return ('t', float(m.group(1)), float(m.group(2)))
    m = re.match(r'matrix\(([-\d.eE]+),([-\d.eE]+),([-\d.eE]+),([-\d.eE]+),([-\d.eE]+),([-\d.eE]+)\)', t)
    if m:
        return ('m', *[float(v) for v in m.groups()])
    return None

def apply_tf(tf, x, y):
    if tf is None:
        return x, y
    if tf[0] == 't':
        return x+tf[1], y+tf[2]
    if tf[0] == 'm':
        _, a, b, c, d, e, f = tf
        return a*x+c*y+e, b*x+d*y+f
    return x, y

items = []
def walk(el, anc):
    tag = el.tag.split('}')[-1]
    if tag in ('path', 'circle', 'rect', 'line', 'ellipse'):
        items.append({'el': el, 'anc': list(anc), 'tag': tag})
    for ch in el:
        walk(ch, anc + [el])
walk(root, [])

def linecol(it):
    for e in [it['el']] + it['anc'][::-1]:
        c = e.get('class')
        if c in CSS and CSS[c]:
            return hex2rgb(CSS[c])
        v = e.get('stroke')
        if v and v.startswith('#'):
            return hex2rgb(v)
    return None

bycol = {}
for it in items:
    c = linecol(it)
    if c and max(c)-min(c) > 40 and max(c) > 60 and not min(c) > 200:
        bycol.setdefault(c, []).append(it)
keys = sorted(bycol, key=lambda k: -len(bycol[k]))
merged = []
for k in keys:
    if len(bycol[k]) < 6 or len(bycol[k]) > 400:
        continue
    for m in merged:
        if max(abs(k[i]-m['rgb'][i]) for i in range(3)) <= 18:
            m['items'] += bycol[k]
            break
    else:
        merged.append({'rgb': k, 'items': list(bycol[k])})

from PIL import Image
img = Image.open(PNG).convert('RGB')
arr = np.array(img).astype(int)
SC = img.width / VBW

def ring_med(cx, cy, r0, r1):
    x0, y0 = cx*SC, cy*SC
    pts = []
    for a in range(0, 360, 12):
        for r in np.arange(r0, r1, 2):
            x, y = int(x0 + r*np.cos(np.radians(a))), int(y0 + r*np.sin(np.radians(a)))
            if 0 <= x < arr.shape[1] and 0 <= y < arr.shape[0]:
                pts.append(arr[y, x])
    if not pts:
        return None
    px = np.array(pts)
    mx, mn = px.max(axis=1), px.min(axis=1)
    sel = px[(mx-mn > 40) & (mx > 60)]
    return np.median(sel, axis=0) if len(sel) >= 5 else None

def circle_pos(it):
    cx, cy = float(it['el'].get('cx', 0)), float(it['el'].get('cy', 0))
    for a in reversed(it['anc']):
        cx, cy = apply_tf(transform_of(a), cx, cy)
    return cx, cy

def path_points(it):
    """走廊path采样点(粗): d指令绝对坐标串"""
    d = it['el'].get('d', '')
    pts = []
    tok = re.findall(r'([MmLlHhVvZz])|(-?\d+\.?\d*)', d)
    cur = [0.0, 0.0]
    cmd = None
    nums = []
    for c, n in tok:
        if c:
            if cmd == 'M' and len(nums) >= 2:
                cur = nums[-2:]
                pts.append((cur[0], cur[1]))
            elif cmd in ('L', 'M') and nums:
                pass
            if c in 'ML':
                nums = []
            cmd = c
        else:
            nums.append(float(n))
            if cmd in ('L', 'M') and len(nums) >= 2:
                x, y = nums[-2], nums[-1]
                pts.append((x, y))
            elif cmd == 'H' and nums:
                pts.append((nums[-1], cur[1]))
            elif cmd == 'V' and nums:
                pts.append((cur[0], nums[-1]))
    # C/Q曲线的控制点也近似为轨迹
    for x, y in re.findall(r'[,-](-?\d+\.?\d*)[,\s]+(-?\d+\.?\d*)', d)[::3]:
        pts.append((float(x), float(y)))
    # 变换
    out = []
    for x, y in pts:
        for a in reversed(it['anc']):
            x, y = apply_tf(transform_of(a), x, y)
        out.append((x, y))
    return out

lat0 = np.mean([st['lat'] for st in known['stations']])
KX = 111000*math.cos(math.radians(lat0))
KY = -111000
geo = {st['id']: (st['lon']*KX, st['lat']*KY) for st in known['stations']}

corridors = []
for i, m in enumerate(merged):
    pts = []
    for it in m['items']:
        if it['tag'] in ('path', 'line'):
            pts += path_points(it)
    circles = []
    for it in items:
        if it['tag'] != 'circle':
            continue
        cx, cy = circle_pos(it)
        r = float(it['el'].get('r', 4))
        med = ring_med(cx, cy, r+3, r+12)
        if med is None:
            continue
        if np.linalg.norm(med - np.array(m['rgb'])) < 60:
            circles.append((cx, cy))
    if len(circles) < 5 or len(pts) < 4:
        continue
    P = np.array(pts)
    # 站圆弧长: 就近走廊点序号
    order = []
    for cx, cy in circles:
        d2 = ((P[:, 0]-cx)**2 + (P[:, 1]-cy)**2)
        j = int(np.argmin(d2))
        order.append((j, cx, cy, float(math.sqrt(d2[j]))))
    order.sort()
    # 去重(同一走廊点多圆取一)
    dedup = []
    lastj = -99
    for j, cx, cy, dd in order:
        if j == lastj:
            continue
        dedup.append((cx, cy, dd))
        lastj = j
    corridors.append({'rgb': m['rgb'], 'pts_count': len(P), 'stations': dedup})

# ---- 与已知线匹配: 站数 + 两端走向 ----
lines_known = {}
for l in known['lines']:
    sts = l['stations']
    lines_known[l['ref']] = sts
used_refs = set()
result = {}
rep = []
for c in sorted(corridors, key=lambda c: -len(c['stations'])):
    n = len(c['stations'])
    if n < 5:
        continue
    S = np.array([(x, y) for x, y, _ in c['stations']])
    v_raster = S[-1] - S[0]
    best = None
    for ref, sts in lines_known.items():
        if ref in used_refs or len(sts) < 4:
            continue
        # 允许站数差<=2(漏检/混线) 且端点地理方向与栅格方向一致
        if abs(len(sts) - n) > 3:
            continue
        g0, g1 = geo.get(sts[0]), geo.get(sts[-1])
        if not g0 or not g1:
            continue
        vgeo = np.array(g1) - np.array(g0)
        cos = float(np.dot(v_raster, vgeo) / (np.linalg.norm(v_raster)*np.linalg.norm(vgeo) + 1e-9))
        cosf = float(np.dot(-v_raster, vgeo) / (np.linalg.norm(v_raster)*np.linalg.norm(vgeo) + 1e-9))
        sc = max(abs(cos), abs(cosf)) - abs(len(sts)-n)*0.05
        if best is None or sc > best[0]:
            best = (sc, ref, cos, cosf)
    if best and best[0] > 0.3:
        sc, ref, cos, cosf = best
        used_refs.add(ref)
        sts = lines_known[ref]
        flip = cosf > cos
        st_list = c['stations'][::-1] if flip else c['stations']
        # 若站数不齐: 均匀缺站标记(名字按序对位可能错位, 记录差距)
        result[ref] = [{'seq': k+1,
                        'name': (sts[k] if k < len(sts) and len(sts) == len(st_list) else None),
                        'x': round(x, 1), 'y': round(y, 1)}
                       for k, (x, y, _) in enumerate(st_list)]
        rep.append(f"{ref}: 站圆{n} vs 已知{len(sts)} {'翻转' if flip else '正序'} cos={max(cos,cosf):.2f}"
                   + ('' if len(sts)==n else ' [站数不齐,名字对位存疑]'))
    else:
        rep.append(f"未匹配色走廊: rgb{c['rgb']} {n}站")

print('\n'.join(rep))
json.dump({'lines': result, 'meta': {'coord': 'Tim SVG viewBox 2848.5x2054.25',
                                     'order': '站圆沿走廊弧长序=官图站序(方向按地理端点校验)'}},
          open('data/gz-line-stations.json', 'w'), ensure_ascii=False, indent=1)
ok = sum(1 for v in result.values() if all(s['name'] for s in v))
print(f'定线 {len(result)} 条, 站数与已知完全一致 {ok} 条')
