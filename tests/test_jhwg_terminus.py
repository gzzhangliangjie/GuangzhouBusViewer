# -*- coding: utf-8 -*-
"""回归: 嘉禾望岗终点标签(2026-10-19 用户验收位)
历史bug: 标签块内部间距被手改成11(标准7.5), 英文行低3.5px压到终点圆/线帽;
修复=终点规则(上中+净距G外推)重放, zh 588.8 / en 596.3, 钉位防漂移。
"""
import math
from conftest import LINE2
from verify_card import load

ZJ_Y, EN_Y, AX = 588.8, 596.3, 1473.8  # 验收钉位值(l2-labels.py PINNED 同源)


def _jhwg():
    c = load(LINE2)
    lb = next(l for l in c['labels'] if l['nm'] == '嘉禾望岗')
    return c, lb


def test_jhwg_pinned_position():
    _, lb = _jhwg()
    assert abs(lb['zy'] - ZJ_Y) < 0.05, 'zh基线漂移: %.1f (应为%.1f)' % (lb['zy'], ZJ_Y)
    assert abs(lb['ey'] - EN_Y) < 0.05, 'en基线漂移: %.1f (应为%.1f)' % (lb['ey'], EN_Y)


def test_jhwg_block_internal_gap_is_standard():
    """块内距恒=7.5(ZH_H 11 + GAP 1.5 + EN 6 - 11), 手改单行必被抓。"""
    _, lb = _jhwg()
    assert abs((lb['ey'] - lb['zy']) - 7.5) < 0.05, '块内距 %.1f ≠ 7.5' % (lb['ey'] - lb['zy'])


def test_jhwg_axis_aligned_above_terminus():
    c, lb = _jhwg()
    circ = next(cc for cc in c['circles'] if math.hypot(cc[0] - AX, cc[1] - 609.8) < 1)
    assert abs(lb['x'] - circ[0]) < 0.2, '未对齐终点圆心x轴'
    assert lb['zy'] < circ[1], '终点标签必须在站上方'


def test_jhwg_clearance_to_line_cap():
    """英文行底(含降部2.5)到终点圆外缘(r4.5+描边1)净距>4.5。
    验收真值5.5; 历史bug态(en=599.8)仅2.0, 必红。"""
    c, lb = _jhwg()
    circle_outer_top = 609.8 - (4.5 + 2 / 2)
    gap = circle_outer_top - (lb['ey'] + 2.5)
    assert gap > 4.5, '净距 %.1f 不足(贴线复发)' % gap
