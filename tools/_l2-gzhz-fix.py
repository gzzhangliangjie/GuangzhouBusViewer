# -*- coding: utf-8 -*-
"""2号线广州火车站钉位上滑(2026-10-21): (1336.5,858)->(1336.5,850)沿本线竖线,
与5号线(1336.5,839.25)/11号线(1336.5,848.25)纵排跨度18.75->10.75px, 广州火车站纵胶囊28.75->20.75(用户'太长'纠偏)。"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

CARD = 'assets/lines/line-2号线.svg'
s = open(CARD, encoding='utf-8').read()


def rep(old, new):
    global s
    assert s.count(old) == 1, 'not-unique(%d): %r' % (s.count(old), old[:60])
    s = s.replace(old, new)


rep('cy="858.0" r="4.5" style="fill:#FFFFFF;stroke:#1E88E5;stroke-width:2" data-nm="广州火车站"',
    'cy="850.0" r="4.5" style="fill:#FFFFFF;stroke:#1E88E5;stroke-width:2" data-nm="广州火车站"')
rep('<text x="1290.5" y="859.8"', '<text x="1290.5" y="851.8"')
rep('<text x="1290.5" y="867.2"', '<text x="1290.5" y="859.2"')

open(CARD, 'w', encoding='utf-8').write(s)
print('2号线广州火车站: 钉(1336.5,858)->(1336.5,850), CN/EN随动')
