# -*- coding: utf-8 -*-
"""官方徽标提取器: 从 Tim 图图例区抠出 19 条线的完整徽标矢量组(色块+白数字+官方字形「N号线/Line N」)
图例网格(实测):
  行 y=166.51: 1,5,9,13,22   列 x≈171,279,387,490,598
  行 y=195.76: 2,6,10,14,GF
  行 y=225.01: 3,7,11,18
  行 y=254.26: 4,8,12,21
  APM 胶囊 y=416.26 x=171
条目 = 色块(class stN 线色) + 白数字(class st0, 色块内) + 黑字(无类 path, fill 继承)
输出 data/badges-official.json: 每 ref {full:{w,h,elements}, chip:{w,h,elements,fill}}
  元素坐标已归一化到各自 bbox 左上角 (0,0)。
"""
import xml.etree.ElementTree as ET
import re, json, os

NS = 'http://www.w3.org/2000/svg'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG = os.path.join(ROOT, 'assets/gz-tim-2026.svg')
OUT = os.path.join(ROOT, 'data/badges-official.json')

ROWS = [
    (166.51, ['1', '5', '9', '13', '22']),
    (195.76, ['2', '6', '10', '14', 'GF']),
    (225.01, ['3', '7', '11', '18']),
    (254.26, ['4', '8', '12', '21']),
]
APM = ('APM', 171.01, 416.26)
COL_PITCH = 108.0          # 图例列距
ROW_BAND = 27.0            # 条目内容带高: 色块顶-2.2 .. 顶+24.8 (行距29.25)
CHIP_H = [13.0, 14.6]      # 色块高容差
CHIP_W = [(12.5, 15.5), (17.0, 19.5), (30.5, 32.5)]  # 1位数/2位数/APM胶囊


def sample_d(d):
    pts = []
    cur = [0.0, 0.0]
    start = [0.0, 0.0]
    for cmd, body in re.findall(r'([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)', d):
        nums = [float(v) for v in re.findall(r'-?\d+\.?\d*(?:[eE][-+]?\d+)?', body)]
        rel = cmd.islower()
        c = cmd.upper()
        i = 0
        while i < len(nums):
            if c == 'M':
                p = nums[i:i+2]; i += 2
                cur = [p[0]+(cur[0] if rel else 0), p[1]+(cur[1] if rel else 0)]
                start = list(cur); pts.append(tuple(cur))
            elif c == 'L':
                p = nums[i:i+2]; i += 2
                cur = [p[0]+(cur[0] if rel else 0), p[1]+(cur[1] if rel else 0)]
                pts.append(tuple(cur))
            elif c == 'H':
                cur[0] = nums[i]+(cur[0] if rel else 0); i += 1; pts.append(tuple(cur))
            elif c == 'V':
                cur[1] = nums[i]+(cur[1] if rel else 0); i += 1; pts.append(tuple(cur))
            elif c in 'CQ':
                p = nums[i+4:i+6] if c == 'C' else nums[i+2:i+4]
                i += 6 if c == 'C' else 4
                if len(p) == 2:
                    cur = [p[0]+(cur[0] if rel else 0), p[1]+(cur[1] if rel else 0)]
                    pts.append(tuple(cur))
            elif c in 'ST':
                p = nums[i:i+2]; i += 2
                cur = [p[0]+(cur[0] if rel else 0), p[1]+(cur[1] if rel else 0)]
                pts.append(tuple(cur))
            elif c == 'A':
                p = nums[i+5:i+7]; i += 7
                if len(p) == 2:
                    cur = [p[0]+(cur[0] if rel else 0), p[1]+(cur[1] if rel else 0)]
                    pts.append(tuple(cur))
            elif c == 'Z':
                cur = list(start); pts.append(tuple(cur)); i = len(nums)
            else:
                i = len(nums)
    return pts


def translate_d(d, ox, oy):
    """路径平移: 绝对命令坐标减 (ox,oy), 相对命令不动。"""
    out = []
    for m in re.finditer(r'([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)', d):
        cmd, body = m.group(1), m.group(2)
        nums = re.findall(r'-?\d+\.?\d*(?:[eE][-+]?\d+)?', body)
        c = cmd.upper()
        # 每组内 x 坐标的序号(绝对命令才平移)
        xidx = {'M': [0], 'L': [0], 'H': [0], 'V': [],
                'C': [0, 2, 4], 'S': [0, 2], 'Q': [0, 2], 'T': [0],
                'A': [5]}.get(c, [])
        yidx = [i + 1 for i in xidx if c not in ('V',)] if c not in ('H', 'V') else ([1] if False else [i + 1 for i in xidx])
        if c == 'V':
            yidx = [0]
        parts = []
        k = 0
        i = 0
        while i < len(nums):
            if c == 'A':
                grp = nums[i:i+7]; i += 7
            elif c in ('H', 'V'):
                grp = nums[i:i+1]; i += 1
            else:
                grp = nums[i:i+2]; i += 2
            g = list(grp)
            if cmd.isupper():
                for xi in (xidx if c != 'V' else []):
                    if xi < len(g):
                        g[xi] = repr(float(g[xi]) - ox)
                for yi in (yidx if c != 'H' else []):
                    if yi < len(g):
                        g[yi] = repr(float(g[yi]) - oy)
            parts.append(' '.join(g))
        out.append(cmd + (' '.join(parts) if parts else ''))
    return ''.join(out)


def main():
    src = open(SVG, encoding='utf-8').read()
    css_fill = {}
    for m in re.finditer(r'\.(st\d+)\{([^}]*)\}', src):
        fm = re.search(r'fill:\s*(#[0-9A-Fa-f]{3,6})', m.group(2))
        if fm and 'stroke' not in m.group(2):
            css_fill[m.group(1)] = fm.group(1)

    root = ET.parse(SVG).getroot()
    paths = []  # (el, x0,y0,x1,y1, fill, cls)
    for anc, el in (([], root),):
        pass

    def walk(el, anc_fills):
        tag = el.tag.split('}')[-1]
        own = el.get('fill')
        cls = el.get('class')
        f = None
        if cls and cls in css_fill:
            f = css_fill[cls]
        elif own and own.startswith('#'):
            f = own
        eff = f if f else anc_fills
        if tag == 'path' and el.get('d'):
            pts = sample_d(el.get('d'))
            if len(pts) >= 3:
                xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
                paths.append((el, min(xs), min(ys), max(xs), max(ys), eff, cls))
        for ch in el:
            walk(ch, eff)

    walk(root, None)

    # ---- 找色块(chips): 线色 fill、无 stroke 的 path, 尺寸=数字块/胶囊 ----
    chips = []
    for el, x0, y0, x1, y1, f, cls in paths:
        w, h = x1-x0, y1-y0
        if not (CHIP_H[0] <= h <= CHIP_H[1]):
            continue
        if not any(a <= w <= b for a, b in CHIP_W):
            continue
        if cls not in css_fill:
            continue
        inrows = any(abs(y0 - ry) < 1.6 and 160 < x0 < 700 for ry, _ in ROWS)
        isapm = abs(y0 - APM[2]) < 1.6 and abs(x0 - APM[1]) < 2
        if inrows or isapm:
            chips.append({'ref': None, 'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1,
                          'w': w, 'h': h, 'fill': f, 'el': el})
    assert len(chips) == 19, '图例色块应 19 枚, 实得 %d' % len(chips)

    # ---- 网格 -> ref ----
    for ry, refs in ROWS:
        row = sorted([c for c in chips if abs(c['y0'] - ry) < 1.6], key=lambda c: c['x0'])
        assert len(row) == len(refs), '行 %s: %d 块 vs %d ref' % (ry, len(row), len(refs))
        for c, r in zip(row, refs):
            c['ref'] = r
    for c in chips:
        if c['ref'] is None:
            c['ref'] = 'APM'

    # ---- 每条目收集内容(色块+白数字+黑字) ----
    out = {}
    for ref in [r for _, rs in ROWS for r in rs] + ['APM']:
        chip = next(c for c in chips if c['ref'] == ref)
        # 条目内容窗: 色块左缘-1 .. 右缘(按列距-10, APM 定宽), 色块顶-2.2 .. 顶+带高
        right = chip['x0'] + (COL_PITCH - 10 if ref != 'APM' else 200)
        if ref in ('22', 'GF'):            # 第5列后无邻列
            right = chip['x0'] + 100
        top = chip['y0'] - 2.2
        bot = chip['y0'] + (ROW_BAND - 2.2 if ref != 'APM' else 27.0)
        content = []
        for el, x0, y0, x1, y1, f, cls in paths:
            if x0 >= chip['x0'] - 1.2 and x1 <= right + 0.5 and y0 >= top - 0.3 and y1 <= bot + 0.3:
                content.append((el, x0, y0, x1, y1, f))
        assert content, '%s 条目无内容' % ref
        # chip 子集: bbox 完全在色块内(数字)
        cx0, cy0, cx1, cy1 = chip['x0'], chip['y0'], chip['x1'], chip['y1']
        chip_els = [c for c in content if c[1] >= cx0-0.6 and c[2] >= cy0-0.6 and c[3] <= cx1+0.6 and c[4] <= cy1+0.6]
        def emit(subset, ox, oy):
            els = []
            for el, x0, y0, x1, y1, f in subset:
                els.append({'d': translate_d(el.get('d'), ox, oy), 'fill': f or '#000000'})
            bb = [min(c[1] for c in subset)-ox, min(c[2] for c in subset)-oy,
                  max(c[3] for c in subset)-ox, max(c[4] for c in subset)-oy]
            return {'w': round(bb[2]-bb[0], 2), 'h': round(bb[3]-bb[1], 2), 'bb': [round(v, 2) for v in bb], 'elements': els}
        full = emit(content, chip['x0'], top)
        chipo = emit(chip_els, cx0, cy0)
        chipo['fill'] = chip['fill']
        chipo['dx'] = round(cx0 - min(c[1] for c in content), 2)   # chip 在 full 内偏移
        chipo['dy'] = round(cy0 - top, 2)
        ndig = len(chip_els)
        print('%-4s full %5.1fx%-5.1f (%d elems)  chip %4.1fx%-4.1f (%d 白件) fill %s'
              % (ref, full['w'], full['h'], len(full['elements']), chipo['w'], chipo['h'], ndig, chip['fill']))
        out[ref] = {'full': full, 'chip': chipo}
    with open(OUT, 'w', encoding='utf-8') as fp:
        json.dump(out, fp, ensure_ascii=False)
    print('→', OUT)


if __name__ == '__main__':
    main()
