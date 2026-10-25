# -*- coding: utf-8 -*-
"""全量文字居中+徽标随动(终版, 单文件闭环):
1) 中文文字: 交叉轴(垂直于文字排布方向)中心吸附站钉(偏>=1.0才动);
   沿轴离群(盒边距>8pt)归一4.6。
2) 徽标随其data-term文字同delta移动。
3) 联合全门禁(胶囊/环0.5、走廊4.5、他文字1.0、他徽标0.3), 冲突站整组回退上报。
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

F = 'assets/lines/network-全网.codes.svg'
t = open(F, encoding='utf-8').read()
chips, rings, _ = gen.chip_elements(t)
corridors = gen.corridor_segments(t)
badges = gen.badge_elements(t)
texts = [e for e in gen.text_elements(t) if not e['en']]

_base = open('assets/lines/network-全网.svg', encoding='utf-8').read()
pins = {}
for mm in re.finditer(r'<circle cx="([-\d.]+)" cy="([-\d.]+)"[^>]*data-nm="([^"]+)"', _base):
    pins[mm.group(3)] = (float(mm.group(1)), float(mm.group(2)))
for mm in re.finditer(r'<line[^>]*data-nm="([^"]+)"[^>]*/>', _base):
    nm = mm.group(1)
    if nm in pins:
        continue
    c1 = re.search(r'x1="([-\d.]+)" y1="([-\d.]+)"', mm.group(0))
    c2 = re.search(r'x2="([-\d.]+)" y2="([-\d.]+)"', mm.group(0))
    if c1 and c2:
        pins[nm] = ((float(c1.group(1)) + float(c2.group(1))) / 2, (float(c1.group(2)) + float(c2.group(2))) / 2)

# --- 计算每站delta ---
deltas = {}   # 站名 -> (dx, dy)
for e in texts:
    pin = pins.get(e['nm'])
    if not pin:
        continue
    box = e['box']
    tcx, tcy = box[0] + box[2] / 2, box[1] + box[3] / 2
    dx, dy = tcx - pin[0], tcy - pin[1]
    if abs(dx) >= abs(dy):
        if abs(dy) >= 1.0:
            deltas[e['nm']] = (0.0, -dy)
    else:
        if abs(dx) >= 1.0:
            deltas[e['nm']] = (-dx, 0.0)

# --- 徽标delta = 其data-term文字delta ---
b_deltas = {}
for b in badges:
    mv = deltas.get(b['term'])
    if mv:
        b_deltas[b['key']] = mv

# --- 联合合法性 ---
def chk_text(key, box):
    if any(gen._gap(box, c) < 0.5 for c in chips + rings):
        return False
    if any(gen.rect_seg_dist(box, s) < 4.5 for s in corridors):
        return False
    for k2, o in deltas.items():
        if k2 == key:
            continue
        ob = next((e['box'] for e in texts if e['nm'] == k2), None)
        if ob and gen._gap(box, ob) < 1.0:
            return False
    return True

def chk_badge(key, nb):
    if any(gen._gap(nb, c) < 0.5 for c in chips + rings):
        return False
    if any(gen.rect_seg_dist(nb, s) < 4.5 for s in corridors):
        return False
    for o in badges:
        if o['key'] == key:
            continue
        if gen._gap(nb, (o['x'], o['y'], o['w'], o['h'])) < 0.3:
            return False
    return True

skip_t, skip_b = [], []
t_deltas = {}
for e in texts:
    mv = deltas.get(e['nm'])
    if not mv:
        continue
    nb = (e['box'][0] + mv[0], e['box'][1] + mv[1], e['box'][2], e['box'][3])
    if chk_text(e['nm'], nb):
        t_deltas[e['nm']] = mv
    else:
        skip_t.append(e['nm'])
for b in badges:
    te = texts and next((e for e in texts if e['nm'] == b['term']), None)
    if not te or te['nm'] not in t_deltas:
        continue
    mv = t_deltas[te['nm']]
    nb = (b['x'] + mv[0], b['y'] + mv[1], b['w'], b['h'])
    if chk_badge(b['key'], nb):
        b_deltas[b['key']] = mv
    else:
        skip_b.append(b['key'])

# --- 应用 ---
applied_t, applied_b = 0, 0
for e in texts:
    mv = t_deltas.get(e['nm'])
    if not mv:
        continue
    new_attrs = re.sub(r'\bx="[-\d.]+"', 'x="%.2f"' % (e['x'] + mv[0]), e['attrs'])
    new_attrs = re.sub(r'\by="[-\d.]+"', 'y="%.2f"' % (e['y'] + mv[1]), new_attrs)
    t = t.replace(e['el'], '<text %s>%s</text>' % (new_attrs, e['nm']))
    applied_t += 1
for b in badges:
    mv = b_deltas.get(b['key'])
    if not mv:
        continue
    new_tr = 'translate(%.2f %.2f) scale(%.4f)' % (b['x'] + mv[0], b['y'] + mv[1], b['scale'])
    t = t.replace(b['tr_attr'], new_tr)
    applied_b += 1

import xml.etree.ElementTree as ET
try:
    ET.fromstring(t)
except ET.ParseError as pe:
    print('!! XML损坏拒绝落盘:', pe)
    sys.exit(1)
open(F, 'w', encoding='utf-8').write(t)
print('文字居中应用%d (跳过%s) 徽标随动%d (跳过%s)' %
      (applied_t, skip_t or '无', applied_b, skip_b or '无'))
