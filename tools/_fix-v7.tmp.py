# -*- coding: utf-8 -*-
# 两枚文字修正: 京溪南方医院拉向其牌至<=9(闭环合法性); 南村万博左移0.25解发丝擦边
import io, sys, re, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'tools')
import importlib.util
spec = importlib.util.spec_from_file_location('gen', 'tools/gen-codes-cards.py')
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

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
li = d['labels_inner']

def chip_near(x, y, r=60):
    best, bc = 9e9, None
    for c in chips:
        dd = ((c[0] - x) ** 2 + (c[1] - y) ** 2) ** 0.5
        if dd < best:
            best, bc = dd, (c[0], c[1])
    return best, bc

def legal_for(nm, w, fs, bx, by, exclude=()):
    box = (bx, by, w, fs * 1.12)
    if any(gen._gap(box, c) < 0.5 for c in chips + rings):
        return False
    if any(gen.rect_seg_dist(box, s) < 4.5 for s in corridors):
        return False
    if any(gen._gap(box, b) < 0.3 for b in badges):
        return False
    for t8 in re.finditer(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*font-size="([\d.]+)"[^>]*>([^<]+)</text>', li):
        if t8.group(4) in exclude or t8.group(4).isascii():
            continue
        f8 = float(t8.group(3))
        w8 = sum(f8 if ord(ch) > 0x2E80 else 0.56 * f8 for ch in t8.group(4))
        ob = (float(t8.group(1)) - w8 / 2, float(t8.group(2)) - f8 * 0.92, w8, f8 * 1.12)
        if gen._gap(box, ob) < 1.0:
            return False
    return True

# 1) 京溪南方医院: 距牌15.4 -> 沿连线拉向牌至<=9, 步进0.5闭环
for nm, w, fs in (('京溪南方医院', None, 7.5),):
    w = gen.part_w(nm, gen.FONT_CARD) / gen.FONT_CARD * fs
    mm = re.search(r'<text x="([-\d.]+)" y="([-\d.]+)"([^>]*)>' + nm + r'</text>', li)
    x, y = float(mm.group(1)), float(mm.group(2))
    bd, bc = chip_near(x, y - fs * 0.56, 80)
    vx, vy = bc[0] - x, bc[1] - y
    vn = (vx * vx + vy * vy) ** 0.5
    done = False
    for st in [s * 0.5 for s in range(1, 61)]:
        nx, ny = x + vx / vn * st, y + vy / vn * st
        box = (nx - w / 2, ny - fs * 0.92, w, fs * 1.12)
        d_to_chip = min(gen._gap(box, c) for c in chips)
        if d_to_chip > 9.0:
            continue
        if gen._gap(box, (bc[0] - 10.25, bc[1] - 4.5, 20.5, 9.0)) < 0.5:
            continue
        if not legal_for(nm, w, fs, nx, ny, exclude=(nm,)):
            continue
        li = li[:mm.start()] + '<text x="%.2f" y="%.2f"%s>%s</text>' % (nx, ny, mm.group(3), nm) + li[mm.end():]
        print('京溪南方医院: 距牌%.1f->%.1fpt (%g,%g)->(%g,%g)' % (bd, d_to_chip, x, y, nx, ny))
        done = True
        break
    if not done:
        print('!! 京溪南方医院 无合法近牌位')

# 2) 南村万博: 环缘0.41 -> 左移0.25
mm = re.search(r'<text x="([-\d.]+)" y="([-\d.]+)"([^>]*)>南村万博</text>', li)
if mm:
    x, y = float(mm.group(1)), float(mm.group(2))
    li = li[:mm.start()] + '<text x="%.2f" y="%.2f"%s>南村万博</text>' % (x - 0.25, y, mm.group(3)) + li[mm.end():]
    print('南村万博: 左移0.25pt')

d['labels_inner'] = li
json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('done')
