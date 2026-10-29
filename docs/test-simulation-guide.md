# 测试模拟手法手册（Electron 验收脚本层）

> 沉淀本项目自动化测试的模拟手法：怎么拉起真实 App、怎么模拟用户点击/输入/拖拽、怎么拿程序化证据。
> 与 `docs/dev-pitfalls.md`（工程雷区）平行：那篇管"怎么干不出事故"，本篇管"怎么测才不作假"。
> 每种手法都注明适用场景与背后的"为什么"——多数限制来自真实假绿事故，不是风格偏好。

## 0. 体系总览：没有测试框架，只有三层门禁 + 一堆可独立执行的验收脚本

本项目**不用任何通用测试框架**（pytest 套件已删，JS 侧无 jest/mocha）。替代物是一套自建体系：

| 层 | 执行器 | 管什么 | 速度 |
|---|---|---|---|
| 工具自测 | `tools/selftest.py` | gen 共享接口单元 + 产物数字金丝 + 沙箱回环 + 门禁突变自检 | 秒级 |
| 产物验收 | `tools/verify-all.py` | SVG 产物全链：XML→分组结构→锚契约→重跑幂等→V1-V7→像素门禁 | 分钟级 |
| 提交门禁 | `tools/hooks/pre-commit` → `precommit-gate.py` | 按 staged 内容分级 T1/T2/T3，产物提交强制全量+accept 基线 | 随提交 |
| App 功能验收 | `test/verify-*.js`（Electron 独立脚本） | 真实拉起 App、真实驱动交互、断言+截图 | 每功能一个 |

**核心哲学：渲染验收必须程序化。** 点击是模拟的（或 CDP 注入的），但证据必须是回读出来的程序化状态——游戏分数、DOM 属性、canvas 像素采样、md5——vision 看图不算通过依据，"看起来对"不算对。

## 1. Electron 验收脚本骨架（所有 verify-*.js 的通用底座）

```js
const { app, BrowserWindow } = require('electron');
app.disableHardwareAcceleration();                       // 渲染确定性, 免 GPU 抖动
app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
app.setPath('userData', path.join(__dirname, '..', '.tmp-userdata-xxx'));  // 隔离!
                                                          // 绝不碰用户正在跑的实例
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1400, height: 900, show: true,  // 必须可见
    webPreferences: { preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true,
      backgroundThrottling: false } });                   // 后台节流会让 capturePage 返回陈旧帧
  await win.loadFile('index.html');
  const exec = js => win.webContents.executeJavaScript(js);  // 注入一切模拟与回读
  // ... 驱动 → 断言 → 截图 → app.exit(通过?0:非0)
});
```

用法：`./node_modules/.bin/electron test/verify-xxx.js`，退出码即通过与否。

四条铁律（每条都有事故判例）：

1. **userData 必须隔离**——测试实例与用户实例共用 userData 会互踩缓存/锁，且绝不 taskkill 用户进程。
2. **窗口必须 `show: true`**——capturePage 对隐藏窗口截出空白。
3. **`backgroundThrottling: false`**——否则 capturePage 拿到的是陈旧帧。
4. **console 报错全量收集**——`win.webContents.on('console-message')` 收集 level≥2，作为独立断言（注意过滤测试脚本自己 getImageData 触发的 willReadFrequently 性能提示）。

## 2. 点击模拟三层级（按真实程度递进）

选型的唯一标准：**被测交互是否经过浏览器的内置判定门**。不过门的用合成事件（快、稳），过门的必须 CDP 真实输入。

### 层级 1：DOM 合成事件 —— 测 UI 逻辑的默认手法

绝大多数验收脚本用这个。主进程通过 `executeJavaScript` 往页面注入，三种形态：

**a) 直接 `.click()`** —— 按钮/卡片/药丸等普通元素：

```js
await exec(`document.querySelector('#mode-nav [data-mode="route"]').click()`);
await exec(`document.querySelector('#scope-picker .scope-pill[data-v="1"]').click()`);
```

**b) 赋值 + 手动派发事件链** —— 表单/联想输入框（程序赋值不触发 input 事件，必须手动发）：

```js
// 路线规划起终点: 填入 → 联想 → 回车确认 (test/verify-route.js)
from.value = '体育西路';
from.dispatchEvent(new Event('input', { bubbles: true }));         // 触发联想
from.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter',
  bubbles: true, cancelable: true }));                              // 选中确认
```

**c) Leaflet 热区走 `.fire()`，不走 DOM** —— 地图上的点击监听的是 Leaflet 内部封装的事件，等价于用户点一下：

```js
// 拼图选站 (test/verify-official-board.js)
hot.get('西塱').fire('click');
```

适用：按钮、表单、地图选站、tab 切换、pill 多选——一切"点了之后走应用自身 JS 逻辑"的交互。

### 层级 2：CDP 真实输入链 —— 拖拽专用（合成事件测出来是假绿）

**事故判例（2026-10-27）**：用户报"判定圆圈亮了却放不进"。项目规则是"容器 dragover 圈亮（preventDefault）才允许 drop"——浏览器对未被 preventDefault 的 dragover 判 no-drop、松手不派发 drop。而合成 `dispatchEvent(new DragEvent('drop'))` 是**直派发，绕过这道门**，测试全绿但真用户拖不进去。结论：凡依赖浏览器拖拽状态机的交互，合成事件=假绿，必须走真实链。

`test/verify-official-dnd-real.js` 的完整配方（Puppeteer 同款 intercept 模式）：

```js
const dbg = win.webContents.debugger;
await dbg.attach('1.1');

// ① 拦截 HTML5 拖拽, 启用 dragIntercepted 事件
await dbg.sendCommand('Input.setInterceptDrags', { enabled: true });

// ② 真实鼠标按下牌池名牌 → 分步移动(按住) → 页面自己触发 dragstart
//    拖拽数据是页面自己 setData 的, 测试不伪造 DataTransfer
await dbg.sendCommand('Input.dispatchMouseEvent',
  { type: 'mousePressed', x, y, button: 'left', buttons: 1, clickCount: 1 });
await mv(x + 6, y + 6, 1);   // mouseMoved 带 buttons:1 = 按住移动
await mv(x + 14, y + 10, 1);

// ③ 等 Input.dragIntercepted 送来真实拖拽数据
let dragData = null;
dbg.on('message', (_e, method, params) => {          // Electron 只走统一 'message'
  if (method === 'Input.dragIntercepted') dragData = params && params.data;
});
for (let i = 0; i < 20 && !dragData; i++) await sleep(50);

// ④ 用真实数据走 dragEnter / dragOver(真实事件, 可被页面 preventDefault 取消)
await dbg.sendCommand('Input.dispatchDragEvent', { type: 'dragEnter', x, y, data: dragData });
await dbg.sendCommand('Input.dispatchDragEvent', { type: 'dragOver',  x, y, data: dragData });

// ⑤ 真实松手: 由 dragover 是否被取消决定 drop 是否派发
await dbg.sendCommand('Input.dispatchDragEvent', { type: 'drop', x, y, data: dragData });
// 兜底: drop 没生效时补发真实 mouseReleased 再试
if (fin.drop === 0) await dbg.sendCommand('Input.dispatchMouseEvent',
  { type: 'mouseReleased', x, y, button: 'left', buttons: 1, clickCount: 1 });
```

配方要点：

- **坐标取真值**：拖起点 = 牌池名牌 `getBoundingClientRect()` 的中心；落点 = 棋盘容器坐标换算。不拍脑袋。
- **三场景覆盖判定门的三个分支**：A 本线站圈亮→可放→+100；B 他线淡化站圈不亮→零响应；C 空白区圈不亮→no-drop 光标。合成事件只能测 A，测不出 B/C 的门行为。
- **debugger 事件只走 `dbg.on('message')`**——Electron 无按方法名分发，别找 `dbg.on('dragIntercepted')`。
- 探针监听器挂在被测监听器**之后**注册，其回调里读 `e.defaultPrevented` 即可反映被测方是否取消了 dragover。

### 层级 3：证据回读闭环 —— 不管哪种点击都必须做

模拟只是手段，通过与否由回读的程序化证据决定，四路并行：

| 证据类型 | 手法 | 判例 |
|---|---|---|
| 应用状态 | 回读 `MetroQuiz.__game()` 的 score/placedNames | 放对牌 +100、牌池数量 -1 |
| DOM 状态 | 回读元素属性（`fill-opacity`、槽位、类名） | 他线站 `fill-opacity==='0.2'` 淡化 |
| canvas 像素 | `getImageData` 全量采样非透明像素数 | 路线画没画出来 = 墨迹 >50 点（`verify-route.js`），数墨迹不数绘制调用 |
| 截图留档 | `win.webContents.invalidate()` + `await capturePage()` → toPNG | `assets/_v-*.png`，供人肉复核 |

注意：canvas 断言断**墨迹**（实际画上去的像素），不断"绘制函数被调了几次"——后者在 preferCanvas 模式下测不出真没画。

## 3. 防假绿闸门（模拟手法的配套纪律）

模拟得再真，门禁本身坏了照样假绿。所以体系里有三道"证明门禁会红"的闸：

1. **门禁突变自检**（`selftest.py` D 段）：在沙箱里故意污染基线断言文件，断言 verify 门禁**必然翻红**——门禁坏了但显示绿 = 最危险的假绿，此闸专防。
2. **真实链门**：拖拽这类过浏览器判定门的交互，合成事件测试不算数，必须 `verify-official-dnd-real.js` 的 CDP 真实链通过。
3. **改动证明**（`tools/prove_change.py`）：任何"已修复"必须附前后像素 diff + 哈希，预期变却没变 = FAIL，汇报给数字不给"已修复"。

## 4. 雷区速查

| 雷区 | 症状 | 正解 |
|---|---|---|
| 合成 DragEvent 直派发 | 全绿但真用户拖不进 | CDP setInterceptDrags 真实链（层级 2） |
| 隐藏窗口 capturePage | 截图全白 | `show: true` + `invalidate()` + `backgroundThrottling: false` |
| 共用 userData | 与用户实例互踩、误杀进程 | `app.setPath('userData', .tmp-*)` 隔离 |
| debugger 按方法名监听 | 事件永远收不到 | 只走 `dbg.on('message')` 统一分发 |
| 程序赋值后等联想出现 | input 事件不触发 | 手动 `dispatchEvent(new Event('input'))` |
| 断言"绘制函数被调用" | canvas 模式下假绿 | getImageData 数墨迹像素 |
| console 噪音污染断言 | 测试脚本自己触发性能提示 | 收集时过滤已知无害前缀（willReadFrequently） |

## 5. 现役验收脚本索引

| 脚本 | 断言数 | 覆盖 |
|---|---|---|
| `test/verify-route.js` | 18 | 路线规划：模式切换→联想选站→规划→行程卡片→地图墨迹→截图 |
| `test/verify-roadnet.js` | 9 | 步行网快照解码/路由 |
| `test/verify-official-board.js` | 30 | 地铁拼图官方棋盘全模式 |
| `test/verify-official-dnd-real.js` | 3 场景 | 真实拖放链（圈亮即可放/不亮 no-drop/他线零响应） |
| `test/verify-bus.js` / `verify-boot10.js` | — | 公交离线直出/启动 |
| `test/verify-108.js`（含 real/crash 变体） | — | 108 事故回归 |
