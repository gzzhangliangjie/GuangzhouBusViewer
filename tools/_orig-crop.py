# -*- coding: utf-8 -*-
"""渲染原图 gz-tim-2026.svg 指定区域为 PNG(视觉核对用)。
用法: python tools/_orig-crop.py x y w h [scale] [out.png]
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
x, y, w, h = (float(v) for v in sys.argv[1:5])
scale = float(sys.argv[5]) if len(sys.argv) > 5 else 3.0
out = sys.argv[6] if len(sys.argv) > 6 else 'data/_orig-crop-tmp.png'
out = out if os.path.isabs(out) else os.path.join(ROOT, out)

s = open(os.path.join(ROOT, 'assets', 'gz-tim-2026.svg'), encoding='utf-8').read()
W, H = int(w * scale), int(h * scale)
s2 = re.sub(r'(<svg\b[^>]*?)width="[^"]*"', r'\1width="%d"' % W, s, count=1)
s2 = re.sub(r'(<svg\b[^>]*?)height="[^"]*"', r'\1height="%d"' % H, s2, count=1)
s2 = re.sub(r'(<svg\b[^>]*?)viewBox="[^"]*"', r'\1viewBox="%s %s %s %s"' % (x, y, w, h), s2, count=1)
assert 'viewBox="%s %s' % (x, y) in s2, 'root svg 属性替换失败'
html = ('<!DOCTYPE html><html><head><meta charset="UTF-8">'
        '<style>html,body{margin:0;padding:0;background:#fff;overflow:hidden}</style></head><body>'
        + s2 + '</body></html>')
hp = os.path.join(ROOT, 'data', '_orig-crop-wrap.html')
open(hp, 'w', encoding='utf-8').write(html)
r = subprocess.run([EDGE, '--headless', '--disable-gpu', '--force-device-scale-factor=1',
                    '--user-data-dir=%s' % os.path.join(ROOT, 'data', '_edge-prof-crop'),
                    '--no-first-run', '--window-size=%d,%d' % (W, H), '--screenshot=%s' % out,
                    'file:///%s' % hp.replace('\\', '/')], capture_output=True, timeout=90)
assert os.path.exists(out), '截图未生成 rc=%s %s' % (r.returncode, r.stderr[-300:])
print(out, os.path.getsize(out))
