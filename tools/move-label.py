# -*- coding: utf-8 -*-
"""单站文字规则化挪位工具(2026-10-25 用户定稿语义):
初始位置 = 当前锚表位(全图规则所算); 挪 = 站体胶囊组基准 8向×gap阶梯(居中规范:
左右排布=垂直居中于站钉, 上下排布=水平居中于站钉), 每候选全门禁合法性检查
(胶囊/环0.5、走廊4.5、其他文字1.0、徽标0.3), 按方向优先序取首个合法。
候选0 = 当前位已在目标侧且全门禁合法 → 不动。
用法: python tools/move-label.py 站名 方向   (方向=right/left/above/below)
写完必须跑 python tools/verify-all.py --quick 全链确认。
"""
import io, os, re, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import importlib.util
spec = importlib.util.spec_from_file_location('gen', os.path.join(ROOT, 'tools', 'gen-codes-cards.py'))
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

NM, DIR = sys.argv[1], sys.argv[2]
DIRS = {'right': (1, 0), 'left': (-1, 0), 'above': (0, -1), 'below': (0, 1)}

t = open('assets/lines/network-全网.codes.svg', encoding='utf-8').read()
chips, rings = [], []
m = re.search(r'<g id="编号牌"[^>]*>(.*?)</g>', t, re.S)
if m:
    for r in re.finditer(r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)"([^>]*)stroke="(#[0-9A-Fa-f]{6})"', m.group(1)):
        x, y, w, h = (float(r.group(k)) for k in (1, 2, 3, 4))
        (rings if 'data-ring' in r.group(5) else chips).append((x, y, w, h))
corridors = []
for mm in re.finditer(r'<line x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)"', t):
    corridors.append(tuple(float(mm.group(k)) for k in (1, 2, 3, 4)))
LNAMES = {'1号线','2号线','3号线','4号线','5号线','6号线','7号线','8号线','9号线','10号线',
          '11号线','12号线','13号线','14号线','18号线','21号线','22号线','广佛线','APM线'}
K2L = {'GF': '广佛线', 'APM': 'APM线'}
bsz = {}
badges = []
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
    badges.append((float(tr.group(1)), float(tr.group(2)),
                   bsz[ln][0] * float(mm.group(2)), bsz[ln][1] * float(mm.group(2))))

p = 'data/codes-final-pins.json'
d = json.load(open(p, encoding='utf-8'))
lm = re.search(r'<text x="([-\d.]+)" y="([-\d.]+)"([^>]*)>' + NM + r'</text>', d['labels_inner'])
assert lm, '锚表无该站文字'
ox, oy, attrs = float(lm.group(1)), float(lm.group(2)), lm.group(3)
fs = float(re.search(r'font-size="([\d.]+)"', attrs).group(1))
w = gen.part_w(NM, gen.FONT_CARD) / gen.FONT_CARD * fs

# 其他文字盒(排除自身)
others = []
for t8 in re.finditer(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*font-size="([\d.]+)"[^>]*>([^<]+)</text>', d['labels_inner']):
    if t8.group(4) == NM:
        continue
    f8 = float(t8.group(3))
    w8 = sum(f8 if ord(ch) > 0x2E80 else 0.56 * f8 for ch in t8.group(4))
    others.append((float(t8.group(1)) - w8 / 2, float(t8.group(2)) - f8 * 0.92, w8, f8 * 1.12, t8.group(4)))

# 站体胶囊组盒(该站胶囊/环并集外扩1.9)
grp = [c for c in chips + rings if abs((c[0] + c[2] / 2) - ox) < 60 and abs((c[1] + c[3] / 2) - oy) < 60]
assert grp, '未找到站体胶囊组'
gx0 = min(c[0] for c in grp) - 1.9
gy0 = min(c[1] for c in grp) - 1.9
gx1 = max(c[0] + c[2] for c in grp) + 1.9
gy1 = max(c[1] + c[3] for c in grp) + 1.9

# 站钉(居中规范基准): 底图站圆(单站)或换乘标记胶囊(多站, 取中点)
_net = open('assets/lines/network-全网.svg', encoding='utf-8').read()
_pin_m = re.search(r'<circle cx="([-\d.]+)" cy="([-\d.]+)"[^>]*data-nm="' + NM + r'"', _net)
if _pin_m:
    pin_x, pin_y = float(_pin_m.group(1)), float(_pin_m.group(2))
else:
    _cap = re.search(r'<(?:line|path)[^>]*data-nm="' + NM + r'"[^>]*/>', _net)
    assert _cap, '底图无该站站圆/胶囊'
    _c1 = re.search(r'x1="([-\d.]+)" y1="([-\d.]+)"', _cap.group(0))
    _c2 = re.search(r'x2="([-\d.]+)" y2="([-\d.]+)"', _cap.group(0))
    if _c1 and _c2:
        pin_x, pin_y = (float(_c1.group(1)) + float(_c2.group(1))) / 2, (float(_c1.group(2)) + float(_c2.group(2))) / 2
    else:
        pin_x, pin_y = 1402.0, 1593.0

def legal(bx, by):
    box = (bx, by, w, fs * 1.12)
    if any(gen._gap(box, c) < 0.5 for c in chips + rings):
        return False
    if any(gen.rect_seg_dist(box, s) < 4.5 for s in corridors):
        return False
    if any(gen._gap(box, o[:4]) < 1.0 for o in others):
        return False
    if any(gen._gap(box, (b[0], b[1], b[2], b[3])) < 0.3 for b in badges):
        return False
    return True

# 候选0=当前位: 已在目标侧且全门禁合法 → 不动(初始位=规则所算)
cur_box = (ox - w / 2, oy - fs * 0.92)
on_side = ((DIR == 'right' and ox > pin_x) or (DIR == 'left' and ox < pin_x) or
           (DIR == 'above' and oy < pin_y) or (DIR == 'below' and oy > pin_y))
if on_side and legal(cur_box[0], cur_box[1]):
    print('%s 已在%s侧且全门禁合法(初始位=规则所算), 不动' % (NM, DIR))
    sys.exit(0)

# 8向×gap阶梯, 方向优先序, 居中规范: 左右=垂直居中于站钉; 上下=水平居中于站钉
dx0, dy0 = DIRS[DIR]
order = [(dx0, dy0)] + [(dx, dy) for dx, dy in DIRS.values() if (dx, dy) != (dx0, dy0)]
placed = None
for sdx, sdy in order:
    for gap in (3.0, 6.0, 10.0, 15.0, 20.0, 26.0):
        if sdx != 0:
            cx = gx1 + sdx * (gap + w / 2) if sdx > 0 else gx0 + sdx * (gap + w / 2)
            cy = pin_y
        else:
            cx = pin_x
            cy = gy1 + sdy * (gap + fs * 0.56) if sdy > 0 else gy0 + sdy * (gap + fs * 0.56)
        box = (cx - w / 2, cy - fs * 0.56, w, fs * 1.12)
        if gen._gap(box, (gx0, gy0, gx1 - gx0, gy1 - gy0)) < 0.5:
            continue
        if any(gen._gap(box, c) < 0.5 for c in chips + rings):
            continue
        if any(gen._gap(box, (b[0], b[1], b[2], b[3])) < 0.3 for b in badges):
            continue
        ok = True
        for seg in corridors:
            if gen.rect_seg_dist(box, seg) < 4.5:
                ok = False
                break
        if not ok:
            continue
        placed = (cx, cy)
        break
    if placed:
        break
assert placed, '8向阶梯均无合法位: %s %s' % (NM, DIR)
print('规则落位: %s (%g,%g) -> (%g,%g) [%s]' % (NM, ox, oy, placed[0], placed[1], DIR))
baseline = placed[1] - fs * 0.56 + 0.92 * fs   # 盒顶=baseline-0.92fs
new_text = '<text x="%.2f" y="%.2f"%s>%s</text>' % (placed[0], baseline, attrs, NM)
d['labels_inner'] = d['labels_inner'].replace(lm.group(0), new_text)
json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('labels_inner 已更新 ->', new_text)
print('下一步必须: python tools/verify-all.py --quick 全链确认')
