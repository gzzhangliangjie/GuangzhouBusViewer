# -*- coding: utf-8 -*-
"""官图中山八/镇龙走廊真值提取: 包围盒与zone相交的 line/path/rect/circle 全打印 + CSS类颜色映射"""
import re, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

s = open('assets/gz-tim-2026.svg', encoding='utf-8').read()

ZONES = {
    'panyu':   (1720, 1560, 1950, 1740),  # 番禺广场大区: 3/18/22 官方画法
}

found_cls = set()

def cls_of(t):
    m = re.search(r'class="([^"]+)"', t)
    if m:
        found_cls.add(m.group(1).split()[0])
        return m.group(1)
    st = re.search(r'stroke="([^"]+)"', t)
    return 'stroke=' + st.group(1) if st else '-'

for name, z in ZONES.items():
    zx0, zy0, zx1, zy1 = z
    print('==== %s zone=%s ====' % (name, z))
    for m in re.finditer(r'<line\b([^>]*)/>', s):
        t = m.group(1)
        g = re.search(r'x1="([-\d.]+)"\s+y1="([-\d.]+)"\s+x2="([-\d.]+)"\s+y2="([-\d.]+)"', t)
        if not g:
            continue
        a, b, c, d = (float(v) for v in g.groups())
        if min(a, c) > zx1 or max(a, c) < zx0 or min(b, d) > zy1 or max(b, d) < zy0:
            continue
        print('L (%8.2f,%8.2f)-(%8.2f,%8.2f) %s' % (a, b, c, d, cls_of(t)))
    for m in re.finditer(r'<path\b([^>]*)/>', s):
        t = m.group(1)
        dm = re.search(r'\bd="([^"]+)"', t)
        if not dm:
            continue
        d = dm.group(1)
        nums = [float(v) for v in re.findall(r'-?\d+\.?\d*', d)]
        if len(nums) < 4:
            continue
        pts = list(zip(nums[::2], nums[1::2]))
        bx0 = min(p[0] for p in pts); bx1 = max(p[0] for p in pts)
        by0 = min(p[1] for p in pts); by1 = max(p[1] for p in pts)
        if bx1 < zx0 or bx0 > zx1 or by1 < zy0 or by0 > zy1:
            continue
        flag = 'REL!' if re.search(r'[mlqahv]', d.replace('e-', '')) else ''
        print('P (%8.2f,%8.2f)-(%8.2f,%8.2f) %s %s d=%s' % (bx0, by0, bx1, by1, cls_of(t), flag, d[:100]))
    for m in re.finditer(r'<rect\b([^>]*)/>', s):
        t = m.group(1)
        g = re.search(r'x="([-\d.]+)"\s+y="([-\d.]+)"\s+width="([-\d.]+)"\s+height="([-\d.]+)"', t)
        if not g:
            continue
        a, b, w, h = (float(v) for v in g.groups())
        if a > zx1 or a + w < zx0 or b > zy1 or b + h < zy0:
            continue
        print('R (%8.2f,%8.2f) %6.1fx%-6.1f %s' % (a, b, w, h, cls_of(t)))
    for m in re.finditer(r'<circle\b([^>]*)/>', s):
        t = m.group(1)
        g = re.search(r'cx="([-\d.]+)"\s+cy="([-\d.]+)"', t)
        if not g:
            continue
        a, b = float(g.group(1)), float(g.group(2))
        if not (zx0 <= a <= zx1 and zy0 <= b <= zy1):
            continue
        r = re.search(r'r="([-\d.]+)"', t)
        print('C (%8.2f,%8.2f) r=%-4s %s' % (a, b, r.group(1) if r else '?', cls_of(t)))

print('==== CSS rules ====')
sty = re.search(r'<style[^>]*>(.*?)</style>', s, re.S)
body = sty.group(1) if sty else s
for c in sorted(found_cls):
    mm = re.search(r'\.%s\b[^}]*}' % re.escape(c), body, re.S)
    print('.%s %s' % (c, ' '.join(mm.group(0).split()) if mm else '(no rule)'))
