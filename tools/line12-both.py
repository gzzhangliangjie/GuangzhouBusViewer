# -*- coding: utf-8 -*-
"""12号线双段卡合成器: 南段卡(rebuild10 CFG 产物) + 北段卡(独立标准卡) → 一卡两段。
两段各自由标准管线 group-card.build 生成(终点延长线版式/数字块对齐/EN拆行 = 全线统一规则),
本脚本只做拼装: 合并四组、去北段头部徽标、并 viewBox、加 data-multi/chains。没有任何放置逻辑。
用法: python tools/rebuild10.py 12号线 12号线北段 && python tools/line12-both.py
"""
import sys, io, re, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOUTH = os.path.join(ROOT, 'assets/lines/line-12号线.svg')                 # rebuild10 南段产物
NORTH = os.path.join(ROOT, 'data/_card-bases/line-12号线北段.svg')          # rebuild10 北段中间产物
CARD = os.path.join(ROOT, 'assets/lines/line-12号线.svg')                  # 最终双段卡(覆写南段产物)
OUT = os.path.join(ROOT, 'data/line12-both.json')

NORTH_CHAIN = ['浔峰岗', '浔峰岗北', '聚龙', '广州白云站', '新市墟', '白云文化广场', '广州体育馆']
SOUTH_CHAIN = ['二沙岛', '赤岗塔', '赤岗', '赤沙北', '赤沙', '北山', '官洲', '大学城北', '大学城南']


def group_span(s, gid):
    """返回 (组内容起点, 组内容终点) — 深度配对(线路徽标组内嵌套徽标子组)。"""
    m = re.search(r'<g id="%s"(?:>| )' % gid, s)
    start = m.end()
    depth, j = 1, start
    while depth:
        no, nc = s.find('<g', j), s.find('</g>', j)
        if no != -1 and no < nc:
            depth += 1
            j = no + 2
        else:
            depth -= 1
            j = nc + 4
    return start, j - 4


def inject(s, gid, add):
    a, b = group_span(s, gid)
    return s[:a] + add + s[a:]   # 前插: 文档序=北段在前(verify_naming V1 真值序)


def vb_of(s):
    return [float(v) for v in re.search(r'viewBox="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"', s).groups()]


def main():
    south = open(SOUTH, encoding='utf-8').read()
    north = open(NORTH, encoding='utf-8').read()
    assert 'data-multi' not in south and 'data-multi' not in north, '输入须为单段标准卡'

    for gid in ('走廊', '站圆', '线路徽标', '站名标注'):
        a, b = group_span(north, gid)
        inner = north[a:b]
        if gid == '线路徽标':   # 双段卡只保留一个头部徽标(南段的)
            inner = re.sub(r'<g data-badge="header".*?</g>', '', inner, count=1)
        south = inject(south, gid, inner)

    # viewBox 并集(14 边距), 背景矩形跟随
    vs, vn = vb_of(south), vb_of(north)
    x0 = min(vs[0], vn[0]) - 14
    y0 = min(vs[1], vn[1]) - 14
    x1 = max(vs[0] + vs[2], vn[0] + vn[2]) + 14
    y1 = max(vs[1] + vs[3], vn[1] + vn[3]) + 14
    m = re.search(r'viewBox="[-\d. ]+"', south)
    south = south.replace(m.group(0), 'viewBox="%.1f %.1f %.1f %.1f"' % (x0, y0, x1 - x0, y1 - y0), 1)
    mb = re.search(r'<rect x="[-\d.]+" y="[-\d.]+" width="[-\d.]+" height="[-\d.]+" fill="#ffffff"\s*/?>', south)
    south = south.replace(mb.group(0), '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#ffffff" />'
                          % (x0, y0, x1 - x0, y1 - y0), 1)

    # data-multi + 双链 + data-pins 并集
    pins = sorted(set((re.search(r'data-pins="([^"]*)"', south).group(1).split(',') if 'data-pins' in south else [])
                      + (re.search(r'data-pins="([^"]*)"', north).group(1).split(',') if 'data-pins' in north else [])))
    south = re.sub(r'data-pins="[^"]*"', 'data-pins="%s"' % ','.join(pins), south, count=1)
    chains = '|'.join([','.join(NORTH_CHAIN), ','.join(SOUTH_CHAIN)])
    south = south.replace('<svg xmlns="http://www.w3.org/2000/svg"',
                          '<svg xmlns="http://www.w3.org/2000/svg" data-multi="1" data-chains="%s"' % chains, 1)

    open(CARD, 'w', encoding='utf-8').write(south)
    json.dump({'north': NORTH_CHAIN, 'south': SOUTH_CHAIN}, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
    print('双段卡合成 → %s (viewBox %.0f,%.0f %.0fx%.0f)' % (CARD, x0, y0, x1 - x0, y1 - y0))


if __name__ == '__main__':
    main()
