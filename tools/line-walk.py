# -*- coding: utf-8 -*-
"""已知线网沿检测图游走 v3
- 官图序 = 已知序 + 偏移(锚点投票, 处理方向翻转)
- 已知序两个方向扩展, 步进: 方向+绕行比打分
- 首锚选框: 沿线几何方向
输出: data/walk-assign.json
"""
import json
import math
import numpy as np
from collections import defaultdict, Counter

stations = json.load(open('data/multibox-stations.json'))
graph = json.load(open('data/corridor-graph.json'))
known = json.load(open('data/_metro-known.json'))

flat = {}
for si, s in enumerate(stations):
    for bi, b in enumerate(s['boxes']):
        flat[len(flat)+1] = {'bid': len(flat)+1, 'si': si, 'bi': bi,
                             'cx': b['cx'], 'cy': b['cy']}
sadj = defaultdict(dict)
for e in graph['edges']:
    a, b2, c, eu = e['a'], e['b'], e['cost'], e['eu']
    sa, sb = flat[a]['si'], flat[b2]['si']
    if sa == sb or eu < 8:
        continue
    r = c / eu
    for u, v in ((sa, sb), (sb, sa)):
        if r < sadj[u].get(v, 9):
            sadj[u][v] = r

lat0 = np.mean([st['lat'] for st in known['stations']])
KX = 111000*math.cos(math.radians(lat0))
KY = -111000
geo = {st['id']: (st['lon']*KX, st['lat']*KY) for st in known['stations']}

def line_of(ref):
    for l in known['lines']:
        if l['ref'] == ref:
            return l
    return None

osj = json.load(open('data/official-stations.json'))

def seed_ok(x, y, rad=40):
    return any((s['x']-x)**2 + (s['y']-y)**2 <= rad*rad for s in stations)

anchor_seeds = []
for st in osj['1']['stations']:
    if seed_ok(st['x'], st['y']):
        anchor_seeds.append(('1', st['officialSeq'], st['name'], st['x'], st['y']))
print(f'1号线种子自证通过 {sum(1 for a in anchor_seeds if a[0]=="1")}/16')
anchor_seeds += [
    ('8', 14, '文化公园', 1714, 3235), ('6', 8, '文化公园', 1714, 3235),
    ('6', 31, '苏元', 4242, 2362), ('6', 32, '香雪', 4565, 2380),
    ('11', 14, '广州火车站', 2739, 2526), ('5', 6, '广州火车站', 2739, 2526),
    ('2', 16, '广州火车站', 2739, 2526), ('6', 9, '一德路', 1816, 3248),
]
# window-reads: 位置自证 -> 低信锚池(仅无高信锚的线使用)
low_seeds = []
try:
    wr = json.load(open('data/window-reads.json'))
    for rr in wr:
        if not rr.get('read'):
            continue
        for part in rr['read'].split(','):
            part = part.strip()
            if '|' not in part:
                continue
            ln, sq = part.split('|')
            if ln.isdigit() and sq.strip().isdigit() and seed_ok(rr['x'], rr['y']):
                l_ = line_of(ln)
                if l_:
                    low_seeds.append((ln, int(sq), rr['x'], rr['y']))
except Exception as ex:
    print('window-reads skipped:', ex)
# gt-reads: idx -> 位置(gt-mapping), 读数形如 11|09=沙河
try:
    gtr = json.load(open('data/gt-reads.json'))
    gtm = json.load(open('data/gt-mapping.json'))
    for k, v in gtr.items():
        if '=' not in v or '?' in v:
            continue
        rd, nm = v.split('=', 1)
        if '|' not in rd:
            continue
        ln, sq = rd.split('|')
        if ln != '11' or not sq.isdigit():
            continue
        idx = int(k)
        if 1 <= idx <= len(gtm):
            m = gtm[idx-1]
            if seed_ok(m['x'], m['y']):
                anchor_seeds.append((ln, int(sq), nm, m['x'], m['y']))
except Exception as ex:
    print('gt-reads skipped:', ex)

assign = {}
used = {}
report = []

def near_station(x, y, rad=70):
    best, bd = None, 1e18
    for si, s in enumerate(stations):
        d = (s['x']-x)**2 + (s['y']-y)**2
        if d < bd:
            bd, best = d, si
    return best if bd <= rad*rad else None

def free_boxes(si, ref=None):
    out = []
    n_known = None
    for it in flat.values():
        if it['si'] != si:
            continue
        if it['bid'] not in used:
            out.append(it)
    if ref is None:
        return out
    # 已占但未含ref且站容量未满: 可共享
    nm = si_name.get(si)
    lines_here = LINESET.get(nm, set()) if nm else set()
    if len(lines_here) >= 2:
        claims = sum(1 for it in flat.values() if it['si'] == si and it['bid'] in used)
        if claims < len(lines_here):
            for it in flat.values():
                if it['si'] == si and it['bid'] in used and ref not in used[it['bid']]:
                    out.append(it)
    return out

def pick_box(si, from_bid=None, gdx=None, gdy=None, ref=None):
    pool = free_boxes(si, ref)
    if not pool:
        return None
    if gdx is None:
        gdx, gdy = 0.0, 0.0
    gn = math.hypot(gdx, gdy) or 1.0
    s = stations[si]
    def sc(it):
        al = ((it['cx']-s['x'])*gdx + (it['cy']-s['y'])*gdy) / gn
        d = 0.0
        if from_bid is not None:
            fb = flat[from_bid]
            d = -math.hypot(it['cx']-fb['cx'], it['cy']-fb['cy'])
        return d + al*15.0
    return max(pool, key=sc)['bid']

def step(cur_bid, kidx, sts, ref, d, apin=None, prev_col=None):
    si = flat[cur_bid]['si']
    j = kidx + d
    if j < 0 or j >= len(sts):
        return None, 0, None
    nc, nn = sts[kidx], sts[j]
    if nc not in geo or nn not in geo:
        return None, 0, None
    gx0, gy0 = geo[nc]
    gx1, gy1 = geo[nn]
    dx, dy = gx1-gx0, gy1-gy0
    dgeo = math.hypot(dx, dy)
    if dgeo < 1:
        return None, 0, None
    cands = []
    for sj, ratio in sadj[si].items():
        nmj = si_name.get(sj)
        if nmj is not None and ref not in LINESET.get(nmj, set()):
            continue
        bx, by = stations[sj]['x'], stations[sj]['y']
        vx, vy = bx-flat[cur_bid]['cx'], by-flat[cur_bid]['cy']
        dr = math.hypot(vx, vy)
        if dr > 1000 or dr < 5 or ratio > 1.9:
            continue
        cosang = (vx*dx+vy*dy)/(dr*dgeo)
        expect = dgeo*SCALE
        dpen = abs(math.log(max(dr, 1)/max(expect, 1)))
        ap = apin.get(nn) if apin else None
        apen = math.hypot(bx-ap[0], by-ap[1]) if ap else 0.0
        cont = col_sim(SCOLOR.get((si, sj)), prev_col) if prev_col is not None else 0.0
        cands.append((cosang-0.5*ratio-0.9*dpen-apen/30.0+1.1*cont, cosang, sj, SCOLOR.get((si, sj))))
    cands.sort(key=lambda c: -c[0])
    for sc, cosang, sj, scolor in cands[:5]:
        if cosang <= 0.15:
            break
        ap = apin.get(nn) if apin else None
        if ap and math.hypot(stations[sj]['x']-ap[0], stations[sj]['y']-ap[1]) > 55:
            continue
        if free_boxes(sj, ref):
            bid = pick_box(sj, cur_bid, dx, dy, ref)
            if bid is not None:
                return (bid, 1, scolor)
        elif not free_boxes(sj, ref):
            # 空框被占/漏检: 跳过该站再走一步(2步地理向量)
            dx2, dy2 = 2*dx, 2*dy
            cands2 = []
            for sk, r2 in sadj[sj].items():
                if sk == si:
                    continue
                bx, by = stations[sk]['x'], stations[sk]['y']
                vx, vy = bx-flat[cur_bid]['cx'], by-flat[cur_bid]['cy']
                dr = math.hypot(vx, vy)
                if dr > 1600 or dr < 5 or r2 > 2.4:
                    continue
                ca2 = (vx*dx2+vy*dy2)/(dr*dgeo*2)
                expect2 = dgeo*2*SCALE
                dpen2 = abs(math.log(max(dr, 1)/max(expect2, 1)))
                cands2.append((ca2-0.5*r2-0.9*dpen2, ca2, sk))
            cands2.sort(key=lambda c: -c[0])
            for sc2, ca2, sk in cands2[:2]:
                if ca2 > 0.25 and free_boxes(sk):
                    bid = pick_box(sk, cur_bid, dx, dy, ref)
                    if bid is not None:
                        return (bid, 2, SCOLOR.get((sj, sk)))
    return None, 0, None

def resolve_anchors_sts(ref, seed_list, sts):
    out = []
    for oseq, name, x, y in seed_list:
        if name is None:
            si = near_station(x, y)
            if si is not None and si_name.get(si) in sts:
                out.append((oseq, sts.index(si_name[si]), si))
            continue
        if name not in sts:
            continue
        si = near_station(x, y)
        if si is None:
            continue
        out.append((oseq, sts.index(name), si))
    return out

def resolve_anchors(ref, seed_list):
    l = line_of(ref)
    if not l:
        return []
    return resolve_anchors_sts(ref, seed_list, l['stations'])

ORDER = ['1', '2', '6', '8', '5', '11', '22', '7', '3', '4', '9', '13', '14', '18', '21', '12', '10', 'GF', 'APM']
seeds_by_line = defaultdict(list)
for ln, sq, nm, x, y in anchor_seeds:
    seeds_by_line[ln].append((sq, nm, x, y))

def shape_ok(walk, sts):
    """走线折线 vs 地理折线 Procrustes: 归一后平均点距 < 0.42*线展幅"""
    ks = sorted(walk)
    if len(ks) < 4:
        return True
    P = np.array([[flat[walk[k]]['cx'], flat[walk[k]]['cy']] for k in ks], float)
    G = []
    for k in ks:
        g = geo.get(sts[k])
        if g is None:
            return True
        G.append(g)
    G = np.array(G, float)
    for A in (P, G):
        A -= A.mean(0)
        A /= (np.linalg.norm(A, axis=1).max() or 1)
    d = np.linalg.norm(P-G, axis=1).mean()
    return d < 0.42


def try_walks(ref, l, anc, apin=None, sts=None):
    """每个锚点尝试起步, 取覆盖最大且不违背oseq锚的最长走线"""
    if sts is None:
        sts = l['stations']
    offs = Counter(o-k for o, k, si in anc if o is not None)
    off = offs.most_common(1)[0][0] if offs else None
    best = None
    for o, k, si in sorted(anc, key=lambda a: (a[1] is None, a[1])):
        if ref == '14':
            print('[dbg14] anchor k=%s si=%s free=%d' % (k, si, len(free_boxes(si, ref))))
        if not free_boxes(si, ref):
            continue
        ka, kb = max(k-1, 0), min(k+1, len(sts)-1)
        g0, g1 = geo.get(sts[ka]), geo.get(sts[kb])
        kdx = gdy = None
        if g0 and g1:
            kdx, gdy = g1[0]-g0[0], g1[1]-g0[1]
        bid0 = pick_box(si, None, kdx, gdy, ref)
        if bid0 is None:
            continue
        walk = {k: bid0}
        DBG = (ref == '5')
        if DBG:
            print(f'  [dbg5] start k={k} {sts[k]} bid{bid0} 站{flat[bid0]["si"]}')
        for d in (1, -1):
            k2, bid = k, bid0
            pcol = None
            for _ in range(len(sts)+2):
                nxt, kd, ncol = step(bid, k2, sts, ref, d, apin, pcol)
                if DBG:
                    tgt = sts[k2+d] if 0 <= k2+d < len(sts) else '?'
                    print(f'  [dbg5] d{d} {sts[k2]} -> {tgt}: {"bid"+str(nxt) if nxt else "FAIL"}')
                if not nxt:
                    break
                k2 += d*kd
                if k2 < 0 or k2 >= len(sts) or k2 in walk or nxt in walk.values():
                    break
                walk[k2] = nxt
                bid = nxt
                pcol = ncol
        # 锚违背检查
        viol = 0
        for o2, k2, si2 in anc:
            if o2 is None:
                continue
            if k2 in walk:
                if flat[walk[k2]]['si'] != si2 or k2 + off != o2:
                    viol += 1
            else:
                viol += 1 if off is not None else 0
        sok = shape_ok(walk, sts)
        score = (len(walk) - 5*viol + (4 if sok else -6), -viol, len(walk))
        if best is None or score > best[0]:
            best = (score, walk, off, viol)
    return best

# ---- 距离尺度标定 ----
def calib_scale():
    pts = []
    byline = defaultdict(list)
    for ln, sq, nm, x, y in anchor_seeds:
        byline[ln].append((sq, nm, x, y))
    for ln, lst in byline.items():
        l = line_of(ln)
        if not l:
            continue
        sts = l['stations']
        lst = [t for t in lst if t[1] is not None]
        lst.sort(key=lambda t: t[0])
        for (s1, n1, x1, y1), (s2, n2, x2, y2) in zip(lst, lst[1:]):
            if n1 in sts and n2 in sts and sts.index(n2) == sts.index(n1)+1                and n1 in geo and n2 in geo:
                dg = math.hypot(geo[n2][0]-geo[n1][0], geo[n2][1]-geo[n1][1])
                dr = math.hypot(x2-x1, y2-y1)
                if dg > 300:
                    pts.append(dr/dg)
    return float(np.median(pts)) if pts else 0.17

SCALE = calib_scale()
print(f'尺度标定: {SCALE:.5f} px/m')
anchor_pos = {}
for ln, sq, nm, x, y in anchor_seeds:
    anchor_pos.setdefault(nm, (x, y))

station_lines_known = {st['id']: st['lines'] for st in known['stations']}
LINESET = {st['id']: set(st['lines']) for st in known['stations']}

# 手工锚钳制(仅这些)
MANUAL_PINCH = {'文化公园': (1714, 3235), '广州火车站': (2739, 2526), '一德路': (1816, 3248)}

_ec = json.load(open('data/edge-colors.json'))
ECOLOR = {}
for k, v in _ec.items():
    a, b2 = map(int, k.split(','))
    ECOLOR[(a, b2)] = tuple(v) if v else None
    ECOLOR[(b2, a)] = tuple(v) if v else None

SCOLOR = {}
for _e in graph['edges']:
    _a, _b, _c, _eu = _e['a'], _e['b'], _e['cost'], _e['eu']
    _sa, _sb = flat[_a]['si'], flat[_b]['si']
    if _sa == _sb:
        continue
    _r = _c/_eu
    _k = (_sa, _sb)
    if _r < sadj[_sa].get(_sb, 9):
        col = ECOLOR.get((_a, _b))
        if col is not None:
            SCOLOR[_k] = col

def col_sim(c1, c2):
    if c1 is None or c2 is None:
        return 0.0
    return max(0.0, 1.0 - float(np.linalg.norm(np.array(c1)-np.array(c2)))/90.0)

assign = {}   # bid -> (ref, seq, name)  (bid可多线共享: 以 assign_m 记录)
assign_m = []  # [(bid, ref, seq, name)]
used = {}     # bid -> set(ref)
done = {}     # ref -> True
clean0 = {}   # ref -> viol==0
si_name = {}  # 站索引 -> 已贴站名
report = []

def fit_global_affine():
    P, G = [], []
    for ln, sq, nm, x, y in anchor_seeds:
        if nm in geo:
            P.append([x, y])
            G.append([geo[nm][0], geo[nm][1]])
    P, G = np.array(P, float), np.array(G, float)
    A = np.hstack([G, np.ones((len(G), 1))])
    sx, *_ = np.linalg.lstsq(A, P[:, 0], rcond=None)
    sy, *_ = np.linalg.lstsq(A, P[:, 1], rcond=None)
    return np.concatenate([sx, sy])

AFF = fit_global_affine()

def geo_resid(name, x, y):
    g = geo.get(name)
    if g is None:
        return 0.0
    px = AFF[0]*g[0] + AFF[1]*g[1] + AFF[2]
    py = AFF[3]*g[0] + AFF[4]*g[1] + AFF[5]
    return math.hypot(px-x, py-y)

def validate_assign(assign, used, si_name, thresh=330):
    """地理残差大的贴名作废; 返回作废数"""
    bad = []
    for bid, (ref, sq, nm) in list(assign.items()):
        it = flat[bid]
        r = geo_resid(nm, it['cx'], it['cy'])
        if r > thresh:
            bad.append((bid, ref, sq, nm, int(r)))
    for bid, ref, sq, nm, r in bad:
        del assign[bid]
        del used[bid]
        si = flat[bid]['si']
        if si_name.get(si) == nm:
            del si_name[si]
    return bad

def harvest(prev_ok):
    """prev_ok: [(bid,ref,seq,name)] 干净线 -> 各线新锚"""
    out = defaultdict(list)
    for bid, r2, s2, n2 in prev_ok:
        for ln in station_lines_known.get(n2, []):
            if ln != r2 and ln in ORDER and not done.get(ln):
                out[ln].append(n2)
    return out

ORDER = ['1', '6', '8', '2', '5', '11', '22', '3', '7', '4', '9', '13', '14', '18', '21', '12', '10', 'GF', 'APM']

for ROUND in range(5):
    report.append(f'== round {ROUND} ==')
    harvested = harvest([t for t in assign_m if done.get(t[1]) and clean0.get(t[1])])
    progressed = False
    for ref in ORDER:
        if done.get(ref):
            continue
        l = line_of(ref)
        if not l:
            done[ref] = True
            continue
        sts = l['stations']
        best_all = None
        for sts in (l['stations'], l['stations'][::-1]):
            anc = resolve_anchors_sts(ref, seeds_by_line.get(ref, []), sts)
            if not any(o is not None for o, k, si in anc):
                for ln, sq, x, y in low_seeds:
                    if ln == ref:
                        si = near_station(x, y)
                        if si is not None and si_name.get(si) in sts:
                            anc.append((sq, sts.index(si_name[si]), si))
            for nm in harvested.get(ref, []):
                if nm in sts:
                    for bid, r2, s2, n2 in assign_m:
                        if n2 == nm and r2 != ref:
                            anc.append((None, sts.index(nm), flat[bid]['si']))
                            break
            apin = {}
            for sq2, nm2, x2, y2 in seeds_by_line.get(ref, []):
                if nm2 in sts:
                    apin[nm2] = (x2, y2)
            for bid, (r2, s2, n2) in []:
                pass
            for bid, r2, s2, n2 in []:
                pass
            best = try_walks(ref, l, anc, apin, sts)
            if best is None:
                continue
            _, walk, off, viol = best
            cov = len(walk)
            if best_all is None or (cov - 5*viol) > (best_all[4] - 5*best_all[2]) + 5:
                best_all = (walk, off, viol, sts, cov)
        if best_all is None:
            dbg = ', '.join('无可用朝向' for _ in range(1))
            report.append(f'{ref}: 起步失败 [{dbg}]')
            continue
        walk, off, viol, sts, cov = best_all
        if off is None:
            off = 1
        if viol:
            for o2, k2, si2 in anc:
                if o2 is not None and k2 in walk and k2 + off != o2:
                    report.append(f'  {ref}违锚: {sts[k2]} 官方{o2} 走线{k2+off}')
        # 锚定段裁剪: 起点锚必真; 走到第一个身份不符的锚前停下
        anchor_ks = {k2: si2 for o2, k2, si2 in anc if o2 is not None}
        ks_ok = []
        for k2 in sorted(walk):
            if k2 in anchor_ks:
                if flat[walk[k2]]['si'] != anchor_ks[k2] or (off is not None and k2 + off != dict((o3, None) for o3 in [0]).get(0, k2) and False):
                    if flat[walk[k2]]['si'] != anchor_ks[k2]:
                        break
            ks_ok.append(k2)
        # 双向: 上述只裁了右侧; 左侧从起点锚向外同样裁
        anchor_start = None
        for k2 in sorted(walk):
            if k2 in anchor_ks and flat[walk[k2]]['si'] == anchor_ks[k2]:
                anchor_start = k2
                break
        if anchor_start is not None:
            lo = anchor_start
            for k2 in sorted(ks_ok):
                if k2 < anchor_start:
                    lo = k2
                else:
                    break
            # 左侧也需锚验证: 保守只保留 anchor_start..ks_ok尾
            walk = {k2: walk[k2] for k2 in ks_ok if k2 >= anchor_start}
            cov = len(walk)
            viol = 0
            for k2, si2 in anchor_ks.items():
                if k2 in walk and flat[walk[k2]]['si'] != si2:
                    viol += 1
        clean = (viol == 0 and cov >= 3)
        if cov >= 1:
            progressed = True
        rep = f'{ref}: {cov}/{len(sts)} off={off}'
        rep += '' if clean else f' 违锚{viol}' + (' (作废)' if viol else '')
        report.append(rep)
        if clean:
            done[ref] = True
            clean0[ref] = (viol == 0)
            for k2, bid in walk.items():
                if ref not in used.get(bid, set()):
                    used.setdefault(bid, set()).add(ref)
                    assign_m.append((bid, ref, k2 + off, sts[k2]))
                    si_name[flat[bid]['si']] = sts[k2]
        elif viol == 0 and cov >= 2:
            # 不标done, 但小走线也占框? 不占, 避免污染
            pass
    if not progressed:
        break

print(chr(10).join(report))
json.dump({'assign_m': assign_m},
          open('data/walk-assign.json', 'w'), indent=1)
print(f'已贴(框,线)对 {len(assign_m)} / 框{len(flat)}')
byl = defaultdict(int)
for bid, ref, s, n in assign_m:
    byl[ref] += 1
print('每线:', dict(sorted(byl.items(), key=lambda kv: -kv[1])))
