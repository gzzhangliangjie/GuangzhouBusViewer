# -*- coding: utf-8 -*-
"""旧卡终点数字块就地迁移器: 非 CFG 管线卡的数字块迁到全线统一规则位
(与终点文字同x居中, 净距3px, 文字块背离圆点一侧), 不重建整卡。
门禁口径: 文字块=ZH基线-11 .. 末行EN基线+2.5; 迁移后跑 verify_card 验证。
用法: python tools/migrate-term-chips.py assets/lines/line-1号线.svg ...
"""
import sys, io, re, os, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from verify_card import text_half_width

CHIP_HH = 6.75
CHIP_HW = 6.75  # chip 13.49 方形; 横排时水平半宽(盒沿用±9.0与竖排一致)


def labels_of(s):
    raw = [{'x': float(m.group(1)), 'y': float(m.group(2)), 'fs': float(m.group(3)), 't': m.group(4)}
           for m in re.finditer(r'<text x="([-\d.]+)" y="([-\d.]+)" text-anchor="middle" '
                                r'font-size="([\d.]+)"[^>]*>([^<]*)</text>', s)]
    out = []
    for z in [r for r in raw if abs(r['fs'] - 10.5) < 0.01]:
        en = min((r for r in raw if abs(r['fs'] - 5.5) < 0.01
                  and abs(r['x'] - z['x']) < 0.3 and 0 < r['y'] - z['y'] < 12),
                 key=lambda r: r['y'] - z['y'], default=None)
        en2 = None
        if en:
            en2 = min((r for r in raw if abs(r['fs'] - 5.5) < 0.01
                       and abs(r['x'] - en['x']) < 0.3 and 3 < r['y'] - en['y'] < 10),
                      key=lambda r: r['y'] - en['y'], default=None)
        wm = max(text_half_width(z['t']), text_half_width(en['t'] if en else '', zh=False))
        out.append({'nm': z['t'], 'x': z['x'], 'zy': z['y'],
                    'box': (z['x'] - wm, z['y'] - 11.0, z['x'] + wm,
                            (en2 or en or z)['y'] + 2.5)})
    return out


def circles_of(s):
    return [(m.group(3), float(m.group(1)), float(m.group(2)))
            for m in re.finditer(r'<circle cx="([-\d.]+)" cy="([-\d.]+)" r="4\.5" data-nm="([^"]+)"', s)]


def terminals_of(s, circs, override=None):
    """终点站名->站圆坐标。默认=站圆文档序首末(构建管线按站序发射);
    支线卡(>2终点)用 --terms=名1,名2,名3 显式给。"""
    if override:
        pos = {nm: (x, y) for nm, x, y in circs}
        missing = [nm for nm in override if nm not in pos]
        assert not missing, 'terms 不在站圆表: %s' % missing
        return {nm: pos[nm] for nm in override}
    return {circs[0][0]: circs[0][1:], circs[-1][0]: circs[-1][1:]}


def main():
    argv = sys.argv[1:]
    override = None
    files = []
    for a in argv:
        if a.startswith('--terms='):
            override = [t for t in a.split('=', 1)[1].split(',') if t]
        else:
            files.append(a)
    for path in files:
        s = open(path, encoding='utf-8').read()
        labs, circs = labels_of(s), circles_of(s)
        terms = terminals_of(s, circs, override)
        chips = list(re.finditer(r'<g data-badge="chip" transform="translate\([-\d. ]+\)" data-box="[^"]*"', s))
        for m in chips:
            bx0, by0, bx1, by1 = [float(v) for v in
                                  re.search(r'data-box="([-\d.,]+)"', m.group(0)).group(1).split(',')]
            cc = ((bx0 + bx1) / 2, (by0 + by1) / 2)
            # 归属=按名单认亲(2026-10-21): chip 只配终点(走廊度1)标签, 圆点取同名站圆。
            # 邻接配对救不了归属错误——1号线广州东站chip曾被旧迁移贴到体育中心标签下。
            # 度1只在重锚后仍唯一, 站名即身份; 环线(无度1终点)整卡跳过
            if not terms:
                print('%s: 无度1终点(环线?), 跳过' % os.path.basename(path))
                break
            tcand = [(math.hypot(l['x'] - cc[0], (l['box'][1] + l['box'][3]) / 2 - cc[1]), l)
                     for l in labs if l['nm'] in terms]
            if not tcand:
                print('%s: chip@(%.0f,%.0f) 附近无终点标签, 跳过' % (os.path.basename(path), cc[0], cc[1]))
                continue
            _, lb = min(tcand)
            dot = terms[lb['nm']]
            lcy = (lb['box'][1] + lb['box'][3]) / 2
            if abs(lb['x'] - dot[0]) > abs(lcy - dot[1]):  # 横向连线: 徽标横排(同y居中)
                cx = lb['box'][2] + 3.0 + CHIP_HW if lb['x'] > dot[0] else lb['box'][0] - 3.0 - CHIP_HW
                cy = lcy
            else:  # 竖向连线: 与终点文字同x居中
                cx = lb['x']
                cy = lb['box'][3] + 3.0 + CHIP_HH if lcy > dot[1] else lb['box'][1] - 3.0 - CHIP_HH
            new = '<g data-badge="chip" transform="translate(%.2f %.2f)" data-box="%.2f,%.2f,%.2f,%.2f"' % (
                cx - CHIP_HW, cy - CHIP_HH, cx - CHIP_HW, cy - CHIP_HH, cx + CHIP_HW, cy + CHIP_HH)
            s = s.replace(m.group(0), new, 1)
            print('%s %s: (%.1f,%.1f) → (%.1f,%.1f)' % (os.path.basename(path), lb['nm'], cc[0], cc[1], cx, cy))
        open(path, 'w', encoding='utf-8').write(s)


if __name__ == '__main__':
    main()
