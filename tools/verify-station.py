# -*- coding: utf-8 -*-
"""单站局部验证(迭代期秒级反馈; 提交仍由pre-commit强制verify-all全量, 本工具不替代):
  0) XML well-formed(全网+codes两份)
  1) codes/base 站点同步一致(文字+徽标transform; 不同步=先跑 tools/sync-base.py)
  2) 几何(codes SVG): V5牌距>=0.5 / V8徽标-文字>=0.3 / 他文字>=1.0 / V7贴牌<=9pt /
     走廊>=4.5(仅WARN: 密集档白光环历史定稿区不在此门)
  3) 像素(base SVG裁剪渲染): 站点窗口内徽标四边外扩3px扫描, 他线色穿透=FAIL
     (is_line_color/本线豁免/他徽标rect豁免与verify-badges-pixel同口径, 全局链为准)
用法: python tools/verify-station.py 站名 [--no-pixel]
"""
import io, os, re, sys, subprocess, tempfile, shutil
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location('gen', os.path.join(ROOT, 'tools', 'gen-codes-cards.py'))
gen = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(gen)

NM = sys.argv[1]
NO_PIXEL = '--no-pixel' in sys.argv
BASE = 'assets/lines/network-全网.svg'
CODES = 'assets/lines/network-全网.codes.svg'
LINES_DIR = os.path.join(ROOT, 'assets', 'lines')
SCALE = 2
EDGE = r'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'

fails, warns = [], []

# ---------- 0) XML ----------
for f in (BASE, CODES):
    try:
        ET.fromstring(open(f, encoding='utf-8').read())
        print('  XML OK   %s' % f)
    except ET.ParseError as e:
        fails.append('XML语法错误 %s: %s' % (f, e))

base = open(BASE, encoding='utf-8').read()
codes = open(CODES, encoding='utf-8').read()

# ---------- 1) 同步一致性 ----------
c_lbl = {e['nm']: e for e in gen.text_elements(codes) if not e['en']}
b_lbl = {e['nm']: e for e in gen.text_elements(base) if not e['en']}
e_c = c_lbl.get(NM)
if not e_c:
    print('codes SVG 无站名文字 "%s", 退出。' % NM)
    sys.exit(1)
e_b = b_lbl.get(NM)
if not e_b or (e_c['x'], e_c['y'], e_c['fs']) != (e_b['x'], e_b['y'], e_b['fs']):
    fails.append('文字与底图不同步(codes %.2f,%.2f vs base %s) —— 先跑 python tools/sync-base.py'
                 % (e_c['x'], e_c['y'], ('%.2f,%.2f' % (e_b['x'], e_b['y'])) if e_b else '缺失'))
c_terms = [b for b in gen.badge_elements(codes) if b['term'] == NM]
b_badges = gen.badge_elements(base)
b_terms = [b for b in b_badges if b['term'] == NM]
if [b['tr_attr'] for b in c_terms] != [b['tr_attr'] for b in b_terms]:
    fails.append('徽标与底图不同步(data-term=%s, codes %d枚 vs base %d枚或值异) —— 先跑 python tools/sync-base.py'
                 % (NM, len(c_terms), len(b_terms)))

# ---------- 2) 几何(codes) ----------
box = e_c['box']
chips, rings, _ = gen.chip_elements(codes)
corridors = gen.corridor_segments(codes)
labels = gen.text_elements(codes)
badges = gen.badge_elements(codes)

# 英文行(与V7同合并规则: |dx|<3 且 0<dy<16)
en_near = [t for t in labels if t['en'] and abs(t['x'] - e_c['x']) < 3 and 0 < t['y'] - e_c['y'] < 16]
boxes = [box] + [t['box'] for t in en_near]

_e = gen.RING_PAD + gen.RIM
gaps5 = [gen._gap(box, c) for c in chips]
gaps5 += [gen._gap(box, (r[0] - _e, r[1] - _e, r[2] + 2 * _e, r[3] + 2 * _e)) for r in rings]
g5 = min(gaps5) if gaps5 else 9e9
print('  V5 牌距     %.2f (>=0.5)' % g5)
if g5 < 0.5:
    fails.append('V5 牌压站名: 净距%.2f<0.5' % g5)

g8 = min([gen._gap((b['x'], b['y'], b['w'], b['h']), tb) for b in badges for tb in boxes] or [9e9])
print('  V8 徽标距   %.2f (>=0.3)' % g8)
if g8 < 0.3:
    fails.append('V8 徽标压文字: 净距%.2f<0.3' % g8)

g_txt = min([gen._gap(box, t['box']) for t in labels if t['nm'] != NM] or [9e9])
print('  他文字距    %.2f (>=1.0)' % g_txt)
if g_txt < 1.0:
    fails.append('文字叠文字: 净距%.2f<1.0' % g_txt)

g_corr = min([gen.rect_seg_dist(box, s) for s in corridors] or [9e9])
print('  走廊距      %.2f (>=4.5, 仅WARN)' % g_corr)
if g_corr < 4.5:
    warns.append('文字距走廊%.2f<4.5(密集档白光环历史定稿区可豁免, 人工确认)' % g_corr)

x0b = min(b[0] for b in boxes)
y0b = min(b[1] for b in boxes)
x1b = max(b[0] + b[2] for b in boxes)
y1b = max(b[1] + b[3] for b in boxes)
gbox = (x0b, y0b, x1b - x0b, y1b - y0b)
g7 = min([gen._gap(gbox, c) for c in chips] or [0.0])
if g7 > 12:
    print('  V7 贴牌     暂缓(无牌暂缓站, 最近牌%.1f>12)' % g7)
else:
    print('  V7 贴牌     %.2f (<=9)' % g7)
    if g7 > 9:
        fails.append('V7 标签离牌远: %.2f>9' % g7)

# ---------- 3) 像素(base裁剪渲染) ----------
if not NO_PIXEL:
    win = 150.0
    cx0, cy0 = box[0] + box[2] / 2, box[1] + box[3] / 2
    x0, y0, x1, y1 = cx0 - win, cy0 - win, cx0 + win, cy0 + win
    for b in b_terms:
        x0 = min(x0, b['x'] - 10)
        y0 = min(y0, b['y'] - 10)
        x1 = max(x1, b['x'] + b['w'] + 10)
        y1 = max(y1, b['y'] + b['h'] + 10)
    ww, wh = x1 - x0, y1 - y0

    NS = 'http://www.w3.org/2000/svg'
    ET.register_namespace('', NS)
    root = ET.fromstring(base)
    W, H = int(ww * SCALE), int(wh * SCALE)
    root.set('viewBox', '%.2f %.2f %.2f %.2f' % (x0, y0, ww, wh))
    root.set('width', str(W))
    root.set('height', str(H))
    svg = ET.tostring(root, encoding='unicode')
    tmpdir = os.path.join(ROOT, 'assets', 'lines', '_pixtmp')
    os.makedirs(tmpdir, exist_ok=True)
    html = os.path.join(tmpdir, '_stwrap.html')
    with open(html, 'w', encoding='utf-8') as f:
        f.write('<!DOCTYPE html><html><head><meta charset="UTF-8"><style>'
                'html,body{margin:0;padding:0;background:#fff;overflow:hidden}</style>'
                '</head><body>%s</body></html>' % svg)
    png = os.path.join(tempfile.gettempdir(), '_stpix.png')
    subprocess.run([EDGE, '--headless', '--disable-gpu', '--disable-lcd-text',
                    '--force-color-profile=srgb', '--force-device-scale-factor=1',
                    '--window-size=%d,%d' % (W, H), '--screenshot=%s' % png,
                    'file:///%s' % html.replace('\\', '/')], capture_output=True, timeout=60)
    shutil.rmtree(tmpdir, ignore_errors=True)
    im = np.array(Image.open(png).convert('RGB')).astype(int)
    Hh, Ww = im.shape[:2]
    sx, sy = Ww / ww, Hh / wh

    def sample(x, y):
        px_, py_ = int((x - x0) * sx), int((y - y0) * sy)
        if 0 <= px_ < Ww and 0 <= py_ < Hh:
            return tuple(int(v) for v in im[py_, px_])
        return (255, 255, 255)

    def is_line_color(p):
        r, g, b = p
        if r > 235 and g > 235 and b > 235:
            return False
        if r < 60 and g < 60 and b < 60:
            return False
        return max(r, g, b) - min(r, g, b) >= 25   # 无彩灰=文字AA; 走廊19色全有饱和度

    def make_own_ok(own_rgb):
        c_r, c_g, c_b = own_rgb
        wr = wg = wb = 255.0

        def own_ok(p):
            r, g, b = p
            chans = [(c_r, wr, r), (c_g, wg, g), (c_b, wb, b)]
            dom = max(chans, key=lambda t: abs(t[1] - t[0]))
            d = dom[1] - dom[0]
            if abs(d) < 1e-6:
                return True
            a = (dom[1] - dom[2]) / d
            if a < -0.15 or a > 1.15:
                return False
            return all(abs(w + a * (c - w) - q) <= 40.0 for c, w, q in chans)

        return own_ok

    own_color = {}
    for _nm in sorted(set(b['key'] for b in b_badges)):
        _src = open(os.path.join(LINES_DIR, 'line-%s.svg' % _nm), encoding='utf-8').read()
        _m3 = re.search(r'id="走廊".*?stroke:(#[0-9A-Fa-f]{6})', _src, re.S)
        if _m3:
            own_color[_nm] = tuple(int(_m3.group(1)[i:i + 2], 16) for i in (1, 3, 5))

    all_rects = [(b['x'], b['y'], b['x'] + b['w'], b['y'] + b['h']) for b in b_badges]

    def in_other_badge(x, y, own_idx):
        for j, (jx0, jy0, jx1, jy1) in enumerate(all_rects):
            if j != own_idx and jx0 <= x <= jx1 and jy0 <= y <= jy1:
                return True
        return False

    scan = [(i, b) for i, b in enumerate(b_badges)
            if b['x'] - 3 >= x0 and b['y'] - 3 >= y0
            and b['x'] + b['w'] + 3 <= x1 and b['y'] + b['h'] + 3 <= y1]
    bad = 0
    for i, b in scan:
        bx, by, bw, bh = b['x'], b['y'], b['w'], b['h']
        own_ok = make_own_ok(own_color[b['key']]) if b['key'] in own_color else (lambda p: False)
        hits = []
        for xi in range(int(bx) - 3, int(bx + bw) + 4):
            for yy in (by - 3, by + bh + 3):
                if in_other_badge(xi, yy, i):
                    continue
                smp = sample(xi, yy)
                if is_line_color(smp) and not own_ok(smp):
                    hits.append(('T' if yy < by else 'B', xi, yy, smp))
        for yi in range(int(by) - 3, int(by + bh) + 4):
            for xx in (bx - 3, bx + bw + 3):
                if in_other_badge(xx, yi, i):
                    continue
                smp = sample(xx, yi)
                if is_line_color(smp) and not own_ok(smp):
                    hits.append(('L' if xx < bx else 'R', xx, yi, smp))
        if hits:
            bad += 1
            fails.append('像素穿透 %s(%.0f,%.0f) %d处: %s' % (b['key'], bx, by, len(hits), hits[:3]))
    print('  像素扫描    窗口%.0fx%.0f 内徽标%d枚, 穿透%d' % (ww, wh, len(scan), bad))

# ---------- 结论 ----------
print()
for w in warns:
    print('WARN: %s' % w)
if fails:
    print('FAIL %s (%d项): %s' % (NM, len(fails), '; '.join(fails)))
    sys.exit(1)
print('PASS %s (局部验证%d项%s)' % (NM, 7, ('; %d条WARN待人工确认' % len(warns)) if warns else ''))
print('提交仍走全量: 人肉确认 -> git commit (pre-commit自动verify-all全量+accept基线)')
