# -*- coding: utf-8 -*-
"""通用单线卡片构建器(v6格式): 走廊+站圆+徽标+站名标注, 逐线过门禁
数据链: metro-data.js(站序/中英名) + gz-tim-2026.svg(走廊/站圆几何)
        + L1/L2 已验证圆(换乘钉, 防站名错位)
用法: python tools/build_card.py 3号线 5号线 ...   # 不带参数=全部剩余线
输出: assets/lines/line-<名>.svg + 逐线门禁报告
"""
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_card import run_gates, text_half_width  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)
SVG = os.path.join(ROOT, 'assets/gz-tim-2026.svg')
OUTDIR = os.path.join(ROOT, 'assets/lines')

# ---------------- 数据 ----------------
def load_metro():
    s = open(os.path.join(ROOT, 'data/metro-data.js'), encoding='utf-8').read()
    d = json.loads(re.search(r'window\.METRO_DATA\s*=\s*(\{.*\})\s*;?\s*$', s, re.S).group(1))
    S = {st['zh']: st for st in d['stations']}
    lines = {}
    for L in d['lines']:
        lines[L['zh']] = {'ref': L['ref'], 'stations': list(L['stations']),
                          'branches': [list(b) for b in L.get('branches', [])],
                          'color': L.get('color'), 'en': L.get('en', ''), 'loop': L.get('loop', False)}
    return lines, S


ANCHOR_BAD = {'广州东站', '体育中心', '广州火车站', '江泰路'}  # 已证与真值偏差29-207px


def load_pins():
    """选廊钉池: L1/L2真值 + svg2off锚 + 各卡圆位(仅用于走廊识别)。
    命名/修复只用 _trusted_pins(L1/L2互证源): 换乘站在每条线的画位不同,
    他线锚/卡位直接当本线钉会把站拉飞(11号线1284px根因)。"""
    pins = {}
    tp = os.path.join(ROOT, 'data/_trusted-pins.json')
    if os.path.exists(tp):
        for k, v in json.load(open(tp, encoding='utf-8')).items():
            pins[k] = tuple(v)
    for a in json.load(open(os.path.join(ROOT, 'data/svg2off-anchors.json'), encoding='utf-8')):
        if a['name'] not in ANCHOR_BAD and a['name'] not in pins:
            pins[a['name']] = (a['sx'], a['sy'])
    # 现有卡片 data-nm 圆位作为跨线互检过的补充钉(失败重建不再饿死后线)
    CARD_PIN_NAMES = getattr(load_pins, '_card_pins', None)
    if CARD_PIN_NAMES is None:
        load_pins._card_pins = set()
    for fn in os.listdir(os.path.join(ROOT, 'assets/lines')):
        if not (fn.startswith('line-') and fn.endswith('.svg')) or '_draft' in fn:
            continue
        try:
            rt = ET.parse(os.path.join(ROOT, 'assets/lines', fn)).getroot()
            for cc in rt.iter('{%s}circle' % NS):
                if cc.get('data-nm') and cc.get('data-nm') not in pins:
                    pins[cc.get('data-nm')] = (float(cc.get('cx')), float(cc.get('cy')))
                    load_pins._card_pins.add(cc.get('data-nm'))
        except Exception:
            pass
    c24 = json.load(open(os.path.join(ROOT, 'data/_l2circles24.json'), encoding='utf-8'))
    for nm, xy in c24.items():
        pins[nm] = tuple(xy)
    l1 = ET.parse(os.path.join(OUTDIR, 'line-1号线-17.svg')).getroot()
    known1 = ['西塱', '坑口', '花地湾', '芳村', '黄沙', '长寿路', '陈家祠', '西门口',
              '公园前', '农讲所', '烈士陵园', '东山口', '杨箕', '体育西路', '体育中心', '广州东站']
    circles1 = sorted(((float(c.get('cx')), float(c.get('cy')))
                       for c in l1.iter('{%s}circle' % NS) if 3 <= float(c.get('r', 0)) <= 12),
                      key=lambda p: p[0])
    circles1.sort(key=lambda p: (p[0] + p[1]))  # 西南→东北 粗序, 再按PCA细排
    import numpy as _np
    C = _np.array(circles1)
    mu = C.mean(0)
    _, _, vt = _np.linalg.svd(C - mu, full_matrices=False)
    axis = vt[0]
    if _np.dot(axis, C[-1] - C[0]) < 0:
        axis = -axis
    order = [circles1[i] for i in _np.argsort((C - mu) @ axis)]
    if len(order) == len(known1):
        for nm, p in zip(known1, order):
            pins.setdefault(nm, p)
    return pins


def sample_d(d):
    pts = []
    cur = [0.0, 0.0]
    start = [0.0, 0.0]
    for cmd, body in re.findall(r'([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)', d or ''):
        nums = [float(v) for v in re.findall(r'-?\d+\.?\d*(?:[eE][-+]?\d+)?', body)]
        rel = cmd.islower()
        c = cmd.upper()
        i = 0
        while i < len(nums):
            if c == 'M':
                p = nums[i:i + 2]; i += 2
                cur = [p[0] + (cur[0] if rel else 0), p[1] + (cur[1] if rel else 0)]
                start = list(cur); pts.append(tuple(cur))
            elif c == 'L':
                p = nums[i:i + 2]; i += 2
                cur = [p[0] + (cur[0] if rel else 0), p[1] + (cur[1] if rel else 0)]
                pts.append(tuple(cur))
            elif c == 'H':
                cur[0] = nums[i] + (cur[0] if rel else 0); i += 1; pts.append(tuple(cur))
            elif c == 'V':
                cur[1] = nums[i] + (cur[1] if rel else 0); i += 1; pts.append(tuple(cur))
            elif c in 'CQ':
                p = nums[i + 4:i + 6] if c == 'C' else nums[i + 2:i + 4]
                i += 6 if c == 'C' else 4
                if len(p) == 2:
                    cur = [p[0] + (cur[0] if rel else 0), p[1] + (cur[1] if rel else 0)]
                    pts.append(tuple(cur))
            elif c in 'ST':
                p = nums[i:i + 2]; i += 2
                cur = [p[0] + (cur[0] if rel else 0), p[1] + (cur[1] if rel else 0)]
                pts.append(tuple(cur))
            elif c == 'A':
                p = nums[i + 5:i + 7]; i += 7
                if len(p) == 2:
                    cur = [p[0] + (cur[0] if rel else 0), p[1] + (cur[1] if rel else 0)]
                    pts.append(tuple(cur))
            elif c == 'Z':
                cur = list(start); pts.append(tuple(cur)); i = len(nums)
            else:
                i = len(nums)
    return pts


def hex2rgb(h):
    h = h.lstrip('#')
    if len(h) == 3:
        h = ''.join(ch * 2 for ch in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _tf_matrix(s):
    """transform 串 -> 3x3 矩阵(支持 translate/scale/rotate/matrix)。"""
    M = np.eye(3)
    for name, args in re.findall(r'(translate|scale|rotate|matrix)\(([^)]*)\)', s or ''):
        v = [float(x) for x in re.split(r'[ ,]+', args.strip()) if x]
        if name == 'translate':
            m = np.array([[1, 0, v[0]], [0, 1, v[1] if len(v) > 1 else 0], [0, 0, 1]])
        elif name == 'scale':
            sx = v[0]; sy = v[1] if len(v) > 1 else v[0]
            m = np.array([[sx, 0, 0], [0, sy, 0], [0, 0, 1]])
        elif name == 'rotate':
            a = math.radians(v[0]); ca, sa = math.cos(a), math.sin(a)
            if len(v) >= 3:
                t1 = np.array([[1, 0, v[1]], [0, 1, v[2]], [0, 0, 1]])
                r = np.array([[ca, -sa, 0], [sa, ca, 0], [0, 0, 1]])
                t2 = np.array([[1, 0, -v[1]], [0, 1, -v[2]], [0, 0, 1]])
                m = t1 @ r @ t2
            else:
                m = np.array([[ca, -sa, 0], [sa, ca, 0], [0, 0, 1]])
        else:
            a, b, c, d, e, f = v[:6]
            m = np.array([[a, c, e], [b, d, f], [0, 0, 1]])
        M = M @ m
    return M


def _apply(M, x, y):
    if M is None:
        return x, y
    p = M @ np.array([x, y, 1.0])
    return float(p[0]), float(p[1])


class Source:
    def __init__(self, path):
        self.root = ET.parse(path).getroot()
        self.css = {}
        for st in self.root.iter('{%s}style' % NS):
            for m in re.finditer(r'\.([\w-]+)\{([^}]*)\}', st.text or ''):
                sm = re.search(r'stroke:\s*(#[0-9A-Fa-f]{3,6})', m.group(2))
                if sm:
                    self.css[m.group(1)] = sm.group(1)
        self.items = []

        def walk(el, anc):
            tag = el.tag.split('}')[-1]
            if tag in ('path', 'circle', 'rect', 'line', 'ellipse'):
                self.items.append((el, anc, tag))
            for ch in el:
                walk(ch, anc + [el])
        walk(self.root, [])
        # 祖先 transform 合成(l2 恰好无变换, 其余线大多有)
        self.tf = {}
        for el, anc, tag in self.items:
            M = np.eye(3)
            has = False
            for a in anc:
                t = a.get('transform')
                if t:
                    M = M @ _tf_matrix(t)
                    has = True
            self.tf[id(el)] = M if has else None
        self.circles = [self._pt(el, float(el.get('cx', 0)), float(el.get('cy', 0))) + (float(el.get('r', 4)),)
                        for el, _, t in self.items if t == 'circle']
        self._rings = None

    def _pt(self, el, x, y):
        return _apply(self.tf.get(id(el)), x, y)

    def rings(self):
        """每源圆的环带色中位数(5700px渲染图采样; None=无有色环)。"""
        if self._rings is not None:
            return self._rings
        from PIL import Image
        png = r'C:/Users/zlj10/WorkBuddy/2026-10-18-14-11-14/metro/gz_metro_2026_5700px.png'
        arr = np.array(Image.open(png).convert('RGB')).astype(int)
        sc = arr.shape[1] / 2848.5
        out = []
        for (cx, cy, r) in self.circles:
            x0, y0 = cx * sc, cy * sc
            pts = []
            for a in range(0, 360, 12):
                for rr in np.arange((r + 2.5) * sc, (r + 10) * sc, 2.0):
                    x, y = int(x0 + rr * np.cos(np.radians(a))), int(y0 + rr * np.sin(np.radians(a)))
                    if 0 <= x < arr.shape[1] and 0 <= y < arr.shape[0]:
                        pts.append(arr[y, x])
            med = None
            if pts:
                px = np.array(pts)
                mx, mn = px.max(axis=1), px.min(axis=1)
                sel = px[(mx - mn > 40) & (mx > 60)]
                if len(sel) >= 5:
                    med = tuple(np.median(sel, axis=0).astype(int))
            out.append(med)
        self._rings = out
        return out

    def stroke_hex(self, el, anc):
        for e in [el] + list(anc[::-1]):
            c = e.get('class')
            if c in self.css:
                return self.css[c]
            v = e.get('stroke')
            if v and v.startswith('#'):
                return v
        return None

    def corridor_groups(self):
        """彩色描边元素按颜色聚簇 -> [{rgb, segs}](坐标已过祖先变换)"""
        by = defaultdict(list)
        for el, anc, tag in self.items:
            if tag not in ('path', 'line'):
                continue
            hx = self.stroke_hex(el, anc)
            if not hx:
                continue
            rgb = hex2rgb(hx)
            # 只留有色线色: 饱和度够(max-min>=40)且非纯黑(max>=60)非近白(min<=235)
            if max(rgb) - min(rgb) < 40 or max(rgb) < 60 or min(rgb) > 235:
                continue
            if tag == 'line':
                x1, y1 = self._pt(el, float(el.get('x1')), float(el.get('y1')))
                x2, y2 = self._pt(el, float(el.get('x2')), float(el.get('y2')))
                if x1 < 300 and x2 < 300:
                    continue  # 图例
                by[rgb].append((x1, y1, x2, y2))
            else:
                pts = [self._pt(el, x, y) for (x, y) in sample_d(el.get('d', ''))]
                pts = [p for p in pts if not (p[0] < 300 and p[1] > 1800)]
                for a, b in zip(pts, pts[1:]):
                    if math.hypot(b[0] - a[0], b[1] - a[1]) > 1:
                        by[rgb].append((a[0], a[1], b[0], b[1]))
        merged = []
        for rgb, segs in by.items():
            if len(segs) < 2:
                continue
            for m in merged:
                if max(abs(rgb[i] - m['rgb'][i]) for i in range(3)) <= 18:
                    m['segs'] += segs
                    break
            else:
                merged.append({'rgb': rgb, 'segs': list(segs)})
        return merged


def seg_pt_dist(s, px, py):
    x1, y1, x2, y2 = s
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 < 1e-9:
        return math.hypot(x1 - px, y1 - py)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(x1 + t * dx - px, y1 + t * dy - py)


def corridor_pts(segs, step=6, cap=2200):
    pts = []
    for s in segs:
        n = max(2, int(math.hypot(s[2] - s[0], s[3] - s[1]) / step))
        for i in range(n + 1):
            pts.append((s[0] + (s[2] - s[0]) * i / n, s[1] + (s[3] - s[1]) * i / n))
    if len(pts) > cap:
        k = len(pts) / cap
        pts = [pts[int(i * k)] for i in range(cap)]
    return pts


def _min_dist2(pts, x, y):
    P = np.asarray(pts)
    return float(((P[:, 0] - x) ** 2 + (P[:, 1] - y) ** 2).min())


def select_corridor(groups, line_sts, pins, trusted=None):
    """主组=钉得分最高; 相容组并集: 至少1个本线钉<55px 且 无他线钉<24px。
    他线惩罚只用可信钉(钉池含坏卡位, 会把正确色组压成负分——1号线#DD2C00根因)。"""
    mine = [(nm, pins[nm]) for nm in line_sts if nm in pins]
    if not mine:
        return None, None, mine
    foreign = [(nm, xy) for nm, xy in (trusted or pins).items() if nm not in line_sts]
    scored = []
    for g in groups:
        pts = corridor_pts(g['segs'], step=10)
        hits = sum(1 for _, (x, y) in mine if _min_dist2(pts, x, y) < 32 ** 2)
        bad = sum(1 for _, (x, y) in foreign if _min_dist2(pts, x, y) < 24 ** 2)
        scored.append((hits - 3 * bad, hits, g, pts))
    scored = [t for t in scored if t[1] >= 1]  # 候选先过"命中至少一钉", 再比得分
    if not scored:
        return None, None, mine
    scored.sort(key=lambda t: -t[0])
    primary = scored[0][2]
    segs = list(primary['segs'])
    seen = {(round(s[0], 2), round(s[1], 2), round(s[2], 2), round(s[3], 2)) for s in segs}
    for _, hits, g, pts in scored[1:]:
        if hits < 1:
            continue
        if any(_min_dist2(pts, x, y) < 55 ** 2 for _, (x, y) in mine) and            not any(_min_dist2(pts, x, y) < 24 ** 2 for _, (x, y) in foreign):
            for sg in g['segs']:
                k = (round(sg[0], 2), round(sg[1], 2), round(sg[2], 2), round(sg[3], 2))
                if k not in seen:
                    seen.add(k)
                    segs.append(sg)
    return primary, segs, mine


def build_chain(segs):
    """端点0.5px聚类(0.5px裂链根因: 连接path端点与主线端点差2-3px), 返回邻接图。"""
    reps, vdeg = [], defaultdict(int)
    def kadd(p):
        for i, r in enumerate(reps):
            if math.hypot(r[0] - p[0], r[1] - p[1]) < 0.5:
                return i
        reps.append(p)
        return len(reps) - 1
    adj = defaultdict(list)
    for si, s in enumerate(segs):
        a, b = kadd((s[0], s[1])), kadd((s[2], s[3]))
        adj[a].append((b, si))
        adj[b].append((a, si))
    return reps, adj


def build_tree(segs):
    """走廊生成树(带边长)。环被生成树剪开; 返回 (reps, tree)。"""
    reps, adj = build_chain(segs)
    if not adj:
        return None, None
    verts = sorted(adj)
    tree = defaultdict(list)

    def span(root):
        seen = {root}
        stack = [root]
        while stack:
            x = stack.pop()
            for y, si in adj[x]:
                if y in seen:
                    continue
                seen.add(y)
                s = segs[si]
                w = math.hypot(s[2] - s[0], s[3] - s[1])
                tree[x].append((y, w))
                tree[y].append((x, w))
                stack.append(y)
        return seen
    seen = set()
    for v in verts:
        if v not in seen:
            seen |= span(v)
    return reps, tree


def assign_on_tree(reps, tree, circles, sts_main, branches, mine):
    """主线圆=两叶间路径上的圆(数相等优先), 支线圆=挂接子树; 钉满足度择优。
    返回 [(站名, (x,y)), ...](主线序, 支线插枢纽后), 警告列表。"""
    if tree is None:
        return None, ['走廊不成链']
    verts = list(tree)
    leaves = [v for v in verts if len(tree[v]) == 1]

    def path(a, b):
        prev = {a: None}
        dq = [a]
        while dq:
            x = dq.pop(0)
            if x == b:
                break
            for y, _ in tree[x]:
                if y not in prev:
                    prev[y] = x
                    dq.append(y)
        if b not in prev:
            return None
        out, cur = [], b
        while cur is not None:
            out.append(cur)
            cur = prev[cur]
        out.reverse()
        return out

    def nearv(x, y, only=None):
        best, bd = None, 1e18
        for v in (only if only is not None else verts):
            d = math.hypot(reps[v][0] - x, reps[v][1] - y)
            if d < bd:
                best, bd = v, d
        return best, bd

    best = None  # (score, order, warns)
    import itertools
    pairs = list(itertools.permutations(leaves, 2)) or [(verts[0], verts[-1])]
    for a, b in pairs:
        P = path(a, b)
        if not P:
            continue
        Pset = set(P)
        arcs = {}
        acc = 0.0
        arcs[P[0]] = 0.0
        for u, w in zip(P, P[1:]):
            acc += math.hypot(reps[w][0] - reps[u][0], reps[w][1] - reps[u][1])
            arcs[w] = acc
        # 圆归路径(近25px), 其余归挂接子树
        on_path, off_path = [], []
        for ci, c in enumerate(circles):
            v, d = nearv(c[0], c[1])
            if v in Pset and d < 25:
                on_path.append((arcs[v], ci))
            else:
                off_path.append((ci, v))
        on_path.sort()
        if len(on_path) != len(sts_main):
            continue
        main_ci = [ci for _, ci in on_path]
        # 支线圆: off_path 按其到主路径的挂接顶点分组
        warns = []
        used = set(main_ci)
        branch_assign = {}
        for br in branches:
            jn = br[0]
            if jn not in sts_main:
                warns.append('支线枢纽 %s 不在主线' % jn)
                continue
            jv, _ = nearv(*circles[main_ci[sts_main.index(jn)]][:2])
            group = []
            for ci, v in off_path:
                if ci in used:
                    continue
                # 该圆的挂接: 沿树向 jv 走是否不经过其他主路径顶点
                pp = path(v, jv)
                if pp and any(u in Pset and u != jv for u in pp[1:-1]):
                    continue
                if pp and len(pp) >= 1:
                    group.append(ci)
            want = len(br) - 1
            if len(group) < want:
                warns.append('支线 %s 圆缺(%d/%d)' % (jn, len(group), want))
                continue
            # 组内按到枢纽距离排
            jx, jy = circles[main_ci[sts_main.index(jn)]][:2]
            group.sort(key=lambda ci: math.hypot(circles[ci][0] - jx, circles[ci][1] - jy))
            branch_assign[jn] = group[:want]
            used.update(group[:want])
        # 主线序 + 支线插枢纽后(保证 names 首尾=主线终点)
        order = [(nm, circles[main_ci[k]][:2]) for k, nm in enumerate(sts_main)]
        pos = {nm: circles[main_ci[k]][:2] for k, nm in enumerate(sts_main)}
        for br in branches:
            jn = br[0]
            if jn not in branch_assign:
                continue
            at = next((i for i, (nm, _) in enumerate(order) if nm == jn), None)
            if at is None:
                continue
            seg = [(nm, circles[ci][:2]) for nm, ci in zip(br[1:], branch_assign[jn])]
            for nm, xy in seg:
                pos[nm] = xy
            order[at + 1:at + 1] = seg
        score = sum(1 for nm, (px, py) in mine
                    if nm in pos and math.hypot(pos[nm][0] - px, pos[nm][1] - py) < 45)
        miss = [nm for nm, (px, py) in mine
                if nm in pos and math.hypot(pos[nm][0] - px, pos[nm][1] - py) >= 45]
        if best is None or score > best[0]:
            best = (score, order, miss + warns)
    return (best[1], best[2]) if best else (None, ['树上无可行指派(叶对均不合)'])


def order_circles_along(segs, circles):
    """走廊弧长链序: 生成树上双BFS直径(环被生成树剪开, 原松弛法在有环图上死循环)。"""
    reps, tree = build_tree(segs)
    if reps is None:
        return None, None
    verts = list(tree)

    def far(u):
        dist = {u: 0.0}
        prev = {u: None}
        stack = [u]
        while stack:
            x = stack.pop()
            for y, w in tree[x]:
                if y not in dist:
                    dist[y] = dist[x] + w
                    prev[y] = x
                    stack.append(y)
        f = max(dist, key=dist.get)
        return f, dist, prev
    u, _, _ = far(verts[0])
    v, dist, prev = far(u)
    path, cur = [], v
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    arc, acc = {path[0]: 0.0}, 0.0
    for a, b in zip(path, path[1:]):
        acc += math.hypot(reps[b][0] - reps[a][0], reps[b][1] - reps[a][1])
        arc[b] = acc
    out = []
    for ci, (cx, cy, r) in enumerate(circles):
        bestv, bd = None, 1e18
        for vv in path:
            d = math.hypot(reps[vv][0] - cx, reps[vv][1] - cy)
            if d < bd:
                bestv, bd = vv, d
        out.append((arc[bestv], ci, bd))
    out.sort()
    return out, (reps[path[0]], reps[path[-1]], acc)


def place_labels(stations, circles_xy, segs, EN, no_term=False):
    """六规则+规则8 放置(源自 l2-labels.py v2, 参数化)。返回 [(nm, box)]"""
    G = 10.0
    ZH_H, EN_H, GAP2 = 11.0, 6.0, 1.5
    SAMP = []
    for (x1, y1, x2, y2) in segs:
        n = max(2, int(math.hypot(x2 - x1, y2 - y1) / 8))
        for i in range(n + 1):
            SAMP.append((x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n))
    SAMP = np.asarray(SAMP)

    def clearance(bx0, by0, bx1, by1):
        dx = np.maximum(np.maximum(bx0 - SAMP[:, 0], 0.0), SAMP[:, 0] - bx1)
        dy = np.maximum(np.maximum(by0 - SAMP[:, 1], 0.0), SAMP[:, 1] - by1)
        return float(np.min(np.hypot(dx, dy)))

    vmap = defaultdict(list)
    for s in segs:
        for p in ((round(s[0], 1), round(s[1], 1)), (round(s[2], 1), round(s[3], 1))):
            vmap[p].append(s)

    labels = []
    for nm, (ax, ay) in zip(stations, circles_xy):
        en = EN.get(nm, '')
        bw = max(2 * text_half_width(nm), 2 * text_half_width(en, zh=False))
        bh = ZH_H + GAP2 + (EN_H + (6.5 if split_en(en, nm) else 0) if en else 0)  # 拆行第二行预留
        best, bd, bdir = None, 1e18, (1, 0)
        for s in segs:
            d = seg_pt_dist(s, ax, ay)
            if d < bd:
                bd, best, bdir = d, s, (s[2] - s[0], s[3] - s[1])
        L = math.hypot(*bdir) or 1.0
        ux, uy = bdir[0] / L, bdir[1] / L
        junc = False
        for (vx, vy), adjsegs in vmap.items():
            if len(adjsegs) < 2 or math.hypot(vx - ax, vy - ay) > 25:
                continue
            if any(abs(s[2] - s[0]) > abs(s[3] - s[1]) for s in adjsegs) and \
               any(abs(s[2] - s[0]) <= abs(s[3] - s[1]) for s in adjsegs):
                junc = True
        labels.append({'nm': nm, 'ax': ax, 'ay': ay, 'en': en, 'bw': bw, 'bh': bh,
                       'horiz': abs(ux) > abs(uy),  # 规则9: 45°为界(<45°上下, >45°左右)
                       'diag': 0.74 < abs(ux) and 0.74 < abs(uy),  # 正45°±3°才法向
                       'term': (not no_term) and nm in (stations[0], stations[-1]), 'ux': ux, 'uy': uy, 'junc': junc})
    TERM = set() if no_term else {stations[0], stations[-1]}

    def candidates(lb):
        ax, ay, bw, bh = lb['ax'], lb['ay'], lb['bw'], lb['bh']
        out = []
        if lb['diag'] and lb['nm'] not in TERM:

            normals = sorted([(-lb['uy'], lb['ux']), (lb['uy'], -lb['ux'])], key=lambda n: n[0])
            for nx, ny in normals:
                d = G + (abs(nx) * bw + abs(ny) * bh) / 2
                cx, cy = ax + nx * d, ay + ny * d
                out.append(('法左' if nx < 0 else '法右', cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2))
            out.append(('上', ax - bw / 2, ay - G - bh, ax + bw / 2, ay - G))
            out.append(('下', ax - bw / 2, ay + G, ax + bw / 2, ay + G + bh))
            return out
        if lb['nm'] in TERM:
            # 终点文字=路线延长线上居中(嘉禾望岗/二沙岛验收版式): 延长线候选一律最先,
            # 外向=最近两段外向均值(贴轴|u|<0.25吸附, 45°不再被规则9阈值吞掉)
            nn = sorted(segs, key=lambda s: seg_pt_dist(s, ax, ay))[:2]
            vx = vy = 0.0
            for s in nn:
                d1 = math.hypot(s[0] - ax, s[1] - ay)
                d2 = math.hypot(s[2] - ax, s[3] - ay)
                fx, fy = (s[2], s[3]) if d1 < d2 else (s[0], s[1])
                L2 = math.hypot(fx - ax, fy - ay) or 1.0
                vx += (ax - fx) / L2
                vy += (ay - fy) / L2
            L2 = math.hypot(vx, vy) or 1.0
            ux, uy = vx / L2, vy / L2
            if 0 <= abs(ux) < 0.25:
                ux = 0.0
            if 0 <= abs(uy) < 0.25:
                uy = 0.0
            L2 = math.hypot(ux, uy) or 1.0
            ux, uy = ux / L2, uy / L2
            d = G + (bw * abs(ux) + bh * abs(uy)) / 2
            cx, cy = ax + ux * d, ay + uy * d
            out.append(('延长', cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2))
            if lb['diag']:
                normals = sorted([(-lb['uy'], lb['ux']), (lb['uy'], -lb['ux'])], key=lambda n: n[0])
                for nx, ny in normals:
                    d = G + (abs(nx) * bw + abs(ny) * bh) / 2
                    cx, cy = ax + nx * d, ay + ny * d
                    out.append(('法左' if nx < 0 else '法右',
                                cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2))
            if lb['horiz']:
                out.append(('端左', ax - G - bw, ay - bh / 2, ax - G, ay + bh / 2))
                out.append(('端右', ax + G, ay - bh / 2, ax + G + bw, ay + bh / 2))
            else:
                out.append(('下中', ax - bw / 2, ay + G, ax + bw / 2, ay + G + bh))
                out.append(('上中', ax - bw / 2, ay - G - bh, ax + bw / 2, ay - G))
            return out
        if lb['horiz']:
            out += [('上', ax - bw / 2, ay - G - bh, ax + bw / 2, ay - G),
                    ('下', ax - bw / 2, ay + G, ax + bw / 2, ay + G + bh),
                    ('左', ax - G - bw, ay - bh / 2, ax - G, ay + bh / 2),
                    ('右', ax + G, ay - bh / 2, ax + G + bw, ay + bh / 2)]
        else:
            out += [('左', ax - G - bw, ay - bh / 2, ax - G, ay + bh / 2),
                    ('右', ax + G, ay - bh / 2, ax + G + bw, ay + bh / 2),
                    ('上', ax - bw / 2, ay - G - bh, ax + bw / 2, ay - G),
                    ('下', ax - bw / 2, ay + G, ax + bw / 2, ay + G + bh)]
        return out

    def push(desc, bx0, by0, bx1, by1, ax, ay):
        if desc.startswith('法') or desc == '延长':
            return bx0, by0, bx1, by1
        pushed = 0.0
        for _ in range(6):
            cl = clearance(bx0, by0, bx1, by1)
            if cl >= G - 0.1:
                break
            need = G - cl + 0.2
            pushed += need
            if pushed > 18:
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
                bx0, bx1 = ax - w / 2, ax + w / 2
            else:
                h = by1 - by0
                by0, by1 = ay - h / 2, ay + h / 2
        return bx0, by0, bx1, by1

    placed = []

    def place(lb):
        for strict in (True, False):
            for desc, bx0, by0, bx1, by1 in candidates(lb):
                r = push(desc, bx0, by0, bx1, by1, lb['ax'], lb['ay'])
                if r is None:
                    continue
                bx0, by0, bx1, by1 = r
                if clearance(bx0, by0, bx1, by1) < G - 1.5:
                    continue
                clash = any(not (bx0 > p['bx1'] or p['bx0'] > bx1 or by0 > p['by1'] or p['by0'] > by1)
                            for p in placed)
                if clash:
                    continue
                if strict:
                    cover = any(bx0 - 4 < p['ax'] < bx1 + 4 and by0 - 4 < p['ay'] < by1 + 4
                                for p in labels if p is not lb)
                    if cover:
                        continue
                lb.update(desc=desc, bx0=bx0, by0=by0, bx1=bx1, by1=by1)
                placed.append(lb)
                return
        best = None
        for desc, bx0, by0, bx1, by1 in candidates(lb):
            ax, ay = lb['ax'], lb['ay']
            for _p in range(10):
                r = push(desc, bx0, by0, bx1, by1, ax, ay)
                if r is None:
                    break
                bx0, by0, bx1, by1 = r
                cl = clearance(bx0, by0, bx1, by1)
                if best is None or cl > best[0]:
                    best = (cl, desc, bx0, by0, bx1, by1)
                if cl >= G - 1.5:
                    break
                need = G - cl + 0.5
                if desc in ('上', '上中'):
                    by0 -= need; by1 -= need
                elif desc in ('下', '下中'):
                    by0 += need; by1 += need
                elif desc in ('左', '端左'):
                    bx0 -= need; bx1 -= need
                else:
                    bx0 += need; bx1 += need
        if best:
            _cl, desc, bx0, by0, bx1, by1 = best
        else:
            desc, bx0, by0, bx1, by1 = candidates(lb)[0]
        # 终局兜底: 自圆八向×递增距离, 取首个净距达标且不撞已放标签的位
        ax0, ay0 = lb['ax'], lb['ay']
        w, h = bx1 - bx0, by1 - by0
        got = None
        for dist in (G + max(w, h) / 2 + 2, G + max(w, h) / 2 + 14, G + max(w, h) / 2 + 26):
            for ang in range(0, 360, 45):
                cx0 = ax0 + dist * math.cos(math.radians(ang))
                cy0 = ay0 + dist * math.sin(math.radians(ang))
                nb = (cx0 - w / 2, cy0 - h / 2, cx0 + w / 2, cy0 + h / 2)
                if clearance(*nb) < G - 1.5:
                    continue
                if any(not (nb[0] > p['bx1'] or p['bx0'] > nb[2] or nb[1] > p['by1'] or p['by0'] > nb[3])
                       for p in placed):
                    continue
                got = nb
                break
            if got:
                break
        if got:
            bx0, by0, bx1, by1 = got
        lb.update(desc=desc, bx0=bx0, by0=by0, bx1=bx1, by1=by1)
        placed.append(lb)

    for lb in labels:
        if not lb['junc']:
            place(lb)
    for lb in labels:
        if lb['junc']:
            place(lb)
    return placed


def split_en(en, zh):
    """英文宽>中文1.5倍且多单词 → 按词拆两行(两行宽差最小)。返回 (行1,行2) 或 None。"""
    if not en or ' ' not in en:
        return None
    if text_half_width(en, zh=False) <= 1.5 * text_half_width(zh):
        return None
    words = en.split(' ')
    best = None
    for i in range(1, len(words)):
        a, b = ' '.join(words[:i]), ' '.join(words[i:])
        d = abs(text_half_width(a, zh=False) - text_half_width(b, zh=False))
        if best is None or d < best[0]:
            best = (d, a, b)
    return best[1], best[2]


_BADGES_JSON = None


def badges_data():
    global _BADGES_JSON
    if _BADGES_JSON is None:
        _BADGES_JSON = json.load(open(os.path.join(ROOT, 'data/badges-official.json'), encoding='utf-8'))
    return _BADGES_JSON


# ===== 头部官方胶囊(v8): 比例承官图网格(107x59->80x43 圆角9), 排版全部墨迹实测校准 =====
PILL_W, PILL_H, PILL_RX = 80.0, 43.0, 9.0
PILL_NUM_X, PILL_NUM_SIZE = 9.5, 25.0
PILL_ZH_SIZE, PILL_EN_SIZE = 11.5, 7.5
PILL_COL_MIN, PILL_COL_GAP = 38.0, 5.0
PILL_DARK = '#614F2E'          # 亮底深字(官方黄底徽标暖褐)
_NUM_FONT = None
_EN_FONT = None


def _num_ink_w(num):
    """数字串在 YaHei bold 25pt 下的墨宽(PIL 实测, 不手估)。"""
    global _NUM_FONT
    if _NUM_FONT is None:
        from PIL import ImageFont
        _NUM_FONT = ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc', 200)  # 25pt x8
    return _NUM_FONT.getlength(num) / 8.0 * 0.98


def _en_ink_w(en):
    global _EN_FONT
    if _EN_FONT is None:
        from PIL import ImageFont
        _EN_FONT = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 60)  # 7.5pt x8
    return _EN_FONT.getlength(en) / 8.0 * 0.98


def pill_text_color(color):
    """亮底(黄/金/黄绿)用暖褐深字, 其余白字——对应官方胶囊实际配色。"""
    r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    L = 0.299 * r + 0.587 * g + 0.114 * b
    return PILL_DARK if L >= 175 else '#FFFFFF'


def pill_metrics(ref):
    """返回 (W, col_x, num, zh, en): 胶囊宽与右列 x 由数字墨宽自适应。"""
    num = ref
    zh = '号线' if ref.isdigit() else '线'
    en = {'GF': 'Guangfo Line', 'APM': 'Line'}.get(ref, 'Line %s' % ref if ref.isdigit() else ref)
    col_x = max(PILL_COL_MIN, PILL_NUM_X + _num_ink_w(num) + PILL_COL_GAP)
    W = max(PILL_W, col_x + max(PILL_ZH_SIZE * 2, _en_ink_w(en)) + 5)
    return W, col_x, num, zh, en


def badge_header_scale(ref):
    return 1.0


def badge_full_size(ref):
    if ref == 'GF':  # 广佛线: 堆叠两行(广佛线/Guangfo Line), 无编号
        return 73.0, PILL_H, 1.0
    return pill_metrics(ref)[0], PILL_H, 1.0


def make_badge_official(ref, color, x, y, scale, mode):
    """官方徽标组(mode: full=头部官方胶囊, x/y=左上角 | chip=终点数字块, x/y=色块中心)。
    头部: 线色胶囊+深/白数字+右列号线/Line N; 终点: Tim 图抠出的 13.5 色块白数字。
    产出 <g data-badge data-box [data-ink]>, 门禁按属性消费。"""
    g = ET.Element('{%s}g' % NS)
    if mode == 'full' and ref == 'GF':
        # 广佛线堆叠胶囊: 上「广佛线」下「Guangfo Line」, 均居中, 无编号
        ink = pill_text_color(color)
        W, H = 73.0, PILL_H
        g.set('data-badge', 'header')
        g.set('transform', 'translate(%g %g)' % (x, y))
        r = ET.SubElement(g, '{%s}rect' % NS)
        r.set('x', '0'); r.set('y', '0')
        r.set('width', '%.1f' % W); r.set('height', '%.1f' % H); r.set('rx', '%.1f' % PILL_RX)
        r.set('fill', color)
        t = ET.SubElement(g, '{%s}text' % NS)
        t.set('x', '%.1f' % (W / 2)); t.set('y', '%.1f' % 21.2)
        t.set('text-anchor', 'middle'); t.set('font-family', "'Microsoft YaHei', sans-serif")
        t.set('font-size', '15'); t.set('font-weight', '600'); t.set('fill', ink)
        t.text = '广佛线'
        t2 = ET.SubElement(g, '{%s}text' % NS)
        t2.set('x', '%.1f' % (W / 2)); t2.set('y', '%.1f' % 32.75)
        t2.set('text-anchor', 'middle'); t2.set('font-family', 'Arial, sans-serif')
        t2.set('font-size', '8'); t2.set('fill', ink)
        t2.text = 'Guangfo Line'
        g.set('data-ink', ink)
        g.set('data-box', '%.1f,%.1f,%.1f,%.1f' % (x, y, x + W, y + H))
        g.set('data-chip', '%.1f,%.1f,%.1f,%.1f' % (x, y, x + W, y + H))
        return g
    if mode == 'full':
        W, col_x, num, zh, en = pill_metrics(ref)
        ink = pill_text_color(color)
        g.set('data-badge', 'header')
        g.set('transform', 'translate(%g %g)' % (x, y))
        r = ET.SubElement(g, '{%s}rect' % NS)
        r.set('x', '0'); r.set('y', '0')
        r.set('width', '%.1f' % W); r.set('height', '%.1f' % PILL_H); r.set('rx', '%.1f' % PILL_RX)
        r.set('fill', color)
        t = ET.SubElement(g, '{%s}text' % NS)
        t.set('x', '%.1f' % PILL_NUM_X); t.set('y', '%.1f' % 32.5)
        t.set('font-family', "'Microsoft YaHei', sans-serif"); t.set('font-size', '%g' % PILL_NUM_SIZE)
        t.set('font-weight', 'bold'); t.set('fill', ink); t.text = num
        t2 = ET.SubElement(g, '{%s}text' % NS)
        t2.set('x', '%.1f' % col_x); t2.set('y', '%.1f' % 21.5)
        t2.set('font-family', "'Microsoft YaHei', sans-serif"); t2.set('font-size', '%g' % PILL_ZH_SIZE)
        t2.set('font-weight', '600'); t2.set('fill', ink); t2.text = zh
        t3 = ET.SubElement(g, '{%s}text' % NS)
        t3.set('x', '%.1f' % col_x); t3.set('y', '%.1f' % 35.0)
        t3.set('font-family', 'Arial, sans-serif'); t3.set('font-size', '%g' % PILL_EN_SIZE)
        t3.set('fill', ink); t3.text = en
        g.set('data-ink', ink)
        g.set('data-box', '%.1f,%.1f,%.1f,%.1f' % (x, y, x + W, y + PILL_H))
        g.set('data-chip', '%.1f,%.1f,%.1f,%.1f' % (x, y, x + W, y + PILL_H))
        return g
    # 终点数字块: 原图抠出色块+白数字, 中心锚点
    m = badges_data()[ref]['chip']
    # 锚点铁律: 元件必须 0 基(2026-10-20 12号线数字块飞出事故), 绝对首坐标越界当场炸
    for e in m['elements']:
        mm = re.match(r'M\s*([-\d.]+)[ ,]+([-\d.]+)', e['d'])
        assert mm and -0.05 <= float(mm.group(1)) <= m['w'] + 0.05 \
            and -0.05 <= float(mm.group(2)) <= m['h'] + 0.05, \
            'chip 锚点未归一化 ref=%s M=%s w=%s' % (ref, mm.groups() if mm else '?', m['w'])
    g.set('data-badge', 'chip')
    tx = x - m['w'] * scale / 2
    ty = y - m['h'] * scale / 2
    tr = 'translate(%g %g)' % (tx, ty)
    if scale and scale != 1.0:
        tr += ' scale(%g)' % scale
    g.set('transform', tr)
    for e in m['elements']:
        p = ET.SubElement(g, '{%s}path' % NS)
        p.set('d', e['d'])
        p.set('fill', e['fill'])
    g.set('data-box', '%.1f,%.1f,%.1f,%.1f' % (tx, ty, tx + m['w'] * scale, ty + m['h'] * scale))
    return g


def make_badge(color, num, zh, en, x, y, scale=1.0):
    """兼容包装(v8): 旧脚本(l5-card/l6-card/_l3/_fix_l3等)的旧胶囊调用自动产出官方徽标。
    scale=1: x/y=左上角(头部胶囊); scale<1: x/y=中心(终点数字块, 原尺寸)。zh/en 由 ref 推导。"""
    if scale == 1.0:
        return make_badge_official(num, color, x, y, 1.0, 'full')
    return make_badge_official(num, color, x, y, 1.0, 'chip')


def _decreasing(pairs):
    ss = [k for _, k in sorted(pairs)]
    dec = sum(1 for a, b in zip(ss, ss[1:]) if b < a)
    return dec > len(ss) / 2


def _seg_len(s):
    return math.hypot(s[2] - s[0], s[3] - s[1])


def _seg_project(segs, x, y):
    best, bd = None, 1e18
    for s in segs:
        x1, y1, x2, y2 = s
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        if L2 < 1e-9:
            t = 0.0
        else:
            t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / L2))
        px, py = x1 + t * dx, y1 + t * dy
        d = math.hypot(px - x, py - y)
        if d < bd:
            best, bd = (px, py), d
    return best, bd


def build_line(linename, src, groups, lines, S, pins):
    L = lines[linename]
    sts = list(L['stations'])
    for _br in L.get('branches', []):  # 支线并入站表(枢纽后插)
        if _br[0] in sts:
            sts[sts.index(_br[0]) + 1:sts.index(_br[0]) + 1] = _br[1:]
        else:
            sts += _br[1:]
    N = len(sts)
    EN = {nm: S[nm].get('en', '') for nm in sts if nm in S}
    missing_data = [nm for nm in sts if nm not in S]
    if missing_data:
        return None, 'metro-known 缺站: %s' % missing_data

    _tp = json.load(open(os.path.join(ROOT, 'data/_trusted-pins.json'), encoding='utf-8'))
    _pins_naming = {k: tuple(v) for k, v in _tp.items()}  # 命名/修复锚=可信表+仲裁注入
    for _nm in sts:
        if _nm not in _pins_naming and _nm in pins and _nm in getattr(load_pins, '_card_pins', set()):
            pass
    mine = [(nm, _pins_naming[nm]) for nm in sts if nm in _pins_naming]
    for _nm, _xy in pins.items():
        _pins_naming.setdefault(_nm, _xy)
    _trusted = {k: tuple(v) for k, v in json.load(open(os.path.join(ROOT, 'data/_trusted-pins.json'), encoding='utf-8')).items()}
    for _nm, _xy in pins.items():
        _trusted.setdefault(_nm, _xy) if False else None
    g, segs, _mine_full = select_corridor(groups, sts, pins, trusted=_trusted)
    _primary_keys = {(round(q[0], 1), round(q[1], 1), round(q[2], 1), round(q[3], 1))
                     for q in g['segs']}
    if g is None or not segs:
        return None, '无锚钉命中(无法确认走廊色)'
    rgb = g['rgb']
    color = '#%02X%02X%02X' % rgb
    if len(segs) < 2:
        return None, '走廊段过少'

    def near_circles(sel_segs, lim=6.0):
        pts = corridor_pts(sel_segs, step=5)
        if not pts:
            return []
        P = np.asarray(pts)
        C = np.array([(c[0], c[1]) for c in src.circles])
        rs = np.array([c[2] for c in src.circles])
        d2 = ((C[:, 0:1] - P[None, :, 0]) ** 2 + (C[:, 1:2] - P[None, :, 1]) ** 2).min(axis=1)
        idx = np.where((rs >= 2.5) & (rs <= 8) & (d2 <= lim * lim))[0]
        out = []
        for i in idx:
            cx, cy = src.circles[i][0], src.circles[i][1]
            if not any(math.hypot(cx - ox, cy - oy) < 2.2 for ox, oy, _ in out):
                out.append((cx, cy, src.circles[i][2]))
        return out

    rings = src.rings()

    def ring_ok(c_idx, rgb, tol=70):
        m = rings[c_idx]
        return m is not None and max(abs(m[i] - rgb[i]) for i in range(3)) < tol

    def circles_of_color(sel_segs, rgb, lim=9.0):
        """走廊附近 + 环色匹配线色 的源圆(换乘站他线环被排除)。"""
        pts = corridor_pts(sel_segs, step=5)
        if not pts:
            return []
        P = np.asarray(pts)
        C = np.array([(c[0], c[1]) for c in src.circles])
        d2 = ((C[:, 0:1] - P[None, :, 0]) ** 2 + (C[:, 1:2] - P[None, :, 1]) ** 2).min(axis=1)
        out = []
        for i in np.where(d2 <= lim * lim)[0].tolist():
            if not ring_ok(i, rgb):
                continue
            cx, cy = src.circles[i][0], src.circles[i][1]
            if not any(math.hypot(cx - ox, cy - oy) < 2.2 for ox, oy, _ in out):
                out.append((cx, cy, src.circles[i][2]))
        return out

    # 完整性优先: 主组环色圆已够则不合并(合并会引入他线段污染)
    base_circles = circles_of_color(segs, rgb)
    if len(base_circles) >= N:
        pool = []
    else:
        pool = [(s, g2['rgb']) for g2 in groups for s in g2['segs']
                if s not in segs and (s[0], s[1], s[2], s[3]) not in
                {(q[0], q[1], q[2], q[3]) for q in segs}]
    for _round in range(14):
        pts1 = np.asarray(corridor_pts(segs, step=10, cap=2500))
        rest, added = [], False
        for s, rgb2 in pool:
            ends = [(s[0], s[1]), (s[2], s[3])]
            d_ends = min(((pts1[:, 0] - e[0]) ** 2 + (pts1[:, 1] - e[1]) ** 2).min() for e in ends)
            if d_ends > 30 ** 2:
                rest.append((s, rgb2))
                continue
            proven = circles_of_color([s], rgb, lim=12) or any(
                _min_dist2(corridor_pts([s], step=8), x, y) < 30 ** 2 for _, (x, y) in mine)
            if proven:
                segs.append(s)
                added = True
            elif d_ends <= 8 ** 2 and max(abs(rgb2[i] - rgb[i]) for i in range(3)) <= 40:
                spts = corridor_pts([s], step=4)
                rings_near = [rings[i] for i in range(len(src.circles))
                              if rings[i] is not None
                              and _min_dist2(spts, src.circles[i][0], src.circles[i][1]) < 12 ** 2]
                foreign = [m for m in rings_near if max(abs(m[k] - rgb[k]) for k in range(3)) > 100]
                ours = [m for m in rings_near if max(abs(m[k] - rgb[k]) for k in range(3)) < 70]
                if not foreign or ours:
                    segs.append(s)
                    added = True
            else:
                rest.append((s, rgb2))
        pool = rest
        if not added:
            break

    circles = circles_of_color(segs, rgb)
    if len(circles) < N:
        circles = circles + [c for c in near_circles(segs) if c not in circles]

    def clip_terminal(term_xy):
        """把离 term_xy 最远的走廊端剪到该点(l2同款终点裁剪)。"""
        best, bd = None, -1
        for si, s in enumerate(segs):
            for k, (ex, ey) in enumerate(((s[0], s[1]), (s[2], s[3]))):
                d = math.hypot(ex - term_xy[0], ey - term_xy[1])
                if d > bd:
                    bd, best = d, (si, k)
        if best is None or bd <= 92:
            return  # ≤92px 的过站延伸按原图保留(官方版式: 线过终点圆继续走一段)
        si, k = best
        # 沿该段方向把端点收到 距终点92px 处
        s = list(segs[si])
        ex, ey = s[k*2], s[k*2+1]
        dx, dy = ex-term_xy[0], ey-term_xy[1]
        dl = math.hypot(dx, dy) or 1.0
        s[k*2], s[k*2+1] = term_xy[0]+dx/dl*92, term_xy[1]+dy/dl*92
        segs[si] = tuple(s)

    # 钉圆对齐: 每钉 45px 内必有圆, 缺则按钉在走廊的投影合成(换乘两线圆位差可>40)
    for nm, (px, py) in mine:
        if not any(math.hypot(c[0] - px, c[1] - py) < 45 for c in circles):
            proj, d = _seg_project(segs, px, py)
            circles.append((proj[0], proj[1], 4.5))

    ordered, _ = order_circles_along(segs, circles)
    if ordered is None:
        return None, '走廊不成链'
    circ_by_arc = [circles[ci] for _, ci, _ in ordered]
    arcs = [o[0] for o in ordered]
    arc_cis = [ci for _, ci, _ in ordered]

    # 命名(在插值前锁定更稳): 见下方 assign; 此处先跳过旧路径
    # 非钉缺站: 最大弧长间隙中点插圆(投影到走廊)
    if len(circ_by_arc) < N:
        merged = list(zip(arcs, circ_by_arc))
        for _ in range(N - len(circ_by_arc)):
            gaps = sorted((merged[i + 1][0] - merged[i][0], i) for i in range(len(merged) - 1))
            gi = gaps[-1][1]
            a, b = merged[gi][1][:2], merged[gi + 1][1][:2]
            proj, _d = _seg_project(segs, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            mid = (merged[gi][0] + merged[gi + 1][0]) / 2
            merged.insert(gi + 1, (mid, (proj[0], proj[1], 4.5)))
        circ_by_arc = [c for _, c in merged]
    if len(circ_by_arc) > N:
        pin_xy = [xy for _, xy in mine]
        keep = [c for c in circ_by_arc
                if any(math.hypot(c[0] - px, c[1] - py) < 45 for px, py in pin_xy)]
        rest = sorted((c for c in circ_by_arc if c not in keep),
                      key=lambda c: _seg_project(segs, c[0], c[1])[1])
        circ_by_arc = (keep + rest)[:N]
    if len(circ_by_arc) != N:
        return None, '站圆数 %d ≠ 站数 %d' % (len(circ_by_arc), N)

    # 圆序定名: 钉圆锁进其站名槽位(语义真值), 其余圆2-opt排最短链, 名=站表序
    slot_circle = {}
    used_ids = set()
    for nm, (px, py) in mine:
        si = sts.index(nm) if nm in sts else -1
        if si < 0:
            continue
        best, bd = None, 1e18
        for c in circ_by_arc:
            if id(c) in used_ids:
                continue
            d = math.hypot(c[0] - px, c[1] - py)
            if d < bd:
                best, bd = c, d
        if best is not None and bd < 25:
            slot_circle[si] = best
            used_ids.add(id(best))
        else:
            # 可信钉25px内才吸圆; 否则钉位合成(43px外的可能是他线换乘圆, 1号线西塱教训)
            slot_circle[si] = (px, py, 4.5)
            used_ids.add(id((px, py, 4.5)))
    rem = [c for c in circ_by_arc if id(c) not in used_ids]
    chain = [None] * N
    for si, c in slot_circle.items():
        chain[si] = c
    fs = [i for i in range(N) if chain[i] is None]
    for i, c in zip(fs, rem):
        chain[i] = c

    def tlen(ch):
        return sum(math.hypot(b[0] - a[0], b[1] - a[1])
                   for a, b in zip(ch, ch[1:]) if a and b)
    base = tlen(chain)
    lockidx = set(slot_circle)
    for _it in range(80):
        improved = False
        for i in range(N):
            for j in range(i + 1, N):
                if chain[i] is None or chain[j] is None:
                    continue
                if any(i <= k <= j for k in lockidx):
                    continue
                chain[i:j + 1] = chain[i:j + 1][::-1]
                if tlen(chain) < base - 0.5:
                    base = tlen(chain)
                    improved = True
                else:
                    chain[i:j + 1] = chain[i:j + 1][::-1]
        if not improved:
            break
    names = sts
    circles_xy = [(c[0], c[1]) for c in chain]
    assign_warns = []
    pos0 = dict(zip(names, circles_xy))
    pin_warn = [nm for nm, (px, py) in mine
                if nm in pos0 and math.hypot(pos0[nm][0]-px, pos0[nm][1]-py) > 45]

    # 位置引擎: 链上相邻可信锚之间, 非锚站按官方弧长分数落位(单调映射; 锚=L1/L2/锚站表)
    try:
        OFF = {}
        _ost = json.load(open(os.path.join(ROOT, 'data/official-stations.json'), encoding='utf-8'))
        for _k, _v in _ost.items():
            for _s in (_v.get('stations') or []):
                if isinstance(_s, dict) and _s.get('name') and 'x' in _s:
                    OFF.setdefault(_s['name'], (_s['x'], _s['y']))
        pin_pos = {nm: xy for nm, xy in mine}
        chs = [list(L['stations'])] + [list(br) for br in L.get('branches', [])]
        for _eng in range(3):
            changed = False
            for ch in chs:
                pts = []
                for nm in ch:
                    k = names.index(nm) if nm in names else None
                    pts.append(circles_xy[k] if k is not None else None)
                ai = [i for i, nm in enumerate(ch) if nm in pin_pos and pts[i] is not None
                      and nm in OFF]
                for i1, i2 in zip(ai, ai[1:]):
                    if i2 - i1 < 2:
                        continue
                    o1, o2 = OFF[ch[i1]], OFF[ch[i2]]
                    t1, t2 = pts[i1], pts[i2]
                    if math.hypot(t2[0]-t1[0], t2[1]-t1[1]) < 3:
                        continue
                    # 官方弧长分数(链序经过的官方坐标)
                    oks = [i1]
                    olen = [0.0]
                    for k in range(i1+1, i2):
                        if ch[k] in OFF:
                            oks.append(k)
                            olen.append(olen[-1] + math.hypot(OFF[ch[k]][0]-OFF[ch[oks[-2]]][0],
                                                               OFF[ch[k]][1]-OFF[ch[oks[-2]]][1]))
                    oks.append(i2)
                    olen.append(olen[-1] + math.hypot(o2[0]-OFF[ch[oks[-2]]][0], o2[1]-OFF[ch[oks[-2]]][1]))
                    total = olen[-1] or 1.0
                    frac = {k: olen[j]/total for j, k in enumerate(oks)}
                    for k in range(i1+1, i2):
                        nm = ch[k]
                        if nm in pin_pos:
                            continue
                        f = frac.get(k)
                        if f is None:
                            # 无官方坐标: 相邻已知分数线性补
                            prev_f = max((frac[q] for q in frac if q < k), default=0.0)
                            next_f = min((frac[q] for q in frac if q > k), default=1.0)
                            span = sum(1 for q in range(i1+1, i2) if q not in frac) + 1
                            f = prev_f + (next_f-prev_f)/max(1, span)
                        cand = (t1[0] + (t2[0]-t1[0])*f, t1[1] + (t2[1]-t1[1])*f)
                        gk = names.index(nm)
                        old = circles_xy[gk]
                        # 采纳条件: 候选改善与两链邻的距离和
                        def d(p, q):
                            return math.hypot(p[0]-q[0], p[1]-q[1])
                        prev_pt = circles_xy[names.index(ch[k-1])] if ch[k-1] in names else None
                        next_pt = circles_xy[names.index(ch[k+1])] if ch[k+1] in names else None
                        sc_old = (d(old, prev_pt) if prev_pt else 0) + (d(old, next_pt) if next_pt else 0)
                        sc_new = (d(cand, prev_pt) if prev_pt else 0) + (d(cand, next_pt) if next_pt else 0)
                        if sc_new < sc_old - 0.5:
                            circles_xy[gk] = (round(cand[0], 1), round(cand[1], 1))
                            changed = True
            if not changed:
                break
    except Exception as _e:
        assign_warns.append('位置引擎异常:%r' % _e)

    # 走廊=矢量提取几何: 沿"主链+支线链"在原图段图上寻路(BFS), 缺口直连, 站点引入/引出
    def corridor_by_walk(orig_segs, chains_pts, primary_keys=None):
        reps, adj = build_chain(orig_segs)
        all_pts = [p for ch in chains_pts for p in ch]
        if not adj or not all_pts:
            return [(a[0], a[1], b[0], b[1]) for a, b in zip(all_pts, all_pts[1:])]

        pk = primary_keys or set()
        prim_v = set()
        if pk:
            for si0, q0 in enumerate(orig_segs):
                k0 = (round(q0[0], 1), round(q0[1], 1), round(q0[2], 1), round(q0[3], 1))
                if k0 in pk:
                    for p0 in ((q0[0], q0[1]), (q0[2], q0[3])):
                        for v0 in adj:
                            if math.hypot(reps[v0][0]-p0[0], reps[v0][1]-p0[1]) < 3:
                                prim_v.add(v0)

        def nearv(x, y):
            # 优先本线色组端点(他线段端点会劫持引入段, 走廊变斜线)
            for pool in (prim_v, adj):
                best, bd = None, 1e18
                for v in pool:
                    d = math.hypot(reps[v][0]-x, reps[v][1]-y)
                    if d < bd:
                        best, bd = v, d
                if best is not None and bd < 60:
                    return best, bd
            return best, bd

        def bfs(a, b):
            # Dijkstra: 本线色组段=原长, 他线段=5倍(平行捷径必让位于参考图画线)
            import heapq
            pk = primary_keys or set()
            dist = {a: 0.0}
            prev = {a: None}
            hq = [(0.0, a)]
            while hq:
                d0, x = heapq.heappop(hq)
                if x == b:
                    break
                if d0 > dist.get(x, 1e18):
                    continue
                for y, si in adj[x]:
                    s0 = orig_segs[si]
                    L0 = math.hypot(s0[2]-s0[0], s0[3]-s0[1])
                    k0 = (round(s0[0], 1), round(s0[1], 1), round(s0[2], 1), round(s0[3], 1))
                    w = L0 if k0 in pk else 5.0 * L0
                    nd = d0 + w
                    if nd < dist.get(y, 1e18):
                        dist[y] = nd
                        prev[y] = x
                        heapq.heappush(hq, (nd, y))
            if b not in prev:
                return None
            path, cur = [], b
            while cur is not None:
                path.append(cur)
                cur = prev[cur]
            return path[::-1]

        out = []
        for ch in chains_pts:
            for a, b in zip(ch, ch[1:]):
                if math.hypot(b[0]-a[0], b[1]-a[1]) < 3:
                    continue
                va, da = nearv(*a)
                vb, db = nearv(*b)
                if va is None or vb is None:
                    out.append((a[0], a[1], b[0], b[1]))
                    continue
                p = bfs(va, vb) if va != vb else [va, vb]
                if p is None or da > 60 or db > 60:
                    out.append((a[0], a[1], b[0], b[1]))  # 缺口: 站到站直连
                    continue
                # 站圆在路径段上(<3px)则把该段在圆点处劈开(过站, 无悬挂引入)
                def split_at(pt, path_edges):
                    px, py = pt
                    for idx, q in enumerate(path_edges):
                        qx1, qy1, qx2, qy2 = q
                        ddx, ddy = qx2-qx1, qy2-qy1
                        L2 = ddx*ddx + ddy*ddy
                        if L2 < 1e-9:
                            continue
                        t = max(0.0, min(1.0, ((px-qx1)*ddx + (py-qy1)*ddy)/L2))
                        if math.hypot(qx1+t*ddx-px, qy1+t*ddy-py) < 3 and 0.02 < t < 0.98:
                            path_edges[idx] = (qx1, qy1, px, py)
                            path_edges.insert(idx+1, (px, py, qx2, qy2))
                            return True
                    return False
                path_edges = []
                for u, w in zip(p, p[1:]):
                    for y, si in adj[u]:
                        if y == w:
                            path_edges.append(tuple(orig_segs[si]))
                if not split_at(a, path_edges) and da > 2:
                    out.append((a[0], a[1], reps[va][0], reps[va][1]))
                out.extend(path_edges)
                if not split_at(b, path_edges) and db > 2:
                    out.append((reps[vb][0], reps[vb][1], b[0], b[1]))
        # 终点延伸: 链两端站在源图上向外(背离来路)的段并入(≤92px, 深2)——
        # 广州东站"过站向左"的尾巴、西塱线尾等官方画法
        used = set()

        def _dk(q):
            a = (round(q[0], 1), round(q[1], 1), round(q[2], 1), round(q[3], 1))
            b = (round(q[2], 1), round(q[3], 1), round(q[0], 1), round(q[1], 1))
            return min(a, b)
        out2 = []
        for q in out:
            k = _dk(q)
            if k not in used:
                used.add(k)
                out2.append(q)
        # 共线覆盖去重: 子段被更长段完整覆盖时删子段(花地湾三重描边根因)
        def _cover(sub, big):
            ax, ay, bx, by = big
            px, py, qx, qy = sub
            def d2line(x, y):
                dx, dy = bx-ax, by-ay
                L2 = dx*dx+dy*dy or 1.0
                t = max(0.0, min(1.0, ((x-ax)*dx+(y-ay)*dy)/L2))
                return math.hypot(ax+t*dx-x, ay+dy*t-y)
            def within(x, y):
                return (min(ax, bx)-1 <= x <= max(ax, bx)+1 and min(ay, by)-1 <= y <= max(ay, by)+1)
            return d2line(px, py) < 1.5 and d2line(qx, qy) < 1.5 and within(px, py) and within(qx, qy)
        drop = set()
        for i in range(len(out2)):
            for j in range(len(out2)):
                if i == j or i in drop or j in drop:
                    continue
                li = math.hypot(out2[i][2]-out2[i][0], out2[i][3]-out2[i][1])
                lj = math.hypot(out2[j][2]-out2[j][0], out2[j][3]-out2[j][1])
                if lj > li + 0.5 and _cover(out2[i], out2[j]):
                    drop.add(i)
        out = [q for i, q in enumerate(out2) if i not in drop]
        for ch in chains_pts:
            for term in (ch[0], ch[-1]):
                vT, dT = nearv(*term)
                if vT is None or dT > 40:
                    continue
                # 来路方向: 沿已用段; 收集 vT 邻接且未用、远端距终点≤92 的段(两层)
                frontier = [(vT, 0)]
                seen_v = {vT}
                while frontier:
                    v, depth = frontier.pop(0)
                    if depth >= 2:
                        continue
                    for y, si in adj[v]:
                        if y in seen_v:
                            continue
                        seen_v.add(y)
                        q = tuple(orig_segs[si])
                        k = _dk(q)
                        if primary_keys and k not in {(round(z[0], 1), round(z[1], 1), round(z[2], 1), round(z[3], 1)) and _dk(z) for z in primary_keys and []}:
                            pass
                        far = math.hypot(reps[y][0]-term[0], reps[y][1]-term[1])
                        if k in used or far > 92:
                            continue
                        used.add(k)
                        out.append(q)
                        frontier.append((y, depth + 1))
        return out

    # 线尾段外推: 段两端无好锚时, 用近端好锚+官方方向+局部比例尺把尾段摆正
    try:
        for ch in chs:
            pts = [circles_xy[names.index(nm)] if nm in names else None for nm in ch]
            okm = [i for i in range(len(ch)-1)
                   if pts[i] and pts[i+1] and math.hypot(pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1]) <= 120]
            if len(okm) < 2:
                continue
            for lo, hi, side in ((0, min(okm)+0, 'head'), (max(okm)+1, len(ch)-1, 'tail')):
                pass
            # 头尾段
            for side, rng in (('head', range(0, min(okm))), ('tail', range(max(okm)+2, len(ch)))):
                idxs = list(rng)
                if not idxs:
                    continue
                # 近端好锚
                if side == 'head':
                    a_i = min(okm)+1
                    sec = list(range(0, a_i))
                    # 参考好段: a_i 往后取几段估比例尺/方向对
                    ref = [(ch[i], ch[i+1]) for i in okm[:4]]
                else:
                    a_i = max(okm)
                    sec = list(range(a_i+1, len(ch)))
                    ref = [(ch[i], ch[i+1]) for i in okm[-4:]]
                if not sec:
                    continue
                o_anchor = OFF.get(ch[a_i])
                o_sec = [OFF.get(ch[k]) for k in sec]
                if not o_anchor or not all(o_sec):
                    continue
                # 比例尺: 参考段的 Tim距/官方距 均值
                rs = []
                for u, w in ref:
                    if u in OFF and w in OFF and u in names and w in names:
                        pu, pw = circles_xy[names.index(u)], circles_xy[names.index(w)]
                        od = math.hypot(OFF[w][0]-OFF[u][0], OFF[w][1]-OFF[u][1])
                        td = math.hypot(pw[0]-pu[0], pw[1]-pu[1])
                        if od > 1:
                            rs.append(td/od)
                if not rs:
                    continue
                scale = sum(rs)/len(rs)
                pa = circles_xy[names.index(ch[a_i])] if ch[a_i] in names else None
                if not pa:
                    continue
                prev_o = o_anchor
                prev_p = pa
                for j, k in enumerate(sec):
                    od = math.hypot(o_sec[j][0]-prev_o[0], o_sec[j][1]-prev_o[1])
                    ang = math.atan2(o_sec[j][1]-prev_o[1], o_sec[j][0]-prev_o[0])
                    td = od*scale
                    cand = (prev_p[0] + td*math.cos(ang), prev_p[1] + td*math.sin(ang))
                    if ch[k] in names and ch[k] not in pin_pos:
                        circles_xy[names.index(ch[k])] = (round(cand[0], 1), round(cand[1], 1))
                    prev_o = o_sec[j]
                    prev_p = cand
    except Exception as _e:
        assign_warns.append('尾段外推异常:%r' % _e)

    # 可信钉终局复位: 任何引擎不得移动真值位(西塱1280教训)
    for _nm, _xy in _pins_naming.items():
        if _nm in names:
            circles_xy[names.index(_nm)] = _xy

    # 多链模型: 主链+支线链(分叉线可有>2终点; 走廊/G10/终点徽标均按链)
    name_pos = dict(zip(names, circles_xy))
    chains = [list(L['stations'])] + [list(br) for br in L.get('branches', [])]
    chains_pts = [[name_pos[nm] for nm in ch if nm in name_pos] for ch in chains]
    segs = corridor_by_walk(segs, chains_pts, _primary_keys)
    chain_ends = []
    for ci, ch in enumerate(chains):
        ends_nm = [ch[0], ch[-1]] if ci == 0 else [ch[-1]]  # 支线只取尾端(首端是枢纽)
        for e in ends_nm:
            if e in name_pos and name_pos[e] not in chain_ends:
                chain_ends.append(name_pos[e])

    # 终局超距收敛: 链内相邻超距, 未钉端按官方弧长插值重置; 双钉夹段内部站官方弧长重排
    try:
        OFF2 = OFF
        for _fin in range(3):
            npf = dict(zip(names, circles_xy))
            chs = [list(L['stations'])] + [list(br) for br in L.get('branches', [])]
            changed = False
            for ch in chs:
                idxs = [names.index(nm) for nm in ch if nm in npf]
                for u, w in zip(idxs, idxs[1:]):
                    a, b = circles_xy[u], circles_xy[w]
                    gaps2 = math.hypot(b[0]-a[0], b[1]-a[1])
                    med2 = 70.0
                    cap2 = max(2.5*med2, 110.0)
                    if gaps2 <= cap2:
                        continue
                    ua = names[u] in pin_pos
                    ub = names[w] in pin_pos
                    if ua and ub:
                        # 夹段内部站(u..w之间)官方弧长重排
                        interior = idxs[idxs.index(u)+1:idxs.index(w)] if w-u > 1 else []
                        oa, ob = OFF2.get(names[u]), OFF2.get(names[w])
                        if interior and oa and ob:
                            total = math.hypot(ob[0]-oa[0], ob[1]-oa[1]) or 1.0
                            for k in interior:
                                ok = OFF2.get(names[k])
                                if ok:
                                    t = min(1.0, math.hypot(ok[0]-oa[0], ok[1]-oa[1])/total)
                                    circles_xy[k] = (round(a[0]+(b[0]-a[0])*t, 1),
                                                     round(a[1]+(b[1]-a[1])*t, 1))
                                    changed = True
                    elif not ua:
                        # 未钉端向钉端靠: 该端位 = 官方弧长插值(用两侧官方坐标)
                        prev_i = idxs[idxs.index(u)-1] if idxs.index(u) > 0 else None
                        o_b = OFF2.get(names[w])
                        if prev_i is not None and OFF2.get(names[prev_i]) and o_b:
                            o_a0 = OFF2[names[prev_i]]
                            o_u = OFF2.get(names[u])
                            if o_u:
                                total = math.hypot(o_b[0]-o_a0[0], o_b[1]-o_a0[1]) or 1.0
                                t = min(1.0, math.hypot(o_u[0]-o_a0[0], o_u[1]-o_a0[1])/total)
                                p0 = circles_xy[prev_i]
                                circles_xy[u] = (round(p0[0]+(b[0]-p0[0])*t, 1),
                                                 round(p0[1]+(b[1]-p0[1])*t, 1))
                                changed = True
                    elif not ub:
                        nxt_i = idxs[idxs.index(w)+1] if idxs.index(w)+1 < len(idxs) else None
                        o_a = OFF2.get(names[u])
                        if nxt_i is not None and OFF2.get(names[nxt_i]) and o_a:
                            o_b0 = OFF2[names[nxt_i]]
                            o_w = OFF2.get(names[w])
                            if o_w:
                                total = math.hypot(o_b0[0]-o_a[0], o_b0[1]-o_a[1]) or 1.0
                                t = min(1.0, math.hypot(o_w[0]-o_a[0], o_w[1]-o_a[1])/total)
                                p1 = circles_xy[nxt_i]
                                circles_xy[w] = (round(a[0]+(p1[0]-a[0])*t, 1),
                                                 round(a[1]+(p1[1]-a[1])*t, 1))
                                changed = True
            if not changed:
                break
    except Exception as _e:
        assign_warns.append('终局收敛异常:%r' % _e)

    # 可信钉终局复位: 任何引擎不得移动真值位(西塱1280教训)
    for _nm, _xy in _pins_naming.items():
        if _nm in names:
            circles_xy[names.index(_nm)] = _xy

    # 多链模型: 主链+支线链(分叉线可有>2终点; 走廊/G10/终点徽标均按链)
    name_pos = dict(zip(names, circles_xy))
    chains = [list(L['stations'])] + [list(br) for br in L.get('branches', [])]
    chains_pts = [[name_pos[nm] for nm in ch if nm in name_pos] for ch in chains]
    segs = corridor_by_walk(segs, chains_pts, _primary_keys)
    chain_ends = []
    for ci, ch in enumerate(chains):
        ends_nm = [ch[0], ch[-1]] if ci == 0 else [ch[-1]]  # 支线只取尾端(首端是枢纽)
        for e in ends_nm:
            if e in name_pos and name_pos[e] not in chain_ends:
                chain_ends.append(name_pos[e])

    # 铁律3: 圆严格在线上(缝合后走廊) —— 超距圆投影吸附
    circles_xy = [(_seg_project(segs, x, y)[0] if _seg_project(segs, x, y)[1] > 1.2 else (x, y))
                  for (x, y) in circles_xy]

    # ---- 组卡 ----
    xs = [p[0] for p in circles_xy] + [s[0] for s in segs] + [s[2] for s in segs]
    ys = [p[1] for p in circles_xy] + [s[1] for s in segs] + [s[3] for s in segs]
    x0, x1m = min(xs) - 115, max(xs) + 65
    y0, y1m = min(ys) - 95, max(ys) + 85
    svg = ET.Element('{%s}svg' % NS)
    svg.set('viewBox', '%.1f %.1f %.1f %.1f' % (x0, y0, x1m - x0, y1m - y0))
    svg.set('width', str(round(x1m - x0))); svg.set('height', str(round(y1m - y0)))
    bg = ET.SubElement(svg, '{%s}rect' % NS)
    bg.set('x', str(x0)); bg.set('y', str(y0)); bg.set('width', str(x1m - x0)); bg.set('height', str(y1m - y0))
    bg.set('fill', '#ffffff')
    gco = ET.SubElement(svg, '{%s}g' % NS); gco.set('id', '走廊')
    STY = 'fill:none;stroke:%s;stroke-width:7;stroke-linecap:round' % color
    for (sx1, sy1, sx2, sy2) in segs:
        ln = ET.SubElement(gco, '{%s}line' % NS)
        ln.set('x1', str(round(sx1, 2))); ln.set('y1', str(round(sy1, 2)))
        ln.set('x2', str(round(sx2, 2))); ln.set('y2', str(round(sy2, 2)))
        ln.set('style', STY)
    gc = ET.SubElement(svg, '{%s}g' % NS); gc.set('id', '站圆')
    for nm, (cx, cy) in zip(names, circles_xy):
        if nm in _pins_naming:
            cx, cy = _pins_naming[nm]  # 可信钉终裁(写盘最后一言)
        c = ET.SubElement(gc, '{%s}circle' % NS)
        c.set('cx', str(cx)); c.set('cy', str(cy)); c.set('r', '4.5')
        c.set('data-nm', nm)
        c.set('style', 'fill:#FFFFFF;stroke:%s;stroke-width:2' % color)

    placed = place_labels(names, circles_xy, segs, EN, no_term=bool(L.get('loop')))
    lb_boxes = [(lb['bx0'], lb['by0'], lb['bx1'], lb['by1']) for lb in placed]

    def rect_hit(b1, b2, m=2.0):
        return not (b1[2] < b2[0] + m or b2[2] + m < b1[0] or b1[3] < b2[1] + m or b2[3] + m < b1[1])

    def corridor_hit(box):
        for (x1, y1, x2, y2) in segs:
            for i in range(9):
                t = i / 8
                px, py = x1 + t * (x2 - x1), y1 + t * (y2 - y1)
                if box[0] - 2 < px < box[2] + 2 and box[1] - 2 < py < box[3] + 2:
                    return True
        return False

    def badge_box(cx, cy):
        cw = badges_data()[L['ref']]['chip']['w']
        ch = badges_data()[L['ref']]['chip']['h']
        return (cx - cw / 2 - 2, cy - ch / 2 - 2, cx + cw / 2 + 2, cy + ch / 2 + 2)

    gb = ET.SubElement(svg, '{%s}g' % NS); gb.set('id', '线路徽标')
    gb_boxes = []
    def _gb_add(gel):
        gb.append(gel)
        gb_boxes.append(tuple(float(v) for v in gel.get('data-box').split(',')))
    _hw, _hh, _hs = badge_full_size(L['ref'])
    _gb_add(make_badge_official(L['ref'], color, x0 + 56, y0 + 36, _hs, 'full'))
    ends = chain_ends if len(chain_ends) >= 2 else [circles_xy[0], circles_xy[-1]]
    if L.get('loop'):
        ends = ends[:1] + [circles_xy[0], circles_xy[1]]
    # 终点版式(与2号线嘉禾望岗验收样式统一):
    #   文字=放置器所放(线侧或轴向) | 徽标=圆点->文字中心 射线上、越过文字远端(三点一线)
    #   走廊=文字侧过站延伸剪回圆点(线终于圆点), 对侧保留原图延伸(≤92px)
    for (tx, ty) in ends:
        tlb = next((lb for lb in placed
                    if math.hypot((lb['bx0']+lb['bx1'])/2 - tx, (lb['by0']+lb['by1'])/2 - ty) < 60), None)
        ux, uy = 0.0, -1.0
        if tlb is not None:
            cxL, cyL = (tlb['bx0']+tlb['bx1'])/2, (tlb['by0']+tlb['by1'])/2
            du = math.hypot(cxL-tx, cyL-ty) or 1.0
            ux, uy = (cxL-tx)/du, (cyL-ty)/du
        # 文字侧延伸剪回圆点
        for si3, s3 in enumerate(segs):
            for k3 in (0, 1):
                ex3, ey3 = (s3[0], s3[1]) if k3 == 0 else (s3[2], s3[3])
                if math.hypot(ex3-tx, ey3-ty) <= 12:
                    continue
                along = (ex3-tx)*ux + (ey3-ty)*uy
                perp2 = abs(-(ex3-tx)*uy + (ey3-ty)*ux)
                if along > 8 and perp2 < 26:
                    ss = list(segs[si3])
                    ss[k3*2], ss[k3*2+1] = tx, ty
                    segs[si3] = tuple(ss)
        # 徽标: 射线上越过文字远端(三点一线)。框内候选优先; 全出框时取最近候选
        # 并把卡框向外扩(终点在卡缘的横向线, 滘口/高增曾因此掉环搜兜底变竖排)
        placed_ok = False
        min_ext = 40.0
        if tlb is not None:
            far = max(((cx-tx)*ux + (cy-ty)*uy)
                      for cx in (tlb['bx0'], tlb['bx1'])
                      for cy in (tlb['by0'], tlb['by1']))
            min_ext = max(min_ext, far + badges_data()[L['ref']]['chip']['w'] / 2 + 6)
        import itertools as _it
        _own = (tlb['bx0'], tlb['by0'], tlb['bx1'], tlb['by1']) if tlb else None
        others = [lbb for lbb in lb_boxes if lbb != _own]
        cand = []
        for extra in sorted(set(round(min_ext) + d for d in (0, 12, 26, 42, 60, 80))):
            bx = tx + ux*extra
            by = ty + uy*extra
            bb = badge_box(bx, by)
            if any(rect_hit(bb, lbb) for lbb in others):
                continue
            inside = not (bb[0] < x0+5 or bb[2] > x1m-5 or bb[1] < y0+5 or bb[3] > y1m-5)
            cand.append((0 if inside else 1, extra, bx, by))
            if inside:
                break
        if cand:
            cand.sort(key=lambda c: (c[0], c[1]))
            _, extra, bx, by = cand[0]
            _gb_add(make_badge_official(L['ref'], color, bx, by, 1.0, 'chip'))
            placed_ok = True
        if not placed_ok:
            for dist in (48, 58, 70, 85, 100):
                for ang in range(0, 360, 30):
                    bx = tx + dist * math.cos(math.radians(ang))
                    by = ty + dist * math.sin(math.radians(ang))
                    bb = badge_box(bx, by)
                    if bb[0] < x0+5 or bb[2] > x1m-5 or bb[1] < y0+5 or bb[3] > y1m-5:
                        continue
                    if corridor_hit(bb) or any(rect_hit(bb, lb) for lb in lb_boxes):
                        continue
                    _gb_add(make_badge_official(L['ref'], color, bx, by, 1.0, 'chip'))
                    placed_ok = True
                    break
                if placed_ok:
                    break
        if not placed_ok:
            for (bx, by) in ((x0+56, y1m-40), (x1m-56, y1m-40), (x0+56, y0+100), (x1m-56, y0+100)):
                bb = badge_box(bx, by)
                if bb[0] < x0+5 or bb[2] > x1m-5 or bb[1] < y0+5 or bb[3] > y1m-5:
                    continue
                if corridor_hit(bb) or any(rect_hit(bb, lbb) for lbb in lb_boxes):
                    continue
                _gb_add(make_badge_official(L['ref'], color, bx, by, 1.0, 'chip'))
                placed_ok = True
                break

    # viewBox 按标签实测左边距重算(英文宽站名防出框)
    if placed:
        lm = min(lb['bx0'] for lb in placed)
        rm = max(lb['bx1'] for lb in placed)
        tm = min(lb['by0'] for lb in placed)
        bm = max(lb['by1'] + (6.5 if split_en(lb['en'], lb['nm']) else 0) for lb in placed)
        if placed_ok and 'bb' in dir():
            pass
        # 徽标远缘计入(官方徽标 data-box 即缩放后实际包围盒), 四边都收(终点chip可外扩卡框)
        for (bx0, by0, bx1, by1) in gb_boxes:
            lm = min(lm, bx0)
            rm = max(rm, bx1)
            tm = min(tm, by0)
            bm = max(bm, by1)
        if lm - 12 < x0:
            x0 = lm - 12
        if rm + 12 > x1m:
            x1m = rm + 12
        if tm - 12 < y0:
            y0 = tm - 12
        if bm + 12 > y1m:
            y1m = bm + 12
        svg.set('viewBox', '%.1f %.1f %.1f %.1f' % (x0, y0, x1m - x0, y1m - y0))
        svg.set('width', str(round(x1m - x0)))
        bg.set('x', str(x0))
        bg.set('width', str(x1m - x0))
        bg.set('y', str(y0))
        bg.set('height', str(y1m - y0))

    gl = ET.SubElement(svg, '{%s}g' % NS); gl.set('id', '站名标注')
    gl.set('font-family', "'Microsoft YaHei', 'PingFang SC', sans-serif")
    for lb in placed:
        zx = (lb['bx0'] + lb['bx1']) / 2
        zy = lb['by0'] + 11
        t = ET.SubElement(gl, '{%s}text' % NS)
        t.set('x', str(round(zx, 1))); t.set('y', str(round(zy, 1)))
        t.set('text-anchor', 'middle'); t.set('font-size', '10.5'); t.set('font-weight', '500')
        t.set('fill', '#1a1a1a'); t.text = lb['nm']
        if lb['en']:
            sp = split_en(lb['en'], lb['nm'])
            te = ET.SubElement(gl, '{%s}text' % NS)
            te.set('x', str(round(zx, 1))); te.set('y', str(round(lb['by1'], 1)))
            te.set('text-anchor', 'middle'); te.set('font-size', '5.5'); te.set('font-family', 'Arial, sans-serif'); te.set('fill', '#444444')
            te.text = sp[0] if sp else lb['en']
            if sp:  # 第二行英文: 行距6.5, 同 x 同字号
                te2 = ET.SubElement(gl, '{%s}text' % NS)
                te2.set('x', str(round(zx, 1))); te2.set('y', str(round(lb['by1'] + 6.5, 1)))
                te2.set('text-anchor', 'middle'); te2.set('font-size', '5.5'); te2.set('fill', '#444444')
                te2.text = sp[1]
    out = os.path.join(OUTDIR, 'line-%s.svg' % linename)
    draft = out.replace('.svg', '_draft.svg')
    ET.ElementTree(svg).write(draft, encoding='unicode', xml_declaration=False)
    R = run_gates(draft, expect_n=N)
    fails = ['%s:%s' % (no, detail) for no, name, ok, detail in R if not ok]
    if fails:
        return out, fails  # 门禁未过: 只留草稿, 正式卡保持原样
    os.replace(draft, out)
    warns = assign_warns + ['钉位疑议:%s' % pin_warn if pin_warn else '']
    warns = [w for w in warns if w]
    msg = ('ALL PASS' if not fails else fails)
    if warns:
        msg = ('%s | 警告: %s' % (msg, '; '.join(warns)))
    return out, msg


def main():
    lines, S = load_metro()
    pins = load_pins()
    src = Source(SVG)
    groups = src.corridor_groups()
    want = sys.argv[1:] or [k for k in lines if k not in ('1号线', '2号线')]
    results = {}
    pending = list(want)
    for _pas in range(3):  # 多遍: 过门禁线的站名坐标反哺钉池, 逐遍解锁无钉线
        if not pending:
            break
        nxt = []
        for ln in pending:
            if ln not in lines:
                results[ln] = '✗ metro-data 无此线'
                continue
            try:
                out, msg = build_line(ln, src, groups, lines, S, pins)
            except Exception as e:
                out, msg = None, '异常 %r' % e
            passed = bool(out) and isinstance(msg, str) and msg.startswith('ALL PASS')
            results[ln] = ('✓ ' if passed else '✗ ') + (msg if isinstance(msg, str) else '; '.join(map(str, msg)))
            if passed and _pas < 2:
                rt = ET.parse(out).getroot()
                for t in rt.iter('{%s}text' % NS):
                    if t.get('font-size') == '10.5':
                        pins.setdefault(t.text, (float(t.get('x')), float(t.get('y'))))
            elif not passed and _pas < 2:
                nxt.append(ln)
        pending = nxt
    ok = [k for k, v in results.items() if v.startswith('✓')]
    for k in want:
        print('%-6s %s' % (k, results.get(k, '?')))
    print()
    print('通过 %d / 失败 %d' % (len(ok), len(results) - len(ok)))
    return 0 if len(ok) == len(results) else 1
