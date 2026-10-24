# -*- coding: utf-8 -*-
"""执行36枚徽标归一化(广州南站=离群站排除): 按 _badge-norm-moves.tmp.json 清单,
写 codes/底图/锚表 三处 transform。"""
import io, sys, re, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

moves = json.load(open('data/_badge-norm-moves.tmp.json', encoding='utf-8'))
moves = [mv for mv in moves if mv['nm'] != '广州南站']
print('执行归一化:', len(moves), '枚(已排除广州南站)')

p = 'data/codes-final-pins.json'
d = json.load(open(p, encoding='utf-8'))

# 构建 old translate串 -> new translate串 (按徽标key+近似位置匹配)
t = open('assets/lines/network-全网.codes.svg', encoding='utf-8').read()
repl = []
for mv in moves:
    key = mv['key']
    # 在SVG中找该key的徽标transform(取与old距离最近的)
    best = None
    for mm in re.finditer(r'<g data-badge="header" transform="translate\([-\d.]+ ([-\d.]+)\) scale\(([\d.]+)\)"[^>]*>(.*?)</g>', t):
        ts = re.findall(r'>([^<>]+)</text>', mm.group(3))
        k2 = ts[0].strip() if ts else '?'
        if k2 != key:
            continue
        tr = re.search(r'translate\(([-\d.]+) ([-\d.]+)\)', mm.group(0))
        bx, by = float(tr.group(1)), float(tr.group(2))
        dd = (bx - mv['old'][0]) ** 2 + (by - mv['old'][1]) ** 2
        if best is None or dd < best[0]:
            best = (dd, mm.group(0), 'translate(%.2f %.2f) scale(%s)' % (mv['new'][0], mv['new'][1], mm.group(2)))
    assert best, key
    repl.append((best[1], best[2], key, mv['nm']))

for f in ('assets/lines/network-全网.codes.svg', 'assets/lines/network-全网.svg'):
    s = open(f, encoding='utf-8').read()
    for o, n, key, nm in repl:
        assert o in s, f + ' ' + key + nm
        s = s.replace(o, n)
    open(f, 'w', encoding='utf-8').write(s)
d['badges'] = [next((n for o, n, k2, nm in repl if o == x), x) for x in d['badges']]
json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('三处同步完成')
