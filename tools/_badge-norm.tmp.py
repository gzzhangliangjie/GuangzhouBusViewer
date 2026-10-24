# -*- coding: utf-8 -*-
"""徽标-文字 全量归一化: 全部41枚(除环线11号线), 目标=沿轴间隙5 + 交叉轴对齐文字中心。
阶梯: 沿当前侧轴 gap 5为主, 不合法试4/6/3/7/2/8/10; 仍不合法换对侧再试; 全不合法保留上报。
文字不动(已居中)。输出 transform 更新并写 codes/底图/锚表三处。
"""
import io, sys, re, json, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'tools')
import importlib.util
spec = importlib.util.spec_from_file_location('gen', 'tools/gen-codes-cards.py')
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

t = open('assets/lines/network-全网.codes.svg', encoding='utf-8').read()
corridors = [tuple(float(m.group(k)) for k in (1, 2, 3, 4))
             for m in re.finditer(r'<line x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)"', t)]
chips, rings = [], []
m = re.search(r'<g id="编号牌"[^>]*>(.*?)</g>', t, re.S)
for r in re.finditer(r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)"([^>]*)stroke="(#[0-9A-Fa-f]{6})"', m.group(1)):
    x, y, w, h = (float(r.group(k)) for k in (1, 2, 3, 4))
    (rings if 'data-ring' in r.group(5) else chips).append((x, y, w, h))
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
    tr_full = mm.group(0).split('transform="')[1].split('"')[0]
    tr = re.search(r'translate\(([-\d.]+) ([-\d.]+)\)', mm.group(0))
    badges.append({'ln': ln, 'key': key, 'x': float(tr.group(1)), 'y': float(tr.group(2)),
                   'w': bsz[ln][0] * float(mm.group(2)), 'h': bsz[ln][1] * float(mm.group(2)),
                   'tr': tr_full})

d = json.load(open('data/codes-final-pins.json', encoding='utf-8'))
texts = {}
for mm in re.finditer(r'<text ([^>]*)>([^<]+)</text>', d['labels_inner']):
    at, nm = mm.group(1), mm.group(2)
    if nm.isascii():
        continue
    x = float(re.search(r'x="([-\d.]+)"', at).group(1))
    y = float(re.search(r'y="([-\d.]+)"', at).group(1))
    fs = float(re.search(r'font-size="([\d.]+)"', at).group(1))
    texts[nm] = {'x': x, 'y': y, 'fs': fs, 'box': gen.text_box({'x': x, 'y': y, 'fs': fs, 'content': nm})}

# 焊接终点→站名
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

others = [(o['box'][0], o['box'][1], o['box'][2], o['box'][3], k2) for k2, o in texts.items()]

def legal_box(box, self_tr):
    if any(gen._gap(box, c) < 0.5 for c in chips + rings):
        return False
    if any(gen.rect_seg_dist(box, s) < 4.5 for s in corridors):
        return False
    if any(gen._gap(box, o[:4]) < 1.0 for o in others):
        return False
    for b2 in badges:
        if b2['tr'] == self_tr:
            continue
        if gen._gap(box, (b2['x'], b2['y'], b2['w'], b2['h'])) < 0.3:
            return False
    return True

GAP_T = 5.0
moves = []
keep = []
for b in badges:
    stns = line_data.get(b['ln'], [])
    if not stns:   # 环线11号线
        keep.append((b['key'], '-', '环线跳过'))
        continue
    bc = (b['x'] + b['w'] / 2, b['y'] + b['h'] / 2)
    end, st = min(stns, key=lambda e: math.hypot(bc[0] - e[0][0], bc[1] - e[0][1]))
    nm = st[0]
    o = texts.get(nm)
    if not o:
        keep.append((b['key'], nm, '缺文字'))
        continue
    box = o['box']
    tcx, tcy = box[0] + box[2] / 2, box[1] + box[3] / 2
    bdx, bdy = bc[0] - tcx, bc[1] - tcy
    if abs(bdx) >= abs(bdy):
        sgn = 1 if bdx > 0 else -1
        cand = (tcx + sgn * (box[2] / 2 + GAP_T + b['w'] / 2), tcy)
    else:
        sgn = 1 if bdy > 0 else -1
        cand = (tcx, tcy + sgn * (box[3] / 2 + GAP_T + b['h'] / 2))
    cbox = (cand[0] - b['w'] / 2, cand[1] - b['h'] / 2, b['w'], b['h'])
    if legal_box(cbox, b['tr']):
        if abs(math.hypot(cand[0] - bc[0], cand[1] - bc[1])) > 0.3:
            moves.append((b['key'], nm, (b['x'], b['y']), (cand[0] - b['w'] / 2, cand[1] - b['h'] / 2), 'gap5'))
        else:
            keep.append((b['key'], nm, '已在理想位'))
        continue
    # 阶梯: 4/6/3/7/2/8/10 -> 对侧5 -> 换轴5
    placed = None
    for g2 in (4.0, 6.0, 3.0, 7.0, 2.0, 8.0, 10.0):
        if abs(bdx) >= abs(bdy):
            c2 = (tcx + sgn * (box[2] / 2 + g2 + b['w'] / 2), tcy)
        else:
            c2 = (tcx, tcy + sgn * (box[3] / 2 + g2 + b['h'] / 2))
        c2box = (c2[0] - b['w'] / 2, c2[1] - b['h'] / 2, b['w'], b['h'])
        if legal_box(c2box, b['tr']):
            placed = (c2, c2box, 'gap%g' % g2)
            break
    if not placed:
        os_ = -sgn if abs(bdx) >= abs(bdy) else -0
        if abs(bdx) >= abs(bdy):
            c2 = (tcx - sgn * (box[2] / 2 + GAP_T + b['w'] / 2), tcy)
        else:
            c2 = (tcx, tcy - sgn * (box[3] / 2 + GAP_T + b['h'] / 2))
        c2box = (c2[0] - b['w'] / 2, c2[1] - b['h'] / 2, b['w'], b['h'])
        if legal_box(c2box, b['tr']):
            placed = (c2, c2box, '对侧gap5')
        else:
            keep.append((b['key'], nm, '阶梯+对侧均不合法'))
            continue
    moves.append((b['key'], nm, (b['x'], b['y']), (placed[0][0] - b['w'] / 2, placed[0][1] - b['h'] / 2), placed[2]))

print('归一化 %d 枚:' % len(moves))
for key, nm, old, new, how in moves:
    print('  %-4s %-8s (%g,%g) -> (%g,%g) [%s]' % (key, nm, old[0], old[1], new[0], new[1], how))
print('保留 %d:' % len(keep))
for k in keep:
    print('  ', k)
json.dump([{'key': k, 'nm': nm, 'old': old, 'new': new, 'how': how}
           for k, nm, old, new, how in moves],
          open('data/_badge-norm-moves.tmp.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
