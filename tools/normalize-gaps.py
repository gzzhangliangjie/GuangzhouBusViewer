# -*- coding: utf-8 -*-
"""沿轴间隙归一化(终版): 沿轴间隙偏离标准带(<3.0或>6.5)的文字,
沿当前侧收拢到4.6(引擎主流值), 阶梯4.6/3.6/5.6/2.6/6.6/1.6/7.6,
全门禁合法性(胶囊/环0.5、走廊4.5、他文字1.0、徽标0.3), 不合法保留上报。
用法: python tools/normalize-gaps.py
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

# 胶囊组(中心距<=12) -> (中心, 盒)
centers = [(c[0] + c[2] / 2, c[1] + c[3] / 2) for c in chips]
groups = []
for c in centers:
    for g in groups:
        if any((c[0] - gc[0]) ** 2 + (c[1] - gc[1]) ** 2 <= 144 for gc in g):
            g.append(c)
            break
    else:
        groups.append([c])
ginfo = [(sum(c[0] for c in g) / len(g), sum(c[1] for c in g) / len(g),
          min(c[0] for c in g) - 12.15, min(c[1] for c in g) - 6.4,
          max(c[0] for c in g) + 12.15, max(c[1] for c in g) + 6.4) for g in groups]

def legal(box, self_nm):
    if any(gen._gap(box, c) < 0.5 for c in chips + rings):
        return False
    if any(gen.rect_seg_dist(box, s) < 4.5 for s in corridors):
        return False
    if any(gen._gap(box, (b['x'], b['y'], b['w'], b['h'])) < 0.3 for b in badges):
        return False
    for o in texts:
        if o['nm'] == self_nm:
            continue
        if gen._gap(box, o['box']) < 1.0:
            return False
    return True

applied, kept = 0, []
new_t = t
for e in texts:
    nm, box = e['nm'], e['box']
    tcx, tcy = box[0] + box[2] / 2, box[1] + box[3] / 2
    best, bg = 9e18, None
    for gi, (gx, gy, gx0, gy0, gx1, gy1) in enumerate(ginfo):
        dd = (tcx - gx) ** 2 + (tcy - gy) ** 2
        if dd < best:
            best, bg = dd, gi
    gx, gy, gx0, gy0, gx1, gy1 = ginfo[bg]
    dx, dy = tcx - gx, tcy - gy
    if abs(dx) >= abs(dy):
        sgn = 1 if dx > 0 else -1
        ax, cur = 0, abs(dx) - box[2] / 2 - (gx1 - gx0) / 2
    else:
        sgn = 1 if dy > 0 else -1
        ax, cur = 1, abs(dy) - box[3] / 2 - (gy1 - gy0) / 2
    if 3.0 <= cur <= 6.5:
        continue
    placed = None
    for g in (4.6, 3.6, 5.6, 2.6, 6.6, 1.6, 7.6):
        if ax == 0:
            nc = (gx + sgn * ((gx1 - gx0) / 2 + g + box[2] / 2), tcy)
        else:
            nc = (tcx, gy + sgn * ((gy1 - gy0) / 2 + g + box[3] / 2))
        nbox = (nc[0] - box[2] / 2, nc[1] - box[3] / 2, box[2], box[3])
        if legal(nbox, nm):
            placed = (nc, g)
            break
    if placed:
        (ncx, ncy), g = placed
        moves_el = e['el']
        new_attrs = re.sub(r'\bx="[-\d.]+"', 'x="%.2f"' % ncx, e['attrs'])
        new_attrs = re.sub(r'\by="[-\d.]+"', 'y="%.2f"' % ncy, new_attrs)
        
        new_el = '<text %s>%s</text>' % (new_attrs, nm)
        new_t = t.replace(e["el"], new_el)
        applied += 1
        print('%-8s %s轴 gap%.1f -> %.1f' % (nm, '横' if ax == 0 else '纵', cur, g))
    else:
        kept.append((nm, round(cur, 1)))
        print('保留: %s gap%.1f (阶梯不合法)' % (nm, cur))

if applied:
    import xml.etree.ElementTree as ET
    try:
        ET.fromstring(new_t)
    except ET.ParseError as pe:
        print('!! XML损坏拒绝落盘:', pe)
        sys.exit(1)
    open(F, 'w', encoding='utf-8').write(new_t)
print('应用%d 保留%d' % (applied, len(kept)))
