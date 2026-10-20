# -*- coding: utf-8 -*-
"""改动证明器: 防"声称修了但产物完全没变"(2026-10-20 用户令杜绝, 本次连出多起)。
对目标文件记 before 哈希(可选: 卡片渲染成 PNG), 执行命令, 记 after, 按预期断言变/不变。
渲染对比输出差异像素数+变化区外接框, 可存 diff 高亮图 —— 即"截图对比"的机械化。

用法:
  # 预期卡片变(渲染级对比): 变了才过, 没变=命令失败
  python tools/prove_change.py --expect changed --render assets/lines/line-12号线.svg -- python tools/line12-both.py
  # 预期不变(仅文件哈希):
  python tools/prove_change.py --expect same --watch data/badges-official.json -- python tools/xxx.py
  # --diff-out data/_diff.png 存前后渲染差异高亮图
"""
import argparse
import hashlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()[:16]


def render_png(svg):
    from verify_card_pixel import render
    im, _ = render(svg)
    return im


def diff_stats(a, b, tol=10):
    mask = (abs(a - b) > tol).any(axis=2)
    n = int(mask.sum())
    if n == 0:
        return 0, None, mask
    ys, xs = mask.nonzero()
    return n, (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())), mask


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--expect', choices=['changed', 'same'], required=True)
    ap.add_argument('--render', help='SVG 卡片: 前后各渲染一次做像素对比')
    ap.add_argument('--watch', action='append', default=[], help='跟踪哈希的文件(可多个)')
    ap.add_argument('--diff-out', help='差异高亮图输出路径')
    ap.add_argument('cmd', nargs='+', help='-- 之后的被检命令')
    a = ap.parse_args()

    before_h = {p: sha(p) for p in a.watch if os.path.exists(p)}
    before_px = render_png(a.render) if a.render else None

    r = subprocess.run(a.cmd, cwd=ROOT)
    if r.returncode != 0:
        print('PROVE-FAIL: 命令本身失败 rc=%d' % r.returncode)
        return 2

    fails = []
    detail = []
    for p in a.watch:
        after = sha(p) if os.path.exists(p) else '(缺失)'
        was = before_h.get(p, '(原本缺失)')
        changed = after != was
        detail.append('%s: %s → %s' % (os.path.relpath(p, ROOT), was, after))
        if a.expect == 'changed' and not changed:
            fails.append('%s 预期变化但哈希未变' % os.path.relpath(p, ROOT))
        if a.expect == 'same' and changed:
            fails.append('%s 预期不变但哈希变了' % os.path.relpath(p, ROOT))

    if before_px is not None:
        after_px = render_png(a.render)
        if after_px.shape != before_px.shape:
            fails.append('渲染尺寸变了 %s → %s' % (before_px.shape, after_px.shape))
        else:
            n, bbox, mask = diff_stats(before_px, after_px)
            detail.append('渲染差异像素 %d%s' % (n, (' 外接框 %s' % (bbox,)) if bbox else ''))
            if a.expect == 'changed' and n < 50:
                fails.append('预期有变化但渲染逐像素相同(%dpx) — 修改没生效或没被执行' % n)
            if a.expect == 'same' and n > 0:
                fails.append('预期不变但渲染差异 %dpx, 外接框 %s' % (n, bbox))
            if a.diff_out and n > 0:
                import numpy as np
                from PIL import Image
                hl = after_px.astype('uint8').copy()
                hl[mask] = [255, 0, 0]
                Image.fromarray(hl).save(a.diff_out)
                detail.append('diff图 → %s' % a.diff_out)

    print('PROVE %s' % ('PASS' if not fails else 'FAIL'))
    for d in detail:
        print('  ' + d)
    for f in fails:
        print('  ✗ ' + f)
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
