# -*- coding: utf-8 -*-
"""基线锁: 防止已验收状态被回退/静默改坏(用户指令: 通过完善关联机制杜绝退缩行为)。
accept  = 快照当前已验证状态为验收基线(仅在你明确认可"对了"时执行)
check   = 当前态 vs 验收基线, 任何元件(文字坐标/徽标坐标/产物md5)不一致即报REGRESSION
被check拦下的改动, 只有两种出路: 撤回本次改动, 或用户明确认可新状态后重新accept。
用法: python tools/baseline-lock.py accept|check
"""
import io, os, re, sys, json, hashlib
if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location('gen', os.path.join(ROOT, 'tools', 'gen-codes-cards.py'))
gen = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(gen)
BASE = 'data/_accepted-baseline.json'
CODES = 'assets/lines/network-全网.codes.svg'
KEY_FILES = ['assets/lines/network-全网.svg', 'assets/lines/network-全网.codes.svg']


def md5(p):
    return hashlib.md5(open(p, 'rb').read()).hexdigest()


def snapshot():
    labels = {}
    _csvg = open(CODES, encoding='utf-8').read()
    _clm = re.search(r'<g id="站名标注"[^>]*>(.*?)</g>', _csvg, re.S)
    if _clm:
        for mm in re.finditer(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*>([^<]+)</text>', _clm.group(1)):
            labels[mm.group(3)] = [float(mm.group(1)), float(mm.group(2))]
    badges = []
    t = open(CODES, encoding='utf-8').read()
    for e in gen.badge_elements(t):
        badges.append([e['key'], e['x'], e['y'], e['scale']])
    return {'labels': labels, 'badges': badges,
            'md5': {f: md5(f) for f in KEY_FILES}}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    if cmd == 'accept':
        snap = snapshot()
        json.dump(snap, open(BASE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('验收基线已锁定: 文字%d站 徽标%d枚' % (len(snap['labels']), len(snap['badges'])))
        return
    if not os.path.exists(BASE):
        print('无验收基线(首次运行), 跳过回归检查')
        return
    base = json.load(open(BASE, encoding='utf-8'))
    cur = snapshot()
    regs = []
    for nm, pos in base['labels'].items():
        if nm not in cur['labels']:
            regs.append('文字 %s 从锚表消失' % nm)
        elif cur['labels'][nm] != pos:
            regs.append('文字 %s 移位: %s -> %s' % (nm, pos, cur['labels'][nm]))
    for nm in cur['labels']:
        if nm not in base['labels']:
            regs.append('文字 %s 新出现' % nm)
    for i, b in enumerate(base['badges']):
        if i >= len(cur['badges']):
            regs.append('徽标 %s 消失' % b[0])
            continue
        if cur['badges'][i][:2] != b[:2]:
            regs.append('徽标 %s 移位: (%g,%g) -> (%g,%g)' % (b[0], b[1], b[2], cur['badges'][i][1], cur['badges'][i][2]))
        elif cur['badges'][i][3] != b[3]:
            regs.append('徽标 %s 缩放变化: %s -> %s' % (b[0], b[3], cur['badges'][i][3]))
    if len(cur['badges']) > len(base['badges']):
        for b in cur['badges'][len(base['badges']):]:
            regs.append('徽标 %s 新出现' % b[0])
    for f in KEY_FILES:
        if md5(f) != base['md5'].get(f):
            regs.append('产物变更: %s' % f)
    if regs:
        print('REGRESSION %d 项(相对验收基线, 未经accept确认的改动):' % len(regs))
        for r in regs[:40]:
            print('  ' + r)
        if len(regs) > 40:
            print('  ...共%d项' % len(regs))
        sys.exit(1)
    print('基线锁: 与验收态一致, 0回归')


if __name__ == '__main__':
    main()
