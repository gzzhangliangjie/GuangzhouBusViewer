# -*- coding: utf-8 -*-
"""锚表升级: fin.badges 纯字符串(文档序) -> [{'key':线号,'tr':translate串}] (key匹配);
同时更新 _repin/verify-badges-pixel/sync-base 的读写; 并设嘉禾望岗2号线徽标到文字上方。"""
import io, sys, re, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

p = 'data/codes-final-pins.json'
d = json.load(open(p, encoding='utf-8'))
t = open('assets/lines/network-全网.codes.svg', encoding='utf-8').read()

LNAMES = {'1号线','2号线','3号线','4号线','5号线','6号线','7号线','8号线','9号线','10号线',
          '11号线','12号线','13号线','14号线','18号线','21号线','22号线','广佛线','APM线'}
K2L = {'GF': '广佛线', 'APM': 'APM线'}

# 从当前SVG提取(顺序即文档序, 与现有fin.badges一一对应)
cur = []
for mm in re.finditer(r'<g data-badge="header" transform="translate\([-\d.]+ ([-\d.]+)\) scale\(([\d.]+)\)"[^>]*>(.*?)</g>', t, re.S):
    ts = re.findall(r'>([^<>]+)</text>', mm.group(3))
    key = ts[0].strip() if ts else '?'
    ln = key if key in LNAMES else (K2L.get(key) or (key + '号线' if key.isdigit() else '?'))
    tr = re.search(r'translate\(([-\d.]+) ([-\d.]+)\)', mm.group(0))
    cur.append({'key': ln, 'tr': 'translate(%s %s)' % (tr.group(1), tr.group(2)),
                'x': float(tr.group(1)), 'y': float(tr.group(2))})
assert len(cur) == len(d['badges']), 'SVG徽标数与锚表不一致: %d vs %d' % (len(cur), len(d['badges']))

# 嘉禾望岗2号线: 文字(1519.44,563.54)上方 -> translate(1506.88 544.24)
target = 'translate(1506.88 544.24)'
for c in cur:
    if c['key'] == '2号线' and c['y'] < 700:
        c['tr'] = target
        print('2号线嘉禾望岗徽标 ->', target)

d['badges'] = [{'key': c['key'], 'tr': c['tr']} for c in cur]
json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('锚表升级为key格式:', len(d['badges']), '条')

# 更新 _repin.tmp.py: 输出key格式
s = open('data/_repin.tmp.py', encoding='utf-8').read()
old = """trs = ['translate(%s)' % m.group(1) for m in re.finditer(r'<g data-badge="header" transform="translate\\(([-\\d.]+) ([-\\d.]+)\\)', t)]
assert len(trs) == 41, len(trs)"""
if old not in s:
    old = None
print('repin脚本待重写(下一步)')
