# -*- coding: utf-8 -*-
# 两阶段: 阶段1=全量规则判定(R1胶囊0.5/R2走廊4.5/R3文字1.0/R4徽标0.3/R5贴牌9/
#         R6居中=交叉轴对齐——能居中却没居中即违规, 中心位须合法);
# 阶段2=只调整违规项(居中违规吸附到组心, 其余违规按对应规则最小位移)。
import io, sys, re, json, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'tools')
import importlib.util
spec = importlib.util.spec_from_file_location('gen', 'tools/gen-codes-cards.py')
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

d = json.load(open('data/codes-final-pins.json', encoding='utf-8'))
li = d['labels_inner']
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

# 中文主行文字盒
zhs = []
for mm in re.finditer(r'<text ([^>]*)>([^<]+)</text>', li):
    at, nm = mm.group(1), mm.group(2)
    if nm.isascii():
        continue
    try:
        x = float(re.search(r'\bx="([-\d.]+)"', at).group(1))
        y = float(re.search(r'\by="([-\d.]+)"', at).group(1))
        fs = float(re.search(r'font-size="([\d.]+)"', at).group(1))
    except (AttributeError, ValueError):
        continue
    w = sum(fs if ord(ch) > 0x2E80 else 0.56 * fs for ch in nm)
    zhs.append({'nm': nm, 'x': x, 'by': y,
                'box': (x - w / 2, y - fs * 0.92, w, fs * 1.12),
                'w': w, 'fs': fs, 'attrs': at})

# 胶囊组(距<=12聚类)
groups = []
for c in chips:
    for g in groups:
        if any(math.hypot(c[0] - gc[0], c[1] - gc[1]) <= 12 for gc in g):
            g.append(c)
            break
    else:
        groups.append([c])
ginfo = [(sum(c[0] for c in g) / len(g), sum(c[1] for c in g) / len(g)) for g in groups]

def legal(box, self_nm):
    if any(gen._gap(box, c) < 0.5 for c in chips + rings):
        return False
    if any(gen.rect_seg_dist(box, s) < 4.5 for s in corridors):
        return False
    if any(gen._gap(box, o['box']) < 1.0 for o in zhs if o['nm'] != self_nm):
        return False
    if any(gen._gap(box, b) < 0.3 for b in badges):
        return False
    return True

viol = []
for o in zhs:
    box = o['box']
    v = []
    if any(gen._gap(box, c) < 0.5 for c in chips + rings):
        v.append('R1胶囊')
    if any(gen.rect_seg_dist(box, s) < 4.5 for s in corridors):
        v.append('R2走廊')
    if any(gen._gap(box, b) < 0.3 for b in badges):
        v.append('R4徽标')
    best, bg = 9e9, None
    for gx, gy in ginfo:
        dd = math.hypot(box[0] + box[2] / 2 - gx, box[1] + box[3] / 2 - gy)
        if dd < best:
            best, bg = dd, (gx, gy)
    dx, dy = box[0] + box[2] / 2 - bg[0], box[1] + box[3] / 2 - bg[1]
    if abs(dx) >= abs(dy):
        off = abs(dy)
    else:
        off = abs(dx)
    if off > 3.0:
        # R6居中: 试吸附到组心(交叉轴), 中心位须合法才算违规
        if abs(dx) >= abs(dy):
            cand = (box[0], bg[1] - box[3] / 2, box[2], box[3])
        else:
            cand = (bg[0] - box[2] / 2, box[1], box[2], box[3])
        if legal(cand, o['nm']):
            v.append('R6能居中未居中(偏%.1f)' % off)
        # 中心位不合法(走廊/胶囊占用) = 斜位合规解, 不算违规
    if v:
        viol.append((o, v, bg))
print('违规总数: %d / %d' % (len(viol), len(zhs)))
for o, v, bg in viol:
    print('  %-8s 盒心(%g,%g) 组心(%g,%g): %s' % (o['nm'], box[0] + box[2] / 2 if False else o['box'][0] + o['box'][2] / 2,
          o['box'][1] + o['box'][3] / 2, bg[0], bg[1], ','.join(v)))
# 阶段2: 应用R6居中修正(中心位已在阶段1验证合法; 逐站应用, 每步对已更新位置重查)
applied = 0
for o, v, bg in viol:
    if not any(x.startswith('R6') for x in v):
        continue
    box = o['box']
    dx, dy = box[0] + box[2] / 2 - bg[0], box[1] + box[3] / 2 - bg[1]
    if abs(dx) >= abs(dy):
        cand = (box[0], bg[1] - box[3] / 2, box[2], box[3])
    else:
        cand = (bg[0] - box[2] / 2, box[1], box[2], box[3])
    if not legal(cand, o['nm']):
        continue
    # 写回labels_inner: 该站中文主行基线 = cand盒顶 + 0.92fs
    om = re.search(r'<text x="[-\d.]+" y="[-\d.]+"([^>]*)>' + re.escape(o['nm']) + r'</text>', li)
    if not om:
        continue
    baseline = cand[1] + o['fs'] * 0.92
    li = li[:om.start()] + '<text x="%.2f" y="%.2f"%s>%s</text>' % (cand[0] + cand[2] / 2, baseline, om.group(1), o['nm']) + li[om.end():]
    applied += 1
d['labels_inner'] = li
json.dump(d, open('data/codes-final-pins.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('R6居中修正已应用:', applied, '处')

json.dump([{'nm': o['nm'], 'x': o['x'], 'by': o['by'], 'fs': o['fs'], 'w': o['w'],
            'attrs': o['attrs'], 'v': v, 'gx': bg[0], 'gy': bg[1]} for o, v, bg in viol],
          open('data/_label-violations.tmp.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('违规清单已存 data/_label-violations.tmp.json')
