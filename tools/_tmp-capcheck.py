# -*- coding: utf-8 -*-
"""三胶囊像素验收: 白内心+黑环边缘+各线走廊色到边"""
import io, sys
from PIL import Image
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

CASES = [
    ('data/_net-xizhan.png', 1075, 1250,
     [('白心', 1107.0, 1280.2, 'FFFFFF', True),
      ('黑环左', 1096.5, 1280.25, '000000', 'dark'),
      ('黑环上', 1107.0, 1274.0, '000000', 'dark'),
      ('22号线V红', 1102.5, 1258.0, 'DD2C00', True),
      ('10号线斜蓝', 1116.0, 1290.4, '90CAF9', True),
      ('广佛线W', 1085.0, 1280.3, None, 'report'),
      ('1号线V', 1111.5, 1258.0, None, 'report')]),
    ('data/_net-gznz.png', 1368, 1573,
     [('白心', 1392.8, 1593.0, 'FFFFFF', True),
      ('黑环左', 1380.6, 1593.0, '000000', 'dark'),
      ('7号线斜绿', 1404.0, 1579.3, '7CB342', True),
      ('2号线斜蓝', 1413.4, 1579.1, '1E88E5', True),
      ('22号线斜红', 1414.0, 1607.5, 'DD2C00', True)]),
    ('data/_net-panyu.png', 1832, 1628,
     [('白心', 1858.5, 1653.6, 'FFFFFF', True),
      ('黑环上', 1858.5, 1643.6, '000000', 'dark'),
      ('3号线H橙', 1840.0, 1649.0, 'ECA154', True),
      ('22号线H红', 1840.0, 1658.25, 'DD2C00', True),
      ('18号线斜蓝', 1850.0, 1649.75, '3949AB', True)]),
]


def hx(p):
    return '%02X%02X%02X' % p[:3]


def near(a, b, tol=60):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


for png, ox, oy, probes in CASES:
    img = Image.open(png).convert('RGB')
    print('====', png)
    ok = True
    for nm, mx, my, col, mode in probes:
        p = img.getpixel((int(round((mx - ox) * 4)), int(round((my - oy) * 4))))
        if mode == 'report':
            print('  %s @(%s,%s)=%s (报告)' % (nm, mx, my, hx(p)))
            continue
        if mode == 'dark':
            good = sum(p) < 240
        else:
            exp = tuple(int(col[i:i + 2], 16) for i in (0, 2, 4))
            good = near(p, exp) if col == 'FFFFFF' else near(p, exp)
        ok = ok and good
        print('  %s @(%s,%s)=%s %s' % (nm, mx, my, hx(p), 'OK' if good else '**FAIL**'))
    print('  =>', 'PASS' if ok else 'FAIL')
