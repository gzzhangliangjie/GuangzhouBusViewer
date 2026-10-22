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
BADGE_SCALE = 0.7        # 徽标整体缩放(用户: 全部调小+2/22号线曾盖线, 2026-10-22)
BADGE_SCALE_BY = {'APM线': 0.5}  # 单线再缩: APM原生102x43全图最宽, 0.7仍71px(用户: 再缩小点, 2026-10-22)
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

# ---------- 各线徽标(复用主卡header徽标, 端点外推摆位) ----------
allx = [v for c in corridors for v in (c[1], c[3])]
ally = [v for c in corridors for v in (c[2], c[4])]
gx, gy = sum(allx) / len(allx), sum(ally) / len(ally)


def badge_rect_why(rect, placed_badges, ignore_corridor=False):
    """ignore_corridor=True: 延长线上的徽标可盖走廊(有底色, 规范允许)"""
    x, y, w, h = rect
    for nm2, x2, y2, w2, h2 in placed_badges:
        if not (x + w + 6 < x2 or x2 + w2 + 6 < x or y + h + 6 < y2 or y2 + h2 + 6 < y):
            return '撞徽标%s' % nm2
    if not ignore_corridor:
        for nm2, ax, ay, bx, by, _c in corridors:
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


def badge_rect_ok(rect, placed_badges, ignore_corridor=False):
    return badge_rect_why(rect, placed_badges, ignore_corridor) is None


badges = []             # (线名, 左上x, 左上y, w, h)
badge_fail = []
# 文字位置查询(斜线终点徽标相对文字居中用): 站名 -> (中心x, 盒中心y, 字号); 盒中心=基线+hh/2-0.8fs, hh=fs+1
lab_by_nm = {}
for _lb in labels:
    lab_by_nm.setdefault(_lb[0], (_lb[1], _lb[2] + (_lb[3] + 1) / 2 - 0.8 * _lb[3], _lb[3]))
BADGE_AT = {
    # 手动锚点=用户验收终稿位, 不得删除(2026-10-22教训: 删锚后引擎重放全回到错误位)
    '7号线': [(2100, 686.2)],  # 燕山端延长线(用户: 放另一个终点燕山, 2026-10-22; 旧美的大道端锚废弃)
    '广佛线': [(949, 1604)],
    '1号线': [(1064, 1310), (1072, 1318)],
    '10号线': [(1062, 1225), (1055, 1235)],
    '22号线': [(1845, 1705)],  # 番禺广场下方空位(用户: 放下方更贴线, 2026-10-22; 避18号线斜线x-y=200.25)
    'APM线': [(1700, 1120)],  # 广州塔右下空位(用户: 移到右边空位置, 2026-10-22; 旧(1620,1100)广州塔西侧废弃)
    '12号线': [(1928, 1401.8)],  # 终点大学城南胶囊正左侧同y(用户: 要在终点大学城旁边, 2026-10-22; 中段左移版废弃)
    '2号线': [(1388, 1524)],  # 直线段上方(用户2026-10-23: 7号线下移让位, 2号线2995直线直通)
    '3号线': [(1498.5, 52.7)],  # 机场北端延长线(用户: 海傍端下面有点挤, 2026-10-22)
}
for name in ORDER:
    _sc = BADGE_SCALE_BY.get(name, BADGE_SCALE)
    bw, bh = badge_size[name][0] * _sc, badge_size[name][1] * _sc
    done = False
    for cx, cy in BADGE_AT.get(name, []):
        rect = (cx - bw / 2, cy - bh / 2, bw, bh)
        why = badge_rect_why(rect, badges, ignore_corridor=True)
        if why is None:
            badges.append((name, rect[0], rect[1], bw, bh))
            done = True
            break
        print('  BADGE_AT %s (%g,%g) 拒: %s' % (name, cx, cy, why))
    if done:
        continue
    segs = [(c[1], c[2], c[3], c[4]) for c in corridors if c[0] == name]
    deg, adj = {}, {}
    for ax, ay, bx, by in segs:
        a, b = (round(ax, 1), round(ay, 1)), (round(bx, 1), round(by, 1))
        deg[a] = deg.get(a, 0) + 1; deg[b] = deg.get(b, 0) + 1
        adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a)
    # 端点必须邻近站圆(真终点), 剔除走廊碎裂假端点(广佛线曾因0.1-2.3px裂隙端点掉mid-line)
    ends = [p for p, d in deg.items()
            if d == 1 and min(dist(m['center'], p) for m in markers) < 30]
    # 环线(无真终点, 如11号线): 不走终点公式(会落到任意节点旁压线), 贴本体网格全域搜
    # 最近合法位(用户: 环线大把位置, 华景路/赤沙-龙潭段旁均可, 2026-10-22)
    if not ends:
        _xs2 = [v for c in segs for v in (c[0], c[2])]
        _ys2 = [v for c in segs for v in (c[1], c[3])]
        _own_d2 = lambda rect: min(rect_seg_dist(rect, (s[0], s[1]), (s[2], s[3])) for s in segs)
        best = None
        for cx in range(int(min(_xs2)) - 40, int(max(_xs2)) + 41, 6):
            for cy in range(int(min(_ys2)) - 40, int(max(_ys2)) + 41, 6):
                rect = (cx - bw / 2, cy - bh / 2, bw, bh)
                od = _own_d2(rect)
                if od < 6.5 or od > 60.0:
                    continue
                if badge_rect_why(rect, badges) is not None:   # 全查含走廊: 环线徽标不得压线
                    continue
                if best is None or od < best[0]:
                    best = (od, rect)
        if best:
            badges.append((name, best[1][0], best[1][1], bw, bh))
            print('  徽标 %s 环线贴本体: 距走廊 %.0fpx' % (name, best[0]))
            continue
    # 斜线终点(45°±6°, 0.64<|ux|<0.77): 徽标相对文字居中——文字正上/正下方同x(海傍卡版式),
    # 不沿斜线斜推(2026-10-22用户: 斜向延长线上的徽标需要放在相对文字居中的位置)
    for p in sorted(ends or deg, key=lambda q: -dist(q, (gx, gy))):
        others = adj[p]
        if not others:
            continue
        base = others[0]
        dx, dy = p[0] - base[0], p[1] - base[1]
        n = (dx * dx + dy * dy) ** 0.5 or 1.0
        ux, uy = dx / n, dy / n
        if 0.64 < abs(ux) < 0.77:
            tm = min(markers, key=lambda m: dist(m['center'], p))
            lb = lab_by_nm.get(tm['name'])
            if lb:
                y_lab = lb[1]
                for gap in (7.0, 12.0, 20.0):
                    d = (lb[2] + 1) / 2 + gap + bh / 2
                    cy2 = y_lab + (1 if uy > 0 else -1) * d
                    rect = (lb[0] - bw / 2, cy2 - bh / 2, bw, bh)
                    if badge_rect_ok(rect, badges):     # 不ignore走廊: 居中位不得压任何线
                        badges.append((name, rect[0], rect[1], bw, bh))
                        done = True
                        break
                if done:
                    break
    if done:
        continue
    # 纯规范策略(2026-10-22用户终审定稿): 徽标中心=终点圆心+走廊方向×(r+gap+徽标半伸长), 三点一线
    # 不依赖文字位置/无回退链/ignore_corridor(有底色); 仅撞徽标/撞标签时试另一终点
    for p in sorted(ends or deg, key=lambda q: -dist(q, (gx, gy))):
        others = adj[p]
        if not others:
            continue
        base = others[0]
        dx, dy = p[0] - base[0], p[1] - base[1]
        n = (dx * dx + dy * dy) ** 0.5 or 1.0
        ux, uy = dx / n, dy / n
        tm = min(markers, key=lambda m: dist(m['center'], p))
        r0 = tm['r'] if tm['kind'] != 'capsule' else CAP_W / 2 + CAP_RING
        ext_b = (bw * abs(ux) + bh * abs(uy)) / 2          # 徽标沿方向的半伸长
        for gap in (7.0, 12.0, 20.0, 32.0, 50.0, 72.0, 100.0):
            d = r0 + gap + ext_b
            cx2 = tm['center'][0] + ux * d
            cy2 = tm['center'][1] + uy * d
            rect = (cx2 - bw / 2, cy2 - bh / 2, bw, bh)
            if badge_rect_ok(rect, badges, ignore_corridor=True):
                badges.append((name, rect[0], rect[1], bw, bh))
                done = True
                break
        if done:
            break
    if done:
        continue
    # 兜底: 终点延长线全部被徽标/标签占时, 贴本体网格(终点±150)
    cand = sorted(ends or deg, key=lambda p: -dist(p, (gx, gy)))[:6]
    for p in cand:
        others = adj[p]
        base = others[0] if others else (gx, gy)
        dx, dy = p[0] - base[0], p[1] - base[1]
        n = (dx * dx + dy * dy) ** 0.5 or 1.0
        ux, uy = dx / n, dy / n
        dirs = [(ux, uy)] + [(d2[0] or 0, d2[1] or 0) for d2 in DIRS]
        for reach in (max(bw, bh) / 2 + 8.0, max(bw, bh) / 2 + 30.0, max(bw, bh) / 2 + 52.0, 90.0, 130.0):
            for vx, vy in dirs:
                cx, cy = p[0] + vx * reach, p[1] + vy * reach
                rect = (cx - bw / 2, cy - bh / 2, bw, bh)
                if badge_rect_ok(rect, badges):
                    badges.append((name, rect[0], rect[1], bw, bh))
                    done = True
                    break
            if done:
                break
        if done:
            break
    if not done:
        badge_fail.append(name)
        print('  !! 徽标 %s 未找到合法位' % name)
# 双段线第二枚徽标(2026-10-22用户: 12号线分两段, 广州体育馆这段也是12号线也要标识):
# 主循环每线一枚只标了南段; 双段卡按连通分量补第二枚, 版式=该段终点旁同规范
BADGE_AT_2ND = {
    '12号线': [(1456.0, 783.0)],  # 北段广州体育馆端: 终点标签正下方同x近距(徽标有底色可盖本线45°延长线, 规范允许;
                                   # 旧gap32位(1456,809.9)离终点72px被用户打回太远)
}
for _n2, _anchors2 in BADGE_AT_2ND.items():
    _sc2 = BADGE_SCALE_BY.get(_n2, BADGE_SCALE)
    _bw2, _bh2 = badge_size[_n2][0] * _sc2, badge_size[_n2][1] * _sc2
    for _cx2, _cy2 in _anchors2:
        _rect2 = (_cx2 - _bw2 / 2, _cy2 - _bh2 / 2, _bw2, _bh2)
        _why2 = badge_rect_why(_rect2, badges, ignore_corridor=True)
        if _why2 is None:
            badges.append((_n2, _rect2[0], _rect2[1], _bw2, _bh2))
        else:
            badge_fail.append(_n2)
            print('  !! 二段徽标 %s (%g,%g) 拒: %s' % (_n2, _cx2, _cy2, _why2))

# 贴本体校正: 离本体>90px的徽标在本体走廊包围盒外扩120px内网格搜最近合法位(用户: APM偏离太远, 2026-10-22)
for _i in range(len(badges)):
    _nm, _bx, _by, _bw, _bh = badges[_i]
    _own = [c for c in corridors if c[0] == _nm]
    if not _own:
        continue

    def _own_d(rect):
        return min(rect_seg_dist(rect, (c[1], c[2]), (c[3], c[4])) for c in _own)

    if _own_d((_bx, _by, _bw, _bh)) <= 90.0:
        continue
    # 搜索域: 非环线限定终点±150px(徽标必须在终点旁, 广佛线曾掉mid-line), 环线全线bbox
    _segs2 = [(c[1], c[2], c[3], c[4]) for c in _own]
    _deg2 = {}
    for ax, ay, bx, by in _segs2:
        a, b = (round(ax, 1), round(ay, 1)), (round(bx, 1), round(by, 1))
        _deg2[a] = _deg2.get(a, 0) + 1; _deg2[b] = _deg2.get(b, 0) + 1
    _endps = [q for q, d in _deg2.items() if d == 1]
    _cs = ((_bx + _bw / 2), (_by + _bh / 2))
    if _endps and min(dist(_cs, q) for q in _endps) < 120:
        continue  # 终点徽标(策略性远端)不迁: 2/10号线曾被贴本体搬到mid-line(2026-10-22)
    if _endps:
        _xs = [v for q in _endps for v in (q[0] - 150, q[0] + 150)]
        _ys = [v for q in _endps for v in (q[1] - 150, q[1] + 150)]
    else:
        _xs = [v for c in _own for v in (c[1], c[3])]
        _ys = [v for c in _own for v in (c[2], c[4])]
    best = None
    for cx in range(int(min(_xs)), int(max(_xs)) + 1, 6):
        for cy in range(int(min(_ys)), int(max(_ys)) + 1, 6):
            rect = (cx - _bw / 2, cy - _bh / 2, _bw, _bh)
            od = _own_d(rect)
            if od > 90.0 or od < 6.5:
                continue
            if badge_rect_why(rect, [b for j, b in enumerate(badges) if j != _i]) is not None:
                continue
            if best is None or od < best[0]:
                best = (od, rect)
    if best:
        badges[_i] = (_nm, best[1][0], best[1][1], _bw, _bh)
        print('  徽标 %s 贴本体迁址: 离本体 %.0fpx' % (_nm, best[0]))
    else:
        print('  !! 徽标 %s 本体±120px内无合法位' % _nm)
# 落位审计: 每枚复检(应全过; 2号线/22号线曾盖线的防线) + 离本体距离(过远=偏离本体)
for _nm, _bx, _by, _bw, _bh in badges:
    _why = badge_rect_why((_bx, _by, _bw, _bh), [b for b in badges if b[0] != _nm], ignore_corridor=True)
    if _why:
        print('  !! 徽标 %s 复检撞: %s' % (_nm, _why))
    _own = [c for c in corridors if c[0] == _nm]
    if _own:
        _d = min(rect_seg_dist((_bx, _by, _bw, _bh), (c[1], c[2]), (c[3], c[4])) for c in _own)
        if _d > 90.0:
            print('  !! 徽标 %s 偏离本体 %.0fpx' % (_nm, _d))

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
               % (fmt(bx), fmt(by), fmt(BADGE_SCALE_BY.get(nm, BADGE_SCALE)), badge_inner[nm]))
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
