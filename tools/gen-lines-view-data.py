# -*- coding: utf-8 -*-
"""扫描 assets/lines/ 主卡，生成 data/lines-view-data.js（线路图查看页的数据真源）。

主卡 = line-<线名>.svg（line-color-* 共色采样碎片不算）；全网合成图 network-全网.svg 置顶。
历史 line-<线名>-NN.svg 来源卡已删（2026-10-21 用户定稿：中间结果不再展示）。
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

groups = {}
for fn in os.listdir(LINES_DIR):
    if fn.startswith('line-color-'):
        continue  # 共色采样碎片，非线卡
    m = re.match(r'^line-(.+)\.svg$', fn)
    if not m:
        continue
    name = m.group(1)
    assert name not in groups, f'{name} 出现多个主卡'
    groups[name] = fn

assert set(groups) == set(ORDER), f'主卡与 ORDER 不一致: 多={sorted(set(groups) - set(ORDER))} 少={sorted(set(ORDER) - set(groups))}'

lines = []
# 全网合成图置顶(tools/build-network.py 生成, 同名站唯一标记)
net = os.path.join(LINES_DIR, 'network-全网.svg')
assert os.path.exists(net), '缺 assets/lines/network-全网.svg, 先跑 python tools/build-network.py'
lines.append({
    'name': '全网',
    'color': '#1a1a1a',
    'card': 'assets/lines/network-全网.svg',
    'kind': 'network',
})
for name in ORDER:
    lines.append({
        'name': name,
        'color': colors.get(name, '#607d8b'),
        'card': 'assets/lines/' + groups[name],
    })

with open(OUT, 'w', encoding='utf-8') as f:
    f.write('// 由 tools/gen-lines-view-data.py 生成，勿手改；重跑该工具再生成。\n')
    f.write('window.LINES_VIEW = ' + json.dumps({'lines': lines}, ensure_ascii=False, indent=1) + ';\n')

print(f'OK {len(lines) - 1} 线 + 全网 -> {OUT}')
