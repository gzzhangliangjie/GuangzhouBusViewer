# 广州公交 · 地铁拼图（Guangzhou Transit）

基于 **Electron + Leaflet** 的桌面应用，两大模式：

- **公交路线预览**：在广州市地图上浏览各条公交线路的走向与站点
- **地铁拼图**：把收起的站名与线号凭记忆拼回真实地图，还原 2026 年广州地铁完整线网
  （19 条线 / 314 座车站）

公交数据来源：**OpenStreetMap**（[ODbL](https://opendatacommons.org/licenses/odbl/) 许可），经 Overpass API 查询。
底图：高德栅格瓦片（默认）或 OpenStreetMap 瓦片，可一键切换。

## 运行

```bash
npm install          # 国内网络建议：npm install --registry=https://registry.npmmirror.com
npm start            # 启动 Electron 应用
npm run dev:web      # 仅在浏览器中调试渲染层（http://127.0.0.1:8177，无需 Electron）
```

> 若 Electron 二进制下载缓慢：
> `set ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/` 后重新 `npm install`。

## 功能：公交路线预览

- 全市公交线路上千条线路索引（首次拉取后缓存 24 小时）
- 按线路号 / 名称 / 起终点 / 运营方搜索
- 点击线路 → 地图绘制走向折线 + 沿途站点（点击站点弹窗）
- 多方向/变体切换（如 B7 与 B7快、上行下行）
- 多线路叠加对比，各自着色（优先使用 OSM 的 colour 标签）
- 高德底图（GCJ-02，自动坐标纠偏）/ OSM 底图（WGS-84）切换
- Overpass 多镜像轮询 + 两轮重试 + 本地缓存（线路几何缓存最近 20 条）
- 线路列表拉取失败时，搜索框回车可直接按线路号查询（轻量请求）

## 功能：地铁拼图

| 模式 | 说明 |
| ---- | ---- |
| 站名模式 | 线路颜色与线号徽章可见，站名收起 → 从名牌池把站名放回对应站点 |
| 线号模式 | 站名可见，线号收起 → 把 1~22 号线编号放回线路徽章 |
| 挑战模式 | 站名 + 线号全部收起，硬核挑战 |

- **两种地图风格**（按 模式×风格×范围 分组保存最佳成绩）：
  - `真实地图`：线路按真实经纬度叠加高德底图（GCJ-02 纠偏），画法与公交模式一致
    （深色描边 + 官方配色、白圈彩芯站点、换乘站白芯黑环）
  - `纯线路图`：游戏直接跑在 **Tim 版广佛地铁图**棋盘上（白底官方风格 45° 折线线网，
    2026-07-30 矢量版）。棋盘由脚本删除站名/线号徽章/图例生成（`assets/tim-board.svg`），
    314 站坐标由 `tools/build_tim_layout.py` 从矢量图自动提取（锚点 TPS 变换 + 贴线贴字形，
    中位误差 6.8px）；站点为透明热区，放置后高亮；单线模式自动蒙灰其余线
- **线路徽章**：官方「X号线」胶囊样式（线路色 + 白字，如 1号线 / 广佛线 / APM线），虚线 ？ 胶囊为待填槽
- **站点编号牌**：每站左下角「线号-序号」小标签（如 1-14），与 UE 原版一致的关键线索
- **站名防堆叠**：缩放分级（已放置/换乘站优先）+ 矩形碰撞去重 + 单视图上限，放大后逐级补全
- **完整线网图对照**：答案图页可一键切换完整版 Tim 线网图（矢量、带全部站名，
  `assets/tim-gzfmetro.svg`，2026-07-30）浏览对照
- **范围**：全网挑战 / 任选单条线（其余线淡灰走向背景、不显示站点）
- **操作**：点名牌再点站点，或直接拖拽；滚轮缩放；Esc 取消选中
- **计分**：放对 +100，放错 -10，提示 -50（自动放对一个），完成后按剩余时间给加成
- **放弃**：随时"放弃并揭示"查看完整答案；主菜单可看答案图

## 技术要点

| 事项 | 说明 |
| --- | --- |
| 坐标系 | OSM 数据为 WGS-84；高德瓦片为 GCJ-02，叠加前逐点转换（`js/coords.js`） |
| 数据量 | 广州市在 OSM 中约有 1,700+ 条 `route=bus` 线路关系，覆盖较完整 |
| 站点识别 | 取关系成员中 `role=platform*` 的节点/面（面取几何首点），站名来自节点标签 |
| 路径 | 关系成员中无 role 的 way，按顺序拼接为多段折线（OSM 映射可能有断口） |
| 地铁数据 | 本地打包 `data/metro-data.js`（314 站双坐标 / 19 线官方配色），离线可玩 |
| 安全 | `contextIsolation: true`、`nodeIntegration: false`、`sandbox: true` |

## 目录结构

```
main.js            Electron 主进程
preload.js         预加载脚本（仅暴露应用信息）
index.html         渲染层入口（顶部"公交路线 / 地铁拼图"模式切换）
css/style.css      公共界面样式（含模式导航）
css/metro.css      地铁拼图样式
js/coords.js       WGS-84 → GCJ-02 坐标转换
js/tiles.js        共享底图瓦片配置（高德 / OSM）
js/overpass.js     Overpass 数据层：镜像轮询、重试、缓存、解析
js/map-layer.js    公交 Leaflet 地图层：底图切换、线路/站点绘制
js/app.js          公交 UI 逻辑：列表、搜索、详情、方向切换
data/metro-data.js 地铁线网数据（314 站；sx/sy 为 Tim 线网图坐标）
assets/            tim-gzfmetro.svg 完整线网图（Tim Wu, CC BY-SA 4.0）
                   tim-board.svg 无字游戏棋盘（由上图删层生成）
                   tim-coords.json 提取的站点坐标
tools/build_tim_layout.py  从 Tim SVG 提取 314 站坐标的管线脚本
js/metro-data.js   地铁数据访问层（线路/站点/徽章/配色）
js/metro-map.js    地铁拼图地图渲染器（真实地图/纯线路图双风格 + 完整图查看器）
js/metro-quiz.js   地铁拼图游戏逻辑（模式/计分/计时/最佳纪录）
server-dev.js      浏览器调试用静态服务器（零依赖）
test/              冒烟测试、纯线路图流程验证与测试数据（见下）
```

## 测试

```bash
# Electron 渲染层冒烟测试（加载页面、检查公交与地铁模块就绪、切换模式、无控制台错误即通过）
./node_modules/.bin/electron test/smoke-main.js

# 纯线路图模式流程验证（答案图渲染/缩放分级/官方图切换/单线游戏/真实地图回归）
./node_modules/.bin/electron test/verify-schematic.js

# 浏览器内调试（配合 GzBusDebug 注入离线数据，不依赖 Overpass 网络）
npm run dev:web
# 打开控制台执行：
#   GzBusDebug.loadFixture('/test/b7-fixture.json')
```

`test/b7-fixture.json`：B7 线测试数据，站点名称与坐标来自 OSM 真实数据，
但顺序按地理走廊近似排序、路径为站点间直连段，仅用于离线验证渲染管线。

## 地铁数据来源

- 线路/站名/坐标：© OpenStreetMap 贡献者（ODbL），取自开源项目
  [guangzhou-metro-typing](https://github.com/JamieStudio-lab/guangzhou-metro-typing) 的 2026-07 快照，
  并用 Overpass API 补齐 **3 号线机场段（10 站）** 与 **14 号线知识城支线（8 站）**
  （由姊妹项目 [GuangzhouMetroQuiz](../GuangzhouMetroQuiz)（UE 5.5）的 `tools/gen_layout.py` 生成）
- 纯线路图棋盘：[Guangzhou-Foshan Metro Diagram by Tim Wu](https://commons.wikimedia.org/wiki/File:Guangzhou-Foshan_Metro_Diagram_by_Tim.svg)
  （Wikimedia Commons，**CC BY-SA 4.0**，2026-07-30 版）——游戏棋盘为删层无字版，完整版在答案图页对照浏览
- 3 号线主线 = 海傍 … 体育西路 … 机场北；支线 = 体育西路 … 天河客运站
- 14 号线支线 = 新和 - 红卫 - 新南 - 枫下 - 知识城 - 何棠下 - 旺村 - 汤村 - 镇龙北 - 镇龙

## 已知限制

- Overpass 镜像站均为国际线路，大陆直连不稳定：已内置 5 个镜像轮询 + 2 轮重试
  + 24 小时索引缓存 + 单线路 20 条 LRU 缓存，但仍可能偶发失败（点击"刷新"重试即可）
- OSM 数据由社区维护，个别线路可能缺站点角色、路径断线或信息滞后
- OSM 底图瓦片在大陆基本无法加载，默认底图已设为高德
- 地铁线网快照日期 2026-07，与最新线网可能存在个别差异

## 调研记录（同类项目与地图服务）

### GitHub 类似项目

- [OsmHackTW/BusRouteMap](https://github.com/OsmHackTW/BusRouteMap) — 台湾公车路线地图（Leaflet），思路最接近本项目
- [daibor/bus-route-radiation-map](https://github.com/daibor/bus-route-radiation-map) — 公交线路辐射图（高德 JS API）
- [HwH13/beijing-bus-route](https://github.com/HwH13/beijing-bus-route) — 用高德 API 抓取北京全部公交线路
- [BusRouter.sg](https://busrouter.sg/) — 新加坡标杆项目；国内有基于 [CPTOND-2025](https://github.com/jean89091515/CPTOND) 数据集的类似可视化
- [MobilityData/awesome-transit](https://github.com/MobilityData/awesome-transit) — GTFS 数据与工具大全（广州无官方 GTFS）

### 地图服务对比

| 服务 | 是否要 Key | 国内速度 | 坐标系 | 备注 |
| --- | --- | --- | --- | --- |
| 高德栅格瓦片 | 否 | 快 | GCJ-02 | 本项目默认底图 |
| OSM 瓦片 | 否 | 慢/不稳 | WGS-84 | 与 OSM 数据天然同源 |
| 高德 JS API 2.0 | 要（免费申请） | 快 | GCJ-02 | 有公交线路查询官方示例 |
| 百度/腾讯 JS API | 要 | 快 | BD-09/GCJ-02 | 需申请 Key |
| Mapbox | 要 | 一般 | WGS-84 | 免费额度有限 |

### 公交数据源

- **OpenStreetMap Overpass API**（本项目采用）：免 Key，广州 1,700+ 条线路，含站点/路径/颜色/运营方；缺点是镜像站在大陆直连不稳定（已做多镜像轮询 + 重试 + 缓存）
- **高德公交线路查询 API**（`/v3/bus/linename`）：数据最权威、国内快，但需申请 Key
- **8684.cn / 车来了**：有数据但无开放接口，抓取不受官方支持
- **官方 GTFS**：广州未公开发布

## 许可

代码 MIT。地图数据 © OpenStreetMap 贡献者（ODbL）；底图 © 高德地图。
