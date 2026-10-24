# -*- coding: utf-8 -*-
# 徽标-文字 归一化(可靠映射版): 徽标→本线焊接终点(最近)→终点站→终点文字;
# 徽标 = 文字盒外侧间隙统一5pt + 交叉轴居中于文字中心; 合法性阶梯(5/8/12/16/20+换侧);
# 文字不动(交叉轴已达标)。输出: 徽标transform更新清单。
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
                   'w': bsz[ln][0] * float(mm.group(2)), 'h': bsz[ln][1] * float(mm.group(2))})

d = json.load(open('data/codes-final-pins.json', encoding='utf-8'))
texts = {}
for mm in re.finditer(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*font-size="([\d.]+)"[^>]*>([^<]+)</text>', d['labels_inner']):
    nm = mm.group(4)
    if nm.isascii():
        continue
    fs = float(mm.group(3))
    w = sum(fs if ord(ch) > 0x2E80 else 0.56 * fs for ch in nm)
    texts[nm] = (float(mm.group(1)), float(mm.group(2)) - fs * 0.92 + fs * 1.12 / 2, w, fs * 1.12, fs)

# 焊接终点(带站名)
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
            min(math.hypot(p[0] - m[1], p[1] - m[2]) for m in markers) < 30]
    stns = []
    for p in ends:
        st = min(markers, key=lambda mk: math.hypot(p[0] - mk[1], p[1] - mk[2]))
        stns.append((p, st))
    line_data[name] = stns

UPD = {}
for b in badges:
    stns = line_data.get(b['ln'], [])
    if not stns:
        continue
    bc = (b['x'] + b['w'] / 2, b['y'] + b['h'] / 2)
    end, st = min(stns, key=lambda e: math.hypot(bc[0] - e[0][0], bc[1] - e[0][1]))
    nm = st[0]
    tx = texts.get(nm)
    if not tx:
        continue
    tcx, tcy, tw, th, tfs = tx
    bdx, bdy = bc[0] - tcx, bc[1] - tcy
    if abs(bdx) >= abs(bdy):
        side, sgn = ('r' if bdx > 0 else 'l'), (1 if bdx > 0 else -1)
        cur_gap = abs(bdx) - b['w'] / 2 - tw / 2
    else:
        side, sgn = ('b' if bdy > 0 else 'a'), (1 if bdy > 0 else -1)
        cur_gap = abs(bdy) - b['h'] / 2 - th / 2
    UPD.setdefault(b['ln'], []).append({'b': b, 'nm': nm, 'side': side, 'sgn': sgn, 'cur': cur_gap, 'tc': (tcx, tcy, tw, th)})

print('=== 现状间隙(徽标盒边-文字盒边, 目标统一5) ===')
for ln, lst in UPD.items():
    for e in lst:
        mark = '<<' if abs(e['cur'] - 5.0) > 2.5 else ''
        print('%-6s %-8s %s侧 间隙%.1f %s' % (ln, e['nm'], {'r': '右', 'l': '左', 'a': '上', 'b': '下'}[e['side']], e['cur'], mark))
json.dump([{'ln': ln, 'nm': e['nm'], 'side': e['side'], 'cur': e['cur']}
           for ln, lst in UPD.items() for e in lst],
          open('data/_badge-text-state.tmp.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
