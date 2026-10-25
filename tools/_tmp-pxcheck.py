# -*- coding: utf-8 -*-
"""四并圆点像素验收: 采样共享圆黑环+两线走廊色 (zone原点/scale与_svg-crop一致)"""
import io, sys
from PIL import Image
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

CASES = [
    # (png, ox, oy, 圆心map, 线A采样map+色, 线B采样map+色)
    ('data/_net-zsb.png', 1050, 890, (1120.5, 947.25),
     [(1120.5, 930.0, 'E53935', '5号线V红'), (1120.5, 965.0, 'FFCC66', '11号线V黄'),
      (1129.5, 944.0, 'FFCC66', '11号线短弦黄'), (1090.0, 956.25, 'E53935', '5号线H红')]),
    ('data/_net-chq.png', 1120, 855, (1174.5, 902.25),
     [(1174.5, 880.0, '00897B', '8号线V青'), (1198.0, 878.5, 'FFCC66', '11号线斜黄'),
      (1145.0, 931.5, 'FFCC66', '11号线斜黄2')]),
    ('data/_net-ryf.png', 1080, 995, (1120.5, 1032.75),
     [(1100.0, 1012.25, '80286c', '6号线斜紫'), (1120.5, 1058.0, 'FFCC66', '11号线V黄')]),
    ('data/_net-zl.png', 2260, 345, (2335.5, 389.2),
     [(2324.0, 389.2, '6D4C41', '14号线stub棕'), (2315.25, 398.25, '6D4C41', '14号线斜棕'),
      (2318.0, 406.0, '1A237E', '21号线斜')]),
]

def hx(p):
    return '%02X%02X%02X' % p[:3]

def near(a, b, tol=60):
    return all(abs(x - y) <= tol for x, y in zip(a, b))

for png, ox, oy, (cx, cy), probes in CASES:
    img = Image.open(png).convert('RGB')
    sc = img.width / (lambda: 0)() if False else None
    # scale由脚本固定4
    sc = 4.0
    px = lambda mx, my: img.getpixel((int(round((mx - ox) * sc)), int(round((my - oy) * sc))))
    print('==== %s 圆心(%s,%s) ====' % (png, cx, cy))
    c = px(cx, cy)
    lum = []
    for rr in [3.0 + 0.05 * i for i in range(70)]:
        for a in range(0, 8):
            import math as _m
            mx2, my2 = cx + rr * _m.cos(a * 0.7854), cy + rr * _m.sin(a * 0.7854)
            lum.append(sum(px(mx2, my2)))
    ring_min = min(lum)
    print('  圆心色=%s(期望白) 环最小亮度=%d(期望<200)' % (hx(c), ring_min))
    ok = near(c, (255, 255, 255), 40) and ring_min < 200
    for mx, my, col, nm in probes:
        p = px(mx, my)
        exp = tuple(int(col[i:i + 2], 16) for i in (0, 2, 4))
        good = near(p, exp)
        ok = ok and good
        print('  %s @(%s,%s)=%s 期望#%s %s' % (nm, mx, my, hx(p), col, 'OK' if good else '**FAIL**'))
    print('  => %s' % ('PASS' if ok else 'FAIL'))
