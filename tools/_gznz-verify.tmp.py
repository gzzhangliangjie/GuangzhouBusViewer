# -*- coding: utf-8 -*-
# 广州南站文字 (1448,1594.75) 权威校验: 正确盒约定(中心x/基线y), 全654走廊+胶囊+环+徽标+文字
import io, sys, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'tools')
import importlib.util
spec = importlib.util.spec_from_file_location('gen', 'tools/gen-codes-cards.py')
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

NM = '广州南站'
TX, TY = 1448.00, 1594.75
FS = 7.5
W = gen.part_w(NM, gen.FONT_CARD) / gen.FONT_CARD * FS
BOX = (TX - W / 2, TY - FS * 0.92, W, FS * 1.12)
print('文字盒: (%g,%g)-(%g,%g) 宽%g' % (BOX[0], BOX[1], BOX[0] + BOX[2], BOX[1] + BOX[3], W))

t = open('assets/lines/network-全网.codes.svg', encoding='utf-8').read()
worst_c = (9e9, None)
for m in re.finditer(r'<line x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)"', t):
    seg = tuple(float(m.group(k)) for k in (1, 2, 3, 4))
    d = gen.rect_seg_dist(BOX, seg)
    if d < worst_c[0]:
        worst_c = (d, seg)
print('最近走廊: %.2fpt seg(%g,%g)->(%g,%g)' % (worst_c[0], worst_c[1][0], worst_c[1][1], worst_c[1][2], worst_c[1][3]))

chips, rings = [], []
m = re.search(r'<g id="编号牌"[^>]*>(.*?)</g>', t, re.S)
for r in re.finditer(r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)"([^>]*)stroke="(#[0-9A-Fa-f]{6})"', m.group(1)):
    x, y, w, h = (float(r.group(k)) for k in (1, 2, 3, 4))
    (rings if 'data-ring' in r.group(5) else chips).append((x, y, w, h))
worst_chip = min((gen._gap(BOX, c), c) for c in chips + rings)
print('最近胶囊/环: %.2fpt 盒(%g,%g)-(%g,%g)' % (worst_chip[0], worst_chip[1][0], worst_chip[1][1], worst_chip[1][0] + worst_chip[1][2], worst_chip[1][1] + worst_chip[1][3]))

LNAMES = {'1号线','2号线','3号线','4号线','5号线','6号线','7号线','8号线','9号线','10号线','11号线','12号线','13号线','14号线','18号线','21号线','22号线','广佛线','APM线'}
K2L = {'GF': '广佛线', 'APM': 'APM线'}
p = 'data/codes-final-pins.json'
d = json.load(open(p, encoding='utf-8'))
bsz, badges = {}, []
worst_b = (9e9, None)
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
    bb = (float(tr.group(1)), float(tr.group(2)), bsz[ln][0] * float(mm.group(2)), bsz[ln][1] * float(mm.group(2)))
    g8 = gen._gap(BOX, bb)
    if g8 < worst_b[0]:
        worst_b = (g8, ln)
print('最近徽标: %.2fpt (%s)' % (worst_b[0], worst_b[1]))
worst_t = (9e9, None)
for t8 in re.finditer(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*font-size="([\d.]+)"[^>]*>([^<]+)</text>', d['labels_inner']):
    if t8.group(4) == NM:
        continue
    f8 = float(t8.group(3))
    w8 = gen.part_w(t8.group(4), gen.FONT_CARD) / gen.FONT_CARD * f8 if not t8.group(4).isascii() else None
    if t8.group(4).isascii():
        import math
        w8 = gen._FM_ARIAL[5.5].getlength(t8.group(4)) / 10.0 if gen._FM_ARIAL else 30
    tb = (float(t8.group(1)) - w8 / 2, float(t8.group(2)) - f8 * 0.92, w8, f8 * 1.12)
    g8 = gen._gap(BOX, tb)
    if g8 < worst_t[0]:
        worst_t = (g8, t8.group(4))
print('最近其他文字: %.2fpt (%s)' % (worst_t[0], worst_t[1]))
print()
print('结论: 走廊%.2f 胶囊%.2f 徽标%.2f 文字%.2f' % (worst_c[0], worst_chip[0], worst_b[0], worst_t[0]))
