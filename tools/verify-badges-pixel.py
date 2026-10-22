# -*- coding: utf-8 -*-
"""徽标像素审计门禁: 渲染后全部徽标四边外扩3px扫描, 任何线色穿透=FAIL。
规范: 徽标不得压任何走廊; ⚠️viewBox必须从SVG实时读取(徽标移动会改变画布bbox, 硬编码=坐标错位假告警)。
用法: python tools/verify-badges-pixel.py  (改徽标必跑, 2026-10-23教训)
"""
import io, os, sys, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_card_pixel import render

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG = os.path.join(ROOT, 'assets/lines/network-全网.svg')
im, _ = render(SVG)
head = open(SVG, encoding='utf-8').read(400)
VB = [float(v) for v in re.search(r'viewBox="([-\d. ]+)"', head).group(1).split()]
H, W = im.shape[:2]
sx, sy = W / VB[2], H / VB[3]

def sample(x, y):
    px_, py_ = int((x - VB[0]) * sx), int((y - VB[1]) * sy)
    if 0 <= px_ < W and 0 <= py_ < H:
        return tuple(int(v) for v in im[py_, px_])
    return (255, 255, 255)

def is_line_color(p):
    r, g, b = p
    if r > 235 and g > 235 and b > 235:
        return False
    if r < 60 and g < 60 and b < 60:
        return False
    return True

LINES_DIR = os.path.join(ROOT, 'assets/lines')
size = {}
for name in ['1号线','2号线','3号线','4号线','5号线','6号线','7号线','8号线','9号线','10号线','11号线','12号线','13号线','14号线','18号线','21号线','22号线','广佛线','APM线']:
    src = open(os.path.join(LINES_DIR, 'line-%s.svg' % name), encoding='utf-8').read()
    m = re.search(r'<g data-badge="header"[^>]*>(.*?)</g>', src, re.S)
    rr = re.search(r'<rect x="([\d.-]+)" y="([\d.-]+)" width="([\d.]+)" height="([\d.]+)"', m.group(1))
    sc = {'APM线': 0.5}.get(name, 0.7)
    size[name] = (float(rr.group(3)) * sc, float(rr.group(4)) * sc)

badges = json.load(open(os.path.join(ROOT, 'data/_network-audit.json'), encoding='utf-8'))['badges']
bad = 0
for nm, bx, by in badges:
    bw, bh = size[nm]
    hits = []
    for xi in range(int(bx) - 3, int(bx + bw) + 4):
        for yy in (by - 3, by + bh + 3):
            if is_line_color(sample(xi, yy)):
                hits.append(('T' if yy < by else 'B', xi, yy, sample(xi, yy)))
    for yi in range(int(by) - 3, int(by + bh) + 4):
        for xx in (bx - 3, bx + bw + 3):
            if is_line_color(sample(xx, yi)):
                hits.append(('L' if xx < bx else 'R', xx, yi, sample(xx, yi)))
    if hits:
        bad += 1
        print('!! %s (%.0f,%.0f) 穿透%d处: %s' % (nm, bx, by, len(hits), hits[:3]))
print('徽标像素审计: %d/%d 穿透' % (bad, len(badges)))
sys.exit(1 if bad else 0)
