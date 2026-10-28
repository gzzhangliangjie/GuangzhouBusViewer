# 工程雷区手册（工具链层）

> 沉淀跨任务的工程实践铁律。与 `docs/card-acceptance.md`（验收层）平行：那篇管"怎么判定能不能交付"，本篇管"怎么干才不出工程事故"。
> 每条都来自真实事故，附症状与杜绝手段。新条目按"症状 → 根因 → 铁律 → 自检"四段写。

## 1. heredoc 转义吃反斜杠（2026-10-21 两次连炸）

### 症状
- **内联脚本体被吃**：`python - <<'EOF'` 里写 `hp.replace('\\', '/')`，落进解释器的变成 `replace('\', '/')` → `SyntaxError: unterminated string literal`。
- **用 heredoc 生成脚本被吃**：通过 heredoc 内联 python 往 `.py` 文件里写字符串 `'\\n    '`（想要字面量 `\n`），生成文件里变成真实换行 → 生成的脚本自身 `SyntaxError: line 37`。
- 两次都发生在 Git Bash + `python - <<'EOF'`（引号 EOF，本应禁变量展开）。

### 根因
命令串经过 工具调用 → harness → Git Bash → heredoc 多层传输，**上游层的转义处理会在引号 EOF 之前吃掉一级反斜杠**；引号 EOF 只能防 shell 的变量/命令展开，防不了更前面的层。结论：heredoc 体内的反斜杠**不可信**，与引号写法无关。

### 铁律（按优先级，1=唯一可靠通道）
1. **内联 python 一律禁止**。要跑多行逻辑：先用 Write 工具落盘 `tools/_tmp-*.py` → `python tools/_tmp-xxx.py` 运行 → 用完删除。不经过 shell 传输代码体，问题根除。
2. **改代码文件（.py/.js/.html/.svg）必须用 Edit/Write 工具**，绝不用 `heredoc + sed/python` 生成或修补代码——生成体里的转义无法保证。
3. 确实只想要一条一行小命令时，内容必须**零反斜杠**：正则用字符类 `[/]` 代替 `\/`、路径一律正斜杠、不写 `\n` `\t` `\\`（要换行处用 `os.linesep` 或分次命令）。
4. **落盘脚本运行前先语法自检**：`python -m py_compile <file>`，SyntaxError 当场修，不带病推进（"生成即坏"只有这一道闸）。

### 自检
- 任何 `<<'EOF'` 出现在命令里且体内容含 `\`：停下来，改走 Write 落盘。
- 刚生成的脚本：先 `py_compile` 再执行。
- 报 `SyntaxError: unterminated string literal` 且行号指向字符串：第一时间怀疑传输被吃，不要怀疑自己代码。

## 2. Overpass 镜像"时通时断"：单轮竞速一轮全败=功能跪（2026-10-29 道路查看事故）

### 症状
- 道路查看每次搜索都报"所有 Overpass 镜像均失败（Failed to fetch）"，但公交侧历史数据明明拉到过。
- 逐镜像探测（Electron fetch 栈、真实 POST 查询）：`maps.mail.ru` 第一次 504、几秒后重试 200 返回 162 个路段；`overpass-api.de` 406/502（本机网络拦）；`overpass.kumi.systems` / `overpass.private.coffee` 对空 UA 返回 429"请带有意义的 User-Agent"；`openstreetmap.ru` 已死。

### 根因
1. **镜像过载是常态不是故障**：同一镜像连续两次请求一败一成（504 后 15s 内 200），失败是瞬时挤爆。旧 `runQuery` 只竞速一轮，一轮全败即抛错——对"时通时断"的镜像群，单轮全败概率极高。
2. **渲染进程 fetch 不能自定义 User-Agent**（浏览器 forbidden header，session 级才可设）；Electron 主进程的 Node fetch 默认不带 UA，kumi/private.coffee 直接 429。App 实际走渲染进程（自带完整 Chromium UA），此项不影响线上，但写探针脚本时必须显式带 UA，否则测出来全是 429 假象。

### 铁律
1. 对时通时断的数据源，**竞速必须配多轮重试**（现行 `runQuery` rounds=3，轮间 1.5s，镜像健康记忆跨轮生效），单轮失败就向用户报错=把镜像抖动变成功能不可用。
2. 探测 Overpass 用 Electron 主进程脚本时**必须带浏览器 UA**，不带 UA 的 429 结果作废。
3. 镜像探测要打**真实 POST 查询**，GET 空查询的 406/429 与真实行为不一致。
4. 慢源查询必须给用户**进度反馈**（"第 n 轮"），60-90s 无反馈的等待=用户以为跪了。

### 自检
- 改动 `runQuery`/数据层后：用真实查询逐镜像跑一轮探测，不许只看代码。
- 新增联网功能：先确认"全部镜像都抖"时的行为——应重试并报轮次，而不是一次性报错。

## 3. Leaflet 地图容器 0×0 尺寸残留：瓦片只铺一角（2026-10-29 道路查看）

### 症状
- 搜索出结果后地图瓦片只覆盖视口一部分，四周灰底，路名画到灰底上；手动触发 `window.dispatchEvent(new Event('resize'))` 后自动恢复。

### 根因
打点实测（包一层 `invalidateSize` 记录尺寸）：`fitBounds` 时容器尺寸是对的（980x674），但面板隐藏/切回瞬间容器会变 **0×0**——Leaflet 在 0 尺寸下收缩视图，再展开时瓦片层不会自动按新尺寸重铺。只靠 `show()` 里一次 `invalidateSize()` 盖不住所有尺寸变化路径。

### 铁律
1. Leaflet 地图挂在**会隐藏/切换的容器**上时，必须挂 `ResizeObserver` 对容器 `invalidateSize({animate:false})`（现行 roads.js `ensureMap`），单次延迟 invalidateSize 不可靠。
2. 排查"瓦片只铺一角"类问题：先给 `L.Map.prototype.invalidateSize` 打点记录 `map.getSize()` vs `container.clientWidth`，看 fitBounds 时刻的尺寸再下结论，不猜。

### 自检
- 改地图初始化/视图切换后：重载页面→切视图→搜索→截图，确认瓦片满幅且无手动 resize。

## 4.（待沉淀）
新雷区按同格式追加。
