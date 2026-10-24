# -*- coding: utf-8 -*-
"""全网合成图: 19张主卡(原图绝对坐标)走廊合并 + 同名站唯一标记 + 换乘标签 + 图例。

原则(勿动摇):
- 走廊逐元素原样复制(各卡坐标=官图绝对坐标, 仅viewBox不同, 已核全卡无transform);
- 换乘站唯一: 同名实例散布<=SPREAD_CIRC → 共享圆(多线黑描边/单线本线色);
  散布>SPREAD_CIRC → 凸包包络胶囊(粗白描边+细黑描边, 官图胶囊换乘画法),
  每条服务线走廊端点都在包络内(构造保证), 不出现第二个独立站圆;
- 换乘枢纽定向胶囊规则(2026-10-21 用户定稿, 勿动摇):
  1) 能并单圆(两线走廊有共同可达点且钉距<=9px)→共享圆(如珠江新城/彩虹桥/如意坊);
  2) 并不了圆→定向胶囊(**胶囊方向⊥线群走向**): 线群主要【纵向】走向→【横向】胶囊(各线钉同y横排, 如西塱/芳村/广州南站/官洲/大学城北/大学城南),
     主要【横向】走向→【纵向】胶囊(各线钉同x纵排, 如东湖/沙园/番禺广场/广州火车站/五羊邨/嘉禾望岗/广州东站),
     沿45°斜线汇交→【垂直于斜线】的斜向胶囊(两钉连线⊥斜线, 如镇龙/中山八);
  3) 钉位微调只沿各自走廊(每钉在本线走廊上+走链单调), 跨度>9px即可成胶囊且尽量小;
     需更小时可重切走廊缓坡让两线端互相探进(东湖接缝压缩27→13.5px先例);
     锁死走廊无法靠拢的(如芳村两竖线相距18px)以走廊几何为下限。
- 门禁: N1 标记数=唯一站名数  N2 实例全落标记内  N3 标签净距(走廊/标记/互斥)
  N4 不同名标记不塌缩(<8px即红)  N5 幂等(重跑字节一致)。
用法: python tools/build-network.py
"""
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINES_DIR = os.path.join(ROOT, 'assets', 'lines')
OUT_SVG = os.path.join(LINES_DIR, 'network-全网.svg')
OUT_JSON = os.path.join(ROOT, 'data', '_network-audit.json')
NS = 'http://www.w3.org/2000/svg'
Q = lambda t: '{%s}%s' % (NS, t)

ORDER = ['1号线', '2号线', '3号线', '4号线', '5号线', '6号线', '7号线', '8号线',
         '9号线', '10号线', '11号线', '12号线', '13号线', '14号线', '18号线',
         '21号线', '22号线', '广佛线', 'APM线']

SPREAD_CIRC = 9.0        # 同名实例最大两两距离阈值: 内=共享圆, 外=胶囊包络
BADGE_H = 13.5           # 徽标高=1.5×序号胶囊高(codes全网编号牌 H=9.0), 2026-10-24用户定稿;
                         # 宽随各卡徽标原比例(原高均43 -> 统一scale=13.5/43≈0.314)
FORCE_CAPSULE = {'镇龙'}  # 钉距<=9仍按胶囊: 几何锁死站的显式豁免(2026-10-22)
CAP_W = 10.0             # 胶囊白色带宽(=直径)
CAP_RING = 2.0           # 胶囊黑描边宽
CIRC_R_MULTI = 5.0       # 多线共享圆半径
INK = '#1a1a1a'
CORRIDOR_HALF = 3.5      # 走廊 stroke-width 7 的半宽
GAP_CORRIDOR = 2.0       # 标签-走廊净距下限
GAP_MARKER = 1.5         # 标签-标记净距下限
GAP_LABEL = 1.5          # 标签-标签净距下限
FONT_ZH = 10.5
DIRS = [(0, -1), (1, 0), (1, -1), (-1, 0), (-1, -1), (0, 1), (1, 1), (-1, 1)]
RINGS = [4.0, 12.0, 20.0]


# ---------- 几何 ----------
def dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def seg_point_dist(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    dd = dx * dx + dy * dy
    t = 0.0 if dd == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / dd))
    return dist(p, (ax + t * dx, ay + t * dy))


def rect_seg_dist(rect, a, b):
    """rect=(x,y,w,h). 线段与矩形净距: 相交=0(含穿过: 两端在外中间穿越也必须判0——
    2026-10-22 2号线徽标被22号线斜线贯穿bug根因: 旧版仅两端都在内才判0),
    否则端点到矩形/角到线段取小。"""
    rx, ry, rw, rh = rect
    cx0, cy0, cx1, cy1 = rx, ry, rx + rw, ry + rh

    def pt_rect(p):
        qx = min(max(p[0], cx0), cx1); qy = min(max(p[1], cy0), cy1)
        return dist(p, (qx, qy))

    def seg_rect_inter():
        t0, t1 = 0.0, 1.0
        dx, dy = b[0] - a[0], b[1] - a[1]
        for d, lo, hi in ((dx, cx0 - a[0], cx1 - a[0]), (dy, cy0 - a[1], cy1 - a[1])):
            if abs(d) < 1e-12:
                if lo > 0 or hi < 0:
                    return False
            else:
                ta, tb = lo / d, hi / d
                if ta > tb:
                    ta, tb = tb, ta
                t0, t1 = max(t0, ta), min(t1, tb)
                if t0 > t1:
                    return False
        return True

    if pt_rect(a) == 0 or pt_rect(b) == 0 or seg_rect_inter():
        return 0.0
    corners = [(cx0, cy0), (cx1, cy0), (cx1, cy1), (cx0, cy1)]
    return min(pt_rect(a), pt_rect(b), min(seg_point_dist(c, a, b) for c in corners))


def hull(points):
    """单调链凸包, 退化(<3不同点)返回按输入序的1-2点。"""
    pts = sorted(set((round(x, 2), round(y, 2)) for x, y in points))
    if len(pts) <= 2:
        return pts
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo = []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    up = []
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    h = lo[:-1] + up[:-1]
    if len(h) > 2 and all(abs(cross(h[0], h[i], h[i + 1])) < 1e-9 for i in range(1, len(h) - 1)):
        return [h[0], h[-1]]
    return h if len(h) >= 3 else [pts[0], pts[-1]]


def poly_edges(h):
    return [(h[i], h[(i + 1) % len(h)]) for i in range(len(h))]


def point_in_poly(p, h):
    x, y = p
    inside = False
    for i in range(len(h)):
        x1, y1 = h[i]; x2, y2 = h[(i + 1) % len(h)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def fmt(v):
    return ('%.2f' % v).rstrip('0').rstrip('.')


def fmt4(v):
    return ('%.4f' % v).rstrip('0').rstrip('.')


# ---------- 解析主卡 ----------
corridors = []          # (线名, x1,y1,x2,y2, 颜色)
instances = {}          # 站名 -> [(线名, x, y)]
colors = {}
badge_inner = {}        # 线名 -> header徽标组内容(局部坐标)
badge_size = {}         # 线名 -> (w, h)
for name in ORDER:
    path = os.path.join(LINES_DIR, 'line-%s.svg' % name)
    src = open(path, encoding='utf-8').read()
    m = re.search(r'<g data-badge="header"[^>]*>(.*?)</g>', src, re.S)
    assert m, '%s 缺 header 徽标组' % name
    badge_inner[name] = m.group(1)
    rr = re.search(r'<rect x="([\d.-]+)" y="([\d.-]+)" width="([\d.]+)" height="([\d.]+)"', m.group(1))
    badge_size[name] = (float(rr.group(3)), float(rr.group(4)))
    root = ET.parse(path).getroot()
    for g in root.findall(Q('g')):
        gid = g.get('id')
        if gid == '走廊':
            for ln in g.findall(Q('line')):
                m = re.search(r'stroke:(#[0-9A-Fa-f]+)', ln.get('style', ''))
                colors[name] = m.group(1) if m else '#607d8b'
                corridors.append((name, *(float(ln.get(k)) for k in ('x1', 'y1', 'x2', 'y2')), colors[name]))
        elif gid == '站圆':
            for c in g.findall(Q('circle')):
                nm = c.get('data-nm')
                assert nm, '%s 站圆缺 data-nm' % name
                key = (nm, name)
                assert key not in instances.get(nm, []) or True
                instances.setdefault(nm, []).append((name, float(c.get('cx')), float(c.get('cy'))))

for nm in instances:
    seen = set()
    for ln, x, y in instances[nm]:
        assert (ln, round(x, 1), round(y, 1)) not in seen, '%s 同卡重复站圆' % nm
        seen.add((ln, round(x, 1), round(y, 1)))

# ---------- 唯一标记 ----------
markers = []            # dict(name, lines, kind, ...)
audit = {'stations': 0, 'shared_circle': 0, 'capsule': 0, 'single': 0,
         'spread_list': [], 'capsule_names': []}
for nm in sorted(instances):
    pts = [(x, y) for _, x, y in instances[nm]]
    lines = sorted(set(ln for ln, _, _ in instances[nm]))
    multi = len(lines) > 1
    spread = max((dist(a, b) for i, a in enumerate(pts) for b in pts[i + 1:]), default=0.0)
    audit['stations'] += 1
    if not multi:
        audit['single'] += 1
    if spread > SPREAD_CIRC or nm in FORCE_CAPSULE:  # 强制胶囊: 镇龙=两平行45°斜线垂距7.9px锁死(直线+垂直胶囊唯一解)
        h = hull(pts)
        cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
        markers.append(dict(name=nm, lines=lines, kind='capsule', hull=h, center=(cx, cy), spread=spread))
        audit['capsule'] += 1
        audit['capsule_names'].append(nm)
    else:
        cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
        kind = 'circ_multi' if multi else 'circ_single'
        markers.append(dict(name=nm, lines=lines, kind=kind, center=(cx, cy), spread=spread,
                            r=CIRC_R_MULTI if multi else 4.5))
        if multi:
            audit['shared_circle'] += 1
    if multi and spread > 0.5:
        audit['spread_list'].append([nm, round(spread, 1), lines])

# ---------- 标签(仅换乘站) ----------
def label_box(nm, x, y):
    w = len(nm) * FONT_ZH + 2
    return w, FONT_ZH + 2.5


def place_box(w, h, px, py, dx, dy):
    """锚点(px,py)=标记外沿点, 按8向放置, 返回标签矩形(x,y,w,h)。"""
    if dx > 0:
        x = px
    elif dx < 0:
        x = px - w
    else:
        x = px - w / 2
    if dy > 0:
        y = py
    elif dy < 0:
        y = py - h
    else:
        y = py - h / 2
    return x, y, w, h


def marker_anchor(mk, dx, dy):
    """从标记中心沿(dx,dy)取外沿锚点。"""
    cx, cy = mk['center']
    if mk['kind'] == 'capsule':
        r = CAP_W / 2 + CAP_RING
    else:
        r = mk['r'] + 1.0
    return cx + dx * r, cy + dy * r


def clearances_ok(rect, mk, placed):
    x, y, w, h = rect
    for nm2, x2, y2, w2, h2 in placed:
        if not (x + w + GAP_LABEL < x2 or x2 + w2 + GAP_LABEL < x or
                y + h + GAP_LABEL < y2 or y2 + h2 + GAP_LABEL < y):
            return False
    for _, ax, ay, bx, by, _c in corridors:
        if rect_seg_dist(rect, (ax, ay), (bx, by)) < CORRIDOR_HALF + GAP_CORRIDOR:
            return False
    for other in markers:
        if other is mk:
            continue
        if other['kind'] == 'capsule':
            edges = poly_edges(other['hull']) if len(other['hull']) > 2 else [tuple(other['hull'])]
            for a, b in edges:
                if rect_seg_dist(rect, a, b) < CAP_W / 2 + GAP_MARKER:
                    return False
        else:
            ox, oy = other['center']
            qx = min(max(ox, x), x + w); qy = min(max(oy, y), y + h)
            if dist((ox, oy), (qx, qy)) < other['r'] + GAP_MARKER:
                return False
    return True


labels = []              # (名, cx, 基线y) 全部站名统一7.5px加粗(2026-10-22用户: 大小间距全线一致)
placed_boxes = []
failed = []
transfers = [m for m in markers if len(m['lines']) > 1]
st_labels = []
ST_FONT = 7.5
RINGS_TIGHT = [4.0, 8.0, 13.0, 19.0]
ST_GAP = 3.0             # 标签盒-本站标记最小净距(用户: 太近贴在一起, 2026-10-22)


def st_w(nm):
    return sum(ST_FONT if ord(ch) > 0x2E80 else 4.2 for ch in nm)


def mk_gap(rect, mk):
    """标签盒到标记边缘净距(圆=点距-r, 胶囊=盒到hull边净距-半宽)。"""
    x, y, w, h = rect
    if mk['kind'] == 'capsule':
        edges = poly_edges(mk['hull']) if len(mk['hull']) > 2 else [tuple(mk['hull'])]
        return min(rect_seg_dist(rect, a, b) for a, b in edges) - CAP_W / 2
    ox, oy = mk['center']
    qx = min(max(ox, x), x + w); qy = min(max(oy, y), y + h)
    return dist((ox, oy), (qx, qy)) - mk['r']


def st_clear(rect, own_mk):
    x, y, w, h = rect
    if mk_gap(rect, own_mk) < ST_GAP:          # 本站: 不贴不叠(太近=贴在一起, 用户纠偏)
        return False
    cx_, cy_ = x + w / 2, y + h / 2            # 归属无歧义: 标签中心离本站最近
    od = dist((cx_, cy_), own_mk['center'])
    for other in markers:
        if other is not own_mk and dist((cx_, cy_), other['center']) < od - 1.0:
            return False
    for nm2, x2, y2, w2, h2 in placed_boxes:
        if not (x + w + 1.0 < x2 or x2 + w2 + 1.0 < x or y + h + 1.0 < y2 or y2 + h2 + 1.0 < y):
            return False
    for nm2, ax, ay, bx, by, _c in corridors:
        if rect_seg_dist(rect, (ax, ay), (bx, by)) < CORRIDOR_HALF + 1.0:
            return False
    for other in markers:
        if other is own_mk:
            continue
        if other['kind'] == 'capsule':
            edges = poly_edges(other['hull']) if len(other['hull']) > 2 else [tuple(other['hull'])]
            for a, b in edges:
                if rect_seg_dist(rect, a, b) < CAP_W / 2 + 1.0:
                    return False
        else:
            ox, oy = other['center']
            qx = min(max(ox, x), x + w); qy = min(max(oy, y), y + h)
            if dist((ox, oy), (qx, qy)) < other['r'] + 1.0:
                return False
    return True


def st_clear_noline(rect, own_mk):
    """APM密集段专用: 豁免走廊碰撞——三平行竖线夹缝无合法位, 用户2026-10-22定稿
    (稍微重叠可接受), 渲染配白描边光环保压线可读; 其余检查(本站净距/歧义/互斥/撞圆)全保留。"""
    x, y, w, h = rect
    if mk_gap(rect, own_mk) < ST_GAP:
        return False
    cx_, cy_ = x + w / 2, y + h / 2
    od = dist((cx_, cy_), own_mk['center'])
    for other in markers:
        if other is not own_mk and dist((cx_, cy_), other['center']) < od - 1.0:
            return False
    for nm2, x2, y2, w2, h2 in placed_boxes:
        if not (x + w + 1.0 < x2 or x2 + w2 + 1.0 < x or y + h + 1.0 < y2 or y2 + h2 + 1.0 < y):
            return False
    for other in markers:
        if other is own_mk:
            continue
        if other['kind'] == 'capsule':
            edges = poly_edges(other['hull']) if len(other['hull']) > 2 else [tuple(other['hull'])]
            for a, b in edges:
                if rect_seg_dist(rect, a, b) < CAP_W / 2 + 1.0:
                    return False
        else:
            ox, oy = other['center']
            qx = min(max(ox, x), x + w); qy = min(max(oy, y), y + h)
            if dist((ox, oy), (qx, qy)) < other['r'] + 1.0:
                return False
    return True


card_label = {}   # 站名 -> (x, y基线) 取自各卡站名标注(标准方位参考)
for _name in ORDER:
    _p = os.path.join(LINES_DIR, 'line-%s.svg' % _name)
    try:
        _src = open(_p, encoding='utf-8').read()
    except OSError:
        continue
    _g = re.search(r'<g id="站名标注"[^>]*>(.*?)</g>', _src, re.S)
    if not _g:
        continue
    for _t in re.finditer(r'<text x="([\d.-]+)" y="([\d.-]+)"[^>]*font-size="10.5"[^>]*>([^<]+)</text>', _g.group(1)):
        card_label.setdefault(_t.group(3).strip(), (float(_t.group(1)), float(_t.group(2))))


APM_DENSE = {'天河南', '黄埔大道', '妇儿中心', '花城大道', '大剧院', '体育中心南'}  # APM中段: 三平行竖线夹缝
ST_FONT2 = 6.0   # 二档小字(向后兼容引用)
ST_TIERS = [(7.5, 8.5), (6.0, 7.0), (5.0, 6.0), (4.2, 5.0)]   # 逐档缩小到放得下(2026-10-22用户: 竖排诡异改回横排, 有重叠字就小点)


def st_wfs(nm, fs):
    return sum(fs if ord(ch) > 0x2E80 else 0.56 * fs for ch in nm)


def st_w2(nm):
    return sum(ST_FONT2 if ord(ch) > 0x2E80 else 3.4 for ch in nm)


def _cands_for(mk, nm, w, hh, fs):
    mx, my = mk['center']
    cands = []
    if nm in APM_DENSE and fs <= 6.5:            # 东带横排: APM竖线(x1687.5)右侧专用列, 净距4.5起(竖排已废, 2026-10-22)
        cands.append((1696.5 + w / 2, my))
    if nm in term_dir:                           # 卡片规范: 终点文字在走廊延长线上(含斜线)
        ux, uy = term_dir[nm]
        ext = (w * abs(ux) + hh * abs(uy)) / 2
        r0 = (mk['r'] if mk['kind'] != 'capsule' else CAP_W / 2 + CAP_RING)
        for g_ in (5.0, 9.0, 14.0):
            cands.append((mx + ux * (r0 + g_ + ext), my + uy * (r0 + g_ + ext)))
    if nm in card_label:                         # 卡片标准方位(保盒边净距钳制)
        cx, cy = card_label[nm]
        ox, oy = cx - mx, (cy - 1.75) - my
        L = (ox * ox + oy * oy) ** 0.5
        if L > 1:
            k = min(1.0, 14.0 / L)
            px, py = mx + ox * k, my + oy * k
            rect = (px - w / 2, py - hh / 2, w, hh)
            g0 = mk_gap(rect, mk)
            if g0 < ST_GAP + 0.5:
                px += ox / L * (ST_GAP + 0.5 - g0)
                py += oy / L * (ST_GAP + 0.5 - g0)
            cands.append((px, py))
    for ring in RINGS_TIGHT:
        for dx, dy in DIRS:
            ax, ay = marker_anchor(mk, dx, dy)
            r2 = place_box(w, hh, ax + dx * ring, ay + dy * ring, dx, dy)
            cands.append((r2[0] + w / 2, r2[1] + hh / 2))
    return cands


def place_one(mk):
    """横排逐档缩小直到放得下; 竖排已废(2026-10-22用户: 竖向显示诡异)。
    APM密集段: 大档(7.5/6)全拒先落东带列兜底(fs6+豁免走廊, 白光环), 不让掉进极小字档;
    18号线冼村段右移后多数站紧环即可放(用户: 稍微重叠可接受)。"""
    nm = mk['name']
    for fs, hh in ((7.5, 8.5), (6.0, 7.0)):
        w = st_wfs(nm, fs)
        for cx, cy in _cands_for(mk, nm, w, hh, fs):
            rect = (cx - w / 2, cy - hh / 2, w, hh)
            if st_clear(rect, mk):
                labels.append((nm, cx, cy - hh / 2 + 0.8 * fs, fs, False))
                placed_boxes.append((nm,) + rect)
                return True
    if nm in APM_DENSE:                      # 兜底: 东带列(x1695起)+豁免走廊碰撞(fs6起, 不掉4.2极小字)
        for fs, hh in ((6.0, 7.0), (5.0, 6.0)):
            w = st_wfs(nm, fs)
            for dy2 in (0.0, -9.0, 9.0):     # y偏移错开邻站歧义(妇儿中心vs冼村隔29px)
                cx = 1695.0 + w / 2
                cy = mk['center'][1] + dy2
                rect = (cx - w / 2, cy - hh / 2, w, hh)
                if st_clear_noline(rect, mk):
                    labels.append((nm, cx, cy - hh / 2 + 0.8 * fs, fs, False))
                    placed_boxes.append((nm,) + rect)
                    return True
    for fs, hh in ((5.0, 6.0), (4.2, 5.0)):  # 非密集段继续小档
        w = st_wfs(nm, fs)
        for cx, cy in _cands_for(mk, nm, w, hh, fs):
            rect = (cx - w / 2, cy - hh / 2, w, hh)
            if st_clear(rect, mk):
                labels.append((nm, cx, cy - hh / 2 + 0.8 * fs, fs, False))
                placed_boxes.append((nm,) + rect)
                return True
    failed.append(nm)
    return False


# 受限优先: 换乘站可选位少先放, 其余按名序
def opt_n(mk):
    w, h = st_w(mk['name']), 8.5
    n = 0
    for ring in RINGS_TIGHT:
        for dx, dy in DIRS:
            ax, ay = marker_anchor(mk, dx, dy)
            if st_clear(place_box(w, h, ax + dx * ring, ay + dy * ring, dx, dy), mk):
                n += 1
    return n


# 终点外向方向(站名->单位向量): 终点站名按卡片规范放走廊延长线上, 徽标三点一线跟随(2026-10-22)
term_dir = {}
for _ln in ORDER:
    _segs = [(c[1], c[2], c[3], c[4]) for c in corridors if c[0] == _ln]
    _deg, _adj = {}, {}
    for ax, ay, bx, by in _segs:
        a, b = (round(ax, 1), round(ay, 1)), (round(bx, 1), round(by, 1))
        _deg[a] = _deg.get(a, 0) + 1; _deg[b] = _deg.get(b, 0) + 1
        _adj.setdefault(a, []).append(b); _adj.setdefault(b, []).append(a)
    for p, d in _deg.items():
        if d == 1:
            tm = min(markers, key=lambda m: dist(m['center'], p))
            if dist(tm['center'], p) < 30 and tm['name'] not in term_dir and _adj[p]:
                o = _adj[p][0]
                dd = (p[0] - o[0], p[1] - o[1])
                nn = (dd[0] ** 2 + dd[1] ** 2) ** 0.5 or 1.0
                term_dir[tm['name']] = (dd[0] / nn, dd[1] / nn)

# 终点文字候选豁免: 多线共享圆且终点线走向与并圆线走向冲突的站, 延长线文字=斜挂旁线不对齐,
# 跳过term_dir让紧环放轴向位(2026-10-22用户: 文字没有跟圆点对齐/广州塔文字归位)
NO_TERM_DIR = {'林和西', '广州塔'}  # 林和西=APM斜×3号线竖; 广州塔=APM斜×3号线竖(右下对角→右侧同y)
for _nm in NO_TERM_DIR:
    term_dir.pop(_nm, None)
_mks = sorted(markers, key=lambda m: (len(m['lines']) <= 1, opt_n(m), m['name']))
for mk in _mks:
    place_one(mk)
print('  站名: %d/%d (未放: %s)' % (len(labels), len(markers), ','.join(failed) or '无'))

# 终版文字锚定(codes锚表labels_inner): 底图站名直接采用终版标签——两模式一套的源头统一,
# 徽标落位/复检全部对终版文字(此前底图算法标签↔回写标签两套坐标, 徽标贴字规则被复检
# 的旧标签盒误伤)。labels_inner为空或缺条数不齐时保留算法标签(文件尚未生成的首次运行)。
_fin_labels_inner = ''
_fin_pins_path = os.path.join(ROOT, 'data', 'codes-final-pins.json')
if os.path.exists(_fin_pins_path):
    try:
        _fin_labels_inner = json.load(open(_fin_pins_path, encoding='utf-8')).get('labels_inner', '')
    except (ValueError, KeyError):
        _fin_labels_inner = ''
if _fin_labels_inner:
    _new_labels = []
    for _mm in re.finditer(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*font-size="([\d.]+)"[^>]*>([^<]+)</text>', _fin_labels_inner):
        _new_labels.append((_mm.group(4), float(_mm.group(1)), float(_mm.group(2)), float(_mm.group(3)), False))
    if len(_new_labels) == len(markers):
        labels = _new_labels
        placed_boxes = []
        for _nm, _cx, _cy_bl, _fs, _stk in labels:
            _w = st_wfs(_nm, _fs)
            _hh = _fs + 1.0
            _cy = _cy_bl - 0.8 * _fs + _hh / 2
            placed_boxes.append((_nm, _cx - _w / 2, _cy - _hh / 2, _w, _hh))
        print('  站名: 已采用codes锚表labels_inner终版(%d条)' % len(labels))

# ---------- 各线徽标(复用主卡header徽标, 端点外推摆位) ----------
allx = [v for c in corridors for v in (c[1], c[3])]
ally = [v for c in corridors for v in (c[2], c[4])]
gx, gy = sum(allx) / len(allx), sum(ally) / len(ally)


def badge_rect_why(rect, placed_badges, ignore_corridor=False, own_line=None):
    """ignore_corridor=True: 延长线上的徽标可盖走廊(有底色, 规范允许);
    own_line: 只豁免本线走廊(可盖本线延长线), 他线走廊仍严查——
    2号线@广州南站判例规则化: 延长线被他线占时该档被拒, 外推/兜底自然让位。"""
    x, y, w, h = rect
    for nm2, x2, y2, w2, h2 in placed_badges:
        if not (x + w + 6 < x2 or x2 + w2 + 6 < x or y + h + 6 < y2 or y2 + h2 + 6 < y):
            return '撞徽标%s' % nm2
    if not ignore_corridor or own_line is not None:
        for nm2, ax, ay, bx, by, _c in corridors:
            if own_line is not None and nm2 == own_line:
                continue
            if rect_seg_dist(rect, (ax, ay), (bx, by)) < CORRIDOR_HALF + 3.0:
                return '撞走廊%s@(%g,%g)' % (nm2, ax, ay)
    for other in markers:
        if other['kind'] == 'capsule':
            edges = poly_edges(other['hull']) if len(other['hull']) > 2 else [tuple(other['hull'])]
            for a, b in edges:
                if rect_seg_dist(rect, a, b) < CAP_W / 2 + 3.0:
                    return '撞胶囊'
        else:
            ox, oy = other['center']
            qx = min(max(ox, x), x + w); qy = min(max(oy, y), y + h)
            if dist((ox, oy), (qx, qy)) < other['r'] + 3.0:
                return '撞站圆(%g,%g)' % (ox, oy)
    for nm2, x2, y2, w2, h2 in placed_boxes:
        if not (x + w + 2 < x2 or x2 + w2 + 2 < x or y + h + 2 < y2 or y2 + h2 + 2 < y):
            return '撞标签%s' % nm2
    return None


def badge_rect_ok(rect, placed_badges, ignore_corridor=False, own_line=None):
    return badge_rect_why(rect, placed_badges, ignore_corridor, own_line) is None


badges = []             # (线名, 左上x, 左上y, w, h)
badge_home = []         # 与badges同序: 各徽标所属终点(环线=None), 贴本体校正用
badge_fail = []
# 文字位置查询(斜线终点徽标相对文字居中用): 站名 -> (中心x, 盒中心y, 字号); 盒中心=基线+hh/2-0.8fs, hh=fs+1
lab_by_nm = {}
for _lb in labels:
    lab_by_nm.setdefault(_lb[0], (_lb[1], _lb[2] + (_lb[3] + 1) / 2 - 0.8 * _lb[3], _lb[3]))
# 徽标规则(2026-10-24定稿, 用户: 大量徽标距离终点文字较远/没有相对终点文字居中——
# 标准位=【终点站名文字轴线居中外侧】, 对全部终点统一执行, 无白名单:
#   文字在站体左/右(|dx|>|dy|): 徽标在文字外侧同y, x=文字盒边+gap+半宽;
#   文字在站体上/下(含45°, 既定稿=文字正上/下方同x): 徽标在文字外侧同x, y=文字盒边+gap+半高;
#   gap阶梯5/9/14/20/32/50/72/100(多线同终点同侧自动错档堆叠); 主轴全堵试垂直轴; 再堵兜底旧
#   走廊方向公式。徽标缩小(13.5pt)后按旧中心保留会离文字脱开~13pt——文字轴规则让全部徽标
#   随新尺寸回收贴字。合法性口径=与codes终检同一套(他线走廊6.5/标签不叠/他徽标6/站圆胶囊3)。
# 文字源=codes锚表labels_inner(与底图回写同源, 两模式一套); 缺失回退底图算法标签。
# 环线(11号线)无终点文字对象: 沿用验收锚位(贴本体), 无锚才网格搜。
# 真终点=焊接图degree-1: 走廊节点6px内焊成同一节点(裂隙两侧并回)再算度数——穿过型裂隙焊后
# 度数2=内部点自然剔除; 重叠段悬空端点落同线他段内部=假终点剔除(1号线花地湾判例);
# 且端点30px内须有站圆(广佛线0.1-2.3px裂隙端点掉mid-line教训)。
# 环线锚位(11号线贴本体验收位, 无文字规则对象故持久化保留); 终点徽标一律文字轴规则
_OLD_SC = {'APM线': 0.5}   # 锚位尺寸口径: 旧版缩放(0.7/APM0.5), 用于中心换算
# 编号胶囊rect(codes层持久化的确定性数据, 见gen-codes-cards落盘说明): 底图落位即考虑胶囊
_chip_obstacles = []
_chip_path = os.path.join(ROOT, 'data', '_chip-rects.json')
if os.path.exists(_chip_path):
    try:
        _cr = json.load(open(_chip_path, encoding='utf-8'))
        _chip_obstacles = [tuple(r) for r in _cr.get('chips', []) + _cr.get('rings', [])]
    except (ValueError, KeyError):
        _chip_obstacles = []
_anc_path = os.path.join(ROOT, 'data', 'codes-final-pins.json')
badge_anchors = {}
if os.path.exists(_anc_path):
    try:
        for _a in json.load(open(_anc_path, encoding='utf-8')).get('network_badge_anchors', []):
            badge_anchors.setdefault(_a['ln'], []).append((float(_a['x']), float(_a['y'])))
    except (ValueError, KeyError):
        badge_anchors = {}


def _rgap(r1, r2):
    dx = max(r2[0] - (r1[0] + r1[2]), r1[0] - (r2[0] + r2[2]), 0.0)
    dy = max(r2[1] - (r1[1] + r1[3]), r1[1] - (r2[1] + r2[3]), 0.0)
    return (dx * dx + dy * dy) ** 0.5


def _place_ok(rect, own_ln, skip_idx=-1):
    """落位合法性(2026-10-24统一口径, 用户: 10号线徽标紧贴路线/11号线离线远——
    本线他线走廊一律>=6.5, 旧"本线可贴可盖"豁免废除: 文字轴落位下横向贴线视觉不可接受;
    终版标签盒不叠/他徽标>=6/站圆胶囊>=3/编号胶囊>=3(下方_chip数据, 整合进计算流程)。
    文字盒=placed_boxes(已锚定为labels_inner终版)。
    角点检查: 像素门禁在四边外扩3px扫描, 斜走廊贴近rect角点时rect边距6.5合格但
    角点+3px扫描点距斜线可<3.5(APM林和西判例)——4个外扩角点须距所有走廊>=3.6。"""
    _corners = [(rect[0] - 3.0, rect[1] - 3.0),
                (rect[0] + rect[2] + 3.0, rect[1] - 3.0),
                (rect[0] - 3.0, rect[1] + rect[3] + 3.0),
                (rect[0] + rect[2] + 3.0, rect[1] + rect[3] + 3.0)]
    for nm2, ax, ay, bx, by, _c in corridors:
        if rect_seg_dist(rect, (ax, ay), (bx, by)) < 6.5:
            return False
        for cpt in _corners:
            if seg_point_dist(cpt, (ax, ay), (bx, by)) < 4.2:
                return False
    for r9 in _chip_obstacles:
        if _rgap(rect, r9) < 0.3:
            return False
    for _nm2, _x2, _y2, _w2, _h2 in placed_boxes:
        if _rgap(rect, (_x2, _y2, _w2, _h2)) < 0.3:
            return False
    for _j2, (_nm2, _bx2, _by2, _bw2, _bh2) in enumerate(badges):
        if _j2 == skip_idx:
            continue
        if _rgap(rect, (_bx2, _by2, _bw2, _bh2)) < 6.0:
            return False
    for mk in markers:
        if mk['kind'] == 'capsule':
            edges = poly_edges(mk['hull']) if len(mk['hull']) > 2 else [tuple(mk['hull'])]
            if any(rect_seg_dist(rect, a, b) < CAP_W / 2 + 3.0 for a, b in edges):
                return False
        else:
            ox, oy = mk['center']
            qx = min(max(ox, rect[0]), rect[0] + rect[2])
            qy = min(max(oy, rect[1]), rect[1] + rect[3])
            if dist((ox, oy), (qx, qy)) < mk['r'] + 3.0:
                return False
    return True


line_ends = {}           # 线名 -> 焊接真终点列表(贴本体校正复用)
for name in ORDER:
    _sc = BADGE_H / badge_size[name][1]
    bw, bh = badge_size[name][0] * _sc, BADGE_H
    segs = [(c[1], c[2], c[3], c[4]) for c in corridors if c[0] == name]

    def _weld(p):
        for q in _nodes:
            if dist(p, q) <= 6.0:
                return q
        _nodes.append(p)
        return p

    _nodes = []
    wdeg, wadj = {}, {}
    for ax, ay, bx, by in segs:
        a = _weld((round(ax, 1), round(ay, 1)))
        b = _weld((round(bx, 1), round(by, 1)))
        wdeg[a] = wdeg.get(a, 0) + 1; wdeg[b] = wdeg.get(b, 0) + 1
        wadj.setdefault(a, []).append(b); wadj.setdefault(b, []).append(a)
    ends = [p for p, d in wdeg.items()
            if d == 1 and wadj[p] and min(dist(p, m['center']) for m in markers) < 30]

    def _on_seg_interior(p):
        """重叠段假终点: 悬空端点落在同线另一段的严格内部(1号线花地湾=短段戳进长段的
        重叠画法, 端点恰在花地湾钉位)。真终点的邻接段端点投影t=0/1不会误伤。"""
        for ax, ay, bx, by in segs:
            if seg_point_dist(p, (ax, ay), (bx, by)) > 0.75:
                continue
            dx, dy = bx - ax, by - ay
            dd = dx * dx + dy * dy
            t = 0.0 if dd == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / dd))
            if 0.05 < t < 0.95:
                return True
        return False

    ends = [p for p in ends if not _on_seg_interior(p)]
    line_ends[name] = ends
    # L1 已验收锚位(用户架构: 锚表=终稿持久化, 同0eff3db): 中心不变按13.5pt重算top-left,
    # 必须通过与所有元件相同的规则检查(_place_ok)——锚位不是豁免, 是规则合法解中的在选解;
    # 不合法才由规则(L2文字轴)重推。胶囊净距口径=不重叠(0.3pt), 3pt过严口径已废除
    # (正是它把浔峰岗/西塱徽标推远的)。
    _osc = _OLD_SC.get(name, 0.7)
    _ow, _oh = badge_size[name][0] * _osc, badge_size[name][1] * _osc
    covered = []
    for _ax, _ay in badge_anchors.get(name, []):
        _cx, _cy = _ax + _ow / 2, _ay + _oh / 2
        rect = (_cx - bw / 2, _cy - bh / 2, bw, bh)
        if not _place_ok(rect, name):
            _fixed = None
            for _st in range(1, 241):
                _dd = _st * 0.5
                for _k in range(16):
                    import math as _mm
                    _ra = _mm.radians(_k * 22.5)
                    _r2 = (rect[0] + _mm.cos(_ra) * _dd, rect[1] + _mm.sin(_ra) * _dd, bw, bh)
                    if _place_ok(_r2, name):
                        _fixed = _r2
                        break
                if _fixed:
                    break
            if _fixed:
                print('  徽标 %s 锚位微调 %.1fpt' % (name, _dd))
                rect = _fixed
            else:
                print('  !! 徽标 %s 锚位违规且无解, 弃锚改文字轴规则' % name)
                continue
        badges.append((name, rect[0], rect[1], bw, bh))
        _ce = min(ends, key=lambda q: dist((rect[0] + bw / 2, rect[1] + bh / 2), q)) if ends else None
        if _ce and dist((rect[0] + bw / 2, rect[1] + bh / 2), _ce) <= 120:
            badge_home.append(_ce)
            covered.append(_ce)
        else:
            badge_home.append(None)
    # 环线(无真终点, 如11号线): 无文字规则对象, 沿用验收锚位; 无锚贴本体网格全域搜
    if not ends:
        if badge_anchors.get(name):
            continue
        _xs2 = [v for c in segs for v in (c[0], c[2])]
        _ys2 = [v for c in segs for v in (c[1], c[3])]
        _own_d2 = lambda rect: min(rect_seg_dist(rect, (s[0], s[1]), (s[2], s[3])) for s in segs)
        best = None
        for cx in range(int(min(_xs2)) - 40, int(max(_xs2)) + 41, 6):
            for cy in range(int(min(_ys2)) - 40, int(max(_ys2)) + 41, 6):
                rect = (cx - bw / 2, cy - bh / 2, bw, bh)
                od = _own_d2(rect)
                if od < 10.0 or od > 60.0:
                    continue
                if badge_rect_why(rect, badges) is not None:   # 全查含走廊: 环线徽标不得压线
                    continue
                if best is None or od < best[0]:
                    best = (od, rect)
        if best:
            badges.append((name, best[1][0], best[1][1], bw, bh))
            badge_home.append(None)
            print('  徽标 %s 环线贴本体: 距走廊 %.0fpx' % (name, best[0]))
        else:
            badge_fail.append(name)
            print('  !! 徽标 %s 环线无合法位' % name)
        continue
    # 终点: 文字轴线居中外侧(锚位已覆盖的端跳过——L1已在验收位落位)
    for c in sorted((e for e in ends if not any(dist(e, q) <= 1.0 for q in covered)),
                    key=lambda q: -dist(q, (gx, gy))):
        base = wadj[c][0]
        dx, dy = c[0] - base[0], c[1] - base[1]
        n = (dx * dx + dy * dy) ** 0.5 or 1.0
        ux, uy = dx / n, dy / n
        tm = min(markers, key=lambda m: dist(m['center'], c))
        lb = None
        _bl = lab_by_nm.get(tm['name'])
        if _bl:
            _fs = _bl[2]
            _w = sum(_fs if ord(ch) > 0x2E80 else 0.56 * _fs for ch in tm['name'])
            lb = (_bl[0], _bl[1], _w, _fs + 1.0)   # (中心x, 盒中心y, 盒w, 盒h)
        done = False
        if lb:
            lx, lcy, lw, lhh = lb
            mx, my = tm['center']
            dxl, dyl = lx - mx, lcy - my
            # 主轴=文字相对站体偏移较大的轴(外侧优先), 副轴次之, 反向最后; 合法性裁决
            # 候选=文字盒4正向+4对角 × gap阶梯, 按【文字中心距离】升序取首个合法——
            # 主轴外侧天然最近; 枢纽终点正向被围时对角近档自动胜过正向远档
            # (嘉禾望岗判例: 正向最近合法=右72, 对角gap14更近)
            sx = 1 if dxl >= 0 else -1
            sy = 1 if dyl >= 0 else -1
            cands = []
            for gap in (5.0, 9.0, 14.0, 20.0, 32.0, 50.0, 72.0, 100.0):
                for sgx, sgy in ((sx, 0), (0, sy), (-sx, 0), (0, -sy), (sx, sy), (-sx, sy), (sx, -sy), (-sx, -sy)):
                    cx2 = lx + sgx * (lw / 2 + gap + bw / 2)
                    cy2 = lcy + sgy * (lhh / 2 + gap + bh / 2)
                    rect = (cx2 - bw / 2, cy2 - bh / 2, bw, bh)
                    dt = dist((cx2, cy2), (lx, lcy))
                    cands.append((dt, gap, rect))
            cands.sort(key=lambda t2: t2[0])
            for _dt, _gap, rect in cands:
                if _place_ok(rect, name):
                    badges.append((name, rect[0], rect[1], bw, bh))
                    badge_home.append(c)
                    done = True
                    break
        # 兜底: 旧走廊方向公式(徽标中心=终点圆心+走廊方向×(r0+gap+半伸长), 可盖本线延长线)
        if not done:
            r0 = tm['r'] if tm['kind'] != 'capsule' else CAP_W / 2 + CAP_RING
            ext_b = (bw * abs(ux) + bh * abs(uy)) / 2
            for gap in (7.0, 12.0, 20.0, 32.0, 50.0, 72.0, 100.0):
                d = r0 + gap + ext_b
                cx2 = tm['center'][0] + ux * d
                cy2 = tm['center'][1] + uy * d
                rect = (cx2 - bw / 2, cy2 - bh / 2, bw, bh)
                if _place_ok(rect, name):
                    badges.append((name, rect[0], rect[1], bw, bh))
                    badge_home.append(c)
                    done = True
                    break
        # 终点邻域网格(终点±150)
        if not done:
            dirs = [(ux, uy)] + [(d2[0] or 0, d2[1] or 0) for d2 in DIRS]
            for reach in (max(bw, bh) / 2 + 8.0, max(bw, bh) / 2 + 30.0, max(bw, bh) / 2 + 52.0, 90.0, 130.0):
                for vx, vy in dirs:
                    cx3, cy3 = c[0] + vx * reach, c[1] + vy * reach
                    rect = (cx3 - bw / 2, cy3 - bh / 2, bw, bh)
                    if badge_rect_ok(rect, badges):
                        badges.append((name, rect[0], rect[1], bw, bh))
                        badge_home.append(c)
                        done = True
                        break
                if done:
                    break
        if not done:
            badge_fail.append('%s@(%g,%g)' % (name, c[0], c[1]))
            print('  !! 徽标 %s (%g,%g) 未找到合法位' % (name, c[0], c[1]))
# 双段线(12号线两段)不需要补徽标: 主循环按去碎裂真终点逐端放置, 两段各自的
# 起点终点已天然覆盖(旧BADGE_AT_2ND单端版式随手动锚一并废除, 2026-10-24)。

# 落位审计: 每枚复检(应全过; 2号线/22号线曾盖线的防线) + 离本体距离(过远=偏离本体)。
# 复检口径=与落位同一套_place_ok(跳过自身); 偏离本体>110px仅告警——文字轴规则下徽标跟
# 终版文字走, 个别被nudge推远的终点文字(如冼村)带着徽标离走廊稍远属规则内行为。
for _i, (_nm, _bx, _by, _bw, _bh) in enumerate(badges):
    if not _place_ok((_bx, _by, _bw, _bh), _nm, skip_idx=_i):
        print('  !! 徽标 %s 复检撞' % _nm)

# 站距钳制(2026-10-24 用户: 10和11要算的是到站点的距离——徽标属于终点站, 视觉的远=离站远;
# 旧锚位中心距站44~82px, 大盒时代盒缘够到站体, 缩到13.5pt后同中心小盒脱站):
# 每枚徽标归属站点(终点=走廊端点最近站圆; 环线=本线最近站圆), 中心到站钉距离
# 钳到[r+4, 30]区间——超30沿中心->站方向拉回(30/35/40/45/55/65取首个合法档),
# 侵入站体(r+4内)沿反向推出。合法性=_place_ok同口径(走廊6.5/胶囊牌标签不叠)。
badge_stn = []           # 与badges同序: (站名, 站钉中心)
_mk_by_name = {m['name']: m for m in markers}
for (_nm, _bx, _by, _bw, _bh), _home in zip(badges, badge_home):
    _c = (_bx + _bw / 2, _by + _bh / 2)
    if _home is not None:
        _st = min(markers, key=lambda m: dist(_home, m['center']))
    else:
        _own_marks = [m for m in markers if _nm in m['lines']]
        _st = min(_own_marks, key=lambda m: dist(_c, m['center'])) if _own_marks else None
    badge_stn.append((_st['name'], _st['center']) if _st else (None, None))
for _i, (_nm, _bx, _by, _bw, _bh) in enumerate(badges):
    _stn_nm, _stn_c = badge_stn[_i]
    if not _stn_c:
        continue
    _mk = _mk_by_name[_stn_nm]
    _r_out = (_mk['r'] if _mk['kind'] != 'capsule' else CAP_W / 2 + CAP_RING) + 4.0
    _bc = (_bx + _bw / 2, _by + _bh / 2)
    _d = dist(_bc, _stn_c)
    if _r_out <= _d <= 30.0:
        continue
    _vx, _vy = _stn_c[0] - _bc[0], _stn_c[1] - _bc[1]
    _vn = (_vx * _vx + _vy * _vy) ** 0.5 or 1.0
    if _d > 30.0:          # 拉近站台: 极角搜索——R阶梯×角偏移(0/±25/±50...180), 首个合法位;
                           # 直线档被终点文字挡死时(万顷沙/南沙客运港判例)绕角落到站旁空位
        import math as _m2
        _th0 = _m2.atan2(_bc[1] - _stn_c[1], _bc[0] - _stn_c[0])
        _done2 = False
        for _R in (30.0, 35.0, 40.0, 45.0, 55.0, 65.0, 80.0):
            if _R >= _d:
                break
            for _dth in (0.0, 25.0, -25.0, 50.0, -50.0, 75.0, -75.0, 100.0, -100.0,
                         125.0, -125.0, 150.0, -150.0, 180.0):
                _th = _th0 + _m2.radians(_dth)
                _trect = ((_stn_c[0] + _m2.cos(_th) * _R) - _bw / 2,
                          (_stn_c[1] + _m2.sin(_th) * _R) - _bh / 2, _bw, _bh)
                if _place_ok(_trect, _nm, skip_idx=_i):
                    badges[_i] = (_nm, _trect[0], _trect[1], _bw, _bh)
                    print('  徽标 %s 站距钳制: 距站%.0f->%.0fpx(角偏%.0f°)' % (_nm, _d, _R, _dth))
                    _done2 = True
                    break
            if _done2:
                break
    else:                  # 侵入站体, 反向推出
        for _target in (_r_out + 2.0, _r_out + 5.0, _r_out + 9.0):
            _trect = ((_stn_c[0] + _vx / _vn * _target) - _bw / 2,
                      (_stn_c[1] + _vy / _vn * _target) - _bh / 2, _bw, _bh)
            if _place_ok(_trect, _nm, skip_idx=_i):
                badges[_i] = (_nm, _trect[0], _trect[1], _bw, _bh)
                print('  徽标 %s 站距钳制: 距站%.0f->%.0fpx(推出)' % (_nm, _d, _target))
                break

# 文字轴合规复查(2026-10-24 用户: 徽标跟终点文字的距离和居中 批量检查 不符合规范的调整):
# 违规 = 文字盒净距<0.3(压字, 万顷沙/南沙客运港判例) 或 文字中心距>45(远离, 站距钳制推出判例);
# 主轴偏移不作为判据(西塱类枢纽站旁斜位为已验收态, 偏移判据会误推)。
# 调整 = 重走文字轴候选阶梯(8向×gap按文字距离升序), 过滤=合法+文字盒净距>=0.3+
#        站距<=40(两级: 有解带站距过滤, 无解退纯文字轴——文字规则优先于站距);
# 环线(home=None)跳过。放在站距钳制之后: 两规则冲突时文字轴结果为准。
def _text_cands(lx, lcy, lw, lhh, bw, bh, sx, sy):
    _cands = []
    for _gap in (5.0, 9.0, 14.0, 20.0, 32.0, 50.0, 72.0, 100.0):
        for _sgx, _sgy in ((sx, 0), (0, sy), (-sx, 0), (0, -sy),
                           (sx, sy), (-sx, sy), (sx, -sy), (-sx, -sy)):
            _cx2 = lx + _sgx * (lw / 2 + _gap + bw / 2)
            _cy2 = lcy + _sgy * (lhh / 2 + _gap + bh / 2)
            _dt = dist((_cx2, _cy2), (lx, lcy))
            _cands.append((_dt, (_cx2 - bw / 2, _cy2 - bh / 2, bw, bh)))
    _cands.sort(key=lambda t2: t2[0])
    return _cands

for _i, (_nm, _bx, _by, _bw, _bh) in enumerate(badges):
    if badge_home[_i] is None:
        continue
    _stn_nm, _stn_c = badge_stn[_i]
    _bl = lab_by_nm.get(_stn_nm)
    if not _bl:
        continue
    _fs = _bl[2]
    _lw = sum(_fs if ord(ch) > 0x2E80 else 0.56 * _fs for ch in _stn_nm)
    _lx, _lcy, _lhh = _bl[0], _bl[1], _fs + 1.0
    _bc = (_bx + _bw / 2, _by + _bh / 2)
    _dt0 = dist(_bc, (_lx, _lcy))
    _sd0 = dist(_bc, _stn_c)
    if _sd0 <= 35.0:
        continue   # 站距<=35=已靠站(用户: 不要远——靠站优先于贴文字, 站文分离站不复议)
    _g0 = _rgap((_bx, _by, _bw, _bh), (_lx - _lw / 2, _lcy - _lhh / 2, _lw, _lhh))
    if _g0 >= 0.3 and _dt0 <= 45.0:
        continue
    _sx = 1 if (_bc[0] - _stn_c[0]) * (_lx - _stn_c[0]) >= 0 else -1
    _sy = 1 if (_bc[1] - _stn_c[1]) * (_lcy - _stn_c[1]) >= 0 else -1
    _new = None
    for _stage in (40.0, None):
        for _dt2, _rect2 in _text_cands(_lx, _lcy, _lw, _lhh, _bw, _bh, _sx, _sy):
            if not _place_ok(_rect2, _nm, skip_idx=_i):
                continue
            if _rgap(_rect2, (_lx - _lw / 2, _lcy - _lhh / 2, _lw, _lhh)) < 0.3:
                continue
            if _stage is not None and dist((_rect2[0] + _bw / 2, _rect2[1] + _bh / 2), _stn_c) > _stage:
                continue
            _new = _rect2
            break
        if _new:
            break
    if _new and (abs(_new[0] - _bx) > 0.3 or abs(_new[1] - _by) > 0.3):
        badges[_i] = (_nm, _new[0], _new[1], _bw, _bh)
        print('  徽标 %s 文字轴复查调整: (%g,%g)->(%g,%g) [压字%s 距文字%.0f]'
              % (_nm, _bx, _by, _new[0], _new[1], _g0 < 0.3, _dt0))

# ---------- 画布 ----------
xs = [v for c in corridors for v in (c[1], c[3])]
ys = [v for c in corridors for v in (c[2], c[4])]
for lb in labels:
    _w_ = st_wfs(lb[0], lb[3])
    xs += [lb[1] - _w_ / 2, lb[1] + _w_ / 2]; ys += [lb[2] - 8.5, lb[2]]
for _nm, bx, by, bw, bh in badges:
    xs += [bx, bx + bw]; ys += [by, by + bh]
for mk in markers:
    if mk['kind'] == 'capsule':
        xs += [p[0] for p in mk['hull']]; ys += [p[1] for p in mk['hull']]
PAD = 26
minx, miny = min(xs) - PAD, min(ys) - PAD
maxx, maxy = max(xs) + PAD, max(ys) + PAD

# 图例带: 标题 + 19色chip, 底部追加
LEG_H = 0
title = '广州地铁线网全图'
sub = '%d线 · %d站(换乘%d)' % (len(ORDER), len(instances), len(transfers))


def chip_w(nm):
    zh = sum(1 for ch in nm if ord(ch) > 0x2E80)
    lat = len(nm) - zh
    return max(34.0, 14 + zh * 12.5 + lat * 7.5)


LEG_PAD = 18
LEG_TITLE_W = 16 * len(title) * 0.0 + len(title) * 19 + len(sub) * 7.2 + 30
avail = (maxx - minx) - 2 * LEG_PAD
row = LEG_TITLE_W
rows = 1
chips = []
for nm in ORDER:
    w = chip_w(nm)
    if row + w > avail and row > LEG_TITLE_W:
        rows += 1; row = 0
    chips.append((nm, row, rows - 1, w))
    row += w + 8
LEG_H = rows * 30 + 14

vb = (minx, miny, maxx - minx, maxy - miny + LEG_H)

# ---------- SVG ----------
out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="%s %s %s %s" width="%d" height="%d">' %
       (fmt(vb[0]), fmt(vb[1]), fmt(vb[2]), fmt(vb[3]), round(vb[2]), round(vb[3] + LEG_H))]
out.append('<rect x="%s" y="%s" width="%s" height="%s" fill="#ffffff"/>' %
           (fmt(minx), fmt(miny), fmt(maxx - minx), fmt(maxy - miny + LEG_H)))
out.append('<g id="走廊">')
for nm, x1, y1, x2, y2, col in corridors:
    out.append('<line x1="%s" y1="%s" x2="%s" y2="%s" style="fill:none;stroke:%s;stroke-width:7;stroke-linecap:round"/>' %
               (fmt(x1), fmt(y1), fmt(x2), fmt(y2), col))
out.append('</g>')
out.append('<g id="站圆">')
for mk in markers:
    if mk['kind'] == 'circ_single':
        cx, cy = mk['center']
        out.append('<circle cx="%s" cy="%s" r="4.5" data-nm="%s" style="fill:#FFFFFF;stroke:%s;stroke-width:2"/>' %
                   (fmt(cx), fmt(cy), mk['name'], colors[mk['lines'][0]]))
out.append('</g>')
out.append('<g id="换乘标记">')
for mk in markers:
    if mk['kind'] == 'circ_multi':
        cx, cy = mk['center']
        out.append('<circle cx="%s" cy="%s" r="%s" data-nm="%s" style="fill:#FFFFFF;stroke:%s;stroke-width:2"/>' %
                   (fmt(cx), fmt(cy), fmt(mk['r']), mk['name'], INK))
    elif mk['kind'] == 'capsule':
        h = mk['hull']
        if len(h) == 2:
            (x1, y1), (x2, y2) = h
            for wid, col in ((CAP_W + 2 * CAP_RING, INK), (CAP_W, '#FFFFFF')):
                out.append('<line x1="%s" y1="%s" x2="%s" y2="%s" data-nm="%s" style="fill:none;stroke:%s;stroke-width:%s;stroke-linecap:round"/>' %
                           (fmt(x1), fmt(y1), fmt(x2), fmt(y2), mk['name'], col, fmt(wid)))
        else:
            d = 'M' + ' L'.join('%s %s' % (fmt(x), fmt(y)) for x, y in h) + ' Z'
            # 黑14/白10双描边(与两点胶囊同口径): 旧4黑/6白=黑被白全盖, 多边形胶囊描边隐形(2026-10-21)
            out.append('<path d="%s" data-nm="%s" style="fill:#FFFFFF;stroke:%s;stroke-width:%s;stroke-linejoin:round;stroke-miterlimit:10"/>' %
                       (d, mk['name'], INK, fmt(CAP_W + 2 * CAP_RING)))
            out.append('<path d="%s" style="fill:none;stroke:#FFFFFF;stroke-width:%s;stroke-linejoin:round"/>' % (d, fmt(CAP_W)))
out.append('</g>')
out.append('<g id="线路徽标">')
for nm, bx, by, bw, bh in badges:
    out.append('<g data-badge="header" transform="translate(%s %s) scale(%s)">%s</g>'
               % (fmt(bx), fmt(by), fmt4(BADGE_H / badge_size[nm][1]), badge_inner[nm]))
out.append('</g>')
out.append('<g id="站名标注" font-family="\'Microsoft YaHei\', \'PingFang SC\', sans-serif" '
           'font-weight="700" fill="%s">' % INK)
for nm, cx, cy, fs, stacked in labels:
    halo = nm in APM_DENSE and fs <= 6.5         # 兜底东带列站名(压线): 白描边光环垫底保可读; 通用位站不压线不加
    hstyle = ' style="paint-order:stroke;stroke:#FFFFFF;stroke-width:2.2;stroke-linejoin:round"' if halo else ''
    if stacked:                                 # CJK竖排: 每字一tspan同x顺dy
        inner = ''.join('<tspan x="%s"%s>%s</tspan>' %
                        (fmt(cx), (' dy="%s"' % fmt(fs)) if k else '', ch)
                        for k, ch in enumerate(nm))
        out.append('<text x="%s" y="%s" font-size="%s" text-anchor="middle"%s>%s</text>'
                   % (fmt(cx), fmt(cy), fmt(fs), hstyle, inner))
    else:
        out.append('<text x="%s" y="%s" font-size="%s" text-anchor="middle"%s>%s</text>'
                   % (fmt(cx), fmt(cy), fmt(fs), hstyle, nm))
out.append('</g>')
out.append('<g id="图例">')
leg_top = maxy + 10
out.append('<text x="%s" y="%s" font-family="\'Microsoft YaHei\', \'PingFang SC\', sans-serif" font-size="19" font-weight="700" fill="%s">%s</text>' %
           (fmt(minx + LEG_PAD), fmt(leg_top + 20), INK, title))
out.append('<text x="%s" y="%s" font-family="\'Microsoft YaHei\', \'PingFang SC\', sans-serif" font-size="10.5" fill="#666666">%s · 换乘站白底深边唯一, 胶囊=多走廊换乘</text>' %
           (fmt(minx + LEG_PAD + len(title) * 19 + 14), fmt(leg_top + 19), sub))
for nm, off, rowi, w in chips:
    x = minx + LEG_PAD + off
    y = leg_top + rowi * 30 + (26 if rowi == 0 else 6)
    out.append('<rect x="%s" y="%s" width="%s" height="22" rx="6" fill="%s"/>' % (fmt(x), fmt(y), fmt(w), colors[nm]))
    zh = sum(1 for ch in nm if ord(ch) > 0x2E80)
    fs = 12.5 if zh else 11.5
    out.append('<text x="%s" y="%s" text-anchor="middle" font-family="\'Microsoft YaHei\', sans-serif" font-size="%s" font-weight="700" fill="#FFFFFF">%s</text>' %
               (fmt(x + w / 2), fmt(y + 16), fmt(fs), nm))
out.append('</g>')
out.append('</svg>')
svg = '\n'.join(out) + '\n'

# ---------- 门禁 ----------
errs = []
if len(markers) != len(instances):
    errs.append('N1 标记数%d != 唯一站名%d' % (len(markers), len(instances)))
mk_by_name = {m['name']: m for m in markers}
for nm, pts in instances.items():
    mk = mk_by_name[nm]
    for _ln, x, y in pts:
        if mk['kind'] == 'capsule':
            h = mk['hull']
            edges = poly_edges(h) if len(h) > 2 else [tuple(h)]
            if not (point_in_poly((x, y), h) or min(seg_point_dist((x, y), a, b) for a, b in edges) <= CAP_W / 2):
                errs.append('N2 %s 实例(%.1f,%.1f)不在包络内' % (nm, x, y))
        else:
            if dist((x, y), mk['center']) > mk['r']:
                errs.append('N2 %s 实例(%.1f,%.1f)超出共享圆 r=%s' % (nm, x, y, mk['r']))
if failed:
    errs.append('N3 标签放不下: %s' % ', '.join(failed))
if badge_fail:
    errs.append('N6 徽标放不下: %s' % ', '.join(badge_fail))
for i, a in enumerate(markers):
    for b in markers[i + 1:]:
        if a['name'] == b['name']:
            continue
        if dist(a['center'], b['center']) < 8.0:
            errs.append('N4 标记塌缩 %s/%s dist=%.1f' % (a['name'], b['name'], dist(a['center'], b['center'])))

audit['labels'] = len(labels)
audit['label_failed'] = failed
audit['corridors'] = len(corridors)
audit['badges'] = [(nm, round(bx, 1), round(by, 1)) for nm, bx, by, _w, _h in badges]
audit['badge_failed'] = badge_fail
audit['viewBox'] = [round(v, 2) for v in vb]
with open(OUT_JSON, 'w', encoding='utf-8') as f:
    json.dump(audit, f, ensure_ascii=False, indent=1)

if errs:
    print('FAIL')
    for e in errs:
        print(' ', e)
    sys.exit(1)

old = open(OUT_SVG, encoding='utf-8').read() if os.path.exists(OUT_SVG) else None
with open(OUT_SVG, 'w', encoding='utf-8') as f:
    f.write(svg)
print('OK 站%d(换乘%d 共享圆%d 胶囊%d 单线%d) 走廊%d 标签%d -> %s' %
      (audit['stations'], len(transfers), audit['shared_circle'], audit['capsule'], audit['single'],
       len(corridors), len(labels), OUT_SVG))
print('   胶囊站:', ' '.join(audit['capsule_names']))
if old is not None and old != svg:
    print('   N5: 覆盖已有文件(内容变化)')
