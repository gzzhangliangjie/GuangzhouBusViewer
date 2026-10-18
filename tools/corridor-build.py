# -*- coding: utf-8 -*-
"""走廊构建 v2: 带掩码MCP最短代价路径连框
每框为源, 在4x降采样代价栅格(带=1, 非带=40)上扩散, 到邻近框的累计代价<=K*欧氏距离 -> 边.
输出: data/corridor-graph.json
"""
import json
import numpy as np
from PIL import Image
from skimage.graph import MCP_Geometric

arr = np.array(Image.open('assets/official-ref.jpg').convert('RGB')).astype(int)
H, W, _ = arr.shape
stations = json.load(open('data/multibox-stations.json'))

flat = []
for si, s in enumerate(stations):
    for bi, b in enumerate(s['boxes']):
        flat.append({'bid': len(flat)+1, 'si': si, 'box': b, 'cx': b['cx'], 'cy': b['cy']})

r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
mx = arr.max(axis=2)
band = (mx < 235) & ((np.abs(r-g) > 18) | (np.abs(g-b) > 18) | (np.abs(r-b) > 18))
band[:380, :] = False
band[5460:, :] = False
for it in flat:
    bx = it['box']
    band[max(bx['y0']-2, 0):bx['y1']+3, max(bx['x0']-2, 0):bx['x1']+3] = True   # 胶囊内可通行

# 4x 降采样(块内有带则带)
ds = 4
h2, w2 = H//ds, W//ds
bm = band[:h2*ds, :w2*ds].reshape(h2, ds, w2, ds).any(axis=(1, 3))
cost = np.where(bm, 1.0, 40.0)
print(f'栅格 {w2}x{h2}, 带占比 {bm.mean():.3f}')

mcp = MCP_Geometric(cost)
pos = {it['bid']: (min(int(it['cy']//ds), h2-1), min(int(it['cx']//ds), w2-1)) for it in flat}

MAXEU = 720     # 欧氏上限(px, 原图)
K = 3.2         # 代价/欧氏 上限
edges = []
for it in flat:
    src = pos[it['bid']]
    cume, _ = mcp.find_costs([src])
    for jt in flat:
        if jt['bid'] <= it['bid']:
            continue
        eu = np.hypot(it['cx']-jt['cx'], it['cy']-jt['cy'])
        if eu > MAXEU or eu < 8:
            continue
        c = cume[pos[jt['bid']]]
        if not np.isfinite(c):
            continue
        if c <= K * (eu/ds) + 15:
            edges.append((it['bid'], jt['bid'], round(float(c)*ds, 0), round(eu, 0)))
print(f'边 {len(edges)}')

adj = {it['bid']: [] for it in flat}
for a, b2, _, _ in edges:
    adj[a].append(b2)
    adj[b2].append(a)
comps = []
seen = set()
for it in flat:
    if it['bid'] in seen:
        continue
    stack, comp = [it['bid']], []
    seen.add(it['bid'])
    while stack:
        u = stack.pop()
        comp.append(u)
        for v in adj[u]:
            if v not in seen:
                seen.add(v)
                stack.append(v)
    comps.append(sorted(comp))
comps.sort(key=len, reverse=True)
print(f'分量 {len(comps)}: 尺寸', sorted([len(c) for c in comps], reverse=True)[:25])
json.dump({'nodes': [it['bid'] for it in flat], 'edges': [{'a': a, 'b': b2, 'cost': c, 'eu': e} for a, b2, c, e in edges],
           'comps': comps}, open('data/corridor-graph.json', 'w'), indent=1)
print('done')
