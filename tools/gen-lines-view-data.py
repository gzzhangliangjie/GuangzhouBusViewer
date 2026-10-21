# -*- coding: utf-8 -*-
"""扫描 assets/lines/ 提取卡，生成 data/lines-view-data.js（线路图查看页的数据真源）。

主卡 = line-<线名>.svg；分段/来源卡 = line-<线名>-NN.svg。
线色取 data/_line-colors.json，缺省回退 #607d8b。
幂等：重跑覆盖。用法: python tools/gen-lines-view-data.py
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINES_DIR = os.path.join(ROOT, 'assets', 'lines')
OUT = os.path.join(ROOT, 'data', 'lines-view-data.js')

ORDER = ['1号线', '2号线', '3号线', '4号线', '5号线', '6号线', '7号线', '8号线',
         '9号线', '10号线', '11号线', '12号线', '13号线', '14号线', '18号线',
         '21号线', '22号线', '广佛线', 'APM线']

colors = {}
with open(os.path.join(ROOT, 'data', '_line-colors.json'), encoding='utf-8') as f:
    for e in json.load(f):
        colors[e['zh']] = e['color']

pat = re.compile(r'^line-(.+?)(?:-(\d+))?\.svg$')
groups = {}
for fn in os.listdir(LINES_DIR):
    if fn.startswith('line-color-'):
        continue  # 共色采样碎片，非线卡
    m = pat.match(fn)
    if not m:
        continue
    name, seg = m.group(1), m.group(2)
    groups.setdefault(name, {'card': None, 'segs': []})
    if seg is None:
        assert groups[name]['card'] is None, f'{name} 出现多个主卡'
        groups[name]['card'] = fn
    else:
        groups[name]['segs'].append(seg)

for name, g in groups.items():
    assert g['card'], f'{name} 只有分段卡没有主卡: {g}'

lines = []
for name in ORDER:
    g = groups.pop(name)
    lines.append({
        'name': name,
        'color': colors.get(name, '#607d8b'),
        'card': 'assets/lines/' + g['card'],
        'segs': [{'file': f'assets/lines/line-{name}-{s}.svg', 'tag': s}
                 for s in sorted(g['segs'], key=int)],
    })
assert not groups, f'ORDER 之外还有线: {sorted(groups)}'

with open(OUT, 'w', encoding='utf-8') as f:
    f.write('// 由 tools/gen-lines-view-data.py 生成，勿手改；重跑该工具再生成。\n')
    f.write('window.LINES_VIEW = ' + json.dumps({'lines': lines}, ensure_ascii=False, indent=1) + ';\n')

print(f'OK {len(lines)} 线, 分段卡 {sum(len(l["segs"]) for l in lines)} 张 -> {OUT}')
