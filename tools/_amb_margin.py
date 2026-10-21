# -*- coding: utf-8 -*-
"""标签归属余量: 自圆距/最近他圆距, >0.7 视为含糊。
用法: python tools/_amb_margin.py 卡:站1,站2 ..."""
import os, sys, io, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_card import load
import xml.etree.ElementTree as ET

NS = '{http://www.w3.org/2000/svg}'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

def margins(card, stations):
    c = load('assets/lines/line-%s.svg' % card)
    pos = {}
    for g in c['root'].iter(NS + 'g'):
        if g.get('id') == '站圆':
            for el in g.iter(NS + 'circle'):
                if el.get('data-nm'):
                    pos[el.get('data-nm')] = (float(el.get('cx')), float(el.get('cy')))
    circles = [(x, y) for (x, y, r) in c['circles']]
    for st in stations:
        lb = next(l for l in c['labels'] if l['nm'] == st)
        lcx, lcy = lb['x'], (lb['box'][1] + lb['box'][3]) / 2
        own = math.hypot(pos[st][0] - lcx, pos[st][1] - lcy)
        others = sorted(math.hypot(x - lcx, y - lcy) for (x, y) in circles if (x, y) != pos[st])
        print('%s %-6s 自圆距%.0f 最近他圆距%.0f 余量比%.2f %s' % (
            card, st, own, others[0], own / others[0], '<-- 含糊' if own / others[0] > 0.7 else ''))

for spec in sys.argv[1:]:
    card, sts = spec.rsplit(':', 1)
    margins(card, sts.split(','))
