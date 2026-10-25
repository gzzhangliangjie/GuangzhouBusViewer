# -*- coding: utf-8 -*-
"""G8候选插桩: 对比外科前后两卡的chip配对候选差异"""
import sys, io
sys.path.insert(0, 'tools')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import verify_card as V

for path in ('data/_l2-before.svg', 'assets/lines/line-2号线.svg'):
    c = V.load(path)
    labels, badges = c['labels'], c['badges']
    print('====', path)
    for bd in badges:
        if bd.get('mode') != 'chip':
            continue
        bx0, by0, bx1, by1 = bd['box']
        ccx, ccy = (bx0 + bx1) / 2, (by0 + by1) / 2
        print('  chip @(%.1f,%.1f)' % (ccx, ccy))
        for lb in labels:
            lcy = (lb['box'][1] + lb['box'][3]) / 2
            if abs(lb['x'] - ccx) <= 60:
                gb = by0 - lb['box'][3]
                ga = lb['box'][1] - by1
                if 0 < gb < 20 or 0 < ga < 20:
                    print('    V %s below=%.1f above=%.1f (box_bottom=%.1f)' % (lb['nm'], gb, ga, lb['box'][3]))
            if abs(lcy - ccy) <= 60:
                gr = bx0 - lb['box'][2]
                glf = lb['box'][0] - bx1
                if 0 < gr < 20 or 0 < glf < 20:
                    print('    H %s right=%.1f left=%.1f' % (lb['nm'], gr, glf))
