# -*- coding: utf-8 -*-
"""单线卡片结构验收门禁（v6 卡片格式：g[id=走廊/站圆/线路徽标/站名标注]）

用法:
    python tools/verify_card.py assets/lines/line-2号线.svg [--expect-n 24]
    python -m pytest tests -q          # tests/ 调用本模块同名门禁

门禁判据与出处详见 docs/card-acceptance.md；每条门禁对应一次真实翻车。
仅做结构层(T0)检查，不渲染；像素层(T1)见文档第二节。
"""
import os
import re
import sys
import math
import argparse
import xml.etree.ElementTree as ET

try:
    from PIL import ImageFont
    F_ZH = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 21)  # 2x 后除2 = 10.5pt 宽
    F_EN = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 11)  # 2x 后除2 = 5.5pt 宽
except Exception:
    F_ZH = F_EN = None

NS = 'http://www.w3.org/2000/svg'
ZORDER = ['走廊', '站圆', '线路徽标', '站名标注']  # z序铁律：走廊底→圆→徽标→名(最上)
G = 10.0            # 放置算法净距基准
CLR_MIN = G - 1.5   # 标签盒到走廊实测净距下限(=放置器push容差, 门禁不得严于算法保证)
ON_LINE_MAX = 1.5   # 铁律3: 站圆严格在线上
TERM_CLIP = 12.0    # 终点裁剪: 走廊端点离终点圆距离上限


def text_half_width(s, zh=True):
    """PIL 2x 实测半宽(msyh 21px↔显示10.5 / 11px↔显示5.5)：先除2回到显示宽度，再除2取半。"""
    if F_ZH is None:
        return (len(s.encode('gbk', 'ignore')) * (10.5 if zh else 5.5)) / 2
    f = F_ZH if zh else F_EN
    return f.getlength(s) / 4.0


def seg_pt_dist(x1, y1, x2, y2, px, py):
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 < 1e-9:
        return math.hypot(x1 - px, y1 - py)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(x1 + t * dx - px, y1 + t * dy - py)


def rect_seg_clearance(rx0, ry0, rx1, ry1, segs):
    """盒到走廊折线采样净距（与放置算法 clearance 同口径），交叉即 0。"""
    best = 1e18
    for (x1, y1, x2, y2) in segs:
        for i in range(21):
            t = i / 20.0
            px, py = x1 + t * (x2 - x1), y1 + t * (y2 - y1)
            dx = max(rx0 - px, 0.0, px - rx1)
            dy = max(ry0 - py, 0.0, py - ry1)
            best = min(best, math.hypot(dx, dy))
    return best


def load(path):
    root = ET.parse(path).getroot()
    groups = {g.get('id'): g for g in root.iter('{%s}g' % NS) if g.get('id')}
    order = [g.get('id') for g in root if g.tag.endswith('}g') and g.get('id')]

    segs = []
    for el in groups.get('走廊', {}).iter('{%s}line' % NS):
        segs.append((float(el.get('x1')), float(el.get('y1')),
                     float(el.get('x2')), float(el.get('y2'))))

    circles = []
    pos_by_nm = {}
    for el in groups.get('站圆', {}).iter('{%s}circle' % NS):
        circles.append((float(el.get('cx')), float(el.get('cy')), float(el.get('r', '0'))))
        if el.get('data-nm'):
            pos_by_nm[el.get('data-nm')] = (float(el.get('cx')), float(el.get('cy')))

    # zh(10.5)/en(5.5) 配对: 同 x、en 基线在 zh 下方 12 内
    raw = []
    for el in groups.get('站名标注', {}).iter('{%s}text' % NS):
        raw.append({'x': float(el.get('x')), 'y': float(el.get('y')),
                    'fs': float(el.get('font-size', '0')), 't': (el.text or '').strip()})
    labels = []
    for z in [r for r in raw if abs(r['fs'] - 10.5) < 0.01]:
        en = min((r for r in raw if abs(r['fs'] - 5.5) < 0.01
                  and abs(r['x'] - z['x']) < 0.3 and 0 < r['y'] - z['y'] < 12),
                 key=lambda r: r['y'] - z['y'], default=None)
        lb = {'nm': z['t'], 'x': z['x'], 'zy': z['y'],
              'ey': en['y'] if en else None, 'en': en['t'] if en else ''}
        if en:  # 拆行英文第二行: 链式自 en1(同x, 紧随其下一行), 不参与 zh 配对
            en2 = min((r for r in raw if abs(r['fs'] - 5.5) < 0.01
                       and abs(r['x'] - en['x']) < 0.3 and 3 < r['y'] - en['y'] < 10),
                      key=lambda r: r['y'] - en['y'], default=None)
            if en2:
                lb['en2'], lb['ey2'] = en2['t'], en2['y']
        labels.append(lb)
    for lb in labels:  # 重建标签盒(以实测文本为准, 不信放置器内部状态)
        wm = max(text_half_width(lb['nm']), text_half_width(lb['en'], zh=False),
                 text_half_width(lb.get('en2', ''), zh=False))
        lb['box'] = (lb['x'] - wm, lb['zy'] - 11.0, lb['x'] + wm,
                     (lb.get('ey2') or lb['ey'] or lb['zy']) + 2.5)

    badges = []
    for g in groups.get('线路徽标', []):
        db = g.get('data-box')
        if db:  # 官方徽标(v7): 卡片自带缩放后包围盒
            x0, y0, x1, y1 = [float(v) for v in db.split(',')]
            badges.append({'box': (x0, y0, x1, y1), 'scale': 1.0,
                           'mode': g.get('data-badge') or 'full',
                           'chip': tuple(float(v) for v in g.get('data-chip').split(',')) if g.get('data-chip') else None,
                           'ink': g.get('data-ink')})
            continue
        r = g.find('{%s}rect' % NS)
        if r is None:
            continue
        x, y = float(r.get('x')), float(r.get('y'))
        w, h = float(r.get('width')), float(r.get('height'))
        tr = g.get('transform') or ''
        m = re.search(r'translate\(([-\d.]+)[ ,]+([-\d.]+)\)', tr)
        sc = 0.6 if 'scale(0.6)' in tr else (1.0 if not tr else None)
        if sc is None:
            continue
        # 缩放徽标的几何基准是 transform 的平移锚点(通常是缩放中心), 不是 rect 左上角
        cx, cy = (float(m.group(1)), float(m.group(2))) if (m and sc != 1.0) else (x + w / 2, y + h / 2)
        bw, bh = w * sc, h * sc
        badges.append({'box': (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2), 'scale': sc})

    vb = [float(v) for v in root.get('viewBox').split()]
    return {'root': root, 'order': order, 'segs': segs, 'circles': circles,
            'labels': labels, 'badges': badges, 'vb': vb,
            'multi': root.get('data-multi') == '1',
            'card_chains': (root.get('data-chains') or '').split('|') if root.get('data-chains') else None}


def run_gates(path, expect_n=None, chains=None, pins=None):
    # data-pins: 卡片自带真值钉(原图已验证圆位), 与显式参数合并
    _root_pins = None
    try:
        _root_pins = ET.parse(path).getroot().get('data-pins')
    except Exception:
        pass
    if _root_pins:
        pins = set(list(pins or []) + [p for p in _root_pins.split(',') if p])
    """返回 [(门禁号, 名称, ok, detail)]；全过才算过门禁。
    chains: 各链站名序列(主链+支线链), G10 按链内相邻量距(分叉边界不算)
    pins: 真值钉站名集合(原图已验证圆位), G10 对涉及钉位的站距豁免——超距是画图几何
    事实而非错位(8号线西村jog绕行/沙园-宝岗大道被2号线黑圆占位均为此类)"""
    c = load(path)
    segs, circles, labels, badges, vb = c['segs'], c['circles'], c['labels'], c['badges'], c['vb']
    R = []

    def add(no, name, ok, detail=''):
        R.append((no, name, bool(ok), detail))

    # G1 z序铁律: 四组齐全且顺序=走廊→站圆→徽标→名
    idx = [c['order'].index(g) for g in ZORDER if g in c['order']]
    add('G1', 'z序(走廊→圆→徽标→名)',
        len(idx) == 4 and idx == sorted(idx),
        '组序: %s' % '→'.join(c['order']))

    # G2 铁律3: 站圆严格在走廊上
    off = [((nm_x[0], nm_x[1]), min(seg_pt_dist(*s, nm_x[0], nm_x[1]) for s in segs))
           for nm_x in circles]
    worst = max(off, key=lambda t: t[1]) if off else (0, 0)
    add('G2', '站圆在线(≤%.1fpx)' % ON_LINE_MAX,
        all(d <= ON_LINE_MAX for _, d in off),
        '最差 %s 偏 %.2fpx' % (worst[0], worst[1]))

    # G3 铁律4: 走廊单连通、仅两端点游离且都在终点圆内
    parent = list(range(len(segs)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        parent[find(a)] = find(b)

    def key(p):  # 端点聚类键: 0.5px 网格(原始坐标末位舍入差不再裂键)
        return (round(p[0] * 2) / 2, round(p[1] * 2) / 2)

    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            for pi in ((segs[i][0], segs[i][1]), (segs[i][2], segs[i][3])):
                for pj in ((segs[j][0], segs[j][1]), (segs[j][2], segs[j][3])):
                    if math.hypot(pi[0] - pj[0], pi[1] - pj[1]) < 6.0:
                        union(i, j)
    ncomp = len({find(i) for i in range(len(segs))})
    # 端点按邻近(≤0.5px)聚类计数, 网格取整在边界值上会裂键
    reps = []
    vdeg = []
    for s in segs:
        for p in ((s[0], s[1]), (s[2], s[3])):
            hit = next((i for i, r in enumerate(reps) if math.hypot(r[0] - p[0], r[1] - p[1]) < 6.0), None)
            if hit is None:
                reps.append(p)
                vdeg.append(1)
            else:
                vdeg[hit] += 1
    loose = [reps[i] for i, d in enumerate(vdeg) if d == 1]
    loose_ok = all(any(math.hypot(k[0] - cx, k[1] - cy) < TERM_CLIP for cx, cy, _ in circles)
                   for k in loose)
    multi = c['root'].get('data-multi') == '1'  # 12号线: 两段开通实线同图展示
    ok3 = (ncomp == 2 and len(loose) <= 4) if multi else (ncomp == 1 and len(loose) <= 3)
    add('G3', '走廊单连通+终点裁剪', ok3 and loose_ok,
        '%d连通段, %d游离端点%s' % (ncomp, len(loose), '' if loose_ok else '(有端点不在终点圆内)'))

    # G4 站名=站圆=站数
    n = expect_n or len(circles)
    add('G4', '站数一致(圆=中文名=期望%d)' % n,
        len(circles) == len(labels) == n,
        '圆%d 中文名%d' % (len(circles), len(labels)))

    # G5 中文名英文配对完整(结构化站名, 不缺字)
    bad = [lb['nm'] for lb in labels if not lb['en']]
    add('G5', '站名中英配对', not bad, '缺英文: %s' % bad if bad else '全%d对' % len(labels))

    # G6 文字不出框(viewBox 内, 左边距≥10)
    out = []
    for lb in labels:
        x0, y0, x1, y1 = lb['box']
        if x0 < vb[0] + 3 or x1 > vb[0] + vb[2] - 3 or y0 < vb[1] + 3 or y1 > vb[1] + vb[3] - 3:
            out.append(lb['nm'])
    lm = min((lb['box'][0] for lb in labels), default=vb[0]) - vb[0]
    add('G6', '文字不出框+左边距≥10', not out and lm >= 10,
        '出框: %s; 左边距%.0f' % (out or '无', lm))

    # G7 铁律1: 标签不与走廊重叠。中文主名净距≥CLR_MIN(放置规则); 英文行到中线≥4(笔宽3.5+0.5)
    clash = []
    for lb in labels:
        wm_zh = text_half_width(lb['nm'])
        zbox = (lb['x'] - wm_zh, lb['zy'] - 11.0, lb['x'] + wm_zh, lb['zy'] + 1.5)
        clz = rect_seg_clearance(*zbox, segs)
        if clz < CLR_MIN:
            clash.append('%s 中文净距%.1f' % (lb['nm'], clz))
        if lb['ey'] is not None:  # 英文缺失由 G5 报, 此处不崩
            wm_en = text_half_width(lb['en'], zh=False)
            ebox = (lb['x'] - wm_en, lb['ey'] - 5.5, lb['x'] + wm_en, lb['ey'] + 1.5)
            cle = rect_seg_clearance(*ebox, segs)
            if cle < 4.0:
                clash.append('%s 英文净距%.1f' % (lb['nm'], cle))
        if lb.get('ey2') is not None:  # 拆行英文第二行
            wm_e2 = text_half_width(lb.get('en2', ''), zh=False)
            ebox2 = (lb['x'] - wm_e2, lb['ey2'] - 5.5, lb['x'] + wm_e2, lb['ey2'] + 1.5)
            cle2 = rect_seg_clearance(*ebox2, segs)
            if cle2 < 4.0:
                clash.append('%s 英文2行净距%.1f' % (lb['nm'], cle2))
    add('G7', '标签净距(中文≥%.1f 英文≥4.0)' % CLR_MIN, not clash, '; '.join(clash) or '全过')

    # G8 徽标三枚+避让+终点数字块-文字对齐(2026-10-20 全线统一规则:
    # 数字块与文字同x居中≤3, 净间距2~8, 原独立G8b并入)
    bad_al = []
    if badges and all('mode' in b for b in badges):
        # v7 官方徽标: 1 头部(full) + 2~3 终点(chip); 环线仅头部
        nhead = sum(1 for b in badges if b['mode'] == 'header')
        nchip = sum(1 for b in badges if b['mode'] == 'chip')
        multi = c['root'].get('data-multi') == '1'
        ok8 = nhead == 1 and (nchip in (2, 3, 4) if multi else nchip in (2, 3) or nchip == 0)
        why8 = '头%d+终点%d' % (nhead, nchip)
        for bd in badges:
            if bd.get('mode') != 'chip':
                continue
            bx0, by0, bx1, by1 = bd['box']
            ccx = (bx0 + bx1) / 2.0
            ccy = (by0 + by1) / 2.0
            # 配对双口径(2026-10-21): 竖排=数字块与文字同x居中上下邻接; 横排=同y居中左右邻接
            cand = []  # (mode, gap, label)
            for lb in labels:
                lcy = (lb['box'][1] + lb['box'][3]) / 2.0
                if abs(lb['x'] - ccx) <= 60:
                    gb = by0 - lb['box'][3]   # 数字块在文字块下方
                    ga = lb['box'][1] - by1   # 数字块在文字块上方
                    if 0 < gb < 15:
                        cand.append(('v', gb, lb))
                    if 0 < ga < 15:
                        cand.append(('v', ga, lb))
                if abs(lcy - ccy) <= 60:
                    gr = bx0 - lb['box'][2]   # 数字块在文字块右侧
                    glf = lb['box'][0] - bx1  # 数字块在文字块左侧
                    if 0 < gr < 15:
                        cand.append(('h', gr, lb))
                    if 0 < glf < 15:
                        cand.append(('h', glf, lb))
            if not cand:
                bad_al.append('chip@(%.0f,%.0f)无相邻文字' % (ccx, ccy))
                continue
            mode, gap, lb = min(cand, key=lambda t: abs(t[1] - 3.0))
            if mode == 'v':
                dax = abs(ccx - lb['x'])
            else:
                dax = abs(ccy - (lb['box'][1] + lb['box'][3]) / 2.0)
            if dax > 3.0:
                bad_al.append('%s 数字块偏%.1fpx' % (lb['nm'], dax))
            if not (2.0 <= gap <= 8.0):
                bad_al.append('%s 数字块间距%.1fpx' % (lb['nm'], gap))
    else:
        ok8 = (len(badges) in (3, 4) and sum(1 for b in badges if b['scale'] == 0.6) in (2, 3)) or len(badges) == 1  # 环线(11号线)无终点徽标
        why8 = '徽标%d枚' % len(badges)
    def overlap(a, b, m=0.0):
        return not (a[2] < b[0] + m or b[2] + m < a[0] or a[3] < b[1] + m or b[3] + m < a[1])
    for bd in badges:
        for lb in labels:
            if overlap(bd['box'], lb['box']):
                ok8, why8 = False, '徽标压 %s 标签' % lb['nm']
        if rect_seg_clearance(*bd['box'], segs) < 1.0:
            ok8, why8 = False, '徽标压走廊'
    if bad_al:
        ok8 = False
        why8 = (why8 + '; ' if why8 else '') + '; '.join(bad_al)
    add('G8', '徽标+避让+数字块对齐', ok8, why8)

    # G9 铁律2验收: 标签盒不得罩住他站圆(就近归属的操作化判据)
    wrong = []
    for lb in labels:
        x0, y0, x1, y1 = lb['box']
        for cc in circles:
            inside = x0 - 2 < cc[0] < x1 + 2 and y0 - 2 < cc[1] < y1 + 2
            near_own = math.hypot(cc[0] - lb['x'], cc[1] - (lb['zy'] + (lb['ey'] or lb['zy'])) / 2) < 25
            if inside and not near_own:
                wrong.append('%s罩(%.0f,%.0f)' % (lb['nm'], cc[0], cc[1]))
    add('G9', '标签不罩他站圆', not wrong, '; '.join(wrong) or '全过')

    # G10 站距规整: 相邻站圆距 ≤ max(2.5×中位距, 110px) 且全线无超距跳站(2026-10-19 用户投诉
    #     "线路中断/站点距离过大"的制度化拦截——折线乱连/断链必炸此门禁)
    pos_nm = {}
    for cc in c['root'].iter('{%s}circle' % NS):
        if cc.get('data-nm'):
            pos_nm[cc.get('data-nm')] = (float(cc.get('cx')), float(cc.get('cy')))
    if not chains and c.get('card_chains'):
        chains = c['card_chains']  # 多段卡(12号线)自带链序
    if chains:
        chains = [ch.split(',') if isinstance(ch, str) else ch for ch in chains]
        seqs = [[pos_nm[nm] for nm in ch if nm in pos_nm] for ch in chains]
        seq_nm = [[nm for nm in ch if nm in pos_nm] for ch in chains]
    else:
        # 无chains时按卡内文档序取站名(占位序号会让data-pins豁免失效, 14号线支线边界误报教训)
        _doc = [[nm for nm in pos_nm]]
        seqs = [[pos_nm[nm] for nm in ch] for ch in _doc]
        seq_nm = _doc
    gaps = []
    for sq in seqs:
        for u, w in zip(sq, sq[1:]):
            gaps.append(math.hypot(w[0]-u[0], w[1]-u[1]))
    bad_gap = ''
    if gaps:
        med = sorted(gaps)[len(gaps)//2]
        cap = max(2.5*min(med, 80), 110.0)
        over_g = []   # (链号, 序号, 距离) — 真值钉(pins)涉及的站距豁免: 超距=画图几何事实非错位
        for si, sq in enumerate(seqs):
            nms = seq_nm[si]
            for gi, (u, w) in enumerate(zip(sq, sq[1:])):
                g = math.hypot(w[0]-u[0], w[1]-u[1])
                if g > cap and not (pins and (nms[gi] in pins or nms[gi+1] in pins)):
                    over_g.append(g)
        stacked = [i for i, g in enumerate(gaps) if g < 3]
        if over_g:
            bad_gap = '超距%d处 最大%.0fpx (中位%.0f)' % (len(over_g), max(over_g), med)
        elif stacked:
            bad_gap = '堆叠%d处(间距<3px)' % len(stacked)
    add('G10', '站距规整(≤max(2.5×中位,110))', not bad_gap, bad_gap or '中位%.0f 最大%.0f' % (sorted(gaps)[len(gaps)//2] if gaps else 0, max(gaps) if gaps else 0))

    def split_en_text(en, zh):
        if not en or ' ' not in en or text_half_width(en, zh=False) <= 1.5 * text_half_width(zh):
            return [en] if en else []
        best, bd = None, 1e18
        ws = en.split(' ')
        for i in range(1, len(ws)):
            a, b = ' '.join(ws[:i]), ' '.join(ws[i:])
            d = abs(text_half_width(a, zh=False) - text_half_width(b, zh=False))
            if best is None or d < best[0]:
                best = (d, a, b)
        return [best[1], best[2]]

    # G11 标签贴圆距离(2026-10-21 固化): 标签中心到自圆距离 ≤ G + 盒半宽/1 + 18(推进上限)。
    # 盒宽按拆行后最宽行算——旧bw用整条EN, 广州东站52px/华师50px离圆过远(用户点名)
    far_lbl = []
    for lb in labels:
        own = min(((x, y) for (x, y, r) in circles),
                  key=lambda p: math.hypot(p[0] - lb['x'], p[1] - (lb['box'][1] + lb['box'][3]) / 2))
        dist = math.hypot(lb['x'] - own[0], (lb['box'][1] + lb['box'][3]) / 2 - own[1])
        en_lines = split_en_text(lb.get('en', ''), lb['nm'])
        en_hw = max([text_half_width(t, zh=False) for t in en_lines] + [0.0])
        bw_eff = 2 * max(text_half_width(lb['nm']), en_hw)
        if dist > 10.0 + bw_eff / 2 + 18.0:
            far_lbl.append('%s 距圆%.0fpx(上限%.0f)' % (lb['nm'], dist, 10.0 + bw_eff / 2 + 18.0))
    add('G11', '标签贴圆(≤10+盒宽/2+18)', not far_lbl, '; '.join(far_lbl) or '全过')

    # G12 终点文字延长线方位(2026-10-21 固化): 终点标签偏移主轴 = 走廊外向主轴
    # (嘉禾望岗/二沙岛版式; data-multi 特例卡按用户定稿豁免)。对角(比值<1.2)不计
    if multi:
        add('G12', '终点延长线方位', True, 'data-multi 特例卡豁免')
    else:
        bad_term = []
        for bd_ in badges:
            if bd_.get('mode') != 'chip':
                continue
            bx0, by0, bx1, by1 = bd_['box']
            ccx, ccy = (bx0 + bx1) / 2.0, (by0 + by1) / 2.0
            cand = []
            for lb in labels:
                lcy = (lb['box'][1] + lb['box'][3]) / 2.0
                if abs(lb['x'] - ccx) <= 60:
                    g1 = by0 - lb['box'][3]
                    g2 = lb['box'][1] - by1
                    if 0 < g1 < 15 or 0 < g2 < 15:
                        cand.append((abs(g1 - 3.0) + abs(g2 - 3.0), lb))
                if abs(lcy - ccy) <= 60:
                    g1 = bx0 - lb['box'][2]
                    g2 = lb['box'][0] - bx1
                    if 0 < g1 < 15 or 0 < g2 < 15:
                        cand.append((abs(g1 - 3.0) + abs(g2 - 3.0), lb))
            if not cand:
                continue  # 配对失败已由G8报
            _, lb = min(cand)
            ax, ay = min(((x, y) for (x, y, r) in circles),
                         key=lambda p: math.hypot(p[0] - lb['x'], p[1] - (lb['box'][1] + lb['box'][3]) / 2))
            vx = vy = 0.0
            near = sorted(segs, key=lambda s: seg_pt_dist(*s, ax, ay))[:2]
            for s in near:
                d1 = math.hypot(s[0] - ax, s[1] - ay)
                d2 = math.hypot(s[2] - ax, s[3] - ay)
                fx, fy = (s[2], s[3]) if d1 < d2 else (s[0], s[1])
                L2 = math.hypot(fx - ax, fy - ay) or 1.0
                vx += (ax - fx) / L2
                vy += (ay - fy) / L2
            L2 = math.hypot(vx, vy) or 1.0
            uox, uoy = vx / L2, vy / L2
            lcx, lcy = lb['x'], (lb['box'][1] + lb['box'][3]) / 2.0
            odx, ody = lcx - ax, lcy - ay
            r2 = max(abs(uox), abs(uoy)) / max(1e-6, min(abs(uox), abs(uoy)))
            if r2 >= 1.2:
                conn_axis = 'h' if abs(odx) > abs(ody) else 'v'
                ext_axis = 'h' if abs(uox) > abs(uoy) else 'v'
                if conn_axis != ext_axis:
                    bad_term.append('%s 文字方位%s 延长线%s' % (lb['nm'],
                        '横' if conn_axis == 'h' else '竖', '横' if ext_axis == 'h' else '竖'))
        add('G12', '终点延长线方位', not bad_term, '; '.join(bad_term) or '全过')

    # G13 终点贴圆(2026-10-21 固化): 终点圆12px内的走廊游离端必须贴到圆心(≤1.5px)。
    # 香雪6px/番禺广场6px出头小揪教训; 中段微缝(非终点圆附近)不在此列
    def key(p):
        return (round(p[0] * 2) / 2, round(p[1] * 2) / 2)

    deg = {}
    for s in segs:
        for p in ((s[0], s[1]), (s[2], s[3])):
            deg[key(p)] = deg.get(key(p), 0) + 1
    _term_circles = []
    for bd_ in badges:
        if bd_.get('mode') != 'chip':
            continue
        bx0, by0, bx1, by1 = bd_['box']
        ccx, ccy = (bx0 + bx1) / 2.0, (by0 + by1) / 2.0
        cand = []
        for lb in labels:
            lcy = (lb['box'][1] + lb['box'][3]) / 2.0
            if abs(lb['x'] - ccx) <= 60:
                g1 = by0 - lb['box'][3]
                g2 = lb['box'][1] - by1
                if 0 < g1 < 15 or 0 < g2 < 15:
                    cand.append((abs(g1 - 3.0) + abs(g2 - 3.0), lb))
            if abs(lcy - ccy) <= 60:
                g1 = bx0 - lb['box'][2]
                g2 = lb['box'][0] - bx1
                if 0 < g1 < 15 or 0 < g2 < 15:
                    cand.append((abs(g1 - 3.0) + abs(g2 - 3.0), lb))
        if not cand:
            continue
        _, lb = min(cand)
        ax, ay = min(((x, y) for (x, y, r) in circles),
                     key=lambda p: math.hypot(p[0] - lb['x'], p[1] - lcy))
        _term_circles.append((ax, ay))
    bad_stub = []
    for p, n in deg.items():
        if n != 1:
            continue
        for tx, ty in _term_circles:
            d = math.hypot(p[0] - tx, p[1] - ty)
            if 1.5 < d <= 12.0:
                bad_stub.append('端(%0.f,%0.f) 离终点圆%.1fpx' % (p[0], p[1], d))
                break
    add('G13', '终点贴圆(≤1.5px)', not bad_stub, '; '.join(bad_stub[:4]) or '全过')

    # G14 站圆不塌缩(2026-10-21 固化): 任意两站圆间距≥8px。
    # 8号线彩虹桥曾被走链塌到凤凰新村钉位(两圆距离0), 圆点数=文字数由G4把守, 本门禁把守位置
    collapse = []
    for i in range(len(circles)):
        for j in range(i + 1, len(circles)):
            d = math.hypot(circles[i][0] - circles[j][0], circles[i][1] - circles[j][1])
            if d < 8.0:
                collapse.append('第%d/%d圆相距%.1fpx' % (i + 1, j + 1, d))
    add('G14', '站圆不塌缩(≥8px)', not collapse, '; '.join(collapse[:4]) or '全过')

    # G15 密集线交替(2026-10-21 固化): 最小站距<30px的线, 相邻站标签必须异侧
    # (APM全线等分24px, 全挤一侧=体育中心南被推离圆点54px教训); 用户拍板左右各放几个
    gaps = [math.hypot(circles[i + 1][0] - circles[i][0], circles[i + 1][1] - circles[i][1])
            for i in range(len(circles) - 1)]
    _uniform_dense = gaps and min(gaps) < 30.0 and sorted(gaps)[len(gaps) // 2] < 30.0
    if _uniform_dense:
        _ns = '{http://www.w3.org/2000/svg}'
        pos_by_nm = {}
        for g in c['root'].iter(_ns + 'g'):
            if g.get('id') == '站圆':
                for el in g.iter(_ns + 'circle'):
                    if el.get('data-nm'):
                        pos_by_nm[el.get('data-nm')] = (float(el.get('cx')), float(el.get('cy')))
        order = list(pos_by_nm.keys())  # 站圆文档序=站序

        def _side(nm):
            p = pos_by_nm.get(nm)
            lb = next((l for l in labels if l['nm'] == nm), None)
            if not p or not lb:
                return '?'
            dx = lb['x'] - p[0]
            return '左' if dx < -2 else ('右' if dx > 2 else '中')
        bad_alt = []
        for i in range(len(order) - 1):
            a, b = order[i], order[i + 1]
            sa, sb = _side(a), _side(b)
            if sa != sb and {sa, sb} <= {'左', '右'}:
                continue
            if sa == '中' or sb == '中':
                continue  # 轴向(终点延长)不参与交替
            bad_alt.append('%s-%s 同侧%s' % (a, b, sa))
        add('G15', '密集线左右交替', not bad_alt, '; '.join(bad_alt[:4]) or '全过')
    else:
        add('G15', '密集线左右交替', True, '非均匀密集线豁免(中位站距≥30)')

    # G16 无之字折角(2026-10-21 固化, 用户拍板"线路要平滑过渡不能有折角"):
    # 相邻走廊段在同一轴继续推进的同时另一轴反向折叠(山峰/之字)=明显折角;
    # 转向>123°(dot<-0.55)也算。3号线海傍曾被画成"先45°上再45°下"山峰形。
    def _unit(ax, ay, bx, by):
        L = math.hypot(bx - ax, by - ay) or 1.0
        return ((bx - ax) / L, (by - ay) / L)
    by_pt = {}
    for k, (x1, y1, x2, y2) in enumerate(segs):
        by_pt.setdefault((round(x1, 1), round(y1, 1)), []).append((k, 0))
        by_pt.setdefault((round(x2, 1), round(y2, 1)), []).append((k, 1))
    fold = []
    for (px, py), refs in by_pt.items():
        if len(refs) != 2:
            continue  # 链端/分叉关节不查
        # T型并线关节(第三条段穿越此点, 如3号线支线45°并入主竖线)不算折角
        if any(seg_pt_dist(sg[0], sg[1], sg[2], sg[3], px, py) < 0.6
               for k, sg in enumerate(segs) if k not in (refs[0][0], refs[1][0])):
            continue
        (k1, e1), (k2, e2) = refs
        a, b = segs[k1], segs[k2]
        u = _unit(a[0], a[1], a[2], a[3]) if e1 == 1 else _unit(a[2], a[3], a[0], a[1])
        v = _unit(b[0], b[1], b[2], b[3]) if e2 == 0 else _unit(b[2], b[3], b[0], b[1])
        if ((u[0] * v[0] > 0.3 and u[1] * v[1] < -0.3) or (u[1] * v[1] > 0.3 and u[0] * v[0] < -0.3)
                or (u[0] * v[0] + u[1] * v[1]) < -0.55):
            fold.append('(%g,%g)' % (px, py))
    add('G16', '无之字折角', not fold, '; '.join(fold[:4]) or '全过')

    # G17 长非标斜段(2026-10-21 固化, 用户点名"石碁南折角太明显"):
    # 角度距{0,45,90}° >4° 且长度 >40px = 红。官图短过渡段(≤30px, 26.6°/63.4°缓坡缓和)合法;
    # 长孤非标斜段(3号线曾128px@23.7°)读作画错的明显折角。正确画法=标准45°折角(拐点可落两站间空档)。
    bad_odd = []
    for x1, y1, x2, y2 in segs:
        L2 = math.hypot(x2 - x1, y2 - y1)
        if L2 < 1e-6:
            continue
        a2 = math.degrees(math.atan2(abs(y2 - y1), abs(x2 - x1)))
        if min(abs(a2), abs(a2 - 45), abs(a2 - 90)) > 4.0 and L2 > 40.0:
            bad_odd.append('%.1f°/%.0fpx@(%g,%g)' % (a2, L2, x1, y1))
    add('G17', '无长非标斜段(>40px且离0/45/90超4°)', not bad_odd, '; '.join(bad_odd[:4]) or '全过')

    # G18 无硬拐(2026-10-21 固化, 用户点名"别的地方有这样的折角么"):
    # 全网画法铁律=轴向段接45°段必须带短过渡(90°转角=13px 45°切角; 轴向→长斜线=20px 26.6°/63.4°缓坡)。
    # 轴向|45° 关节两侧都>16px(即无切角/缓坡缓冲)=硬拐即红。审计基线: 修前全网仅3号线(2076.7,1649)一处。
    bad_hard = []
    for (jx, jy), refs in by_pt.items():
        if len(refs) != 2:
            continue
        if any(seg_pt_dist(sg[0], sg[1], sg[2], sg[3], jx, jy) < 0.6
               for k, sg in enumerate(segs) if k not in (refs[0][0], refs[1][0])):
            continue
        (k1, e1), (k2_, e2) = refs
        a, b = segs[k1], segs[k2_]
        u = _unit(a[0], a[1], a[2], a[3]) if e1 == 1 else _unit(a[2], a[3], a[0], a[1])
        v = _unit(b[0], b[1], b[2], b[3]) if e2 == 0 else _unit(b[2], b[3], b[0], b[1])
        au = math.degrees(math.atan2(abs(u[1]), abs(u[0])))
        av = math.degrees(math.atan2(abs(v[1]), abs(v[0])))
        _axis = lambda t: t < 2.5 or t > 87.5
        _diag = lambda t: 42.5 < t < 47.5
        if (_axis(au) and _diag(av)) or (_diag(au) and _axis(av)):
            if math.hypot(a[2] - a[0], a[3] - a[1]) > 16 and math.hypot(b[2] - b[0], b[3] - b[1]) > 16:
                bad_hard.append('(%g,%g)' % (jx, jy))
    add('G18', '无硬拐(轴向↔45°须切角/缓坡过渡)', not bad_hard, '; '.join(bad_hard[:4]) or '全过')

    return R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('card')
    ap.add_argument('--expect-n', type=int, default=None)
    a = ap.parse_args()
    R = run_gates(a.card, a.expect_n)
    print('%s  (%s)' % (os.path.basename(a.card), a.card))
    npass = 0
    for no, name, ok, detail in R:
        print('  %-3s %-2s %-24s %s' % (no, '✓' if ok else '✗', name, detail))
        npass += ok
    print('门禁: %d/%d 通过' % (npass, len(R)))
    sys.exit(0 if npass == len(R) else 1)


if __name__ == '__main__':
    main()
