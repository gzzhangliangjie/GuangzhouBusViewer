# -*- coding: utf-8 -*-
"""把 Tim 广佛地铁矢量图按线路拆分: 每条线一个SVG
元素按有效描边色(含祖先g继承)归类; 站圆按 fill/stroke 归类;
色->线名 用 data/_line-colors.json 就近匹配。
输出: assets/lines/<ref>.svg + index
"""
import json
import os
import re
import colorsys
import xml.etree.ElementTree as ET

NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)
SVG = 'assets/gz-tim-2026.svg'
OUT = 'assets/lines'
os.makedirs(OUT, exist_ok=True)

tree = ET.parse(SVG)
root = tree.getroot()

# CSS class -> (stroke, fill)
CSS = {}
for st in root.iter('{%s}style' % NS):
    body = st.text or ''
    for m in re.finditer(r'\.([\w-]+)\{([^}]*)\}', body):
        cls, body2 = m.group(1), m.group(2)
        sm = re.search(r'stroke:\s*(#[0-9A-Fa-f]{3,6}|rgb\([^)]+\))', body2)
        fm = re.search(r'fill:\s*(#[0-9A-Fa-f]{3,6}|rgb\([^)]+\))', body2)
        CSS[cls] = (sm.group(1) if sm else None, fm.group(1) if fm else None)
print('CSS类:', len(CSS), ' 有stroke的:', sum(1 for v in CSS.values() if v[0]))

def eff_color(el, ancestors):
    """class(CSS) 或直接属性 -> (stroke或fill名, 色值)"""
    for e in [el] + ancestors[::-1]:
        c = e.get('class')
        if c and c in CSS:
            s, f = CSS[c]
            if s:
                return 'stroke', s
        v = e.get('stroke')
        if v and v != 'none' and not v.startswith('url'):
            return 'stroke', v
    for e in [el] + ancestors[::-1]:
        c = e.get('class')
        if c and c in CSS:
            s, f = CSS[c]
            if f:
                return 'fill', f
        v = e.get('fill')
        if v and v != 'none' and not v.startswith('url'):
            return 'fill', v
    return None, None

# 遍历, 收集 (元素, 祖先链, 色)
items = []
def walk(el, anc):
    tag = el.tag.split('}')[-1]
    if tag in ('path', 'circle', 'rect', 'line', 'ellipse'):
        attr, col = eff_color(el, anc)
        items.append({'el': el, 'anc': list(anc), 'attr': attr, 'col': col})
    for ch in el:
        walk(ch, anc + [el])
walk(root, [])
print('图形元素:', len(items))

def norm_col(c):
    c = c.strip()
    if c.startswith('#'):
        if len(c) == 4:
            c = '#' + ''.join(ch*2 for ch in c[1:])
        return tuple(int(c[i:i+2], 16) for i in (1, 3, 5))
    m = re.match(r'rgb\((\d+)[, ]+(\d+)[, ]+(\d+)\)', c)
    if m:
        return tuple(int(v) for v in m.groups())
    return None

# 聚类颜色(带符号, 纯白/纯黑/灰除外)
groups = {}
for it in items:
    if it['col'] is None:
        continue
    rgb = norm_col(it['col'])
    if rgb is None:
        continue
    mx, mn = max(rgb), min(rgb)
    if mx > 245 and mn > 245:   # 白
        continue
    if mx < 60:                 # 黑/深灰
        continue
    if mx - mn < 40:            # 灰
        continue
    groups.setdefault(rgb, []).append(it)
# 近似色合并
keys = sorted(groups, key=lambda k: -len(groups[k]))
merged = []
for k in keys:
    placed = False
    for m in merged:
        if max(abs(k[i]-m['rgb'][i]) for i in range(3)) <= 18:
            m['items'] += groups[k]
            placed = True
            break
    if not placed:
        merged.append({'rgb': k, 'items': list(groups[k])})
merged.sort(key=lambda m: -len(m['items']))
print('彩色类:', len(merged))
for m in merged[:25]:
    print('  ', m['rgb'], len(m['items']))

# 线色表
linecolors = json.load(open('data/_line-colors.json'))
def nearest_line(rgb):
    name, bd = None, 1e18
    for lc in linecolors:
        h = lc['color'].lstrip('#')
        c = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
        d = sum((a-b)**2 for a, b in zip(c, rgb)) ** .5
        if d < bd:
            bd, name = d, lc['zh']
    return name, bd

def copy_with_ancestors(el, anc):
    """复制元素, 外包必要的祖先g(保留transform/公共attr)"""
    chain = []
    for a in anc:
        if a is root:
            continue
        g = ET.Element('{%s}g' % NS)
        for k, v in a.attrib.items():
            if k.startswith('{http://www.w3.org/XML/1998/namespace}'):
                continue
            if k in ('id', 'class', 'stroke', 'fill', 'style'):
                continue
            g.set(k, v)
        chain.append(g)
    node = el
    import copy
    node = copy.deepcopy(el)
    for g in reversed(chain):
        g.append(node)
        node = g
    return node

VB = root.get('viewBox') or '0 0 2848.5 2054.25'
manifest = []
for mi, m in enumerate(merged):
    if len(m['items']) < 6 or len(m['items']) > 400:   # 过大=水体/底图结构
        continue
    name, dist = nearest_line(m['rgb'])
    ref = re.sub(r'\s+', '', name)
    svg = ET.Element('{%s}svg' % NS)
    svg.set('viewBox', VB)
    svg.set('width', VB.split()[2]); svg.set('height', VB.split()[3])
    bg = ET.SubElement(svg, '{%s}rect' % NS)
    bg.set('x', '0'); bg.set('y', '0')
    bg.set('width', VB.split()[2]); bg.set('height', VB.split()[3])
    bg.set('fill', '#ffffff')
    for it in m['items']:
        svg.append(copy_with_ancestors(it['el'], it['anc']))
    fn = f'{OUT}/line-{ref}-{mi:02d}.svg'
    ET.ElementTree(svg).write(fn, encoding='unicode', xml_declaration=False)
    manifest.append({'file': os.path.basename(fn), 'color': '#%02x%02x%02x' % m['rgb'],
                     'guess': name, 'dist': round(dist, 1), 'n': len(m['items'])})
json.dump(manifest, open(f'{OUT}/manifest.json', 'w'), ensure_ascii=False, indent=1)
print('输出', len(manifest), '个线SVG ->', OUT)
