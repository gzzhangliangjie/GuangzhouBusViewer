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


def build(line_zh, gid, color, loop=False, overrides=None, chains=None):
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

    # ===== 组几何 =====
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

    # ===== 链化 =====
    rem = list(segs); chain = []
    s0 = min(rem, key=lambda s: min(s[0], s[2]))
    chain.append(s0); rem.remove(s0)
    cur = (s0[2], s0[3]) if (s0[0], s0[1]) <= (s0[2], s0[3]) else (s0[0], s0[1])
    while rem:
        best, bd = None, 31
        for s in rem:
            for pe in ((s[0], s[1]), (s[2], s[3])):
                ddst = math.hypot(pe[0]-cur[0], pe[1]-cur[1])
                if ddst < bd: bd, best = ddst, (s, pe)
        if not best: break
        s, pe = best; rem.remove(s)
        if math.hypot(s[0]-pe[0], s[1]-pe[1]) < 1:
            chain.append(s); cur = (s[2], s[3])
        else:
            chain.append((s[2], s[3], s[0], s[1])); cur = (s[0], s[1])
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

    # ===== 站表 =====
    LD, SD = B.load_metro()
    L = LD[line_zh]
    sts = list(L['stations'])
    N = len(sts)
    EN = {nm: SD[nm].get('en', '') for nm in sts if nm in SD}

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

    # ===== 定位覆盖 =====
    if overrides:
        for nm, xy in overrides.items():
            if nm in coords:
                a, d2 = narc(xy[0], xy[1])
                coords[nm] = (xy[0], xy[1], a, True)
                print('  覆盖 %s -> %s' % (nm, xy))

    cxy = [(coords[nm][0], coords[nm][1]) for nm in order]

    # G3: 走廊端点裁进终点圆
    if not loop:
        def trim(seg_list):
            out = []
            for s in seg_list:
                x1, y1, x2, y2 = s
                for k, (px, py) in enumerate(((x1, y1), (x2, y2))):
                    for ex, ey in ((chain[0][0], chain[0][1]), (chain[-1][2], chain[-1][3])):
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
    xs = [p[0] for p in cxy]+[s[0] for s in segs]+[s[2] for s in segs]
    ys = [p[1] for p in cxy]+[s[1] for s in segs]+[s[3] for s in segs]
    x0, x1 = min(xs)-115, max(xs)+65
    y0, y1 = min(ys)-95, max(ys)+85
    num = line_zh.replace('号线', '').replace('线', '')
    lname = 'Line %s' % num if line_zh.endswith('号线') else line_zh

    svg = ET.Element('{%s}svg' % NS)
    svg.set('viewBox', '%.1f %.1f %.1f %.1f' % (x0, y0, x1-x0, y1-y0))
    svg.set('width', str(round(x1-x0))); svg.set('height', str(round(y1-y0)))
    bg = ET.SubElement(svg, '{%s}rect' % NS)
    bg.set('x', str(x0)); bg.set('y', str(y0))
    bg.set('width', str(x1-x0)); bg.set('height', str(y1-y0)); bg.set('fill', '#ffffff')

    ST = 'fill:none;stroke:%s;stroke-width:7;stroke-linecap:round' % color
    gc = ET.SubElement(svg, '{%s}g' % NS); gc.set('id', '走廊')
    for s in segs:
        ln = ET.SubElement(gc, '{%s}line' % NS)
        ln.set('x1', '%.2f' % s[0]); ln.set('y1', '%.2f' % s[1])
        ln.set('x2', '%.2f' % s[2]); ln.set('y2', '%.2f' % s[3])
        ln.set('style', ST)

    go = ET.SubElement(svg, '{%s}g' % NS); go.set('id', '站圆')
    for nm, (cx, cy) in zip(order, cxy):
        c = ET.SubElement(go, '{%s}circle' % NS)
        c.set('cx', '%.1f' % cx); c.set('cy', '%.1f' % cy); c.set('r', '4.5')
        c.set('data-nm', nm); c.set('style', 'fill:#FFFFFF;stroke:%s;stroke-width:2' % color)

    gb = ET.SubElement(svg, '{%s}g' % NS); gb.set('id', '线路徽标')
    gb.append(B.make_badge(color, num, '号线' if line_zh.endswith('号线') else '', lname, x1-96, y0+36))
    if not loop:
        for tn in (order[0], order[-1]):
            tx, ty = coords[tn][0], coords[tn][1]
            gb.append(B.make_badge(color, num, '号线' if line_zh.endswith('号线') else '', lname, tx, ty-55, 0.6))

    pl = B.place_labels(order, cxy, segs, EN)
    gl = ET.SubElement(svg, '{%s}g' % NS); gl.set('id', '站名标注')
    gl.set('font-family', "'Microsoft YaHei', 'PingFang SC', sans-serif")
    for lb in pl:
        zx = (lb['bx0']+lb['bx1'])/2; zy = lb['by0']+11
        t = ET.SubElement(gl, '{%s}text' % NS)
        t.set('x', '%.1f' % zx); t.set('y', '%.1f' % zy)
        t.set('text-anchor', 'middle'); t.set('font-size', '10.5'); t.set('font-weight', '500')
        t.set('fill', '#1a1a1a'); t.text = lb['nm']
        if lb['en']:
            te = ET.SubElement(gl, '{%s}text' % NS)
            te.set('x', '%.1f' % zx); te.set('y', '%.1f' % lb['by1'])
            te.set('text-anchor', 'middle'); te.set('font-size', '5.5'); te.set('fill', '#444444')
            te.text = lb['en']

    out = os.path.join(ROOT, 'assets/lines/line-%s.svg' % line_zh)
    ET.ElementTree(svg).write(out, encoding='unicode', xml_declaration=False)

    R = run_gates(out, expect_n=N, chains=chains)
    npass = sum(o for _, _, o, _ in R)
    print('  门禁: %d/%d' % (npass, len(R)))
    for no, nm, o, dt in R:
        if not o:
            print('  %s %s' % (no, dt[:110]))

    vb = [float(v) for v in svg.get('viewBox').split()]
    W, H = round(vb[2]), round(vb[3])  # 原始尺寸渲染(用户明令, 禁400px缩略)
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
