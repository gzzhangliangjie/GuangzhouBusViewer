# -*- coding: utf-8 -*-
"""英文站名拆行(存量卡): en宽>中文1.5倍且多单词 → 按词拆两行(两行宽差最小), 行距6.5。
标签在走廊上方时整组上移6.5(第二行落回原 en 底位); 逐标签校验:
出框/中文净距≥8.5/英文行净距≥4/不压其他标签/不罩他站圆 —— 任一不过则该标签跳过不拆。
用法: python tools/split-en-labels.py [线名...] 无参=全部19线
"""
import sys, io, re, os, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from verify_card import text_half_width

LINES = ['1号线', '2号线', '3号线', '4号线', '5号线', '6号线', '7号线', '8号线', '9号线',
         '10号线', '11号线', '12号线', '13号线', '14号线', '18号线', '21号线', '22号线',
         '广佛线', 'APM线']
CLR_ZH, CLR_EN, ROW = 8.5, 4.0, 6.5


def seg_clearance(box, segs):
    """box 到走廊采样点最小距离"""
    x0, y0, x1, y1 = box
    best = 1e18
    for (ax, ay, bx, by) in segs:
        n = max(2, int(math.hypot(bx-ax, by-ay) / 8))
        for i in range(n + 1):
            px, py = ax + (bx-ax)*i/n, ay + (by-ay)*i/n
            dx = max(x0-px, 0.0, px-x1)
            dy = max(y0-py, 0.0, py-y1)
            best = min(best, math.hypot(dx, dy))
    return best


def split_lines(en, nm):
    if not en or ' ' not in en:
        return None
    if text_half_width(en, zh=False) <= 1.5 * text_half_width(nm):
        return None
    words = en.split(' ')
    best = None
    for i in range(1, len(words)):
        a, b = ' '.join(words[:i]), ' '.join(words[i:])
        d = abs(text_half_width(a, zh=False) - text_half_width(b, zh=False))
        if best is None or d < best[0]:
            best = (d, a, b)
    return best[1], best[2]


def process(zh):
    path = os.path.join(ROOT, 'assets/lines/line-%s.svg' % zh)
    s = open(path, encoding='utf-8').read()
    vb = [float(v) for v in re.search(r'viewBox="([^"]*)"', s).group(1).split()]

    circles = {}
    for m in re.finditer(r'<circle([^>]*?)/>', s):
        at = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        if 'data-nm' in at:
            circles[at['data-nm']] = (float(at['cx']), float(at['cy']))
    segs = [(float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)))
            for m in re.finditer(r'<line x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)"', s)]

    en_nodes = list(re.finditer(
        r'<text x="([-\d.]+)" y="([-\d.]+)" text-anchor="middle" font-size="5\.5" fill="#444444">([^<]*)</text>', s))
    zh_nodes = list(re.finditer(
        r'<text x="([-\d.]+)" y="([-\d.]+)" text-anchor="middle" font-size="10\.5" font-weight="500" fill="#1a1a1a">([^<]*)</text>', s))

    # 配对(与 verify_card 同规则) + 现有全部标签盒
    labels = []
    for z in zh_nodes:
        zx, zy, nm = float(z.group(1)), float(z.group(2)), z.group(3)
        en = min((e for e in en_nodes
                  if abs(float(e.group(1)) - zx) < 0.3 and 0 < float(e.group(2)) - zy < 12),
                 key=lambda e: float(e.group(2)) - zy, default=None)
        labels.append({'nm': nm, 'x': zx, 'zy': zy, 'znode': z,
                       'enode': en, 'en': en.group(3) if en else '',
                       'ey': float(en.group(2)) if en else None})
    for lb in labels:
        wm = max(text_half_width(lb['nm']), text_half_width(lb['en'], zh=False))
        lb['box'] = (lb['x'] - wm, lb['zy'] - 11.0, lb['x'] + wm,
                     (lb['ey'] or lb['zy']) + 2.5)

    done = skip = 0
    plan = []
    for lb in labels:
        lines = split_lines(lb['en'], lb['nm'])
        if not lines or lb['enode'] is None:
            continue
        cir = circles.get(lb['nm'])
        side_up = cir is not None and (lb['zy'] + (lb['ey'] or lb['zy'])) / 2 < cir[1]
        shift = -ROW if side_up else 0.0
        zy2, ey2 = lb['zy'] + shift, lb['ey'] + shift
        e2y = ey2 + ROW
        wzh = text_half_width(lb['nm'])
        w1 = text_half_width(lines[0], zh=False)
        w2 = text_half_width(lines[1], zh=False)
        wm = max(wzh, w1, w2)
        zh_b = (lb['x']-wzh, zy2-11.0, lb['x']+wzh, zy2+1.5)
        e1_b = (lb['x']-w1, ey2-5.5, lb['x']+w1, ey2+1.5)
        e2_b = (lb['x']-w2, e2y-5.5, lb['x']+w2, e2y+1.5)
        new_box = (lb['x']-wm, zy2-11.0, lb['x']+wm, e2y+1.5)
        why = None
        if new_box[0] < vb[0]+3 or new_box[2] > vb[0]+vb[2]-3 or new_box[1] < vb[1]+3 or new_box[3] > vb[1]+vb[3]-3:
            why = '出框'
        if not why and seg_clearance(zh_b, segs) < CLR_ZH:
            why = '中文净距%.1f' % seg_clearance(zh_b, segs)
        if not why and seg_clearance(e1_b, segs) < CLR_EN:
            why = '英文行1净距%.1f' % seg_clearance(e1_b, segs)
        if not why and seg_clearance(e2_b, segs) < CLR_EN:
            why = '英文行2净距%.1f' % seg_clearance(e2_b, segs)
        if not why:
            for o in labels:
                if o is lb:
                    continue
                ob = o['box']
                if not (new_box[2] + 1 < ob[0] or ob[2] + 1 < new_box[0]
                        or new_box[3] + 1 < ob[1] or ob[3] + 1 < new_box[1]):
                    why = '压标签 %s' % o['nm']
                    break
        if not why:
            for nm2, (cx2, cy2) in circles.items():
                if nm2 == lb['nm']:
                    continue
                if new_box[0]-2 < cx2 < new_box[2]+2 and new_box[1]-2 < cy2 < new_box[3]+2:
                    why = '罩他站圆 %s' % nm2
                    break
        if why:
            skip += 1
            print('   %-6s 跳过: %s' % (lb['nm'], why))
            continue
        plan.append((lb['znode'].start(), lb, zy2, ey2, e2y, lines))
    # 按文档位置倒序应用(前面的编辑不会使后面较小偏移的编辑失效)
    for _, lb, zy2, ey2, e2y, lines in sorted(plan, key=lambda t: -t[0]):
        zn = lb['znode']
        zn_seg = zn.group(0)
        s = s[:zn.start()] + zn_seg.replace('y="%s"' % zn.group(2), 'y="%.1f"' % zy2) + s[zn.start() + len(zn_seg):]
        en_ = re.search(r'<text x="([-\d.]+)" y="([-\d.]+)" text-anchor="middle" font-size="5\.5" fill="#444444">([^<]*)</text>',
                        s[zn.start():])
        en_abs_start = zn.start() + en_.start()
        en_seg = en_.group(0)
        en_seg_new = en_seg.replace('y="%s"' % en_.group(2), 'y="%.1f"' % ey2).replace(
            '>%s<' % en_.group(3), '>%s<' % lines[0])
        s = s[:en_abs_start] + en_seg_new + \
            '<text x="%s" y="%.1f" text-anchor="middle" font-size="5.5" fill="#444444">%s</text>' % (
                en_.group(1), e2y, lines[1]) + s[en_abs_start + len(en_seg):]
        done += 1
    open(path, 'w', encoding='utf-8').write(s)
    return done, skip


if __name__ == '__main__':
    names = sys.argv[1:] or LINES
    for zh in names:
        d, sk = process(zh)
        print('%-6s 拆%d 跳%d' % (zh, d, sk))
