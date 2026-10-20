# -*- coding: utf-8 -*-
"""门禁尾巴外科后修: 标签净距不足->沿法向推; 徽标压盖->挪最近空位。改后即过门禁。"""
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_card import load, run_gates, text_half_width  # noqa: E402

G = 10.0


def fix_label(card, nm):
    c = load(card)
    segs = c['segs']
    lb = next(l for l in c['labels'] if l['nm'] == nm)

    def clearance(bx0, by0, bx1, by1):
        best = 1e18
        for (x1, y1, x2, y2) in segs:
            for i in range(21):
                t = i / 20
                px, py = x1 + t * (x2 - x1), y1 + t * (y2 - y1)
                dx = max(bx0 - px, 0.0, px - bx1)
                dy = max(by0 - py, 0.0, py - by1)
                best = min(best, math.hypot(dx, dy))
        return best

    s = open(card, encoding='utf-8').read()
    # 找 zh/en text 元素并整体平移
    mzh = re.search(r'<text x="([\d.]+)" y="([\d.]+)"([^>]*>)(%s)</text>' % re.escape(nm), s)
    if not mzh:
        return False, '未找到 %s 的 text' % nm
    zx, zy = float(mzh.group(1)), float(mzh.group(2))
    men = re.search(r'(<text x=")([\d.]+)(" y=")([\d.]+)"([^>]*>[^<]*</text>)', s[mzh.end():mzh.end()+400])
    en_x = float(men.group(2)); en_y = float(men.group(4))
    # 最近走廊点
    best, bd = None, 1e18
    for (x1, y1, x2, y2) in segs:
        for i in range(41):
            t = i / 40
            px, py = x1 + t * (x2 - x1), y1 + t * (y2 - y1)
            d = math.hypot(px - (zx + en_x) / 2, py - (zy + en_y) / 2)
            if d < bd:
                best, bd = (px, py), d
    cx, cy = (zx + en_x) / 2, (zy + en_y) / 2
    dx, dy = cx - best[0], cy - best[1]
    L = math.hypot(dx, dy) or 1.0
    wm = max(text_half_width(nm), text_half_width(lb['en'], zh=False))
    box = (cx - wm, zy - 11, cx + wm, en_y + 1.5)
    need = G - 0.8 - clearance(*box)
    if need <= 0:
        return True, '本已达标'
    mv = need + 1
    nx, ny = cx + dx / L * mv, cy + dy / L * mv
    ddx, ddy = nx - cx, ny - cy
    s = s.replace(mzh.group(0), '<text x="%.1f" y="%.1f"%s%s</text>' % (zx + ddx, zy + ddy, mzh.group(3), nm))
    seg2 = men.group(0)
    seg2n = seg2.replace('x="%s"' % men.group(2), 'x="%.1f"' % (en_x + ddx)).replace('y="%s"' % men.group(4), 'y="%.1f"' % (en_y + ddy))
    s = s.replace(seg2, seg2n, 1)
    open(card, 'w', encoding='utf-8').write(s)
    return True, '位移(%.1f,%.1f)' % (ddx, ddy)


def fix_badge(card):
    c = load(card)
    vb = c['vb']
    x0, y0, x1, y1 = vb[0], vb[1], vb[0] + vb[2], vb[1] + vb[3]
    bad = next((b for b in c['badges']
                if any(not (b['box'][2] < l['box'][0] or l['box'][2] < b['box'][0]
                            or b['box'][3] < l['box'][1] or l['box'][3] < b['box'][1])
                       for l in c['labels'])
                or _corr(b['box'], c['segs']) < 1.0), None)
    if bad is None:
        return True, '无压盖'
    def free(bb):
        if bb[0] < x0 + 4 or bb[2] > x1 - 4 or bb[1] < y0 + 4 or bb[3] > y1 - 4:
            return False
        if any(not (bb[2] < l['box'][0] or l['box'][2] < bb[0] or bb[3] < l['box'][1] or l['box'][3] < bb[1])
               for l in c['labels']):
            return False
        return _corr(bb, c['segs']) > 3
    spot = None
    bw = bad['box'][2] - bad['box'][0]
    bh = bad['box'][3] - bad['box'][1]
    for fi in range(33):
        for fj in range(33):
            bx = x0 + (x1 - x0) * fi / 32
            by = y0 + (y1 - y0) * fj / 32
            bb = (bx - bw / 2, by - bh / 2, bx + bw / 2, by + bh / 2)
            if free(bb):
                spot = (bx, by)
                break
        if spot:
            break
    if not spot:
        return False, '无空位'
    s = open(card, encoding='utf-8').read()
    if bad.get('mode') == 'chip':
        # v7 官方徽标: 色块中心即 translate 锚点, 同步重写 data-box
        pat = re.compile(r'(<g[^>]*data-badge="chip"[^>]*transform="translate\()([-\d.]+)[ ,]+([-\d.]+)(\)[^>]*data-box=")[^"]*(")')
        m = pat.search(s)
        if not m:
            return False, '找不到 chip 徽标'
        nx, ny = spot
        s = pat.sub(lambda mm: '%s%.1f %.1f%s%.1f,%.1f,%.1f,%.1f%s' % (
            mm.group(1), nx, ny, mm.group(4),
            nx - bw / 2, ny - bh / 2, nx + bw / 2, ny + bh / 2, mm.group(5)), s, count=1)
    else:
        cx0 = (bad['box'][0] + bad['box'][2]) / 2
        cy0 = (bad['box'][1] + bad['box'][3]) / 2
        s = re.sub(r'translate\(%s %s\) scale\(0\.6\)' % (re.escape('%.2f' % cx0 if abs(cx0 - round(cx0)) > 0.01 else '%.1f' % cx0), re.escape('%.1f' % cy0)),
                   'translate(%.1f %.1f) scale(0.6)' % spot, s)
    open(card, 'w', encoding='utf-8').write(s)
    return True, '徽标挪至(%.0f,%.0f)' % spot


def _corr(bb, segs):
    best = 1e18
    for (x1, y1, x2, y2) in segs:
        for i in range(21):
            t = i / 20
            px, py = x1 + t * (x2 - x1), y1 + t * (y2 - y1)
            dx = max(bb[0] - px, 0.0, px - bb[2])
            dy = max(bb[1] - py, 0.0, py - bb[3])
            best = min(best, math.hypot(dx, dy))
    return best


if __name__ == '__main__':
    card, kind, nm = sys.argv[1], sys.argv[2], sys.argv[3]
    print(fix_label(card, nm) if kind == 'label' else fix_badge(card))
    R = run_gates(card)
    print('门禁: %d/%d' % (sum(ok for _, _, ok, _ in R), len(R)))
