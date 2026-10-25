# -*- coding: utf-8 -*-
"""pre-commit 分级门禁(2026-10-25 用户: 纯文档/纯脚本提交不必跑全量verify-all):
按staged文件的最强影响分级:
  T1 纯文档(*.md, docs/)                    -> 放行(产物不受影响)
  T2 产物/数据(assets/**, data/*.json)      -> verify-all --quick 全量 + accept基线入库
     生成器链(build-network/gen-codes-cards/sync-base)在列时升级为非quick全量
     (重跑链+幂等; 重跑后worktree产物与staged不一致=生成器输出已变未随提交 -> 拒绝)
  T3 其他(tools脚本/js/html等, 不喂生成器)  -> XML+基线快检(秒级, 基线漂移仅提示)
用法: .git/hooks/pre-commit 调用; 可手动 python tools/precommit-gate.py 演练。
"""
import io, os, sys, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r.returncode, (r.stdout or '') + (r.stderr or '')

staged = [l for l in run(['git', 'diff', '--cached', '--name-only'])[1].splitlines() if l.strip()]
if not staged:
    print('无staged文件, 放行')
    sys.exit(0)

def is_doc(f):
    return f.endswith('.md') or f.startswith('docs/')

CHAIN = ('tools/build-network.py', 'tools/gen-codes-cards.py', 'tools/sync-base.py')

def is_chain(f):
    return f in CHAIN

def is_art(f):
    return f.startswith('assets/') or (f.startswith('data/') and f.endswith('.json'))

# ---- T1 纯文档 ----
if all(is_doc(f) for f in staged):
    print('T1 纯文档提交(%d个文件), 产物不受影响, 跳过验证链' % len(staged))
    sys.exit(0)

# ---- T2 产物/数据/生成器链 ----
if any(is_chain(f) or is_art(f) for f in staged):
    has_chain = any(is_chain(f) for f in staged)
    if has_chain:
        print('T2 生成器链变更: 工具自测 + verify-all 全量(重跑链+幂等) ...')
        rcs, outs = run(['python', 'tools/selftest.py'])
        print((outs.strip().splitlines() or [''])[-1])
        if rcs != 0:
            print(outs[-1500:])
            sys.exit(1)
        rc, out = run(['python', 'tools/verify-all.py'])
    else:
        print('T2 产物/数据变更: verify-all --quick ...')
        rc, out = run(['python', 'tools/verify-all.py', '--quick'])
    print((out.strip().splitlines() or [''])[-1])
    if rc != 0:
        print(out[-2000:])
        sys.exit(1)
    if has_chain:
        drift = [l for l in run(['git', 'diff', '--name-only'])[1].splitlines()
                 if l.startswith('assets/lines/')]
        if drift:
            print('FAIL: 生成器重跑输出与staged产物不一致(%s) —— 把再生成产物 git add 后重新提交'
                  % '、'.join(drift))
            sys.exit(1)
    rc2, out2 = run(['python', 'tools/baseline-lock.py', 'accept'])
    if rc2 != 0:
        print(out2)
        sys.exit(1)
    print(out2.strip())
    rc3, _ = run(['git', 'add', 'data/_accepted-baseline.json'])
    print('提交自检(用户令): 三文档——selftest金丝数字/AGENTS.md条文/docs规范 是否已随本批核对?')
    sys.exit(rc3)

# ---- T3 纯脚本 ----
print('T3 纯脚本提交(%d个文件): 工具自测 + XML/基线快检' % len(staged))
rcs, outs = run(['python', 'tools/selftest.py'])
print((outs.strip().splitlines() or [''])[-1])
if rcs != 0:
    print(outs[-1500:])
    sys.exit(1)
import xml.etree.ElementTree as ET
for f in ('assets/lines/network-全网.svg', 'assets/lines/network-全网.codes.svg'):
    try:
        ET.parse(f)
    except ET.ParseError as e:
        print('FAIL XML %s: %s' % (f, e))
        sys.exit(1)
rc, out = run(['python', 'tools/baseline-lock.py', 'check'])
print(out.strip().splitlines()[-1] if out.strip() else '')
if rc != 0:
    print('(基线漂移如上; 本提交不含产物, 提交产物时将走T2全量)')
print('T3 快检通过')
sys.exit(0)
