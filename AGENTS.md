# 广州地铁线网图工程纪律（每次会话必读, 违者返工）

## 1. 禁用 heredoc 内联 python（用户明令, 已四次违纪）
- 任何 Bash 命令含 `<<` 一律不发。多行 python → Write 落盘 `tools/_tmp-*.py` → 运行；改代码只用 Edit/Write 工具。
- 原因: 命令串经多层传输, 反斜杠序列必被吃（`\1`→`\x01` 静默写坏文件、`\\`→`\`、`\\n`→真实换行）。自我合理化"这个小补丁很简单"=违纪信号, 出现即停。
- 落盘脚本先 `python -m py_compile` 再跑。

## 2. 管道截断雷
- `python 生成器.py | head -N` 会 SIGPIPE 杀掉生成器——SVG 没写盘, 后续门禁读陈旧文件。跑生成器一律 `> 文件 2>&1` 后再 tail；`| grep` 安全。

## 3. 提交前全量验证链（pre-commit 钩子强制, 不许挑门禁）
- `python tools/verify-all.py --quick`：verify-codes-cards(V1–V7, 含V5文字压胶囊) + verify-badges-pixel(徽标穿透) + 幂等md5。
- **任何锚表数据编辑**（`data/codes-final-pins.json` 的 labels_inner / network_badge_anchors / badges）后必须跑全量——文字与徽标流入两层, 不许按"看起来只改了X"筛选门禁（2026-10-24 事故: 改文字未跑V5, 文字压编号胶囊入库被用户抓）。
- 钩子不过 = 修复后重试; `--no-verify` 仅限用户明示。

## 4. 规则与位置必须互相匹配
- 已验收位置若被规则判违规 → 迭代规则阈值本身, **禁止白名单/免疫豁免**（用户明令）。
- 校准基准 = 验收态的客观口径（如徽标-走廊净距6.5=描边3.5+像素门禁3px外扫）。

## 5. 用户点名微调走锚表链路
- 点名改文字/徽标位置 → 改 `data/codes-final-pins.json` 对应锚 → 重跑生成器（规则自动带联动元件跟位）→ **跑全量验证链** → 渲染 codes 终稿亲自核验重叠 → 汇报数字。
