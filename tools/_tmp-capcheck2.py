# -*- coding: utf-8 -*-
"""新增/改造枢纽像素验收: 白心+黑环+本线走廊色(5站)"""
import io, sys
from PIL import Image
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

CASES = [
    # (png, ox, oy, [(名称, mx, my, 期望RGB|None=暗, 模式)])
    ('data/_n-jhwg.png', 1470, 505, [
        ('嘉禾望岗白心', 1498.5, 577.6, 'FFFFFF', 'near'),
        ('嘉禾望岗黑环上', 1498.5, 568.0, None, 'dark'),
        ('嘉禾望岗黑环下', 1498.5, 587.0, None, 'dark'),
        ('3号线V橙上', 1498.5, 545.0, 'ECA154', 'near'),
        ('2号线斜蓝', 1478.0, 602.0, '1E88E5', 'near'),
        ('14号线H棕', 1520.0, 578.2, '6D4C41', 'near')]),
    ('data/_n-zhenlong2.png', 2310, 365, [
        ('镇龙白心', 2338.8, 386.0, 'FFFFFF', 'near'),
        ('镇龙黑环SW', 2331.5, 393.5, None, 'dark'),
        ('14号线stub棕', 2328.0, 389.2, '6D4C41', 'near'),
        ('21号线斜蓝', 2347.5, 377.0, '1A237E', 'near')]),
    ('data/_n-zsb2.png', 1085, 925, [
        ('中山八白心', 1116.0, 951.7, 'FFFFFF', 'near'),
        ('中山八黑环', 1108.0, 959.5, None, 'dark'),
        ('5号线H红', 1095.0, 956.25, 'E53935', 'near'),
        ('11号线V黄', 1120.5, 930.0, 'FFCC66', 'near')]),
    ('data/_n-gzd.png', 1625, 825, [
        ('广州东站白心', 1660.5, 854.3, 'FFFFFF', 'near'),
        ('广州东站黑环上', 1660.5, 845.5, None, 'dark'),
        ('广州东站黑环下', 1660.5, 863.0, None, 'dark'),
        ('11号线H黄', 1640.0, 848.25, 'FFCC66', 'near'),
        ('3号线V橙', 1660.5, 875.0, 'ECA154', 'near')]),
    ('data/_n-zjxc.png', 1635, 1040, [
        ('珠江新城圆白心', 1660.5, 1064.2, 'FFFFFF', 'near'),
        ('珠江新城黑环', 1660.5, 1058.8, None, 'dark'),
        ('5号线H红', 1650.0, 1064.2, 'E53935', 'near'),
        ('3号线V橙', 1660.5, 1085.0, 'ECA154', 'near')]),
]


def hx(p):
    return '%02X%02X%02X' % p[:3]


ok_all = True
for png, ox, oy, probes in CASES:
    img = Image.open(png).convert('RGB')
    print('====', png)
    ok = True
    for nm, mx, my, col, mode in probes:
        p = img.getpixel((int(round((mx - ox) * 4)), int(round((my - oy) * 4))))
        if mode == 'dark':
            good = sum(p) < 240
        else:
            exp = tuple(int(col[i:i + 2], 16) for i in (0, 2, 4))
            good = all(abs(a - b) <= 60 for a, b in zip(p, exp))
        ok = ok and good
        print('  %s @(%s,%s)=%s %s' % (nm, mx, my, hx(p), 'OK' if good else '**FAIL**'))
    ok_all = ok_all and ok
    print('  =>', 'PASS' if ok else 'FAIL')
print('TOTAL:', 'PASS' if ok_all else 'FAIL')
