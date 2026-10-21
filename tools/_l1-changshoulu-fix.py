# -*- coding: utf-8 -*-
"""1号线长寿路站上线路拐点(2026-10-21): 旧管线把圆画在H线西端外3.15px(1176.8,1012.5)靠7px碎屑connector接线;
按拐点站铁律挪到(1183.5,1010.25)=H西端拐角上, 碎屑已删(G16存量红根除)。标签随动。"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

CARD = 'assets/lines/line-1号线.svg'
s = open(CARD, encoding='utf-8').read()


def rep(old, new):
    global s
    assert s.count(old) == 1, 'not-unique(%d): %r' % (s.count(old), old[:60])
    s = s.replace(old, new)


rep('cx="1176.8" cy="1012.5" r="4.5" data-nm="长寿路"', 'cx="1183.5" cy="1010.25" r="4.5" data-nm="长寿路"')
rep('<text x="1176.8" y="992.5"', '<text x="1183.5" y="992.5"')
rep('<text x="1176.8" y="1000.0"', '<text x="1183.5" y="1000.0"')

open(CARD, 'w', encoding='utf-8').write(s)
print('1号线长寿路: 圆(1176.8,1012.5)->拐点(1183.5,1010.25), CN/EN随动')
