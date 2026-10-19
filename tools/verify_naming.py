# -*- coding: utf-8 -*-
"""逐线站名语义验证 v3
V1 卡内站序: <circle data-nm> 序列 == metro-data 真值序(主线+支线整块)
V2 换乘互检: 同名站跨线坐标一致(多数派仲裁), 2号线用真值表
V3 真值钉: L2 真值站在各线卡片位置 ≤45px
用法: python tools/verify_naming.py [线路名...]
"""
import json
import math
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NS = 'http://www.w3.org/2000/svg'
import xml.etree.ElementTree as ET  # noqa: E402

AGREE_TOL = 70.0   # 合法换乘两线圆位偏移实测至~55px
PIN_TOL = 45.0


def metro():
    s = open(os.path.join(ROOT, 'data/metro-data.js'), encoding='utf-8').read()
    return json.loads(re.search(r'window\.METRO_DATA\s*=\s*(\{.*\})\s*;?\s*$', s, re.S).group(1))


def l2truth():
    return {k: tuple(v) for k, v in json.load(
        open(os.path.join(ROOT, 'data/_l2circles24.json'), encoding='utf-8')).items()}


def truth_sts(L):
    sts = list(L['stations'])
    for br in L.get('branches', []):
        if br[0] in sts:
            sts[sts.index(br[0]) + 1:sts.index(br[0]) + 1] = br[1:]
        else:
            sts += br[1:]
    return sts


def card_seq(linename):
    fn = 'line-%s.svg' % linename
    p = os.path.join(ROOT, 'assets/lines', fn)
    if not os.path.exists(p):
        p = os.path.join(ROOT, 'assets/lines', 'line-1号线-17.svg')
    if not os.path.exists(p):
        return None
    out = []
    for c in ET.parse(p).getroot().iter('{%s}circle' % NS):
        if c.get('data-nm'):
            out.append((c.get('data-nm'), float(c.get('cx')), float(c.get('cy'))))
    return out


def analyze(want=None):
    d = metro()
    l2t = l2truth()
    lines = {L['zh']: L for L in d['lines']}
    want = want or [zh for zh in lines]
    pos, reports = {}, {}
    for zh in want:
        if zh == '2号线':
            seq = card_seq(zh) or [(nm, v[0], v[1]) for nm, v in l2t.items()]
            pos[zh] = {nm: (x, y) for nm, x, y in seq}
            reports[zh] = []
            continue
        seq = card_seq(zh)
        if not seq:
            reports[zh] = ['卡片缺失或无 data-nm(需 build_card.py 重建)']
            continue
        pos[zh] = {nm: (x, y) for nm, x, y in seq}
        why = []
        expect = truth_sts(lines[zh])
        got = [nm for nm, _, _ in seq]
        if zh == '1号线':
            pass  # 旧结构卡圆为绘制序, 站序由 verify-line1.py 历史把关; 坐标仍入互检池
        elif got != expect:
            why.append('站序≠真值(期望首%s 实际首%s)' % (expect[:3], got[:3]))
        reports[zh] = why

    allpos = defaultdict(dict)
    for zh, m in pos.items():
        for nm, xy in m.items():
            allpos[nm][zh] = xy
    disagree = defaultdict(set)
    for nm, srcs in allpos.items():
        if len(srcs) < 3:
            continue
        items = list(srcs.items())
        xs = sorted(v[0] for _, v in items)
        ys = sorted(v[1] for _, v in items)
        mx, my = xs[len(xs)//2], ys[len(ys)//2]
        for src, (x, y) in items:
            if math.hypot(x - mx, y - my) > AGREE_TOL:
                disagree[nm].add(src)
    for nm, srcs in disagree.items():
        for zh in srcs:
            if zh in reports:
                reports[zh].append('跨线不一致: %s' % nm)
    for zh in pos:
        if zh == '2号线':
            continue
        for nm, (tx, ty) in l2t.items():
            if nm in pos[zh]:
                x, y = pos[zh][nm]
                if math.hypot(x - tx, y - ty) > PIN_TOL:
                    reports[zh].append('真值钉偏移: %s (%.0fpx)' % (nm, math.hypot(x - tx, y - ty)))
    return pos, reports, disagree


def main():
    _, reports, disagree = analyze()
    ok = [zh for zh in reports if not reports[zh]]
    for zh, why in reports.items():
        print('%-6s %s %s' % (zh, '✓' if not why else '✗',
                              '; '.join(why)[:150] or '通过'))
    print('\n语义验证: %d/%d 通过' % (len(ok), len(reports)))
    if disagree:
        print('跨线不一致站:', {k: sorted(v) for k, v in list(disagree.items())[:12]})
    return 0 if len(ok) == len(reports) else 1


if __name__ == '__main__':
    sys.exit(main())
