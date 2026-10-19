# -*- coding: utf-8 -*-
"""11号线环线逐段像素扫描: 找非#FFCC66标记(站点刻度/黑圆)的中心"""
from PIL import Image
import math, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
im = Image.open(r'C:/Users/zlj10/WorkBuddy/2026-10-18-14-11-14/metro/gz_metro_2026_5700px.png').convert('RGB')
sc = 5700/2848.5
Y = (255, 204, 102)
def yellow(c):
    return abs(c[0]-Y[0]) < 60 and abs(c[1]-Y[1]) < 60 and abs(c[2]-Y[2]) < 80
def walk(x0, y0, x1, y1, name):
    L = math.hypot(x1-x0, y1-y0); n = int(L*2)
    runs = []; cur = None
    for i in range(n+1):
        t = i/n; x = x0+(x1-x0)*t; y = y0+(y1-y0)*t
        # 垂直于走向采样3点, 取中点色
        dx, dy = (x1-x0)/L, (y1-y0)/L
        best = None
        for off in (0,):
            c = im.getpixel((int((x-dy*off)*sc), int((y+dx*off)*sc)))
        c = im.getpixel((int(x*sc), int(y*sc)))
        if not yellow(c):
            if cur is None: cur = [t, t]
            else: cur[1] = t
        else:
            if cur is not None:
                runs.append(cur); cur = None
    if cur: runs.append(cur)
    print('%s:' % name)
    for t0, t1 in runs:
        if (t1-t0)*L < 2.5: continue
        tm = (t0+t1)/2
        print('  (%.1f, %.1f) w=%.1f' % (x0+(x1-x0)*tm, y0+(y1-y0)*tm, (t1-t0)*L))
walk(1876.5, 965.2, 1876.5, 1163.2, '东竖 x1876.5 y965-1163')
walk(1867.5, 947.2, 1777.5, 857.2, 'NE斜')
walk(1759.5, 848.2, 1242.0, 848.2, '北横 y848')
walk(1215.0, 861.8, 1134.0, 942.8, 'NW斜')
walk(1120.5, 969.8, 1120.5, 1163.2, '西竖 x1120.5')
walk(1129.5, 1181.2, 1219.5, 1271.2, 'SW斜')
walk(1237.5, 1280.2, 1759.5, 1280.2, '南横 y1280')
walk(1777.5, 1271.2, 1867.5, 1181.2, 'SE斜')
