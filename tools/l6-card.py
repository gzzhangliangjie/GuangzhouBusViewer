# -*- coding: utf-8 -*-
"""6号线卡片: Tim图按组提取(_x36_) + 站位真值表(圆色×官方案号对位)"""
import sys, math, os, time, re
import xml.etree.ElementTree as ET

NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import build_card as B
from verify_card import run_gates

COLOR = '#8E24AA'

src = open(os.path.join(ROOT, 'assets/gz-tim-2026.svg'), encoding='utf-8').read()
gm = re.search(r'<g\b[^>]*id="_x36_"[^>]*>', src)
start = gm.end(); depth = 1; j = start
while depth > 0:
    no = src.find('<g', j); nc = src.find('</g>', j)
    if no != -1 and no < nc: depth += 1; j = no + 2
    else: depth -= 1; j = nc + 4
inner = src[start:j]
segs = []
for lm in re.finditer(r'<line\b[^>]*/>', inner):
    at = dict(re.findall(r'([\w-]+)="([^"]*)"', lm.group(0)))
    segs.append((float(at['x1']), float(at['y1']), float(at['x2']), float(at['y2'])))
for pm in re.finditer(r'<path\b[^>]*/>', inner):
    at = dict(re.findall(r'([\w-]+)="([^"]*)"', pm.group(0)))
    d = at.get('d', '')
    if not d.startswith('M'):
        continue
    pts = B.sample_d(d)
    if len(pts) >= 2:
        segs.append((pts[0][0], pts[0][1], pts[-1][0], pts[-1][1]))

# ===== 站位真值表 =====
STS = [
    ('浔峰岗',     1066.5,  740.2),   # 真B 终点=西竖线顶端
    ('横沙',      1066.5,  794.2),   # 真P
    ('沙贝',      1066.5,  848.2),   # 真P
    ('河沙',      1066.5,  902.2),   # 真P
    ('坦尾',      1066.5,  956.2),   # 真B(5换乘)
    ('如意坊',     1109.0, 1021.0),   # 补=长对角线中段
    ('黄沙',      1174.5, 1064.2),   # 真B(1换乘)
    ('文化公园',    1228.5, 1064.2),   # 真B(8换乘)
    ('一德路',     1282.5, 1064.2),   # 真P
    ('海珠广场',    1336.5, 1064.2),   # 真B(2换乘)
    ('北京路',     1390.5, 1064.2),   # 真P
    ('团一大广场',   1444.5, 1064.2),   # 真P
    ('东湖',      1498.5, 1032.0),   # 补=竖线上
    ('东山口',     1498.5, 1010.2),   # 真B(1换乘)
    ('区庄',      1498.5,  920.2),   # 真B(5换乘)
    ('黄花岗',     1521.0,  882.0),   # 真P
    ('沙河顶',     1566.0,  880.4),   # 真P(吸附到对角线)
    ('沙河',      1606.5,  848.2),   # 真B(11换乘)
    ('天平架',     1633.5,  821.2),   # 真P
    ('燕塘',      1660.5,  796.5),   # 真B(3换乘)
    ('天河客运站',   1707.0,  794.2),   # 补=794横线上
    ('长湴',      1753.0,  794.2),   # 补=794横线尾
    ('植物园',     1788.0,  768.0),   # 补=上行对角线
    ('龙洞',      1831.5,  740.2),   # 真P
    ('柯木塱',     1878.8,  740.2),   # 真P
    ('高塘石',     1923.8,  740.2),   # 真圆(B)
    ('黄陂',      1975.5,  740.2),   # 真P
    ('金峰',      2020.5,  740.2),   # 真P
    ('暹岗',      2065.5,  740.2),   # 真P
    ('苏元',      2110.5,  740.2),   # 真P
    ('萝岗',      2155.5,  740.2),   # 真P
    ('香雪',      2200.5,  740.2),   # 真圆 终点
]
N = len(STS)
STS = STS[::-1]  # 文档序=数据表方向(香雪→浔峰岗), V1 按此校验
LD, SD = B.load_metro()
L = LD['6号线']
lst = list(L['stations'])
assert [s[0] for s in STS] in (lst, lst[::-1]), '站序与数据表不符(任一方向)'
EN = {nm: SD[nm].get('en', '') for nm, _, _ in STS if nm in SD}
pos = {nm: (x, y) for nm, x, y in STS}
cxy = [pos[s[0]] for s in STS]

# 走廊吸附(G2): 非拐角真圆偏差<2px, 补点吸附到走廊
def snap(px, py):
    best, bd = (px, py), 1e18
    for s in segs:
        x1, y1, x2, y2 = s
        dx, dy = x2-x1, y2-y1; L2 = dx*dx+dy*dy
        if L2 < 1e-9: continue
        t = max(0, min(1, ((px-x1)*dx+(py-y1)*dy)/L2))
        d = math.hypot(x1+t*dx-px, y1+t*dy-py)
        if d < bd: bd, best = d, (x1+t*dx, y1+t*dy)
    return best if bd < 15 else (px, py)
cxy = [snap(x, y) for x, y in cxy]
STS = [(nm, p[0], p[1]) for (nm, _, _), p in zip(STS, cxy)]
pos = {nm: (x, y) for nm, x, y in STS}
cxy = [pos[s[0]] for s in STS]

# G3: 东端走廊裁进香雪圆(原H740延到2308.5, 属其他线画布)
def trim(seg_list):
    out = []
    for s in seg_list:
        x1, y1, x2, y2 = s
        for k, (px, py) in enumerate(((x1, y1), (x2, y2))):
            if math.hypot(px-2308.5, py-740.2) < 0.5 and px > 2200:
                nx = pos['香雪'][0] + 6
                if k == 1: x2 = nx
                else: x1 = nx
        out.append((x1, y1, x2, y2))
    return out
segs = trim(segs)

gaps = [math.hypot(cxy[i+1][0]-cxy[i][0], cxy[i+1][1]-cxy[i][1]) for i in range(N-1)]
med = sorted(gaps)[len(gaps)//2]
cap = max(2.5*min(med, 80), 110.0)
print('站距: 中位%.0f cap%.0f 最大%.0f' % (med, cap, max(gaps)))
for i, g in enumerate(gaps):
    if g > cap or g < 3:
        print('  !! %s->%s %.0fpx' % (STS[i][0], STS[i+1][0], g))

# ===== 组卡 =====
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
for nm, cx, cy in STS:
    c = ET.SubElement(go, '{%s}circle' % NS)
    c.set('cx', '%.1f' % cx); c.set('cy', '%.1f' % cy); c.set('r', '4.5')
    c.set('data-nm', nm); c.set('style', 'fill:#FFFFFF;stroke:%s;stroke-width:2' % COLOR)

gb = ET.SubElement(svg, '{%s}g' % NS); gb.set('id', '线路徽标')
gb.append(B.make_badge(COLOR, '6', '号线', 'Line 6', x1-96, y0+36))
for tn in (STS[0][0], STS[-1][0]):
    tx, ty = pos[tn]
    gb.append(B.make_badge(COLOR, '6', '号线', 'Line 6', tx, ty-55, 0.6))

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

out = os.path.join(ROOT, 'assets/lines/line-6号线.svg')
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
        '<img id=m src="line-6号线.svg?cb=' + str(cb) + '" width="' + str(W) + '" height="' + str(H) + '"></body></html>')
open(os.path.join(ROOT, 'assets/lines/_verify-l6.html'), 'w', encoding='utf-8').write(html)
print('页面 %dx%d' % (W, H))
