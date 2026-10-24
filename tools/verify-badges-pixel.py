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
# 徽标清单统一走 gen.badge_elements(底层接口, 属性无序安全+线名归一)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location('gen', os.path.join(ROOT, 'tools', 'gen-codes-cards.py'))
gen = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(gen)
svg_src = open(SVG, encoding='utf-8').read()
size = {}
badges = []
for _e in gen.badge_elements(svg_src):
    _nm = _e['key']
    if _nm not in size:
        _src = open(os.path.join(LINES_DIR, 'line-%s.svg' % _nm), encoding='utf-8').read()
        _mm = re.search(r'<g data-badge="header"[^>]*>(.*?)</g>', _src, re.S)
        _rr = re.search(r'<rect x="([\d.-]+)" y="([\d.-]+)" width="([\d.]+)" height="([\d.]+)"', _mm.group(1))
        size[_nm] = (float(_rr.group(3)) * _e['scale'], float(_rr.group(4)) * _e['scale'])
    badges.append((_nm, _e['x'], _e['y']))
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

# V8 徽标不压文字(2026-10-24 用户: 万顷沙/南沙客运港徽标压文字为什么没检查出来——
# V5只查文字vs胶囊, 徽标vs文字无门): 站名标注文本盒(中文+英文)与徽标盒净距>=0.3, 纯几何硬算。
svg_txt = open(SVG, encoding='utf-8').read()
_lm8 = re.search(r'<g id="站名标注"[^>]*>(.*?)</g>', svg_txt, re.S)
text_boxes = []
if _lm8:
    for _t8 in re.finditer(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*font-size="([\d.]+)"[^>]*>([^<]+)</text>', _lm8.group(1)):
        _fs8 = float(_t8.group(3))
        _w8 = sum(_fs8 if ord(ch) > 0x2E80 else 0.56 * _fs8 for ch in _t8.group(4))
        _hh8 = _fs8 + 1.0
        _cy8 = float(_t8.group(2)) - 0.8 * _fs8 + _hh8 / 2
        text_boxes.append((float(_t8.group(1)) - _w8 / 2, _cy8 - _hh8 / 2, _w8, _hh8, _t8.group(4)))

def _gap8(r1, r2):
    dx = max(r2[0] - (r1[0] + r1[2]), r1[0] - (r2[0] + r2[2]), 0.0)
    dy = max(r2[1] - (r1[1] + r1[3]), r1[1] - (r2[1] + r2[3]), 0.0)
    return (dx * dx + dy * dy) ** 0.5

v8_bad = 0
for nm, bx, by in badges:
    bw, bh = size[nm]
    for tb in text_boxes:
        g8 = _gap8((bx, by, bw, bh), tb[:4])
        if g8 < 0.3:
            v8_bad += 1
            print('!! V8 徽标 %s 压文字 %s: 净距%.2f' % (nm, tb[4], g8))
print('V8 徽标-文字: %d/%d 重叠' % (v8_bad, len(badges)))
if v8_bad:
    bad += v8_bad

sys.exit(1 if bad else 0)
