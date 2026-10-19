# -*- coding: utf-8 -*-
"""单线卡片回归测试：不需要网络，像素层用无头Edge本地渲染。

跑法(仓库根):
    python -m pytest tests -q
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, 'tools')
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

LINE2 = os.path.join(ROOT, 'assets', 'lines', 'line-2号线.svg')


def pytest_sessionfinish(session, exitstatus):
    """跑完顺手清掉 pytest 缓存与像素门禁临时目录，不留垃圾。"""
    for d in (os.path.join(ROOT, '.pytest_cache'),
              os.path.join(ROOT, 'tests', '.pytest_cache'),
              os.path.join(ROOT, 'assets', 'lines', '_pixtmp')):
        shutil.rmtree(d, ignore_errors=True)
