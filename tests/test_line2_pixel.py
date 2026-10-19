# -*- coding: utf-8 -*-
"""T1 像素门禁(2号线): 无头Edge内联渲染, 形态学分离走廊与文字彩边。
约8秒, 全量跑; 断网/无Edge时skip。"""
import shutil
import pytest
from conftest import LINE2
import verify_card_pixel as VP


@pytest.fixture(scope='module')
def pixel_result():
    if not shutil.which(VP.EDGE.replace('/', '\\')) and not os.path.exists(VP.EDGE):
        pytest.skip('无头Edge不可用')
    return {no: (ok, detail) for no, name, ok, detail in VP.run_gates(LINE2)}


import os  # noqa: E402


def test_p1_renders(pixel_result):
    assert pixel_result['P1'][0], pixel_result['P1'][1]


def test_p2_all_station_text(pixel_result):
    assert pixel_result['P2'][0], pixel_result['P2'][1]


def test_p3_text_not_touching_corridor(pixel_result):
    assert pixel_result['P3'][0], pixel_result['P3'][1]


def test_p4_badges_clean(pixel_result):
    assert pixel_result['P4'][0], pixel_result['P4'][1]
