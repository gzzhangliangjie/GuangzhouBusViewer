# -*- coding: utf-8 -*-
"""1号线走廊碎屑清理(2026-10-21): 关节(1183.5,1010.25)处重复两次的7.1px碎屑段
(一份一位小数格式+一份两位小数格式, 旧管线遗留), G16当折角误红(存量问题, 今晨G16上线后首检发现)。"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

CARD = 'assets/lines/line-1号线.svg'
s = open(CARD, encoding='utf-8').read()

for old in ('<line x1="1183.5" y1="1010.25" x2="1176.8" y2="1012.5" '
            'style="fill:none;stroke:#FDD835;stroke-width:7;stroke-linecap:round" />',
            '<line x1="1176.80" y1="1012.50" x2="1183.50" y2="1010.25" '
            'style="fill:none;stroke:#FDD835;stroke-width:7;stroke-linecap:round" />'):
    assert s.count(old) == 1, 'debris copy not found: %r' % old[:60]
    s = s.replace(old, '')
open(CARD, 'w', encoding='utf-8').write(s)
print('1号线: 删除关节碎屑段x2 (1176.8,1012.5)-(1183.5,1010.25)')
