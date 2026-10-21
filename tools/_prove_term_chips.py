# -*- coding: utf-8 -*-
"""终点徽标改动证明: git HEAD 版 vs 工作区版 逐卡渲染像素 diff。
预期: 修改过的卡必须变(否则FAIL), 违例数 15->0。"""
import os, subprocess, sys, io, tempfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
from verify_card_pixel import render

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
CARDS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '18', '21', '22', 'APM线', '广佛线']

tmp = tempfile.mkdtemp()
total_changed = 0
for ln in CARDS:
    rel = 'assets/lines/line-%s.svg' % ln if ln.endswith('线') else 'assets/lines/line-%s号线.svg' % ln
    cur = os.path.join(tmp, 'cur.svg')
    open(cur, 'w', encoding='utf-8').write(open(rel, encoding='utf-8').read())
    head = os.path.join(tmp, 'head.svg')
    blob = subprocess.run(['git', 'show', 'HEAD:%s' % rel], capture_output=True)
    if blob.returncode != 0:
        print('%-6s 无HEAD版本(新卡?) 跳过' % ln)
        continue
    open(head, 'wb').write(blob.stdout)
    a, _ = render(head)
    b, _ = render(cur)
    if a.shape != b.shape:
        print('%-6s shape变 %s -> %s (画布扩框)' % (ln, a.shape, b.shape))
        h = min(a.shape[0], b.shape[0]); w = min(a.shape[1], b.shape[1])
        a2, b2 = a[:h, :w], b[:h, :w]
        diff = int((np.abs(a2.astype(int) - b2.astype(int)).sum(axis=2) > 30).sum())
    else:
        diff = int((np.abs(a.astype(int) - b.astype(int)).sum(axis=2) > 30).sum())
    tag = 'OK' if diff > 50 else 'FAIL(没变?)'
    total_changed += 1 if diff > 50 else 0
    print('%-6s 像素diff %6d  %s' % (ln, diff, tag))
print('变化卡: %d / %d' % (total_changed, len(CARDS)))
