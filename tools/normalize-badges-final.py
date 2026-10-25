# -*- coding: utf-8 -*-
"""终点徽标-文字关系归一(终版): 每枚徽标以data-term/最近焊接终点定归属文字,
保持当前主轴方位, 中心对齐文字(纵向堆叠→x对齐; 横向并排→y对齐), 间隙
纵向4.1(冼村)/横向6.0(万顷沙), 阶梯退让; 全门禁合法, 不合法保留原位上报。"""
import io, os, re, sys, json, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import importlib.util
spec = importlib.util.spec_from_file_location('gen', 'tools/gen-codes-cards.py')
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

F = 'assets/lines/network-全网.codes.svg'
t = open(F, encoding='utf-8').read()
chips, rings, _ = gen.chip_elements(t)
corridors = gen.corridor_segments(t)
badges = gen.badge_elements(t)
zh = {e['nm']: e for e in gen.text_elements(t) if not e['en']}

# 焊接终点→站名(每线)
import xml.etree.ElementTree as ET
NS = '{http://www.w3.org/2000/svg}'
ORDER = ['1号线','2号线','3号线','4号线','5号线','6号线','7号线','8号线','9号线','10号线','11号线','12号线','13号线','14号线','18号线','21号线','22号线','广佛线','APM线']
line_data = {}
for name in ORDER:
    root = ET.parse('assets/lines/line-%s.svg' % name).getroot()
    segs, markers = [], []
    for g in root.findall(NS + 'g'):
        if g.get('id') == '走廊':
            for ln in g.findall(NS + 'line'):
                segs.append((float(ln.get('x1')), float(ln.get('y1')), float(ln.get('x2')), float(ln.get('y2'))))
        elif g.get('id') == '站圆':
            for c in g.findall(NS + 'circle'):
                markers.append((c.get('data-nm'), float(c.get('cx')), float(c.get('cy'))))
    nodes = []
    def weld(p):
        for q in nodes:
            if math.hypot(p[0] - q[0], p[1] - q[1]) <= 6.0:
                return q
        nodes.append(p)
        return p
    wdeg = {}
    for ax, ay, bx, by in segs:
        a = weld((round(ax, 1), round(ay, 1)))
        b = weld((round(bx, 1), round(by, 1)))
        wdeg[a] = wdeg.get(a, 0) + 1
        wdeg[b] = wdeg.get(b, 0) + 1
    ends = [p for p, deg in wdeg.items() if deg == 1]
    stns = []
    for p in ends:
        st = min(markers, key=lambda mk: math.hypot(p[0] - mk[1], p[1] - mk[2]))
        stns.append((p, st))
    line_data[name] = stns

def legal_box(box, self_key):
    if any(gen._gap(box, c) < 0.5 for c in chips + rings):
        return False
    if any(gen.rect_seg_dist(box, s) < 4.5 for s in corridors):
        return False
    if any(gen._gap(box, o['box']) < 1.0 for o in zh.values()):
        return False
    for o in badges:
        if o['key'] == self_key:
            continue
        if gen._gap(box, (o['x'], o['y'], o['w'], o['h'])) < 0.3:
            return False
    return True

moves = []
keeps = []
for b in badges:
    stns = line_data.get(b['key'], [])
    if not stns:
        continue
    bc = (b['x'] + b['w'] / 2, b['y'] + b['h'] / 2)
    end, st = min(stns, key=lambda e2: math.hypot(bc[0] - e2[0][0], bc[1] - e2[0][1]))
    nm = st[0]
    te = zh.get(nm)
    if not te:
        continue
    tb = te['box']
    tcx, tcy = tb[0] + tb[2] / 2, tb[1] + tb[3] / 2
    bdx, bdy = bc[0] - tcx, bc[1] - tcy
    if abs(bdx) >= abs(bdy):
        axis, side = 0, ('r' if bdx > 0 else 'l')
        cur = abs(bdx) - b['w'] / 2 - tb[2] / 2
    else:
        axis, side = 1, ('b' if bdy > 0 else 'a')
        cur = abs(bdy) - b['h'] / 2 - tb[3] / 2
    target = 4.1 if axis == 1 else 6.0
    if abs(cur - target) <= 0.4:
        continue
    sgn = 1 if cur > 0 else -1
    placed = None
    for g in (target, target - 1.0, target + 1.0, target - 2.0, target + 2.0, target - 3.0, target + 3.0):
        if g <= 0.5:
            break
        if axis == 0:
            nb = (tcx + sgn * (tb[2] / 2 + g + b['w'] / 2), tcy, b['w'], b['h'])
        else:
            nb = (tcx, tcy + sgn * (tb[3] / 2 + g + b['h'] / 2), b['w'], b['h'])
        if legal_box(nb, b['key']):
            placed = (nb[0], nb[1], g)
            break
    if placed:
        nx, ny, g = placed
        new_tr = 'translate(%.2f %.2f) scale(%.4f)' % (nx, ny, b['scale'])
        moves.append((b, new_tr, nm, axis, cur, g))
    else:
        keeps.append((b['key'], nm, axis, cur))

print('归一化 %d 枚:' % len(moves))
for b, new_tr, nm, axis, cur, g in moves:
    print('  %-6s %-8s %s侧 gap%.1f -> %.1f' % (b['key'], nm, '纵' if axis else '横', cur, g))
print('保留 %d:' % len(keeps))
for k in keeps:
    print('  ', k)

for b, new_tr, nm, axis, cur, g in moves:
    pat = re.compile(r'<g data-badge="header"[^>]*transform="' + re.escape(b['tr_attr']) + r'"[^>]*>(.*?)</g>', re.S)
    mm = pat.search(t)
    assert mm, b['key']
    t = t[:mm.start()] + mm.group(0).replace(b['tr_attr'], new_tr) + t[mm.end():]
open(F, 'w', encoding='utf-8').write(t)
import xml.etree.ElementTree as ET
ET.fromstring(t)
print('codes SVG 已更新, XML OK')
