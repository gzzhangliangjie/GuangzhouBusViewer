# -*- coding: utf-8 -*-
# V5冲突盒子明细: 南村万博 文字盒 vs 胶囊/环
import io, sys, re, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'tools')
import importlib.util
spec = importlib.util.spec_from_file_location('gen', 'tools/gen-codes-cards.py')
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

NM = '南村万博'
t = open('assets/lines/network-全网.codes.svg', encoding='utf-8').read()
d = json.load(open('data/codes-final-pins.json', encoding='utf-8'))
lm = re.search(r'<g id="站名标注"[^>]*>(.*?)</g>', t, re.S)
for mm in re.finditer(r'<text ([^>]*)>([^<]+)</text>', lm.group(1)):
    if NM in mm.group(2) or mm.group(2) == NM:
        at = mm.group(1)
        x = float(re.search(r'x="([-\d.]+)"', at).group(1))
        y = float(re.search(r'y="([-\d.]+)"', at).group(1))
        fs = float(re.search(r'font-size="([\d.]+)"', at).group(1))
        box = gen.text_box({'x': x, 'y': y, 'fs': fs, 'content': mm.group(2)})
        print('文字 %s: 盒(%g,%g)-(%g,%g)' % (mm.group(2), box[0], box[1], box[0] + box[2], box[1] + box[3]))

m = re.search(r'<g id="编号牌"[^>]*>(.*?)</g>', t, re.S)
for r in re.finditer(r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)"([^>]*)stroke="(#[0-9A-Fa-f]{6})"', m.group(1)):
    x, y, w, h = (float(r.group(k)) for k in (1, 2, 3, 4))
    cx, cy = x + w / 2, y + h / 2
    if abs(cx - 1768.5) < 40 and abs(cy - 1523.2) < 40:
        print('牌 (%g,%g) 盒(%g,%g)-(%g,%g) %s%s' % (cx, cy, x, y, x + w, y + h, r.group(6), ' [ring]' if 'data-ring' in r.group(5) else ''))
