# 广州公交路线预览（Guangzhou Bus Viewer）

基于 **Electron + Leaflet** 的桌面应用：在广州市地图上浏览各条公交线路的走向与站点。

数据来源：**OpenStreetMap**（[ODbL](https://opendatacommons.org/licenses/odbl/) 许可），经 Overpass API 查询。
底图：高德栅格瓦片（默认）或 OpenStreetMap 瓦片，可一键切换。

## 运行

```bash
npm install          # 国内网络建议：npm install --registry=https://registry.npmmirror.com
npm start            # 启动 Electron 应用
npm run dev:web      # 仅在浏览器中调试渲染层（http://127.0.0.1:8177，无需 Electron）
```

> 若 Electron 二进制下载缓慢：
> `set ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/` 后重新 `npm install`。

## 功能

- 全市公交线路上千条线路索引（首次拉取后缓存 24 小时）
- 按线路号 / 名称 / 起终点 / 运营方搜索
- 点击线路 → 地图绘制走向折线 + 沿途站点（点击站点弹窗）
- 多方向/变体切换（如 B7 与 B7快、上行下行）
- 多线路叠加对比，各自着色（优先使用 OSM 的 colour 标签）
- 高德底图（GCJ-02，自动坐标纠偏）/ OSM 底图（WGS-84）切换
- Overpass 多镜像轮询 + 两轮重试 + 本地缓存（线路几何缓存最近 20 条）
- 线路列表拉取失败时，搜索框回车可直接按线路号查询（轻量请求）

## 技术要点

| 事项 | 说明 |
| --- | --- |
| 坐标系 | OSM 数据为 WGS-84；高德瓦片为 GCJ-02，叠加前逐点转换（`js/coords.js`） |
| 数据量 | 广州市在 OSM 中约有 1,700+ 条 `route=bus` 线路关系，覆盖较完整 |
| 站点识别 | 取关系成员中 `role=platform*` 的节点/面（面取几何首点），站名来自节点标签 |
| 路径 | 关系成员中无 role 的 way，按顺序拼接为多段折线（OSM 映射可能有断口） |
| 安全 | `contextIsolation: true`、`nodeIntegration: false`、`sandbox: true` |

## 目录结构

```
main.js            Electron 主进程
preload.js         预加载脚本（仅暴露应用信息）
index.html         渲染层入口
css/style.css      界面样式
js/coords.js       WGS-84 → GCJ-02 坐标转换
js/overpass.js     Overpass 数据层：镜像轮询、重试、缓存、解析
js/map-layer.js    Leaflet 地图层：底图切换、线路/站点绘制
js/app.js          UI 逻辑：列表、搜索、详情、方向切换
server-dev.js      浏览器调试用静态服务器（零依赖）
test/              冒烟测试与测试数据（见下）
```

## 测试

```bash
# Electron 渲染层冒烟测试（加载页面、检查各模块就绪、无控制台错误即通过）
./node_modules/.bin/electron test/smoke-main.js

# 浏览器内调试（配合 GzBusDebug 注入离线数据，不依赖 Overpass 网络）
npm run dev:web
# 打开控制台执行：
#   GzBusDebug.loadFixture('/test/b7-fixture.json')
```

`test/b7-fixture.json`：B7 线测试数据，站点名称与坐标来自 OSM 真实数据，
但顺序按地理走廊近似排序、路径为站点间直连段，仅用于离线验证渲染管线。

## 已知限制

- Overpass 镜像站均为国际线路，大陆直连不稳定：已内置 5 个镜像轮询 + 2 轮重试
  + 24 小时索引缓存 + 单线路 20 条 LRU 缓存，但仍可能偶发失败（点击"刷新"重试即可）
- OSM 数据由社区维护，个别线路可能缺站点角色、路径断线或信息滞后
- OSM 底图瓦片在大陆基本无法加载，默认底图已设为高德

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
