# -*- coding: utf-8 -*-
"""通用 SVG 区域渲染: python tools/_svg-crop.py <svg路径> <x> <y> <w> <h> <scale> <out.png>"""
import os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'

svg = sys.argv[1]
x, y, w, h, scale = (float(v) for v in sys.argv[2:7])
out = sys.argv[7]
if not os.path.isabs(svg):
    svg = os.path.join(ROOT, svg)
out = out if os.path.isabs(out) else os.path.join(ROOT, out)
s = open(svg, encoding='utf-8').read()
W, H = int(w * scale), int(h * scale)
s = re.sub(r'(<svg\b[^>]*?)width="[^"]*"', r'\1width="%d"' % W, s, count=1)
s = re.sub(r'(<svg\b[^>]*?)height="[^"]*"', r'\1height="%d"' % H, s, count=1)
s = re.sub(r'(<svg\b[^>]*?)viewBox="[^"]*"', r'\1viewBox="%s %s %s %s"' % (x, y, w, h), s, count=1)
assert ('viewBox="%s %s' % (x, y)) in s, 'viewBox 替换失败'
html = ('<!DOCTYPE html><html><head><meta charset="UTF-8">'
        '<style>html,body{margin:0;padding:0;background:#fff;overflow:hidden}</style></head><body>'
        + s + '</body></html>')
hp = os.path.join(ROOT, 'data', '_svg-crop-wrap.html')
open(hp, 'w', encoding='utf-8').write(html)
url = 'file:///' + hp.replace('\\', '/')
r = subprocess.run([EDGE, '--headless', '--disable-gpu', '--force-device-scale-factor=1',
                    '--user-data-dir=%s' % os.path.join(ROOT, 'data', '_edge-prof-svgcrop'),
                    '--no-first-run', '--window-size=%d,%d' % (W, H), '--screenshot=%s' % out, url],
                   capture_output=True, timeout=180)
print(out, os.path.getsize(out) if os.path.exists(out) else 'MISSING rc=%d' % r.returncode)
