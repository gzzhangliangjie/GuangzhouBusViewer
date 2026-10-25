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
