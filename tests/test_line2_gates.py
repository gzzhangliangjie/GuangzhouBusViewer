# -*- coding: utf-8 -*-
"""T0 结构门禁：2号线定稿卡片 9 项全过(逐项断言, 失败时门禁名直读)"""
from conftest import LINE2
from verify_card import run_gates

EXPECT_N = 24


def test_line2_all_gates():
    R = run_gates(LINE2, expect_n=EXPECT_N)
    assert len(R) == 11
    fails = ['%s %s: %s' % (no, name, detail) for no, name, ok, detail in R if not ok]
    assert not fails, '门禁未过:\n' + '\n'.join(fails)


def test_line2_gate_ids_stable():
    R = run_gates(LINE2, expect_n=EXPECT_N)
    assert [no for no, *_ in R] == ['G%d' % i for i in range(1, 9)] + ['G8b', 'G9', 'G10'], \
        '门禁编号/顺序变化需同步 docs/card-acceptance.md'
