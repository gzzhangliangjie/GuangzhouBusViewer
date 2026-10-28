# -*- coding: utf-8 -*-
"""单枚徽标规则化挪位工具(move-label的徽标等价, 2026-10-25): 直接编辑codes SVG(唯一真源)。
语义: 当前位起沿指定方向阶梯平移(2/4/6/8/12/16/20pt), 每步全门禁合法性检查
(与build-network _place_ok 2026-10-24统一口径同源):
  走廊>=6.5 且四外扩角点>=4.2 / 编号胶囊牌环>=0.3 / 站名文字盒>=0.3 / 他徽标>=6.0 /
  站圆>=r+3 / 换乘胶囊>=半宽5+3(标记走gen.marker_elements, 从底图两组解析)
取首个合法平移位。同终点多枚徽标(如西塱1号线/10号线)用线名消歧。--dry只算不写。
用法: python tools/move-badge.py 终点站名 方向 [线名] [--dry]   (方向=right/left/above/below)
写完必须跑: python tools/sync-base.py && python tools/verify-station.py 终点站名
"""
import io, os, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import importlib.util
spec = importlib.util.spec_from_file_location('gen', os.path.join(ROOT, 'tools', 'gen-codes-cards.py'))
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

DRY = '--dry' in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith('--')]
TERM, DIR = args[0], args[1]
LN = args[2] if len(args) > 2 else None
if LN:
    LN = gen.badge_text_to_line(LN)
DX, DY = {'right': (1, 0), 'left': (-1, 0), 'above': (0, -1), 'below': (0, 1)}[DIR]

F = 'assets/lines/network-全网.codes.svg'
t = open(F, encoding='utf-8').read()
base = open('assets/lines/network-全网.svg', encoding='utf-8').read()

badges = gen.badge_elements(t)
cands = [i for i, b in enumerate(badges) if b['term'] == TERM and (not LN or b['key'] == LN)]
if not cands:
    same_term = [b['key'] for b in badges if b['term'] == TERM]
    if same_term:
        raise SystemExit('终点"%s"无 %s 徽标, 该站现有: %s' % (TERM, LN or '匹配', '、'.join(same_term)))
    terms = sorted(set(b['term'] for b in badges if b['term']))
    raise SystemExit('无 data-term="%s" 的徽标。现有终点: %s' % (TERM, '、'.join(terms)))
if len(cands) > 1:
    raise SystemExit('终点"%s"有%d枚徽标(%s), 加线名消歧: python tools/move-badge.py %s 方向 线号'
                     % (TERM, len(cands), '、'.join(badges[i]['key'] for i in cands), TERM))
bi = cands[0]
b = badges[bi]

chips, rings, _ = gen.chip_elements(t)
corridors = gen.corridor_segments(t)
text_boxes = [e['box'] for e in gen.text_elements(t)]
markers = gen.marker_elements(base)

def seg_pt_dist(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    l2 = vx * vx + vy * vy
    tt = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / l2))
    return ((px - ax - tt * vx) ** 2 + (py - ay - tt * vy) ** 2) ** 0.5

def legal(nx, ny):
    rect = (nx, ny, b['w'], b['h'])
    corners = [(rect[0] - 3.0, rect[1] - 3.0),
               (rect[0] + rect[2] + 3.0, rect[1] - 3.0),
               (rect[0] - 3.0, rect[1] + rect[3] + 3.0),
               (rect[0] + rect[2] + 3.0, rect[1] + rect[3] + 3.0)]
    for s in corridors:
        if gen.rect_seg_dist(rect, s) < 6.5:
            return False
        if any(seg_pt_dist(cx, cy, s[0], s[1], s[2], s[3]) < 4.2 for cx, cy in corners):
            return False
    for c in list(chips) + list(rings):
        if gen._gap(rect, c) < 0.3:
            return False
    for tb in text_boxes:
        if gen._gap(rect, tb) < 0.3:
            return False
    for j, ob in enumerate(badges):
        if j == bi:
            continue
        if gen._gap(rect, (ob['x'], ob['y'], ob['w'], ob['h'])) < 6.0:
            return False
    for cx, cy, r, nm in markers['circles']:
        qx = min(max(cx, rect[0]), rect[0] + rect[2])
        qy = min(max(cy, rect[1]), rect[1] + rect[3])
        if ((cx - qx) ** 2 + (cy - qy) ** 2) ** 0.5 < r + 3.0:
            return False
    for hull, nm in markers['capsules']:
        edges = ([(hull[0], hull[1])] if len(hull) == 2
                 else [(hull[k], hull[(k + 1) % len(hull)]) for k in range(len(hull))])
        for a, p in edges:
            if gen.rect_seg_dist(rect, (a[0], a[1], p[0], p[1])) < 5.0 + 3.0:
                return False
    return True

moved = None
for step in (2.0, 4.0, 6.0, 8.0, 12.0, 16.0, 20.0):
    nx, ny = b['x'] + DX * step, b['y'] + DY * step
    if legal(nx, ny):
        moved = (nx, ny, step)
        break
assert moved, '阶梯内(<=20pt)无合法平移位: %s %s %s' % (TERM, DIR, LN or '')
nx, ny, step = moved
print('规则平移: %s %s (%g,%g) -> (%.2f,%.2f) [%s %gpt] 全门禁合法'
      % (b['key'], TERM, b['x'], b['y'], nx, ny, DIR, step))
if DRY:
    print('(dry-run, 未写盘)')
    sys.exit(0)

# 元素级独立替换(禁全局transform串replace——撞重复串会换错徽标)
hit = None
for m in re.finditer(r'<g\s([^>]*data-badge="header"[^>]*)>(.*?)</g>', t, re.S):
    trm = re.search(r'translate\(([-\d.]+) ([-\d.]+)\)', m.group(1))
    tm2 = re.search(r'data-term="([^"]+)"', m.group(1))
    if (tm2 and tm2.group(1) == TERM and trm
            and (float(trm.group(1)), float(trm.group(2))) == (b['x'], b['y'])):
        hit = m
        break
assert hit, '未定位到目标徽标元素(写回失败, 文件未动)'
sc_m = re.search(r'scale\(([\d.]+)\)', hit.group(1))
new_el = re.sub(r'transform="[^"]*"',
                'transform="translate(%.2f %.2f) scale(%s)"' % (nx, ny, sc_m.group(1)),
                hit.group(0), count=1)
# data-anchor 累计(写入契约: 属性owner=move-badge; nudge形=相对自动位的累计偏移, 随codes自锚携带)
_an = re.search(r'data-anchor="([^"]*)"', hit.group(1))
_odx, _ody, _why = 0.0, 0.0, ''
if _an and _an.group(1).startswith('nudge:'):
    _parts = _an.group(1)[6:].split(',')
    _odx, _ody = float(_parts[0]), float(_parts[1])
    _why = _parts[2] if len(_parts) > 2 else ''
_why = (_why + '+' if _why else '') + '%s%gpt' % (DIR, step)
new_el = re.sub(r'\s*data-anchor="[^"]*"', '', new_el, count=1)
new_el = re.sub(r'(<g\s[^>]*?)>',
                r'\1 data-anchor="nudge:%.2f,%.2f,%s">' % (_odx + DX * step, _ody + DY * step, _why),
                new_el, count=1)
t = t.replace(hit.group(0), new_el, 1)
import subprocess
subprocess.run(['python', 'tools/svg-snapshot.py', 'save',
                'auto:move-badge %s %s' % (TERM, DIR)], check=True)
open(F, 'w', encoding='utf-8').write(t)
print('写盘完成。回滚: python tools/svg-snapshot.py restore')
print('下一步: python tools/sync-base.py && python tools/verify-station.py %s' % TERM)
