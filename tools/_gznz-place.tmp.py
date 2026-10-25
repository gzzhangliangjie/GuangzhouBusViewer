# -*- coding: utf-8 -*-
# 广州南站文字: 闭环确定性落位(全部654走廊+胶囊+徽标+其他文字逐项校验)
import io, sys, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'tools')
import importlib.util
spec = importlib.util.spec_from_file_location('gen', 'tools/gen-codes-cards.py')
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

NM = '广州南站'
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
    badges.append((float(tr.group(1)), float(tr.group(2)),
                   bsz[ln][0] * float(mm.group(2)), bsz[ln][1] * float(mm.group(2))))

p = 'data/codes-final-pins.json'
d = json.load(open(p, encoding='utf-8'))
lm = re.search(r'<text x="([-\d.]+)" y="([-\d.]+)"([^>]*)>' + NM + r'</text>', d['labels_inner'])
ox, oy, attrs = float(lm.group(1)), float(lm.group(2)), lm.group(3)
fs = 7.5
w = gen.part_w(NM, gen.FONT_CARD) / gen.FONT_CARD * fs
others = []
for t8 in re.finditer(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*font-size="([\d.]+)"[^>]*>([^<]+)</text>', d['labels_inner']):
    if t8.group(4) == NM:
        continue
    f8 = float(t8.group(3))
    w8 = sum(f8 if ord(ch) > 0x2E80 else 0.56 * f8 for ch in t8.group(4))
    others.append((float(t8.group(1)) - w8 / 2, float(t8.group(2)) - f8 * 0.92, w8, f8 * 1.12, t8.group(4)))

def legal(bx, by):
    box = (bx, by, w, fs * 1.12)
    if any(gen._gap(box, c) < 0.5 for c in chips + rings):
        return False, '胶囊'
    if any(gen.rect_seg_dist(box, s) < 4.5 for s in corridors):
        return False, '走廊'
    if any(gen._gap(box, o[:4]) < 1.0 for o in others):
        return False, '文字'
    if any(gen._gap(box, (b[0], b[1], b[2], b[3])) < 0.3 for b in badges):
        return False, '徽标'
    return True, ''

# 站钉(胶囊组中点)
_net = open('assets/lines/network-全网.svg', encoding='utf-8').read()
_cap = re.search(r'<line[^>]*data-nm="' + NM + r'"[^>]*/>', _net)
xs = [float(v) for v in re.findall(r'[xy][12]="([-\d.]+)"', _cap.group(0))]
pin = (sum(xs[:2]) / 2 if False else sum(xs[i] for i in (0, 2)) / 2, sum(xs[i] for i in (1, 3)) / 2)

# 候选: 当前位 + 右向阶梯(沿y=站钉高度右移, 2pt步进到60pt) — 每候选输出细节
cands = [(ox, oy, '当前位')]
for step in (2, 4, 6, 8, 12, 16, 20, 26, 32, 40, 50, 60):
    cands.append((pin[0] + (ox - pin[0]) * 0 + step + w / 2 + 0, pin[1], '右移%d' % step))
# 右移候选: 盒左缘 = 站钉x + step
cands = [(ox, oy, '当前位')] + [((pin[0] + st + w / 2), oy, '右移%d' % st) for st in
         (2, 4, 6, 8, 12, 16, 20, 26, 32, 40, 50, 60)]
for bx, by, tag in cands:
    ok, why = legal(bx, by)
    print('%-14s 盒(%g,%g)-(%g,%g) -> %s %s' % (tag, bx, by, bx + w, by + fs * 1.12, '合法' if ok else '违规:' + why, ''))
    if ok:
        baseline = by + fs * 0.92 - fs * 0.92 + fs * 0.92
        baseline = by + fs * 0.92
        new_text = '<text x="%.2f" y="%.2f"%s>%s</text>' % (bx + w / 2, baseline, attrs, NM)
        d['labels_inner'] = d['labels_inner'].replace(lm.group(0), new_text)
        json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('已落位:', new_text)
        break
