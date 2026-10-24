# -*- coding: utf-8 -*-
"""徽标像素审计门禁: 渲染后全部徽标四边外扩3px扫描, 任何线色穿透=FAIL。
规范: 徽标不得压任何走廊; ⚠️viewBox必须从SVG实时读取(徽标移动会改变画布bbox, 硬编码=坐标错位假告警)。
用法: python tools/verify-badges-pixel.py  (改徽标必跑, 2026-10-23教训)
"""
import io, os, sys, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_card_pixel import render

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG = os.path.join(ROOT, 'assets/lines/network-全网.svg')
im, _ = render(SVG)
head = open(SVG, encoding='utf-8').read(400)
VB = [float(v) for v in re.search(r'viewBox="([-\d. ]+)"', head).group(1).split()]
H, W = im.shape[:2]
sx, sy = W / VB[2], H / VB[3]

def sample(x, y):
    px_, py_ = int((x - VB[0]) * sx), int((y - VB[1]) * sy)
    if 0 <= px_ < W and 0 <= py_ < H:
        return tuple(int(v) for v in im[py_, px_])
    return (255, 255, 255)

def is_line_color(p):
    r, g, b = p
    if r > 235 and g > 235 and b > 235:
        return False
    if r < 60 and g < 60 and b < 60:
        return False
    if max(r, g, b) - min(r, g, b) < 25:
        return False   # 无彩灰=文字AA(走廊19色全有饱和度), --disable-lcd-text下文字边缘为灰阶
    return True


def make_own_ok(own_rgb):
    """本线色豁免(规范: 徽标有底色可盖本线延长线, 12号线北段判例):
    像素=本线色与白的混色(含AA)不算穿透; 他线色仍FAIL。"""
    ow, o_x, o_y = 255.0, 255.0, 255.0
    c_r, c_g, c_b = own_rgb
    wr, wg, wb = 255.0, 255.0, 255.0

    def own_ok(p):
        r, g, b = p
        # 主通道解混比a, 其余通道残差校验(残差大=混入了别的色)
        chans = [(c_r, wr, r), (c_g, wg, g), (c_b, wb, b)]
        dom = max(chans, key=lambda t: abs(t[1] - t[0]))
        d = dom[1] - dom[0]
        if abs(d) < 1e-6:
            return True
        a = (dom[1] - dom[2]) / d
        if a < -0.15 or a > 1.15:
            return False
        for c, w, q in chans:
            pred = w + a * (c - w)
            if abs(q - pred) > 40.0:
                return False
        return True

    return own_ok

LINES_DIR = os.path.join(ROOT, 'assets/lines')
# 徽标清单+scale直接从底图SVG实读(2026-10-24: scale=18/43统一缩小后硬编码0.7/0.5已失效);
# 尺寸=各卡header rect实际宽高×scale(广佛73/APM 102.2与其余80不同), key→线名
svg_src = open(SVG, encoding='utf-8').read()
KEY2LN = {'GF': '广佛线', 'APM': 'APM线'}
_LNAMES = {'1号线', '2号线', '3号线', '4号线', '5号线', '6号线', '7号线', '8号线',
           '9号线', '10号线', '11号线', '12号线', '13号线', '14号线', '18号线',
           '21号线', '22号线', '广佛线', 'APM线'}   # 广佛线不以"号线"结尾, 不能只判后缀
size = {}
badges = []
for _m in re.finditer(r'<g data-badge="header" transform="translate\([-\d.]+ [-\d.]+\) scale\(([\d.]+)\)"[^>]*>(.*?)</g>', svg_src, re.S):
    _sc = float(_m.group(1))
    _tr = re.search(r'translate\(([-\d.]+) ([-\d.]+)\)', _m.group(0))
    _ts = re.findall(r'>([^<>]+)</text>', _m.group(2))
    _key = _ts[0].strip() if _ts else '?'
    _nm = _key if _key in _LNAMES else (KEY2LN.get(_key) or (_key + '号线' if _key.isdigit() else '?'))
    if _nm not in size:
        _src = open(os.path.join(LINES_DIR, 'line-%s.svg' % _nm), encoding='utf-8').read()
        _mm = re.search(r'<g data-badge="header"[^>]*>(.*?)</g>', _src, re.S)
        _rr = re.search(r'<rect x="([\d.-]+)" y="([\d.-]+)" width="([\d.]+)" height="([\d.]+)"', _mm.group(1))
        size[_nm] = (float(_rr.group(3)) * _sc, float(_rr.group(4)) * _sc)
    badges.append((_nm, float(_tr.group(1)), float(_tr.group(2))))
# 各线走廊色(卡走廊stroke)用于本线色豁免
own_color = {}
for _nm in size:
    _src = open(os.path.join(LINES_DIR, 'line-%s.svg' % _nm), encoding='utf-8').read()
    _m3 = re.search(r'id="走廊".*?stroke:(#[0-9A-Fa-f]{6})', _src, re.S)
    if _m3:
        own_color[_nm] = tuple(int(_m3.group(1)[i:i + 2], 16) for i in (1, 3, 5))
bad = 0
for nm, bx, by in badges:
    bw, bh = size[nm]
    own_ok = make_own_ok(own_color[nm]) if nm in own_color else (lambda p: False)
    hits = []
    for xi in range(int(bx) - 3, int(bx + bw) + 4):
        for yy in (by - 3, by + bh + 3):
            smp = sample(xi, yy)
            if is_line_color(smp) and not own_ok(smp):
                hits.append(('T' if yy < by else 'B', xi, yy, smp))
    for yi in range(int(by) - 3, int(by + bh) + 4):
        for xx in (bx - 3, bx + bw + 3):
            smp = sample(xx, yi)
            if is_line_color(smp) and not own_ok(smp):
                hits.append(('L' if xx < bx else 'R', xx, yi, smp))
    if hits:
        bad += 1
        print('!! %s (%.0f,%.0f) 穿透%d处: %s' % (nm, bx, by, len(hits), hits[:3]))
print('徽标像素审计: %d/%d 穿透' % (bad, len(badges)))
sys.exit(1 if bad else 0)
