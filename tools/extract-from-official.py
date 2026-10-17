# -*- coding: utf-8 -*-
# 官图颜色→线段→站点提取管线
# 步骤：① 颜色掩码 → ② 行/列扫描找线段 → ③ 沿线段找白圆 → ④ 输出站点坐标
from PIL import Image, ImageDraw
import numpy as np
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

img = Image.open('assets/official-ref.jpg').convert('RGB')
arr = np.array(img)
H, W = arr.shape[:2]

COLORS = {
  '1': (243, 211, 0),    # 黄
  '2': (0, 98, 155),     # 蓝
  '3': (236, 161, 84),   # 橙
  '4': (0, 132, 61),     # 绿
  '5': (197, 0, 62),     # 红
  '6': (128, 40, 108),   # 紫
  '8': (0, 138, 150),    # 青
}

def color_mask(rgb, tol=40):
    r, g, b = rgb
    return (np.abs(arr[:,:,0].astype(int)-r) < tol) & \
           (np.abs(arr[:,:,1].astype(int)-g) < tol) & \
           (np.abs(arr[:,:,2].astype(int)-b) < tol)

def find_segments(mask):
    """行/列扫描找水平/垂直线段"""
    segments = []  # (x1,y1,x2,y2) 水平或垂直
    # 水平线段：每行找连续run
    for y in range(0, H, 3):  # 降采样加速
        row = mask[y]
        if not row.any(): continue
        xs = np.where(row)[0]
        # 分组连续run
        runs = []
        start = xs[0]
        for i in range(1, len(xs)):
            if xs[i] - xs[i-1] > 10:
                if xs[i-1] - start > 30:  # 线段最短30px
                    runs.append((start, xs[i-1]))
                start = xs[i]
        if xs[-1] - start > 30:
            runs.append((start, xs[-1]))
        for x1, x2 in runs:
            segments.append(('h', x1, y, x2, y))
    # 垂直线段：每列找连续run
    for x in range(0, W, 3):
        col = mask[:, x]
        if not col.any(): continue
        ys = np.where(col)[0]
        runs = []
        start = ys[0]
        for i in range(1, len(ys)):
            if ys[i] - ys[i-1] > 10:
                if ys[i-1] - start > 30:
                    runs.append((start, ys[i-1]))
                start = ys[i]
        if ys[-1] - start > 30:
            runs.append((start, ys[-1]))
        for y1, y2 in runs:
            segments.append(('v', x, y1, x, y2))
    return segments

def find_stations_on_line(mask, min_d=14, max_d=45):
    """沿线找白圆：白圆 = 线颜色附近的白色像素群"""
    # 构建线的膨胀区域（线附近30px范围）
    # 用卷积近似膨胀
    from numpy.lib.stride_tricks import sliding_window_view
    # 简单方法：对每个白像素，检查周围是否有线颜色
    white = (arr[:,:,0] > 225) & (arr[:,:,1] > 225) & (arr[:,:,2] > 225)
    # 只检查线附近的白像素（在mask的bounding box内）
    ys_line, xs_line = np.where(mask)
    if len(ys_line) == 0: return []
    # 用粗网格（步长5）扫描线附近
    station_candidates = []
    checked = set()
    for y, x in zip(ys_line[::20], xs_line[::20]):
        # 在线像素附近找白圆
        for dy in range(-25, 26, 5):
            for dx in range(-25, 26, 5):
                cy, cx = y + dy, x + dx
                if not (0 <= cy < H and 0 <= cx < W): continue
                key = (cy // 10, cx // 10)
                if key in checked: continue
                checked.add(key)
                if white[cy, cx]:
                    # 从这里向四周扩展找白圆边界
                    y1, y2 = cy, cy
                    x1, x2 = cx, cx
                    # 上下扩展
                    while y1 > 0 and white[y1-1, cx] and cy - y1 < 30: y1 -= 1
                    while y2 < H-1 and white[y2+1, cx] and y2 - cy < 30: y2 += 1
                    # 左右扩展
                    while x1 > 0 and white[cy, x1-1] and cx - x1 < 30: x1 -= 1
                    while x2 < W-1 and white[cy, x2+1] and x2 - cx < 30: x2 += 1
                    d1 = y2 - y1
                    d2 = x2 - x1
                    if min_d <= d1 <= max_d and min_d <= d2 <= max_d and abs(d1 - d2) < 12:
                        # 检查周围是否有线颜色
                        found_line = False
                        for rr in range(max(0,cy-35), min(H,cy+35), 5):
                            for cc in range(max(0,cx-35), min(W,cx+35), 5):
                                if mask[rr, cc]:
                                    found_line = True
                                    break
                            if found_line: break
                        if found_line:
                            station_candidates.append((cx, cy))
    # 去重（距离<20px的合并）
    station_candidates.sort()
    deduped = []
    for c in station_candidates:
        if not deduped or (abs(c[0]-deduped[-1][0]) > 20 or abs(c[1]-deduped[-1][1]) > 20):
            deduped.append(c)
    return deduped

# 提取1号线
ref = '1'
rgb = COLORS[ref]
mask = color_mask(rgb)
print(f'{ref}号线 #{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}: {mask.sum()}px')

segs = find_segments(mask)
print(f'线段数: {len(segs)}')
for s in segs[:10]:
    print(f'  {s[0]}: ({s[1]},{s[2]}) → ({s[3]},{s[4]}) 长{abs(s[3]-s[1]) + abs(s[4]-s[2])}px')

stations = find_stations_on_line(mask)
print(f'站圆数: {len(stations)}')
stations.sort(key=lambda p: p[0])  # 按x排序（1号线西→东）
for i, (cx, cy) in enumerate(stations):
    print(f'  {i+1:02d}: ({cx},{cy})')

# 生成标注图
draw_img = img.copy()
draw = ImageDraw.Draw(draw_img)
# 画线段
for s in segs[:30]:
    draw.line([(s[1], s[2]), (s[3], s[4])], fill=(255, 0, 0), width=2)
# 画站圆
for i, (cx, cy) in enumerate(stations):
    draw.ellipse([cx-25, cy-25, cx+25, cy+25], outline='#ff0000', width=4)
    draw.text((cx-10, cy-60), str(i+1), fill='#ff0000')

# 裁剪到线路范围
ys_s, xs_s = np.where(mask)
if len(ys_s):
    pad = 200
    crop = draw_img.crop((max(0,xs_s.min()-pad), max(0,ys_s.min()-pad),
                          min(W,xs_s.max()+pad), min(H,ys_s.max()+pad)))
    crop.thumbnail((2000, 2000))
    crop.save(f'assets/_extracted-line{ref}.png')
    print(f'标注图: assets/_extracted-line{ref}.png ({crop.size})')

# 保存提取结果
json.dump({
    'line': ref, 'color': f'#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}',
    'segments': [{'type': s[0], 'x1': s[1], 'y1': s[2], 'x2': s[3], 'y2': s[4]} for s in segs],
    'stations': [{'index': i+1, 'img_x': cx, 'img_y': cy} for i, (cx, cy) in enumerate(stations)]
}, open(f'data/extracted-line{ref}.json', 'w'), indent=1)
print(f'保存 data/extracted-line{ref}.json')
