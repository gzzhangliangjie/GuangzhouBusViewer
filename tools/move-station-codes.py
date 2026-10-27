# -*- coding: utf-8 -*-
"""挪站后 codes 家具同步(永久工具): 站名 dx dy 成对传参, 同步 codes SVG 的
站名文字(+紧邻EN行)与编号牌组(填充rect等, 多牌站含环/白描, 含inner分隔线+双文字)。
用法: python tools/move-station-codes.py 站名1 dx1 dy1 [站名2 dx2 dy2 ...]
前提: 卡圆/CFG 已改好(站圆真源=单线卡/rebuild10 CFG); 本工具只同步 codes 侧家具。
写完必须跑: python tools/sync-base.py 并过 verify-all。"""
import io, os, sys, re, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location('gen', os.path.join(ROOT, 'tools', 'gen-codes-cards.py'))
gen = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(gen)

args = sys.argv[1:]
assert len(args) % 3 == 0, '用法: move-station-codes.py 站名 dx dy [...]'
MOVES = [(args[i], float(args[i+1]), float(args[i+2])) for i in range(0, len(args), 3)]

F = 'assets/lines/network-全网.codes.svg'
t = open(F, encoding='utf-8').read()

def shift_attrs(attrs, dx, dy):
    a = re.sub(r'\bx="([-\d.]+)"', lambda m: 'x="%.2f"' % (float(m.group(1))+dx), attrs)
    a = re.sub(r'\by="([-\d.]+)"', lambda m: 'y="%.2f"' % (float(m.group(1))+dy), a)
    return a

for nm, dx, dy in MOVES:
    # 1) 中文标签 + 紧邻EN行
    e = {x['nm']: x for x in gen.text_elements(t)}.get(nm)
    assert e, f'{nm}: codes 无文字'
    ens = [x for x in gen.text_elements(t) if x['en'] and abs(x['x']-e['x']) < 3 and 0 < x['y']-e['y'] < 16]
    t = t.replace(e['el'], '<text %s>%s</text>' % (shift_attrs(e['attrs'], dx, dy), nm), 1)
    for en in ens:
        t = t.replace(en['el'], '<text %s>%s</text>' % (shift_attrs(en['attrs'], dx, dy), en['nm']), 1)
    # 2) 编号牌组: 距旧圆位最近 chip(单线站1rect填充, 多牌站含环/白描共3rect) + inner
    m = re.search(r'<g id="编号牌"[^>]*>', t)
    g0 = m.end()
    g1 = g0 + re.search(r'</g>', t[g0:]).start()
    blk = t[g0:g1]
    # 旧圆位: 文字新位-位移 不能反推圆; 用 chip 新位反查会双重位移——
    # 因此本工具要求传参时先给"未位移前"会匹配到的 chip 现位: 由站名邻域找(距文字新位 <60 的最近chip)
    cand = sorted((math.dist((d['x']+d['w']/2, d['y']+d['h']/2), (e['x'], e['y'])), d)
                  for d in gen.chip_details(t))
    assert cand and cand[0][0] < 60, f'{nm}: 文字60px内无chip'
    d0 = cand[0][1]
    rx, ry = d0['x'], d0['y']
    # 多牌站(换乘): 该站全部chip = 最近chip 20px 邻域内全体
    mine = [d for d in gen.chip_details(t)
            if math.dist((d['x']+d['w']/2, d['y']+d['h']/2), (rx+d0['w']/2, ry+d0['h']/2)) <= 20]
    n_rect = 0
    out, pos = [], 0
    for rm in re.finditer(r'<rect\s([^>]*?)(/?>)', blk):
        at = rm.group(1)
        mx = re.search(r'\bx="([-\d.]+)"', at)
        my = re.search(r'\by="([-\d.]+)"', at)
        if mx and my and any(abs(float(mx.group(1))-d['x']) < 0.01 and abs(float(my.group(1))-d['y']) < 0.01
                             for d in mine):
            na = re.sub(r'\bx="([-\d.]+)"', lambda mo: 'x="%.2f"' % (float(mo.group(1))+dx), at)
            na = re.sub(r'\by="([-\d.]+)"', lambda mo: 'y="%.2f"' % (float(mo.group(1))+dy), na)
            out.append(blk[pos:rm.start()]); out.append('<rect '+na+rm.group(2))
            pos = rm.end(); n_rect += 1
    blk2 = ''.join(out) + blk[pos:]
    assert len(mine) <= n_rect <= 3*len(mine), f'{nm}: 牌rect={n_rect} vs chips={len(mine)} 异常'
    t = t[:g0] + blk2 + t[g1:]
    dd = [d for d in gen.chip_details(t)
          if any(abs(d['x']-(c['x']+dx)) < 0.01 and abs(d['y']-(c['y']+dy)) < 0.01 for c in mine)]
    assert len(dd) == len(mine), f'{nm}: 新位chip={len(dd)}/{len(mine)}'
    for d0b in dd:
        inner = d0b['inner']
        n_in = 0
        for em in list(re.finditer(r'<(line|text)\s[^>]*?>', inner)):
            seg = em.group(0)
            a = re.sub(r'\bx1="([-\d.]+)"', lambda mo: 'x1="%.2f"' % (float(mo.group(1))+dx), seg)
            a = re.sub(r'\bx2="([-\d.]+)"', lambda mo: 'x2="%.2f"' % (float(mo.group(1))+dx), a)
            a = re.sub(r'\by1="([-\d.]+)"', lambda mo: 'y1="%.2f"' % (float(mo.group(1))+dy), a)
            a = re.sub(r'\by2="([-\d.]+)"', lambda mo: 'y2="%.2f"' % (float(mo.group(1))+dy), a)
            a = re.sub(r'\bx="([-\d.]+)"', lambda mo: 'x="%.2f"' % (float(mo.group(1))+dx), a)
            a = re.sub(r'\by="([-\d.]+)"', lambda mo: 'y="%.2f"' % (float(mo.group(1))+dy), a)
            assert seg in inner
            inner = inner.replace(seg, a, 1)
            n_in += 1
        t = t.replace(d0b['inner'], inner, 1)
    print(f'{nm}: 文字+EN{len(ens)}, 牌{n_rect}rect+inner{n_in}, 位移({dx},{dy})')

open(F, 'w', encoding='utf-8').write(t)
print('OK -> 记得 sync-base + verify-all')
