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
# 终稿锚定层(单线卡): data/codes-final-pins.json 的 cards 段, 缺文件=空表
_final_pins_path = os.path.join(ROOT, 'data', 'codes-final-pins.json')
_fp = json.load(open(_final_pins_path, encoding='utf-8')) if os.path.exists(_final_pins_path) else {}
CARD_FINAL = _fp.get('cards', {})

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
def norm_name(nm):
    """站名归一: 東->东(繁简) + 去尾'站'(兜底口径; 广州南站等'站'尾真名由原名优先保住)."""
    nm = nm.replace('東', '东')
    if nm.endswith('站') and len(nm) > 2:
        return nm[:-1]
    return nm


def load_codes():
    """-> codes[(站名, 卡线名)] = (显示线号, 序号). 原名优先, 归一兜底(東圃站->东圃)."""
    codes = {}
    with open(CSV_PATH, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            nm = r['站名']
            card, disp = csv_line_to_card(r['线路'])
            if card is None:
                continue
            if (nm, card) not in codes:
                codes[(nm, card)] = (disp, r['编号'])
            stripped = norm_name(nm)
            if stripped != nm and (stripped, card) not in codes:
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
FONT = 5.5        # 牌字号(全网, 2026-10-23 五轮再缩)
FONT_CARD = 6.0   # 单线卡字号
APM_FONT = 4.1    # APM 专用小字号+textLength压缩(用户: APM牌缩到与数字牌同大)
APM_FONT_CARD = 4.5
H = 9.0           # 牌高
H_CARD = 10.0
PADX = 1.8        # 左右内边距
SEPW = 2.6        # 分隔区宽(含两侧空隙)
GAP = 1.0         # 组内牌间缝
CORR_HALF = 3.5   # 走廊 stroke-width 7 半宽(触线判定含线宽)
RING_PAD = 1.2    # 多线组外描边圈的白衬宽(用户: 描边贴紧内部胶囊, 五轮2.5->1.2)
RIM = 0.7         # 外圈黑边线宽
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


def cell_a_std(card):
    """定宽线号格(牌宽计算基准, 恒 max(两位数字, GF))."""
    std = FONT_CARD if card else FONT
    return max(part_w('22', std), part_w('GF', std))


def cell_a(line_disp, card):
    """竖线位置(线号格宽): 牌外框恒宽不变, 只有竖线随线号位数自适应——
    1位数字线号窄格(文本+1.9呼吸, 2026-10-23 七轮 用户: 竖线左移给序号让空间),
    2位/GF/APM 维持定宽格(APM 压缩基准不变); 省出的宽度由序号格吸收."""
    std = FONT_CARD if card else FONT
    if len(line_disp) == 1 and line_disp.isdigit():
        return part_w(line_disp, std) + 1.9
    return cell_a_std(card)


def cell_b(card):
    """序号格定宽(两位, 标准字号)——牌宽计算的基准值(渲染时序号格=牌宽-边距-线号格-分隔区)."""
    std = FONT_CARD if card else FONT
    return part_w('00', std)


def chip_need_w(line_disp, serial, card):
    """牌需求宽(恒定): 定宽线号格与线号实测取 max + 分隔区 + 两位序号格
    -> 全部牌(数字/GF/APM/支线序号)全等宽; 1位数字线号的竖线左移不改变牌宽."""
    std = FONT_CARD if card else FONT
    return 2 * PADX + max(cell_a_std(card), part_w(line_disp, std) if line_disp != 'APM' else 0) + SEPW + cell_b(card)


def chip_w(line_disp, serial, card):
    import math
    return math.ceil(chip_need_w(line_disp, serial, card) * 2) / 2.0


def serial_font(serial, fs):
    """支线序号(01-1式, 宽于两位格)缩小到 0.75 档 + textLength 压缩(同 APM 处理)."""
    return round(fs * 0.75, 1)


def chip_svg(cx, cy, w, h, color, line_disp, serial, fs, card):
    """一枚编号牌: 白底胶囊+线色边框+线色竖分隔线+黑字两段(定宽格居中);
    超宽文本(APM线号/支线序号)小字号+textLength 压入标准格 -> 全牌同大."""
    x0, y0 = cx - w / 2, cy - h / 2
    ca = cell_a(line_disp, card)
    if line_disp == 'APM':
        # 十一轮末 用户: APM竖线右移给三字母多点空间——线号格=牌宽-边距-分隔-两位小字序号格,
        # 序号两位小字自然宽即可, APM以95%近原生宽渲染(旧: 压入7.3格=73%重压)
        sfs0 = APM_FONT_CARD if card else APM_FONT
        ca = w - 2 * PADX - SEPW - part_w('00', sfs0)
    cb = w - 2 * PADX - ca - SEPW   # 序号格=余量(1位数字线号竖线左移后序号格变宽)
    xline = x0 + PADX + ca / 2
    xsep = x0 + PADX + ca + SEPW / 2
    xser = x0 + PADX + ca + SEPW + cb / 2
    # 墨迹标定: central 基准在雅黑下系统性偏低 ~0.017em(十轮实测牌内墨迹中心 +0.10pt),
    # ty = cy - 0.02fs 抬升; V6 门禁逐牌复测
    sfs = fs
    stl = ''
    std = FONT_CARD if card else FONT
    if part_w(serial, std) > cb + 0.01:
        sfs = serial_font(serial, std)
        stl = f' textLength="{cb:.2f}" lengthAdjust="spacingAndGlyphs"'
    tyL = cy - 0.02 * fs
    tyS = cy - 0.02 * sfs
    tl = (f' textLength="{ca:.2f}" lengthAdjust="spacingAndGlyphs"') if line_disp == 'APM' else ''
    return (
        f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{w:.2f}" height="{h:.2f}" rx="{h / 2:.2f}" '
        f'fill="#FFFFFF" stroke="{color}" stroke-width="1.0"/>' +
        f'<line x1="{xsep:.2f}" y1="{y0 + 1.2:.2f}" x2="{xsep:.2f}" y2="{y0 + h - 1.2:.2f}" '
        f'stroke="{color}" stroke-width="0.8"/>' +
        f'<text x="{xline:.2f}" y="{tyL:.2f}" text-anchor="middle" dominant-baseline="central"'
        f'{tl} font-size="{fs}" font-weight="700" fill="#000000">{line_disp}</text>' +
        f'<text x="{xser:.2f}" y="{tyS:.2f}" text-anchor="middle" dominant-baseline="central"'
        f'{stl} font-size="{sfs}" font-weight="700" fill="#000000">{serial}</text>'
    )


# ---------- 矩形-线段距离 ----------
def dist_pts(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


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
LABEL_CORR_GAP = 4.5    # 标签-走廊净距下限(十六轮 用户怒报大量文字压线: 旧1.0量到走廊中心线,
                        # 走廊描边±3.5 -> 中心线距1.0~3.5的标签全嵌在线上; 改=走廊边缘外1.0=中心线4.5)
LABEL_LBL_GAP = 1.5     # 标签-标签净距下限(十五轮 0.3->1.5: 冼村与妇儿中心标签距1.6"合法但太近"被用户报)


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


def _seg_closest(rect, seg):
    """矩形中心在线段上的投影点(clamp进段)——走廊推让的方向基准."""
    ax, ay, bx2, by2 = seg
    cx, cy = rect[0] + rect[2] / 2, rect[1] + rect[3] / 2
    dx, dy = bx2 - ax, by2 - ay
    dd = dx * dx + dy * dy
    t = 0.0 if dd == 0 else max(0.0, min(1.0, ((cx - ax) * dx + (cy - ay) * dy) / dd))
    return (ax + t * dx, ay + t * dy)


def _gap(r1, r2):
    """两矩形净距(重叠为负, 量级=角部侵入深度).
    ⚠️ox 的 r2 x1 = r2[0]+r2[2](宽)——二~六轮曾误写 r2[3](高), 所有净距判定被扭曲
    (广州东站标签 0.4px 擦边漏推根因, 2026-10-23 六轮修复)."""
    ox = min(r1[0] + r1[2], r2[0] + r2[2]) - max(r1[0], r2[0])
    oy = min(r1[1] + r1[3], r2[1] + r2[3]) - max(r1[1], r2[1])
    if ox >= 0 and oy >= 0:
        return -min(ox, oy)
    return max(-ox if ox < 0 else 0, -oy if oy < 0 else 0)


def nudge_labels(svg_text, pin_by_name, chips_by_station, segs, report, tag, align_centers=None, near_trigger=8.0):
    """编号版站名避让: 与牌相犯(<净距)的标签组沿 钉->标 方向外推(0.5px步进, ±35°/±70°轮换),
    推移校验: 全部牌净距>=LABEL_CHIP_GAP, 走廊净距>=LABEL_CORR_GAP, 其他标签>=LABEL_LBL_GAP.
    对齐pass(七/十轮 用户: 文字位置跟序号胶囊的中心没对齐): 有牌站标签按主偏移轴吸附组心
    (侧置->y对齐组心y / 上下置->x对齐组心x), 带同套净距校验, 放不下则保持原位.
    返回新的站名标注组 innerHTML(全部文本, 位置按需更新)."""
    labels, m = parse_labels(svg_text)
    if not labels:
        return None
    groups = label_groups(labels, set(pin_by_name))
    # 密集档铁律(十七轮末 用户: 放不下的那些文字不用挪位置——底图6px位即终稿):
    # fs<7 标签一律保持底图字号/位置/光环, 不做7.5升级试探(曾把夹缝四站挪乱),
    # 仅当与牌重叠时按密集规则(走廊豁免)推离; 7.5常规标签才走完整避让链,
    # 真放不下(fs>=7 仍违规)才降6px+光环(降档pass)
    downgraded = []
    all_chip_rects = [r for lst in chips_by_station.values() for r in lst]
    cur_boxes = {nm: group_box(g) for nm, g in groups.items()}
    order = sorted(groups.items(), key=lambda kv: -group_box(kv[1])[2] * group_box(kv[1])[3])
    moved, unresolved, relaxed = [], [], []
    import math as _m
    for nm, g in order:
        box = cur_boxes[nm]
        bcx, bcy = box[0] + box[2] / 2, box[1] + box[3] / 2
        # ⚠️必须精确距离筛选——中点±70预筛会漏掉中点在远处的长线段(3号线竖段中点距嘉禾望岗
        # 标签223pt但线段本体贴着标签), 十一轮标签被推上走廊的根因
        near_segs = [s for s in segs if rect_seg_dist((bcx - 35, bcy - 35, 70, 70), s) < 70]
        dense = max(l2['fs'] for l2 in g) < 7.0   # 密集档小字(底图逐档缩小): 允许压线, 走廊豁免
        corr_viol = None if dense else (min(near_segs, key=lambda s: rect_seg_dist(box, s)) if near_segs else None)
        corr_d = rect_seg_dist(box, corr_viol) if corr_viol is not None else 9e9
        chip_viol = min(all_chip_rects, key=lambda r: _gap(box, r), default=None)
        chip_d = _gap(box, chip_viol) if chip_viol is not None else 9e9
        if chip_d >= LABEL_CHIP_GAP and corr_d >= LABEL_CORR_GAP:
            continue   # 牌与走廊都净(fs>=7的标签走廊违规也触发; 小字档只查牌)
        # 推移基准方向: 远离最近违规者(牌或走廊线段的最近点)
        if chip_d < corr_d and chip_viol is not None:
            vcx, vcy = chip_viol[0] + chip_viol[2] / 2, chip_viol[1] + chip_viol[3] / 2
            dx, dy = bcx - vcx, bcy - vcy
        elif corr_viol is not None:
            q = _seg_closest(box, corr_viol)
            dx, dy = bcx - q[0], bcy - q[1]
        else:
            pin = pin_by_name.get(nm)
            dx, dy = (bcx - pin[0], bcy - pin[1]) if pin else (0.0, -1.0)
        l = (dx * dx + dy * dy) ** 0.5 or 1.0
        bx, by = dx / l, dy / l
        near_lbls = [cur_boxes[n2] for n2 in cur_boxes if n2 != nm
                     and abs(cur_boxes[n2][0] - box[0]) < 60 and abs(cur_boxes[n2][1] - box[1]) < 60]
        done = False
        relax = None
        # 兜底链: 全约束 -> 放标签互斥 -> 放走廊净距(十一轮改: 末档不做首个接受——约束一放
        # 原位0.5pt处即"合规"被秒接受=没动, 改全角度×全程取走廊净距最大位, 体育中心南先例)
        for relax_lbl, relax_corr in ((False, False), (True, False), (True, True)):
            best = None   # (corridor_clearance, d, ux, uy, r2)  末档用
            for ang in (0, 35, -35, 70, -70, 105, -105, 180):
                ra = _m.radians(ang)
                ca_, sa_ = _m.cos(ra), _m.sin(ra)
                ux, uy = bx * ca_ - by * sa_, bx * sa_ + by * ca_
                for step in range(1, 57):   # 上限28px: 品字外圈宽~51px/体育中心南出1号线口袋需24.5px
                    d = step * 0.5
                    r2 = (box[0] + ux * d, box[1] + uy * d, box[2], box[3])
                    if not _clear_rect(r2, all_chip_rects, LABEL_CHIP_GAP):
                        continue
                    if relax_corr:
                        cd = min((rect_seg_dist(r2, s) for s in near_segs), default=9e9)
                        if near_segs and (best is None or cd > best[0]):
                            best = (cd, d, ux, uy, r2)
                        continue
                    if not all(rect_seg_dist(r2, s) >= LABEL_CORR_GAP for s in near_segs):
                        continue
                    if not relax_lbl and not _clear_rect(r2, near_lbls, LABEL_LBL_GAP):
                        continue
                    for l2 in g:
                        l2['x'] = round(l2['x'] + ux * d, 2)
                        l2['y'] = round(l2['y'] + uy * d, 2)
                    cur_boxes[nm] = r2
                    moved.append((nm, d, ang))
                    done = True
                    relax = 'lbl' if relax_lbl else None
                    break
                if done:
                    break
            if done:
                break
            if relax_corr and best is not None:
                cd, d, ux, uy, r2 = best
                if cd > corr_d + 0.05:   # 比原位更优才动
                    for l2 in g:
                        l2['x'] = round(l2['x'] + ux * d, 2)
                        l2['y'] = round(l2['y'] + uy * d, 2)
                    cur_boxes[nm] = r2
                    moved.append((nm, d, 0))
                    done = True
                    relax = 'corr'
        if done and relax:
            relaxed.append('%s(%s)' % (nm, relax))
        if not done:
            unresolved.append(nm)

    # 对齐pass: 有牌站的标签吸附组心(十轮: 单牌站也参与——斜走廊站标签沿45°摆位,
    # 对小圆点(9pt)无感但对牌(20.5x9)垂直差1-2pt可见, 厦滘/大石/沙溪用户三报)
    aligned = []
    if align_centers:
        for nm, (gcx, gcy) in align_centers.items():
            if nm not in cur_boxes:
                continue
            box = cur_boxes[nm]
            if not _clear_rect(box, all_chip_rects, LABEL_CHIP_GAP):
                continue   # 仍相犯的以避让结果为准
            bcx, bcy = box[0] + box[2] / 2, box[1] + box[3] / 2
            dx, dy = bcx - gcx, bcy - gcy
            if max(abs(dx), abs(dy)) < 1.0:
                continue   # 已对齐(十轮: 阈值2->1, 斜走廊站标签45°摆位两轴都偏1-2pt)
            axis_y = abs(dx) >= abs(dy)   # 侧置->对y, 上下置->对x
            g = groups[nm]
            near_segs = [s for s in segs if rect_seg_dist((bcx - 35, bcy - 35, 70, 70), s) < 70]
            near_lbls = [cur_boxes[n2] for n2 in cur_boxes if n2 != nm
                         and abs(cur_boxes[n2][0] - box[0]) < 60 and abs(cur_boxes[n2][1] - box[1]) < 60]
            for jitter in (0, 2, -2, 4, -4):
                if axis_y:
                    d = gcy - bcy + jitter
                    if abs(d) < 1:
                        break
                    r2 = (box[0], box[1] + d, box[2], box[3])
                else:
                    d = gcx - bcx + jitter
                    if abs(d) < 1:
                        break
                    r2 = (box[0] + d, box[1], box[2], box[3])
                if (not _clear_rect(r2, all_chip_rects, LABEL_CHIP_GAP) or
                        not all(rect_seg_dist(r2, s) >= LABEL_CORR_GAP for s in near_segs) or
                        not _clear_rect(r2, near_lbls, LABEL_LBL_GAP)):
                    continue
                for l2 in g:
                    if axis_y:
                        l2['y'] = round(l2['y'] + (gcy - bcy + jitter), 2)
                    else:
                        l2['x'] = round(l2['x'] + (gcx - bcx + jitter), 2)
                cur_boxes[nm] = r2
                aligned.append(nm)
                break

    # 逼近pass v3(十六轮 用户: 冼村歪在右上角/天河南漂在线上): 四正方位槽优先——
    # R/L/U/D 贴边居中槽(净距2pt, 密集档免走廊校验)先试, 选距当前最近的合法槽;
    # 无合法槽再16方位×40pt全向扫描(十二轮海珠广场先例). 通用机制无站名硬编码.
    approached = []
    if align_centers:
        import math as _m2
        for nm, (gcx2, gcy2) in align_centers.items():
            if nm not in cur_boxes or nm not in chips_by_station:
                continue
            box = cur_boxes[nm]
            bcx, bcy = box[0] + box[2] / 2, box[1] + box[3] / 2
            d0 = ((bcx - gcx2) ** 2 + (bcy - gcy2) ** 2) ** 0.5
            own = chips_by_station[nm]
            gx0 = min(r[0] for r in own); gy0 = min(r[1] for r in own)
            gx1 = max(r[0] + r[2] for r in own); gy1 = max(r[1] + r[3] for r in own)
            xov = box[0] < gx1 and box[0] + box[2] > gx0
            yov = box[1] < gy1 and box[1] + box[3] > gy0
            straddle = (xov != yov)   # 恰一轴相交=斜角跨骑(冼村歪在右上角型), 距离再近也要槽位归正
            if min(_gap(box, r) for r in own) <= near_trigger and not straddle:
                continue
            g = groups[nm]
            dense = max(l2['fs'] for l2 in groups[nm]) < 7.0   # 密集档小字: 压线允许, 贴近不受走廊限
            near_segs = [] if dense else [s for s in segs if rect_seg_dist((gcx2 - 45, gcy2 - 45, 90, 90), s) < 90]
            near_lbls = [cur_boxes[n2] for n2 in cur_boxes if n2 != nm
                         and abs(cur_boxes[n2][0] - box[0]) < 60 and abs(cur_boxes[n2][1] - box[1]) < 60]
            allchips = [r for lst in chips_by_station.values() for r in lst]   # 含自牌: 逼近也须保净距

            def _legal(r2):
                return (_clear_rect(r2, allchips, LABEL_CHIP_GAP) and
                        all(rect_seg_dist(r2, s) >= LABEL_CORR_GAP for s in near_segs) and
                        _clear_rect(r2, near_lbls, LABEL_LBL_GAP))

            # ①四正方位槽: 贴边2pt+垂直居中, ±jitter
            slot_best = None   # (dist_to_current, r2)
            for side in 'RLUD':
                for jit in (0, 2, -2, 4, -4):
                    if side == 'R':
                        r2 = (gx1 + 2.0, gcy2 - box[3] / 2 + jit, box[2], box[3])
                    elif side == 'L':
                        r2 = (gx0 - 2.0 - box[2], gcy2 - box[3] / 2 + jit, box[2], box[3])
                    elif side == 'U':
                        r2 = (gcx2 - box[2] / 2, gy0 - 2.0 - box[3], box[2], box[3])
                    else:
                        r2 = (gcx2 - box[2] / 2, gy1 + 2.0, box[2], box[3])
                    if not _legal(r2):
                        continue
                    dc = ((r2[0] + r2[2] / 2 - bcx) ** 2 + (r2[1] + r2[3] / 2 - bcy) ** 2) ** 0.5
                    if slot_best is None or dc < slot_best[0]:
                        slot_best = (dc, r2)
            if slot_best is not None and (straddle or slot_best[0] < d0 - 1.0):
                # straddle(斜角跨骑)时合法槽位即接受——归正优先于距离(冼村先例:
                # 槽位距当前14.8>当前距组心13.3 被"更近"条件拒掉=歪位不动的根因)
                r2 = slot_best[1]
                mdx, mdy = r2[0] - box[0], r2[1] - box[1]
                for l2 in g:
                    l2['x'] = round(l2['x'] + mdx, 2)
                    l2['y'] = round(l2['y'] + mdy, 2)
                cur_boxes[nm] = r2
                approached.append('%s:槽位' % nm)
                continue
            # ②全向扫描兜底
            best = None   # (dist_to_center, dx, dy, r2)
            for k in range(16):
                ra = _m2.radians(k * 22.5)
                ux, uy = _m2.cos(ra), _m2.sin(ra)
                for step in range(1, 81):
                    dd = step * 0.5
                    r2 = (box[0] + ux * dd, box[1] + uy * dd, box[2], box[3])
                    if not _legal(r2):
                        continue   # 不break: 走廊带挡住的更远处可能合法(海珠广场最优位在31.6pt外)
                    dc = ((r2[0] + r2[2] / 2 - gcx2) ** 2 + (r2[1] + r2[3] / 2 - gcy2) ** 2) ** 0.5
                    if best is None or dc < best[0]:
                        best = (dc, ux * dd, uy * dd, r2)
            if best is not None and best[0] < d0 - 1.0:
                for l2 in g:
                    l2['x'] = round(l2['x'] + best[1], 2)
                    l2['y'] = round(l2['y'] + best[2], 2)
                cur_boxes[nm] = best[3]
                approached.append('%s:%.1f->%.1f' % (nm, d0, best[0]))
    # 降档pass(十七轮 用户: 实在没地方显示就缩小+描边, 全站统一规则): 7.5px常规仍违反
    # 走廊边净距/牌净距的组 -> 回原位降6px+白光环, 密集档重放(允许压线, 只查牌/邻标)
    orig_pos = {nm: [(l2['x'], l2['y']) for l2 in g] for nm, g in groups.items()}
    for nm, g in order:
        box = cur_boxes[nm]
        if max(l2['fs'] for l2 in g) < 7.0:
            continue   # 已是密集档
        bcx, bcy = box[0] + box[2] / 2, box[1] + box[3] / 2
        near_segs2 = [s for s in segs if rect_seg_dist((bcx - 35, bcy - 35, 70, 70), s) < 70]
        corr_bad = near_segs2 and min(rect_seg_dist(box, s) for s in near_segs2) < LABEL_CORR_GAP
        chip_bad = any(_gap(box, r) < LABEL_CHIP_GAP for r in all_chip_rects)
        # 离牌太远(>12pt)也算"没地方"——推到老远合法位不如降档贴身(用户: 实在没地方就缩小)
        own2 = chips_by_station.get(nm)
        far = own2 and min(_gap(box, r) for r in own2) > 12.0
        if not (corr_bad or chip_bad or far):
            continue
        # 降档: 回原位, 6px+光环
        for l2, (ox2, oy2) in zip(g, orig_pos[nm]):
            l2['x'], l2['y'] = ox2, oy2
            if not l2['content'].isascii():
                l2['fs'] = 6.0
                l2['attrs'] = re.sub(r' font-size="[\d.]+"', ' font-size="6"', l2['attrs'])
                if 'paint-order' not in l2['attrs']:
                    l2['attrs'] += ' style="paint-order:stroke;stroke:#FFFFFF;stroke-width:2.2;stroke-linejoin:round"'
        box = group_box(g)
        cur_boxes[nm] = box
        bcx, bcy = box[0] + box[2] / 2, box[1] + box[3] / 2
        near_lbls2 = [cur_boxes[n3] for n3 in cur_boxes if n3 != nm
                      and abs(cur_boxes[n3][0] - box[0]) < 60 and abs(cur_boxes[n3][1] - box[1]) < 60]
        pin2 = pin_by_name.get(nm)
        dx, dy = (bcx - pin2[0], bcy - pin2[1]) if pin2 else (0.0, -1.0)
        viol2 = min(all_chip_rects, key=lambda r: _gap(box, r), default=None)
        if viol2 is not None and _gap(box, viol2) < 0:
            vcx2, vcy2 = viol2[0] + viol2[2] / 2, viol2[1] + viol2[3] / 2
            dx, dy = bcx - vcx2, bcy - vcy2
        l3 = (dx * dx + dy * dy) ** 0.5 or 1.0
        bx3, by3 = dx / l3, dy / l3
        placed2 = False
        for ang in (0, 35, -35, 70, -70, 105, -105, 180):
            ra = _m.radians(ang)
            ux, uy = bx3 * _m.cos(ra) - by3 * _m.sin(ra), bx3 * _m.sin(ra) + by3 * _m.cos(ra)
            for step in range(1, 57):
                dd = step * 0.5
                r2 = (box[0] + ux * dd, box[1] + uy * dd, box[2], box[3])
                if (_clear_rect(r2, all_chip_rects, LABEL_CHIP_GAP) and
                        _clear_rect(r2, near_lbls2, 0.5)):
                    for l2 in g:
                        l2['x'] = round(l2['x'] + ux * dd, 2)
                        l2['y'] = round(l2['y'] + uy * dd, 2)
                    cur_boxes[nm] = r2
                    downgraded.append(nm)
                    placed2 = True
                    break
            if placed2:
                break
        if not placed2:
            downgraded.append(nm + '(原位降档)')

    rep = report.setdefault('label_nudge', {}).setdefault(tag, {})
    rep['downgraded'] = downgraded
    rep['moved'] = len(moved)
    rep['max_shift'] = max((d for _, d, _ in moved), default=0)
    rep['relaxed'] = relaxed
    rep['unresolved'] = unresolved
    rep['aligned'] = aligned
    rep['approached'] = approached
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
            w = chip_w(disp, serial, True)
            chips.append((nm, disp, serial, cx, cy, w, H_CARD, fs))
        else:
            kept.append((nm, cx, cy))
            report['no_code'].append('%s/%s' % (line, nm))
    m = re.search(r'<g id="站圆">.*?</g>', t, re.S)
    circles_svg = ''.join(
        f'<circle cx="{cx}" cy="{cy}" r="4.5" data-nm="{nm}" style="fill:#FFFFFF;stroke:{color};stroke-width:2"/>'
        for nm, cx, cy in kept)
    chips_svg = ''.join(
        chip_svg(cx, cy, w, H_CARD, color, disp, serial, fs, True)
        for nm, disp, serial, cx, cy, w, h, fs in chips)
    t2 = t[:m.start()] + ('<g id="站圆">' + circles_svg + '</g>' if circles_svg else '') + t[m.end():]
    # 站名避让: 与牌相犯的标签沿钉->标方向外推(缩小后仍压的才推)
    chips_by_station = {}
    for nm, disp, serial, cx, cy, w, h, fs in chips:
        chips_by_station.setdefault(nm, []).append((cx - w / 2, cy - H_CARD / 2, w, H_CARD))
    align_c = {nm: (cx, cy) for nm, disp, serial, cx, cy, w, h, fs in chips}
    # 单线卡贴近优先(用户: 文字离站点远的优先级高于挪位置): 4pt即触发槽位贴边
    new_labels = nudge_labels(t2, {nm: (cx, cy) for nm, cx, cy in card['pins']},
                              chips_by_station, card['segs'], report, line, align_c, near_trigger=4.0)
    if new_labels is not None:
        t2 = re.sub(r'(<g id="站名标注"[^>]*>).*?(</g>)',
                    lambda mm: mm.group(1) + new_labels + mm.group(2), t2, count=1, flags=re.S)
    mn = re.search(r'<g id="站名标注"[^>]*>.*?</g>', t2, re.S)
    # 终稿锚定层(单线卡, 同全网): 底图已回写终版站名组, 整组钉定保重跑逐字节一致
    _cfin = CARD_FINAL.get(line)
    if _cfin and _cfin.get('labels_inner'):
        t2 = t2[:mn.start()] + \
             re.sub(r'(<g id="站名标注"[^>]*>).*?(</g>)',
                    lambda mm: mm.group(1) + _cfin['labels_inner'] + mm.group(2), mn.group(0), count=1, flags=re.S) + \
             t2[mn.end():]
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
    """标准几何候选(十三轮 用户: 都说了要标准的T和品字, 不要乱搞):
    槽位一律以组心(钉均值)为中心的对称标准形——行内等隙((w+GAP)/2)、行距恒定(H+GAP)、
    单牌槽正对牌对中心; 组心恒=钉质心(模式切换锚点); 单牌槽沿用自己钉x是旧版歪T/偏左根因, 已改居中。
    线->槽配对一律由 place_station 置换搜索按方向匹配决定。"""
    n = len(items)
    if n == 1:
        ln, px, py, w = items[0]
        return [('S', [(ln, px, py, w)])]
    gx = sum(it[1] for it in items) / n
    gy = sum(it[2] for it in items) / n
    # 组心=钉质心锚定(十三轮 用户: 槽位要对齐钉位, 两模式切换位置稳定/便于扩展)
    dx = (items[0][3] + GAP) / 2   # 行内半距(全牌等宽)
    dy = (H + GAP) / 2             # 行半距
    ws = [it[3] for it in items]
    cands = []
    if n == 2:
        cands.append(('V', [(items[0][0], gx, gy - dy, ws[0]), (items[1][0], gx, gy + dy, ws[1])]))
        cands.append(('H', [(items[0][0], gx - dx, gy, ws[0]), (items[1][0], gx + dx, gy, ws[1])]))
    elif n == 3:
        cands.append(('P3', [(items[0][0], gx - dx, gy - dy, ws[0]), (items[1][0], gx + dx, gy - dy, ws[1]),
                             (items[2][0], gx, gy + dy, ws[2])]))
        cands.append(('P3D', [(items[0][0], gx, gy - dy, ws[0]), (items[1][0], gx - dx, gy + dy, ws[1]),
                              (items[2][0], gx + dx, gy + dy, ws[2])]))
        cands.append(('V', [(items[0][0], gx, gy - (H + GAP), ws[0]), (items[1][0], gx, gy, ws[1]),
                            (items[2][0], gx, gy + (H + GAP), ws[2])]))
        cands.append(('H', [(items[0][0], gx - (items[0][3] + GAP), gy, ws[0]), (items[1][0], gx, gy, ws[1]),
                            (items[2][0], gx + (items[2][3] + GAP), gy, ws[2])]))
    elif n == 4:
        cands.append(('G4', [(items[0][0], gx - dx, gy - dy, ws[0]), (items[1][0], gx + dx, gy - dy, ws[1]),
                             (items[2][0], gx - dx, gy + dy, ws[2]), (items[3][0], gx + dx, gy + dy, ws[3])]))
        cands.append(('V', [(items[0][0], gx, gy - 1.5 * (H + GAP), ws[0]), (items[1][0], gx, gy - 0.5 * (H + GAP), ws[1]),
                            (items[2][0], gx, gy + 0.5 * (H + GAP), ws[2]), (items[3][0], gx, gy + 1.5 * (H + GAP), ws[3])]))
    return cands


def _pattern_prio(tag, n, items=None):
    """排布优先级终稿(2026-10-23 八轮 用户全部口径收敛):
    1线=S骑线; 2线=V上下紧叠(平行走廊站列x=钉均值, 触线成立);
    3线=一律 P3 T字(上二下一)/P3D 品字(上一下二)——平行走廊站(大学城南)也用三角
    (八轮用户: 大学城南要上12/7下4的T字, 七轮'平行走廊3线=V'是过度推广, 已废);
    4线=G4田字; H=退化兜底."""
    if n == 2:
        return {'V': 0, 'H': 1}.get(tag, 2)
    if n == 3:
        return {'P3': 0, 'P3D': 0, 'V': 1, 'H': 2}.get(tag, 3)
    return {'G4': 0, 'V': 1, 'H': 2}.get(tag, 3)


def exit_vec(segs, px, py, rmin=5.0, rmax=60.0):
    """走廊出向: 站点邻域走廊采样点的合成单位向量和(指向线路走出方向); 半径60
    (八轮: 半径30采不到38pt外的走向段——大学城南4号线南向段在38pt外, 出向被算成0致上4下12/7, 用户要上12/7下4).
    终端站=强出向(如22号线番禺广场=纯西-12); 贯通站两向抵消≈0(走tie-break).
    2026-10-23 七轮 用户: 番禺广场18/22共钉, 牌位须按走廊关联(22西出居左)."""
    vx = vy = 0.0
    for s in segs:
        dx, dy = s[2] - s[0], s[3] - s[1]
        L = (dx * dx + dy * dy) ** 0.5
        if L < 1:
            continue
        steps = max(2, int(L / 2))
        for i in range(steps + 1):
            qx = s[0] + dx * i / steps
            qy = s[1] + dy * i / steps
            d = ((qx - px) ** 2 + (qy - py) ** 2) ** 0.5
            if rmin < d < rmax:
                vx += (qx - px) / d
                vy += (qy - py) / d
    L = (vx * vx + vy * vy) ** 0.5
    return (vx / L, vy / L, L) if L > 1e-6 else (0.0, 0.0, 0.0)


def place_station(items, segs_of):
    """择优(七轮重写: 槽位与牌解耦——全牌等宽, 每模式的槽位做全排列组合搜索):
    全触线 > 规范排布优先级 > 方向匹配(钉偏移+走廊出向+线号tie-break) > 最差距离.
    共钉线(番禺广场18/22)由走廊出向区分; 出向也≈0的贯通线走线号序tie-break
    (东山口1上6下=官图用例口径)."""
    import itertools
    n = len(items)
    gx = sum(it[1] for it in items) / n
    gy = sum(it[2] for it in items) / n
    exits = {}
    for ln, px, py, w in items:
        exits[ln] = exit_vec(segs_of[ln], px, py)
    order_idx = {ln: i for i, ln in enumerate(ORDER)}
    pin_of = {it[0]: (it[1], it[2]) for it in items}
    scored = []
    for tag, placed0 in layout_candidates(items):
        slots = [(cx, cy) for _, cx, cy, _ in placed0]
        prio = _pattern_prio(tag, n, items)
        for perm in itertools.permutations(range(n)):
            placed = [(items[perm[k]][0], slots[k][0], slots[k][1], items[perm[k]][3])
                      for k in range(n)]
            worst, fails = 0.0, []
            for ln, cx, cy, w in placed:
                rect = (cx - w / 2, cy - H / 2, w, H)
                d = min(rect_seg_dist(rect, s) for s in segs_of[ln]) - CORR_HALF
                if d > 0.01:
                    fails.append('%s d=%.1f' % (ln, d))
                worst = max(worst, d)
            dirscore = 0.0
            for ln, cx, cy, w in placed:
                pl = ((cx - gx) ** 2 + (cy - gy) ** 2) ** 0.5 or 1.0
                px, py = pin_of[ln]
                ql = ((px - gx) ** 2 + (py - gy) ** 2) ** 0.5 or 1.0
                # ① 钉偏移方向匹配
                dirscore += ((cx - gx) / pl) * ((px - gx) / ql) + ((cy - gy) / pl) * ((py - gy) / ql)
                # ② 走廊出向匹配(强出向线: 终端/明显单侧走出)
                ex, ey, el = exits[ln]
                if el >= 2.0:
                    dirscore += 0.8 * (((cx - gx) / pl) * ex + ((cy - gy) / pl) * ey)
                # ③ 线号序tie-break(小号先得上/左槽)
                dirscore += 0.01 * (len(ORDER) - order_idx.get(ln, 99))
            scored.append((len(fails) == 0, prio, dirscore, worst, tag, placed, fails))
    scored.sort(key=lambda x: (not x[0], x[1], -x[2], x[3]))
    ok, prio, dirscore, worst, tag, placed, fails = scored[0]
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
    layout_review = []
    for nm, lst in pins.items():
        items = []
        for ln, cx, cy in lst:
            key = (nm, ln)
            if key not in codes:
                report['no_code'].append('全网/%s@%s' % (nm, ln))
                continue
            disp, serial = codes[key]
            items.append((ln, cx, cy, chip_w(disp, serial, False)))
        if not items:
            continue
        tag, placed, fails, worst = place_station(items, segs_of)
        for ln, cx, cy, w in placed:
            chips.append((nm, ln, cx, cy, w))
        if fails:
            report['touch_fail'].append('%s[%s]: %s' % (nm, tag, ','.join(fails)))
        report['layout_tags'][tag] = report['layout_tags'].get(tag, 0) + 1
        # 集中review(六/七轮): 2线须V; 3线须三角(共y横排钉的平行走廊组=V规范); 4线须G4
        n = len(items)
        if n >= 2:
            layout_review.append('%d线 %s %s' % (n, tag, nm))
            if n == 2:
                ok_pat = tag == 'V'
            elif n == 3:
                ok_pat = tag in ('P3', 'P3D')
            else:
                ok_pat = tag == 'G4'
            if not ok_pat:
                report['layout_violations'].append('%d线站%s用了%s(退化)' % (n, nm, tag))

    # 牌-他线无歧义(十三轮 用户: 晓港不是10号线的却叠在10号线上): 单牌站若覆盖他线走廊,
    # 沿本线走廊切向/垂直试移避开(保本线触线+不撞他牌)
    def rect_of(c):
        return (c[2] - c[4] / 2, c[3] - H / 2, c[4], H)

    station_chip_idx = {}
    for idx4, cc in enumerate(chips):
        station_chip_idx.setdefault(cc[0], []).append(idx4)
    amb_fixed = []
    for nm2, idxs in station_chip_idx.items():
        if len(idxs) != 1:
            continue
        k = idxs[0]
        nm, ln, cx, cy, w = chips[k]
        other_segs = [s2 for ln2 in ORDER if ln2 != ln for s2 in segs_of[ln2]
                      if rect_seg_dist((cx - 20, cy - 20, 40, 40), s2) < 40]
        if not other_segs or min(rect_seg_dist((cx - w / 2, cy - H / 2, w, H), s2) for s2 in other_segs) >= CORR_HALF - 0.2:
            continue
        tx, ty = corridor_tangent(segs_of[ln], cx, cy)
        dirs = [(tx, ty), (-tx, -ty), (-ty, tx), (ty, -tx)]
        done2 = False
        for ux, uy in dirs:
            for step in range(1, 25):
                d2 = step * 0.5
                nx, ny = cx + ux * d2, cy + uy * d2
                rect = (nx - w / 2, ny - H / 2, w, H)
                own_touch = min(rect_seg_dist(rect, s2) for s2 in segs_of[ln]) <= CORR_HALF + 0.01
                other_ok = min(rect_seg_dist(rect, s2) for s2 in other_segs) >= CORR_HALF - 0.2
                clash = any(o is not chips[k] and o[0] != nm and rects_overlap(rect, rect_of(o)) for o in chips)
                if own_touch and other_ok and not clash:
                    chips[k] = (nm, ln, nx, ny, w)
                    amb_fixed.append('%s:%.1fpt' % (nm, d2))
                    done2 = True
                    break
            if done2:
                break
        if not done2:
            report.setdefault('chip_amb_unresolved', []).append(nm)
    report['chip_amb_fixed'] = amb_fixed

    # 跨站牌重叠 -> 沿本线走廊推让; 多牌站整组平移保形状(十三轮: 单枚平移曾破坏行对齐=番禺广场18靠上)
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
                group = station_chip_idx.get(nm, [k])
                # 组内代表线取多数(整组同移须各组员保触线): 单牌直接用本线
                ux, uy = corridor_tangent(segs_of[ln], cx, cy)
                for step in range(1, 9):
                    for sgn in (1, -1):
                        ddx, ddy = sgn * step * 2.0 * ux, sgn * step * 2.0 * uy
                        ok_all = True
                        trial = []
                        for k2 in group:
                            nm3, ln3, cx3, cy3, w3 = chips[k2]
                            nx, ny = cx3 + ddx, cy3 + ddy
                            rect = (nx - w3 / 2, ny - H / 2, w3, H)
                            clash = any(o[0] != nm3 and rects_overlap(rect, rect_of(o)) for o in chips)
                            touch = min(rect_seg_dist(rect, s2) for s2 in segs_of[ln3]) <= CORR_HALF + 0.01
                            if clash or not touch:
                                ok_all = False
                                break
                            trial.append((k2, (nm3, ln3, nx, ny, w3)))
                        if ok_all:
                            for k2, val in trial:
                                chips[k2] = val
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
    # 多线组外描边圈 = 沿胶囊边缘的包络(底图换乘胶囊同款双描边技法):
    # 每个胶囊矩形先描粗黑边(2*(pad+RIM))再描细白边(2*pad), 相邻胶囊描边融合成连续外轮廓
    def ring_rect(nm, pad):
        rects = by_st[nm]
        e = pad + RIM   # 轮廓外伸(黑边外缘)
        return (min(r[0] for r in rects) - e, min(r[1] for r in rects) - e,
                max(r[0] + r[2] for r in rects) - min(r[0] for r in rects) + 2 * e,
                max(r[1] + r[3] for r in rects) - min(r[1] for r in rects) + 2 * e)

    ring_pads = {}      # nm -> pad
    obstacles = {}      # nm -> [rect]  多线站=轮廓外缘矩形, 单线站=牌矩形
    for nm, rects in by_st.items():
        if len(rects) >= 2:
            ring_pads[nm] = RING_PAD
            obstacles[nm] = [ring_rect(nm, RING_PAD)]
        else:
            obstacles[nm] = rects

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
                    by_st[nm2] = [rect]
                    obstacles[nm2] = [rect]
                    return True
        return False

    def clear_of_others(nm, rect):
        return all(_gap(rect, r) >= 0.3 for nm2 in obstacles if nm2 != nm for r in obstacles[nm2])

    resolved, leftover = [], []
    for nm in list(ring_pads):
        rect = obstacles[nm][0]
        conflicts = [nm2 for nm2 in obstacles if nm2 != nm and any(_gap(rect, r) < 0.3 for r in obstacles[nm2])]
        if not conflicts:
            continue
        fixed = False
        for nm2 in conflicts:
            if not shift_station_chips(nm2):
                continue
            if clear_of_others(nm, rect):
                fixed = True
                resolved.append('%s:推让%s' % (nm, nm2))
                break
        if not fixed:
            for pad in (0.9, 0.6, 0.4):
                r2 = ring_rect(nm, pad)
                if clear_of_others(nm, r2):
                    ring_pads[nm] = pad
                    obstacles[nm] = [r2]
                    resolved.append('%s:收缩%.1f' % (nm, pad))
                    fixed = True
                    break
            if not fixed:
                ring_pads[nm] = 0.4
                obstacles[nm] = [ring_rect(nm, 0.4)]
                leftover.append(nm)
    report['ring_fix'] = resolved
    report['ring_overlaps'] = leftover

    # 徽标pass(十三轮): 清距=8pt(底图规范: 徽标视觉净距>=8px, verify-badges-pixel.py口径——
    # 首版用0.5pt被用户打脸"12号线徽标直接贴一块, 距离定过没遵守"):
    # a) 与牌/圈净距<8 -> 沿远离违规者方向推到>=8; b) 离本线终点牌净距>25 -> 拉近但不破8
    badge_moves = []
    badge_rects = []   # (线名, rect, transform串)

    def _badge_parse(svg_text):
        out = []
        for mm in re.finditer(r'<g data-badge="header" transform="translate\(([-\d.]+) ([-\d.]+)\) scale\(([\d.]+)\)"([^>]*)>(.*?)</g>', svg_text, re.S):
            tx, ty, sc = float(mm.group(1)), float(mm.group(2)), float(mm.group(3))
            _ts5 = re.findall(r'>([^<>]+)</text>', mm.group(5))
            num_val = _ts5[0].strip() if _ts5 else '?'
            # 徽标文字=卡上线路名: 数字/APM/'广佛线'(15号字, 不以"号线"结尾, 25号字正则抓不到)
            num = num_val if (num_val.isdigit() or num_val in ('APM', '广佛线')) else '?'
            key = num
            out.append({'tx': tx, 'ty': ty, 'ox': tx, 'oy': ty, 'sc': sc, 'key': key, 'inner': mm.group(5), 'span': (mm.start(), mm.end())})
        return out

    _svg_src = open(os.path.join(LINES_DIR, 'network-全网.svg'), encoding='utf-8').read()
    badges = _badge_parse(_svg_src)
    KEY2LN = {'GF': '广佛线', 'APM': 'APM线'}
    # 各线徽标实际尺寸(卡header rect, 广佛73/APM 102.2 与其余80不同, 碰撞盒必须用实尺寸;
    # 2026-10-24 起全网徽标高=2×序号胶囊18pt, scale由底图transform携带)
    _bsz = {}
    for _ln2 in ORDER:
        _src2 = open(os.path.join(LINES_DIR, 'line-%s.svg' % _ln2), encoding='utf-8').read()
        _m2 = re.search(r'<g data-badge="header"[^>]*>(.*?)</g>', _src2, re.S)
        _r2 = re.search(r'<rect x="([\d.-]+)" y="([\d.-]+)" width="([\d.]+)" height="([\d.]+)"', _m2.group(1))
        _bsz[_ln2] = (float(_r2.group(3)), float(_r2.group(4)))

    def _ln_of_key(key):
        if key in KEY2LN:
            return KEY2LN[key]
        cand = key + '号线'
        return cand if cand in ORDER else None

    chip_rects_all = [(cc[2] - cc[4] / 2, cc[3] - H / 2, cc[4], H) for cc in chips]
    ring_rects_all = [r for rs in obstacles.values() for r in rs]
    BADGE_GAP = 8.0   # 底图规范: 徽标视觉净距>=8px
    # 徽标规则终稿(十七轮 用户: 每个决策都是遵守规则; 无任何点名位):
    # R0 底图位=默认(用户验收过, 终点120px内不迁)
    # R1 撞牌/圈(净距<8) -> 终点公式gap梯度(7/12/20/32/50/72/100)沿走廊出向外推最小档
    # R2 混淆规避: 到他线走廊描边距离 < 到本线走廊描边距离(量边不量心)
    #    -> 贴本体网格重放(距本线走廊6.5~60px, 离他线描边>=30px, 不撞牌圈徽标,
    #       离本线终点最近优先——10号线原位离广佛线更近=R2触发, 东侧净空位=规则输出)
    # 环线(11号线)碰撞 -> 规范贴本体网格全域搜
    EDGE = CORR_HALF   # 走廊描边半宽(净距量边不量心)

    def _badge_grid(ln, ocx, ocy, tpx, tpy, bw2, bh2):
        """贴本体网格重放(歧义判定触发): 硬底线=到他线走廊边不近于到本线边(混淆);
        软偏好=离他线边>=20px(能20就20, 不行就挤——用户口径); 优选离本线终点近."""
        own_segs = segs_of[ln]
        other_segs = [s2 for ln2 in ORDER if ln2 != ln for s2 in segs_of[ln2]]
        best = None
        for s in own_segs:
            L = ((s[2] - s[0]) ** 2 + (s[3] - s[1]) ** 2) ** 0.5
            if L < 4:
                continue
            n2 = max(2, int(L / 6))
            dxu, dyu = (s[2] - s[0]) / L, (s[3] - s[1]) / L
            for i in range(n2 + 1):
                qx = s[0] + (s[2] - s[0]) * i / n2
                qy = s[1] + (s[3] - s[1]) * i / n2
                # 采样限定: 终点邻段(终点±80pt)或原位±70pt——重放是局部优选, 不跨图迁移
                if ((qx - tpx) ** 2 + (qy - tpy) ** 2) ** 0.5 > 80 and                    ((qx - ocx) ** 2 + (qy - ocy) ** 2) ** 0.5 > 70:
                    continue
                for sgn in (1, -1):
                    nx_, ny_ = -dyu * sgn, dxu * sgn
                    for off in (14, 20, 28, 40, 56):
                        cx2, cy2 = qx + nx_ * off, qy + ny_ * off
                        r2 = (cx2 - bw2 / 2, cy2 - bh2 / 2, bw2, bh2)
                        if any(_gap(r2, r) < BADGE_GAP for r in chip_rects_all + ring_rects_all):
                            continue
                        if any(_gap(r2, r2b) < 3 for _k2, r2b in badge_rects):
                            continue
                        # 走廊硬约束(十八轮末 用户: 1/2/10/11/22跟路线叠一块——所有移动pass
                        # 都没查走廊, "可盖走廊"只适用于终点延长线自然位, 挪出的新位置必须
                        # 不压任何走廊描边)
                        if min((rect_seg_dist(r2, s2) for s2 in own_segs + other_segs), default=9e9) < 3:
                            continue
                        own_ed = min((rect_seg_dist(r2, s2) for s2 in own_segs), default=9e9) - EDGE
                        oth_ed = min((rect_seg_dist(r2, s2) for s2 in other_segs), default=9e9) - EDGE
                        # 硬底线: 不压他线描边(>=1) + 本线侧强偏好(own_ed<=oth_ed+25, 容差容纳
                        # '广佛线上方'这类本线标注区他线在下方穿过的合法位)
                        if oth_ed < 1 or own_ed > oth_ed + 25:
                            continue
                        margin_pen = 3.0 * max(0.0, 20.0 - min(oth_ed, 20.0))
                        dt = ((cx2 - tpx) ** 2 + (cy2 - tpy) ** 2) ** 0.5
                        dorg = ((cx2 - ocx) ** 2 + (cy2 - ocy) ** 2) ** 0.5
                        score = dt + margin_pen   # 不再奖励'离原位近'——歧义重放本就要离开歧义侧
                        if best is None or score < best[0]:
                            best = (score, r2)
        return best[1] if best else None

    # 十八轮终版: 底图位 → 延长线正交居中 → 真牌圈碰撞最小挤让。就这么简单。
    # 不做公式重放/gap梯度/网格搜索——底图位已按规范放好, 唯一要修的是编号牌引入的新碰撞。
    BADGE_MIN = 1.0
    for bd in badges:
        ln = _ln_of_key(bd['key'])
        if ln:
            bw, bh = _bsz[ln][0] * bd['sc'], _bsz[ln][1] * bd['sc']
        else:                       # 未知key兜底(历史缺省80x43)
            bw, bh = 80 * bd['sc'], 43 * bd['sc']
        rect = (bd['tx'], bd['ty'], bw, bh)
        if not ln:
            badge_rects.append((bd['key'], rect))
            continue
        # ①走廊轴居中已废(把底图位从走廊旁拽到走廊正上方=压线根因);
        # 底图位本身就在延长线旁的正确位置
        # ②真牌圈碰撞(gap<1pt)最小挤让
        viol9 = any(_gap(rect, r) < BADGE_MIN for r in chip_rects_all + ring_rects_all)
        if viol9:
            import math as _m9
            best9 = None
            for k9 in range(16):
                ra9 = _m9.radians(k9 * 22.5)
                ux9, uy9 = _m9.cos(ra9), _m9.sin(ra9)
                for st9 in range(1, 41):
                    dd9 = st9 * 0.5
                    r9 = (rect[0] + ux9 * dd9, rect[1] + uy9 * dd9, bw, bh)
                    if (all(_gap(r9, r) >= BADGE_MIN for r in chip_rects_all + ring_rects_all) and
                            all(_gap(r9, r9b) >= BADGE_MIN for _kb, r9b in badge_rects)):
                        if best9 is None or dd9 < best9[0]:
                            best9 = (dd9, r9)
                        break
            if best9:
                rect = best9[1]
                bd['tx'], bd['ty'] = rect[0], rect[1]
                badge_moves.append('%s:挤让%.1fpt' % (bd['key'], best9[0]))
            else:
                badge_moves.append('%s:无解保持' % bd['key'])
        badge_rects.append((bd['key'], rect))
        continue
        ocx, ocy = bd['ox'] + bw / 2, bd['oy'] + bh / 2
        own_segs = segs_of[ln]
        other_d = min((rect_seg_dist(rect, s2) for ln2 in ORDER if ln2 != ln
                       for s2 in segs_of[ln2] if rect_seg_dist(rect, s2) < 150), default=9e9)
        own_d = min(rect_seg_dist(rect, s2) for s2 in own_segs)
        collide = any(_gap(rect, r) < BADGE_GAP for r in chip_rects_all + ring_rects_all)
        ambiguous = (other_d - EDGE) < (own_d - EDGE) and own_d > EDGE + 1  # 他线描边更近=混淆
        if not collide and not ambiguous:
            badge_rects.append((bd['key'], rect))
            continue
        # 锚定终点=离原位最近的本线钉
        tpx, tpy = min((((p[1] - ocx) ** 2 + (p[2] - ocy) ** 2, p[1], p[2])
                        for nm3, lst in pins.items() for p in lst if p[0] == ln),
                       default=(0, ocx, ocy))[1:3]
        # R1: 终点公式 gap 梯度外推(撞牌时优先, 环线跳过公式)
        if collide and ln != '11号线':
            tx, ty = corridor_tangent(own_segs, tpx, tpy)
            cxs = sum(p[1] for nm3, lst in pins.items() for p in lst if p[0] == ln) / \
                max(1, sum(1 for nm3, lst in pins.items() for p in lst if p[0] == ln))
            cys = sum(p[2] for nm3, lst in pins.items() for p in lst if p[0] == ln) / \
                max(1, sum(1 for nm3, lst in pins.items() for p in lst if p[0] == ln))
            if (tpx - cxs) * tx + (tpy - cys) * ty < 0:
                tx, ty = -tx, -ty   # 出向=背离线体质心
            r0 = 7.0 if len(by_st.get(next((nm3 for nm3, lst in pins.items()
                    for p in lst if p[0] == ln and p[1] == tpx and p[2] == tpy), ''), [])) >= 2 else 4.5
            half = (bw * abs(tx) + bh * abs(ty)) / 2
            placed1 = False
            for rung in (7, 12, 20, 32, 50, 72, 100):
                d2 = r0 + rung + half
                ccx, ccy = tpx + tx * d2, tpy + ty * d2
                r2 = (ccx - bw / 2, ccy - bh / 2, bw, bh)
                if (all(_gap(r2, r) >= BADGE_GAP for r in chip_rects_all + ring_rects_all) and
                        all(_gap(r2, r2b) >= 3 for _k2, r2b in badge_rects)):
                    rect = r2
                    bd['tx'], bd['ty'] = r2[0], r2[1]
                    badge_moves.append('%s:R1外推gap%d' % (bd['key'], rung))
                    placed1 = True
                    break
            if placed1:
                badge_rects.append((bd['key'], rect))
                continue
        # R2/环线: 贴本体网格
        r3 = _badge_grid(ln, ocx, ocy, tpx, tpy, bw, bh)
        if r3 is not None:
            rect = r3
            bd['tx'], bd['ty'] = r3[0], r3[1]
            badge_moves.append('%s:重放(%s)' % (bd['key'], '撞牌' if collide else '混淆'))
        else:
            badge_moves.append('%s:无合法位保持原位' % bd['key'])
        badge_rects.append((bd['key'], rect))
    report['badge_moves'] = badge_moves

    # 组装 SVG
    path = os.path.join(LINES_DIR, 'network-全网.svg')
    t = open(path, encoding='utf-8').read()
    # (徽标transform只在居中pass后统一应用一次——此处早应用会让居中pass的二次替换
    #  按旧坐标匹配而静默失败, 居中从未真正落盘=2/5/13/14/18实测偏差10~23pt的根因)
    for gid in ('站圆', '换乘标记'):
        m = re.search(r'<g id="%s">.*?</g>' % gid, t, re.S)
        t = t[:m.start()] + t[m.end():]
    # 站名避让(牌/圈全部落定后): 钉位=该站各线钉质心
    pin_center = {}
    for nm, lst in pins.items():
        pin_center[nm] = (sum(p[1] for p in lst) / len(lst), sum(p[2] for p in lst) / len(lst))
    all_segs = [s for ln in ORDER for s in segs_of[ln]]
    # 对齐组心: 全部有牌站(多牌=新组形; 单牌=斜走廊标签45°摆位两轴都偏, 十轮用户三报)
    align_centers = {nm: (rs[0][0] + rs[0][2] / 2, rs[0][1] + rs[0][3] / 2)
                     for nm, rs in obstacles.items()}
    # (十七轮 用户: 像 APM 一样是规范——文字实在没地方显示就缩小+描边, 所有站点同一套规则,
    #  终点在他线侧有空间自然回常规字号; 不允许任何规则外的特殊定制——APM专用分支已删,
    #  降档逻辑统一在 nudge_labels 内: 7.5px常规先试, 严格约束无可行位才降6px+白光环)
    new_labels = nudge_labels(t, pin_center, obstacles, all_segs, report, '全网', align_centers)
    if new_labels is not None:
        t = re.sub(r'(<g id="站名标注"[^>]*>).*?(</g>)',
                   lambda mm: mm.group(1) + new_labels + mm.group(2), t, count=1, flags=re.S)
    # 徽标重写 transform(用户: 终点徽标的延长线规范去哪了——全量居中pass把19枚徽标全部
    # 改成"标签上下居中", 覆盖了底图按终点公式/斜线居中/环线网格摆好的已验收位, 已废;
    # 徽标位置=底图位+真碰撞挤让+用户确认的2/10号线歧义重放, 只做写入):
    # ⚠️不能按原始span偏移切片——t已被改写(站圆删除/站名重排), span错位=替换落空。
    # 按data-badge组全文正则重写(key配对, 12号线双段按出现序依次配对)。
    keyed = {}
    for bd in badges:
        keyed.setdefault(bd['key'], []).append(bd)
    seen = {}

    def _sub_badge(mm):
        inner = mm.group(5)
        km = re.search(r'font-size="25"[^>]*>([^<]+)<', inner)
        key = km.group(1) if km else None
        if key in keyed:
            idx = seen.get(key, 0)
            seen[key] = idx + 1
            bd = keyed[key][idx] if idx < len(keyed[key]) else None
            if bd and (abs(bd['tx'] - bd['ox']) > 0.01 or abs(bd['ty'] - bd['oy']) > 0.01):
                return (mm.group(1) + '"translate(%.2f %.2f)' % (bd['tx'], bd['ty']) +
                        mm.group(4) + '>' + inner + '</g>')
        return mm.group(0)

    # 延长线正交居中pass已整体废除(2026-10-24 用户: 已验收的如果要挪说明规则有问题):
    # 本pass按"徽标中心x=终点标签x"重居中, 但已验收位(如2号线广州南站 中心x=1397)与
    # 终版标签x(1366.6)根本不对齐——该规则前提与验收态矛盾, 且标签随锚表变化会反复
    # 搬动徽标(曾把锚定保留的2/5/11/广佛/APM重拽38/27/70pt)。45°斜线徽标的文字居中
    # 由底图放置时的45°分支一次性完成, 此处不再二次重居中。
    t = re.sub(r'(<g data-badge="header" transform=)"translate\(([-\d.]+) ([-\d.]+)\)([^>]*)>(.*?)</g>',
               _sub_badge, t, flags=re.S)
    # 徽标终检挪移(2026-10-24 双端小徽标41枚, 站名定稿后逐枚复检):
    # 底图徽标碰撞检查用的是底图算法标签, codes终版标签(nudge_labels+锚表)位置不同,
    # 直接回写会产生徽标压标签/APM压体育西路等新碰撞。阈值=与已验收位置自洽的硬底线
    # (验收态曾0/20像素穿透的事实口径, 不设白名单——规则必须让已验收位自然合法):
    #   他线走廊中心线>=6.5(描边半宽3.5+像素门禁3px外扫)  本线走廊不限(可盖延长线, 判例)
    #   终版标签仅真叠压(近似盒gap<0)  牌/圈>=3.0(像素门禁口径)  他徽标>=6(旧rect_why口径)
    # 违规者16向螺旋0.5pt步进找最小位移合法位(<=40pt), 找不到保持原位并上报。
    import math as _m6
    # 他线走廊净距阈值(与已验收位置自洽的迭代结果): 盒边到走廊中心线>=6.5
    # = 走廊描边半宽3.5 + 像素门禁四边外扩3px扫描口径。旧验收位全部满足(曾0/20穿透),
    # 2026-10-24曾误收至9.0比验收态更严 -> 把合法老位判违规大挪移(用户打回), 迭代回6.5。
    CORR_CLEAR = 6.5

    def _final_label_boxes2():
        boxes = []
        lm5 = re.search(r'<g id="站名标注"[^>]*>(.*?)</g>', t, re.S)
        if not lm5:
            return boxes
        for mm in re.finditer(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*font-size="([\d.]+)"[^>]*>([^<]+)</text>', lm5.group(1)):
            cx_, cy_bl, fs_, nm_ = float(mm.group(1)), float(mm.group(2)), float(mm.group(3)), mm.group(4)
            w_ = sum(fs_ if ord(ch) > 0x2E80 else 0.56 * fs_ for ch in nm_)
            hh_ = fs_ + 1.0
            cy_ = cy_bl - 0.8 * fs_ + hh_ / 2
            boxes.append((cx_ - w_ / 2, cy_ - hh_ / 2, w_, hh_))
        return boxes

    def _rect_gap(r1, r2):
        dx = max(r2[0] - (r1[0] + r1[2]), r1[0] - (r2[0] + r2[2]), 0.0)
        dy = max(r2[1] - (r1[1] + r1[3]), r1[1] - (r2[1] + r2[3]), 0.0)
        return (dx * dx + dy * dy) ** 0.5

    lab_boxes = _final_label_boxes2()
    fin_bad_boxes = []
    for _i6, bd in enumerate(badges):
        ln = _ln_of_key(bd['key'])
        if ln:
            bw6, bh6 = _bsz[ln][0] * bd['sc'], _bsz[ln][1] * bd['sc']
        else:
            bw6, bh6 = 80 * bd['sc'], 43 * bd['sc']
        rect6 = (bd['tx'], bd['ty'], bw6, bh6)
        if not ln:
            fin_bad_boxes.append(rect6)
            continue
        viol6 = None
        for ln2 in ORDER:
            if ln2 == ln:
                continue
            if any(rect_seg_dist(rect6, s2) < CORR_CLEAR for s2 in segs_of[ln2]):
                viol6 = '他线走廊%s' % ln2
                break
        if not viol6:
            for r6 in lab_boxes:
                if _rect_gap(rect6, r6) < 0.0:
                    viol6 = '压标签'
                    break
        if not viol6:
            for r6 in chip_rects_all + ring_rects_all:
                if _rect_gap(rect6, r6) < 3.0:
                    viol6 = '近牌圈'
                    break
        if not viol6:
            for _j6, (_k6, r6) in enumerate(badge_rects):
                if _j6 != _i6 and _rect_gap(rect6, r6) < 6.0:
                    viol6 = '近他徽标'
                    break
        if not viol6:
            fin_bad_boxes.append(rect6)
            continue
        fixed6, dd6 = None, 0.0
        own_pins6 = [p for nm3, lst in pins.items() for p in lst if p[0] == ln]

        def _ok6(r6, own_lim, pin_lim):
            if any(rect_seg_dist(r6, s2) < CORR_CLEAR for ln2 in ORDER if ln2 != ln for s2 in segs_of[ln2]):
                return False
            if any(_rect_gap(r6, r7) < 0.0 for r7 in lab_boxes):
                return False
            if any(_rect_gap(r6, r7) < 3.0 for r7 in chip_rects_all + ring_rects_all):
                return False
            if any(_rect_gap(r6, r7) < 6.0 for _j7, (_k7, r7) in enumerate(badge_rects) if _j7 != _i6):
                return False
            if own_lim is not None:
                if min((rect_seg_dist(r6, s2) for s2 in segs_of[ln]), default=9e9) > own_lim:
                    return False
            c6 = (r6[0] + bw6 / 2, r6[1] + bh6 / 2)
            if own_pins6:
                dp6 = min(dist_pts(c6, (p[1], p[2])) for p in own_pins6)
                if pin_lim is not None and dp6 > pin_lim:
                    return False
                if dp6 > 60.0 and min((rect_seg_dist(r6, s2) for s2 in segs_of[ln]), default=9e9) > 90.0:
                    return False   # 离钉远时必须贴本线走廊(不得飘到别线旁)
            return True

        for st6 in range(1, 201):     # pass1: 原位螺旋, 距本线走廊<=90
            dd6 = st6 * 0.5
            for k6 in range(16):
                ra6 = _m6.radians(k6 * 22.5)
                ux6, uy6 = _m6.cos(ra6), _m6.sin(ra6)
                r6 = (rect6[0] + ux6 * dd6, rect6[1] + uy6 * dd6, bw6, bh6)
                if _ok6(r6, 90.0, None):
                    fixed6 = r6
                    break
            if fixed6:
                break
        if not fixed6 and own_pins6:  # pass2: 终点钉环形搜索(脱离卡死区): 全候选评分取最优
            # 评分=本线走廊过远罚 + 他徽标扎堆罚(混淆规避R2) + 离钉过远罚; 合法性同pass1口径
            tp6 = min(own_pins6, key=lambda p: dist_pts((rect6[0] + bw6 / 2, rect6[1] + bh6 / 2), (p[1], p[2])))
            best7 = None
            for st7 in range(4, 25):
                rr7 = st7 * 6.25
                for k7 in range(16):
                    ra7 = _m6.radians(k7 * 22.5)
                    cx7 = tp6[1] + _m6.cos(ra7) * rr7
                    cy7 = tp6[2] + _m6.sin(ra7) * rr7
                    r7 = (cx7 - bw6 / 2, cy7 - bh6 / 2, bw6, bh6)
                    if not _ok6(r7, None, 150.0):
                        continue
                    own_d7 = min((rect_seg_dist(r7, s2) for s2 in segs_of[ln]), default=9e9)
                    gap_badge7 = min((_rect_gap(r7, r8) for _j8, (_k8, r8) in enumerate(badge_rects) if _j8 != _i6),
                                     default=9e9)
                    dp7 = dist_pts((cx7, cy7), (tp6[1], tp6[2]))
                    score7 = max(0.0, own_d7 - 45.0) + 2.0 * max(0.0, 24.0 - min(gap_badge7, 24.0)) + 0.2 * dp7
                    if best7 is None or score7 < best7[0]:
                        best7 = (score7, r7)
            if best7 is not None:
                fixed6 = best7[1]
                dd6 = dist_pts((rect6[0], rect6[1]), fixed6[:2])
        if fixed6:
            bd['tx'], bd['ty'] = fixed6[0], fixed6[1]
            badge_moves.append('%s(%g,%g):终检挪移%.1fpt(%s)' % (bd['key'], rect6[0], rect6[1], dd6, viol6))
        else:
            badge_moves.append('%s(%g,%g):终检无解保持(%s)' % (bd['key'], rect6[0], rect6[1], viol6))
        fin_bad_boxes.append(fixed6 if fixed6 else rect6)
    report['badge_final_moves'] = [m for m in badge_moves if '终检' in m]
    # 终检后的transform写回(此时t中的徽标transform还是底图位; _sub_badge只写了挪移过的子集)
    _fb = [0]
    def _rw_final(mm):
        i = _fb[0]
        _fb[0] += 1
        if i < len(fin_bad_boxes):
            return mm.group(1) + '"translate(%.2f %.2f)' % (fin_bad_boxes[i][0], fin_bad_boxes[i][1]) + mm.group(2) + '"'
        return mm.group(0)
    t = re.sub(r'(<g data-badge="header" transform=)"translate\([-\d.]+ [-\d.]+\)([^>]*)"', _rw_final, t)
    # 终稿锚定层(2026-10-23 用户定稿同步): 逐枚审定的徽标/站名/牌偏移持久化到
    # data/codes-final-pins.json —— 重跑=算法产出+锚表覆盖, 输出与已验收SVG逐字节一致。
    # 徽标按文档序配对(与提取序同源); 牌偏移在全部排布pass后应用(不回灌算法);
    # 站名按站名串替换。锚表=终稿持久化(同 _network-audit 性质), 非放置算法。
    fin_path = os.path.join(ROOT, 'data', 'codes-final-pins.json')
    if os.path.exists(fin_path):
        fin = json.load(open(fin_path, encoding='utf-8'))
        for nm, (fx, fy) in fin.get('chip_shift', {}).items():
            chips = [(a, b, cx + fx, cy + fy, w) if a == nm else (a, b, cx, cy, w)
                     for a, b, cx, cy, w in chips]
        lm4 = re.search(r'<g id="站名标注"[^>]*>(.*?)</g>', t, re.S)
        if lm4 and fin.get('labels_inner'):
            # 整组钉定(切换两模式一套文字布局: 底图已回写终版站名组, 此处保证重跑逐字节一致)
            t = t[:lm4.start(1)] + fin['labels_inner'] + t[lm4.end(1):]
        trs = fin.get('badges', [])
        _bi = [0]
        def _pin_badge(mm):
            i = _bi[0]
            _bi[0] += 1
            if i < len(trs):
                return mm.group(1) + '"' + trs[i] + mm.group(4) + '>' + mm.group(5) + '</g>'
            return mm.group(0)
        t = re.sub(r'(<g data-badge="header" transform=)"translate\(([-\d.]+) ([-\d.]+)\)([^>]*)>(.*?)</g>',
                   _pin_badge, t, flags=re.S)
    # 外圈发射: 黑pass(粗) -> 白pass(细, 掏出0.7黑边+白衬) -> 牌(最上); 描边沿胶囊圆角边缘融合
    black_parts, white_parts = [], []
    for nm, pad in ring_pads.items():
        for x, y, w, h in by_st[nm]:
            black_parts.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" rx="{H / 2:.2f}" '
                f'data-ring="{nm}" fill="none" stroke="{INK}" stroke-width="{2 * (pad + RIM):.2f}"/>')
            white_parts.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" rx="{H / 2:.2f}" '
                f'fill="none" stroke="#FFFFFF" stroke-width="{2 * pad:.2f}"/>')
    rings_svg = ''.join(black_parts) + ''.join(white_parts)
    chips_svg = ''.join(
        chip_svg(cx, cy, w, H, color_of[ln], codes[(nm, ln)][0], codes[(nm, ln)][1],
                 font_of(codes[(nm, ln)][0], False), False)
        for nm, ln, cx, cy, w in chips)
    mn = re.search(r'<g id="站名标注"[^>]*>.*?</g>', t, re.S)
    t = t[:mn.end()] + '<g id="编号牌" font-family="\'Microsoft YaHei\', \'PingFang SC\', sans-serif">' + rings_svg + chips_svg + '</g>' + t[mn.end():]
    open(os.path.join(LINES_DIR, 'network-全网.codes.svg'), 'w', encoding='utf-8').write(
        expand_viewbox(t, [r for rs in obstacles.values() for r in rs]
                       + [(cx - w / 2, cy - H / 2, w, H) for nm, ln, cx, cy, w in chips]))

    by_station = {}
    for nm, ln, cx, cy, w in chips:
        by_station.setdefault(nm, []).append(ln)
    report['net_chips'] = len(chips)
    report['net_multi_stations'] = sum(1 for v in by_station.values() if len(v) > 1)
    return chips


def cross_check_master(report):
    """数据门禁(2026-10-23 固化): CSV ↔ 总表 data/station-codes-master.json 全量核对.
    总表=用户整理的权威源(320站/402码, 与广州地铁车站编号总表.pdf同源);
    口径: 站名 norm_name 归一(東->东+去站尾), 广佛线/GF 与 APM 线名映射一致.
    - D1 CSV 每行在总表中有同编号记录(防编造);
    - D2 总表每条(在图上线集合内)在 CSV 中有同编号记录(防漏采);
    违例写入 report['csv_vs_master']."""
    master_path = os.path.join(ROOT, 'data', 'station-codes-master.json')
    if not os.path.exists(master_path):
        report['csv_vs_master'] = ['master json 缺失']
        return
    m = json.load(open(master_path, encoding='utf-8'))
    LN = {'广佛': '广佛线', 'GF': '广佛线', 'APM': 'APM线', 'F2': None}
    master = {}
    for s in m['stations']:
        nm = norm_name(s['name'])
        for c in s['codes']:
            ln = LN.get(c['line'], None if c['line'] in ('F2',) else c['line'] + '号线')
            if ln is None:
                continue   # 佛山2号线(F2)图上无走廊, 不入核对域
            master[(nm, ln)] = c['serial']
    rows = list(csv.DictReader(open(CSV_PATH, encoding='utf-8-sig')))
    csvset = {}
    for r in rows:
        card, _ = csv_line_to_card(r['线路'])
        if card is None:
            continue   # 佛山2号线等图外线不入核对域
        csvset[(norm_name(r['站名']), card)] = r['编号']
    bad = []
    for k, v in csvset.items():
        if k not in master:
            bad.append('D1 CSV多出: %s@%s=%s' % (k[0], k[1], v))
        elif master[k] != v:
            bad.append('D1 编号不同: %s@%s CSV=%s 总表=%s' % (k[0], k[1], v, master[k]))
    for k, v in master.items():
        if k not in csvset:
            bad.append('D2 总表有CSV缺: %s@%s=%s' % (k[0], k[1], v))
    report['csv_vs_master'] = bad


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    codes = load_codes()
    report = {'no_code': [], 'line_chips': {}, 'touch_fail': [], 'chip_overlaps': [], 'layout_tags': {},
              'layout_violations': []}
    cross_check_master(report)   # 数据门禁先行: CSV↔总表核对不过=数据源有问题
    for line in ORDER:
        gen_line_card(line, codes, report)
    gen_network(codes, report)
    open(REPORT, 'w', encoding='utf-8').write(json.dumps(report, ensure_ascii=False, indent=1))
    print('单线牌数:', report['line_chips'])
    print('全网牌数:', report['net_chips'], ' 多牌站:', report['net_multi_stations'], ' 模式:', report['layout_tags'])
    print('无码站(留圆):', report['no_code'])
    print('触线FAIL:', report['touch_fail'])
    print('牌重叠:', report['chip_overlaps'])
    print('排布review:', report['layout_tags'], '违规:', report['layout_violations'] if report['layout_violations'] else '无')


if __name__ == '__main__':
    main()
