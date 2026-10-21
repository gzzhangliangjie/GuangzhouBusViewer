# -*- coding: utf-8 -*-
"""build-network标签段统一重写: 全部站名7.5px加粗+紧贴圆点(用户: 距离减小/换乘站同步缩小一致)"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

p = 'tools/build-network.py'
s = open(p, encoding='utf-8').read()

NL = chr(10)
start = s.index('labels = []              # (名, x, y) 文本锚(左上)')
end_mark = "print('  站名: 换乘%d + 全线%d + 缩放层%d = %d/%d' %"
line_end = s.index(NL, s.index(end_mark))
old_block = s[start:line_end]

new_block = """labels = []              # (名, cx, 基线y) 全部站名统一7.5px加粗(2026-10-22用户: 大小间距全线一致)
placed_boxes = []
failed = []
transfers = [m for m in markers if len(m['lines']) > 1]
st_labels = []
zoom_labels = []        # (名, x, y, 违规数) 缩放层(实在放不下)
zoom_boxes = []
ST_FONT = 7.5
RINGS_TIGHT = [2.5, 6.0, 11.0, 17.0]


def st_w(nm):
    return sum(ST_FONT if ord(ch) > 0x2E80 else 4.2 for ch in nm)


def st_clear(rect, own_mk):
    x, y, w, h = rect
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
    for _t in re.finditer(r'<text x="([\\d.-]+)" y="([\\d.-]+)"[^>]*font-size="10.5"[^>]*>([^<]+)</text>', _g.group(1)):
        card_label.setdefault(_t.group(3).strip(), (float(_t.group(1)), float(_t.group(2))))


def place_one(mk):
    \"\"\"统一放置: 卡片方位拉近(钳13px)→紧环8向→缩放层(最少违规+互避让)。\"\"\"
    nm = mk['name']
    w, h = st_w(nm), 8.5
    mx, my = mk['center']
    cands = []
    if nm in card_label:                       # 卡片标准方位, 拉近钳制(旧位按10.5字号留距, 小字要贴圆)
        cx, cy = card_label[nm]
        ox, oy = cx - mx, (cy - 3.75) - my     # 标签中心相对标记中心
        L = (ox * ox + oy * oy) ** 0.5
        if L > 1:
            k = min(1.0, 13.0 / L)
            cands.append((mx + ox * k, my + oy * k + 3.75))
    for ring in RINGS_TIGHT:
        for dx, dy in DIRS:
            ax, ay = marker_anchor(mk, dx, dy)
            r2 = place_box(w, h, ax + dx * ring, ay + dy * ring, dx, dy)
            cands.append((r2[0] + w / 2, r2[1] + h / 2))
    for cx, cy in cands:
        rect = (cx - w / 2, cy - h / 2, w, h)
        if st_clear(rect, mk):
            labels.append((nm, cx, cy + 3.25))
            placed_boxes.append((nm,) + rect)
            return True
    # 缩放层: 放宽净距, 取最少违规位(互避让), 白描边光环保可读
    best = None
    for cx, cy in cands:
        rect = (cx - w / 2, cy - h / 2, w, h)
        rx_, ry_ = rect[0], rect[1]
        viol = 0
        for nm2, ax, ay, bx, by, _c in corridors:
            if rect_seg_dist(rect, (ax, ay), (bx, by)) < CORRIDOR_HALF + 0.5:
                viol += 1
        for nm2, x2, y2, w2, h2 in placed_boxes + zoom_boxes:
            if not (rx_ + w + 0.5 < x2 or x2 + w2 + 0.5 < rx_ or ry_ + h + 0.5 < y2 or y2 + h2 + 0.5 < ry_):
                viol += 2
                break
        for other in markers:
            if other is mk:
                continue
            if other['kind'] == 'capsule':
                edges = poly_edges(other['hull']) if len(other['hull']) > 2 else [tuple(other['hull'])]
                if any(rect_seg_dist(rect, a, b) < CAP_W / 2 + 0.5 for a, b in edges):
                    viol += 2
                    break
                continue
            ox_, oy_ = other['center']
            qx = min(max(ox_, rx_), rx_ + w); qy = min(max(oy_, ry_), ry_ + h)
            if dist((ox_, oy_), (qx, qy)) < other['r'] + 0.5:
                viol += 2
                break
        if viol == 0:
            best = (0, cx, cy)
            break
        if best is None or viol < best[0]:
            best = (viol, cx, cy)
    assert best, nm
    zoom_labels.append((nm, best[1], best[2] + 3.25, best[0]))
    zoom_boxes.append((nm, best[1] - w / 2, best[2] - h / 2, w, h))
    return True


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


_mks = sorted(markers, key=lambda m: (len(m['lines']) <= 1, opt_n(m), m['name']))
for mk in _mks:
    place_one(mk)
print('  站名: 显示%d + 缩放层%d = %d/%d' % (len(labels), len(zoom_labels), len(labels) + len(zoom_labels), len(markers)))"""

s = s.replace(old_block, new_block)
assert 'RINGS_TIGHT' in s and s.count('RINGS_TIGHT') >= 3
open(p, 'w', encoding='utf-8').write(s)
print('unified block written')
