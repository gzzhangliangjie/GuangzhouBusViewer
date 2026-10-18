# -*- coding: utf-8 -*-
"""1号线卡片站名<text>: 位置取原图字行位置(版式还原), 数据取结构化表"""
import re, json, math
import xml.etree.ElementTree as ET
from collections import defaultdict

NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)

known = json.load(open('data/_metro-known.json'))
en_of = {st['zh']: st.get('en', '') for st in known['stations']}
ANCH = json.load(open('data/svg2off-anchors.json'))
L1 = ['西塱','坑口','花地湾','芳村','黄沙','长寿路','陈家祠','西门口','公园前','农讲所',
      '烈士陵园','东山口','杨箕','体育西路','体育中心','广州东站']

# ---- 原图字形行提取 ----
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

glyphs = []
def walk(el, anc):
    if el.tag.endswith('}path'):
        cls = None
        for e in [el] + anc[::-1]:
            c = e.get('class')
            if c in CSS and CSS[c]:
                cls = CSS[c]
                break
            if e.get('stroke'):
                cls = 'inline'
                break
        if not cls:
            pts = sample_d(el.get('d', ''))
            if len(pts) >= 2:
                xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
                glyphs.append({'x0': min(xs), 'x1': max(xs), 'y0': min(ys), 'y1': max(ys),
                               'cx': (min(xs)+max(xs))/2, 'cy': (min(ys)+max(ys))/2,
                               'w': max(xs)-min(xs), 'h': max(ys)-min(ys)})
    for ch in el:
        walk(ch, anc + [el])
walk(oroot, [])

def is_zh(g):
    return 0.5 < g['w']/max(g['h'], .01) < 2.05 and 5.0 < g['h'] < 13.5

def is_en(g):
    return g['w']/max(g['h'], .01) < 0.95 and 1.5 < g['h'] < 9

pos = {a['name']: (a['sx'], a['sy']) for a in ANCH}
layout = {}
for nm in L1:
    ax, ay = pos[nm]
    zh = [g for g in glyphs if is_zh(g) and abs(g['cx']-ax) < 85 and abs(g['cy']-ay) < 60]
    bands = defaultdict(list)
    for g in zh:
        bands[round(g['cy']//9)].append(g)
    best = None
    for k, bl in bands.items():
        bl.sort(key=lambda g: g['cx'])
        cur = [bl[0]]
        for g in bl[1:]:
            if g['cx'] - cur[-1]['cx'] > 22:
                if len(cur) == len(nm):
                    row = cur
                    ry = sum(g['cy'] for g in row)/len(row)
                    d = abs(ry - ay) + abs((row[0]['cx']+row[-1]['cx'])/2 - ax)*0.5
                    if best is None or d < best[0]:
                        best = (d, row)
                cur = []
            cur.append(g)
        if len(cur) == len(nm):
            ry = sum(g['cy'] for g in cur)/len(cur)
            d = abs(ry - ay) + abs((cur[0]['cx']+cur[-1]['cx'])/2 - ax)*0.5
            if best is None or d < best[0]:
                best = (d, cur)
    if best is None:
        layout[nm] = {'zx': ax, 'zy': ay - 10, 'anc': 'middle', 'ex': ax, 'ey': ay + 18}
        continue
    row = best[1]
    rx0, rx1 = row[0]['x0'], row[-1]['x1']
    zy = sum(g['y1'] for g in row)/len(row)  # 基线近似=行底
    zx = (rx0 + rx1)/2
    # 英文行: zh行±30px内最近的拉丁行
    en = [g for g in glyphs if is_en(g) and rx0-20 < g['cx'] < rx1+20]
    enrows = defaultdict(list)
    for g in en:
        enrows[round(g['cy']//7)].append(g)
    enrow = None
    zrow_y = sum(g['cy'] for g in row)/len(row)
    for k in sorted(enrows, key=lambda k: abs(k*7 - zrow_y)):
        bl = enrows[k]
        if 2 <= len(bl) <= 40:
            enrow = bl
            break
    layout[nm] = {'zx': zx, 'zy': zy, 'anc': 'middle'}
    if enrow:
        ex0 = min(g['x0'] for g in enrow); ex1 = max(g['x1'] for g in enrow)
        ey = sum(g['y1'] for g in enrow)/len(enrow)
        layout[nm].update({'ex': (ex0+ex1)/2, 'ey': ey})
    else:
        layout[nm].update({'ex': zx, 'ey': zy + 14})
    print('%-5s zh@(%.0f,%.0f) en@(%s)' % (nm, zx, zy,
          '(%.0f,%.0f)' % (layout[nm]['ex'], layout[nm]['ey']) if enrow else '无->默认'))

# ---- 写入卡片 ----
# 修正拥挤带5站(实测原图字位: zh中心/zh基线, en中心/基线)
layout['农讲所'] = {'zx': 1392, 'zy': 998, 'anc': 'middle', 'ex': 1392, 'ey': 1005}
layout['烈士陵园'] = {'zx': 1442, 'zy': 1023, 'anc': 'middle', 'ex': 1442, 'ey': 1030}
layout['东山口'] = {'zx': 1473, 'zy': 990, 'anc': 'middle', 'ex': 1473, 'ey': 997}
layout['体育西路'] = {'zx': 1632, 'zy': 945, 'anc': 'middle', 'ex': 1632, 'ey': 952}
layout['体育中心'] = {'zx': 1738, 'zy': 898, 'anc': 'middle', 'ex': 1738, 'ey': 905}

# 四站贴圆(黄沙终点下方/坑口左侧/花地湾右侧/西门口下方), 距圆<=23px
layout['黄沙'] = {'zx': 1176, 'zy': 1082, 'anc': 'middle', 'ex': 1176, 'ey': 1090}
layout['坑口'] = {'zx': 1090, 'zy': 1239, 'anc': 'middle', 'ex': 1090, 'ey': 1247}
layout['花地湾'] = {'zx': 1135, 'zy': 1176, 'anc': 'middle', 'ex': 1137, 'ey': 1184}
layout['西门口'] = {'zx': 1282, 'zy': 1030, 'anc': 'middle', 'ex': 1282, 'ey': 1038}

card = ET.parse('assets/lines/line-1号线-17.svg')
root = card.getroot()
par = {}
def build(el):
    for ch in el:
        par[id(ch)] = el
        build(ch)
build(root)
for t in list(root.iter('{%s}text' % NS)):
    par[id(t)].remove(t)

g = ET.SubElement(root, '{%s}g' % NS)
g.set('id', '站名标注')
g.set('font-family', "'Microsoft YaHei', 'PingFang SC', sans-serif")
for nm in L1:
    L = layout[nm]
    zh_t = ET.SubElement(g, '{%s}text' % NS)
    zh_t.set('x', str(round(L['zx'], 1))); zh_t.set('y', str(round(L['zy'], 1)))
    zh_t.set('text-anchor', L.get('anc', 'middle'))
    zh_t.set('font-size', '10.5')
    zh_t.set('font-weight', '500')
    zh_t.set('fill', '#1a1a1a')
    zh_t.text = nm
    en = en_of.get(nm, '')
    if en:
        en_t = ET.SubElement(g, '{%s}text' % NS)
        en_t.set('x', str(round(L['ex'], 1))); en_t.set('y', str(round(L['ey'], 1)))
        en_t.set('text-anchor', 'middle')
        en_t.set('font-size', '5.5')
        en_t.set('fill', '#444444')
        en_t.text = en

card.write('assets/lines/line-1号线-17.svg', encoding='unicode', xml_declaration=False)
print('原图版式 <text> 写入完成')
