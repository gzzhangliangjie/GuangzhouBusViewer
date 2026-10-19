# -*- coding: utf-8 -*-
"""全部单线卡片 T0 结构门禁参数化: 19 线(1/2定稿 + 3-14/18/21/22/广佛/APM 生成)。
站数期望来自 metro-data(主线+支线), 卡片缺文件=FAIL 不是 SKIP。"""
import json
import os
import re
import pytest
from conftest import ROOT
from verify_card import run_gates


def _lines():
    s = open(os.path.join(ROOT, 'data/metro-data.js'), encoding='utf-8').read()
    d = json.loads(re.search(r'window\.METRO_DATA\s*=\s*(\{.*\})\s*;?\s*$', s, re.S).group(1))
    out = {}
    for L in d['lines']:
        n = len(L['stations']) + sum(len(b) - 1 for b in L.get('branches', []))
        out[L['zh']] = n
    return out


def _cards():
    base = os.path.join(ROOT, 'assets', 'lines')
    special = {}  # 1号线已走标准流程(line-1号线.svg); 旧-17卡仅存档
    for zh, n in _lines().items():
        if zh == '1号线':
            continue
        fn = special.get(zh, 'line-%s.svg' % zh)
        if zh == '1号线':
            fn = 'line-1号线.svg'
        yield pytest.param(os.path.join(base, fn), n, id=zh)


def _chains():
    s = open(os.path.join(ROOT, 'data/metro-data.js'), encoding='utf-8').read()
    d = json.loads(re.search(r'window\.METRO_DATA\s*=\s*(\{.*\})\s*;?\s*$', s, re.S).group(1))
    out = {}
    for L in d['lines']:
        out[L['zh']] = [list(L['stations'])] + [list(b) for b in L.get('branches', [])]
    return out


CH = _chains()


@pytest.mark.parametrize('card,n', list(_cards()))
def test_card_gates(card, n):
    if not os.path.exists(card):
        pytest.fail('卡片缺失: %s' % card)
    zh = re.search(r'line-(.+?)\.svg', os.path.basename(card)).group(1)
    R = run_gates(card, expect_n=n, chains=CH.get(zh))
    fails = ['%s %s: %s' % (no, name, detail) for no, name, ok, detail in R if not ok]
    assert not fails, '%s 门禁未过:\n%s' % (os.path.basename(card), '\n'.join(fails))
