# -*- coding: utf-8 -*-
"""单线卡片图 v3: 编号徽章 + 走廊 + 站圆 + 站名(原字形拷贝) + 内容框缩放"""
import json
import math
import os
import re
import copy
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image

NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)
SVG = 'assets/gz-tim-2026.svg'
PNG = r'C:/Users/zlj10/WorkBuddy/2026-10-18-14-11-14/metro/gz_metro_2026_5700px.png'
OUT = 'assets/lines'
VBW, VBH = 2848.5, 2054.25

tree = ET.parse(SVG)
root = tree.getroot()
CSS = {}
for st in root.iter('{%s}style' % NS):
    for m in re.finditer(r'\.([\w-]+)\{([^}]*)\}', st.text or ''):
        sm = re.search(r'stroke:\s*(#[0-9A-Fa-f]{3,6})', m.group(2))
        CSS[m.group(1)] = sm.group(1) if sm else None

def hex2rgb(h):
    h = h.lstrip('#')
    if len(h) == 3:
        h = ''.join(c*2 for c in h)
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def transform_of(el):
    t = el.get('transform')
    if not t:
        return None
    m = re.match(r'translate\(([-\d.]+)[, ]+([-\d.]+)\)', t)
    if m:
        return ('t', float(m.group(1)), float(m.group(2)))
    m = re.match(r'matrix\(([-\d.eE]+),([-\d.eE]+),([-\d.eE]+),([-\d.eE]+),([-\d.eE]+),([-\d.eE]+)\)', t)
    if m:
        return ('m', *[float(v) for v in m.groups()])
    return None

def apply_tf(tf, x, y):
    if tf is None:
        return x, y
    if tf[0] == 't':
        return x+tf[1], y+tf[2]
    if tf[0] == 'm':
        _, a, b, c, d, e, f = tf
        return a*x+c*y+e, b*x+d*y+f
    return x, y

def sample_d(d):
    pts = []
    cur = [0.0, 0.0]
    start = [0.0, 0.0]
    for cmd, body in re.findall(r'([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)', d):
        nums = [float(v) for v in re.findall(r'-?\d+\.?\d*(?:[eE][-+]?\d+)?', body)]
        rel = cmd.islower()
        c = cmd.upper()
        i = 0
        while i < len(nums):
            if c == 'M':
                p = nums[i:i+2]; i += 2
                cur = [p[0]+(cur[0] if rel else 0), p[1]+(cur[1] if rel else 0)]
                start = list(cur); pts.append(tuple(cur))
            elif c == 'L':
                p = nums[i:i+2]; i += 2
                cur = [p[0]+(cur[0] if rel else 0), p[1]+(cur[1] if rel else 0)]
                pts.append(tuple(cur))
            elif c == 'H':
                cur[0] = nums[i]+(cur[0] if rel else 0); i += 1; pts.append(tuple(cur))
            elif c == 'V':
                cur[1] = nums[i]+(cur[1] if rel else 0); i += 1; pts.append(tuple(cur))
            elif c in 'CQ':
                p = nums[i+4:i+6] if c == 'C' else nums[i+2:i+4]
                i += 6 if c == 'C' else 4
                if len(p) == 2:
                    cur = [p[0]+(cur[0] if rel else 0), p[1]+(cur[1] if rel else 0)]
                    pts.append(tuple(cur))
            elif c == 'S' or c == 'T':
                p = nums[i:i+2]; i += 2
                cur = [p[0]+(cur[0] if rel else 0), p[1]+(cur[1] if rel else 0)]
                pts.append(tuple(cur))
            elif c == 'A':
                p = nums[i+5:i+7]; i += 7
                if len(p) == 2:
                    cur = [p[0]+(cur[0] if rel else 0), p[1]+(cur[1] if rel else 0)]
                    pts.append(tuple(cur))
            elif c == 'Z':
                cur = list(start); pts.append(tuple(cur)); i = len(nums)
            else:
                i = len(nums)
    return pts


items = []
def walk(el, anc):
    tag = el.tag.split('}')[-1]
    if tag in ('path', 'circle', 'rect', 'line', 'ellipse'):
        items.append({'el': el, 'anc': list(anc), 'tag': tag})
    for ch in el:
        walk(ch, anc + [el])
walk(root, [])

def linecol(it):
    for e in [it['el']] + it['anc'][::-1]:
        c = e.get('class')
        if c in CSS and CSS[c]:
            return hex2rgb(CSS[c])
        v = e.get('stroke')
        if v and v.startswith('#'):
            return hex2rgb(v)
    return None

bycol = {}
for it in items:
    c = linecol(it)
    if c and max(c)-min(c) > 40 and max(c) > 60 and not min(c) > 200:
        bycol.setdefault(c, []).append(it)
keys = sorted(bycol, key=lambda k: -len(bycol[k]))
merged = []
for k in keys:
    if len(bycol[k]) < 6 or len(bycol[k]) > 400:
        continue
    for m in merged:
        if max(abs(k[i]-m['rgb'][i]) for i in range(3)) <= 18:
            m['items'] += bycol[k]
            break
    else:
        merged.append({'rgb': k, 'items': list(bycol[k])})

img = Image.open(PNG).convert('RGB')
arr = np.array(img).astype(int)
SC = img.width / VBW

def ring_med(cx, cy, r0, r1):
    x0, y0 = cx*SC, cy*SC
    pts = []
    for a in range(0, 360, 10):
        for r in np.arange(r0, r1, 1.5):
            x, y = int(x0 + r*np.cos(np.radians(a))), int(y0 + r*np.sin(np.radians(a)))
            if 0 <= x < arr.shape[1] and 0 <= y < arr.shape[0]:
                pts.append(arr[y, x])
    if not pts:
        return None
    px = np.array(pts)
    mx, mn = px.max(axis=1), px.min(axis=1)
    sel = px[(mx-mn > 40) & (mx > 60)]
    return np.median(sel, axis=0) if len(sel) >= 5 else None

def center_of(it):
    if it['tag'] == 'circle':
        cx, cy = float(it['el'].get('cx', 0)), float(it['el'].get('cy', 0))
        for a in reversed(it['anc']):
            cx, cy = apply_tf(transform_of(a), cx, cy)
        return cx, cy
    m = re.findall(r'-?\d+\.?\d*(?:[eE][-+]?\d+)?', it['el'].get('d', ''))
    if len(m) < 4:
        return None
    nums = [float(v) for v in m]
    xs, ys = nums[0::2], nums[1::2]
    return (min(xs)+max(xs))/2, (min(ys)+max(ys))/2


def geom_pts(it):
    if it['tag'] == 'line':
        try:
            x1, y1 = float(it['el'].get('x1', 0)), float(it['el'].get('y1', 0))
            x2, y2 = float(it['el'].get('x2', 0)), float(it['el'].get('y2', 0))
        except (TypeError, ValueError):
            return []
        n = max(2, int(((x2-x1)**2 + (y2-y1)**2) ** 0.5 / 10))
        return [(x1 + (x2-x1)*t/n, y1 + (y2-y1)*t/n) for t in range(n+1)]
    return sample_d(it['el'].get('d', ''))

circles = []
for it in items:
    if it['tag'] == 'circle':
        circles.append(it)

def center_of_circle(it):
    if it['tag'] != 'circle':
        return None
    return float(it['el'].get('cx', 0)), float(it['el'].get('cy', 0))

def apply_tf2(tf, x, y):
    if tf is None:
        return x, y
    if tf[0] == 't':
        return x+tf[1], y+tf[2]
    if tf[0] == 'm':
        _, a, b, c, d, e, f = tf
        return a*x+c*y+e, b*x+d*y+f
    return x, y

def copy_el(it):
    chain = []
    for a in it['anc']:
        if a is root:
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

manifest = json.load(open(f'{OUT}/manifest.json'))
by_color_file = {}
for mi in manifest:
    rgb = tuple(int(mi['color'][i:i+2], 16) for i in (1, 3, 5))
    by_color_file[rgb] = mi

report = []
for i, m in enumerate(merged):
    rgb = m['rgb']
    # 站圆归线
    st_circles = []
    for it in circles:
        c = center_of_circle(it)
        if c is None:
            continue
        med = ring_med(c[0], c[1], float(it['el'].get('r', 4))+3, float(it['el'].get('r', 4))+12)
        if med is None:
            continue
        if np.linalg.norm(med - np.array(rgb)) < 60:
            st_circles.append((it, c))
    # 颜色命中的站圆先算(图例过滤基准)
    _seed_c = []
    for it in circles:
        c2 = center_of_circle(it)
        if c2 is None:
            continue
        r = float(it['el'].get('r', 4))
        med = None
        x0, y0 = c2[0]*SC, c2[1]*SC
        _pts = []
        for ang in range(0, 360, 12):
            for rr in np.arange(r+3, r+12, 2):
                x, y = int(x0 + rr*np.cos(np.radians(ang))*SC/2.0), int(y0 + rr*np.sin(np.radians(ang))*SC/2.0)
                if 0 <= x < arr.shape[1] and 0 <= y < arr.shape[0]:
                    _pts.append(arr[y, x])
        if _pts:
            px2 = np.array(_pts)
            mx2, mn2 = px2.max(axis=1), px2.min(axis=1)
            sel2 = px2[(mx2-mn2 > 40) & (mx2 > 60)]
            if len(sel2) >= 5:
                med = np.median(sel2, axis=0)
        if med is not None and float(np.linalg.norm(med - np.array(m['rgb']))) < 60:
            _seed_c.append(c2)
    _seed_arr = np.array(_seed_c) if _seed_c else None
    # 锚点播种(svg2off真实站坐标): 距走廊采样点<40px的锚站, 其就近圆强制收录
    _anchors = json.load(open('data/svg2off-anchors.json'))
    def tf_pts_local(it, pts):
        return list(pts)
    _cpts_probe = []
    for it in m['items']:
        if it['tag'] in ('path', 'line'):
            _cpts_probe += tf_pts_local(it, geom_pts(it))
    _have_c = set(id(it) for it, _ in [(x, 0) for x in []])
    for an in _anchors:
        ax, ay = an['sx'], an['sy']
        if not any((ax-px)**2 + (ay-py)**2 < 40*40 for px, py in _cpts_probe):
            continue
        bestit, bd = None, 1e18
        for it in circles:
            c2 = center_of_circle(it)
            if c2 is None:
                continue
            d2 = (c2[0]-ax)**2 + (c2[1]-ay)**2
            if d2 < bd:
                bd, bestit = d2, it
        if bestit is not None and bd < 20*20:
            st_circles = [(i2, c3) for i2, c3 in st_circles if id(i2) != id(bestit)]
            st_circles.append((bestit, center_of_circle(bestit)))
        else:
            syn = ET.Element('{%s}circle' % NS)
            syn.set('cx', str(ax)); syn.set('cy', str(ay)); syn.set('r', '4.5')
            syn.set('style', 'fill:#FFFFFF;stroke:#%02x%02x%02x;stroke-width:2' % m['rgb'])
            st_circles.append(({'el': syn, 'anc': [], 'tag': 'circle'}, (ax, ay)))
    _myanch_pre = [(an['sx'], an['sy'], an['name']) for an in _anchors
                   if any((an['sx']-px)**2 + (an['sy']-py)**2 < 15*15 for px, py in _cpts_probe)]
    _myanch_set = set(t[2] for t in _myanch_pre)
    # 走廊采样点: 真路径token解析(正确处理相对命令)
    def tf_pts(it, pts):
        return list(pts)
    cpts = []
    for it in m['items']:
        if it['tag'] in ('path', 'line'):
            for q in tf_pts(it, sample_d(it['el'].get('d', ''))):
                _anch = [(an['sx'], an['sy']) for an in json.load(open('data/svg2off-anchors.json'))]
                if _seed_arr is None or len(_seed_arr) == 0 or min((q[0]-s[0])**2 + (q[1]-s[1])**2 for s in _seed_arr) < 420*420 or min((q[0]-s[0])**2 + (q[1]-s[1])**2 for s in _anch) < 60*60:
                    cpts.append(q)
    have = set(id(it) for it, _ in st_circles)
    import numpy as _np
    CP = _np.array(cpts) if cpts else None
    for it in circles:
        if id(it) in have:
            continue
        c2 = center_of_circle(it)
        if c2 is None or CP is None or len(CP) == 0:
            continue
        d2 = ((CP[:, 0]-c2[0])**2 + (CP[:, 1]-c2[1])**2).min()
        if d2 < 17*17:
            st_circles.append((it, c2))
            have.add(id(it))
    if len(st_circles) < 5:
        continue
    # 站名: 就近站圆(45px)的黑色系小path
    # 站名: 全局一对一指派 —— 原图全部中文字行 与 全部锚站 匈牙利配派(总距最小)
    # 每锚站恰得一行字(自身站名), 密集区不会被他站抢行; 本线锚站的行+行下英文=站名
    _allglyphs = []
    for it in items:
        if it['tag'] != 'path' or linecol(it) is not None:
            continue
        pts2 = sample_d(it['el'].get('d', ''))
        if len(pts2) < 2:
            continue
        xs2 = [p[0] for p in pts2]
        ys2 = [p[1] for p in pts2]
        w2, h2 = max(xs2)-min(xs2), max(ys2)-min(ys2)
        if 0.5 < w2/max(h2, .01) < 2.05 and 5.0 < h2 < 13.5:
            _allglyphs.append({'it': it, 'cx': (min(xs2)+max(xs2))/2, 'cy': (min(ys2)+max(ys2))/2})
    # 全局字行
    _rows = []
    _bands = {}
    for g in _allglyphs:
        _bands.setdefault(round(g['cy']//9), []).append(g)
    for k, bl in _bands.items():
        bl.sort(key=lambda g2: g2['cx'])
        cur = []
        for g in bl:
            if cur and g['cx'] - cur[-1]['cx'] > 22:
                if 2 <= len(cur) <= 8:
                    _rows.append(cur)
                cur = []
            cur.append(g)
        if 2 <= len(cur) <= 8:
            _rows.append(cur)
    _rowinfo = [{'cx': sum(g['cx'] for g in rw)/len(rw), 'cy': sum(g['cy'] for g in rw)/len(rw),
                 'n': len(rw), 'row': rw} for rw in _rows]
    # 代价矩阵(锚x行), 匹配约束: |锚名长-行字数|<=1 且 距离<=60
    import numpy as _np
    BIG = 1e6
    C = _np.full((len(_anchors), len(_rowinfo)), BIG)
    for i, an in enumerate(_anchors):
        for j, ri in enumerate(_rowinfo):
            dn = abs(len(an['name']) - ri['n'])
            if dn > 2:
                continue
            d = math.hypot(ri['cx']-an['sx'], ri['cy']-an['sy'])
            if d <= 60:
                C[i, j] = d + 8*dn
    from scipy.optimize import linear_sum_assignment as _lsa
    _ri, _ci = _lsa(C)
    _anchor_row = {}
    for i, j in zip(_ri, _ci):
        if C[i, j] < BIG:
            _anchor_row[i] = j
    print('  指派: %d/%d 锚站获得字行' % (len(_anchor_row), len(_anchors)))
    def _fp_of(el):
        d = el.get('d', '')
        nums = [float(v) for v in re.findall(r'-?[0-9.]+', d)]
        if len(nums) < 4:
            return None
        ox, oy = nums[0], nums[1]
        rel2 = [round(v - (ox if i % 2 == 0 else oy), 1) for i, v in enumerate(nums)]
        return ''.join(re.findall(r'[A-Za-z]', d)) + '|' + ','.join(map(str, rel2))
    _fpmap = {}
    for i, j2 in _anchor_row.items():
        row = _rowinfo[j2]['row']
        nm2 = _anchors[i]['name']
        if len(row) != len(nm2):
            continue
        for g, ch in zip(row, nm2):
            fp = _fp_of(g['it']['el'])
            if fp:
                _fpmap.setdefault(fp, {})
                _fpmap[fp][ch] = _fpmap[fp].get(ch, 0) + 1
    _fp2c = {}
    for fp, vs in _fpmap.items():
        ch, n2 = max(vs.items(), key=lambda kv: kv[1])
        if len(vs) == 1:
            _fp2c[fp] = ch
    def _decode_fallback(a0, a1, aname):
        used_j = set(_anchor_row.values())
        for jj, ri in enumerate(_rowinfo):
            if jj in used_j:
                continue
            d = math.hypot(ri['cx']-a0, ri['cy']-a1)
            if d > 55:
                continue
            txt = ''
            for g in ri['row']:
                fp = _fp_of(g['it']['el'])
                txt += _fp2c.get(fp, '?') if fp else '?'
            if aname in txt:
                return jj
        return None
    names = []
    _named = set()
    for aidx, (a0, a1, aname) in enumerate(_myanch_pre):
        # _myanch_pre的锚在_anchors里的索引: 按名匹配
        ai = next((i for i, an in enumerate(_anchors) if an['name'] == aname and abs(an['sx']-a0) < 1), None)
        j = _anchor_row.get(ai)
        if j is not None:
            # 行内容校验: 解码指派行, 不含站名则作废
            _txt = ''.join(_fp2c.get(_fp_of(g['it']['el']), '?') for g in _rowinfo[j]['row'])
            if aname not in _txt:
                j = None
        if j is None:
            # 宽限补救: 未被指派的行中, 距离<=50且字数差<=2的最近行
            used_j = set(_anchor_row.values())
            best = None
            for jj, ri in enumerate(_rowinfo):
                if jj in used_j or abs(len(aname) - ri['n']) > 2:
                    continue
                d = math.hypot(ri['cx']-a0, ri['cy']-a1)
                if d <= 50 and (best is None or d < best[0]):
                    best = (d, jj)
            if best is None:
                j = _decode_fallback(a0, a1, aname)
            if j is None:
                # 终极兜底: 拷贝40px内未被其他锚站行认领的字形
                _claimed = set()
                for i2, j2 in _anchor_row.items():
                    if _anchors[i2]['name'] == aname:
                        continue
                    for g in _rowinfo[j2]['row']:
                        _claimed.add(id(g['it']['el']))
                _got = 0
                for g in _allglyphs:
                    eid = id(g['it']['el'])
                    if eid in _claimed or eid in _named:
                        continue
                    if math.hypot(g['cx']-a0, g['cy']-a1) < 40:
                        names.append(g['it'])
                        _named.add(eid)
                        _got += 1
                if _got == 0:
                    print('  !! %s 无字行' % aname)
                continue
        row = _rowinfo[j]['row']
        for g in row:
            names.append(g['it'])
            _named.add(id(g['it']))
        # 行28px邻域内一切未认领字形(英文名等), 但排除其他锚点已认领的字形
        _others = set()
        for i2, j2 in _anchor_row.items():
            if _anchors[i2]['name'] == aname:
                continue
            for g2 in _rowinfo[j2]['row']:
                _others.add(id(g2['it']['el']))
        for it in items:
            if it['tag'] != 'path' or linecol(it) is not None:
                continue
            if id(it['el']) in _named or id(it['el']) in _others:
                continue
            pts2 = sample_d(it['el'].get('d', ''))
            if len(pts2) < 2:
                continue
            xs2 = [p[0] for p in pts2]
            ys2 = [p[1] for p in pts2]
            w2, h2 = max(xs2)-min(xs2), max(ys2)-min(ys2)
            cx2, cy2 = (min(xs2)+max(xs2))/2, (min(ys2)+max(ys2))/2
            if any(math.hypot(cx2-g['cx'], cy2-g['cy']) < 28 for g in row):
                names.append(it)
                _named.add(id(it['el']))
    # 内容框
    # 以路线为准: bbox=走廊轨迹范围
    if not cpts:
        continue
    _myanch = [(t[0], t[1]) for t in _myanch_pre]
    if not _myanch:
        _myanch = [(sc[0], sc[1]) for _, sc in st_circles[:5]]
    if not _myanch:
        continue
    xs = [p[0] for p in _myanch]
    ys = [p[1] for p in _myanch]
    for p in cpts:
        if any((p[0]-a0)**2 + (p[1]-a1)**2 < 130*130 for a0, a1 in _myanch):
            xs.append(p[0]); ys.append(p[1])
    for _, sc in st_circles:
        if any((sc[0]-a0)**2 + (sc[1]-a1)**2 < 130*130 for a0, a1 in _myanch):
            xs.append(sc[0]); ys.append(sc[1])
    x0, x1 = min(xs)-65, max(xs)+65
    y0, y1 = min(ys)-75, max(ys)+75
    # 徽章文字: manifest猜测名里的数字/字母
    mi = by_color_file.get(rgb) or next((v for k, v in by_color_file.items()
                                         if max(abs(k[j]-rgb[j]) for j in range(3)) <= 18), None)
    label = ''
    if mi:
        mm = re.search(r'(\d+|[A-Za-z]+)', mi['guess'])
        label = mm.group(1) if mm else '?'
    svg = ET.Element('{%s}svg' % NS)
    for stl in root.iter('{%s}style' % NS):
        svg.append(copy.deepcopy(stl))
    W, H = x1-x0, y1-y0
    svg.set('viewBox', f'{x0} {y0} {W} {H}')
    svg.set('width', str(round(W))); svg.set('height', str(round(H)))
    bg = ET.SubElement(svg, '{%s}rect' % NS)
    bg.set('x', str(x0)); bg.set('y', str(y0)); bg.set('width', str(W)); bg.set('height', str(H))
    bg.set('fill', '#ffffff')
    for it in m['items']:
        svg.append(copy_el(it))
    for it, _ in st_circles:
        svg.append(copy_el(it))
    for it in names:
        svg.append(copy_el(it))
    # 编号徽章(左上角)
    bx, by = x0+46, y0+46
    g = ET.SubElement(svg, '{%s}g' % NS)
    c = ET.SubElement(g, '{%s}circle' % NS)
    c.set('cx', str(bx)); c.set('cy', str(by)); c.set('r', '34')
    c.set('fill', '#%02x%02x%02x' % rgb)
    t = ET.SubElement(g, '{%s}text' % NS)
    t.set('x', str(bx)); t.set('y', str(by+13))
    t.set('text-anchor', 'middle')
    t.set('font-family', 'Arial, sans-serif')
    t.set('font-size', '38')
    t.set('font-weight', 'bold')
    t.set('fill', '#ffffff')
    t.text = label
    fn = mi['file'] if mi else f'line-color-{i:02d}.svg'
    ET.ElementTree(svg).write(f'{OUT}/{fn}', encoding='unicode', xml_declaration=False)
    report.append((fn, len(m['items']), len(st_circles), len(names), label))
for r in report:
    print('%s: 走廊%d 站圆%d 站名字形%d 徽章"%s"' % r)
print('done', len(report))
