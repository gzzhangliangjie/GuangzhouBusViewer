# -*- coding: utf-8 -*-
# 从 Electron localStorage leveldb 提取 gzbus.index.v1（UTF-16LE）缓存索引
import glob, json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

raw = b''
for f in glob.glob(r'C:\Users\zlj10\AppData\Roaming\Electron\Local Storage\leveldb\*'):
    try:
        raw += open(f, 'rb').read()
    except Exception:
        pass

i = raw.find(b'gzbus.index.v1')
j = raw.find(b'{\x00', i)
even = raw[j:] if len(raw[j:]) % 2 == 0 else raw[j:-1]
s = even.decode('utf-16-le', 'ignore')

depth = 0
end = None
instr = False
esc = False
for k, ch in enumerate(s):
    if esc:
        esc = False
        continue
    if ch == chr(92):
        esc = True
        continue
    if ch == '"':
        instr = not instr
        continue
    if instr:
        continue
    if ch == '{':
        depth += 1
    elif ch == '}':
        depth -= 1
        if depth == 0:
            end = k + 1
            break

txt = s[:end]
d = json.loads(txt)
open(r'E:\GuangzhouBusViewer\assets\_cache-index.json', 'w', encoding='utf-8').write(txt)
els = d['data']
print('cached at:', d['at'], '-> lines:', len(els))
print('sample:', json.dumps(els[0], ensure_ascii=False)[:180])
refs = [e['ref'] for e in els]
print('refs:', refs[:12])
