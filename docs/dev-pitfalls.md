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

## 2.（待沉淀）
新雷区按同格式追加。
