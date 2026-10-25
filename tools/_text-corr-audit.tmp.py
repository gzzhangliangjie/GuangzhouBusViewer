# -*- coding: utf-8 -*-
# 全量审计: 站名文字盒(中+英) vs 全部走廊 净距<4.5 的违规清单
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
t = open('assets/lines/network-全网.svg', encoding='utf-8').read()

def seg_d(p, a, b):
    dd = ((b[0]-a[0])**2 + (b[1]-a[1])**2) ** 0.5 or 1.0
    tt = max(0.0, min(1.0, ((p[0]-a[0])*(b[0]-a[0]) + (p[1]-a[1])*(b[1]-a[1])) / dd / dd))
    return ((p[0]-a[0]-tt*(b[0]-a[0]))**2 + (p[1]-a[1]-tt*(b[1]-a[1]))**2) ** 0.5

def rect_seg(rect, a, b):
    best = 9e9
    for px, py in ((rect[0], rect[1]), (rect[0]+rect[2], rect[1]),
                   (rect[0], rect[1]+rect[3]), (rect[0]+rect[2], rect[1]+rect[3]),
                   (rect[0]+rect[2]/2, rect[1]), (rect[0]+rect[2]/2, rect[1]+rect[3]),
                   (rect[0], rect[1]+rect[3]/2), (rect[0]+rect[2], rect[1]+rect[3]/2)):
        best = min(best, seg_d((px, py), a, b))
    # 线段端点在矩形内的情况
    for ex, ey in ((a[0], a[1]), (b[0], b[1])):
        if rect[0] <= ex <= rect[0]+rect[2] and rect[1] <= ey <= rect[1]+rect[3]:
            best = 0.0
    return best

corridors = []
for m in re.finditer(r'<line x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)"', t):
    corridors.append(tuple(float(m.group(k)) for k in (1, 2, 3, 4)))
lm = re.search(r'<g id="站名标注"[^>]*>(.*?)</g>', t, re.S)
bad = []
for mm in re.finditer(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*font-size="([\d.]+)"[^>]*>([^<]+)</text>', lm.group(1)):
    fs = float(mm.group(3))
    w = sum(fs if ord(ch) > 0x2E80 else 0.56 * fs for ch in mm.group(4))
    hh = fs * 1.12
    x = float(mm.group(1)) - w / 2
    y = float(mm.group(2)) - fs * 0.92
    rect = (x, y, w, hh)
    _best = min(((rect_seg(rect, (s[0], s[1]), (s[2], s[3])), s) for s in corridors), key=lambda r: r[0])
    d, seg = _best
    if d < 4.5:
        bad.append((d, mm.group(4), round(x, 1), round(y, 1), seg))
bad.sort()
for d, nm, x, y, seg in bad:
    print('%.2fpt %s 文字盒(%g,%g) 肇事段(%g,%g)->(%g,%g)' % (d, nm, x, y, seg[0], seg[1], seg[2], seg[3]))
print('违规总数:', len(bad))
