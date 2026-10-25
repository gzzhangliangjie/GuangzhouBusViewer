# -*- coding: utf-8 -*-
"""dump Tim组_x31_1(11号线)全部走廊元素: line坐标 + path首尾点(弦), 按文档序输出custom_segs素材"""
import re, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

s = open('assets/gz-tim-2026.svg', encoding='utf-8').read()
m = re.search(r'<g id="_x31_1"(?:>| )', s)
assert m, 'group not found'
start = m.end()
depth, j = 1, start
while depth:
    no, nc = s.find('<g', j), s.find('</g>', j)
    if no != -1 and no < nc:
        depth += 1
        j = no + 2
    else:
        depth -= 1
        j = nc + 4
body = s[start:j - 4]

for mm in re.finditer(r'<line\b([^>]*)/>|<path\b([^>]*)/>', body):
    if mm.group(1) is not None:
        t = mm.group(1)
        g = re.search(r'x1="([-\d.]+)"\s+y1="([-\d.]+)"\s+x2="([-\d.]+)"\s+y2="([-\d.]+)"', t)
        a, b, c, d = (float(v) for v in g.groups())
        print('L (%.2f,%.2f)-(%.2f,%.2f)  -> (%.2f,%.2f,%.2f,%.2f),' % (a, b, c, d, a, b, c, d))
    else:
        t = mm.group(2)
        dm = re.search(r'\bd="([^"]+)"', t)
        d = dm.group(1)
        nums = [float(v) for v in re.findall(r'-?\d+\.?\d*', d)]
        x0, y0 = nums[0], nums[1]
        # 相对命令: 累计到终点
        cmds = re.findall(r'([MmLlHhVvCcSs])(-?\d+\.?\d*)?', d)
        cx, cy = x0, y0
        rel = False
        for ch, _ in cmds:
            pass
        # 简化: 绝对M起点 + 末两个数字按是否相对判断
        print('P start(%.2f,%.2f) raw=%s' % (x0, y0, d[:80]))
