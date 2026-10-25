# -*- coding: utf-8 -*-
"""两份SVG产物字节级快照/还原(2026-10-25 用户: checkout坑爹, 存一版中间文件)。
git checkout禁用于SVG还原: autocrlf改写换行致md5漂移(基线假告警)+会回退未提交工作。
还原优先级: ①生成器链(build→gen→gen→sync, 形态真源, 幂等) ②本工具快照(试错回滚/
生成器自身被改坏的场合)。字节级shutil.copyfile+md5双端校验, 无EOL翻译。
  save [标签]    快照两份SVG到 data/_svg-snapshot/(单槽覆盖, 带md5清单)
  restore        字节级还原 + md5校验(还原后建议跑 verify-all --quick)
  status         当前态 vs 快照 对比
用法: python tools/svg-snapshot.py save|restore|status [标签]
"""
import io, os, sys, json, hashlib, shutil, datetime
if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
FILES = ['assets/lines/network-全网.svg', 'assets/lines/network-全网.codes.svg']
SLOT = os.path.join(ROOT, 'data', '_svg-snapshot')
MAN = os.path.join(SLOT, '_manifest.json')


def md5(p):
    return hashlib.md5(open(p, 'rb').read()).hexdigest()


def save(label=''):
    os.makedirs(SLOT, exist_ok=True)
    man = {'time': datetime.datetime.now().strftime('%m-%d %H:%M:%S'),
           'label': label, 'md5': {}}
    for f in FILES:
        shutil.copyfile(f, os.path.join(SLOT, os.path.basename(f)))
        man['md5'][f] = md5(f)
    json.dump(man, open(MAN, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('快照已存 %s [%s]: %s' % (man['time'], label,
          ' '.join(man['md5'][f][:8] for f in FILES)))
    return man


def load_man():
    if not os.path.exists(MAN):
        raise SystemExit('尚无快照(data/_svg-snapshot/), 先 save')
    return json.load(open(MAN, encoding='utf-8'))


def restore():
    man = load_man()
    for f in FILES:
        src = os.path.join(SLOT, os.path.basename(f))
        if not os.path.exists(src) or md5(src) != man['md5'].get(f):
            raise SystemExit('快照自身md5不符(损坏或不完整), 拒绝还原: %s' % f)
    for f in FILES:
        shutil.copyfile(os.path.join(SLOT, os.path.basename(f)), f)
        if md5(f) != man['md5'][f]:
            raise SystemExit('还原后md5不符: %s' % f)
    print('已字节级还原 %s [%s]: %s' % (man['time'], man.get('label', ''),
          ' '.join(man['md5'][f][:8] for f in FILES)))
    print('下一步: python tools/verify-all.py --quick (基线漂移将如实报告)')
    return man


def status():
    man = load_man()
    for f in FILES:
        cur = md5(f) if os.path.exists(f) else '缺失'
        tag = '一致' if cur == man['md5'][f] else '不同(当前=%s)' % str(cur)[:8]
        print('  %s: 快照%s, %s' % (f, man['md5'][f][:8], tag))
    print('快照时间 %s [%s]' % (man['time'], man.get('label', '')))


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    label = sys.argv[2] if len(sys.argv) > 2 else ''
    if cmd == 'save':
        save(label)
    elif cmd == 'restore':
        restore()
    elif cmd == 'status':
        status()
    else:
        raise SystemExit(__doc__)
