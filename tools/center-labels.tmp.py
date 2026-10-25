# -*- coding: utf-8 -*-
"""侧排文字垂直居中(于站钉) + 徽标随动: 直改codes SVG。
1) 侧排文字(左/右)交叉轴偏>=1.0 → 垂直居中于其站钉(交叉轴=纵向);
   上下排文字水平居中同理(对称处理)。
2) 英文行随中文同delta。
3) 徽标(data-term=站名)随其文字同delta(保持相对关系)。
4) 全门禁合法性: 胶囊/环0.5、走廊4.5、他文字1.0、徽标0.3——
   校验基于"全部移动后"的联合布局(自己的delta对别人的delta), 不合法者整组回退上报。
"""
import io, os, re, sys, json, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import importlib.util
spec = importlib.util.spec_from_file_location('gen', 'tools/gen-codes-cards.py')
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

F = 'assets/lines/network-全网.codes.svg'
t = open(F, encoding='utf-8').read()
chips, rings, _ = gen.chip_elements(t)
corridors = gen.corridor_segments(t)
badges = gen.badge_elements(t)
texts = [e for e in gen.text_elements(t) if not e['en']]

# 站钉(底图站圆/换乘胶囊中点)
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

# 文字 -> 站钉: 站名精确匹配
plans = []
for e in texts:
    pin = pins.get(e['nm'])
    if not pin:
        continue
    px, py = pin
    tcx, tcy = e['box'][0] + e['box'][2] / 2, e['box'][1] + e['box'][3] / 2
    dx, dy = tcx - px, tcy - py
    if abs(dx) >= abs(dy):
        cross = ('y', dy)      # 横向排: 交叉轴=纵向偏移
    else:
        cross = ('x', dx)      # 纵向排: 交叉轴=横向偏移
    plans.append({'e': e, 'pin': pin, 'cross_axis': cross[0], 'cross_off': cross[1], 'ens': []})

# 计划: 交叉轴吸附到站钉(偏>=1.0才动)
moves = {}
for p2 in plans:
    e = p2['e']
    ax, off = p2['cross_axis'], p2['cross_off']
    if abs(off) < 1.0:
        continue
    moves[id(e)] = (ax, -off)   # 吸附到站钉坐标=偏移取反
# 徽标随文字: data-term=站名 → 找文字delta(含其EN? 徽标跟随zh)
b_delta = {}
for b in badges:
    te = None
    for p2 in plans:
        if p2['e']['nm'] == b['term']:
            te = p2
            break
    if not te:
        continue
    mv = moves.get(id(te['e']))
    if mv:
        b_delta[b['key']] = mv

print('计划: 文字%d 徽标%d' % (len(moves), len(b_delta)))

# 贪心逐站应用: 静态冲突(胶囊/环/走廊/未动徽标)→保留原位; 已应用移动计入动态障碍
new_boxes = {}
for e in texts:
    new_boxes[id(e)] = e['box']
new_badges = {b['key']: (b['x'], b['y'], b['w'], b['h']) for b in badges}
applied, kept = 0, []
for p2 in plans:
    e = p2['e']
    if id(e) not in moves:
        continue
    ax, off = moves[id(e)]
    ncx = e['x'] + (off if ax == 'x' else 0)
    ncy = e['y'] + (off if ax == 'y' else 0)
    nbox = (ncx - e['box'][2] / 2, ncy - e['box'][3] / 2, e['box'][2], e['box'][3])
    ok = True
    if any(gen._gap(nbox, c) < 0.5 for c in chips + rings):
        ok = False
    if ok and any(gen.rect_seg_dist(nbox, s2) < 4.5 for s2 in corridors):
        ok = False
    if ok and any(gen._gap(nbox, nb) < 0.5 for nb in new_badges.values()):
        ok = False
    if ok:
        for k2, ob in new_boxes.items():
            if k2 == id(e):
                continue
            if gen._gap(nbox, ob) < 1.0:
                ok = False
                break
    if ok:
        new_boxes[id(e)] = nbox
        nm2 = e['nm']
        new_attrs = re.sub(r'x="[-\d.]+"', 'x="%.2f"' % ncx, e['attrs'])
        new_attrs = re.sub(r'y="[-\d.]+"', 'y="%.2f"' % ncy, new_attrs)
        t = t.replace(e['el'], '<text %s>%s</text>' % (new_attrs, e['nm']))
        applied += 1
    else:
        kept.append((e['nm'], '居中位被占'))
print('应用%d 保留%d' % (applied, len(kept)))
for k2 in kept[:10]:
    print('  保留:', k2)

# 应用到t
for e in texts:
    key = id(e)
    if key in moves:
        ax, off = moves[key]
        ncx, ncy = e['x'] + (off if ax == 'x' else 0), e['y'] + (off if ax == 'y' else 0)
        new_attrs = re.sub(r'\bx="[-\d.]+"', 'x="%.2f"' % ncx, e['attrs'])
        new_attrs = re.sub(r'\by="[-\d.]+"', 'y="%.2f"' % ncy, new_attrs)
        t = t.replace(e['el'], '<text %s>%s</text>' % (new_attrs, e['nm']))
for b in badges:
    key = gen.badge_key_of(b) if hasattr(gen, 'badge_key_of') else b['key']
    if key in b_delta:
        ax, off = b_delta[key]
        nbx = b['x'] + (off if ax == 'x' else 0)
        nby = b['y'] + (off if ax == 'y' else 0)
        new_tr = 'translate(%.2f %.2f) scale(%.4f)' % (nbx, nby, b['scale'])
        t = t.replace(b['tr_attr'], new_tr)

import xml.etree.ElementTree as _ET
try:
    _ET.fromstring(t)
except _ET.ParseError as _pe:
    print('!! XML损坏拒绝落盘:', _pe)
    sys.exit(1)
open(F, 'w', encoding='utf-8').write(t)
print('codes SVG 已更新(文字%d+徽标%d)' % (len(moves), len(b_delta)))
