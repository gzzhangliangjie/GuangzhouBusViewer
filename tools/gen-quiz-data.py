# -*- coding: utf-8 -*-
"""地铁拼图数据生成器: 官网图产品 -> data/quiz-network-data.js (官方线网图棋盘用)。

只读产品文件, 不改任何 SVG。全部解析走 gen-codes-cards 共享接口(§1.7), 校验不过即退出:
- V1 站名双射: 基础图 318 个中文站名文字 <-> 站圆302+换乘胶囊16 (data-nm), 无重名;
- V2 线色双射: 19 条线徽标内色 <-> 走廊组 19 个颜色集合全等, 每线徽标同色;
- V3 编号牌配对: codes 图 400 枚牌按"最近钉位全局唯一指派"配到 (站,线),
  与 CSV 官方编号一一对应; 多牌站的牌必须全部落在该站圈环(data-ring)内;
- V4 站覆盖: 每站至少 1 条线(有牌), 每线牌数 == 该线卡片钉位数(CSV 有码);
用法: python tools/gen-quiz-data.py
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
_spec = importlib.util.spec_from_file_location('gen', os.path.join(HERE, 'gen-codes-cards.py'))
gcc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gcc)

NET = os.path.join(ROOT, 'assets', 'lines', 'network-全网.svg')
NETC = os.path.join(ROOT, 'assets', 'lines', 'network-全网.codes.svg')
OUT = os.path.join(ROOT, 'data', 'quiz-network-data.js')
PAIR_RADIUS = 26.0   # 牌中心到所属钉位最大距离(圈环品字最远档, 超出=配对失败)

fail = []


def check(cond, msg):
    print(('  ok  ' if cond else '  FAIL ') + msg)
    if not cond:
        fail.append(msg)


def line_disp(ln):
    if ln == '广佛线':
        return 'GF'
    if ln == 'APM线':
        return 'APM'
    return ln[:-2]


def dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def main():
    tb = open(NET, encoding='utf-8').read()
    tc = open(NETC, encoding='utf-8').read()
    codes = gcc.load_codes()

    # ---------- V1 站名 <-> 站圆/胶囊 ----------
    texts = [t for t in gcc.text_elements(tb) if not t['en']]
    mk = gcc.marker_elements(tb)
    anchors = {}
    for (cx, cy, r, nm) in mk['circles']:
        anchors.setdefault(nm, (cx, cy))
    for (pts, nm) in mk['capsules']:
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        anchors.setdefault(nm, (cx, cy))
    tnames = [t['nm'] for t in texts]
    check(len(tnames) == 318 and len(set(tnames)) == 318, 'V1 中文站名 318 无重名 (实得 %d/%d)' % (len(tnames), len(set(tnames))))
    check(set(tnames) == set(anchors), 'V1 站名<->站圆/胶囊 双射 (差集 %s)' % (set(tnames) ^ set(anchors)))

    # ---------- V2 线色 ----------
    badges = gcc.badge_elements(tc)
    line_color = {}
    for b in badges:
        fm = None
        for tok in b['inner'].split('fill='):
            if tok.startswith('"#') or tok.startswith("'#"):
                fm = tok[1:8]
                break
        if fm:
            prev = line_color.setdefault(b['key'], fm.upper())
            if prev != fm.upper():
                fail.append('V2 %s 徽标异色 %s/%s' % (b['key'], prev, fm))
    cols = gcc.corridor_colors(tb)
    check(len(line_color) == 19, 'V2 徽标 19 线色 (实得 %d)' % len(line_color))
    check(set(cols) == set(line_color.values()),
          'V2 走廊色集==徽标色集 (走廊 %s)' % (set(cols) ^ set(line_color.values())))

    # ---------- V3 编号牌配对 ----------
    chips, _rings, _span = gcc.chip_elements(tc)
    rings = gcc.ring_elements(tc)
    ring_of = {nm: (x, y, w, h) for nm, x, y, w, h in rings}
    pins = {}          # (nm, ln) -> (cx, cy)
    pin_count = {}
    for ln in gcc.ORDER:
        card = gcc.parse_card(ln)
        pin_count[ln] = len(card['pins'])
        for (nm, cx, cy) in card['pins']:
            if (nm, ln) in codes:
                pins[(nm, ln)] = (cx, cy)
    cand = []
    for ci, (x, y, w, h) in enumerate(chips):
        c = (x + w / 2, y + h / 2)
        for (nm, ln), (px, py) in pins.items():
            d = dist(c, (px, py))
            if d <= PAIR_RADIUS:
                cand.append((d, ci, nm, ln))
    cand.sort()
    chip_key = [None] * len(chips)      # idx -> (nm, ln)
    used_key = set()
    for (d, ci, nm, ln) in cand:
        if chip_key[ci] is None and (nm, ln) not in used_key:
            chip_key[ci] = (nm, ln)
            used_key.add((nm, ln))
    check(len(chip_key) == 400 and all(chip_key), 'V3 牌 400 全配对 (实得 %d)' % sum(1 for k in chip_key if k))
    check(used_key == set(pins), 'V3 (站,线)全覆盖 (差集 %s)' % (used_key ^ set(pins)))
    # 圈环校验: 圈环与牌同位同尺寸(每枚牌一圈), 逐枚对上; 无圈环站配出多牌=结构异常
    by_nm = {}
    for ci, key in enumerate(chip_key):
        if key:
            by_nm.setdefault(key[0], []).append((ci, chips[ci]))
    ring_ok = True
    ring_by_nm = {}
    for nm, rx, ry, rw, rh in rings:
        ring_by_nm.setdefault(nm, []).append((rx, ry, rw, rh))

    def rect_eq(r, c):
        return len(r) == len(c) and all(abs(a - b) < 0.05 for a, b in zip(r, c))

    for nm, rs in ring_by_nm.items():
        cs = [rect for _ci, rect in by_nm.get(nm, [])]
        if len(rs) != len(cs) or not all(any(rect_eq(r, c) for c in cs) for r in rs):
            ring_ok = False
            fail.append('V3 %s 圈环%d 枚与牌%d 枚未逐枚对齐' % (nm, len(rs), len(cs)))
    for nm in by_nm:
        if nm not in ring_by_nm and len(by_nm[nm]) > 1:
            ring_ok = False
            fail.append('V3 %s %d枚牌无圈环' % (nm, len(by_nm[nm])))
    check(ring_ok, 'V3 圈环与牌逐枚对齐 (%d 圈环)' % len(rings))

    # ---------- 组装 ----------
    stations = {}
    for nm, (x, y) in anchors.items():
        stations[nm] = {'x': round(x, 2), 'y': round(y, 2), 'lines': []}
    chips_out = []
    per_line = {}
    for (x, y, w, h), key in zip(chips, chip_key):
        nm, ln = key
        disp, serial = codes[key]
        chips_out.append({'nm': nm, 'line': ln, 'serial': serial,
                          'x': round(x, 2), 'y': round(y, 2), 'w': round(w, 2), 'h': round(h, 2)})
        stations[nm]['lines'].append(ln)
        per_line[ln] = per_line.get(ln, 0) + 1
    for st in stations.values():
        st['lines'].sort(key=lambda l: gcc.ORDER.index(l))
    lines_out = [{'name': ln, 'disp': line_disp(ln), 'color': line_color[ln]}
                 for ln in gcc.ORDER]
    check(all(st['lines'] for st in stations.values()), 'V4 每站至少一线')
    check(all(per_line.get(ln) == pin_count[ln] for ln in gcc.ORDER),
          'V4 每线牌数==钉位数 (%s)' % {ln: (per_line.get(ln), pin_count[ln])
                                       for ln in gcc.ORDER if per_line.get(ln) != pin_count[ln]})

    data = {
        'viewBox': [668, 29.7, 2138, 1937.25],
        'lines': lines_out,
        'stations': stations,
        'chips': chips_out
    }
    body = json.dumps(data, ensure_ascii=False, separators=(', ', ': '))
    js = ('// 由 tools/gen-quiz-data.py 生成（真源: assets/lines/network-全网*.svg + '
          'data/station-codes-official.csv），勿手改。\n'
          '// 校验: 318站名双射 / 19线色全等 / 400编号牌全局唯一配对+圈环包含 / 每线牌数=钉位数。\n'
          'window.QUIZ_NETWORK_DATA = ' + body + ';\n')
    with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write(js)
    print('写出 %s (%d KB): %d线 %d站 %d牌' % (os.path.relpath(OUT, ROOT),
          len(js) // 1024, len(lines_out), len(stations), len(chips_out)))
    if fail:
        print('!! 校验失败 %d 项:' % len(fail))
        for m in fail:
            print('  -', m)
        sys.exit(1)


if __name__ == '__main__':
    main()
