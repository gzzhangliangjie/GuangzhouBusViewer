# -*- coding: utf-8 -*-
"""门禁自检(突变测试): 按历史bug污染卡片副本, 断言对应门禁必然翻红。
门禁若抓不住这些, 全绿就是假阴性。每个用例=一次真实翻车史。
锚串一律按站名/结构正则定位——标签重放会改坐标, 绝不硬编码 xy。
"""
import re
import pytest
from conftest import LINE2
from verify_card import run_gates


def _mutated(tmp_path, pattern, repl, name='mut.svg', flags=0):
    s = open(LINE2, encoding='utf-8').read()
    s2, n = re.subn(pattern, repl, s, count=1, flags=flags)
    assert n == 1, '锚串不存在: %r' % pattern[:60]
    p = tmp_path / name
    p.write_text(s2, encoding='utf-8')
    return str(p)


def _fails(path):
    R = run_gates(path, expect_n=24)
    return {no for no, name, ok, detail in R if not ok}


def test_mutation_jhwg_block_touches_line(tmp_path):
    """嘉禾望岗整块下压到线帽(2026-10-19贴线bug的极端态) → G7必红。"""
    s = open(LINE2, encoding='utf-8').read()
    s, n1 = re.subn(r'(<text x="[\d.]+" y=")[\d.]+("[^>]*>嘉禾望岗</text>)', r'\g<1>600\g<2>', s, count=1)
    s, n2 = re.subn(r'(<text x="[\d.]+" y=")[\d.]+("[^>]*font-size="5.5"[^>]*>Jiahewanggang</text>)',
                    r'\g<1>607.5\g<2>', s, count=1)
    assert n1 == 1 and n2 == 1
    p = tmp_path / 'mut.svg'
    p.write_text(s, encoding='utf-8')
    assert 'G7' in _fails(str(p))


def test_mutation_label_deleted(tmp_path):
    """删除一站标签(结构化站名缺字) → G4/G5必红。"""
    p = _mutated(tmp_path, r'<text x="[\d.]+" y="[\d.]+"[^>]*>江夏</text>', '')
    f = _fails(p)
    assert f & {'G4', 'G5'}


def test_mutation_circle_off_line(tmp_path):
    """站圆挪离走廊(铁律3) → G2必红。"""
    p = _mutated(tmp_path,
                 r'<circle cx="1419\.8" cy="663\.8" r="4\.5"',
                 '<circle cx="1429.8" cy="673.8" r="4.5"')
    assert 'G2' in _fails(p)


def test_mutation_zorder_swapped(tmp_path):
    """z序调换(走廊跑到圆上面) → G1必红。"""
    s = open(LINE2, encoding='utf-8').read()
    g1 = re.search(r'(<g id="走廊">.*?</g>)', s, re.S).group(1)
    g2 = re.search(r'(<g id="站圆">.*?</g>)', s, re.S).group(1)
    p = tmp_path / 'mut.svg'
    p.write_text(s.replace(g1, '§A§').replace(g2, g1).replace('§A§', g2), encoding='utf-8')
    assert 'G1' in _fails(str(p))


def test_mutation_badge_over_label(tmp_path):
    """终点徽标压到站名(铁律1) → G8必红。"""
    p = _mutated(tmp_path, r'translate\(1392\.8 1650\)', 'translate(1392.8 1618)')
    assert 'G8' in _fails(p)


def test_mutation_text_out_of_frame(tmp_path):
    """viewBox 左边距吃掉英文宽站名(2号线v3教训: 英文比中文宽) → G6必红。"""
    p = _mutated(tmp_path, r'viewBox="1221\.5 481\.0', 'viewBox="1270 481.0')
    assert 'G6' in _fails(p)
