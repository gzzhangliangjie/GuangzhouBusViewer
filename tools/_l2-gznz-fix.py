# -*- coding: utf-8 -*-
"""2号线广州南站并胶囊微调(2026-10-21): 终点沿45°走廊上滑(1392.8,1599.8)->(1399.5,1593.0),
与22号线钉(1399.5,1593)重合, 7号线(1386,1593)不动 → 三线横排13.5px → 横向小胶囊。
外科: 圆+走廊末段+CN/EN/chip随动(走廊方向不变, 纯平移Δ=(+6.7,-6.8))。用法: python tools/_l2-gznz-fix.py
"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

CARD = 'assets/lines/line-2号线.svg'
s = open(CARD, encoding='utf-8').read()


def rep(old, new):
    global s
    assert s.count(old) == 1, 'not-unique(%d): %r' % (s.count(old), old[:60])
    s = s.replace(old, new)


rep('cx="1392.8" cy="1599.8" r="4.5"', 'cx="1399.5" cy="1593.0" r="4.5"')
rep('<line x1="1489.5" y1="1503.0" x2="1392.8" y2="1599.8"',
    '<line x1="1489.5" y1="1503.0" x2="1399.5" y2="1593.0"')
rep('<text x="1392.8" y="1620.8"', '<text x="1399.5" y="1614.0"')
rep('<text x="1392.8" y="1628.3"', '<text x="1399.5" y="1621.5"')
rep('translate(1386.06 1643.3)" data-box="1386.1,1643.3,1399.5,1656.8"',
    'translate(1392.76 1636.5)" data-box="1392.8,1636.5,1406.2,1650.0"')

open(CARD, 'w', encoding='utf-8').write(s)
print('2号线广州南站: 钉(1392.8,1599.8)->(1399.5,1593.0), 走廊/CN/EN/chip随动')
