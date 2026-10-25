# 广州地铁线网图工程纪律（每次会话必读, 违者返工）

## 1. 禁用 heredoc 内联 python（用户明令, 已四次违纪）
- 任何 Bash 命令含 `<<` 一律不发。多行 python → Write 落盘 `tools/_tmp-*.py` → 运行；改代码只用 Edit/Write 工具。
- 原因: 命令串经多层传输, 反斜杠序列必被吃（`\1`→`\x01` 静默写坏文件、`\\`→`\`、`\\n`→真实换行）。自我合理化"这个小补丁很简单"=违纪信号, 出现即停。
- 落盘脚本先 `python -m py_compile` 再跑。

## 1.5 坐标输出精度统一两位小数
- SVG 内所有坐标值（translate/transform/text x/y/rect 等）**必须格式化为 `%.2f`**（两位小数）。
- 原因: 不同代码路径用了 `%.1f`/`%g`/原值透传, 产出 `548.6` vs `548.60` 混杂; 字符串替换时 `548.6` 匹配不上 `548.60` 导致修改静默失败。
- 修改坐标时用**数值正则匹配**（`re` + `float()` 比较），不使用精确字符串匹配。

## 1.6 徽标 data-term 属性全链贯通
- `build-network.py` 徽标输出必须携带 `data-term="终点站名"`；`gen-codes-cards.py` codes SVG 徽标同样携带。
- 锚定/归一化脚本以 `(线名, 终点站名)` 为锚定键（data-term + badge_text_to_line 线名归一），**禁止文档序匹配**（顺序无关，增删不错位）。

## 1.7 SVG 数据提取必须走 gen 共享接口（禁止自行写解析正则）
- 所有需要读取 SVG 徽标/文字/胶囊/走廊信息的脚本，必须调用 `gen.badge_elements()` / `gen.text_elements()` / `gen.chip_elements()` / `gen.corridor_segments()`。
- **一次性脚本（`_*` 前缀）同样适用**——写新脚本时 import gen 用共享接口，禁止复制粘贴旧正则。
- 原因：每个绕过共享接口的脚本都自带一套正则假设（属性顺序、精度格式、坐标含义），一次不匹配就静默出错。已发生：`_norm-closed` 群体偏移、`_spread-4` 精度不匹配、`_gap-fix` 函数签名错乱。

## 2. 管道截断雷
- `python 生成器.py | head -N` 会 SIGPIPE 杀掉生成器——SVG 没写盘, 后续门禁读陈旧文件。跑生成器一律 `> 文件 2>&1` 后再 tail；`| grep` 安全。

## 3. 验证与提交纪律（pre-commit 钩子强制）
- 迭代期单站调整: 改 codes SVG（SVG 即锚表）→ `python tools/sync-base.py` → `python tools/verify-station.py 站名` 局部验证（秒级）。批量归一工具（normalize-*.py）跑完仍须全量。
- **提交=人肉确认动作（2026-10-25 用户定稿）**: agent 不得自主 `git commit`，用户确认后才执行。pre-commit 全绿自动 `baseline-lock.py accept` 并随提交入库——**基线=最后一次经用户确认的全绿提交**；verify-all 的基线检查只报告漂移不拦截。
- 提交时 pre-commit 强制 `python tools/verify-all.py --quick` 全量（V1–V7 + V8徽标不压文字 + 像素四边扫描 + 幂等md5），不许挑门禁；钩子不过 = 修复后重试; `--no-verify` 仅限用户明示。

## 4. 规则与位置必须互相匹配
- 已验收位置若被规则判违规 → 迭代规则阈值本身, **禁止白名单/免疫豁免**（用户明令）。
- 校准基准 = 验收态的客观口径（如徽标-走廊净距6.5=描边3.5+像素门禁3px外扫）。

## 5. 用户点名微调走自锚定链路
- 点名改文字/徽标位置 → 文字用 `tools/move-label.py 站名 方向`（或直接改 codes SVG 对应元素），徽标直接改 codes SVG transform（SVG 即锚表，重跑自动沿用；量净距用 gen.text_box/badge_elements 禁手算）→ `sync-base.py` → `verify-station.py 站名` 局部验证 → 渲染核验 → 汇报数字 → **用户确认后提交**（pre-commit 自动全量+accept基线）。
