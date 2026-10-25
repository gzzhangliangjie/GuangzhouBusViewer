# -*- coding: utf-8 -*-
"""闭环归一化: 从当前SVG实测 -> 算目标 -> 直接应用 -> 自检, 一个脚本完成。
排除: 广州南站(离群)、西塱/广州东站/番禺广场(枢纽合规解)、11号线(环线)。"""
import io, sys, re, json, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'tools')
import importlib.util
spec = importlib.util.spec_from_file_location('gen', 'tools/gen-codes-cards.py')
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

EXCLUDE_NM = {'广州南站', '西塱', '广州东站', '番禺广场'}
GAP = 5.0

def build(t):
    corridors = [tuple(float(m.group(k)) for k in (1, 2, 3, 4))
                 for m in re.finditer(r'<line x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)"', t)]
    chips, rings = [], []
    m = re.search(r'<g id="编号牌"[^>]*>(.*?)</g>', t, re.S)
    for r in re.finditer(r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)"([^>]*)stroke="(#[0-9A-Fa-f]{6})"', m.group(1)):
        x, y, w, h = (float(r.group(k)) for k in (1, 2, 3, 4))
        (rings if 'data-ring' in r.group(5) else chips).append((x, y, w, h))
    return corridors, chips, rings

t = open('assets/lines/network-全网.codes.svg', encoding='utf-8').read()
corridors, chips, rings = build(t)
LNAMES = {'1号线','2号线','3号线','4号线','5号线','6号线','7号线','8号线','9号线','10号线',
          '11号线','12号线','13号线','14号线','18号线','21号线','22号线','广佛线','APM线'}
K2L = {'GF': '广佛线', 'APM': 'APM线'}
bsz, badges = {}, []
for mm in re.finditer(r'<g data-badge="header" transform="translate\([-\d.]+ ([-\d.]+)\) scale\(([\d.]+)\)"[^>]*>(.*?)</g>', t, re.S):
    ts = re.findall(r'>([^<>]+)</text>', mm.group(3))
    key = ts[0].strip() if ts else '?'
    ln = key if key in LNAMES else (K2L.get(key) or (key + '号线' if key.isdigit() else '?'))
    if ln not in bsz:
        src = open('assets/lines/line-%s.svg' % ln, encoding='utf-8').read()
        bm = re.search(r'<g data-badge="header"[^>]*>(.*?)</g>', src, re.S)
        rr = re.search(r'width="([\d.]+)" height="([\d.]+)"', bm.group(1))
        bsz[ln] = (float(rr.group(1)), float(rr.group(2)))
    tr = re.search(r'translate\(([-\d.]+) ([-\d.]+)\)', mm.group(0))
    badges.append({'ln': ln, 'key': key, 'x': float(tr.group(1)), 'y': float(tr.group(2)),
                   'w': bsz[ln][0] * float(mm.group(2)), 'h': bsz[ln][1] * float(mm.group(2))})

d = json.load(open('data/codes-final-pins.json', encoding='utf-8'))
texts = {}
for mm in re.finditer(r'<text ([^>]*)>([^<]+)</text>', d['labels_inner']):
    at, nm = mm.group(1), mm.group(2)
    if nm.isascii():
        continue
    x = float(re.search(r'x="([-\d.]+)"', at).group(1))
    y = float(re.search(r'y="([-\d.]+)"', at).group(1))
    fs = float(re.search(r'font-size="([\d.]+)"', at).group(1))
    texts[nm] = (x, y, fs, gen.text_box({'x': x, 'y': y, 'fs': fs, 'content': nm}))

import xml.etree.ElementTree as ET
NS = 'http://www.w3.org/2000/svg'
Q = lambda t2: '{%s}%s' % (NS, t2)
ORDER = ['1号线','2号线','3号线','4号线','5号线','6号线','7号线','8号线','9号线','10号线','11号线','12号线','13号线','14号线','18号线','21号线','22号线','广佛线','APM线']
line_data = {}
for name in ORDER:
    root = ET.parse('assets/lines/line-%s.svg' % name).getroot()
    segs, markers = [], []
    for g in root.findall(Q('g')):
        if g.get('id') == '走廊':
            for ln in g.findall(Q('line')):
                segs.append((float(ln.get('x1')), float(ln.get('y1')), float(ln.get('x2')), float(ln.get('y2'))))
        elif g.get('id') == '站圆':
            for c in g.findall(Q('circle')):
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

    def seg_interior(p):
        for ax, ay, bx, by in segs:
            dd = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5 or 1.0
            tt = max(0.0, min(1.0, ((p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)) / dd / dd))
            if 0.05 < tt < 0.95 and math.hypot(p[0] - ax - tt * (bx - ax), p[1] - ay - tt * (by - ay)) < 0.75:
                return True
        return False
    ends = [p for p, deg in wdeg.items()
            if deg == 1 and not seg_interior(p) and
            min(math.hypot(p[0] - mk[1], p[1] - mk[2]) for mk in markers) < 30]
    stns = []
    for p in ends:
        st = min(markers, key=lambda mk: math.hypot(p[0] - mk[1], p[1] - mk[2]))
        stns.append((p, st))
    line_data[name] = stns

others = [(o[3][0], o[3][1], o[3][2], o[3][3], k2) for k2, o in texts.items()]

def legal_box(box):
    if any(gen._gap(box, c) < 0.5 for c in chips + rings):
        return False
    if any(gen.rect_seg_dist(box, s) < 4.5 for s in corridors):
        return False
    if any(gen._gap(box, o[:4]) < 1.0 for o in others):
        return False
    if any(gen._gap(box, (b['x'], b['y'], b['w'], b['h'])) < 0.3 for b in badges):
        return False
    return True

applied = 0
skipped = []
for b in badges:
    if b['key'] == '11':
        continue
    stns = line_data.get(b['ln'], [])
    if not stns:
        continue
    bc = (b['x'] + b['w'] / 2, b['y'] + b['h'] / 2)
    end, st = min(stns, key=lambda e: math.hypot(bc[0] - e[0][0], bc[1] - e[0][1]))
    nm = st[0]
    if nm in EXCLUDE_NM:
        skipped.append((b['key'], nm, '排除清单'))
        continue
    o = texts.get(nm)
    if not o:
        continue
    tbox = o[3]
    tcx, tcy = tbox[0] + tbox[2] / 2, tbox[1] + tbox[3] / 2
    bdx, bdy = bc[0] - tcx, bc[1] - tcy
    cands = []
    if abs(bdx) >= abs(bdy):
        sgn = 1 if bdx > 0 else -1
        for g in (GAP, 4.0, 6.0, 3.0, 7.0, 2.0, 8.0, 10.0):
            cands.append(((tcx + sgn * (tbox[2] / 2 + g + b['w'] / 2), tcy), 'gap%g' % g))
        cands.append(((tcx - sgn * (tbox[2] / 2 + GAP + b['w'] / 2), tcy), '对侧'))
    else:
        sgn = 1 if bdy > 0 else -1
        for g in (GAP, 4.0, 6.0, 3.0, 7.0, 2.0, 8.0, 10.0):
            cands.append(((tcx, tcy + sgn * (tbox[3] / 2 + g + b['h'] / 2)), 'gap%g' % g))
        cands.append(((tcx, tcy - sgn * (tbox[3] / 2 + GAP + b['h'] / 2)), '对侧'))
    for cc, how in cands:
        cbox = (cc[0] - b['w'] / 2, cc[1] - b['h'] / 2, b['w'], b['h'])
        dd = math.hypot(cc[0] - bc[0], cc[1] - bc[1])
        if dd <= 0.3:
            applied += 0
            break
        if legal_box(cbox):
            old_tr = 'translate(%.2f %.2f) scale(%s)' % (b['x'], b['y'], ('%.4f' % (b['w'] / 80.0)).rstrip('0').rstrip('.'))
            sc_m = re.search(r'scale\(([\d.]+)\)', '')  # 实际scale从key对应badge取
            # 保留原scale: 从当前badge w/80 反推
            sc = ('%.4f' % (b['w'] / 80.0)).rstrip('0').rstrip('.')
            new_tr = 'translate(%.2f %.2f) scale(%s)' % (cc[0], cc[1], sc)
            if old_tr != new_tr and old_tr in t:
                t = t.replace(old_tr, new_tr)
                applied += 1
                print('%-4s %-8s -> (%g,%g) [%s]' % (b['key'], nm, cc[0], cc[1], how))
            break
    else:
        skipped.append((b['key'], nm, '阶梯+对侧均不合法'))

open('assets/lines/network-全网.codes.svg', 'w', encoding='utf-8').write(t)
print('应用:', applied, ' 跳过:', skipped)
