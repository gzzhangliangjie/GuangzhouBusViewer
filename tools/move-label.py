# -*- coding: utf-8 -*-
"""单站文字规则化挪位工具(自锚定架构版): 直接编辑 codes SVG(唯一真源), 不经JSON。
语义: 初始位置 = 当前位(规则所算); 挪 = 沿指定方向阶梯平移(2/4/6/8/12/16/20pt),
每步全门禁合法性检查(胶囊/环0.5、走廊4.5、其他文字1.0、徽标0.3), 取首个合法平移。
用法: python tools/move-label.py 站名 方向   (方向=right/left/above/below)
写完必须跑 python tools/verify-all.py --quick 全链确认。
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

NM, DIR = sys.argv[1], sys.argv[2]
DX, DY = {'right': (1, 0), 'left': (-1, 0), 'above': (0, -1), 'below': (0, 1)}[DIR]

F = 'assets/lines/network-全网.codes.svg'
t = open(F, encoding='utf-8').read()
chips, rings, _ = gen.chip_elements(t)
corridors = gen.corridor_segments(t)
labels = {e['nm']: e for e in gen.text_elements(t)}
badges = [(b['x'], b['y'], b['w'], b['h']) for b in gen.badge_elements(t)]

e = labels.get(NM)
assert e, 'codes SVG 无该站文字'
fs = e['fs']
w = gen.part_w(NM, gen.FONT_CARD) / gen.FONT_CARD * fs

others = [(o['box'][0], o['box'][1], o['box'][2], o['box'][3], o['nm'])
          for k2, o in labels.items() if k2 != NM]

def legal(bx, by):
    box = (bx, by, w, fs * 1.12)
    if any(gen._gap(box, c) < 0.5 for c in chips + rings):
        return False
    if any(gen.rect_seg_dist(box, s) < 4.5 for s in corridors):
        return False
    if any(gen._gap(box, o[:4]) < 1.0 for o in others):
        return False
    if any(gen._gap(box, b) < 0.3 for b in badges):
        return False
    return True

moved = None
for step in (2.0, 4.0, 6.0, 8.0, 12.0, 16.0, 20.0):
    nx, ny = e['x'] + DX * step, e['y'] + DY * step
    if legal(nx, ny):
        moved = (nx, ny, step)
        break
assert moved, '阶梯内(<=20pt)无合法平移位: %s %s' % (NM, DIR)
nx, ny, step = moved
new_attrs = re.sub(r'\bx="[-\d.]+"', 'x="%.2f"' % nx, e['attrs'])
new_attrs = re.sub(r'\by="[-\d.]+"', 'y="%.2f"' % ny, new_attrs)
new_el = '<text %s>%s</text>' % (new_attrs, NM)
t = t.replace(e['el'], new_el)
import subprocess
subprocess.run(['python', 'tools/svg-snapshot.py', 'save',
                'auto:move-label %s %s' % (NM, DIR)], check=True)
open(F, 'w', encoding='utf-8').write(t)
print('规则平移: %s (%g,%g) -> (%g,%g) [%s %gpt] 全门禁合法' % (NM, e['x'], e['y'], nx, ny, DIR, step))
print('回滚: python tools/svg-snapshot.py restore')
print('下一步: python tools/sync-base.py && python tools/verify-station.py %s' % NM)
