# -*- coding: utf-8 -*-
"""终点文字/徽标 权威判定(只读, 两阶段之阶段1):
宽度一律 gen.text_box/part_w(渲染同源), 不用启发式。
理想位: 文字=站钉交叉轴居中且贴胶囊组3.5; 徽标=贴文字盒沿轴5、交叉轴居中于文字。
违规 = 现位不合规 且 理想位全门禁合法(胶囊0.5/走廊4.5/他文字1.0/他徽标0.3/贴牌9)。
理想位不合法 = 合规解(斜位/远位), 不列。
输出: data/_term-violations.json + 控制台清单。
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
    tr = re.search(r'translate\(([-\d.]+) ([-\d.]+)\)', mm.group(0))
    badges.append({'ln': ln, 'x': float(tr.group(1)), 'y': float(tr.group(2)),
                   'w': bsz[ln][0] * float(mm.group(2)), 'h': bsz[ln][1] * float(mm.group(2)),
                   'tr': mm.group(0).split('transform="')[1].split('"')[0]})

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

# 站钉: 底图站圆/换乘胶囊中点
_net = open('assets/lines/network-全网.svg', encoding='utf-8').read()
pins = {}
for mm in re.finditer(r'<circle cx="([-\d.]+)" cy="([-\d.]+)"[^>]*data-nm="([^"]+)"', _net):
    pins[mm.group(3)] = (float(mm.group(1)), float(mm.group(2)))
for mm in re.finditer(r'<line[^>]*data-nm="([^"]+)"[^>]*/>', _net):
    nm = mm.group(1)
    if nm in pins:
        continue
    c1 = re.search(r'x1="([-\d.]+)" y1="([-\d.]+)"', mm.group(0))
    c2 = re.search(r'x2="([-\d.]+)" y2="([-\d.]+)"', mm.group(0))
    if c1 and c2:
        pins[nm] = ((float(c1.group(1)) + float(c2.group(1))) / 2, (float(c1.group(2)) + float(c2.group(2))) / 2)

# 徽标→焊接终点→站名(可靠映射)
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

others = [o['box'] for o in texts.values()]

def legal_box(box):
    if any(gen._gap(box, c) < 0.5 for c in chips + rings):
        return False
    if any(gen.rect_seg_dist(box, s) < 4.5 for s in corridors):
        return False
    if any(gen._gap(box, o) < 1.0 for o in others):
        return False
    if any(gen._gap(box, (b['x'], b['y'], b['w'], b['h'])) < 0.3 for b in badges):
        return False
    return True

GAP = 6.0
viol = []
print('=== 判定(理想位合法而未放置=违规) ===')
for b in badges:
    stns = line_data.get(b['ln'], [])
    if not stns:
        continue
    bc = (b['x'] + b['w'] / 2, b['y'] + b['h'] / 2)
    end, st = min(stns, key=lambda e: math.hypot(bc[0] - e[0][0], bc[1] - e[0][1]))
    nm = st[0]
    o = texts.get(nm)
    pin = pins.get(nm)
    if not o or not pin:
        continue
    box = o['box']
    tcx, tcy = box[0] + box[2] / 2, box[1] + box[3] / 2
    # R6文字居中: 交叉轴偏差>3 且 吸附位合法 => 违规
    dx, dy = tcx - pin[0], tcy - pin[1]
    t_viol = None
    if abs(dx) >= abs(dy):
        t_off = abs(dy)
        t_cand = (box[0], pin[1] - box[3] / 2, box[2], box[3])
    else:
        t_off = abs(dx)
        t_cand = (pin[0] - box[2] / 2, box[1], box[2], box[3])
    others_wo = [x['box'] for k2, x in texts.items() if k2 != nm]
    def legal_box_wo(bx):
        if any(gen._gap(bx, c) < 0.5 for c in chips + rings):
            return False
        if any(gen.rect_seg_dist(bx, s) < 4.5 for s in corridors):
            return False
        if any(gen._gap(bx, ob) < 1.0 for ob in others_wo):
            return False
        if any(gen._gap(bx, (b2['x'], b2['y'], b2['w'], b2['h'])) < 0.3 for b2 in badges):
            return False
        return True
    if t_off > 3.0 and legal_box_wo(t_cand):
        t_viol = ('能居中未居中', t_off, t_cand)
    # 徽标-文字: 间隙/交叉轴
    bdx, bdy = bc[0] - tcx, bc[1] - tcy
    if abs(bdx) >= abs(bdy):
        side = 'r' if bdx > 0 else 'l'
        cur_gap = abs(bdx) - b['w'] / 2 - box[2] / 2
        b_off = abs(bdy)
    else:
        side = 'b' if bdy > 0 else 'a'
        cur_gap = abs(bdy) - b['h'] / 2 - box[3] / 2
        b_off = abs(bdx)
    # 理想位: 同侧(与文字相对站钉方向一致优先; 否则现侧) 贴5+交叉对齐
    cands = []
    if side == 'r':
        cands.append((tcx + box[2] / 2 + GAP, tcy))
    elif side == 'l':
        cands.append((tcx - box[2] / 2 - GAP, tcy))
    elif side == 'b':
        cands.append((tcx, tcy + box[3] / 2 + GAP))
    else:
        cands.append((tcx, tcy - box[3] / 2 - GAP))
    # 备选: 文字相对站钉的外侧方向(规范: 徽标在文字外侧=远离站体)
    pdx, pdy = tcx - pin[0], tcy - pin[1]
    if abs(pdx) >= abs(pdy):
        cands.append((tcx + (GAP + b['w'] / 2 + box[2] / 2) * (1 if pdx > 0 else -1), tcy))
    else:
        cands.append((tcx, tcy + (GAP + b['h'] / 2 + box[3] / 2) * (1 if pdy > 0 else -1)))
    b_viol = None
    if abs(cur_gap - GAP) > 2.5 or b_off > 3.0:
        for cc in cands:
            cbox = (cc[0] - b['w'] / 2, cc[1] - b['h'] / 2, b['w'], b['h'])
            if legal_box(cbox):
                b_viol = ('间隙%.1f/交叉%.1f不合规' % (cur_gap, b_off), cc, cbox)
                break
    if t_viol or b_viol:
        viol.append({'ln': b['ln'], 'nm': nm, 'text_viol': t_viol and (t_viol[0], round(t_viol[1], 1)),
                     'badge_viol': b_viol and (b_viol[0], round(b_viol[1][0], 2), round(b_viol[1][1], 2)),
                     'text_cand': t_viol and t_viol[2], 'badge_cand': b_viol and b_viol[2],
                     'badge_tr': b['tr']})
        tv = t_viol[0] if t_viol else '-'
        bv = b_viol[0] if b_viol else '-'
        print('%-6s %-8s 文字:%s 徽标:%s' % (b['ln'], nm, tv, bv))

json.dump(viol, open('data/_term-violations.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print()
print('违规总数: %d' % len(viol))
print('清单已存 data/_term-violations.json')
