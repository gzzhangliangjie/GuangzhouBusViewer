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
    return [(float(m.group(1)), float(m.group(2)))
            for m in re.finditer(r'<circle cx="([-\d.]+)" cy="([-\d.]+)" r="4\.5"', s)]


def main():
    for path in sys.argv[1:]:
        s = open(path, encoding='utf-8').read()
        labs, circs = labels_of(s), circles_of(s)
        chips = list(re.finditer(r'<g data-badge="chip" transform="translate\([-\d. ]+\)" data-box="[^"]*"', s))
        for m in chips:
            bx0, by0, bx1, by1 = [float(v) for v in
                                  re.search(r'data-box="([-\d.,]+)"', m.group(0)).group(1).split(',')]
            cc = ((bx0 + bx1) / 2, (by0 + by1) / 2)
            # 配对=门禁同款竖向邻接优先(0<gap<15 且 x距≤60 — 无x窗会同排标签全部并列,
            # 按文档序误配, 6号线chip被搬到1089px外的萝岗), |gap-3|为主 x距为次; 回退中心距≤80
            adj = []
            for l in labs:
                if abs(l['x'] - cc[0]) > 60:
                    continue
                gb = by0 - l['box'][3]
                ga = l['box'][1] - by1
                if 0 < gb < 15:
                    adj.append((abs(gb - 3.0), abs(l['x'] - cc[0]), l))
                if 0 < ga < 15:
                    adj.append((abs(ga - 3.0), abs(l['x'] - cc[0]), l))
            lb = min(adj, key=lambda t: (t[0], t[1]))[2] if adj else None
            if lb is None:
                lb = min(labs, key=lambda l: (l['x'] - cc[0]) ** 2 + ((l['box'][1] + l['box'][3]) / 2 - cc[1]) ** 2)
                d = math.hypot(lb['x'] - cc[0], (lb['box'][1] + lb['box'][3]) / 2 - cc[1])
                if d > 80:
                    print('%s: chip@(%.0f,%.0f) 最近文字 %s 距离%.0fpx>80, 跳过' % (
                        os.path.basename(path), cc[0], cc[1], lb['nm'], d))
                    continue
            dot = min(circs, key=lambda c: (c[0] - lb['x']) ** 2 + (c[1] - (lb['box'][1] + lb['box'][3]) / 2) ** 2)
            if math.hypot(dot[0] - lb['x'], dot[1] - (lb['box'][1] + lb['box'][3]) / 2) > 40:
                print('%s: 配对标签 %s 离任意圆>40px, 跳过(请人工核)' % (os.path.basename(path), lb['nm']))
                continue
            lcy = (lb['box'][1] + lb['box'][3]) / 2
            cx = lb['x']
            cy = lb['box'][3] + 3.0 + CHIP_HH if lcy > dot[1] else lb['box'][1] - 3.0 - CHIP_HH
            new = '<g data-badge="chip" transform="translate(%.2f %.2f)" data-box="%.2f,%.2f,%.2f,%.2f"' % (
                cx - 9.0, cy - CHIP_HH, cx - 9.0, cy - CHIP_HH, cx + 9.0, cy + CHIP_HH)
            s = s.replace(m.group(0), new, 1)
            print('%s %s: (%.1f,%.1f) → (%.1f,%.1f)' % (os.path.basename(path), lb['nm'], cc[0], cc[1], cx, cy))
        open(path, 'w', encoding='utf-8').write(s)


if __name__ == '__main__':
    main()
