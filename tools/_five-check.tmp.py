# -*- coding: utf-8 -*-
# 五站精查: 文字vs站钉交叉轴偏移 / 徽标vs文字 沿轴间隙+交叉轴偏移
import io, sys, re, math, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'tools')
import importlib.util
spec = importlib.util.spec_from_file_location('gen', 'tools/gen-codes-cards.py')
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

STATIONS = {
    '大学城南': {'pin': (1966.5, 1401.8), 'badge_key': '12', 'badge_cur': (1994.65, 1415.07)},
    '香雪':     {'pin': (2308.5, 740.2),  'badge_key': '6',  'badge_cur': (2323.13, 746.13)},
    '燕山':     {'pin': (2135.75, 693.65), 'badge_key': '7',  'badge_cur': (2115.75, 666.77)},
    '镇龙':     {'pin': (2336.4, 377.1),  'badge_key': '14', 'badge_cur': (2317.66, 344.53)},
    '增城广场': {'pin': (2740.5, 362.2),  'badge_key': '21', 'badge_cur': (2755.13, 368.13)},
}
t = open('assets/lines/network-全网.codes.svg', encoding='utf-8').read()
lm = re.search(r'<g id="站名标注"[^>]*>(.*?)</g>', t, re.S)
for nm, info in STATIONS.items():
    m = re.search(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*>' + nm + r'</text>', lm.group(1))
    x, y = float(m.group(1)), float(m.group(2))
    fs = 7.5
    w = gen.part_w(nm, gen.FONT_CARD) / gen.FONT_CARD * fs
    box = gen.text_box({'x': x, 'y': y, 'fs': fs, 'content': nm})
    tcx, tcy = box[0] + box[2] / 2, box[1] + box[3] / 2
    px, py = info['pin']
    dx, dy = tcx - px, tcy - py
    t_axis = '横向' if abs(dx) >= abs(dy) else '纵向'
    t_off = abs(dy) if t_axis == '横向' else abs(dx)
    bk = info['badge_cur']
    bw, bh = 25.12, 13.5
    bcx, bcy = bk[0] + bw / 2, bk[1] + bh / 2
    bdx, bdy = bcx - tcx, bcy - tcy
    if abs(bdx) >= abs(bdy):
        b_side = '右' if bdx > 0 else '左'
        b_gap = abs(bdx) - bw / 2 - box[2] / 2
        b_off = abs(bdy)
    else:
        b_side = '下' if bdy > 0 else '上'
        b_gap = abs(bdy) - bh / 2 - box[3] / 2
        b_off = abs(bdx)
    print('%-6s 文字(%g,%g) 站侧%s 交叉轴偏%.1f | 徽标%s侧 间隙%.1f 交叉轴偏%.1f' %
          (nm, x, y, t_axis, t_off, b_side, b_gap, b_off))
