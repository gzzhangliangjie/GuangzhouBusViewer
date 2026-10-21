# -*- coding: utf-8 -*-
"""裁卡片终点局部(站圆坐标取自卡内 data-nm):
python tools/_card_term_crop.py 卡.svg 站名1,站名2 -> data/_crop-<卡>-<站>.png (2x)"""
import sys, os, subprocess, tempfile
import xml.etree.ElementTree as ET
from PIL import Image

NS = '{http://www.w3.org/2000/svg}'
ET.register_namespace('', NS[1:-1])  # ns0: 前缀在 HTML 内联时整页拒渲
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
card, stations = sys.argv[1], sys.argv[2].split(',')
R, Z = 110, 2

tree = ET.parse(card)
root = tree.getroot()
pos = {c.get('data-nm'): (float(c.get('cx')), float(c.get('cy')))
       for c in root.iter(NS + 'circle') if c.get('data-nm')}
vb = [float(v) for v in root.get('viewBox').split()]
W, H = int(vb[2] * Z), int(vb[3] * Z)
root.set('width', str(W)); root.set('height', str(H))
svg = ET.tostring(root, encoding='unicode')
html = os.path.join(tempfile.gettempdir(), '_cardwrap.html')
open(html, 'w', encoding='utf-8').write(
    '<!DOCTYPE html><meta charset="UTF-8"><style>html,body{margin:0;background:#fff}</style>' + svg)
png = os.path.join(tempfile.gettempdir(), '_cardfull.png')
subprocess.run([r'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', '--headless', '--disable-gpu',
                '--window-size=%d,%d' % (W, H), '--screenshot=%s' % png,
                'file:///' + html.replace('\\', '/')], capture_output=True, timeout=120)
im = Image.open(png).convert('RGB')

base = os.path.basename(card)[:-4]
for st in stations:
    x, y = pos[st]
    x0 = max(0, int((x - vb[0] - R) * Z)); y0 = max(0, int((y - vb[1] - R) * Z))
    x1 = min(W, int((x - vb[0] + R) * Z)); y1 = min(H, int((y - vb[1] + R) * Z))
    c = im.crop((x0, y0, x1, y1))
    out = 'data/_crop-%s-%s.png' % (base, st)
    c.save(out)
    print('saved', out, c.size)
