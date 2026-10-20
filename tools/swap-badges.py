# -*- coding: utf-8 -*-
"""原位换徽标: 现存卡片里手绘胶囊(rect 80x43+scale0.6) → 官图提取徽标组(badges-official.json)
头部(无transform): 同左上角锚点换 full 条目(高度对齐42, 宽≤240且≤45%卡宽);
终点(scale 0.6): 同中心换 chip 色块(官方 13.5x13.5/18x13.5/31.5x13.5)。
只动 <g id="线路徽标"> 内部, 走廊/站圆/站名几何零变动。--check 只跑门禁不改文件。
"""
import sys, io, re, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import xml.etree.ElementTree as ET
import build_card as B
from verify_card import run_gates
import importlib.util
_spec = importlib.util.spec_from_file_location('group_card_mod', os.path.join(ROOT, 'tools', 'group-card.py'))
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)

NS = 'http://www.w3.org/2000/svg'
LINES = ['1号线', '2号线', '3号线', '4号线', '5号线', '6号线', '7号线', '8号线', '9号线',
         '10号线', '11号线', '12号线', '13号线', '14号线', '18号线', '21号线', '22号线',
         '广佛线', 'APM线']


def ref_of(zh):
    return zh.replace('号线', '') if zh.endswith('号线') else {'广佛线': 'GF', 'APM线': 'APM'}[zh]


def swap_card(zh, apply=True):
    path = os.path.join(ROOT, 'assets/lines/line-%s.svg' % zh)
    s = open(path, encoding='utf-8').read()
    m0 = re.search(r'<g id="线路徽标">', s)
    if not m0:
        return zh, False, '无线路徽标组'
    start = m0.end()
    depth, j = 1, start
    while depth > 0:
        no = s.find('<g', j); nc = s.find('</g>', j)
        if no != -1 and no < nc:
            depth += 1; j = no + 2
        else:
            depth -= 1; j = nc + 4
    inner = s[start:j-4]  # 去掉 </g>(j=</g> 之后的第一个字符)
    ref = ref_of(zh)
    bd = B.badges_data()[ref]
    vb = [float(v) for v in re.search(r'viewBox="([^"]*)"', s).group(1).split()]

    kids = re.findall(r'<g\b.*?</g>', inner)
    heads, chips = [], []
    for k in kids:
        db = re.search(r'data-box="([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)"', k)
        if not db:
            continue
        x0, y0, x1, y1 = (float(db.group(i)) for i in range(1, 5))
        if 'data-badge="header"' in k:
            heads.append((x0, y0))                 # 胶囊与旧胶囊同尺寸, 锚点即原位
        elif 'data-badge="chip"' in k or (x1 - x0) < 40:
            chips.append(((x0 + x1) / 2, (y0 + y1) / 2))
        else:                                      # 旧版胶囊(rect 80x43 或 0.6 缩放组)
            tr = re.search(r'translate\(([-\d.]+)[ ,]([-\d.]+)\)(?:\s*scale\(([\d.]+)\))?', k)
            if tr and tr.group(3):
                chips.append((float(tr.group(1)), float(tr.group(2))))
            else:
                heads.append((x0, y0))
    if not heads:
        return zh, False, '未识别出徽标'
    color = re.search(r'<g id="走廊">.*?stroke:(#[0-9A-Fa-f]{6})', s, re.S).group(1).upper()

    def build(c=None):
        """头部=官方胶囊(旧位)。终点=数字块, 一律按三点一线规范重钉:
        终点圆→本站标签中心射线, 越过文字远端+chip半宽+6 (1号线定稿规范);
        理想位碰撞/出框时回退环搜。"""
        from verify_card import rect_seg_clearance
        import math as _m
        parts = []
        head_boxes = []
        for (hx, hy) in heads:
            pw, ph, _ = B.badge_full_size(ref)
            g = B.make_badge_official(ref, color, hx, hy, 1.0, 'full')
            head_boxes.append((hx, hy, hx + pw, hy + ph))
            parts.append(g)
        for (cx, cy) in chips:
            cw = bd['chip']['w']; ch = bd['chip']['h']
            def _hit(bb):
                if any(not (bb[2] < h[0] or h[2] < bb[0] or bb[3] < h[1] or h[3] < bb[1]) for h in head_boxes):
                    return True
                if c is not None:
                    for lb in c['labels']:
                        lbb = lb['box']
                        if not (bb[2] < lbb[0] or lbb[2] < bb[0] or bb[3] < lbb[1] or lbb[3] < bb[1]):
                            return True
                    if rect_seg_clearance(*bb, c['segs']) < 4.0:
                        return True
                return False
            cands = []
            if c is not None:
                # 三点一线锚=本端走廊尖端(度=1 端点, 即终点圆位; 中间站关节度>=2 被排除)
                from collections import Counter
                cnt = Counter()
                for sg in c['segs']:
                    for e in ((round(sg[0], 1), round(sg[1], 1)), (round(sg[2], 1), round(sg[3], 1))):
                        cnt[e] += 1
                tips = [e for e, n in cnt.items() if n == 1] or list(cnt)
                pt = min(tips, key=lambda t: _m.hypot(t[0]-cx, t[1]-cy))
                lb = min(c['labels'], key=lambda t: _m.hypot((t['box'][0]+t['box'][2])/2-pt[0], (t['box'][1]+t['box'][3])/2-pt[1]))
                ux, uy = (lb['box'][0]+lb['box'][2])/2-pt[0], (lb['box'][1]+lb['box'][3])/2-pt[1]
                du = _m.hypot(ux, uy) or 1.0
                ux, uy = ux/du, uy/du
                far = max((px_-pt[0])*ux + (py_-pt[1])*uy for px_ in (lb['box'][0], lb['box'][2]) for py_ in (lb['box'][1], lb['box'][3]))
                ext = far + cw/2 + 6
                cands.append((pt[0]+ux*ext, pt[1]+uy*ext))            # 三点一线理想位
                cands.append((pt[0]+ux*(far+cw/2+14), pt[1]+uy*(far+cw/2+14)))
            cands.append((cx, cy))                                    # 现位兜底
            for r0 in (14, 24, 36, 50):
                for ang in range(0, 360, 30):
                    cands.append((cx + r0 * _m.cos(_m.radians(ang)), cy + r0 * _m.sin(_m.radians(ang))))
            for (nx, ny) in cands:
                nb = (nx - cw/2, ny - ch/2, nx + cw/2, ny + ch/2)
                if nb[0] < vb[0]+4 or nb[2] > vb[0]+vb[2]-4 or nb[1] < vb[1]+4 or nb[3] > vb[1]+vb[3]-4:
                    continue
                if not _hit(nb):
                    g = B.make_badge_official(ref, color, nx, ny, 1.0, 'chip')
                    break
            else:
                g = B.make_badge_official(ref, color, cx, cy, 1.0, 'chip')
            parts.append(g)
        return parts

    if apply:
        from verify_card import load as _vc_load
        _c = _vc_load(path)  # 现卡标签/走廊(换徽标不动几何, 可直接用作碰撞真值)
        def _strip(el):
            for e in el.iter():
                if isinstance(e.tag, str) and e.tag.startswith('{'):
                    e.tag = e.tag.split('}', 1)[1]
            return el
        new_inner = ''.join(ET.tostring(_strip(p), encoding='unicode') for p in build(_c))
        open(path, 'w', encoding='utf-8').write(s[:start] + new_inner + s[j-4:])
        R = run_gates(path, chains=G._chains_for(zh))
        fails = ['%s:%s' % (no, dt) for no, nm, ok, dt in R if not ok]
        tag = '换徽标 头%d+终%d' % (len(heads), len(chips))
        return zh, not fails, tag + (' 门禁%d/%d %s' % (sum(o for _, _, o, _ in R), len(R), '; '.join(fails) if fails else '全过'))
    return zh, True, '试算 头%d+终%d' % (len(heads), len(chips))


if __name__ == '__main__':
    names = sys.argv[1:] or LINES
    bad = 0
    for zh in names:
        zh, ok, msg = swap_card(zh)
        print('%-6s %s %s' % (zh, '✓' if ok else '✗', msg))
        bad += 0 if ok else 1
    sys.exit(1 if bad else 0)
