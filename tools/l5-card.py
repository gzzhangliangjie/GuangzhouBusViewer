# -*- coding: utf-8 -*-
"""5号线卡片: Tim图按组提取(_x35_) + 站位真值表(圆+序号严格对位)"""
import sys, math, os, time, re
import xml.etree.ElementTree as ET

NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import build_card as B
from verify_card import run_gates

COLOR = '#E53935'

# ===== 走廊: _x35_ 组(排除 display:none 的 st46 残段) =====
src = open(os.path.join(ROOT, 'assets/gz-tim-2026.svg'), encoding='utf-8').read()
gm = re.search(r'<g\b[^>]*id="_x35_"[^>]*>', src)
start = gm.end(); depth = 1; j = start
while depth > 0:
    no = src.find('<g', j); nc = src.find('</g>', j)
    if no != -1 and no < nc: depth += 1; j = no + 2
    else: depth -= 1; j = nc + 4
inner = src[start:j]
segs = []
for lm in re.finditer(r'<line\b[^>]*/>', inner):
    at = dict(re.findall(r'([\w-]+)="([^"]*)"', lm.group(0)))
    if at.get('class') == 'st46':  # display:none 残段
        continue
    segs.append((float(at['x1']), float(at['y1']), float(at['x2']), float(at['y2'])))
# 圆角path并进走廊(端点即line端点, 直弦代替弧) — 否则G3断连
for pm in re.finditer(r'<path\b[^>]*/>', inner):
    at = dict(re.findall(r'([\w-]+)="([^"]*)"', pm.group(0)))
    if at.get('class') == 'st46':
        continue
    d = at.get('d', '')
    if not d.startswith('M'):
        continue
    pts = B.sample_d(d)  # 状态机解析(d数字有连写, 正则必炸)
    if len(pts) >= 2:
        segs.append((pts[0][0], pts[0][1], pts[-1][0], pts[-1][1]))

# ===== 站位真值表(官方案号序; 真=原SVG圆位, 补=走廊插值) =====
STS = [
    ('滘口',       994.5,  956.2),   # 真R 终点=走廊西端
    ('坦尾',      1066.5,  956.2),   # 真B
    ('中山八',     1111.5,  956.2),   # 补=拐角
    ('西场',      1120.5,  848.2),   # 真R
    ('西村',      1174.5,  839.2),   # 真B
    ('广州火车站', 1300.0,  839.2),   # 补=线上(向西微调避西村162px超距)
    ('小北',      1399.5,  902.2),   # 真R
    ('淘金',      1444.5,  947.2),   # 真R
    ('区庄',      1498.5,  920.2),   # 真B
    ('动物园',     1552.5,  933.8),   # 真R
    ('杨箕',      1552.5, 1010.2),   # 真B
    ('五羊邨',     1579.5, 1064.2),   # 真B
    ('珠江新城',    1660.5, 1064.2),   # 真B
    ('猎德',      1768.5, 1064.2),   # 真R
    ('潭村',      1822.5, 1064.2),   # 真R
    ('员村',      1876.5, 1064.2),   # 真B
    ('科韵路',     1937.2, 1064.2),   # 真B
    ('车陂南',     1984.5, 1064.2),   # 真B
    ('东圃',      2038.5, 1064.2),   # 真R
    ('三溪',      2092.5, 1064.2),   # 真R
    ('鱼珠',      2146.5, 1037.2),   # 真B 对角线上
    ('大沙地',     2200.5, 1010.2),   # 真R
    ('大沙东',     2254.5, 1010.2),   # 真B
    ('文冲',      2299.5, 1010.2),   # 真R
    ('双沙',      2340.0, 1010.2),   # 真R
    ('庙头',      2380.5, 1010.2),   # 真R
    ('夏园',      2398.5, 1019.2),   # 补=东南对角线起点
    ('保盈大道',   2452.5, 1073.2),   # 真R
    ('夏港',      2488.5, 1109.2),   # 真R
    ('黄埔新港',   2524.5, 1145.2),   # 真R 终点=走廊东端
]
N = len(STS)
LD, SD = B.load_metro()
L = LD['5号线']
assert list(L['stations']) == [s[0] for s in STS], '站序与官表不符!'
EN = {nm: SD[nm].get('en', '') for nm, _, _ in STS if nm in SD}
cxy = [(x, y) for _, x, y in STS]

# 站距报告
gaps = [math.hypot(cxy[i+1][0]-cxy[i][0], cxy[i+1][1]-cxy[i][1]) for i in range(N-1)]
med = sorted(gaps)[len(gaps)//2]
cap = max(2.5*min(med, 80), 110.0)
print('站距: 中位%.0f cap%.0f 最大%.0f' % (med, cap, max(gaps)))
for i, g in enumerate(gaps):
    if g > cap or g < 3:
        print('  !! %s->%s %.0fpx' % (STS[i][0], STS[i+1][0], g))

# ===== 组卡(同l6装配) =====
xs = [p[0] for p in cxy]+[s[0] for s in segs]+[s[2] for s in segs]
ys = [p[1] for p in cxy]+[s[1] for s in segs]+[s[3] for s in segs]
x0, x1 = min(xs)-115, max(xs)+65
y0, y1 = min(ys)-95, max(ys)+85

svg = ET.Element('{%s}svg' % NS)
svg.set('viewBox', '%.1f %.1f %.1f %.1f' % (x0, y0, x1-x0, y1-y0))
svg.set('width', str(round(x1-x0))); svg.set('height', str(round(y1-y0)))
bg = ET.SubElement(svg, '{%s}rect' % NS)
bg.set('x', str(x0)); bg.set('y', str(y0))
bg.set('width', str(x1-x0)); bg.set('height', str(y1-y0)); bg.set('fill', '#ffffff')

ST = 'fill:none;stroke:%s;stroke-width:7;stroke-linecap:round' % COLOR
gc = ET.SubElement(svg, '{%s}g' % NS); gc.set('id', '走廊')
for s in segs:
    ln = ET.SubElement(gc, '{%s}line' % NS)
    ln.set('x1', '%.2f' % s[0]); ln.set('y1', '%.2f' % s[1])
    ln.set('x2', '%.2f' % s[2]); ln.set('y2', '%.2f' % s[3])
    ln.set('style', ST)

go = ET.SubElement(svg, '{%s}g' % NS); go.set('id', '站圆')
for (nm, cx, cy), (px, py) in zip(STS, cxy):
    c = ET.SubElement(go, '{%s}circle' % NS)
    c.set('cx', '%.1f' % px); c.set('cy', '%.1f' % py); c.set('r', '4.5')
    c.set('data-nm', nm); c.set('style', 'fill:#FFFFFF;stroke:%s;stroke-width:2' % COLOR)

gb = ET.SubElement(svg, '{%s}g' % NS); gb.set('id', '线路徽标')
gb.append(B.make_badge(COLOR, '5', '号线', 'Line 5', x1-96, y0+36))
for tn in (STS[0][0], STS[-1][0]):
    tx, ty = dict((nm, (x, y)) for nm, x, y in STS)[tn]
    gb.append(B.make_badge(COLOR, '5', '号线', 'Line 5', tx, ty-55, 0.6))

pl = B.place_labels([s[0] for s in STS], cxy, segs, EN)
gl = ET.SubElement(svg, '{%s}g' % NS); gl.set('id', '站名标注')
gl.set('font-family', "'Microsoft YaHei', 'PingFang SC', sans-serif")
for lb in pl:
    zx = (lb['bx0']+lb['bx1'])/2; zy = lb['by0']+11
    t = ET.SubElement(gl, '{%s}text' % NS)
    t.set('x', '%.1f' % zx); t.set('y', '%.1f' % zy)
    t.set('text-anchor', 'middle'); t.set('font-size', '10.5'); t.set('font-weight', '500')
    t.set('fill', '#1a1a1a'); t.text = lb['nm']
    if lb['en']:
        te = ET.SubElement(gl, '{%s}text' % NS)
        te.set('x', '%.1f' % zx); te.set('y', '%.1f' % lb['by1'])
        te.set('text-anchor', 'middle'); te.set('font-size', '5.5'); te.set('fill', '#444444')
        te.text = lb['en']

out = os.path.join(ROOT, 'assets/lines/line-5号线.svg')
ET.ElementTree(svg).write(out, encoding='unicode', xml_declaration=False)

R = run_gates(out, expect_n=N)
print('门禁: %d/%d' % (sum(o for _, _, o, _ in R), len(R)))
for no, nm, o, dt in R:
    if not o:
        print('  %s %s' % (no, dt[:120]))

vb = [float(v) for v in svg.get('viewBox').split()]
W = 400; H = round(W*vb[3]/vb[2])
cb = int(time.time()*1000)
html = ('<!DOCTYPE html><html><head><meta charset="UTF-8">'
        '<style>html,body{margin:0;height:100%;background:#fff;overflow:hidden}'
        'img{position:absolute;left:0;top:0}</style></head><body>'
        '<img id=m src="line-5号线.svg?cb=' + str(cb) + '" width="' + str(W) + '" height="' + str(H) + '"></body></html>')
open(os.path.join(ROOT, 'assets/lines/_verify-l5.html'), 'w', encoding='utf-8').write(html)
print('页面 %dx%d' % (W, H))
