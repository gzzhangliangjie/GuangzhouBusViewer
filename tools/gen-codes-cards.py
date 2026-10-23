# -*- coding: utf-8 -*-
"""站点编号牌卡生成器: 官图提取卡/全网图 -> *.codes.svg 变体(线路图页"查看站点编号"勾选后展示)。

画法规格(官图 gz-map-2025b 编号版, 2026-10-23 用户4张用例截图定稿):
- 牌 = 横向圆角胶囊(stadium): 白底 + 黑字 + 边框=本线色 + 内部本线色竖分隔线;
  文字「线号|站序」分居分隔线两侧, 线号用裸线号(1/10/22/GF/APM), 站序两位补零;
- 排布按交汇线数(官图模式): 2线=纵叠 / 3线=品字(上二下一) / 4线=田字(2x2);
  落位=弹性网格——槽位先取各线钉位(触线天然成立), 再按最小不叠间距对称推开;
  同线纵排钉(嘉禾望岗)品字放不下时退化纵叠, 候选(纵叠/横排/品字/田字)按
  "全触线 > 钉向匹配" 择优;
- 数据唯一真源 data/station-codes-official.csv(用户指定); 站名匹配: 原名优先,
  去尾'站'兜底(APM 海心沙站->海心沙; 广州南站 等'站'尾真名不剥);
  广佛线显示名=GF(用户指定); CSV 有而图上无走廊的线(佛山2号线)不生成牌。

门禁:
- G1 单线卡: 有码站恰一枚牌, 无码站保留原站圆并列入报告;
- G2 全网: (站,线)∈图上钉∩CSV码 → 恰一枚牌;
- G3 触线: 每牌矩形与本线走廊线段距离 ≤ 走廊半宽3.5(视觉接触);
- G4 牌-牌: 不同站牌矩形不相交; 同站组内不叠(构造保证) + 跨站重叠沿走廊推让;
- G5 幂等: 重跑字节一致。
用法: python tools/gen-codes-cards.py
"""
import csv
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINES_DIR = os.path.join(ROOT, 'assets', 'lines')
CSV_PATH = os.path.join(ROOT, 'data', 'station-codes-official.csv')
REPORT = os.path.join(ROOT, 'data', '_codes-cards-report.json')

ORDER = ['1号线', '2号线', '3号线', '4号线', '5号线', '6号线', '7号线', '8号线',
         '9号线', '10号线', '11号线', '12号线', '13号线', '14号线', '18号线',
         '21号线', '22号线', '广佛线', 'APM线']


def csv_line_to_card(ln):
    """CSV线路名 -> (卡线名, 显示线号); 图上无走廊的线返回 (None, None)."""
    if ln == '广佛线':
        return ('广佛线', 'GF')
    if ln == 'APM':
        return ('APM线', 'APM')
    if ln in [x for x in ORDER if x.endswith('号线')]:
        return (ln, ln[:-2])
    return (None, None)


# ---------- 编号数据 ----------
def load_codes():
    """-> codes[(站名, 卡线名)] = (显示线号, 序号). 原名优先, 去尾'站'兜底."""
    codes = {}
    with open(CSV_PATH, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            nm = r['站名']
            card, disp = csv_line_to_card(r['线路'])
            if card is None:
                continue
            if (nm, card) not in codes:
                codes[(nm, card)] = (disp, r['编号'])
            stripped = nm[:-1] if nm.endswith('站') and len(nm) > 2 else None
            if stripped and (stripped, card) not in codes:
                codes[(stripped, card)] = (disp, r['编号'])
    return codes


# ---------- 卡片解析 ----------
CIRCLE_RE = re.compile(r'<circle ([^>]*data-nm="([^"]+)"[^>]*)/>')
ATTR = lambda at, k: float(re.search(k + r'="([-\d.]+)"', at).group(1))


def parse_card(line):
    """-> {'pins': [(nm,cx,cy)], 'segs': [(x1,y1,x2,y2)], 'color': str}"""
    t = open(os.path.join(LINES_DIR, 'line-%s.svg' % line), encoding='utf-8').read()
    pins = []
    for m in CIRCLE_RE.finditer(t):
        at, nm = m.group(1), m.group(2)
        pins.append((nm, ATTR(at, 'cx'), ATTR(at, 'cy')))
    segs = []
    for m in re.finditer(r'<line x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)"', t):
        segs.append((float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))))
    color = re.search(r'stroke:(#\w+)', CIRCLE_RE.search(t).group(1)).group(1)
    return {'pins': pins, 'segs': segs, 'color': color}


# ---------- 牌几何 ----------
FONT = 6.0        # 牌字号(全网, 2026-10-23 三轮再缩)
FONT_CARD = 6.5   # 单线卡字号
APM_FONT = 5.1    # APM 专用更小字号(用户: 尤其APM要缩更小)
APM_FONT_CARD = 5.5
H = 10.0          # 牌高
H_CARD = 11.0
PADX = 2.0        # 左右内边距
SEPW = 3.0        # 分隔区宽(含两侧空隙)
GAP = 1.2         # 组内牌间缝
CORR_HALF = 3.5   # 走廊 stroke-width 7 半宽(触线判定含线宽)
RING_PAD = 2.5    # 多线组外描边圈的内衬(用户: 多线要在胶囊组外围多画一圈描边)
INK = '#1a1a1a'

# 文本宽度 = 渲染字体(微软雅黑 Bold)实测, 精确到 0.1px(APM 估算 13 vs 实测 17, 必须量测)
from PIL import ImageFont
try:
    _FM = {round(fs, 1): ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc', int(fs * 10))
           for fs in (FONT, FONT_CARD, APM_FONT, APM_FONT_CARD)}
    _FM_ARIAL = {round(fs, 1): ImageFont.truetype('C:/Windows/Fonts/arial.ttf', int(fs * 10))
                 for fs in (5.5, 6.0)}
except Exception:
    _FM = None
    _FM_ARIAL = None
_W_CACHE = {}


def font_of(line_disp, card):
    """牌字号: APM 专用更小档, 其余标准档."""
    if line_disp == 'APM':
        return APM_FONT_CARD if card else APM_FONT
    return FONT_CARD if card else FONT


def part_w(txt, fs):
    key = (txt, round(fs, 1))
    if key in _W_CACHE:
        return _W_CACHE[key]
    if _FM is not None:
        w = _FM[round(fs, 1)].getlength(txt) / 10.0
    else:   # 字体缺失兜底: 经验宽度
        w = sum(0.62 * fs if c.isalpha() else (0.586 * fs if c.isdigit() else 1.0 * fs) for c in txt)
    _W_CACHE[key] = w
    return w


def cell_a(line_disp, fs):
    """线号格宽(定宽): 数字/GF 统一按 max(两位数字, GF); APM 独立(字母宽, 官图同款).
    -> 1位与2位数字线号的牌总宽全等(2026-10-23 用户: 编号胶囊需保持一样大小)."""
    if line_disp == 'APM':
        return part_w('APM', fs)
    return max(part_w('22', fs), part_w('GF', fs))


def cell_b(fs):
    return part_w('00', fs)   # 序号格定宽(两位)


def chip_need_w(line_disp, serial, fs):
    """牌需求宽 = 定宽格 与 实测文本宽 取 max(兜住 CSV 支线序号 01-1 这类长内容)."""
    return 2 * PADX + max(cell_a(line_disp, fs), part_w(line_disp, fs)) + SEPW + max(cell_b(fs), part_w(serial, fs))


def chip_w(line_disp, serial, fs):
    import math
    return math.ceil(chip_need_w(line_disp, serial, fs) * 2) / 2.0


def chip_svg(cx, cy, w, h, color, line_disp, serial, fs):
    """一枚编号牌: 白底胶囊+线色边框+线色竖分隔线+黑字两段(定宽格居中)."""
    x0, y0 = cx - w / 2, cy - h / 2
    ca = cell_a(line_disp, fs)
    xline = x0 + PADX + ca / 2
    xsep = x0 + PADX + ca + SEPW / 2
    xser = x0 + PADX + ca + SEPW + cell_b(fs) / 2
    ty = cy + 0.06 * fs
    return (
        f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{w:.2f}" height="{h:.2f}" rx="{h / 2:.2f}" '
        f'fill="#FFFFFF" stroke="{color}" stroke-width="1.0"/>' +
        f'<line x1="{xsep:.2f}" y1="{y0 + 1.2:.2f}" x2="{xsep:.2f}" y2="{y0 + h - 1.2:.2f}" '
        f'stroke="{color}" stroke-width="0.8"/>' +
        f'<text x="{xline:.2f}" y="{ty:.2f}" text-anchor="middle" dominant-baseline="central" '
        f'font-size="{fs}" font-weight="700" fill="#000000">{line_disp}</text>' +
        f'<text x="{xser:.2f}" y="{ty:.2f}" text-anchor="middle" dominant-baseline="central" '
        f'font-size="{fs}" font-weight="700" fill="#000000">{serial}</text>'
    )


# ---------- 矩形-线段距离 ----------
def rect_seg_dist(rect, seg):
    rx, ry, rw, rh = rect
    a, b = (seg[0], seg[1]), (seg[2], seg[3])
    cx0, cy0, cx1, cy1 = rx, ry, rx + rw, ry + rh

    def pt_rect(p):
        qx = min(max(p[0], cx0), cx1); qy = min(max(p[1], cy0), cy1)
        return ((p[0] - qx) ** 2 + (p[1] - qy) ** 2) ** 0.5

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

    def seg_point_dist(p):
        ddx, ddy = b[0] - a[0], b[1] - a[1]
        dd = ddx * ddx + ddy * ddy
        t = 0.0 if dd == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * ddx + (p[1] - a[1]) * ddy) / dd))
        return ((p[0] - a[0] - t * ddx) ** 2 + (p[1] - a[1] - t * ddy) ** 2) ** 0.5

    corners = [(cx0, cy0), (cx1, cy0), (cx1, cy1), (cx0, cy1)]
    return min(pt_rect(a), pt_rect(b), min(seg_point_dist(c) for c in corners))


def rects_overlap(r1, r2, pad=0.0):
    return (r1[0] - pad < r2[0] + r2[2] and r1[0] + r1[2] > r2[0] - pad and
            r1[1] - pad < r2[1] + r2[3] and r1[1] + r1[3] > r2[1] - pad)


def expand_viewbox(t, chip_rects, margin=2.0):
    """牌超出原 viewBox 时扩画布(背景白 rect 同步), 防边缘牌被裁."""
    m = re.search(r'viewBox="([-\d.]+) ([-\d.]+) ([\d.]+) ([\d.]+)"', t)
    vx, vy, vw, vh = (float(m.group(i)) for i in range(1, 5))
    if chip_rects:
        x0 = min(r[0] for r in chip_rects) - margin
        y0 = min(r[1] for r in chip_rects) - margin
        x1 = max(r[0] + r[2] for r in chip_rects) + margin
        y1 = max(r[1] + r[3] for r in chip_rects) + margin
    else:
        x0, y0, x1, y1 = vx, vy, vx + vw, vy + vh
    nx0, ny0, nx1, ny1 = min(vx, x0), min(vy, y0), max(vx + vw, x1), max(vy + vh, y1)
    if (nx0, ny0, nx1, ny1) == (vx, vy, vx + vw, vy + vh):
        return t
    t = t.replace(m.group(0), 'viewBox="%.2f %.2f %.2f %.2f"' % (nx0, ny0, nx1 - nx0, ny1 - ny0), 1)
    bg = re.search(r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)" fill="#ffffff"', t)
    if bg:
        t = t.replace(bg.group(0),
                      '<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="#ffffff"' % (nx0, ny0, nx1 - nx0, ny1 - ny0), 1)
    return t


# ---------- 站名标签避让(编号版): 牌压名 -> 沿钉→标方向外推, 校验走廊/邻标净距 ----------
LABEL_CHIP_GAP = 1.0    # 标签-牌净距下限
LABEL_CORR_GAP = 1.0    # 标签-走廊净距下限(推移后不得新压线)
LABEL_LBL_GAP = 0.3     # 标签-标签净距下限(推移后)


def parse_labels(svg_text):
    """站名标注组 -> [(nm, x, y, fs, attrs, content)]; zh=content匹配站名, en=拼音小字号."""
    m = re.search(r'<g id="站名标注"[^>]*>(.*?)</g>', svg_text, re.S)
    out = []
    if not m:
        return out, m
    for tx in re.finditer(r'<text ([^>]*)>([^<]+)</text>', m.group(1)):
        at, content = tx.group(1), tx.group(2)
        gx = re.search(r'\bx="([-\d.]+)"', at)
        gy = re.search(r'\by="([-\d.]+)"', at)
        gf = re.search(r'font-size="([\d.]+)"', at)
        if not (gx and gy):
            continue
        out.append({'x': float(gx.group(1)), 'y': float(gy.group(1)),
                    'fs': float(gf.group(1)) if gf else 7.5, 'attrs': at, 'content': content})
    return out, m


def label_groups(labels, pin_names):
    """站名(zh, 中文任意字号含密集区6/5px)与紧邻其下的拼音(en/en2)聚成一组: -> {nm: [label...]}."""
    zh = [l for l in labels if l['content'] in pin_names and not l['content'].isascii()]
    ens = [l for l in labels if l not in zh]
    groups = {l['content']: [l] for l in zh}
    for e in ens:
        best, bd = None, 1e9
        for z in zh:
            dy = e['y'] - z['y']
            d = abs(e['x'] - z['x']) + abs(dy)
            if dy > -1 and abs(e['x'] - z['x']) < 4 and dy < 16 and d < bd:
                best, bd = z, d
        if best:
            groups[best['content']].append(e)
    return groups


def text_box(l):
    """单条text近似盒(中锚+基线y): 宽=实测, 高=fs*1.1."""
    import math
    if _FM_ARIAL is not None and l['fs'] < 6.8 and l['content'].isascii():
        w = _FM_ARIAL[round(min(l['fs'], 6.0), 1)].getlength(l['content']) / 10.0
    else:
        w = part_w(l['content'], FONT_CARD) / FONT_CARD * l['fs']   # 按字号比例换算(bold量宽, 保守偏宽)
    return (l['x'] - w / 2, l['y'] - l['fs'] * 0.92, w, l['fs'] * 1.12)


def group_box(items):
    boxes = [text_box(l) for l in items]
    x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes); y1 = max(b[1] + b[3] for b in boxes)
    return (x0, y0, x1 - x0, y1 - y0)


def _clear_rect(rect, others, gap):
    """真净距判据: 与任一 other 的净距 >= gap(角部擦边也算犯, rects_overlap(pad) 会漏判)."""
    for o in others:
        if _gap(rect, o) < gap:
            return False
    return True


def _gap(r1, r2):
    """两矩形净距(重叠为负, 量级=角部侵入深度)."""
    ox = min(r1[0] + r1[2], r2[0] + r2[3]) - max(r1[0], r2[0])
    oy = min(r1[1] + r1[3], r2[1] + r2[3]) - max(r1[1], r2[1])
    if ox >= 0 and oy >= 0:
        return -min(ox, oy)
    return max(-ox if ox < 0 else 0, -oy if oy < 0 else 0)


def nudge_labels(svg_text, pin_by_name, chips_by_station, segs, report, tag):
    """编号版站名避让: 与牌相犯(<净距)的标签组沿 钉->标 方向外推(0.5px步进, ±35°/±70°轮换),
    推移校验: 全部牌净距>=LABEL_CHIP_GAP, 走廊净距>=LABEL_CORR_GAP, 其他标签>=LABEL_LBL_GAP.
    返回新的站名标注组 innerHTML(全部文本, 位置按需更新)."""
    labels, m = parse_labels(svg_text)
    if not labels:
        return None
    groups = label_groups(labels, set(pin_by_name))
    all_chip_rects = [r for lst in chips_by_station.values() for r in lst]
    cur_boxes = {nm: group_box(g) for nm, g in groups.items()}
    order = sorted(groups.items(), key=lambda kv: -group_box(kv[1])[2] * group_box(kv[1])[3])
    moved, unresolved, relaxed = [], [], []
    import math as _m
    for nm, g in order:
        box = cur_boxes[nm]
        if _clear_rect(box, all_chip_rects, LABEL_CHIP_GAP):
            continue   # 本就不压(含邻站牌)
        # 推移基准方向: 远离最近的相犯牌; 无相犯牌信息时用 钉->标 方向
        bcx, bcy = box[0] + box[2] / 2, box[1] + box[3] / 2
        viol = min(all_chip_rects, key=lambda r: _gap(box, r))
        if viol is not None:
            vcx, vcy = viol[0] + viol[2] / 2, viol[1] + viol[3] / 2
            dx, dy = bcx - vcx, bcy - vcy
        else:
            pin = pin_by_name.get(nm)
            dx, dy = (bcx - pin[0], bcy - pin[1]) if pin else (0.0, -1.0)
        l = (dx * dx + dy * dy) ** 0.5 or 1.0
        bx, by = dx / l, dy / l
        near_segs = [s for s in segs
                     if abs((s[0] + s[2]) / 2 - bcx) < 70 and abs((s[1] + s[3]) / 2 - bcy) < 70]
        near_lbls = [cur_boxes[n2] for n2 in cur_boxes if n2 != nm
                     and abs(cur_boxes[n2][0] - box[0]) < 60 and abs(cur_boxes[n2][1] - box[1]) < 60]
        done = False
        relax = None
        # 兜底链: 全约束 -> 放标签互斥 -> 放走廊净距(牌不压名优先, 2026-10-23 用户主诉)
        for relax_lbl, relax_corr in ((False, False), (True, False), (True, True)):
            for ang in (0, 35, -35, 70, -70, 105, -105, 180):
                ra = _m.radians(ang)
                ca_, sa_ = _m.cos(ra), _m.sin(ra)
                ux, uy = bx * ca_ - by * sa_, bx * sa_ + by * ca_
                for step in range(1, 49):   # 上限24px: 品字外圈宽~51px, 标签逃出需>16px
                    d = step * 0.5
                    r2 = (box[0] + ux * d, box[1] + uy * d, box[2], box[3])
                    if not _clear_rect(r2, all_chip_rects, LABEL_CHIP_GAP):
                        continue
                    if not relax_corr and not all(rect_seg_dist(r2, s) >= LABEL_CORR_GAP for s in near_segs):
                        continue
                    if not relax_lbl and not _clear_rect(r2, near_lbls, LABEL_LBL_GAP):
                        continue
                    for l2 in g:
                        l2['x'] = round(l2['x'] + ux * d, 2)
                        l2['y'] = round(l2['y'] + uy * d, 2)
                    cur_boxes[nm] = r2
                    moved.append((nm, d, ang))
                    done = True
                    relax = 'lbl' if (relax_lbl and not relax_corr) else ('corr' if relax_corr else None)
                    break
                if done:
                    break
            if done:
                break
        if done and relax:
            relaxed.append('%s(%s)' % (nm, relax))
        if not done:
            unresolved.append(nm)
    rep = report.setdefault('label_nudge', {}).setdefault(tag, {})
    rep['moved'] = len(moved)
    rep['max_shift'] = max((d for _, d, _ in moved), default=0)
    rep['relaxed'] = relaxed
    rep['unresolved'] = unresolved
    # 重组 innerHTML
    emit = []
    grouped_ids = {id(l2) for g in groups.values() for l2 in g}
    for l2 in labels:
        if id(l2) in grouped_ids:
            at = re.sub(r'\bx="[-\d.]+"', 'x="%.2f"' % l2['x'], l2['attrs'])
            at = re.sub(r'\by="[-\d.]+"', 'y="%.2f"' % l2['y'], at)
        else:
            at = l2['attrs']
        emit.append('<text %s>%s</text>' % (at, l2['content']))
    return ''.join(emit)


# ---------- 单线卡 ----------
def gen_line_card(line, codes, report):
    path = os.path.join(LINES_DIR, 'line-%s.svg' % line)
    t = open(path, encoding='utf-8').read()
    card = parse_card(line)
    color = card['color']
    chips, kept = [], []
    for nm, cx, cy in card['pins']:
        key = (nm, line)
        if key in codes:
            disp, serial = codes[key]
            fs = font_of(disp, True)
            w = chip_w(disp, serial, fs)
            chips.append((nm, disp, serial, cx, cy, w, H_CARD, fs))
        else:
            kept.append((nm, cx, cy))
            report['no_code'].append('%s/%s' % (line, nm))
    m = re.search(r'<g id="站圆">.*?</g>', t, re.S)
    circles_svg = ''.join(
        f'<circle cx="{cx}" cy="{cy}" r="4.5" data-nm="{nm}" style="fill:#FFFFFF;stroke:{color};stroke-width:2"/>'
        for nm, cx, cy in kept)
    chips_svg = ''.join(
        chip_svg(cx, cy, w, H_CARD, color, disp, serial, fs)
        for nm, disp, serial, cx, cy, w, h, fs in chips)
    t2 = t[:m.start()] + ('<g id="站圆">' + circles_svg + '</g>' if circles_svg else '') + t[m.end():]
    # 站名避让: 与牌相犯的标签沿钉->标方向外推(缩小后仍压的才推)
    chips_by_station = {}
    for nm, disp, serial, cx, cy, w, h, fs in chips:
        chips_by_station.setdefault(nm, []).append((cx - w / 2, cy - H_CARD / 2, w, H_CARD))
    new_labels = nudge_labels(t2, {nm: (cx, cy) for nm, cx, cy in card['pins']},
                              chips_by_station, card['segs'], report, line)
    if new_labels is not None:
        t2 = re.sub(r'(<g id="站名标注"[^>]*>).*?(</g>)',
                    lambda mm: mm.group(1) + new_labels + mm.group(2), t2, count=1, flags=re.S)
    mn = re.search(r'<g id="站名标注"[^>]*>.*?</g>', t2, re.S)
    t2 = t2[:mn.end()] + '<g id="编号牌" font-family="\'Microsoft YaHei\', \'PingFang SC\', sans-serif">' + chips_svg + '</g>' + t2[mn.end():]
    out = os.path.join(LINES_DIR, 'line-%s.codes.svg' % line)
    open(out, 'w', encoding='utf-8').write(
        expand_viewbox(t2, [(cx - w / 2, cy - H_CARD / 2, w, H_CARD) for nm, disp, serial, cx, cy, w, h, fs in chips]))
    report['line_chips'][line] = len(chips)
    return chips


# ---------- 全网: 弹性网格排布 ----------
def push_apart(centers, widths, minsep, axis):
    """同轴槽位按最小间距对称推开(围绕两两中点, 迭代到收敛). widths=各槽宽(另一轴用)."""
    n = len(centers)
    idx = sorted(range(n), key=lambda i: centers[i][0] if axis == 'x' else centers[i][1])
    vals = [centers[i][0] if axis == 'x' else centers[i][1] for i in idx]
    for _ in range(8):
        moved = False
        for k in range(n - 1):
            need = ((widths[idx[k]] + widths[idx[k + 1]]) / 2 if axis == 'x' else minsep) + (GAP if axis == 'x' else 0)
            if axis == 'y':
                need = minsep
            if vals[k + 1] - vals[k] < need - 1e-9:
                c = (vals[k] + vals[k + 1]) / 2
                d = (need - (vals[k + 1] - vals[k])) / 2
                vals[k], vals[k + 1] = vals[k] - d, vals[k + 1] + d
                moved = True
        if not moved:
            break
    out = list(centers)
    for j, i in enumerate(idx):
        x, y = centers[i]
        out[i] = (vals[j], y) if axis == 'x' else (x, vals[j])
    return out


def _separate(placed):
    """组内两两防叠: 重叠对沿主轴对称推开(松弛迭代), 保证任意两牌矩形净距>=GAP."""
    placed = [list(p) for p in placed]
    for _ in range(24):
        worst = None
        for a in range(len(placed)):
            for b in range(a + 1, len(placed)):
                ra = (placed[a][1] - placed[a][3] / 2, placed[a][2] - H / 2, placed[a][3], H)
                rb = (placed[b][1] - placed[b][3] / 2, placed[b][2] - H / 2, placed[b][3], H)
                ovx = min(ra[0] + ra[2], rb[0] + rb[2]) - max(ra[0], rb[0]) - GAP
                ovy = min(ra[1] + ra[3], rb[1] + rb[3]) - max(ra[1], rb[1]) - GAP
                if ovx < 0 or ovy < 0:
                    continue
                if worst is None or ovx * ovy > worst[0]:
                    worst = (ovx * ovy, a, b, ovx, ovy)
        if worst is None:
            break
        _, a, b, ovx, ovy = worst
        if ovx <= 0:
            d = ovy / 2 + 0.05
            s = 1 if placed[a][2] <= placed[b][2] else -1
            placed[a][2] -= s * d
            placed[b][2] += s * d
        elif ovy <= 0:
            d = ovx / 2 + 0.05
            s = 1 if placed[a][1] <= placed[b][1] else -1
            placed[a][1] -= s * d
            placed[b][1] += s * d
        else:
            # 两轴都侵: 沿侵入量较小的轴推(推开代价小)
            if ovx <= ovy:
                d = ovx / 2 + 0.05
                s = 1 if placed[a][1] <= placed[b][1] else -1
                placed[a][1] -= s * d
                placed[b][1] += s * d
            else:
                d = ovy / 2 + 0.05
                s = 1 if placed[a][2] <= placed[b][2] else -1
                placed[a][2] -= s * d
                placed[b][2] += s * d
    return [tuple(p) for p in placed]


def layout_candidates(items):
    """items=[(line, pinx, piny, w)] -> [(tag, [(line, cx, cy, w)])].
    槽位初始化=各线钉位(触线天然成立), 再最小间距推开; 模式随线数与钉形自适应."""
    n = len(items)
    if n == 1:
        ln, px, py, w = items[0]
        return [('S', [(ln, px, py, w)])]
    cands = []
    # 纵叠(官图2线模式; 同轴钉的多线站退化用)
    pts = push_apart([(it[1], it[2]) for it in items], [1] * n, H + GAP, 'y')
    cands.append(('V', [(items[i][0], pts[i][0], pts[i][1], items[i][3]) for i in range(n)]))
    # 横排
    pts = push_apart([(it[1], it[2]) for it in items], [it[3] for it in items], 0, 'x')
    cands.append(('H', [(items[i][0], pts[i][0], pts[i][1], items[i][3]) for i in range(n)]))
    if n == 3:
        # 品字: 底槽=钉y最大者, 顶排=其余按x排序
        bottom = max(range(n), key=lambda i: items[i][2])
        top = sorted([i for i in range(n) if i != bottom], key=lambda i: items[i][1])
        pairs = push_apart([(items[top[0]][1], items[top[0]][2]), (items[top[1]][1], items[top[1]][2])],
                           [items[top[0]][3], items[top[1]][3]], 0, 'x')
        bx, by = items[bottom][1], items[bottom][2]
        row_y = min(p[1] for p in pairs)
        if by - row_y < H + GAP:
            sh = (H + GAP - (by - row_y)) / 2
            pairs = [(x, y - sh) for x, y in pairs]
            by += sh
        place = {top[0]: pairs[0], top[1]: pairs[1], bottom: (bx, by)}
        cands.append(('P3', [(items[i][0], place[i][0], place[i][1], items[i][3]) for i in range(n)]))
    if n == 4:
        # 田字: 列=x排序对半分; 列内同x(=列钉x均值)竖排推开, 列间再推开
        order = sorted(range(4), key=lambda i: items[i][1])
        left, right = sorted(order[:2], key=lambda i: items[i][2]), sorted(order[2:], key=lambda i: items[i][2])
        cells = {}
        for col in (left, right):
            mx = sum(items[i][1] for i in col) / 2.0
            pts = push_apart([(mx, items[i][2]) for i in col], [1] * len(col), H + GAP, 'y')
            for i, p in zip(col, pts):
                cells[i] = p
        wL = max(items[i][3] for i in left)
        wR = max(items[i][3] for i in right)
        lx = cells[left[-1]][0]
        rx = cells[right[0]][0]
        if rx - lx < (wL + wR) / 2 + GAP:
            d = ((wL + wR) / 2 + GAP - (rx - lx)) / 2
            for i in left:
                cells[i] = (cells[i][0] - d, cells[i][1])
            for i in right:
                cells[i] = (cells[i][0] + d, cells[i][1])
        cands.append(('G4', [(items[i][0], cells[i][0], cells[i][1], items[i][3]) for i in range(4)]))
    return [(tag, _separate(placed)) for tag, placed in cands]


def place_station(items, segs_of):
    """择优: 全触线 > 钉向匹配 > 最差距离. 返回 (tag, placed, fails, worst)."""
    n = len(items)
    gx = sum(it[1] for it in items) / n
    gy = sum(it[2] for it in items) / n
    scored = []
    for tag, placed in layout_candidates(items):
        worst, fails = 0.0, []
        for ln, cx, cy, w in placed:
            rect = (cx - w / 2, cy - H / 2, w, H)
            d = min(rect_seg_dist(rect, s) for s in segs_of[ln]) - CORR_HALF
            if d > 0.01:
                fails.append('%s d=%.1f' % (ln, d))
            worst = max(worst, d)
        dirscore = 0.0
        pin_of = {it[0]: (it[1], it[2]) for it in items}
        for ln, cx, cy, w in placed:
            pl = ((cx - gx) ** 2 + (cy - gy) ** 2) ** 0.5 or 1.0
            px, py = pin_of[ln]
            ql = ((px - gx) ** 2 + (py - gy) ** 2) ** 0.5 or 1.0
            dirscore += ((cx - gx) / pl) * ((px - gx) / ql) + ((cy - gy) / pl) * ((py - gy) / ql)
        scored.append((len(fails) == 0, dirscore, worst, tag, placed, fails))
    scored.sort(key=lambda x: (not x[0], -x[1], x[2]))
    ok, dirscore, worst, tag, placed, fails = scored[0]
    for a in range(len(placed)):
        for b in range(a + 1, len(placed)):
            ra = (placed[a][1] - placed[a][3] / 2, placed[a][2] - H / 2, placed[a][3], H)
            rb = (placed[b][1] - placed[b][3] / 2, placed[b][2] - H / 2, placed[b][3], H)
            if rects_overlap(ra, rb, pad=-GAP):
                fails.append('组内叠(%s+%s)' % (placed[a][0], placed[b][0]))
    return tag, placed, fails, worst


def corridor_tangent(segs, x, y):
    """站点邻近走廊的走向(取最近线段方向单位向量)."""
    best, bd = None, 1e9
    for s in segs:
        d = rect_seg_dist((x - 0.1, y - 0.1, 0.2, 0.2), s)
        if d < bd:
            bd = d
            dx, dy = s[2] - s[0], s[3] - s[1]
            l = (dx * dx + dy * dy) ** 0.5 or 1.0
            best = (dx / l, dy / l)
    return best or (1.0, 0.0)


def gen_network(codes, report):
    cards = {ln: parse_card(ln) for ln in ORDER}
    segs_of = {ln: cards[ln]['segs'] for ln in ORDER}
    color_of = {ln: cards[ln]['color'] for ln in ORDER}
    pins = {}
    for ln in ORDER:
        for nm, cx, cy in cards[ln]['pins']:
            pins.setdefault(nm, []).append((ln, cx, cy))

    chips = []   # (nm, line, cx, cy, w)
    for nm, lst in pins.items():
        items = []
        for ln, cx, cy in lst:
            key = (nm, ln)
            if key not in codes:
                report['no_code'].append('全网/%s@%s' % (nm, ln))
                continue
            disp, serial = codes[key]
            items.append((ln, cx, cy, chip_w(disp, serial, font_of(disp, False))))
        if not items:
            continue
        tag, placed, fails, worst = place_station(items, segs_of)
        for ln, cx, cy, w in placed:
            chips.append((nm, ln, cx, cy, w))
        if fails:
            report['touch_fail'].append('%s[%s]: %s' % (nm, tag, ','.join(fails)))
        report['layout_tags'][tag] = report['layout_tags'].get(tag, 0) + 1

    # 跨站牌重叠 -> 沿本线走廊推让(牌滑线, 触线保持)
    def rect_of(c):
        return (c[2] - c[4] / 2, c[3] - H / 2, c[4], H)

    for i in range(len(chips)):
        for j in range(i + 1, len(chips)):
            if chips[i][0] == chips[j][0]:
                continue
            a, b = chips[i], chips[j]
            if not rects_overlap(rect_of(a), rect_of(b)):
                continue
            resolved = False
            for k in (j, i):
                nm, ln, cx, cy, w = chips[k]
                ux, uy = corridor_tangent(segs_of[ln], cx, cy)
                for step in range(1, 9):
                    for sgn in (1, -1):
                        nx, ny = cx + sgn * step * 2.0 * ux, cy + sgn * step * 2.0 * uy
                        rect = (nx - w / 2, ny - H / 2, w, H)
                        clash = any(o is not chips[k] and o[0] != nm and rects_overlap(rect, rect_of(o)) for o in chips)
                        touch = min(rect_seg_dist(rect, s) for s in segs_of[ln]) <= CORR_HALF + 0.01
                        if not clash and touch:
                            chips[k] = (nm, ln, nx, ny, w)
                            resolved = True
                            break
                    if resolved:
                        break
                if resolved:
                    break
            if not resolved:
                report['chip_overlaps'].append('%s(%s)x%s(%s)' % (a[0], a[1], b[0], b[1]))

    # 多线组外描边圈(官图用例: 换乘组整体加一圈黑描边白底包络) + 组矩形(避让障碍)
    by_st = {}
    for nm, ln, cx, cy, w in chips:
        by_st.setdefault(nm, []).append((cx - w / 2, cy - H / 2, w, H))
    rings = []          # (nm, rect)
    obstacles = {}      # nm -> [rect]  多线站=圈矩形, 单线站=牌矩形
    for nm, rects in by_st.items():
        if len(rects) >= 2:
            x0 = min(r[0] for r in rects) - RING_PAD
            y0 = min(r[1] for r in rects) - RING_PAD
            x1 = max(r[0] + r[2] for r in rects) + RING_PAD
            y1 = max(r[1] + r[3] for r in rects) + RING_PAD
            ring = (x0, y0, x1 - x0, y1 - y0)
            rings.append((nm, ring))
            obstacles[nm] = [ring]
        else:
            obstacles[nm] = rects
    ring_bad = []
    for nm, ring in rings:
        for nm2, rects2 in obstacles.items():
            if nm2 == nm:
                continue
            if any(_gap(ring, r2) < 0.3 for r2 in rects2):
                ring_bad.append('%s x %s' % (nm, nm2))

    # 外圈冲突解析: 优先沿走廊推让邻站单牌(触线保持), 不行则逐档收缩本圈内衬
    def shift_station_chips(nm2):
        idx = [i for i, c in enumerate(chips) if c[0] == nm2]
        if len(idx) != 1:
            return False   # 多牌组不动(整组重排复杂, 走收缩)
        i = idx[0]
        nm, ln, cx, cy, w = chips[i]
        ux, uy = corridor_tangent(segs_of[ln], cx, cy)
        others = [r for nm3, rects3 in obstacles.items() if nm3 != nm2 for r in rects3]
        for step in range(1, 9):
            for sgn in (1, -1):
                d = sgn * step * 2.0
                rect = (cx + d * ux - w / 2, cy + d * uy - H / 2, w, H)
                touch = min(rect_seg_dist(rect, s) for s in segs_of[ln]) <= CORR_HALF + 0.01
                if touch and all(_gap(rect, o) >= 0.3 for o in others):
                    chips[i] = (nm, ln, cx + d * ux, cy + d * uy, w)
                    obstacles[nm2] = [rect]
                    return True
        return False

    def shrink_ring(nm, ring_rect):
        best = ring_rect
        for pad in (1.8, 1.2, 0.8):
            rects = by_st[nm]
            r2 = (min(r[0] for r in rects) - pad, min(r[1] for r in rects) - pad,
                  max(r[0] + r[2] for r in rects) - min(r[0] for r in rects) + 2 * pad,
                  max(r[1] + r[3] for r in rects) - min(r[1] for r in rects) + 2 * pad)
            ok = all(_gap(r2, o) >= 0.3 for nm3, rects3 in obstacles.items() if nm3 != nm
                     for o in rects3)
            if ok:
                return r2
            best = r2
        return best   # 收到底仍犯: 记录

    resolved, leftover = [], []
    for nm, ring in rings:
        conflicts = [nm2 for nm2 in obstacles if nm2 != nm and any(_gap(ring, r) < 0.3 for r in obstacles[nm2])]
        if not conflicts:
            continue
        fixed = False
        for nm2 in conflicts:
            if not shift_station_chips(nm2):
                continue
            if all(_gap(ring, r) >= 0.3 for nm2b in obstacles if nm2b != nm for r in obstacles[nm2b]):
                fixed = True
                resolved.append('%s:推让%s' % (nm, nm2))
                break
        if not fixed:
            r2 = shrink_ring(nm, ring)
            rings[rings.index((nm, ring))] = (nm, r2)
            obstacles[nm] = [r2]
            if all(_gap(r2, r) >= 0.3 for nm2b in obstacles if nm2b != nm for r in obstacles[nm2b]):
                resolved.append('%s:收缩' % nm)
            else:
                leftover.append(nm)
    report['ring_fix'] = resolved
    report['ring_overlaps'] = leftover

    # 组装 SVG
    path = os.path.join(LINES_DIR, 'network-全网.svg')
    t = open(path, encoding='utf-8').read()
    for gid in ('站圆', '换乘标记'):
        m = re.search(r'<g id="%s">.*?</g>' % gid, t, re.S)
        t = t[:m.start()] + t[m.end():]
    # 站名避让(牌/圈全部落定后): 钉位=该站各线钉质心
    pin_center = {}
    for nm, lst in pins.items():
        pin_center[nm] = (sum(p[1] for p in lst) / len(lst), sum(p[2] for p in lst) / len(lst))
    all_segs = [s for ln in ORDER for s in segs_of[ln]]
    new_labels = nudge_labels(t, pin_center, obstacles, all_segs, report, '全网')
    if new_labels is not None:
        t = re.sub(r'(<g id="站名标注"[^>]*>).*?(</g>)',
                   lambda mm: mm.group(1) + new_labels + mm.group(2), t, count=1, flags=re.S)
    rings_svg = ''.join(
        f'<rect x="{r[0]:.2f}" y="{r[1]:.2f}" width="{r[2]:.2f}" height="{r[3]:.2f}" rx="5" '
        f'data-ring="{nm}" fill="#FFFFFF" stroke="{INK}" stroke-width="1.4"/>'
        for nm, r in rings)
    chips_svg = ''.join(
        chip_svg(cx, cy, w, H, color_of[ln], codes[(nm, ln)][0], codes[(nm, ln)][1],
                 font_of(codes[(nm, ln)][0], False))
        for nm, ln, cx, cy, w in chips)
    mn = re.search(r'<g id="站名标注"[^>]*>.*?</g>', t, re.S)
    t = t[:mn.end()] + '<g id="编号牌" font-family="\'Microsoft YaHei\', \'PingFang SC\', sans-serif">' + rings_svg + chips_svg + '</g>' + t[mn.end():]
    open(os.path.join(LINES_DIR, 'network-全网.codes.svg'), 'w', encoding='utf-8').write(
        expand_viewbox(t, [r for _, r in rings] + [(cx - w / 2, cy - H / 2, w, H) for nm, ln, cx, cy, w in chips]))

    by_station = {}
    for nm, ln, cx, cy, w in chips:
        by_station.setdefault(nm, []).append(ln)
    report['net_chips'] = len(chips)
    report['net_multi_stations'] = sum(1 for v in by_station.values() if len(v) > 1)
    return chips


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    codes = load_codes()
    report = {'no_code': [], 'line_chips': {}, 'touch_fail': [], 'chip_overlaps': [], 'layout_tags': {}}
    for line in ORDER:
        gen_line_card(line, codes, report)
    gen_network(codes, report)
    open(REPORT, 'w', encoding='utf-8').write(json.dumps(report, ensure_ascii=False, indent=1))
    print('单线牌数:', report['line_chips'])
    print('全网牌数:', report['net_chips'], ' 多牌站:', report['net_multi_stations'], ' 模式:', report['layout_tags'])
    print('无码站(留圆):', report['no_code'])
    print('触线FAIL:', report['touch_fail'])
    print('牌重叠:', report['chip_overlaps'])


if __name__ == '__main__':
    main()
