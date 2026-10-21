# -*- coding: utf-8 -*-
"""2号线嘉禾望岗终点回撤(2026-10-21): 钉(1498.5,578.2)->(1498.5,585.0)=45°斜线端点,
删6.8px竖stub(走廊直终于斜线端), 与3号线(570)/14号线(578.2)纵排15px→竖向胶囊(用户定向规则)。"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

CARD = 'assets/lines/line-2号线.svg'
s = open(CARD, encoding='utf-8').read()


def rep(old, new):
    global s
    assert s.count(old) == 1, 'not-unique(%d): %r' % (s.count(old), old[:60])
    s = s.replace(old, new)


rep('cy="578.2" r="4.5" style="fill:#FFFFFF;stroke:#1E88E5;stroke-width:2" data-nm="嘉禾望岗"',
    'cy="585.0" r="4.5" style="fill:#FFFFFF;stroke:#1E88E5;stroke-width:2" data-nm="嘉禾望岗"')
rep('<line x1="1498.5" y1="585.0" x2="1498.5" y2="578.2" '
    'style="fill:none;stroke:#1E88E5;stroke-width:7;stroke-linecap:round" />', '')
rep('<text x="1498.5" y="557.2"', '<text x="1498.5" y="564.0"')
rep('<text x="1498.5" y="564.7"', '<text x="1498.5" y="571.5"')
rep('translate(1491.81 526.7)" data-box="1491.8,526.7,1505.2,540.2"',
    'translate(1491.81 533.5)" data-box="1491.8,533.5,1505.2,547.0"')

open(CARD, 'w', encoding='utf-8').write(s)
print('2号线嘉禾望岗: 钉(1498.5,578.2)->(1498.5,585.0), 删stub, CN/EN/chip随动+6.8')
