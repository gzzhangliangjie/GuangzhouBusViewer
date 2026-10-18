# -*- coding: utf-8 -*-
"""官方徽标v4: 修复文字出框(Line1基线应在盒内y+35) + 终点徽标缩放60%并避开标签
布局(参考图像素): 黄底80x43 rx9; 内容y+8..y+35高28; 数字1高28 baseline y+35;
  右列: '号线'rel y8-19(baseline y+18, font11), 'Line 1'rel y31-35(baseline y+35, font7.5);
  1与右列水平间距12(1右缘x+26 -> 右列x+38).
终点徽标: scale=0.6(48x25.8), 西塱放标签下方, 广州东站放标签左侧.
"""
import xml.etree.ElementTree as ET

NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)
CARD = 'assets/lines/line-1号线-17.svg'

card = ET.parse(CARD)
root = card.getroot()
par = {}
def build(el):
    for ch in el:
        par[id(ch)] = el
        build(ch)
build(root)
removed = 0
for g in list(root.iter('{%s}g' % NS)):
    if g.get('id') == '线路徽标':
        par[id(g)].remove(g)
        removed += 1
print('旧徽标删除:', removed)

vb = [float(v) for v in root.get('viewBox').split()]

def make_badge(g, x, y, s=1.0):
    inner = ET.SubElement(g, '{%s}g' % NS)
    if s != 1.0:
        inner.set('transform', 'translate(%s %s) scale(%s) translate(%s %s)' % (x, y, s, -x, -y))
    rect = ET.SubElement(inner, '{%s}rect' % NS)
    rect.set('x', str(x)); rect.set('y', str(y))
    rect.set('width', '80'); rect.set('height', '43')
    rect.set('rx', '9')
    rect.set('fill', '#F5CD42')
    t1 = ET.SubElement(inner, '{%s}text' % NS)
    t1.set('x', str(x + 10)); t1.set('y', str(y + 32.5))
    t1.set('font-family', "'Microsoft YaHei', sans-serif")
    t1.set('font-size', '25')
    t1.set('dominant-baseline', 'auto')
    t1.set('font-weight', 'bold')
    t1.set('fill', '#614F2E')
    t1.text = '1'
    t2 = ET.SubElement(inner, '{%s}text' % NS)
    t2.set('x', str(x + 38)); t2.set('y', str(y + 22))
    t2.set('font-family', "'Microsoft YaHei', sans-serif")
    t2.set('font-size', '11')
    t2.set('font-weight', '600')
    t2.set('fill', '#614F2E')
    t2.text = '号线'
    t3 = ET.SubElement(inner, '{%s}text' % NS)
    t3.set('x', str(x + 38)); t3.set('y', str(y + 35))
    t3.set('font-family', "Arial, sans-serif")
    t3.set('font-size', '7.5')
    t3.set('fill', '#614F2E')
    t3.text = 'Line 1'

g = ET.SubElement(root, '{%s}g' % NS)
g.set('id', '线路徽标')
# 1) 左上角(全尺寸)
make_badge(g, vb[0] + 16, vb[1] + 14)
# 2) 西塱终点: 标签(1101,1290)-(1122,1309) -> 徽标签下方 y=1318, 60%缩放(48x26)
make_badge(g, 1111.5 - 24, 1318, 0.6)
# 3) 广州东站: 标签(1566,848)-(1650,866.5) -> 徽标签左侧 x=1566-8-48=1510
make_badge(g, 1510, 857.2 - 13, 0.6)

card.write(CARD, encoding='unicode', xml_declaration=False)
print('徽标v4写入: 左上全尺寸 + 两终点60%(避开标签)')
