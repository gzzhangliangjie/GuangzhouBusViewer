# -*- coding: utf-8 -*-
"""45°站标签法向在位迁移器(旧卡专用: 1/2/3号线等无存活生成器的卡)。
只动 非终点(无chip) 且 最近走廊段在正45°±6° 且 标签未法向放置 的站:
挪到法向位(两侧择优: 净距≥G、不压标签、归属余量小者优先), 中文+英文整组平移。
写临时文件跑 verify_card 门禁, 全过才落盘, 否则保持原卡。
用法: python tools/migrate-diag-labels.py assets/lines/line-2号线.svg ...
"""
import os, sys, io, math, re, tempfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_card import load, run_gates, rect_seg_clearance
import xml.etree.ElementTree as ET

NS = '{http://www.w3.org/2000/svg}'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
G = 10.0

for path in sys.argv[1:]:
    c = load(path)
    root = c['root']
    pos = {}
    order = []
    for g in root.iter(NS + 'g'):
        if g.get('id') == '站圆':
            for el in g.iter(NS + 'circle'):
                if el.get('data-nm'):
                    nm = el.get('data-nm')
                    pos[nm] = (float(el.get('cx')), float(el.get('cy')))
                    order.append(nm)
    circles = [(x, y) for (x, y, r) in c['circles']]
    # 终点=有终点数字块贴近的标签(3号线支线3终点也覆盖)
    chips = [(b['box'][0] + b['box'][2]) / 2 and
             ((b['box'][0] + b['box'][2]) / 2, (b['box'][1] + b['box'][3]) / 2)
             for b in c['badges'] if b.get('mode') == 'chip']
    moved = 0
    for lb in c['labels']:
        nm = lb['nm']
        if nm not in pos:
            continue
        ax, ay = pos[nm]
        lcx, lcy = lb['x'], (lb['box'][1] + lb['box'][3]) / 2
        if any(math.hypot(cx - lcx, cy - lcy) < 80 for cx, cy in chips):
            continue  # 终点不动(延长线版式+chip联动)
        # 最近走廊段
        best, bd = None, 1e9
        for s in c['segs']:
            x1, y1, x2, y2 = s
            vx, vy = x2 - x1, y2 - y1
            L2 = vx * vx + vy * vy or 1.0
            t = max(0.0, min(1.0, ((ax - x1) * vx + (ay - y1) * vy) / L2))
            d = math.hypot(x1 + t * vx - ax, y1 + t * vy - ay)
            if d < bd:
                bd, best = d, s
        x1, y1, x2, y2 = best
        L = math.hypot(x2 - x1, y2 - y1) or 1.0
        ux, uy = (x2 - x1) / L, (y2 - y1) / L
        if not (0.64 < abs(ux) < 0.77 and 0.64 < abs(uy) < 0.77):
            continue  # 不在正45°带
        odx, ody = lcx - ax, lcy - ay
        ol = math.hypot(odx, ody) or 1.0
        n1, n2 = (-uy, ux), (uy, -ux)
        if max(odx / ol * n1[0] + ody / ol * n1[1], odx / ol * n2[0] + ody / ol * n2[1]) > 0.9:
            continue  # 已法向
        bw = (lb['box'][2] - lb['box'][0]) / 2
        bh = lb['box'][3] - lb['box'][1]
        # 两侧法向候选: (净距, 归属余量, 法向)
        cand = []
        for n in (n1, n2):
            d = G + (abs(n[0]) * bw + abs(n[1]) * bh) / 2
            cx, cy = ax + n[0] * d, ay + n[1] * d
            box = (cx - bw, cy - bh / 2, cx + bw, cy + bh / 2)
            cl = rect_seg_clearance(*box, c['segs'])
            if cl < G - 1.5:
                continue
            if any(not (box[2] < q['box'][0] or q['box'][2] < box[0] or
                        box[3] < q['box'][1] or q['box'][3] < box[1])
                   for q in c['labels'] if q is not lb):
                continue
            own = math.hypot(cx - ax, cy - ay)
            other = min((math.hypot(cx - px, cy - py) for (px, py) in circles
                         if (px, py) != (ax, ay)), default=1e9)
            cand.append((own / max(other, 1e-9), cx, cy, box))
        if not cand:
            print('%s %s: 法向两侧均不可行, 保持原位' % (os.path.basename(path), nm))
            continue
        cand.sort()
        _, cx, cy, box = cand[0]
        if cx / 1 == lcx / 1 and cy / 1 == lcy / 1:
            continue
        # 平移该站 zh + en(+en2) 文本: x=center, y=基线随盒顶
        # 找该站的 text 元素
        for g in root.iter(NS + 'g'):
            if g.get('id') != '站名标注':
                continue
            ts = [t for t in g.iter(NS + 'text')
                  if abs(float(t.get('x')) - lb['x']) < 0.3 and t.text]
            zh = next((t for t in ts if t.text == nm and t.get('font-size') == '10.5'), None)
            if zh is None:
                continue
            zy = float(zh.get('y'))
            ens = [t for t in ts if t is not zh and abs(float(t.get('x')) - lb['x']) < 0.3
                   and 0 < float(t.get('y')) - zy < 14]
            new_zy = box[1] + 11.0
            for t in [zh] + sorted(ens, key=lambda t: float(t.get('y'))):
                t.set('x', '%.1f' % cx)
            zh.set('y', '%.1f' % new_zy)
            prev = zy
            for t in sorted(ens, key=lambda t: float(t.get('y'))):
                ty = float(t.get('y'))
                t.set('y', '%.1f' % (new_zy + (ty - zy)))
        moved += 1
        print('%s %s: 偏移(%.0f,%.0f)->法向(%.0f,%.0f)' % (
            os.path.basename(path), nm, odx, ody, cx - ax, cy - ay))
    if not moved:
        print('%s: 无需迁移' % os.path.basename(path))
        continue
    out = path.replace('.svg', '_mig.svg')
    ET.ElementTree(root).write(out, encoding='unicode', xml_declaration=False)
    N = len(order)
    R = run_gates(out, expect_n=N)
    fails = ['%s %s' % (no, dt[:90]) for no, nm, ok, dt in R if not ok]
    if fails:
        os.remove(out)
        print('%s: 门禁未过, 保持原卡: %s' % (os.path.basename(path), '; '.join(fails)))
    else:
        os.replace(out, path)
        print('%s: 门禁 %d/%d 全过, 落盘' % (os.path.basename(path), len(R), len(R)))
