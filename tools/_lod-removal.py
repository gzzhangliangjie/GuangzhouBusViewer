# -*- coding: utf-8 -*-
"""删缩放层+二档小字(用户: APM继续缩小到放得下/不搞放大显示骚操作)"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

p = 'tools/build-network.py'
s = open(p, encoding='utf-8').read()

# 1) place_one 整函数替换
start = s.index('APM_DENSE = {')
end = s.index('# 受限优先: 换乘站可选位少先放, 其余按名序')
new_block = '''APM_DENSE = {'天河南', '黄埔大道', '妇儿中心', '花城大道', '大剧院'}  # APM中段: 三平行竖线夹缝
ST_FONT2 = 6.0   # 二档小字: 7.5px放不下时继续缩小(用户定稿, 2026-10-22), 不搞缩放层


def st_w2(nm):
    return sum(ST_FONT2 if ord(ch) > 0x2E80 else 3.4 for ch in nm)


def _cands_for(mk, nm, w, hh, fs):
    mx, my = mk['center']
    cands = []
    if nm in APM_DENSE and fs == ST_FONT2:
        cands.append((mx + 8.0 + w / 2, my))    # 东侧梯子位(缩小后与18号线净距~18px, 1:1放下)
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
    """7.5px常规→6px二档(继续缩小直到放得下, 无缩放层)。返回True=已放。"""
    nm = mk['name']
    for fs, hh in ((ST_FONT, 8.5), (ST_FONT2, 7.0)):
        w = st_w(nm) if fs == ST_FONT else st_w2(nm)
        for cx, cy in _cands_for(mk, nm, w, hh, fs):
            rect = (cx - w / 2, cy - hh / 2, w, hh)
            if st_clear(rect, mk):
                labels.append((nm, cx, cy - hh / 2 + 0.8 * fs, fs))
                placed_boxes.append((nm,) + rect)
                return True
    failed.append(nm)
    return False


'''
s = s[:start] + new_block + s[end:]

# 2) zoom层残留清理
s = s.replace("""zoom_labels = []        # (名, x, y, 违规数) 缩放层(实在放不下)
zoom_boxes = []
""", "")
s = s.replace("""print('  站名: 显示%d + 缩放层%d = %d/%d' % (len(labels), len(zoom_labels), len(labels) + len(zoom_labels), len(markers)))""",
              """print('  站名: %d/%d (未放: %s)' % (len(labels), len(markers), ','.join(failed) or '无'))""")

# 3) 发射段: per-label字号, 删缩放层组
old_emit = """out.append('<g id="站名标注" font-family="\\'Microsoft YaHei\\', \\'PingFang SC\\', sans-serif" '
           'font-size="7.5" font-weight="700" fill="%s">' % INK)
for nm, cx, cy in labels:
    out.append('<text x="%s" y="%s" text-anchor="middle">%s</text>' % (fmt(cx), fmt(cy), nm))
out.append('</g>')"""
new_emit = """out.append('<g id="站名标注" font-family="\\'Microsoft YaHei\\', \\'PingFang SC\\', sans-serif" '
           'font-weight="700" fill="%s">' % INK)
for nm, cx, cy, fs in labels:
    out.append('<text x="%s" y="%s" font-size="%s" text-anchor="middle">%s</text>'
               % (fmt(cx), fmt(cy), fmt(fs), nm))
out.append('</g>')"""
assert s.count(old_emit) == 1, 'emit mismatch'
s = s.replace(old_emit, new_emit)

# 4) 删 zoom_group 与 -全名 变体(按标记行区间删除)
if 'zoom_group = (' in s:
    z_start = s.index('zoom_group = (')
    z_end = s.index("out.append('<g id=\"图例\">')")
    s = s[:z_start] + s[z_end:]
if '# 全名变体' in s:
    z = s.index('# 全名变体')
    z2 = s.index('f.write(svg_full)', z)
    z2 = s.index('\n', z2) + 1
    s = s[:z] + s[z2:]

open(p, 'w', encoding='utf-8').write(s)
print('builder rewritten')
