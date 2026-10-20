# -*- coding: utf-8 -*-
"""12号线双段卡生成器(v3): 南段(基卡) + 北段(浔峰岗→广州体育馆 7站, Tim图实线)。
单独处理本线(用户指定): 不改 metro-data; 北段站序写入 data/line12-both.json 供 V1 使用。
根节点 data-multi="1" + data-chains 供 G3/G8/G10 多段语义。

终点布局规则(用户定稿):
  浔峰岗/广州体育馆/二沙岛 = 三点半一线: 圆→文字中心→数字块同在走廊延长线上,
    数字块与文字居中(同x), 间距统一3px; 浔峰岗/广州体育馆文字在圆下, 二沙岛在圆上。
  大学城南 = 圆正下方(走廊主向竖直), 英文拆两行后文字块与数字块联动下移。
  大学城北(中途站) = 原位英文拆两行。

基卡来源(2026-10-20 铁律): data/_card-bases/line-12号线.svg 备份, 幂等重生成。
**绝不用 git checkout 回退工作区卡** — HEAD 落后于工作区已修好的中间状态时会
把修好的问题改回去(已发生过)。
用法: python tools/line12-both.py
"""
import sys, io, re, os, math, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import build_card as B
from verify_card import text_half_width
import xml.etree.ElementTree as ET

NS = 'http://www.w3.org/2000/svg'
COLOR = '#33691E'
CARD = os.path.join(ROOT, 'assets/lines/line-12号线.svg')
OUT = os.path.join(ROOT, 'data/line12-both.json')
BASE = os.path.join(ROOT, 'data/_card-bases/line-12号线.svg')   # 未生成态基卡备份


def load_base():
    """基卡内容: 优先 _card-bases 备份; 备份缺失且当前卡未生成时现场建档。"""
    if os.path.exists(BASE):
        return open(BASE, encoding='utf-8').read()
    s = open(CARD, encoding='utf-8').read()
    assert 'data-multi' not in s, \
        '缺基卡备份 %s 且当前卡已是双段卡。禁止 git checkout 回退(会丢中间修复), 请先补基卡备份' % BASE
    os.makedirs(os.path.dirname(BASE), exist_ok=True)
    open(BASE, 'w', encoding='utf-8').write(s)
    print('基卡备份建立 → %s' % BASE)
    return s

NORTH = [
    ('浔峰岗',       (1066.5, 740.25),  'Xunfenggang',                       ['left', 'below', 'above']),
    ('浔峰岗北',     (1089.0, 708.75),  'Xunfenggang North',                 ['left', 'above', 'below']),
    ('聚龙',        (1174.5, 686.25),  'Julong',                            ['above', 'left', 'right']),
    ('广州白云站',    (1246.5, 686.25),  'Guangzhou Baiyun Railway Station',  ['above', 'left', 'right']),
    ('新市墟',       (1325.25, 686.25), 'Xinshixu',                          ['above', 'left', 'right']),
    ('白云文化广场',   (1390.5, 693.0),   'Baiyun Culture Square',             ['right', 'below', 'left']),
    ('广州体育馆',    (1437.75, 740.25), 'Guangzhou Gymnasium',               ['left', 'above', 'right']),
]
NORTH_SEGS = [
    (1066.5, 740.25, 1075.5, 722.25),
    (1075.5, 722.25, 1102.5, 695.25),
    (1102.5, 695.25, 1120.5, 686.25),
    (1120.5, 686.25, 1374.75, 686.25),
    (1374.75, 686.25, 1392.75, 695.25),
    (1392.75, 695.25, 1437.75, 740.25),
]
GAP, CLR_ZH, CLR_EN = 13.0, 8.5, 4.0
CHIP_HW, CHIP_HH, CHIP_GAP = 9.0, 6.75, 3.0   # 数字块半宽/半高(data-box 18x13.5)/文字块-数字块净距

# 终点: 站名 → (圆位, 延长线基准点(走廊邻端), 英文)
TERM = {
    '浔峰岗':     ((1066.5, 740.25),  (1075.5, 722.25),  'Xunfenggang'),
    '广州体育馆':  ((1437.75, 740.25), (1392.75, 695.25), 'Guangzhou Gymnasium'),
    '二沙岛':     ((1552.5, 1120.5),  (1568.2, 1136.2),  'Ersha Island'),
    '大学城南':    ((1984.5, 1401.8),  None,              'Higher Education Mega Center South'),
}


def seg_clearance(box, segs):
    x0, y0, x1, y1 = box
    best = 1e18
    for (ax, ay, bx, by) in segs:
        n = max(2, int(math.hypot(bx - ax, by - ay) / 8))
        for i in range(n + 1):
            px, py = ax + (bx - ax) * i / n, ay + (by - ay) * i / n
            dx = max(x0 - px, 0.0, px - x1)
            dy = max(y0 - py, 0.0, py - y1)
            best = min(best, math.hypot(dx, dy))
    return best


def term_layout(nm, cir, far, en):
    """三点半一线: 文字中心在延长线上, 数字块与文字同x、文字外侧3px。"""
    if far is None:                      # 大学城南: 走廊主向竖直, 圆正下方
        ddx, ddy = 0.0, 1.0
    else:
        ddx, ddy = cir[0] - far[0], cir[1] - far[1]
        L = math.hypot(ddx, ddy)
        ddx, ddy = ddx / L, ddy / L
    en_lines = [en]
    if nm == '大学城南':                  # 官方全称过长, 固定断行
        en_lines = ['Higher Education Mega Center', 'South']
    k = len(en_lines)
    zh_w = text_half_width(nm)
    en_w = max(text_half_width(t, zh=False) for t in en_lines)
    lab_w = 2.0 * max(zh_w, en_w)
    bh = 11.0 + 7.5 + 6.5 * (k - 1) + 2.5
    ext = (lab_w * abs(ddx) + bh * abs(ddy)) / 2.0   # 文字块半展延(沿方向)
    px = cir[0] + ddx * (10.0 + ext)
    py = cir[1] + ddy * (10.0 + ext)
    top = py - bh / 2.0
    rows = [(top + 11.0, nm), (top + 18.5, en_lines[0])] + \
           [(top + 25.0 + 6.5 * i, en_lines[1 + i]) for i in range(k - 2)]
    box = (px - lab_w / 2.0, top, px + lab_w / 2.0, top + bh)
    cc = (px, box[3] + CHIP_GAP + CHIP_HH) if ddy >= 0 else (px, box[1] - CHIP_GAP - CHIP_HH)
    return (px, rows, box), cc


def main():
    s = load_base()   # 幂等: 永远从基卡重生成, 不依赖工作区状态也不碰 git
    vbm = re.search(r'viewBox="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"', s)
    vx0, vy0, vw, vh = (float(v) for v in vbm.groups())
    vb = (vx0, vy0, vx0 + vw, vy0 + vh)

    south_boxes = []
    for m in re.finditer(r'<text x="([-\d.]+)" y="([-\d.]+)" text-anchor="middle" '
                         r'font-size="([\d.]+)"[^>]*>([^<]*)</text>', s):
        fs, x, y, t = float(m.group(3)), float(m.group(1)), float(m.group(2)), m.group(4)
        wm = text_half_width(t, zh=(fs == 10.5))
        top = y - (11.0 if fs == 10.5 else 5.5)
        south_boxes.append((x - wm, top, x + wm, y + 2.5))

    placed, layout = [], {}

    # ===== 终点(4): 三点半一线 =====
    term_lab, term_chip = {}, {}
    for nm, (cir, far, en) in TERM.items():
        (lx, rows, box), cc = term_layout(nm, cir, far, en)
        term_lab[nm] = (lx, rows, box)
        term_chip[nm] = cc
        placed.append((box, nm))
        placed.append(((cc[0] - CHIP_HW, cc[1] - CHIP_HH, cc[0] + CHIP_HW, cc[1] + CHIP_HH), nm + '#chip'))
        print('   [终点] %s 文字中心(%.2f,%.2f) 数字块(%.2f,%.2f)' % (nm, lx, (box[1] + box[3]) / 2, cc[0], cc[1]))

    # ===== 北段其余站: 程序化候选摆放(逐候选过走廊净距/标签互斥校验) =====
    for nm, est, en, prefer in NORTH:
        if nm in TERM:
            continue
        zh_w = text_half_width(nm)
        sp = B.split_en(en, nm)
        en_lines = sp if sp else [en]
        wm = max([zh_w] + [text_half_width(t, zh=False) for t in en_lines])
        k = len(en_lines)
        bh = 11.0 + 7.5 + 6.5 * (k - 1) + 2.5
        cx, cy = est

        cands = []
        for side in prefer:
            xoffs = (0.0, -12.0, 12.0) if side in ('above', 'below') else (0.0,)
            for extra in (0.0, 8.0, 16.0, 24.0):
                for xoff in xoffs:
                    if side == 'above':
                        bx0, bx1 = cx - wm + xoff, cx + wm + xoff
                        by1 = cy - 4.5 - 3.0 - extra
                        by0 = by1 - bh
                    elif side == 'below':
                        by0 = cy + 4.5 + 3.0 + extra
                        bx0, bx1, by1 = cx - wm + xoff, cx + wm + xoff, by0 + bh
                    else:
                        x_ = cx - GAP - 2 * wm - extra if side == 'left' else cx + GAP + extra
                        by0, by1 = cy - bh / 2, cy + bh / 2
                        bx0, bx1 = x_, x_ + 2 * wm
                    box = (bx0, by0, bx1, by1)
                    ry = [(by0 + 11.0, nm), (by0 + 18.5, en_lines[0])] + \
                         [(by0 + 25.0 + 6.5 * i, en_lines[1 + i]) for i in range(k - 2)]
                    cands.append((box, ry))

        box = None
        for bb, ry in cands:
            zh_b = (bb[0], ry[0][0] - 11.0, bb[2], ry[0][0] + 1.5)
            if seg_clearance(zh_b, NORTH_SEGS) < CLR_ZH:
                continue
            bad = False
            for i in range(1, k):
                eb = (bb[0], ry[i][0] - 5.5, bb[2], ry[i][0] + 1.5)
                if seg_clearance(eb, NORTH_SEGS) < CLR_EN:
                    bad = True
                    break
            if bad:
                continue
            for ob in [p[0] for p in placed] + south_boxes:
                if not (bb[2] + 1 < ob[0] or ob[2] + 1 < bb[0] or bb[3] + 1 < ob[1] or ob[3] + 1 < bb[1]):
                    bad = True
                    break
            if bad:
                print('   [拒] %s box=%s' % (nm, tuple(round(v, 1) for v in bb)))
                continue
            box = bb
            layout[nm] = ((bb[0] + bb[2]) / 2, ry)
            placed.append((bb, nm))
            break
        if box is None:
            print('!! %s 无合规位' % nm)
            return

    corr = ''.join('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" '
                   'style="fill:none;stroke:%s;stroke-width:7;stroke-linecap:round" />' % (*sg, COLOR)
                   for sg in NORTH_SEGS)
    s = re.sub(r'(<g id="走廊"[^>]*>)', r'\1' + corr, s, count=1)
    circ = ''.join('<circle cx="%.2f" cy="%.2f" r="4.5" data-nm="%s" '
                   'style="fill:#FFFFFF;stroke:%s;stroke-width:2" />' % (x, y, nm, COLOR)
                   for nm, (x, y), _, _ in NORTH)
    s = re.sub(r'(<g id="站圆"[^>]*>)', r'\1' + circ, s, count=1)
    lab = ''.join(label_xml(nm, layout[nm]) for nm, _, _, _ in NORTH if nm not in TERM)
    lab += ''.join(label_xml(nm, (v[0], v[1])) for nm, v in term_lab.items() if nm in dict((n, 1) for n, _, _, _ in NORTH))
    s = re.sub(r'(<g id="站名标注"[^>]*>)', r'\1' + lab, s, count=1)
    chips = ''.join(chip_xml(*term_chip[nm]) for nm in ('浔峰岗', '广州体育馆'))
    s = re.sub(r'(<g id="线路徽标"[^>]*>)', r'\1' + chips, s, count=1)

    # ===== 南段手术: 终点迁位/英文拆行/数字块联动 =====
    def move_text(content, x, y):
        nonlocal s
        pat = re.compile(r'(<text x=")([-\d.]+)" y="([-\d.]+)"([^>]*>%s</text>)' % re.escape(content))
        s2, n = pat.subn(lambda m: '%s%.2f" y="%.2f"%s' % (m.group(1), x, y, m.group(4)), s)
        assert n == 1, '迁位失败: %s (n=%d)' % (content, n)
        s = s2

    def split_en2(content):
        nonlocal s
        pat = re.compile(r'<text x="([-\d.]+)" y="([-\d.]+)" text-anchor="middle" '
                         r'font-size="5\.5" fill="#444444">%s</text>' % re.escape(content))
        m = pat.search(s)
        assert m, '拆行失败: %s' % content
        x, y = float(m.group(1)), float(m.group(2))
        w1, w2 = content.rsplit(' ', 1)
        two = ('<text x="%.2f" y="%.2f" text-anchor="middle" font-size="5.5" fill="#444444">%s</text>'
               '<text x="%.2f" y="%.2f" text-anchor="middle" font-size="5.5" fill="#444444">%s</text>'
               ) % (x, y, w1, x, y + 6.5, w2)
        s = s[:m.start()] + two + s[m.end():]

    def move_chip(old_tr, cc):
        nonlocal s
        pat = re.compile(r'translate\(%s\)" data-box="[^"]*"' % re.escape(old_tr))
        s2, n = pat.subn('translate(%.2f %.2f)" data-box="%.2f,%.2f,%.2f,%.2f"' % (
            cc[0] - CHIP_HW, cc[1] - CHIP_HH, cc[0] - CHIP_HW, cc[1] - CHIP_HH,
            cc[0] + CHIP_HW, cc[1] + CHIP_HH), s)
        assert n == 1, '数字块迁位失败: %s (n=%d)' % (old_tr, n)
        s = s2

    lx, rows, _ = term_lab['二沙岛']
    move_text('二沙岛', lx, rows[0][0])
    move_text('Ersha Island', lx, rows[1][0])
    move_chip('1543.51 1175.65', term_chip['二沙岛'])
    lx, rows, _ = term_lab['大学城南']
    move_text('大学城南', lx, rows[0][0])
    split_en2('Higher Education Mega Center South')
    move_chip('1975.51 1441.05', term_chip['大学城南'])
    split_en2('Higher Education Mega Center North')      # 大学城北(中途站)同规则拆行

    # 英文行统一 Arial(量宽与门禁一致)
    s = s.replace('font-size="5.5" fill="#444444"',
                  'font-size="5.5" font-family="Arial, sans-serif" fill="#444444"')

    chains = [','.join(n for n, _, _, _ in NORTH),
              '二沙岛,赤岗塔,赤岗,赤沙北,赤沙,北山,官洲,大学城北,大学城南']
    s = s.replace('<svg xmlns="http://www.w3.org/2000/svg"',
                  '<svg xmlns="http://www.w3.org/2000/svg" data-multi="1" data-chains="%s"' % '|'.join(chains), 1)

    m = re.search(r'viewBox="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"', s)
    x0, y0, w, h = (float(v) for v in m.groups())
    allx = [x0, x0 + w] + [b[0] for b, _ in placed] + [b[2] for b, _ in placed]
    ally = [y0, y0 + h] + [b[1] for b, _ in placed] + [b[3] for b, _ in placed]
    nx0, ny0 = min(allx) - 14, min(ally) - 14
    nx1, ny1 = max(allx) + 14, max(ally) + 14
    s = s.replace(m.group(0), 'viewBox="%.1f %.1f %.1f %.1f"' % (nx0, ny0, nx1 - nx0, ny1 - ny0), 1)
    mbg = re.search(r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([-\d.]+)" height="([-\d.]+)" fill="#ffffff"', s)
    if mbg:
        s = s.replace(mbg.group(0), '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#ffffff" />' % (
            nx0, ny0, nx1 - nx0, ny1 - ny0), 1)
    open(CARD, 'w', encoding='utf-8').write(s)
    json.dump({'north': [n for n, _, _, _ in NORTH],
               'south': ['二沙岛', '赤岗塔', '赤岗', '赤沙北', '赤沙', '北山', '官洲', '大学城北', '大学城南']},
              open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
    print('双段卡写入 + %s' % OUT)


def chip_xml(cx, cy):
    g = B.make_badge_official('12', COLOR, cx, cy, 1.0, 'chip')
    for e in g.iter():
        if isinstance(e.tag, str) and e.tag.startswith('{'):
            e.tag = e.tag.split('}', 1)[1]
    return ET.tostring(g, encoding='unicode')


def label_xml(nm, layout):
    x, rows = layout
    out = ['<text x="%.1f" y="%s" text-anchor="middle" font-size="10.5" '
           'font-weight="500" fill="#1a1a1a">%s</text>' % (x, rows[0][0], nm)]
    for y, line in rows[1:]:
        out.append('<text x="%.1f" y="%s" text-anchor="middle" font-size="5.5" '
                   'fill="#444444">%s</text>' % (x, y, line))
    return ''.join(out)


if __name__ == '__main__':
    main()
