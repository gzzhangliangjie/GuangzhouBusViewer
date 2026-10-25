# -*- coding: utf-8 -*-
# 普君北路: 距牌9.3 -> 微移0.5靠牌(闭环全门禁检查)
import io, sys, re, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'tools')
import importlib.util
spec = importlib.util.spec_from_file_location('gen', 'tools/gen-codes-cards.py')
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

NM = '普君北路'
t = open('assets/lines/network-全网.codes.svg', encoding='utf-8').read()
chips, rings = [], []
m = re.search(r'<g id="编号牌"[^>]*>(.*?)</g>', t, re.S)
for r in re.finditer(r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)"([^>]*)stroke="(#[0-9A-Fa-f]{6})"', m.group(1)):
    x, y, w, h = (float(r.group(k)) for k in (1, 2, 3, 4))
    (rings if 'data-ring' in r.group(5) else chips).append((x, y, w, h))
corridors = []
for mm in re.finditer(r'<line x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)"', t):
    corridors.append(tuple(float(mm.group(k)) for k in (1, 2, 3, 4)))
badges = []
for mm in re.finditer(r'<g data-badge="header" transform="translate\([-\d.]+ ([-\d.]+)\) scale\(([\d.]+)\)"[^>]*>(.*?)</g>', t, re.S):
    tr = re.search(r'translate\(([-\d.]+) ([-\d.]+)\)', mm.group(0))
    badges.append((float(tr.group(1)), float(tr.group(2)), 25.12, 13.5))

p = 'data/codes-final-pins.json'
d = json.load(open(p, encoding='utf-8'))
lm = re.search(r'<text x="([-\d.]+)" y="([-\d.]+)"([^>]*)>' + NM + r'</text>', d['labels_inner'])
x, y, attrs = float(lm.group(1)), float(lm.group(2)), lm.group(3)
fs = 7.5
w = gen.part_w(NM, gen.FONT_CARD) / gen.FONT_CARD * fs
best, bc = 9e9, None
for c in chips:
    dd = ((c[0] - x) ** 2 + (c[1] - y) ** 2) ** 0.5
    if dd < best:
        best, bc = dd, (c[0], c[1])
vx, vy = bc[0] - x, bc[1] - y
vn = (vx * vx + vy * vy) ** 0.5

def legal(bx, by):
    box = (bx, by, w, fs * 1.12)
    if any(gen._gap(box, c) < 0.5 for c in chips + rings):
        return False
    if any(gen.rect_seg_dist(box, s) < 4.5 for s in corridors):
        return False
    if any(gen._gap(box, b) < 0.3 for b in badges):
        return False
    for t8 in re.finditer(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*font-size="([\d.]+)"[^>]*>([^<]+)</text>', d['labels_inner']):
        if t8.group(4) == NM or t8.group(4).isascii():
            continue
        f8 = float(t8.group(3))
        w8 = sum(f8 if ord(ch) > 0x2E80 else 0.56 * f8 for ch in t8.group(4))
        if gen._gap(box, (float(t8.group(1)) - w8 / 2, float(t8.group(2)) - f8 * 0.92, w8, f8 * 1.12)) < 1.0:
            return False
    return True

for st in (0.5, 1.0, 1.5, 2.0):
    nx, ny = x + vx / vn * st, y + vy / vn * st
    box = (nx - w / 2, ny - fs * 0.92, w, fs * 1.12)
    d_new = min(gen._gap(box, c) for c in chips)
    if d_new > 9.0 and legal(nx, ny):
        new_text = '<text x="%.2f" y="%.2f"%s>%s</text>' % (nx, ny, attrs, NM)
        d['labels_inner'] = d['labels_inner'].replace(lm.group(0), new_text)
        json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('普君北路: 距牌%.1f->%.1fpt (%g,%g)->(%g,%g)' % (best, d_new, x, y, nx, ny))
        break
else:
    print('!! 普君北路 阶梯内无合法靠牌位')
