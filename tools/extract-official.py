# -*- coding: utf-8 -*-
"""官方参考图线路提取 v2: 实测采色 -> 遮罩 -> 闭合成带 -> 沿线推进 -> RDP线段拟合 -> 白圆=站
用法: python tools/extract-official.py <lineNo> <seedX,seedY> [tol]
种子点必须落在线路本体上(非站点处)。
输出: data/official-ext-lineN.json + assets/_ext-lineN.png 标注图
"""
import sys, json, math
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

IMG = 'assets/official-ref.jpg'
TOP_IGNORE = 600      # 顶部标题区忽略
STEP = 12             # 推进步长
WIN = 23              # 推进窗口半径
CLOSING = 31          # 闭合成带宽度(填站圆)
MIN_RUN = 40          # 站间最小间距
RDP_EPS = 18          # 线段拟合容差

def sample_color(arr, sx, sy, rad=12):
    region = arr[max(sy-rad,0):sy+rad, max(sx-rad,0):sx+rad].reshape(-1,3)
    return tuple(int(v) for v in np.median(region, 0))

def make_masks(arr, ref, tol):
    r, g, b = arr[:,:,0].astype(int), arr[:,:,1].astype(int), arr[:,:,2].astype(int)
    m = np.sqrt((r-ref[0])**2 + (g-ref[1])**2 + (b-ref[2])**2) < tol
    m[:TOP_IGNORE,:] = False
    lbl, n = ndimage.label(m, structure=np.ones((3,3)))
    if n:
        sizes = ndimage.sum(m, lbl, range(1, n+1))
        m = np.isin(lbl, np.where(sizes >= 80)[0] + 1)
    # 可分离结构闭合成带(补站圆缺口与压线文字造成的洞)
    s1 = np.ones((CLOSING,1), bool); s2 = np.ones((1,CLOSING), bool)
    c = ndimage.binary_dilation(m, s1); c = ndimage.binary_dilation(c, s2)
    c = ndimage.binary_erosion(c, s1);  c = ndimage.binary_erosion(c, s2)
    return m, c

def march(mask, seed, heading, max_steps=2500):
    """前向扇区质心 + 动量限转的走线"""
    h = np.array(heading, float); h /= np.linalg.norm(h)
    x, y = float(seed[0]), float(seed[1])
    R = 20
    path = []
    for _ in range(max_steps):
        x0, y0 = int(round(x)), int(round(y))
        ya, yb = max(y0-R,0), min(y0+R+1, mask.shape[0])
        xa, xb = max(x0-R,0), min(x0+R+1, mask.shape[1])
        win = mask[ya:yb, xa:xb]
        if win.sum() < 25: break
        ys, xs = np.where(win)
        xs = xs + xa; ys = ys + ya
        dx = xs - x; dy = ys - y
        sel = (dx*h[0] + dy*h[1] > 0) & (dx*dx + dy*dy < (R*0.9)**2)
        if sel.sum() < 15: break
        cx, cy = float(xs[sel].mean()), float(ys[sel].mean())
        d = np.array([cx - x, cy - y])
        nd = np.linalg.norm(d)
        if nd < 0.5: break
        d /= nd
        h = 0.6*h + 0.4*d
        nh = np.linalg.norm(h)
        if nh < 1e-6: break
        h /= nh
        x, y = x + h[0]*STEP, y + h[1]*STEP
        path.append((int(round(x)), int(round(y))))
        if len(path) > 40 and abs(x-path[-40][0]) < 12 and abs(y-path[-40][1]) < 12:
            break  # 环路保护
    return path

def rdp(points, eps):
    if len(points) < 3: return points[:]
    pts = np.array(points, float)
    a, b = pts[0], pts[-1]
    ab = b - a; n = math.hypot(*ab)
    if n < 1e-6: _, idx = max((np.hypot(*(p-a)), i) for i, p in enumerate(pts)); d, idx = _, idx
    else:
        d = np.abs(ab[0]*(pts[:,1]-a[1]) - ab[1]*(pts[:,0]-a[0])) / n
        idx = int(d.argmax())
    if d[idx] <= eps: return [points[0], points[-1]]
    left = rdp(points[:idx+1], eps); right = rdp(points[idx:], eps)
    return left[:-1] + right

def find_stations(orig, path):
    cov = []
    yy, xx = np.mgrid[-6:7, -6:7]
    disk = (yy**2 + xx**2) <= 36
    H, W = orig.shape
    for (x, y) in path:
        if 6 <= x < W-6 and 6 <= y < H-6:
            cov.append(float(orig[y-6:y+7, x-6:x+7][disk].mean()))
        else:
            cov.append(1.0)
    cov = np.array(cov)
    low = cov < 0.2
    stations = []
    i = 0
    while i < len(path):
        if low[i]:
            j = i
            while j+1 < len(path) and low[j+1]: j += 1
            seg = path[i:j+1]
            cx = sum(p[0] for p in seg)/len(seg)
            cy = sum(p[1] for p in seg)/len(seg)
            stations.append({'x': int(cx), 'y': int(cy), 'run': len(seg)})
            i = j+1
        else:
            i += 1
    merged = []
    for st in stations:
        if merged and math.hypot(st['x']-merged[-1]['x'], st['y']-merged[-1]['y']) < MIN_RUN:
            a, b = merged[-1], st
            w = a['run'] + b['run']
            merged[-1] = {'x': int((a['x']*a['run']+b['x']*b['run'])/w),
                          'y': int((a['y']*a['run']+b['y']*b['run'])/w), 'run': w}
        else:
            merged.append(st)
    return merged

def main(line, seed, tol):
    img = Image.open(IMG).convert('RGB')
    arr = np.array(img)
    ref = sample_color(arr, *seed)
    print(f'实测种子色: RGB{ref}')
    orig, closed = make_masks(arr, ref, tol)

    xi, yi = seed
    win = closed[yi-WIN:yi+WIN+1, xi-WIN:xi+WIN+1]
    ys, xs = np.where(win)
    pts = np.stack([xs, ys], 1).astype(float)
    ctr = pts.mean(0); p = pts - ctr
    val, vec = np.linalg.eigh(p.T @ p / len(p))
    v = vec[:, -1]

    fwd = march(closed, (xi, yi), v)
    bwd = march(closed, (xi, yi), -v)
    path = bwd[::-1] + fwd
    print(f'推进路径: {len(path)} 点, 端点 {path[0]} -> {path[-1]}')

    segs = rdp(path, RDP_EPS)
    print(f'RDP 线段拟合: {len(segs)} 顶点 -> {len(segs)-1} 段')
    for i in range(len(segs)-1):
        print(f'  段{i+1}: {segs[i]} -> {segs[i+1]}')

    stations = find_stations(orig, path)
    print(f'站点: {len(stations)}')
    for i, st in enumerate(stations):
        print(f'  {i+1:02d}: ({st["x"]},{st["y"]}) run={st["run"]}')

    json.dump({'line': line, 'refColor': list(ref), 'tol': tol, 'seed': list(seed),
               'pathLen': len(path),
               'segments': [[int(a[0]),int(a[1]),int(b[0]),int(b[1])] for a,b in zip(segs,segs[1:])],
               'stations': [{'i': i+1, 'x': st['x'], 'y': st['y']} for i, st in enumerate(stations)]},
              open(f'data/official-ext-line{line}.json','w'), indent=1)

    draw = ImageDraw.Draw(img)
    draw.line([tuple(s) for s in segs], fill='#ff0000', width=3)
    for i, st in enumerate(stations):
        draw.ellipse([st['x']-30,st['y']-30,st['x']+30,st['y']+30], outline='#ff0000', width=5)
        draw.text((st['x']-12, st['y']-75), str(i+1), fill='#ff0000')
    xs = [st['x'] for st in stations]; ys = [st['y'] for st in stations]
    box = (max(min(xs)-250,0), max(min(ys)-250,0), min(max(xs)+250, img.width), min(max(ys)+250, img.height))
    img.crop(box).save(f'assets/_ext-line{line}.png')
    print(f'标注图 assets/_ext-line{line}.png')

if __name__ == '__main__':
    seed = tuple(int(v) for v in sys.argv[2].split(','))
    main(sys.argv[1], seed, int(sys.argv[3]) if len(sys.argv)>3 else 45)
