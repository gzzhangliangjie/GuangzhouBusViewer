# -*- coding: utf-8 -*-
"""渲染官图整图 -> 裁横向终点局部2x -> 拼对照图 data/_official-term-refs.png"""
import xml.etree.ElementTree as ET
import subprocess, tempfile, os, json
from PIL import Image, ImageDraw

NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
root = ET.parse('assets/gz-tim-2026.svg').getroot()
W, H = 2848, 2054
root.set('width', str(W)); root.set('height', str(H))
svg = ET.tostring(root, encoding='unicode')
html = os.path.join(tempfile.gettempdir(), '_timwrap.html')
open(html, 'w', encoding='utf-8').write(
    '<!DOCTYPE html><meta charset="UTF-8"><style>html,body{margin:0;background:#fff}</style>' + svg)
png = os.path.join(tempfile.gettempdir(), '_tim.png')
subprocess.run([r'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', '--headless', '--disable-gpu',
                '--window-size=%d,%d' % (W, H), '--screenshot=%s' % png,
                'file:///' + html.replace('\\', '/')], capture_output=True, timeout=120)
im = Image.open(png).convert('RGB')
print('map png', im.size)
terms = {'滘口': (994.5, 956.2), '万胜围': (2488.5, 1820.2), '沥滘': (1620.0, 524.2), '飞鹅岭': (1314.0, 92.2),
         '广州东站': (1660.0, 844.0), '燕山': (2155.5, 686.2), '南沙客运港': (1962.0, 924.8), '新城东': (882.0, 1604.2),
         '万顷沙': (2515.5, 1874.2), '高增': (1498.5, 254.2)}
R, Z = 95, 2
cells = []
for nm, (x, y) in terms.items():
    box = (max(0, int(x - R)), max(0, int(y - R)), min(W, int(x + R)), min(H, int(y + R)))
    c = im.crop(box)
    c = c.resize((c.width * Z, c.height * Z), Image.LANCZOS)
    cells.append((nm, c))
cw = max(c.width for _, c in cells); ch = max(c.height for _, c in cells)
cols = 5; rows = (len(cells) + cols - 1) // cols
sheet = Image.new('RGB', (cols * cw, rows * (ch + 22)), '#dddddd')
dr = ImageDraw.Draw(sheet)
for i, (nm, c) in enumerate(cells):
    px, py = (i % cols) * cw, (i // cols) * (ch + 22)
    sheet.paste(c, (px + (cw - c.width) // 2, py + 22))
    dr.text((px + 6, py + 4), nm, fill='black')
sheet.save('data/_official-term-refs.png')
print('saved data/_official-term-refs.png', sheet.size)
