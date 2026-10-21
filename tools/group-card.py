# -*- coding: utf-8 -*-
"""通用组提取建卡器: Tim图按<g id>分组 + 站位真值自动对位(圆色×官方案号)
用法: python tools/group-card.py 7号线 _x37_ ['#7CB342']
"""
import sys, math, os, time, re, json
import xml.etree.ElementTree as ET

NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import build_card as B
from verify_card import run_gates


def build(line_zh, gid, color, loop=False, overrides=None, chains=None, custom_segs=None, branch=None, pad=None,
          stations=None, en_extra=None, outpath=None, data_multi=False):
    src = open(os.path.join(ROOT, 'assets/gz-tim-2026.svg'), encoding='utf-8').read()

    # ===== 样式表(类->stroke, 记录display:none) =====
    sm = re.search(r'<style[^>]*>(.*?)</style>', src, re.S)
    cls_stroke, cls_hidden = {}, set()
    for mm in re.finditer(r'\.(st\d+)\{([^}]*)\}', sm.group(1)):
        body = mm.group(2)
        if 'display:none' in body.replace(' ', ''):
            cls_hidden.add(mm.group(1))
        pm = re.search(r'stroke:(#[0-9A-Fa-f]{6})', body)
        if pm:
            cls_stroke[mm.group(1)] = pm.group(1)

    # ===== 组几何(custom_segs=显式段表跳过组提取, 用于走廊重定向如12号线胶囊绕行) =====
    if custom_segs is not None:
        segs = [tuple(float(v) for v in s) for s in custom_segs]
    else:
        gm = re.search(r'<g\b[^>]*id="%s"[^>]*>' % re.escape(gid), src)
        if not gm:
            print('!! 找不到组 %s' % gid); return None
        start = gm.end(); depth = 1; j = start
        while depth > 0:
            no = src.find('<g', j); nc = src.find('</g>', j)
            if no != -1 and no < nc: depth += 1; j = no + 2
            else: depth -= 1; j = nc + 4
        inner = src[start:j]
        segs = []
        for lm in re.finditer(r'<line\b[^>]*/>', inner):
            at = dict(re.findall(r'([\w-]+)="([^"]*)"', lm.group(0)))
            if at.get('class') in cls_hidden:
                continue
            segs.append((float(at['x1']), float(at['y1']), float(at['x2']), float(at['y2'])))
        for pm in re.finditer(r'<path\b[^>]*/>', inner):
            at = dict(re.findall(r'([\w-]+)="([^"]*)"', pm.group(0)))
            if at.get('class') in cls_hidden:
                continue
            d = at.get('d', '')
            if not d.startswith('M'):
                continue
            pts = B.sample_d(d)
            if len(pts) >= 2 and math.hypot(pts[-1][0]-pts[0][0], pts[-1][1]-pts[0][1]) > 1:
                segs.append((pts[0][0], pts[0][1], pts[-1][0], pts[-1][1]))

    # ===== 孤立短段过滤(游离stub, 如22号线在建残段) =====
    def _ends(s):
        return [(s[0], s[1]), (s[2], s[3])]
    keep = []
    for i, s in enumerate(segs):
        lonely = True
        for j, t in enumerate(segs):
            if i == j: continue
            for ex, ey in _ends(s):
                if min(math.hypot(ex-ox, ey-oy) for ox, oy in _ends(t)) <= 31:
                    lonely = False; break
            if not lonely: break
        if not lonely:
            keep.append(s)
        else:
            print('  过滤游离段 (%.1f,%.1f)-(%.1f,%.1f)' % s)
    segs = keep

    # ===== 链化(端点聚类成图, 从叶子走全链; 贪心死端会断链——广佛线教训) =====
    nodes = []          # 节点=聚类后的端点
    def node_of(x, y):
        for i, (nx, ny) in enumerate(nodes):
            if math.hypot(nx-x, ny-y) <= 4.0:
                return i
        nodes.append((x, y)); return len(nodes)-1
    adj = {}            # 节点->[(段索引, 端点侧)]
    for si, s in enumerate(segs):
        a, b = node_of(s[0], s[1]), node_of(s[2], s[3])
        adj.setdefault(a, []).append((si, 0))
        adj.setdefault(b, []).append((si, 1))
    leaves = sorted([n for n, v in adj.items() if len(v) == 1])
    start = leaves[0] if leaves else 0
    chain, used = [], [False]*len(segs)
    cur, prev_side = start, None
    while True:
        nxt = [(si, side) for si, side in adj.get(cur, []) if not used[si]]
        if not nxt:
            break
        si, side = nxt[0]
        used[si] = True
        s = segs[si]
        if side == 0:   # 本段(x1,y1)在cur -> 定向为 (x2,y2)->(x1,y1) 使段首接cur
            chain.append((s[2], s[3], s[0], s[1]))
            cur = node_of(s[2], s[3])
        else:
            chain.append(s)
            cur = node_of(s[0], s[1])
    if len(chain) != len(segs):
        print('  !! 链化不完整 %d/%d' % (len(chain), len(segs)))
    total = sum(math.hypot(s[2]-s[0], s[3]-s[1]) for s in chain)

    def narc(px, py):
        acc = 0; ba, bd = 0, 1e18
        for s in chain:
            x1, y1, x2, y2 = s
            dx, dy = x2-x1, y2-y1; L2 = dx*dx+dy*dy
            if L2 < 1e-9: continue
            t = max(0, min(1, ((px-x1)*dx+(py-y1)*dy)/L2))
            ddst = math.hypot(x1+t*dx-px, y1+t*dy-py)
            if ddst < bd: bd, ba = ddst, acc+t*math.hypot(dx, dy)
            acc += math.hypot(dx, dy)
        return ba, bd

    def a2xy(a):
        a = max(0, min(a, total)); acc = 0
        for s in chain:
            L = math.hypot(s[2]-s[0], s[3]-s[1])
            if acc+L >= a and L > 0:
                t = (a-acc)/L
                return (s[0]+t*(s[2]-s[0]), s[1]+t*(s[3]-s[1]))
            acc += L
        return (chain[-1][2], chain[-1][3])

    def _badge_half():
        return max(B.badges_data()[_REF]['chip']['w'], B.badges_data()[_REF]['chip']['h']) / 2

    def _tdir(px, py):
        # 终点徽标方向: 沿走廊末端向外(1号线定稿规则: 三点一线)
        best, bd = None, 1e18
        for s in chain:
            x1, y1, x2, y2 = s
            dx, dy = x2-x1, y2-y1; L2 = dx*dx+dy*dy
            if L2 < 1e-9: continue
            t = max(0, min(1, ((px-x1)*dx+(py-y1)*dy)/L2))
            d = math.hypot(x1+t*dx-px, y1+t*dy-py)
            if d < bd: bd, best = d, (dx, dy, L2**0.5, t)
        dx, dy, L, t = best
        ux, uy = dx/L, dy/L
        if t < 0.5: ux, uy = -ux, -uy
        return ux, uy

    def _tdist(tn):
        # 终点徽标距离: 水平终端排到终点标签外侧(标签宽+净距), 竖直终端55
        tx, ty = coords_of.get(tn, (0, 0))
        ux, uy = _tdir(tx, ty)
        if abs(ux) > abs(uy):
            bw = 2*max(B.text_half_width(tn), B.text_half_width(EN.get(tn, ''), zh=False))
            return 10 + bw + 8 + _badge_half() + 6
        return 68

    # ===== 站表 =====
    LD, SD = B.load_metro()
    L = LD[line_zh]
    _REF = L['ref']   # 支线段长循环会重绑L(浮点), 徽标ref必须提前捕获
    sts = list(stations) if stations else list(L['stations'])
    N = len(sts)
    _sts_all = list(sts) + (list(branch['stations']) if branch else [])
    EN = {nm: SD[nm].get('en', '') for nm in _sts_all if nm in SD}
    EN.update(en_extra or {})

    codes = json.load(open(os.path.join(ROOT, 'data/gz-station-codes.json'), encoding='utf-8'))
    lkey = line_zh.replace('号线', '')
    inter = set()
    for s in codes['stations']:
        if any(c['line'] == lkey for c in s['codes']) and len(s['codes']) > 1:
            inter.add(s['name'])

    # ===== 候选圆(走廊上8px内, 本线色或黑) =====
    cand = []
    for cm in re.finditer(r'<circle ([^>]+)/>', src):
        at = dict(re.findall(r'([\w-]+)="([^"]*)"', cm.group(1)))
        try: cx, cy = float(at['cx']), float(at['cy'])
        except: continue
        if cx < 300: continue
        st = cls_stroke.get(at.get('class', ''), None)
        if st not in (color, '#000000'):
            continue
        a, ddst = narc(cx, cy)
        if ddst < 8:
            cand.append((a, cx, cy, st == '#000000'))
    cand.sort()
    # 弧长去重(9px内的同弧圆只留一个)
    dedup = []
    for c in cand:
        if not dedup or c[0]-dedup[-1][0] > 9:
            dedup.append(c)
    cand = dedup

    # ===== 方向/相位选择: 换乘站应落黑圆 =====
    def assign(reverse, phase=0):
        order = sts[::-1] if reverse else sts
        used = [False]*len(cand)
        coords = {}
        for i, nm in enumerate(order):
            exp = total*(i+phase)/(N-1) if N > 1 else 0
            best_j, bd = -1, 45
            for jj, (a, cx, cy, blk) in enumerate(cand):
                if used[jj]: continue
                # 序保持: 候选弧长 >= 上一站弧长-4
                pv = coords.get(order[i-1]) if i else None
                if pv and a < pv[2]-4: continue
                da = abs(a - exp)
                if da < bd: bd, best_j = da, jj
            if best_j >= 0:
                a, cx, cy, blk = cand[best_j]
                used[best_j] = True
                coords[nm] = (cx, cy, a, True)
            else:
                ea = min(max(exp, 0), total)
                x, y = a2xy(ea)
                coords[nm] = (x, y, ea, False)
        return order, coords

    def score(order, coords):
        sc = 0
        for nm in order:
            got_circle = coords[nm][3]
            if nm in inter:
                a, cx, cy, blk = None, None, None, None
                for jj, (aa, cx2, cy2, blk2) in enumerate(cand):
                    if abs(aa-coords[nm][2]) < 0.6: blk = blk2
                if blk: sc += 2
                elif got_circle: sc -= 1  # 换乘站配到色圆
            else:
                if got_circle: sc += 1
        if not loop:
            if coords[order[0]][2] < 30: sc += 1
            if coords[order[-1]][2] > total-30: sc += 1
        return sc

    best = None
    phases = list(range(N)) if loop else [0]
    for rev in (False, True):
        for ph in phases:
            order, coords = assign(rev, ph)
            sc = score(order, coords)
            if best is None or sc > best[0]:
                best = (sc, order, coords, rev, ph)
    sc, order, coords, rev, ph = best
    print('%s 组%s: %d段链%0.fpx 圆%d/%d 分%d 方向%s 相位%d' % (line_zh, gid, len(chain), total, sum(1 for v in coords.values() if v[3]), N, sc, '反' if rev else '正', ph))
    order = list(sts)  # V1: 卡内文档序=metro-data真值序(方向选择只作用于弧长对位)

    # ===== 定位覆盖 =====
    if overrides:
        for nm, xy in overrides.items():
            if nm in coords:
                a, d2 = narc(xy[0], xy[1])
                coords[nm] = (xy[0], xy[1], a, True)
                print('  覆盖 %s -> %s' % (nm, xy))

    cxy = [(coords[nm][0], coords[nm][1]) for nm in order]

    # ===== 支线(如14号线知识城线): 独立链弧长定位 + 并入卡 =====
    bsegs = None
    if branch:
        bsegs = [tuple(float(v) for v in s) for s in branch['segs']]
        border = list(branch['stations'])
        bacc = 0.0; bsadd = []
        for s in bsegs:
            L = math.hypot(s[2]-s[0], s[3]-s[1]); bsadd.append((bacc, L)); bacc += L
        def ba2xy(a):
            a = max(0.0, min(a, bacc))
            for (a0, L), s in zip(bsadd, bsegs):
                if a0 + L >= a and L > 0:
                    t = (a - a0) / L
                    return (s[0]+t*(s[2]-s[0]), s[1]+t*(s[3]-s[1]))
            return (bsegs[-1][2], bsegs[-1][3])
        bcoords = {}
        bo = (overrides or {})
        Nb = len(border)
        for i, nm in enumerate(border):
            if nm in bo:
                bcoords[nm] = (bo[nm][0], bo[nm][1])
            else:
                bcoords[nm] = ba2xy(bacc*i/(Nb-1) if Nb > 1 else 0.0)
        print('  支线: %d站 %d段 %0.fpx' % (Nb, len(bsegs), bacc))
        # 发射序(V1真值序): 主链锚站前段 + 支线(去锚) + 主链余段
        anch = branch.get('anchor', border[0])
        ai = order.index(anch) if anch in order else -1
        emit = order[:ai+1] + border[1:] + order[ai+1:]
        epos = {}
        for nm in order:
            epos[nm] = (coords[nm][0], coords[nm][1])
        for nm in border[1:]:
            epos[nm] = bcoords[nm]
    else:
        emit = order
        epos = {nm: (coords[nm][0], coords[nm][1]) for nm in order}

    # G3: 走廊端点裁进终点圆(端点取向: 取链首/链尾远离邻段的一端, 原始段序可能反向)
    if not loop:
        if len(chain) > 1:
            def _far(seg, ox, oy):
                d1 = math.hypot(seg[0]-ox, seg[1]-oy)
                d2 = math.hypot(seg[2]-ox, seg[3]-oy)
                return (seg[0], seg[1]) if d1 > d2 else (seg[2], seg[3])
            _term = [_far(chain[0], chain[1][0], chain[1][1]),
                     _far(chain[-1], chain[-2][2], chain[-2][3])]
        else:
            _term = [(chain[0][0], chain[0][1]), (chain[0][2], chain[0][3])]
        def trim(seg_list):
            out = []
            for s in seg_list:
                x1, y1, x2, y2 = s
                for k, (px, py) in enumerate(((x1, y1), (x2, y2))):
                    for ex, ey in _term:
                        if math.hypot(px-ex, py-ey) < 0.5:
                            bx, by = min(cxy, key=lambda c: math.hypot(c[0]-ex, c[1]-ey))
                            if math.hypot(bx-ex, by-ey) < 11: continue
                            ox, oy = (x2-x1, y2-y1) if k == 1 else (x1-x2, y1-y2)
                            Lg = math.hypot(ox, oy) or 1
                            nx, ny = bx+ox/Lg*6, by+oy/Lg*6
                            if k == 0: x1, y1 = nx, ny
                            else: x2, y2 = nx, ny
                out.append((x1, y1, x2, y2))
            return out
        segs = trim(segs)

    gaps = [math.hypot(cxy[i+1][0]-cxy[i][0], cxy[i+1][1]-cxy[i][1]) for i in range(N-1)]
    med = sorted(gaps)[len(gaps)//2] if gaps else 0
    cap = max(2.5*min(med, 80), 110.0)
    print('  站距: 中位%.0f cap%.0f 最大%.0f' % (med, cap, max(gaps) if gaps else 0))
    for i, g in enumerate(gaps):
        if g > cap or g < 3:
            print('  !! %s->%s %.0fpx' % (order[i], order[i+1], g))

    # ===== 组卡 =====
    _all_segs = segs + (bsegs or [])
    _all_xy = [epos[nm] for nm in emit]
    xs = [p[0] for p in _all_xy]+[s[0] for s in _all_segs]+[s[2] for s in _all_segs]
    ys = [p[1] for p in _all_xy]+[s[1] for s in _all_segs]+[s[3] for s in _all_segs]
    coords_of = {k: (v[0], v[1]) for k, v in coords.items()}
    _termi = list((order[0], order[-1]) if not loop else ())
    if branch:
        _termi.append(border[-1])
    for tn in _termi:
        if tn in coords_of:
            tx, ty = coords_of[tn]
            ux, uy = _tdir(tx, ty)
            dist = _tdist(tn)
        else:  # 支线终点
            tx, ty = epos[tn]
            s = bsegs[-1]
            dx, dy = s[2]-s[0], s[3]-s[1]; L = math.hypot(dx, dy) or 1
            ux, uy = dx/L, dy/L
            bw2 = 2*max(B.text_half_width(tn), B.text_half_width(EN.get(tn, ''), zh=False))
            dist = 10 + bw2 + 8 + _badge_half() + 6 if abs(ux) > abs(uy) else 68
        xs += [tx+ux*dist-24, tx+ux*dist+24]
        ys += [ty+uy*dist-14, ty+uy*dist+14]
    _pad = dict(l=115, r=65, t=95, b=85); _pad.update(pad or {})
    x0, x1 = min(xs)-_pad['l'], max(xs)+_pad['r']
    y0, y1 = min(ys)-_pad['t'], max(ys)+_pad['b']
    num = line_zh.replace('号线', '').replace('线', '')
    lname = 'Line %s' % num if line_zh.endswith('号线') else line_zh

    svg = ET.Element('{%s}svg' % NS)
    svg.set('viewBox', '%.1f %.1f %.1f %.1f' % (x0, y0, x1-x0, y1-y0))
    # 真值钉持久化: 门禁G10据此豁免画图几何事实性超距(钉位=原图已验证圆位)
    _pins = sorted(set((overrides or {}).keys()))
    if _pins:
        svg.set('data-pins', ','.join(_pins))
    svg.set('width', str(round(x1-x0))); svg.set('height', str(round(y1-y0)))
    bg = ET.SubElement(svg, '{%s}rect' % NS)
    bg.set('x', str(x0)); bg.set('y', str(y0))
    bg.set('width', str(x1-x0)); bg.set('height', str(y1-y0)); bg.set('fill', '#ffffff')
    if data_multi:  # 多链卡(3号线主+支/12号线双段): 门禁按链口径(G3双连通,G8多chip,V1链序)
        svg.set('data-multi', '1')
        cs = chains or []
        svg.set('data-chains', '|'.join(','.join(ch) for ch in cs))

    ST = 'fill:none;stroke:%s;stroke-width:7;stroke-linecap:round' % color
    gc = ET.SubElement(svg, '{%s}g' % NS); gc.set('id', '走廊')
    for s in _all_segs:
        ln = ET.SubElement(gc, '{%s}line' % NS)
        ln.set('x1', '%.2f' % s[0]); ln.set('y1', '%.2f' % s[1])
        ln.set('x2', '%.2f' % s[2]); ln.set('y2', '%.2f' % s[3])
        ln.set('style', ST)

    go = ET.SubElement(svg, '{%s}g' % NS); go.set('id', '站圆')
    for nm in emit:
        cx, cy = epos[nm]
        c = ET.SubElement(go, '{%s}circle' % NS)
        c.set('cx', '%.1f' % cx); c.set('cy', '%.1f' % cy); c.set('r', '4.5')
        c.set('data-nm', nm); c.set('style', 'fill:#FFFFFF;stroke:%s;stroke-width:2' % color)

    pl = B.place_labels(emit, _all_xy, _all_segs, EN)
    plmap = {lb['nm']: lb for lb in pl}

    gb = ET.SubElement(svg, '{%s}g' % NS); gb.set('id', '线路徽标')
    _bw, _bh, _bs = B.badge_full_size(_REF)
    gb.append(B.make_badge_official(_REF, color, x1 - 16 - _bw, y0 + 36, _bs, 'full'))
    if not loop:
        # 终点数字块(2026-10-21 方位统一): 徽标在 终点圆->终点文字 连线延长线上、背离圆点
        # 一侧, 与文字块居中(横向连线同y横排/竖向连线同x竖排), 净距3px(竖向口径=末行基线+2.5)
        _chh = B.badges_data()[_REF]['chip']['h'] / 2
        _chw = B.badges_data()[_REF]['chip']['w'] / 2
        _chip_boxes = []
        def _chip_xy(tn):
            lb = plmap[tn]
            tx, ty = epos[tn]
            lcx, lcy = (lb['bx0'] + lb['bx1']) / 2, (lb['by0'] + lb['by1']) / 2
            if abs(lcx - tx) > abs(lcy - ty):  # 横向连线: 徽标横排(同y居中)
                cx = lb['bx1'] + 3.0 + _chw if lcx > tx else lb['bx0'] - 3.0 - _chw
                cy = lcy
            else:  # 竖向连线: 与终点文字同x居中(净距3=末行基线+2.5口径)
                cx = lcx
                cy = lb['by1'] + 5.5 + _chh \
                    if lcy > ty else lb['by0'] - 3.0 - _chh
            _chip_boxes.append((cx - _chw, cy - _chh, cx + _chw, cy + _chh))
            return cx, cy
        for tn in (order[0], order[-1]):
            cx, cy = _chip_xy(tn)
            gb.append(B.make_badge_official(_REF, color, cx, cy, 1.0, 'chip'))
        if branch:
            cx, cy = _chip_xy(border[-1])
            gb.append(B.make_badge_official(_REF, color, cx, cy, 1.0, 'chip'))
        if _chip_boxes:  # 数字块可越过既定pad(横向终点贴卡缘), 卡框随盒外扩
            nx0, ny0 = min(b[0] for b in _chip_boxes) - 12, min(b[1] for b in _chip_boxes) - 12
            nx1, ny1 = max(b[2] for b in _chip_boxes) + 12, max(b[3] for b in _chip_boxes) + 12
            if nx0 < x0 or ny0 < y0 or nx1 > x1 or ny1 > y1:
                x0, y0 = min(x0, nx0), min(y0, ny0)
                x1, y1 = max(x1, nx1), max(y1, ny1)
                svg.set('viewBox', '%.1f %.1f %.1f %.1f' % (x0, y0, x1-x0, y1-y0))
                svg.set('width', str(round(x1-x0))); svg.set('height', str(round(y1-y0)))
                bg.set('x', str(x0)); bg.set('y', str(y0))
                bg.set('width', str(x1-x0)); bg.set('height', str(y1-y0))
    gl = ET.SubElement(svg, '{%s}g' % NS); gl.set('id', '站名标注')
    gl.set('font-family', "'Microsoft YaHei', 'PingFang SC', sans-serif")
    for lb in pl:
        zx = (lb['bx0']+lb['bx1'])/2; zy = lb['by0']+11
        t = ET.SubElement(gl, '{%s}text' % NS)
        t.set('x', '%.1f' % zx); t.set('y', '%.1f' % zy)
        t.set('text-anchor', 'middle'); t.set('font-size', '10.5'); t.set('font-weight', '500')
        t.set('fill', '#1a1a1a'); t.text = lb['nm']
        if lb['en']:
            sp = B.split_en(lb['en'], lb['nm'])
            te = ET.SubElement(gl, '{%s}text' % NS)
            te.set('x', '%.1f' % zx); te.set('y', '%.1f' % (lb['by0'] + 18.5))  # EN1紧随中文(Δ7.5<12, G5配对)
            te.set('text-anchor', 'middle'); te.set('font-size', '5.5'); te.set('font-family', 'Arial, sans-serif'); te.set('fill', '#444444')
            te.text = sp[0] if sp else lb['en']
            if sp:  # 第二行英文: 行距6.5
                te2 = ET.SubElement(gl, '{%s}text' % NS)
                te2.set('x', '%.1f' % zx); te2.set('y', '%.1f' % (lb['by0'] + 25.0))
                te2.set('text-anchor', 'middle'); te2.set('font-size', '5.5'); te2.set('fill', '#444444')
                te2.text = sp[1]

    out = os.path.join(ROOT, outpath) if outpath else os.path.join(ROOT, 'assets/lines/line-%s.svg' % line_zh)
    ET.ElementTree(svg).write(out, encoding='unicode', xml_declaration=False)

    R = run_gates(out, expect_n=N + (len(branch['stations'])-1 if branch else 0), chains=chains, pins=set((overrides or {}).keys()))
    npass = sum(o for _, _, o, _ in R)
    print('  门禁: %d/%d' % (npass, len(R)))
    for no, nm, o, dt in R:
        if not o:
            print('  %s %s' % (no, dt[:110]))

    vb = [float(v) for v in svg.get('viewBox').split()]
    W, H = round(vb[2]), round(vb[3])  # 原始尺寸渲染(用户明令, 禁400px缩略)
    if not outpath:  # 中间产物(如12号线北段)不写verify页
        cb = int(time.time()*1000)
        html = ('<!DOCTYPE html><html><head><meta charset="UTF-8">'
                '<style>html,body{{margin:0;height:100%;background:#fff;overflow:hidden}}'
                'img{{position:absolute;left:0;top:0}}</style></head><body>'
                '<img id=m src="line-{}.svg?cb={}" width="{}" height="{}"></body></html>').format(line_zh, cb, W, H)
        open(os.path.join(ROOT, 'assets/lines/_verify-%s.html' % line_zh), 'w', encoding='utf-8').write(html)
    return npass == len(R)


def _chains_for(line_zh):
    s = open(os.path.join(ROOT, 'data/metro-data.js'), encoding='utf-8').read()
    d = json.loads(re.search(r'window\.METRO_DATA\s*=\s*(\{.*\})\s*;?\s*$', s, re.S).group(1))
    for L in d['lines']:
        if L['zh'] == line_zh:
            return [list(L['stations'])] + [list(bb) for bb in L.get('branches', [])]
    return None


if __name__ == '__main__':
    line_zh, gid, color = sys.argv[1], sys.argv[2], sys.argv[3]
    loop = '--loop' in sys.argv
    ok = build(line_zh, gid, color, loop=loop, chains=_chains_for(line_zh))
    sys.exit(0 if ok else 1)
