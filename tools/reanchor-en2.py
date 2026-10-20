# -*- coding: utf-8 -*-
"""拆行英文标签重锚(v9.1): 拆行使标签变窄后, 侧放标签按 圆心±(10+半宽) 重新贴回圆点。
上下放标签(x 居中于圆)不动。逐标签校验: 走廊净距(zh≥8.5/en≥4)/不压其他标签/出框 —— 不过则跳过。
用法: python tools/reanchor-en2.py [线名...] 无参=全部19线
"""
import sys, io, re, os, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from verify_card import text_half_width

LINES = ['1号线', '2号线', '3号线', '4号线', '5号线', '6号线', '7号线', '8号线', '9号线',
         '10号线', '11号线', '12号线', '13号线', '14号线', '18号线', '21号线', '22号线',
         '广佛线', 'APM线']
CLR_ZH, CLR_EN, GAP = 8.5, 4.0, 10.0


def seg_clearance(box, segs):
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

    labels = []
    for z in zh_nodes:
        zx, zy, nm = float(z.group(1)), float(z.group(2)), z.group(3)
        ens = [e for e in en_nodes if abs(float(e.group(1)) - zx) < 0.3 and 0 < float(e.group(2)) - zy]
        ens.sort(key=lambda e: float(e.group(2)) - zy)
        en1 = ens[0] if (ens and float(ens[0].group(2)) - zy < 12) else None
        en2 = ens[1] if (en1 and len(ens) > 1 and 3 < float(ens[1].group(2)) - float(en1.group(2)) < 10) else None
        wm = max(text_half_width(nm),
                 text_half_width(en1.group(3) if en1 else '', zh=False) if en1 else 0,
                 text_half_width(en2.group(3) if en2 else '', zh=False) if en2 else 0)
        bottom = (float(en2.group(2)) if en2 else (float(en1.group(2)) if en1 else zy)) + 2.5
        labels.append({'nm': nm, 'x': zx, 'zy': zy, 'wm': wm,
                       'box': (zx - wm, zy - 11.0, zx + wm, bottom),
                       'en1': en1, 'en2': en2, 'cir': circles.get(nm)})
    done = skip = 0
    for lb in labels:
        if not lb['en2'] or not lb['cir']:
            continue  # 只处理拆过行的侧放标签
        cx, cy = lb['cir']
        lcx = (lb['box'][0] + lb['box'][2]) / 2
        lcy = (lb['box'][1] + lb['box'][3]) / 2
        if abs(lcy - cy) > 8:
            continue  # 上下放: x 本就居中于圆
        if abs(lcx - cx) <= GAP + lb['wm'] + 0.5:
            continue  # 已贴边
        side_left = lcx < cx
        new_x = (cx - GAP - lb['wm']) if side_left else (cx + GAP + lb['wm'])
        new_box = (new_x - lb['wm'], lb['box'][1], new_x + lb['wm'], lb['box'][3])
        zh_b = (new_x - text_half_width(lb['nm']), lb['zy'] - 11.0,
                new_x + text_half_width(lb['nm']), lb['zy'] + 1.5)
        e1y = float(lb['en1'].group(2))
        e1_b = (new_x - text_half_width(lb['en1'].group(3), zh=False), e1y - 5.5,
                new_x + text_half_width(lb['en1'].group(3), zh=False), e1y + 1.5)
        e2_b = (new_x - text_half_width(lb['en2'].group(3), zh=False), lb['box'][3] - 4.0,
                new_x + text_half_width(lb['en2'].group(3), zh=False), lb['box'][3])
        why = None
        if new_box[0] < vb[0] + 3 or new_box[2] > vb[0] + vb[2] - 3:
            why = '出框'
        if not why and seg_clearance(zh_b, segs) < CLR_ZH:
            why = '中文净距%.1f' % seg_clearance(zh_b, segs)
        if not why and seg_clearance(e1_b, segs) < CLR_EN:
            why = '行1净距%.1f' % seg_clearance(e1_b, segs)
        if not why and seg_clearance(e2_b, segs) < CLR_EN:
            why = '行2净距%.1f' % seg_clearance(e2_b, segs)
        if not why:
            for o in labels:
                if o is lb:
                    continue
                ob = o['box']
                if not (new_box[2] + 1 < ob[0] or ob[2] + 1 < new_box[0]
                        or new_box[3] + 1 < ob[1] or ob[3] + 1 < new_box[1]):
                    why = '压标签 %s' % o['nm']
                    break
        if why:
            # 全贴边不行 → 渐进: 从现位向圆点走 75%/50%/25%, 取能过校验的最贴近档
            for t in (0.75, 0.5, 0.25):
                px_ = lcx + (new_x - lcx) * t
                pb = (px_ - lb['wm'], lb['box'][1], px_ + lb['wm'], lb['box'][3])
                pzh = (px_ - text_half_width(lb['nm']), lb['zy'] - 11.0,
                       px_ + text_half_width(lb['nm']), lb['zy'] + 1.5)
                pe1 = (px_ - text_half_width(lb['en1'].group(3), zh=False), e1y - 5.5,
                       px_ + text_half_width(lb['en1'].group(3), zh=False), e1y + 1.5)
                pe2 = (px_ - text_half_width(lb['en2'].group(3), zh=False), lb['box'][3] - 4.0,
                       px_ + text_half_width(lb['en2'].group(3), zh=False), lb['box'][3])
                ok = (vb[0] + 3 <= pb[0] and pb[2] <= vb[0] + vb[2] - 3
                      and seg_clearance(pzh, segs) >= CLR_ZH and seg_clearance(pe1, segs) >= CLR_EN
                      and seg_clearance(pe2, segs) >= CLR_EN)
                if ok:
                    for o in labels:
                        if o is lb:
                            continue
                        ob = o['box']
                        if not (pb[2] + 1 < ob[0] or ob[2] + 1 < pb[0]
                                or pb[3] + 1 < ob[1] or ob[3] + 1 < pb[1]):
                            ok = False
                            break
                if ok:
                    new_x, new_box, why = px_, pb, None
                    break
        if why:
            skip += 1
            print('   %-6s 跳过: %s' % (lb['nm'], why))
            continue
        dx = new_x - lb['x']
        for m in [lb['en1'], lb['en2']]:
            pass
        # 平移该标签全部行(zh/en1/en2)的 x
        for nd in ([z for z in zh_nodes if z.group(3) == lb['nm'] and abs(float(z.group(1)) - lb['x']) < 0.3][0],
                   lb['en1'], lb['en2']):
            old_x = nd.group(1)
            seg = nd.group(0)
            s = s.replace(seg, seg.replace('x="%s"' % old_x, 'x="%.1f"' % (float(old_x) + dx)), 1)
        lb['x'] = new_x
        lb['box'] = new_box
        done += 1
    open(path, 'w', encoding='utf-8').write(s)
    return done, skip


if __name__ == '__main__':
    names = sys.argv[1:] or LINES
    for zh in names:
        d, sk = process(zh)
        print('%-6s 重锚%d 跳%d' % (zh, d, sk))
