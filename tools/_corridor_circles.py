# -*- coding: utf-8 -*-
"""列出某组走廊沿线圆位(含弧长), 供人工核钉: python tools/_corridor_circles.py <gid>"""
import sys, io, re, math
sys.stdout=io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'tools')
import importlib.util
spec = importlib.util.spec_from_file_location('gc', 'tools/group-card.py')
import os
os.environ['PROBE']='1'
src = open('assets/gz-tim-2026.svg', encoding='utf-8').read()
sm = re.search(r'<style[^>]*>(.*?)</style>', src, re.S).group(1)
cls = {}; hid = set()
for mm in re.finditer(r'\.(st\d+)\{([^}]*)\}', sm):
    if 'display:none' in mm.group(2).replace(' ', ''): hid.add(mm.group(1))
    pm = re.search(r'stroke:(#[0-9A-Fa-f]{6})', mm.group(2))
    if pm: cls[mm.group(1)] = pm.group(1)
import build_card as B
gid = sys.argv[1]
gm = re.search(r'<g\b[^>]*id="%s"[^>]*>' % re.escape(gid), src)
start = gm.end(); depth = 1; j = start
while depth > 0:
    no = src.find('<g', j); nc = src.find('</g>', j)
    if no != -1 and no < nc: depth += 1; j = no + 2
    else: depth -= 1; j = nc + 4
inner = src[start:j]
segs = []
for lm in re.finditer(r'<line\b[^>]*/>', inner):
    at = dict(re.findall(r'([\w-]+)="([^"]*)"', lm.group(0)))
    if at.get('class') in hid: continue
    segs.append(tuple(float(at[k]) for k in ('x1','y1','x2','y2')))
for pm in re.finditer(r'<path\b[^>]*/>', inner):
    at = dict(re.findall(r'([\w-]+)="([^"]*)"', pm.group(0)))
    if at.get('class') in hid: continue
    d = at.get('d', '')
    if d.startswith('M'):
        pts = B.sample_d(d)
        if len(pts) >= 2: segs.append((pts[0][0], pts[0][1], pts[-1][0], pts[-1][1]))
# 弧长参数化(按段序, 不链化 — 只为排序)
acc = 0; sadd = []
for s in segs:
    L = math.hypot(s[2]-s[0], s[3]-s[1])
    sadd.append((acc, s)); acc += L
def narc(px, py):
    ba, bd = 0, 1e18
    for a0, (x1,y1,x2,y2) in sadd:
        dx, dy = x2-x1, y2-y1; L2 = dx*dx+dy*dy
        if L2 < 1e-9: continue
        t = max(0, min(1, ((px-x1)*dx+(py-y1)*dy)/L2))
        d = math.hypot(x1+t*dx-px, y1+t*dy-py)
        if d < bd: bd, ba = d, a0+t*math.hypot(dx,dy)
    return ba, bd
rows = []
for cm in re.finditer(r'<circle ([^>]+)/>', src):
    at = dict(re.findall(r'([\w-]+)="([^"]*)"', cm.group(1)))
    try: cx, cy = float(at['cx']), float(at['cy'])
    except: continue
    if cx < 300: continue
    a, d = narc(cx, cy)
    if d < 10: rows.append((a, cx, cy, cls.get(at.get('class','?'), '?'), d))
rows.sort()
for a, cx, cy, col, d in rows:
    print('arc %7.1f  (%7.1f,%7.1f) %-8s d=%.1f' % (a, cx, cy, col, d))
print('total len %.1f, %d segs, %d circles' % (acc, len(segs), len(rows)))
