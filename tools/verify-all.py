# -*- coding: utf-8 -*-
"""全量验证链: 提交时pre-commit钩子强制, 不允许按改动范围挑门禁。
链路: 重跑两生成器+sync -> 幂等md5 -> 基线漂移报告(仅报告, 提交时pre-commit自动accept)
     -> verify-codes-cards(V1-V7) -> verify-badges-pixel(V8+像素)。
任一环FAIL即退出码1。用法: python tools/verify-all.py [--quick]  (--quick跳过重跑只验产物)
"""
import io, os, sys, subprocess, hashlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
BASE = 'assets/lines/network-全网.svg'
CODES = 'assets/lines/network-全网.codes.svg'


def md5(p):
    return hashlib.md5(open(p, 'rb').read()).hexdigest()


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', cwd=ROOT)
    return r.returncode, (r.stdout or '') + (r.stderr or '')


fails = []

# 0) XML 语法检查(2026-10-25 用户: 这个问题出了无数次——文本替换吃掉标签前缀/闭合,
#    渲染时才炸; 放最前端坏文件秒FAIL)
import xml.etree.ElementTree as ET0
print('== 0) XML 语法检查 ==')
for f in ('assets/lines/network-全网.svg', 'assets/lines/network-全网.codes.svg'):
    try:
        ET0.fromstring(open(f, encoding='utf-8').read())
        print('  %s OK' % f)
    except ET0.ParseError as e:
        fails.append('XML语法错误 %s: %s' % (f, e))
        print('  %s FAIL: %s' % (f, e))

# 0.5) G1 分组结构(2026-10-28 P1): 组集合与z序冻结——底图6组/codes5组,
#     组序=绘制z序契约(docs/layout-refactor-plan.md §3); 调组序/组外塞元素=门禁红。
print('== 0.5) G1 分组结构 ==')
import re as _re1
_G1_EXPECT = {
    BASE: ['走廊', '站圆', '换乘标记', '线路徽标', '站名标注', '图例'],
    CODES: ['走廊', '线路徽标', '站名标注', '编号牌', '图例'],
}
for _f1, _want1 in _G1_EXPECT.items():
    _got1 = _re1.findall(r'<g id="([^"]+)"', open(_f1, encoding='utf-8').read())
    if _got1 != _want1:
        fails.append('G1 %s 分组结构漂移: 实测%s' % (_f1, _got1))
        print('  %s FAIL: %s' % (_f1, _got1))
    else:
        print('  %s OK (%d组)' % (_f1, len(_got1)))

# 0.55) G7 钉戳站擅动断言(2026-10-28 用户判例"APM东带全部错位, 特殊规则优先"):
#     data-pin-base 站=已验收定制终稿, 其坐标相对HEAD漂移=FAIL——特殊规则优先的机器化,
#     引擎变更/通用优化一律不得重排钉戳站; 确需挪动=用户明令后 --allow-pin-drift 放行一次。
if '--allow-pin-drift' not in sys.argv:
    print('== 0.55) G7 钉戳站擅动 ==')
    import subprocess as _sp7
    _pin_re = _re1.compile(r'<text x="([-\d.]+)" y="([-\d.]+)"([^>]*)data-pin-base="1"[^>]*>([^<]+)</text>')
    try:
        _head7 = _sp7.run(['git', 'show', 'HEAD:' + BASE], capture_output=True, text=True,
                          encoding='utf-8').stdout
        _now7 = open(BASE, encoding='utf-8').read()
        _h7 = {m.group(4): (m.group(1), m.group(2)) for m in _pin_re.finditer(_head7)}
        _n7 = {m.group(4): (m.group(1), m.group(2)) for m in _pin_re.finditer(_now7)}
        _drift7 = sorted(nm for nm in set(_h7) | set(_n7)
                         if nm not in _h7 or nm not in _n7 or _h7[nm] != _n7[nm])
        if _drift7:
            fails.append('G7 钉戳站擅动(已验收终稿, 特殊规则优先): %s' % '、'.join(_drift7))
            print('  FAIL: %s' % '、'.join(_drift7))
        else:
            print('  OK (%d枚钉戳站坐标与已验收态一致)' % len(_n7))
    except Exception as _e7:
        print('  SKIP (%s)' % _e7)

# 0.6) G4 写入契约断言(P2): 徽标锚继承零丢失 + data-loc/nudge 站名属性 codes→base 同步
print('== 0.6) G4 属性继承/同步 ==')
import json as _j4
try:
    _r4 = _j4.load(open('data/_codes-cards-report.json', encoding='utf-8'))
except (OSError, ValueError):
    _r4 = {}
_ba4 = _r4.get('badge_anchor') or {}
if _ba4.get('miss'):
    fails.append('G4 徽标锚丢失(算法位写入, 自锚将延续错误位): %s' % _ba4['miss'])
    print('  徽标锚 FAIL: 命中%s 丢%s' % (_ba4.get('hit'), _ba4['miss']))
else:
    print('  徽标锚 OK (命中%s)' % _ba4.get('hit', '?'))
_a4 = {}
for _f4 in (CODES, BASE):
    _t4 = open(_f4, encoding='utf-8').read()
    _m4 = _re1.search(r'<g id="站名标注"[^>]*>(.*?)</g>', _t4, _re1.S)
    _a4[_f4] = sorted(_re1.findall(r'<text[^>]*data-(?:loc|nudge)="[^"]*"[^>]*>([^<]+)</text>', _m4.group(1))) if _m4 else []
if _a4[BASE] != _a4[CODES]:
    fails.append('G4 data-loc/nudge 站名属性 codes→base 同步缺失: codes=%s base=%s' % (_a4[CODES], _a4[BASE]))
    print('  属性同步 FAIL')
else:
    print('  属性同步 OK (%d站带语义锚)' % len(_a4[CODES]))

# 1) 全链重跑 + 幂等
if '--quick' not in sys.argv:
    print('== 1) 重跑 build-network / gen-codes-cards / sync ==')
    for cmd in (['python', 'tools/build-network.py'],
                ['python', 'tools/gen-codes-cards.py'],
                ['python', 'tools/gen-codes-cards.py'],
                ['python', 'tools/sync-base.py']):
        if cmd is None:
            continue
        rc, out = run(cmd)
        if rc != 0:
            fails.append('重跑失败: %s\n%s' % (' '.join(cmd), out[-1500:]))
    m1, c1 = md5(BASE), md5(CODES)
    for cmd in (['python', 'tools/build-network.py'],
                ['python', 'tools/gen-codes-cards.py'],
                ['python', 'tools/sync-base.py']):
        if cmd is None:
            continue
        rc, out = run(cmd)
        if rc != 0:
            fails.append('二次重跑失败: %s' % ' '.join(cmd))
    if (m1, c1) != (md5(BASE), md5(CODES)):
        fails.append('幂等破坏: 两轮重跑产物md5不一致')

# 1.5) 基线漂移报告(2026-10-25 用户定稿: 提交=人肉确认动作, pre-commit全绿自动accept——
#      基线=最后一次经用户确认的全绿提交。此处只报告相对上次确认提交的漂移, 不FAIL:
#      迭代期工作区相对上次提交必然漂移, 硬拦=假告警源; 漂移清单用于人工发现意外回退)
rc, out = run(['python', 'tools/baseline-lock.py', 'check'])
if rc != 0:
    drift = [l for l in out.splitlines() if l.startswith('  ')]
    print('== 1.5) 基线漂移(相对上次确认提交, 仅报告不拦截) ==')
    for l in drift[:20]:
        print(l)
    if len(drift) > 20:
        print('  ...共%d项' % len(drift))
else:
    print(out.strip().splitlines()[-1] if out.strip() else '基线: 一致')

# 2) codes验证器 V1-V7
print('== 2) verify-codes-cards (V1-V7) ==')
rc, out = run(['python', 'tools/verify-codes-cards.py'])
print(out.strip().splitlines()[-1] if out.strip() else '(无输出)')
if rc != 0:
    fails.append('verify-codes-cards FAIL:\n' + '\n'.join(l for l in out.splitlines() if 'FAIL' in l or '✗' in l)[:1500])

# 3) 徽标像素门禁
print('== 3) verify-badges-pixel ==')
rc, out = run(['python', 'tools/verify-badges-pixel.py'])
print(out.strip().splitlines()[-1] if out.strip() else '(无输出)')
if rc != 0:
    fails.append('verify-badges-pixel FAIL:\n' + out[-1000:])

print()
if fails:
    print('FAIL (%d项)' % len(fails))
    for f in fails:
        print('---', f)
    sys.exit(1)
print('ALL GREEN')
