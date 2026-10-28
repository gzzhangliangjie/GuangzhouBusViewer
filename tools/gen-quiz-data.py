# -*- coding: utf-8 -*-
"""地铁拼图数据生成器: 官网图产品 -> data/quiz-network-data.js (官方线网图棋盘用)。

只读产品文件, 不改任何 SVG。全部解析走 gen-codes-cards 共享接口(§1.7), 校验不过即退出:
- V1 站名双射: 基础图 318 个中文站名文字 <-> 站圆302+换乘胶囊16 (data-nm), 无重名;
- V2 线色双射: 19 条线徽标内色 <-> 走廊组 19 个颜色集合全等, 每线徽标同色;
- V3 编号牌配对: codes 图 400 枚牌按"牌面解码"配到 (站,线)——隔线色+线号字+序号字
  是绘制端按 (站,线) 画入的权威身份, 解码后经 CSV 唯一反查; 钉位仅用于别名消歧与
  漂移报告(就近指派在多牌站钉位/落位错位时整站互换, 2026-10-26 实测 63 枚/32 站);
  多牌站的牌必须全部落在该站圈环(data-ring)内;
- V4 站覆盖: 每站至少 1 条线(有牌), 每线牌数 == 该线卡片钉位数(CSV 有码);
用法: python tools/gen-quiz-data.py
"""
import importlib.util
import json
import os
import re
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
    return gcc.line_disp(ln)   # 显示名=共享派生规则+定制表(custom_params.LINE_DISPLAY)


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

    # ---------- V3 编号牌配对(牌面内容即身份) ----------
    # codes SVG 绘制端(chip_svg)把隔线色+线号字+序号字按 (站,线) 画进牌面, 牌面即权威
    # 身份: 解码牌面 -> (线, 序号) -> CSV 唯一反查 (站,线)。旧"就近钉位指派"废弃:
    # 钉位与牌实际落位在多牌站错位时整站身份互换(2026-10-26 实测 63 枚/32 站)。
    # 钉位现在只用于: ①别名消歧(归一站名的 codes 双条目取卡片原名) ②漂移报告。
    details = gcc.chip_details(tc)
    chips = [(d['x'], d['y'], d['w'], d['h']) for d in details]
    check(len(details) == 400 and all(
        d['inner'].startswith('<line') and d['inner'].endswith('</text>')
        and d['inner'].count('<text') == 2 for d in details),
        'V3 逐牌内标记 line+双text 结构 (实得 %d)' % len(details))
    rings = gcc.ring_elements(tc)
    pins = {}          # (nm, ln) -> (cx, cy)   (别名消歧 + 漂移报告)
    pin_count = {}
    for ln in gcc.ORDER:
        card = gcc.parse_card(ln)
        pin_count[ln] = len(card['pins'])
        for (nm, cx, cy) in card['pins']:
            if (nm, ln) in codes:
                pins[(nm, ln)] = (cx, cy)
    pin_names = {nm for (nm, _ln) in pins}
    disp2line = {}
    for (_nm, ln), (disp, _serial) in codes.items():
        disp2line.setdefault(disp, ln)

    chip_key = [None] * len(chips)      # idx -> (nm, ln)
    drift = []                          # (距离, (nm, ln)) 钉位漂移报告用
    for ci, d in enumerate(details):
        lm = re.search(r'stroke="(#[0-9A-Fa-f]{6})"', d['inner'])
        texts = re.findall(r'>([^<>]+)</text>', d['inner'])
        if not lm or len(texts) != 2:
            fail.append('V3 牌%d 牌面解码失败(缺隔线色或非双text)' % ci)
            continue
        stroke, t_disp, t_serial = lm.group(1).upper(), texts[0], texts[1]
        ln = disp2line.get(t_disp)
        if ln is None:
            fail.append('V3 牌%d 线号字 %r 无所属线' % (ci, t_disp))
            continue
        ref = line_color.get(ln, '').upper()
        if ref and ref != stroke:
            fail.append('V3 牌%d 隔线色 %s != %s 徽标色 %s' % (ci, stroke, ln, ref))
        hits = sorted(nm for (nm, l2), v in codes.items()
                      if l2 == ln and v == (t_disp, t_serial) and nm in pin_names)
        if len(hits) != 1:
            fail.append('V3 牌%d (%s|%s) CSV 反查命中 %d 义: %s' % (ci, t_disp, t_serial, len(hits), hits))
            continue
        chip_key[ci] = (hits[0], ln)
        pin = pins.get(chip_key[ci])
        if pin:
            drift.append((dist((d['x'] + d['w'] / 2, d['y'] + d['h'] / 2), pin), chip_key[ci]))
    check(len(chip_key) == 400 and all(chip_key), 'V3 牌 400 全配对 (实得 %d)' % sum(1 for k in chip_key if k))
    check(set(chip_key) == set(pins), 'V3 (站,线)全覆盖 (差集 %s)' % (set(chip_key) ^ set(pins)))
    if drift:
        drift.sort(reverse=True)
        over = [(d, k) for d, k in drift if d > PAIR_RADIUS]
        print('  info V3 钉位漂移 最大 %.1fpt (%s)%s' % (
            drift[0][0], '/'.join(drift[0][1]),
            ('; %d 枚超 %.0fpt 阈(身份已由牌面保证, 仅报告不拦截)' % (len(over), PAIR_RADIUS)) if over else ''))
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
    for (x, y, w, h), d, key in zip(chips, details, chip_key):
        nm, ln = key
        disp, serial = codes[key]
        chips_out.append({'nm': nm, 'line': ln, 'serial': serial,
                          'x': round(x, 2), 'y': round(y, 2), 'w': round(w, 2), 'h': round(h, 2),
                          'd': d['inner']})
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
        'gen': __import__('datetime').date.today().strftime('%Y%m%d'),
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
