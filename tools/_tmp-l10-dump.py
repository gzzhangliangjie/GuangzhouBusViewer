# -*- coding: utf-8 -*-
"""官图10号线(_x31_0_1_)走廊dump + 沿线站圆/st57标记提取, 与我方钉位对账"""
import re, io, sys, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

s = open('assets/gz-tim-2026.svg', encoding='utf-8').read()
m = re.search(r'<g id="_x31_0_1_"(?:>| )', s)
assert m, 'group not found'
start = m.end()
depth, j = 1, start
while depth:
    no, nc = s.find('<g', j), s.find('</g>', j)
    if no != -1 and no < nc:
        depth += 1
        j = no + 2
    else:
        depth -= 1
        j = nc + 4
body = s[start:j - 4]

segs = []
for mm in re.finditer(r'<line\b([^>]*)/>', body):
    g = re.search(r'x1="([-\d.]+)"\s+y1="([-\d.]+)"\s+x2="([-\d.]+)"\s+y2="([-\d.]+)"', mm.group(1))
    a, b, c, d = (float(v) for v in g.groups())
    segs.append((a, b, c, d))
    print('L (%.2f,%.2f)-(%.2f,%.2f)' % (a, b, c, d))
for mm in re.finditer(r'<path\b([^>]*)/>', body):
    dm = re.search(r'\bd="([^"]+)"', mm.group(1))
    print('P d=%s' % dm.group(1)[:90])

def pdist(sg, px, py):
    x1, y1, x2, y2 = sg
    L2 = (x2 - x1) ** 2 + (y2 - y1) ** 2
    t = max(0.0, min(1.0, ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / L2))
    return math.hypot(px - x1 - t * (x2 - x1), py - y1 - t * (y2 - y1))

print('---- 站圆(距走廊≤6px) ----')
for mm in re.finditer(r'<circle\b([^>]*)/>', s):
    g = re.search(r'cx="([-\d.]+)"\s+cy="([-\d.]+)"', mm.group(1))
    if not g:
        continue
    a, b = float(g.group(1)), float(g.group(2))
    d = min(pdist(sg, a, b) for sg in segs)
    if d <= 6.0:
        cls = re.search(r'class="([^"]+)"', mm.group(1))
        print('C (%8.2f,%8.2f) d=%.1f %s' % (a, b, d, cls.group(1) if cls else '-'))

print('---- st57标记(距走廊≤18px) ----')
for mm in re.finditer(r'<(?:circle|path)\b([^>]*)class="st57"[^>]*/>', s):
    t = mm.group(0)
    if t.startswith('<circle'):
        g = re.search(r'cx="([-\d.]+)"\s+cy="([-\d.]+)"', t)
        a, b = float(g.group(1)), float(g.group(2))
        txt = '(%s,%s)' % (a, b)
    else:
        dm = re.search(r'\bd="([^"]+)"', t)
        nums = [float(v) for v in re.findall(r'-?\d+\.?\d*', dm.group(1))]
        pts = list(zip(nums[::2], nums[1::2]))
        a = sum(p[0] for p in pts) / len(pts)
        b = sum(p[1] for p in pts) / len(pts)
        txt = 'c~(%.1f,%.1f) %s' % (a, b, dm.group(1)[:50])
    d = min(pdist(sg, a, b) for sg in segs)
    if d <= 18.0:
        print('57 d=%.1f %s' % (d, txt))
