# -*- coding: utf-8 -*-
# 4号线 大涌/塘坑/南横 三站分散(用户: 靠太近): 大涌-11.25 / 南横+11.25 (塘坑不动),
# 间距 22.3/22.7 -> 33.55/33.75 (与邻档广隆45/南沙客运港45协调); 钉在水平走廊上走廊不动。
import io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

card = 'assets/lines/line-4号线.svg'
s = open(card, encoding='utf-8').read()
edits = [
    ('<circle cx="2488.5" cy="1820.2" r="4.5" data-nm="大涌"',
     '<circle cx="2477.25" cy="1820.2" r="4.5" data-nm="大涌"'),
    ('<circle cx="2533.5" cy="1820.2" r="4.5" data-nm="南横"',
     '<circle cx="2544.75" cy="1820.2" r="4.5" data-nm="南横"'),
    ('<text x="2488.50" y="1804.60" text-anchor="middle" font-size="10.5" font-weight="500" fill="#1a1a1a">大涌</text>',
     '<text x="2477.25" y="1804.60" text-anchor="middle" font-size="10.5" font-weight="500" fill="#1a1a1a">大涌</text>'),
    ('<text x="2488.50" y="1812.10" text-anchor="middle" font-size="5.5" font-family="Arial, sans-serif" fill="#444444">Dachong</text>',
     '<text x="2477.25" y="1812.10" text-anchor="middle" font-size="5.5" font-family="Arial, sans-serif" fill="#444444">Dachong</text>'),
    ('<text x="2533.50" y="1804.60" text-anchor="middle" font-size="10.5" font-weight="500" fill="#1a1a1a">南横</text>',
     '<text x="2544.75" y="1804.60" text-anchor="middle" font-size="10.5" font-weight="500" fill="#1a1a1a">南横</text>'),
    ('<text x="2533.50" y="1812.10" text-anchor="middle" font-size="5.5" font-family="Arial, sans-serif" fill="#444444">Nanheng</text>',
     '<text x="2544.75" y="1812.10" text-anchor="middle" font-size="5.5" font-family="Arial, sans-serif" fill="#444444">Nanheng</text>'),
]
for o, n in edits:
    if o in s:
        s = s.replace(o, n)
    else:
        assert n in s, '两者皆无: ' + o[:60]   # 已应用过则跳过
open(card, 'w', encoding='utf-8').write(s)

p = 'data/codes-final-pins.json'
d = json.load(open(p, encoding='utf-8'))
net_edits = [
    ('<text x="2488.50" y="1812.20" font-size="7.5" text-anchor="middle">大涌</text>',
     '<text x="2477.25" y="1812.20" font-size="7.5" text-anchor="middle">大涌</text>'),
    ('<text x="2533.50" y="1812.20" font-size="7.5" text-anchor="middle">南横</text>',
     '<text x="2544.75" y="1812.20" font-size="7.5" text-anchor="middle">南横</text>'),
]
# 网络文字实际位先查再改(相对钉偏移不变: 大涌文字在钉左11.25? 先打印现状)
import re
lm = re.search(r'<g id="站名标注"[^>]*>(.*?)</g>', d['labels_inner'])
for nm in ('大涌', '南横'):
    m = re.search(r'<text[^>]*>' + nm + r'</text>', lm.group(1))
    print('labels_inner', nm, m.group(0) if m else 'NOT FOUND')
