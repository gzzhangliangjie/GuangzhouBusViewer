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
- 解析/定位/校验一律走 `gen.badge_elements()` 的 `(线名, 终点站名)` 键（badge_text_to_line 线名归一），**禁止对裸 transform 串做文档序断言**。
- ⚠️锚定**值的存储/同步** = 自锚定架构（2026-10-25 用户定稿"SVG 本身即锚表"）：徽标锚 = 上一版 codes SVG 按 **(线名, 终点站名) 键配对**（新增终点无锚走算法位并提示, 键重复硬报错, 无文档序）；编号牌 chips 位移增量仍按文档序 + 数量硬报错（牌无廉价身份标识, 唯一残余文档序通道）。

## 1.7 SVG 数据提取必须走 gen 共享接口（禁止自行写解析正则）
- 所有需要读取 SVG 徽标/文字/胶囊/走廊信息的脚本，必须调用 `gen.badge_elements()` / `gen.text_elements()` / `gen.chip_elements()` / `gen.corridor_segments()` / `gen.marker_elements()` / `gen.ring_elements()` / `gen.corridor_colors()`（后三者为共享接口增量：站圆+胶囊标记 / 圈环带 data-ring 身份 / 走廊色分布）。
- **一次性脚本（`_*` 前缀）同样适用**——写新脚本时 import gen 用共享接口，禁止复制粘贴旧正则。
- 原因：每个绕过共享接口的脚本都自带一套正则假设（属性顺序、精度格式、坐标含义），一次不匹配就静默出错。已发生：`_norm-closed` 群体偏移、`_spread-4` 精度不匹配、`_gap-fix` 函数签名错乱。
- **下游消费链（2026-10-26）**：`data/quiz-network-data.js`（地铁拼图官方棋盘配对数据）由 `tools/gen-quiz-data.py` 从产品图生成——318 站名双射 + 400 牌**按牌面解码配对**（隔线色+线号字+序号字是绘制端按 (站,线) 画入的权威身份，解码后经 CSV 唯一反查；钉位只做别名消歧与漂移报告。~~就近钉位指派~~已废弃：钉位与落位在多牌站错位时整站身份互换，曾致 63 枚/32 站错配、单线模式亮灰胶囊看似随机）+ 圈环逐枚对齐，校验不过即拒绝写出；**改 network SVG / 编号 CSV 后必须重跑**，否则 App 端 `metro-board.js` 装载时按坐标对不上 DOM 会 fail-loud 拒绝渲染。
- **拼图单线展示口径（2026-10-26 用户令）**：单条线路 scope 下数字胶囊一律"本线亮、他线灰"——站名/线号/挑战模式 400 牌全作背景按线亮灰。编号模式已移除（2026-10-27 用户令：编号按顺序填意义不大；牌数据保留——胶囊形式站旁标注与放弃揭示注入仍用）。断言在 verify-official-board ⑩（体育西路 1|14 亮/3|11 灰为牌面配对回归哨兵）。**徽标同口径（2026-10-27）**：hidePieces 对他线徽标只淡化不收槽（旧实现全线收槽→单线线号模式出现 18 个永远填不上的空槽），哨兵 ⑫开局槽=本线终点枚数/池=1。
- **线号模式多槽位+无色起步（2026-10-27 用户令）**：每枚终点徽标独立槽位，槽键=`线名|终点`（data-term，同键重复报错；11号线环线 1 枚/12 号线分段 4 枚/3、14 号线含支线 3 枚/其余 2 枚，全网 41 槽 19 牌）；判定按线名部分比较，任意一枚放对→同线其余槽位自动补齐、整线原位上色（+100 落在放入处）。开局填写框默认黑框（浅色线框白底看不清，颜色留作"已填对"信号）、线号牌池胶囊默认灰色不带线色（防颜色泄露线路归属）。断言 ⑤（双槽/黑框/灰胶囊/放一枚整线补齐）+⑫。
- **定位未填写（2026-10-27 用户令）**：官方棋盘局内"定位未填写"按钮 → `MetroBoard.unfilledList()/focusUnfilled()`（目标=站名热区∪徽标/编号牌槽位，放置即移除天然只剩未填）聚焦居中+CSS 闪烁三连（`.mb-blink`，只放大不缩小，FOCUS_ZOOM=0）；quiz 层洗牌袋（棋面一变重洗+避开上次）保证连点尽量不重复。断言 verify-official-board ⑪（连点318次去重318/318）+⑫。

## 2. 管道截断雷
- `python 生成器.py | head -N` 会 SIGPIPE 杀掉生成器——SVG 没写盘, 后续门禁读陈旧文件。跑生成器一律 `> 文件 2>&1` 后再 tail；`| grep` 安全。

## 3. 验证与提交纪律（pre-commit 钩子强制）
- 迭代期单站调整: 改 codes SVG（SVG 即锚表）→ `python tools/sync-base.py` → `python tools/verify-station.py 站名` 局部验证（秒级）。批量归一工具（normalize-*.py）跑完仍须全量。
- **提交=人肉确认动作（2026-10-25 用户定稿）**: agent 不得自主 `git commit`，用户确认后才执行。pre-commit 全绿自动 `baseline-lock.py accept` 并随提交入库——**基线=最后一次经用户确认的全绿提交**；verify-all 的基线检查只报告漂移不拦截。
- 提交分级门禁（pre-commit 按 staged 内容分级, `tools/precommit-gate.py`）: **T1** 纯文档（*.md, docs/）放行; **T2** 产物/数据（assets/**, data/*.json）或生成器链（build-network/gen-codes-cards/sync-base）→ verify-all 全量（生成器链变更升级非 quick：重跑链+幂等，重跑输出与 staged 不一致=拒绝——产物必须随生成器变更同 commit 入库）+ accept 基线; **T3** 纯脚本 → 工具自测（`tools/selftest.py`: gen共享接口单元+产物数字金丝+快照沙箱）+ XML/基线快检。钩子不过=修复后重试; `--no-verify` 仅限用户明示。
- ⚠️钩子文件已入库: `tools/hooks/pre-commit`（`.git/hooks/` 不受 git 版本保护）。**克隆或换机后必须安装**: `cp tools/hooks/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit`——不装=全部门禁静默失效。
- **产物数字金丝**（selftest.py, 定稿冻结值: 41徽标/318文字/400牌/16胶囊/302圆/scale统一0.314/transform无链）随定稿变更须有意识更新——与基线 accept 同理, 不许静默漂移。
- **每批提交前过"三文档同步"（2026-10-26 用户令, 防废弃用例复发）**: ①selftest 金丝数字 ②AGENTS.md 条文 ③docs/network-map-spec.md——逐条对照本批改动, 冲突即改; 规范正文只写现行规则, 过期判例移"大坑档案"或标注历史。
- **测试体系终版（2026-10-26）**: 唯一测试执行器 = `tools/selftest.py`（A.gen共享接口单元 / B.产物数字金丝 / C.快照沙箱 / D.基线锁突变自检——污染沙箱断言门禁必然翻红, 防假绿）; 产物验收不用测试框架, 由 verify-all+基线锁承担（比逐用例断言更严）。旧 pytest 套件已删除（单线卡时代过期锚, 思想已移植 selftest）, **模块被 import 时禁再包 sys.stdout**（重复包装会关底层流, rewrap 只放 `__main__`）。

## 4. 规则与位置必须互相匹配
- 已验收位置若被规则判违规 → 迭代规则阈值本身, **禁止白名单/免疫豁免**（用户明令）。
- 校准基准 = 验收态的客观口径（如徽标-走廊净距6.5=描边3.5+像素门禁3px外扫）。

## 5. 用户点名微调走自锚定链路
- 点名改文字/徽标位置 → 文字用 `tools/move-label.py 站名 方向`，徽标用 `tools/move-badge.py 终点站名 方向 [线号] [--dry]`（同终点多枚用线号消歧；也可直改 codes SVG 对应元素——SVG 即锚表，重跑自动沿用；量净距一律走 gen 接口禁手算）→ `sync-base.py` → `verify-station.py 站名` 局部验证 → 渲染核验 → 汇报数字 → **用户确认后提交**（pre-commit 自动全量+accept基线）。
- ⚠️ 两份 SVG 的还原**禁用 `git checkout`**（autocrlf 改写换行致 md5 漂移、基线假告警，还会回退未提交工作）。还原优先级: ①重跑生成器链 build→gen→gen→sync（幂等，形态真源）②`python tools/svg-snapshot.py restore`（字节级快照; move-badge/move-label 写盘前自动 save 一版，试验性改动随时可回滚）。
