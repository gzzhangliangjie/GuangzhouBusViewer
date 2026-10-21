# -*- coding: utf-8 -*-
"""2号线北排整体错位一站修复(2026-10-21): 官图真值=嘉禾望岗(1498.5,578.2)黑/白云文化广场(1390.5,693)黑,
卡上站名全左移一格+多一个830圆缺一个1498.5圆。外科手术: 删830圆、增1498.5圆、圆改名、走廊延伸+竖stub、
标签随动、终点数字块随动。用法: python tools/_l2-shift-fix.py
"""
import re, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

CARD = 'assets/lines/line-2号线.svg'
s = open(CARD, encoding='utf-8').read()

# ---- 1) 删多余830圆(官图竖线上无此圆) ----
t830 = '<circle cx="1336.5" cy="830.0" r="4.5" style="fill:#FFFFFF;stroke:#1E88E5;stroke-width:2" data-nm="三元里" />'
if t830 not in s:
    raise SystemExit('830圆未匹配')
s = s.replace(t830 + '\n    ', '', 1) if t830 + '\n    ' in s else s.replace(t830, '', 1)

# ---- 2) 圆改名(链式倒序: 每格让位给北邻站名, 官图真值名归位) ----
REN = [
    ('1473.8', '609.8', '嘉禾望岗', '黄边'),
    ('1446.8', '636.8', '黄边', '江夏'),
    ('1419.8', '663.8', '江夏', '萧岗'),
    ('1390.5', '693.0', '萧岗', '白云文化广场'),
    ('1361.2', '722.2', '白云文化广场', '白云公园'),
    ('1336.5', '760.5', '白云公园', '飞翔公园'),
    ('1336.5', '801.0', '飞翔公园', '三元里'),
]
for cx, cy, old, new in reversed(REN):
    t0 = '<circle cx="%s" cy="%s" r="4.5" style="fill:#FFFFFF;stroke:#1E88E5;stroke-width:2" data-nm="%s" />' % (cx, cy, old)
    if t0 not in s:
        raise SystemExit('圆改名未匹配: %s@(%s,%s)' % (old, cx, cy))
    s = s.replace(t0, t0.replace('data-nm="%s"' % old, 'data-nm="%s"' % new), 1)

# ---- 3) 新增嘉禾望岗终点圆: 插在原嘉禾望岗圆位(现名黄边)之前保持文档序 ----
anchor = '<circle cx="1473.8" cy="609.8" r="4.5" style="fill:#FFFFFF;stroke:#1E88E5;stroke-width:2" data-nm="黄边" />'
if anchor not in s:
    raise SystemExit('黄边锚圆未匹配')
newc = '<circle cx="1498.5" cy="578.2" r="4.5" style="fill:#FFFFFF;stroke:#1E88E5;stroke-width:2" data-nm="嘉禾望岗" />'
s = s.replace(anchor, newc + '\n    ' + anchor, 1)

# ---- 4) 走廊: 对角线延伸到(1498.5,585.0) + 竖stub进圆 ----
m = re.search(r'<line x1="1345\.5" y1="738\.0" x2="1473\.8" y2="609\.8"[^>]*/>', s)
if not m:
    raise SystemExit('走廊段未匹配')
ext = m.group(0).replace('x2="1473.8" y2="609.8"', 'x2="1498.5" y2="585.0"')
s = s.replace(m.group(0), ext, 1)
sty = re.search(r'style="[^"]*"', m.group(0)).group(0)
stub = '<line x1="1498.5" y1="585.0" x2="1498.5" y2="578.2" %s />' % sty
k2 = s.find('>', s.find('<g id="走廊')) + 1
s = s[:k2] + '\n    ' + stub + s[k2:]

# ---- 5) 标签随动 ----
def setpos(txt, nx, ny):
    global s
    m2 = re.search(r'<text x="([\d.-]+)" y="([\d.-]+)"([^>]*)>%s</text>' % re.escape(txt), s)
    if not m2:
        raise SystemExit('标签未匹配: %s' % txt)
    s = s.replace(m2.group(0), '<text x="%.1f" y="%.1f"%s>%s</text>' % (nx, ny, m2.group(3), txt), 1)

def mv(txt, fx, fy):
    m2 = re.search(r'<text x="([\d.-]+)" y="([\d.-]+)"([^>]*)>%s</text>' % re.escape(txt), s)
    if not m2:
        raise SystemExit('标签未匹配: %s' % txt)
    setpos(txt, float(m2.group(1)) + fx, float(m2.group(2)) + fy)

# 嘉禾望岗终点版式: 文字圆正上方21px, EN+7.5
setpos('嘉禾望岗', 1498.5, 557.2)
setpos('Jiahewanggang', 1498.5, 564.7)
mv('黄边', 27.0, -27.0); mv('Huangbian', 27.0, -27.0)
mv('江夏', 27.0, -27.0); mv('Jiangxia', 27.0, -27.0)
mv('萧岗', 29.3, -29.2); mv('Xiao-gang', 29.3, -29.2)
mv('白云文化广场', 29.3, -29.2); mv('Baiyun Culture Square', 29.3, -29.2)
# 白云公园移到对角线钉位: 标签改对角线法向(同黄边偏移-19.1,-17.3)
setpos('白云公园', 1342.1, 704.9)
setpos('Baiyun Park', 1342.1, 712.4)
mv('飞翔公园', 0, -40.5); mv('Feixiang Park', 0, -40.5)
mv('三元里', 0, -29.0); mv('Sanyuanli', 0, -29.0)

# ---- 6) 终点数字块随动: 同x居中1498.5, 文字上缘再上净距3 ----
s = s.replace('translate(1467.06 558.31)" data-box="1467.1,558.3,1480.5,571.8"',
              'translate(1491.81 526.7)" data-box="1491.8,526.7,1505.2,540.2"', 1)

open(CARD, 'w', encoding='utf-8').write(s)
n = len(re.findall(r'data-nm="', s))
print('2号线手术后站圆数:', n)
for nm, cx, cy in [('嘉禾望岗', '1498.5', '578.2'), ('白云文化广场', '1390.5', '693.0'), ('三元里', '1336.5', '801.0'), ('黄边', '1473.8', '609.8')]:
    ok = ('cx="%s" cy="%s"' % (cx, cy)) in s and ('data-nm="%s"' % nm) in s
    print(' %s -> (%s,%s) %s' % (nm, cx, cy, 'OK' if ok else 'FAIL'))
