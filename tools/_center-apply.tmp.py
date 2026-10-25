# -*- coding: utf-8 -*-
"""批量应用居中修正(清单 data/_label-center-viol.json):
每站替换文字元素 y=基线(盒顶+0.92fs), 逐站应用后基于最新布局重查合法性(防连锁碰撞);
不合法者保留原位上报。"""
import io, sys, re, json, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'tools')
import importlib.util
spec = importlib.util.spec_from_file_location('gen', 'tools/gen-codes-cards.py')
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

viol = json.load(open('data/_label-center-viol.json', encoding='utf-8'))
p = 'data/codes-final-pins.json'
d = json.load(open(p, encoding='utf-8'))
li = d['labels_inner']

applied, kept = 0, []
for v in viol:
    nm, cand, fs = v['nm'], v['cand'], v['fs']
    # 当前布局下重查合法性(前面应用可能改变邻域)
    cur_boxes = []
    for mm in re.finditer(r'<text ([^>]*)>([^<]+)</text>', li):
        at2, nm2 = mm.group(1), mm.group(2)
        mx = re.search(r'x="([-\d.]+)"', at2)
        my = re.search(r'y="([-\d.]+)"', at2)
        mfs = re.search(r'font-size="([\d.]+)"', at2)
        if not (mx and my and mfs):
            continue
        x2, y2, f2 = float(mx.group(1)), float(my.group(1)), float(mfs.group(1))
        cur_boxes.append((gen.text_box({'x': x2, 'y': y2, 'fs': f2, 'content': nm2}), nm2))
    mm = re.search(r'<text x="[-\d.]+" y="[-\d.]+"([^>]*)>' + re.escape(nm) + r'</text>', li)
    if not mm:
        kept.append((nm, '锚表未命中'))
        continue
    old_el = mm.group(0)
    old_x = float(re.search(r'x="([-\d.]+)"', old_el).group(1))
    old_y = float(re.search(r'y="([-\d.]+)"', old_el).group(1))
    baseline = cand[1] + fs * 0.92
    new_el = '<text x="%.2f" y="%.2f"%s>%s</text>' % (cand[0] + cand[2] / 2, baseline, mm.group(1), nm)
    trial = li.replace(old_el, new_el)
    # 合法性: 与其他文字盒净距>=1(基于trial布局)
    ok = True
    nbx = (cand[0], baseline - fs * 0.92, cand[2], fs * 1.12)
    for b2, nm2 in cur_boxes:
        if nm2 == nm:
            continue
        if gen._gap(nbx, b2) < 1.0:
            ok = False
            break
    if not ok:
        kept.append((nm, '吸附后与他文字<1'))
        continue
    li = trial
    applied += 1
d['labels_inner'] = li
json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('居中修正应用:', applied, ' 保留:', kept)
