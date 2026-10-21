# -*- coding: utf-8 -*-
"""1号线芳村钉位外科(2026-10-21): (1112.7,1142.8)->(1113.6,1140.0)沿本线62.6°斜段上滑2.9px,
与22号线(1102.5,1140)/11号线(1120.5,1140)同y横排→芳村横向胶囊(用户定向规则)。标签随动。"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

CARD = 'assets/lines/line-1号线.svg'
s = open(CARD, encoding='utf-8').read()


def rep(old, new):
    global s
    assert s.count(old) == 1, 'not-unique(%d): %r' % (s.count(old), old[:60])
    s = s.replace(old, new)


rep('cx="1112.7" cy="1142.8" r="4.5" data-nm="芳村"', 'cx="1113.6" cy="1140.0" r="4.5" data-nm="芳村"')
rep('<text x="1089.8" y="1144.5" text-anchor="middle" font-size="10.5" font-weight="500" fill="#1a1a1a">芳村</text>',
    '<text x="1090.7" y="1141.7" text-anchor="middle" font-size="10.5" font-weight="500" fill="#1a1a1a">芳村</text>')
rep('<text x="1089.8" y="1152.0"', '<text x="1090.7" y="1149.2"')

open(CARD, 'w', encoding='utf-8').write(s)
print('1号线芳村: 钉(1112.7,1142.8)->(1113.6,1140.0), CN/EN随动')
