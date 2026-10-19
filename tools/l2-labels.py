# -*- coding: utf-8 -*-
"""1号线站名标签自动放置 v2(干净重写)
规则: 1横线上下/竖线左右 2终点中轴对齐 3不交叉不重叠 4盒中心对圆心 5净距统一G
拐角站: 圆心25px内有走廊顶点且两侧方向混合 -> 第二遍放置, 四方位按邻距降序选
"""
import re, json, math
import xml.etree.ElementTree as ET
from collections import defaultdict
from PIL import ImageFont

NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)
G = 10.0
TERMINUS = {'广州南站', '嘉禾望岗'}
CARD = 'assets/lines/line-2号线.svg'
L1 = ['广州南站','石壁','会江','南浦','洛溪','南洲','东晓南','江泰路','昌岗','江南西',
      '市二宫','海珠广场','公园前','纪念堂','越秀公园','广州火车站','三元里','飞翔公园',
      '白云公园','白云文化广场','萧岗','江夏','黄边','嘉禾望岗']

known = json.load(open('data/_metro-known.json'))
en_of = {st['zh']: st.get('en', '') for st in known['stations']}
_anch = {a['name']: (a['sx'], a['sy']) for a in json.load(open('data/svg2off-anchors.json'))}
_l2map = json.load(open('data/_l2circles24.json')) if __import__('os').path.exists('data/_l2circles24.json') else {}

card = ET.parse(CARD)
root = card.getroot()

# ---- 走廊线段 ----
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
            elif c == 'C':
                p = nums[i+4:i+6]; i += 6
                if len(p) == 2:
                    cur = [p[0]+(cur[0] if rel else 0), p[1]+(cur[1] if rel else 0)]
                    pts.append(tuple(cur))
            else:
                i = len(nums)
    return pts

segs = []
for g in root.iter('{%s}g' % NS):
    if g.get('id') != '走廊':
        continue
    for el in g:
        if el.tag.split('}')[-1] == 'line':
            segs.append((float(el.get('x1')), float(el.get('y1')),
                         float(el.get('x2')), float(el.get('y2'))))
print('走廊线段:', len(segs))

# ---- 圆心锚点(卡片) ----
ANCH = {}
for c in root.iter('{%s}circle' % NS):
    if float(c.get('r', '0')) >= 10:
        continue
    cx, cy = float(c.get('cx')), float(c.get('cy'))
    nm = min(L1, key=lambda k: (_l2map[k][0]-cx)**2 + (_l2map[k][1]-cy)**2)
    if math.hypot(_l2map[nm][0]-cx, _l2map[nm][1]-cy) < 25:
        ANCH[nm] = (cx, cy)
for n in L1:
    ANCH.setdefault(n, tuple(_l2map.get(n) or _anch.get(n) or (0, 0)))
print('圆心锚点:', len(ANCH))

# ---- 字体测量 ----
f_zh = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 21)
f_en = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 11)
ZH_H, EN_H, GAP2 = 11.0, 6.0, 1.5

# ---- 几何工具 ----
def nearest_seg(ax, ay):
    best, bd, bdir = None, 1e18, (1, 0)
    for (x1, y1, x2, y2) in segs:
        dx, dy = x2-x1, y2-y1
        L2 = dx*dx + dy*dy
        if L2 < 1e-6:
            continue
        t = max(0, min(1, ((ax-x1)*dx + (ay-y1)*dy) / L2))
        px, py = x1 + t*dx, y1 + t*dy
        d = math.hypot(ax-px, ay-py)
        if d < bd:
            best, bd, bdir = (px, py), d, (dx, dy)
    return best, bdir

def _ccw(A, B, C):
    return (C[1]-A[1])*(B[0]-A[0]) > (B[1]-A[1])*(B[0]-A[0])
def seg_rect_cross(x1, y1, x2, y2, rx0, ry0, rx1, ry1):
    def si(A, B, C, D):
        return _ccw(A, C, D) != _ccw(B, C, D) and _ccw(A, B, C) != _ccw(A, B, D)
    A, B = (x1, y1), (x2, y2)
    cs = [(rx0, ry0), (rx1, ry0), (rx1, ry1), (rx0, ry1)]
    for i in range(4):
        if si(A, B, cs[i], cs[(i+1) % 4]):
            return True
    return rx0 <= x1 <= rx1 and ry0 <= y1 <= ry1

def clearance(bx0, by0, bx1, by1):
    best = 1e18
    for (x1, y1, x2, y2) in segs:
        if seg_rect_cross(x1, y1, x2, y2, bx0, by0, bx1, by1):
            return 0.0
        for i in range(21):
            t = i / 20
            px, py = x1 + t*(x2-x1), y1 + t*(y2-y1)
            dx = max(bx0-px, 0, px-bx1)
            dy = max(by0-py, 0, py-by1)
            best = min(best, math.hypot(dx, dy))
    return best

# ---- 拐角检测 ----
vmap = defaultdict(list)
for s in segs:
    vmap[(round(s[0], 1), round(s[1], 1))].append(s)
    vmap[(round(s[2], 1), round(s[3], 1))].append(s)

labels = []
for nm in L1:
    ax, ay = ANCH[nm]
    en = en_of.get(nm, '')
    wz = f_zh.getlength(nm) / 2.0
    we = f_en.getlength(en) / 2.0 if en else 0
    bw = max(wz, we)
    bh = ZH_H + GAP2 + (EN_H if en else 0)
    _, (dx, dy) = nearest_seg(ax, ay)
    junc = False
    for (vx, vy), adj in vmap.items():
        if len(adj) < 2 or math.hypot(vx-ax, vy-ay) > 25:
            continue
        if any(abs(s[2]-s[0]) > abs(s[3]-s[1]) for s in adj) and \
           any(abs(s[2]-s[0]) <= abs(s[3]-s[1]) for s in adj):
            junc = True
    _L = math.hypot(dx, dy) or 1.0
    ux, uy = dx/_L, dy/_L
    dx, dy = ux, uy  # 用归一化分量判断
    labels.append({'nm': nm, 'ax': ax, 'ay': ay, 'en': en, 'bw': bw, 'bh': bh,
                   'horiz': abs(dx) > 1.3*abs(dy), 'term': nm in TERMINUS, 'junc': junc,
                   'ux': ux, 'uy': uy,
                   'diag': 0.45 < abs(ux) and 0.45 < abs(uy)})
for _pi, _lb in enumerate(labels):
    _lb['_parity'] = _pi
# 验收钉位: 用户确认过的终点标签盒(重放不得漂移; 嘉禾望岗 2026-10-19 验收)
PINNED = {'嘉禾望岗': (1452.8, 577.8, 1494.8, 596.3)}
for _lb in labels:
    if _lb['nm'] in PINNED:
        _lb['pinned'] = True
        _lb['bx0'], _lb['by0'], _lb['bx1'], _lb['by1'] = PINNED[_lb['nm']]
        _lb['desc'] = '钉位'
print('钉位:', list(PINNED))
print('拐角站:', [lb['nm'] for lb in labels if lb['junc']])
print('斜线站:', [lb['nm'] for lb in labels if lb['diag']])

# ---- 候选 ----
def candidates(lb):
    ax, ay, bw, bh = lb['ax'], lb['ay'], lb['bw'], lb['bh']
    out = []
    if lb['diag'] and not lb['term']:

        # 规则8: 法线两侧放置(优先线左侧 nx<0)
        normals = sorted([(-lb['uy'], lb['ux']), (lb['uy'], -lb['ux'])], key=lambda n: n[0])
        for k, (nx, ny) in enumerate(normals):
            d = G + (abs(nx) * bw + abs(ny) * bh) / 2
            cx, cy = ax + nx * d, ay + ny * d
            out.append(('法左' if nx < 0 else '法右', cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2))
        out.append(('上', ax - bw / 2, ay - G - bh, ax + bw / 2, ay - G))
        out.append(('下', ax - bw / 2, ay + G, ax + bw / 2, ay + G + bh))
        return out
    if lb['term']:
        if lb['horiz']:
            out.append(('端左', ax - G - bw, ay - bh / 2, ax - G, ay + bh / 2))
            out.append(('端右', ax + G, ay - bh / 2, ax + G + bw, ay + bh / 2))
        else:
            out.append(('下中', ax - bw / 2, ay + G, ax + bw / 2, ay + G + bh))
            out.append(('上中', ax - bw / 2, ay - G - bh, ax + bw / 2, ay - G))
        return out
    if lb['horiz']:
        out.append(('上', ax - bw / 2, ay - G - bh, ax + bw / 2, ay - G))
        out.append(('下', ax - bw / 2, ay + G, ax + bw / 2, ay + G + bh))
        out.append(('左', ax - G - bw, ay - bh / 2, ax - G, ay + bh / 2))
        out.append(('右', ax + G, ay - bh / 2, ax + G + bw, ay + bh / 2))
    else:
        out.append(('左', ax - G - bw, ay - bh / 2, ax - G, ay + bh / 2))
        out.append(('右', ax + G, ay - bh / 2, ax + G + bw, ay + bh / 2))
        out.append(('上', ax - bw / 2, ay - G - bh, ax + bw / 2, ay - G))
        out.append(('下', ax - bw / 2, ay + G, ax + bw / 2, ay + G + bh))
    return out

def push_to_gap(lb, desc, bx0, by0, bx1, by1):
    if desc.startswith('法'):
        # 规则8法向盒的净距由构造保证(G+半投影), 轴向外推=沿线滑动, 禁推
        return bx0, by0, bx1, by1
    pushed = 0.0
    for _ in range(6):
        cl = clearance(bx0, by0, bx1, by1)
        if cl >= G - 0.1:
            break
        need = G - cl + 0.2
        pushed += need
        if pushed > 16:
            return None
        if desc in ('上', '上中'):
            by0 -= need; by1 -= need
        elif desc in ('下', '下中'):
            by0 += need; by1 += need
        elif desc in ('左', '端左'):
            bx0 -= need; bx1 -= need
        else:
            bx0 += need; bx1 += need
        if desc in ('上', '下', '上中', '下中'):
            w = bx1 - bx0
            bx0, bx1 = lb['ax'] - w/2, lb['ax'] + w/2
        else:
            h = by1 - by0
            by0, by1 = lb['ay'] - h/2, lb['ay'] + h/2
    return bx0, by0, bx1, by1

placed = []
def place(lb):
    cands = candidates(lb)
    if lb['junc'] and placed:
        def adj_gap(c):
            _, x0, y0, x1, y1 = c
            g = 1e18
            for p in placed:
                gx = max(p['bx0']-x1, x0-p['bx1'], 0)
                gy = max(p['by0']-y1, y0-p['by1'], 0)
                g = min(g, math.hypot(gx, gy))
            return g
        cands = sorted(cands, key=lambda c: -adj_gap(c))
    for strict in (True, False):
        for desc, bx0, by0, bx1, by1 in cands:
            _r = push_to_gap(lb, desc, bx0, by0, bx1, by1)
            if _r is None:
                continue
            bx0, by0, bx1, by1 = _r
            bad = False
            for (x1, y1, x2, y2) in segs:
                if seg_rect_cross(x1, y1, x2, y2, bx0, by0, bx1, by1):
                    if math.hypot((x1+x2)/2-lb['ax'], (y1+y2)/2-lb['ay']) < 12:
                        continue
                    bad = True
                    break
            if bad:
                continue
            clash = False
            for p in placed:
                if not (bx0 > p['bx1'] or p['bx0'] > bx1 or by0 > p['by1'] or p['by0'] > by1):
                    clash = True
                    break
            if clash:
                continue
            if strict:
                cover = False
                for lb2 in labels:
                    if lb2 is lb:
                        continue
                    if bx0-4 < lb2['ax'] < bx1+4 and by0-4 < lb2['ay'] < by1+4:
                        cover = True
                        break
                if cover:
                    continue
            lb.update({'desc': desc, 'bx0': bx0, 'by0': by0, 'bx1': bx1, 'by1': by1})
            placed.append(lb)
            return
    desc, bx0, by0, bx1, by1 = cands[0]
    _r = push_to_gap(lb, desc, bx0, by0, bx1, by1)
    if _r is not None:
        bx0, by0, bx1, by1 = _r
    lb.update({'desc': desc, 'bx0': bx0, 'by0': by0, 'bx1': bx1, 'by1': by1})
    placed.append(lb)


for lb in labels:
    if lb.get('pinned'):
        placed.append(lb)
        continue
    if lb['junc']:
        continue
    place(lb)
for lb in labels:
    if lb.get('pinned') or not lb['junc']:
        continue
    place(lb)

for lb in placed:
    print('%-5s %-3s bbox(%.0f,%.0f)-(%.0f,%.0f) 净距%.1f' %
          (lb['nm'], lb['desc'], lb['bx0'], lb['by0'], lb['bx1'], lb['by1'],
           clearance(lb['bx0'], lb['by0'], lb['bx1'], lb['by1'])))

# ---- 写入 ----
par = {}
def build(el):
    for ch in el:
        par[id(ch)] = el
        build(ch)
build(root)
for gg in list(root.iter('{%s}g' % NS)):
    if gg.get('id') == '站名标注':
        par[id(gg)].remove(gg)
g = ET.SubElement(root, '{%s}g' % NS)
g.set('id', '站名标注')
g.set('font-family', "'Microsoft YaHei', 'PingFang SC', sans-serif")
for lb in placed:
    zx = (lb['bx0'] + lb['bx1']) / 2
    zy = lb['by0'] + ZH_H
    zh_t = ET.SubElement(g, '{%s}text' % NS)
    zh_t.set('x', str(round(zx, 1))); zh_t.set('y', str(round(zy, 1)))
    zh_t.set('text-anchor', 'middle')
    zh_t.set('font-size', '10.5')
    zh_t.set('font-weight', '500')
    zh_t.set('fill', '#1a1a1a')
    zh_t.text = lb['nm']
    if lb['en']:
        en_t = ET.SubElement(g, '{%s}text' % NS)
        en_t.set('x', str(round(zx, 1))); en_t.set('y', str(round(lb['by1'], 1)))
        en_t.set('text-anchor', 'middle')
        en_t.set('font-size', '5.5')
        en_t.set('fill', '#444444')
        en_t.text = lb['en']
card.write(CARD, encoding='unicode', xml_declaration=False)
print('写入完成')
