# -*- coding: utf-8 -*-
"""1号线卡片文字终修: 原图中最近锚站属于1号线16站的字形, 整体替换卡片文字
规则(唯一): glyph -> 最近锚站(47选1); 属于本线站且距锚<=75px -> 保留
"""
import re, math, json, copy
import xml.etree.ElementTree as ET

NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)
L1 = ['西塱','坑口','花地湾','芳村','黄沙','长寿路','陈家祠','西门口','公园前','农讲所',
      '烈士陵园','东山口','杨箕','体育西路','体育中心','广州东站']
ANCH = {p['name']: (p['sx'], p['sy']) for p in json.load(open('data/svg2off-anchors.json'))}
L1SET = set(L1)

orig = ET.parse('assets/gz-tim-2026.svg')
oroot = orig.getroot()
CSS = {}
for st in oroot.iter('{%s}style' % NS):
    for m in re.finditer(r'\.([\w-]+)\{([^}]*)\}', st.text or ''):
        sm = re.search(r'stroke:\s*(#[0-9A-Fa-f]{3,6})', m.group(2))
        CSS[m.group(1)] = sm.group(1) if sm else None

def sample_d(d):
    pts = []
    cur = [0.0, 0.0]
    for cmd, body in re.findall(r'([MmLlHhVvCc])([^MmLlHhVvCc]*)', d or ''):
        nums = [float(v) for v in re.findall(r'-?\d+\.?\d*', body)]
        rel = cmd.islower()
        c = cmd.upper()
        i = 0
        while i < len(nums):
            if c in 'ML':
                p = nums[i:i+2]; i += 2
                cur = [p[0]+(cur[0] if rel else 0), p[1]+(cur[1] if rel else 0)]
                pts.append(tuple(cur))
            elif c == 'H':
                cur[0] = nums[i]+(cur[0] if rel else 0); i += 1; pts.append(tuple(cur))
            elif c == 'V':
                cur[1] = nums[i]+(cur[1] if rel else 0); i += 1; pts.append(tuple(cur))
            elif c == 'C':
                p = nums[i+4:i+6]; i += 6
                if len(p) == 2:
                    cur = [p[0]+(cur[0] if rel else 0), p[1]+(cur[1] if rel else 0)]
                    pts.append(tuple(cur))
            else:
                i = len(nums)
    return pts

def has_stroke(el, anc):
    for e in [el] + anc[::-1]:
        c = e.get('class')
        if c in CSS and CSS[c]:
            return True
        if e.get('stroke'):
            return True
    return False

items = []
def walk(el, anc):
    tag = el.tag.split('}')[-1]
    if tag == 'path':
        items.append({'el': el, 'anc': list(anc)})
    for ch in el:
        walk(ch, anc + [el])
walk(oroot, [])

kept = []
stats = {nm: {'zh': 0, 'en': 0} for nm in L1}
for it in items:
    if has_stroke(it['el'], it['anc']):
        continue
    pts = sample_d(it['el'].get('d', ''))
    if len(pts) < 2:
        continue
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    w, h = max(xs)-min(xs), max(ys)-min(ys)
    cx, cy = (min(xs)+max(xs))/2, (min(ys)+max(ys))/2
    dists = [(math.hypot(cx-pos[0], cy-pos[1]), nm2) for nm2, pos in ANCH.items()]
    dists.sort()
    d1, n1 = dists[0]
    # 最近锚属本线: 直接收; 否则若本线站距离<=1.3倍最近距离(密集区长名延伸)也收
    take = None
    if n1 in L1SET and d1 <= 75:
        take = n1
    else:
        for d2, n2 in dists:
            if n2 in L1SET and d2 <= d1 * 1.3 and d2 <= 110:
                take = n2
                break
    bn = take
    if bn is not None:
        kept.append(it)
        if 0.5 < w/max(h, .01) < 2.05 and 5.0 < h < 13.5:
            stats[bn]['zh'] += 1
        elif w/max(h, .01) < 0.95 and 1.5 < h < 9:
            stats[bn]['en'] += 1

print('归属1号线的字形: %d' % len(kept))
for nm in L1:
    print('%-5s zh%-3d en%-3d' % (nm, stats[nm]['zh'], stats[nm]['en']))

# 替换卡片文字: 删旧path(无stroke类的), 插新
card = ET.parse('assets/lines/line-1号线-17.svg')
croot = card.getroot()
par = {}
def build(el):
    for ch in el:
        par[id(ch)] = el
        build(ch)
build(croot)
removed = 0
for p in list(croot.iter('{%s}path' % NS)):
    if not has_stroke(p, []):
        par[id(p)].remove(p)
        removed += 1
def copy_it(it):
    chain = []
    for a in it['anc']:
        if a is oroot:
            continue
        g = ET.Element('{%s}g' % NS)
        for k, v in a.attrib.items():
            if '{' in k or k == 'transform':
                continue
            g.set(k, v)
        chain.append(g)
    node = copy.deepcopy(it['el'])
    for g in reversed(chain):
        g.append(node)
        node = g
    return node
for it in kept:
    croot.append(copy_it(it))
card.write('assets/lines/line-1号线-17.svg', encoding='unicode', xml_declaration=False)
print('删除旧文字%d, 插入新文字%d' % (removed, len(kept)))
