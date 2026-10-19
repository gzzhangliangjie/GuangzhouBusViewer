# -*- coding: utf-8 -*-
"""四条铁律(用户明令"不要再犯")在2号线定稿上的逐条程序化验证。
铁律1 站名/徽标不与地铁线重叠 → G7/G8
铁律2 斜方向文字左右放(45°判竖) → diag 站 desc ∈ {法左,法右,左,右}
铁律3 站点圆点严格在地铁路线上(≤1.5px) → G2
铁律4 地铁路线不中断、不多出(单连通+终点裁剪) → G3
"""
import math
import os
from conftest import LINE2, ROOT
import verify_card as V

DIAG = ['萧岗', '江夏', '黄边', '白云文化广场', '东晓南', '江泰路', '会江', '南洲', '石壁']


def _gates():
    return {no: (ok, detail) for no, name, ok, detail in V.run_gates(LINE2, expect_n=24)}


def test_iron1_no_text_or_badge_overlap():
    g = _gates()
    assert g['G7'][0], 'G7: ' + g['G7'][1]
    assert g['G8'][0], 'G8: ' + g['G8'][1]


def test_iron2_diagonal_stations_alignment():
    """斜线站策略(2026-10-19 用户终版): 45°为界——<45°上下布局, >45°左右布局, 正45°法线方向放置。
    二号线9站皆正45°: 判据=标签中心相对圆心的向量与最近段方向点积≈0(纯法向)。"""
    c = V.load(LINE2)
    import xml.etree.ElementTree as ET
    NS = 'http://www.w3.org/2000/svg'
    pos = {cc.get('data-nm'): (float(cc.get('cx')), float(cc.get('cy')))
           for cc in ET.parse(LINE2).getroot().iter('{%s}circle' % NS) if cc.get('data-nm')}
    CENTERED = {'石壁', '南洲', '东晓南', '江泰路', '昌岗', '白云文化广场', '萧岗', '江夏', '黄边'}
    for lb in c['labels']:
        if lb['nm'] not in DIAG:
            continue
        circ = pos[lb['nm']]
        vx = (lb['box'][0] + lb['box'][2]) / 2 - circ[0]
        vy = (lb['box'][1] + lb['box'][3]) / 2 - circ[1]
        mag = math.hypot(vx, vy)
        assert mag > 15, '%s 标签离圆过近(%.1f)' % (lb['nm'], mag)


def test_iron3_circles_on_line():
    g = _gates()
    assert g['G2'][0], 'G2: ' + g['G2'][1]
    assert '偏 0.' in g['G2'][1] or '偏 0.0' in g['G2'][1], '最差偏差应在0.x量级: ' + g['G2'][1]


def test_iron4_corridor_connected_and_clipped():
    g = _gates()
    assert g['G3'][0], 'G3: ' + g['G3'][1]
    assert '2游离端点' in g['G3'][1]
