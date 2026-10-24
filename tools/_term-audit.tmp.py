# -*- coding: utf-8 -*-
# 终点文字/徽标 全量审计+归一化:
#   文字: 交叉轴居中于站钉(左右排布y=站钉y; 上下排布x=站钉x)
#   徽标: 与终点文字 交叉轴居中 + 沿轴间隙统一5pt(文字盒边->徽标盒边)
#   合法性: 胶囊/环0.5、走廊4.5、其他文字1.0、他徽标0.3; 理想位不合法则原位保留并上报
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
li = d['labels_inner']
texts = {}
for mm in re.finditer(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*font-size="([\d.]+)"[^>]*>([^<]+)</text>', li):
    nm = mm.group(4)
    if nm.isascii():
        continue
    fs = float(mm.group(3))
    w = sum(fs if ord(ch) > 0x2E80 else 0.56 * fs for ch in nm)
    texts[nm] = {'x': float(mm.group(1)), 'by': float(mm.group(2)), 'w': w, 'fs': fs,
                 'box': (float(mm.group(1)) - w / 2, float(mm.group(2)) - fs * 0.92, w, fs * 1.12)}

# 站钉
pins = {}
import xml.etree.ElementTree as ET
NS = 'http://www.w3.org/2000/svg'
Q = lambda t2: '{%s}%s' % (NS, t2)
ORDER = ['1号线','2号线','3号线','4号线','5号线','6号线','7号线','8号线','9号线','10号线','11号线','12号线','13号线','14号线','18号线','21号线','22号线','广佛线','APM线']
for name in ORDER:
    root = ET.parse('assets/lines/line-%s.svg' % name).getroot()
    for g in root.findall(Q('g')):
        if g.get('id') == '站圆':
            for c in g.findall(Q('circle')):
                pins.setdefault(c.get('data-nm'), (float(c.get('cx')), float(c.get('cy'))))
# 胶囊站钉(换乘标记中点)
_net = open('assets/lines/network-全网.svg', encoding='utf-8').read()
for mm in re.finditer(r'<line[^>]*data-nm="([^"]+)"[^>]*/>', _net):
    nm = mm.group(1)
    c1 = re.search(r'x1="([-\d.]+)" y1="([-\d.]+)"', mm.group(0))
    c2 = re.search(r'x2="([-\d.]+)" y2="([-\d.]+)"', mm.group(0))
    if c1 and c2 and nm not in pins:
        pins[nm] = ((float(c1.group(1)) + float(c2.group(1))) / 2, (float(c1.group(2)) + float(c2.group(2))) / 2)

# 终点归属: 每徽标 -> 本线走廊端点(焊接略, 用度1端点近似=线段端点中距站圆最远者) -> 最近站圆
import xml.etree.ElementTree as ET
line_ends = {}
for name in ORDER:
    root = ET.parse('assets/lines/line-%s.svg' % name).getroot()
    pts = []
    for g in root.findall(Q('g')):
        if g.get('id') == '走廊':
            for ln in g.findall(Q('line')):
                pts.append((float(ln.get('x1')), float(ln.get('y1'))))
                pts.append((float(ln.get('x2')), float(ln.get('y2'))))
    line_ends[name] = pts

def terminus_of(badge):
    name = badge['ln']
    pts = line_ends[name]
    bc = (badge['x'] + badge['w'] / 2, badge['y'] + badge['h'] / 2)
    far = max(pts, key=lambda p: (p[0] - bc[0]) ** 2 + (p[1] - bc[1]) ** 2)
    best, bnm = 9e9, None
    root = ET.parse('assets/lines/line-%s.svg' % name).getroot()
    for g in root.findall(Q('g')):
        if g.get('id') == '站圆':
            for c in g.findall(Q('circle')):
                dd = (float(c.get('cx')) - far[0]) ** 2 + (float(c.get('cy')) - far[1]) ** 2
                if dd < best:
                    best, bnm = dd, c.get('data-nm')
    return bnm

print('=== 审计(文字-站钉交叉轴 / 徽标-文字交叉轴+沿轴间隙) ===')
updates_t = {}
updates_b = []
for b in badges:
    nm = terminus_of(b)
    tx = texts.get(nm)
    pin = pins.get(nm)
    if not tx or not pin:
        print('!! %s(%s) 缺文字或站钉' % (b['ln'], nm))
        continue
    tcx, tcy = tx['x'], tx['by'] - tx['fs'] * 0.92 + tx['fs'] * 1.12 / 2
    dx, dy = tcx - pin[0], tcy - pin[1]
    t_side = '右' if abs(dx) >= abs(dy) and dx > 0 else ('左' if abs(dx) >= abs(dy) else ('下' if dy > 0 else '上'))
    t_off = abs(dy) if abs(dx) >= abs(dy) else abs(dx)
    bcx, bcy = b['x'] + b['w'] / 2, b['y'] + b['h'] / 2
    bdx, bdy = bcx - tcx, bcy - tcy
    if abs(bdx) >= abs(bdy):
        b_side = '右' if bdx > 0 else '左'
        b_gap = bdx - (b['w'] / 2 + tx['w'] / 2) if bdx > 0 else -bdx - (b['w'] / 2 + tx['w'] / 2)
        b_off = abs(bdy)
    else:
        b_side = '下' if bdy > 0 else '上'
        b_gap = bdy - (b['h'] / 2 + tx['fs'] * 1.12 / 2) if bdy > 0 else -bdy - (b['h'] / 2 + tx['fs'] * 1.12 / 2)
        b_off = abs(bdx)
    flag = ''
    if t_off > 3 or abs(b_off) > 3 or abs(b_gap - 5.0) > 2.5 or b_side != t_side:
        flag = '<<不统一'
    print('%-6s %-8s 文字(%g,%g)站侧%s偏%.1f | 徽标文字%s侧间隙%.1f 交叉偏%.1f %s' %
          (b['ln'], nm, tcx, tcy, t_side, t_off, b_side, b_gap, b_off, flag))
    if flag:
        updates_t[nm] = (pin, tx, t_side)
        updates_b.append((b, nm, tx, t_side))

print()
print('不统一总数:', len(updates_b))
json.dump([{'ln': b['ln'], 'nm': nm} for b, nm, tx, ts in updates_b],
          open('data/_badge-text-fix.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
