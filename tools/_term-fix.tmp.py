# -*- coding: utf-8 -*-
"""集中处理22项违规(清单 data/_term-violations.json):
文字: 吸附到站钉交叉轴居中(理想位已预验合法)
徽标: 归位理想位(贴文字5pt交叉居中, transform写回fin.badges按键匹配)
顺序: 先全部文字(改变文字盒), 再按新文字盒重算徽标理想位(文字动了徽标跟着),
      每枚合法性终验, 不合法保留原位并上报。
"""
import io, sys, re, json, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'tools')
import importlib.util
spec = importlib.util.spec_from_file_location('gen', 'tools/gen-codes-cards.py')
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

viol = json.load(open('data/_term-violations.json', encoding='utf-8'))
p = 'data/codes-final-pins.json'
d = json.load(open(p, encoding='utf-8'))
li = d['labels_inner']

# ---- 阶段A: 文字居中(逐项替换labels_inner) ----
t_done = 0
for v in viol:
    if not v.get('text_cand'):
        continue
    nm = v['nm']
    tcand = v['text_cand']  # [x, y, w, h] 盒
    fs = 7.5
    baseline = tcand[1] + fs * 0.92
    pat = re.compile(r'<text x="[-\d.]+" y="[-\d.]+"([^>]*)>' + re.escape(nm) + r'</text>')
    mm = pat.search(li)
    assert mm, 'labels_inner缺 ' + nm
    li = li[:mm.start()] + '<text x="%.2f" y="%.2f"%s>%s</text>' % (tcand[0] + tcand[2] / 2, baseline, mm.group(1), nm) + li[mm.end():]
    t_done += 1
d['labels_inner'] = li
json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('文字居中应用:', t_done)

# ---- 阶段B: 重建后按新文字盒重算徽标理想位并写fin.badges ----
t = open('assets/lines/network-全网.codes.svg', encoding='utf-8').read()
corridors = [tuple(float(m.group(k)) for k in (1, 2, 3, 4))
             for m in re.finditer(r'<line x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)"', t)]
chips, rings = [], []
m = re.search(r'<g id="编号牌"[^>]*>(.*?)</g>', t, re.S)
for r in re.finditer(r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)"([^>]*)stroke="(#[0-9A-Fa-f]{6})"', m.group(1)):
    x, y, w, h = (float(r.group(k)) for k in (1, 2, 3, 4))
    (rings if 'data-ring' in r.group(5) else chips).append((x, y, w, h))
# 徽标(codes SVG当前=旧位; 逐键替换transform)
badge_els = []
for mm in re.finditer(r'<g data-badge="header" transform="([^"]+)"[^>]*>(.*?)</g>', t, re.S):
    ts = re.findall(r'>([^<>]+)</text>', mm.group(2))
    badge_els.append((mm.group(1), ts[0].strip() if ts else '?'))
# 新文字盒
texts = {}
for mm in re.finditer(r'<text ([^>]*)>([^<]+)</text>', d['labels_inner']):
    at, nm = mm.group(1), mm.group(2)
    if nm.isascii():
        continue
    x = float(re.search(r'x="([-\d.]+)"', at).group(1))
    y = float(re.search(r'y="([-\d.]+)"', at).group(1))
    fs = float(re.search(r'font-size="([\d.]+)"', at).group(1))
    texts[nm] = {'x': x, 'y': y, 'fs': fs, 'box': gen.text_box({'x': x, 'y': y, 'fs': fs, 'content': nm})}

others = [o['box'] for o in texts.values()]

def legal_box(box, self_tr):
    if any(gen._gap(box, c) < 0.5 for c in chips + rings):
        return False
    if any(gen.rect_seg_dist(box, s) < 4.5 for s in corridors):
        return False
    if any(gen._gap(box, o) < 1.0 for o in others):
        return False
    for tr, key in badge_els:
        if tr == self_tr:
            continue
        mm2 = re.match(r'translate\(([-\d.]+) ([-\d.]+)\) scale\(([\d.]+)\)', tr)
        if not mm2:
            continue
        bx, by, sc = float(mm2.group(1)), float(mm2.group(2)), float(mm2.group(3))
        if gen._gap(box, (bx, by, 80 * sc, 43 * sc)) < 0.3:
            return False
    return True

# 键: 徽标transform串 -> (线名->文字站名)
tr2stn = {}
for v in viol:
    tr2stn[v['badge_tr']] = v['nm']

new_trs = {}
skip = []
# 重读最新清单(文字居中后徽标理想位已随新文字盒更新)
viol = json.load(open('data/_term-violations.json', encoding='utf-8'))
tr2stn = {}
for v in viol:
    if v.get('badge_cand'):
        tr2stn[v['badge_tr']] = (v['nm'], v['badge_cand'])
for tr, key in badge_els:
    if tr not in tr2stn:
        continue
    nm, cand = tr2stn[tr]
    mm2 = re.match(r'translate\(([-\d.]+) ([-\d.]+)\) scale\(([\d.]+)\)', tr)
    sc = float(mm2.group(3))
    cbox = (cand[0] - 80 * sc / 2, cand[1] - 43 * sc / 2, 80 * sc, 43 * sc)
    if legal_box(cbox, tr):
        new_trs[tr] = 'translate(%.2f %.2f) scale(%.4f)' % (cand[0], cand[1], sc)
        print('徽标 %-4s %-8s -> (%g,%g)' % (key, nm, cand[0], cand[1]))
    else:
        skip.append((key, nm, '理想位不合法(保留原位)'))

# 写三处: codes SVG / 底图 / fin.badges
for f in ('assets/lines/network-全网.codes.svg', 'assets/lines/network-全网.svg'):
    s = open(f, encoding='utf-8').read()
    for o, n in new_trs.items():
        assert o in s, f + ' ' + o
        s = s.replace(o, n)
    open(f, 'w', encoding='utf-8').write(s)
d['badges'] = [new_trs.get(x, x) for x in d['badges']]
json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('徽标归位:', len(new_trs), ' 保留:', skip)
