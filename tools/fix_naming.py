# -*- coding: utf-8 -*-
"""多数派仲裁闭环: 跨线不一致站 -> 多数派坐标注入钉 -> 重建少数派线 -> 复验。
用法: python tools/fix_naming.py   (循环至全绿或无改进)
"""
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_naming as VN  # noqa: E402
import build_card as BC  # noqa: E402
from collections import defaultdict  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

NS = 'http://www.w3.org/2000/svg'


def majority_pos(nm, pos, disagree, l2truth):
    """站的多数派坐标: 排除少数派后的中位数(真值源加权)。"""
    outs = disagree.get(nm, set())
    xs, ys = [], []
    for zh, m in pos.items():
        if zh in outs or nm not in m:
            continue
        xs.append(m[nm][0]); ys.append(m[nm][1])
    if nm in l2truth:
        xs.append(l2truth[nm][0]); ys.append(l2truth[nm][1])
        xs.append(l2truth[nm][0]); ys.append(l2truth[nm][1])  # 真值双票
    if not xs:
        return None
    xs.sort(); ys.sort()
    return xs[len(xs)//2], ys[len(ys)//2]


def main():
    lines, S = BC.load_metro()
    src = BC.Source(BC.SVG)
    groups = src.corridor_groups()
    base_pins = BC.load_pins()
    l2truth = {k: tuple(v) for k, v in __import__('json').load(
        open(os.path.join(BC.ROOT, 'data/_l2circles24.json'), encoding='utf-8')).items()}

    for rnd in range(6):
        pos, reports, disagree = VN.analyze()
        bad = {zh: why for zh, why in reports.items() if why}
        print('第%d轮: %d 线未过' % (rnd + 1, len(bad)))
        if not bad:
            print('全部通过')
            return 0
        # 注入表: 线 -> 站 -> 多数派坐标
        inject = defaultdict(dict)
        for nm, outs in disagree.items():
            mp = majority_pos(nm, pos, disagree, l2truth)
            if mp is None:
                continue
            for zh in outs:
                inject[zh][nm] = mp
        # 真值钉偏移的站也注入真值
        for zh, why in bad.items():
            for w in why:
                if w.startswith('真值钉偏移:'):
                    nm = w.split(':')[1].split('(')[0].strip()
                    if nm in l2truth:
                        inject[zh][nm] = l2truth[nm]
        if not inject:
            print('无可注入仲裁(剩余为无多数派/结构问题):', {k: v[:2] for k, v in bad.items()})
            return 1
        rebuilt = 0
        for zh, extra in sorted(inject.items()):
            if zh not in lines:
                continue
            pins = dict(base_pins)
            pins.update(extra)
            try:
                out, msg = BC.build_line(zh, src, groups, lines, S, pins)
                ok = bool(out) and isinstance(msg, str) and msg.startswith('ALL PASS')
                rebuilt += 1
                print('  重建 %-6s %s 注入%d钉 %s' % (zh, '✓' if ok else '✗', len(extra),
                      '' if ok else str(msg)[:80]))
            except Exception as e:
                print('  重建 %-6s 异常 %r' % (zh, e))
        if not rebuilt:
            print('重建失败')
            return 1
    _, reports, _ = VN.analyze()
    bad = {zh: why for zh, why in reports.items() if why}
    print('6轮后仍未过:', list(bad))
    return 1


if __name__ == '__main__':
    sys.exit(main())
