# -*- coding: utf-8 -*-
"""全量验证链: 提交前必跑(pre-commit钩子强制), 不允许按改动范围挑门禁。
链路: 重跑两生成器+sync -> 幂等md5 -> verify-codes-cards(V1-V7) -> verify-badges-pixel
     -> 文字/胶囊重叠审计(V5已含, 此处对底图再全量复核)。
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
