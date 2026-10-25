# -*- coding: utf-8 -*-
"""工具自测(2026-10-25): gen共享接口单元 + 产物不变量金丝 + 快照沙箱回环。秒级无渲染。
precommit-gate 在 T3(纯脚本)与 T2生成器链档自动调用; 也可手动 python tools/selftest.py。
⚠️产物数字金丝(41徽标/318文字/400牌/16胶囊/302圆/scale0.314)是定稿冻结值,
随定稿变更需有意识更新本文件(与基线accept同理, 不许静默漂移)。
"""
import io, os, sys, re, json, tempfile, shutil, importlib.util
import xml.etree.ElementTree as ET
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

FAILS = []
N = [0]

def check(name, cond, detail=''):
    N[0] += 1
    print('  %s %s%s' % ('✓' if cond else '✗', name, ('' if cond else '  <-- ' + str(detail))))
    if not cond:
        FAILS.append(name)

# ================= A. gen 共享接口(合成SVG, §1.7地基) =================
print('== A. gen 共享接口 ==')
spec = importlib.util.spec_from_file_location('gen', os.path.join(ROOT, 'tools', 'gen-codes-cards.py'))
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

check('线名归一 1->1号线', gen.badge_text_to_line('1') == '1号线')
check('线名归一 APM->APM线', gen.badge_text_to_line('APM') == 'APM线')
check('线名归一 GF->广佛线', gen.badge_text_to_line('GF') == '广佛线')
check('线名归一 全名原样', gen.badge_text_to_line('2号线') == '2号线')

# badge_elements: data-term 在 transform 前/后都要解析出key/term/坐标(§1.6属性无序教训)
els_a = gen.badge_elements('<g data-badge="header" data-term="西塱" transform="translate(10.00 20.00) scale(0.314)">'
                           '<rect width="80.0" height="43.0"/><text>1</text></g>')
els_b = gen.badge_elements('<g transform="translate(30.00 40.00) scale(0.5)" data-term="嘉禾望岗" data-badge="header">'
                           '<rect width="80.0" height="43.0"/><text>2</text></g>')
check('badge解析(term在前)', len(els_a) == 1 and els_a[0]['key'] == '1号线' and els_a[0]['term'] == '西塱'
      and els_a[0]['x'] == 10.0 and els_a[0]['y'] == 20.0 and els_a[0]['scale'] == 0.314
      and abs(els_a[0]['h'] - 43.0 * 0.314) < 1e-9, els_a)
check('badge解析(term在后)', len(els_b) == 1 and els_b[0]['key'] == '2号线'
      and els_b[0]['term'] == '嘉禾望岗' and els_b[0]['x'] == 30.0, els_b)
# scale链: 只取首个scale(tr_attr契约, sync整值替换依赖此语义)
els_c = gen.badge_elements('<g data-badge="header" transform="translate(1.00 2.00) scale(0.314) scale(0.314)">'
                           '<rect width="80.0" height="43.0"/><text>3</text></g>')
check('badge解析scale链取首值', len(els_c) == 1 and els_c[0]['scale'] == 0.314
      and els_c[0]['tr_attr'] == 'translate(1.00 2.00) scale(0.314)', els_c)

chip_svg = ('<g id="编号牌">'
            '<rect x="0.00" y="0.00" width="20.50" height="9.00" fill="#FFFFFF" stroke="#1E88E5" stroke-width="1"/>'
            '<rect x="30.00" y="0.00" width="20.50" height="9.00" fill="none" stroke="#E53935" data-ring="1"/>'
            '</g>')
ch, rn, _ = gen.chip_elements(chip_svg)
check('chip/ring区分(白实心vs ring)', len(ch) == 1 and len(rn) == 1, (ch, rn))
ch3, rn3, _ = gen.chip_elements('<g id="编号牌">'
                                '<rect x="0.00" y="0.00" width="20.50" height="9.00"/></g>')
check('无stroke的rect不入牌(chip契约)', len(ch3) == 0 and len(rn3) == 0, (ch3, rn3))

check('corridor_segments基础', gen.corridor_segments('<line x1="0" y1="0" x2="3" y2="4"/>'[0:0].join(
    ['<line x1="0" y1="0" x2="3" y2="4"/>'])) == [(0.0, 0.0, 3.0, 4.0)])

mk = gen.marker_elements('<svg><g id="站圆"><circle cx="1.0" cy="2.0" r="4.5" data-nm="甲"/></g>'
                         '<g id="换乘标记"><circle cx="3.0" cy="4.0" r="5" data-nm="乙"/>'
                         '<line x1="0" y1="0" x2="10" y2="0" data-nm="丙" style="stroke-width:14"/>'
                         '<line x1="0" y1="0" x2="10" y2="0" data-nm="丙" style="stroke-width:10"/>'
                         '<path d="M5 5 L8 5 L8 8 Z" data-nm="丁"/></g>'
                         '<g id="走廊"><line x1="99" y1="99" x2="100" y2="100" data-nm="丙"/></g></svg>')
check('marker圆=2(仅站圆/换乘两组)', len(mk['circles']) == 2, mk['circles'])
check('marker线段胶囊黑白去重=1', sum(1 for h, _ in mk['capsules'] if len(h) == 2) == 1, mk['capsules'])
check('marker多边形胶囊解析', any(len(h) == 3 and h[2] == (8.0, 8.0) for h, _ in mk['capsules']))
check('marker不含走廊组线段', all(h[0] != (99.0, 99.0) for h, _ in mk['capsules']))

# ================= B. 产物不变量金丝(定稿冻结值) =================
print('== B. 产物不变量金丝 ==')
base = open('assets/lines/network-全网.svg', encoding='utf-8').read()
codes = open('assets/lines/network-全网.codes.svg', encoding='utf-8').read()
for nm2, t2 in (('底图', base), ('codes', codes)):
    try:
        ET.fromstring(t2)
        check('XML %s' % nm2, True)
    except ET.ParseError as e:
        check('XML %s' % nm2, False, str(e))

badges = gen.badge_elements(codes)
check('徽标数=41', len(badges) == 41, len(badges))
check('徽标全带data-term', all(b['term'] for b in badges))
check('(线名,终点)对唯一', len(set((b['key'], b['term']) for b in badges)) == len(badges))
chainy = [b['key'] for b in badges if re.search(r'scale\([\d.]+\)\s+scale\(', b['tr_attr'])]
check('transform单scale无链(16连scale金丝)', not chainy, chainy[:3])
check('scale统一0.314(精度病金丝)', set(b['scale'] for b in badges) == {0.314},
      set(b['scale'] for b in badges))
miss = [k for k in set(b['key'] for b in badges)
        if not os.path.exists(os.path.join(ROOT, 'assets', 'lines', 'line-%s.svg' % k))]
check('徽标线卡文件齐全', not miss, miss)

zh = [t for t in gen.text_elements(codes) if not t['en']]
check('站名文字=318', len(zh) == 318, len(zh))
ch2, rn2, _ = gen.chip_elements(codes)
check('编号牌=400', len(ch2) == 400, len(ch2))
mk2 = gen.marker_elements(base)
check('换乘胶囊=16', len(mk2['capsules']) == 16, len(mk2['capsules']))
check('标记圆=302', len(mk2['circles']) == 302, len(mk2['circles']))

bb = gen.badge_elements(base)
check('底图徽标transform与codes全等(同步金丝)',
      [b['tr_attr'] for b in bb] == [b['tr_attr'] for b in badges])
check('底图徽标data-term与codes全等',
      [b['term'] for b in bb] == [b['term'] for b in badges])

# 站圆都贴走廊(单线卡时代铁律3的全网版; 实测max=0.94, 阈值2.0)
mk_seg = gen.corridor_segments(base)

def _pt_seg(px, py, s):
    vx, vy = s[2] - s[0], s[3] - s[1]
    l2 = vx * vx + vy * vy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - s[0]) * vx + (py - s[1]) * vy) / l2))
    return ((px - s[0] - t * vx) ** 2 + (py - s[1] - t * vy) ** 2) ** 0.5

worst = max(min(_pt_seg(c[0], c[1], s) for s in mk_seg) for c in mk2['circles'])
check('站圆贴走廊(最远%.2f<=2.0)' % worst, worst <= 2.0, worst)

# 组序不变量: 走廊<站圆<换乘标记<线路徽标<站名标注(z序=视觉层级)
pos = [base.index('<g id="%s"' % g) for g in ('走廊', '站圆', '换乘标记', '线路徽标', '站名标注')]
check('底图组序不变量', pos == sorted(pos), pos)

# 内容不出画(单线卡v3教训: viewBox吃掉宽站名)
vb4 = [float(v) for v in re.search(r'viewBox="([-\d. ]+)"', base[:400]).group(1).split()]
out_txt = [t['nm'] for t in gen.text_elements(base)
           if t['box'][0] < vb4[0] - 0.5 or t['box'][1] < vb4[1] - 0.5
           or t['box'][0] + t['box'][2] > vb4[0] + vb4[2] + 0.5
           or t['box'][1] + t['box'][3] > vb4[1] + vb4[3] + 0.5]
out_bd = [b['key'] for b in bb if b['x'] < vb4[0] or b['y'] < vb4[1]
          or b['x'] + b['w'] > vb4[0] + vb4[2] or b['y'] + b['h'] > vb4[1] + vb4[3]]
check('文字不出画', not out_txt, out_txt[:5])
check('徽标不出画', not out_bd, out_bd[:5])

# 被引用线卡完整性(卡=徽标尺寸/走廊色真源, load-bearing输入)
card_bad = []
for k in sorted(set(b['key'] for b in badges)):
    p = os.path.join(ROOT, 'assets', 'lines', 'line-%s.svg' % k)
    try:
        src = open(p, encoding='utf-8').read()
        ET.fromstring(src)
        assert re.search(r'id="走廊".*?stroke:#[0-9A-Fa-f]{6}', src, re.S), '缺走廊色'
        assert 'data-badge="header"' in src, '缺徽标头'
    except Exception as e:
        card_bad.append('%s:%s' % (k, e))
check('被引用线卡结构完整(41张)', not card_bad, card_bad[:3])

# ================= C. 快照沙箱回环 =================
print('== C. 快照沙箱 ==')
spec2 = importlib.util.spec_from_file_location('svgsnap', os.path.join(ROOT, 'tools', 'svg-snapshot.py'))
snap = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(snap)
tmp = tempfile.mkdtemp()
try:
    fa, fb = os.path.join(tmp, 'a.svg'), os.path.join(tmp, 'b.svg')
    open(fa, 'w').write('A1\n')
    open(fb, 'w').write('B1\n')
    snap.FILES = [fa, fb]
    snap.SLOT = os.path.join(tmp, 'slot')
    snap.MAN = os.path.join(snap.SLOT, '_manifest.json')
    snap.save('t1')
    open(fa, 'w').write('A2\n')
    snap.restore()
    check('快照回环字节还原', open(fa).read() == 'A1\n' and open(fb).read() == 'B1\n')
    open(fa, 'w').write('AX\n')
    open(os.path.join(snap.SLOT, 'a.svg'), 'w').write('CORRUPT\n')
    try:
        snap.restore()
        check('损坏快照拒绝还原', False, '竟未拒绝')
    except SystemExit:
        check('损坏快照拒绝还原(且未污染文件)', open(fa).read() == 'AX\n')
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ================= D. 门禁突变自检(baseline-lock沙箱: 证明它真的会红) =================
print('== D. 基线锁突变自检 ==')
spec3 = importlib.util.spec_from_file_location('bl', os.path.join(ROOT, 'tools', 'baseline-lock.py'))
bl = importlib.util.module_from_spec(spec3)
spec3.loader.exec_module(bl)
tmp2 = tempfile.mkdtemp()
try:
    fa = os.path.join(tmp2, 'base.svg')
    fc = os.path.join(tmp2, 'codes.svg')
    fb = os.path.join(tmp2, 'baseline.json')
    CODES_MK = ('<svg><g id="站名标注"><text x="10.00" y="20.00" font-size="7.5">甲</text></g>'
                '<g data-badge="header" data-term="甲" transform="translate(5.00 6.00) scale(0.314)">'
                '<rect width="80.0" height="43.0"/><text>1</text></g></svg>')
    open(fa, 'w').write('<svg/>')
    open(fc, 'w').write(CODES_MK)
    bl.BASE, bl.CODES, bl.KEY_FILES = fb, fc, [fa, fc]

    def bl_check():
        import contextlib
        buf = io.StringIO()
        old_argv, old_out = sys.argv, sys.stdout
        sys.argv = ['baseline-lock', 'check']
        try:
            with contextlib.redirect_stdout(buf):
                bl.main()
            return 0, buf.getvalue()
        except SystemExit as e:
            return e.code or 1, buf.getvalue()
        finally:
            sys.argv, sys.stdout = old_argv, old_out

    sys.argv = ['baseline-lock', 'accept']
    bl.main()
    rc, out = bl_check()
    check('基线锁: 未变=0回归', rc == 0 and '0回归' in out, (rc, out))
    open(fc, 'w').write(CODES_MK.replace('translate(5.00 6.00)', 'translate(9.00 6.00)'))
    rc, out = bl_check()
    check('基线锁: 徽标移位会红', rc == 1 and '移位' in out, (rc, out))
    open(fc, 'w').write(CODES_MK.replace('<g data-badge="header"', '<g data-badge="head"'))
    rc, out = bl_check()
    check('基线锁: 徽标消失会红', rc == 1 and '消失' in out, (rc, out))
    open(fc, 'w').write(CODES_MK + '<!--x-->')
    rc, out = bl_check()
    check('基线锁: 字节变更报产物变更', rc == 1 and '产物变更' in out, (rc, out))
    open(fc, 'w').write(CODES_MK.replace('<text x="10.00" y="20.00" font-size="7.5">甲</text>', ''))
    rc, out = bl_check()
    check('基线锁: 文字消失会红', rc == 1 and '消失' in out, (rc, out))
finally:
    shutil.rmtree(tmp2, ignore_errors=True)

print()
if FAILS:
    print('SELFTEST FAIL %d项: %s' % (len(FAILS), '; '.join(FAILS)))
    sys.exit(1)
print('SELFTEST ALL PASS (%d项)' % N[0])
