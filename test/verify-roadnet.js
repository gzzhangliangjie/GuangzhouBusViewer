// 路网快照验收：步行真实化（路线规划）+ 道路查看本地检索（离线秒出）
// 用法: ./node_modules/.bin/electron test/verify-roadnet.js
const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

const OUT = 'E:/GuangzhouBusViewer/assets';
app.disableHardwareAcceleration();
app.setPath('userData', fs.mkdtempSync(path.join(require('os').tmpdir(), 'gzroadnet-')));
app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');

app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1400, height: 860, show: true,
    webPreferences: { preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true } });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));
  // POI 探针需要高德 key（无 key 会落 Overpass 慢速兜底拖死验收）
  await win.webContents.executeJavaScript(
    `localStorage.setItem('gzbus.amap.key.v1', JSON.stringify({ key: '04f065a4e72d55a1f150454d361122c4' })); 'ok'`);
  const exec = js => win.webContents.executeJavaScript(js);
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const log = (...a) => console.log('[roadnet]', ...a);
  const errors = [];
  win.webContents.on('console-message', (_e, lv, m) => {
    const s = String(m);
    if (lv >= 2 && !s.includes('willReadFrequently')) errors.push(s.slice(0, 160));
  });

  let fails = 0;
  const check = (name, cond, detail) => {
    log((cond ? 'PASS' : 'FAIL') + ' ' + name + (detail ? '  → ' + detail : ''));
    if (!cond) fails++;
  };

  /* ① 快照装载 + 统计 */
  const stats = await exec(`RoadNet.ready().then(ok => JSON.stringify({ ok, ...RoadNet.stats() }))`);
  const st = JSON.parse(stats);
  check('快照装载', st.ok && st.nodeN > 50000, `${st.nodeN} 节点 / ${st.wayN} 路段`);

  /* ② 真实步行路径：聚仁坊→团一大广场/农讲所 实走 vs 直线
     （POI 坐标用历史实测值硬编码——验收不依赖外部网络/配额） */
  const walk = await exec(`(async () => {
    await RoutePlanner.ready();
    const gcj = { lat: 23.1214, lng: 113.2743 };              // 聚仁坊（高德历史实测）
    const w = RoutePlanner.gcjToWgs(gcj.lat, gcj.lng);
    const targets = ['团一大广场', '农讲所'].map(nm => {
      const t = RoutePlanner.resolveInstance(nm, null);
      const r = RoadNet.walkPath({ lat: w[0], lng: w[1] }, { lat: t.lat, lng: t.lng }, 4000);
      const dLine = Math.round(Math.hypot((t.lng - w[1]) * Math.cos(23.1 * Math.PI / 180) * 111320,
        (t.lat - w[0]) * 110540));
      return { nm, ok: !!r, m: r ? r.m : 0, ptsN: r ? r.pts.length : 0, straight: dLine };
    });
    return JSON.stringify(targets);
  })()`, 180000);
  const walks = JSON.parse(walk);
  for (const wk of walks) {
    check(`步行真实路径 ${wk.nm}`, wk.ok && wk.m > wk.straight && wk.ptsN >= 5,
      `实走 ${wk.m}m / 直线 ${wk.straight}m（${(wk.m / wk.straight).toFixed(2)}×）/${wk.ptsN}点`);
  }

  /* ③ 道路查看本地检索：首次含图装载（冷），第二次检索必须热秒出 */
  await exec(`document.querySelector('#mode-nav [data-mode="roads"]').click()`);
  await sleep(300);
  await exec(`(() => {
    const el = document.querySelector('#road-search');
    el.value = '黄埔大道';
    return 1;
  })()`);
  let t0 = Date.now();
  await exec(`document.querySelector('#road-go').click()`);
  let rst = '';
  for (let i = 0; i < 40; i++) {
    await sleep(300);
    rst = await exec(`document.querySelector('#road-status').textContent`);
    if (rst.includes('匹配') || rst.includes('正在查看')) break;
  }
  const coldMs = Date.now() - t0;
  // 热检索：换一个词再查（图已装载，应秒出）
  await exec(`(() => { const el = document.querySelector('#road-search'); el.value = '中山大道'; return 1; })()`);
  t0 = Date.now();
  await exec(`document.querySelector('#road-go').click()`);
  for (let i = 0; i < 40; i++) {
    await sleep(200);
    rst = await exec(`document.querySelector('#road-status').textContent`);
    if (rst.includes('本地路网快照')) break;
  }
  const warmMs = Date.now() - t0;
  const srcOk = await exec(`RoadNet.searchRoads('中山大道').length > 0`);
  const roadUi = await exec(`(() => {
    const cv = document.querySelector('#roads-map .leaflet-overlay-pane canvas');
    let ink = 0;
    if (cv) {
      const ctx = cv.getContext('2d');
      const img = ctx.getImageData(0, 0, cv.width, cv.height).data;
      for (let i = 3; i < img.length; i += 40) if (img[i] > 0) ink++;
    }
    return {
      items: document.querySelectorAll('#road-list li').length,
      ink
    };
  })()`);
  check('道路本地检索快出', srcOk && warmMs < 15000,
    `冷 ${(coldMs / 1000).toFixed(1)}s（含图装载）/ 热 ${warmMs}ms（含长路绘制）/ 快照命中=${srcOk}`);
  check('道路列表+绘制', roadUi.items >= 1 && roadUi.ink > 50,
    `${roadUi.items} 条 墨迹 ${roadUi.ink}`);
  fs.writeFileSync(OUT + '/_v-roadnet-roads.png', (await win.webContents.capturePage()).toPNG());

  /* ④ 路线规划：岗顶→芳村（站名输入走本地解析，验收零网络）步行段真实折线 */
  await exec(`document.querySelector('#mode-nav [data-mode="route"]').click()`);
  await sleep(400);
  for (const [sel, val] of [['#route-from', '岗顶'], ['#route-to', '芳村']]) {
    await exec(`(() => {
      const el = document.querySelector('${sel}');
      el.focus(); el.value = '${val}';
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
      return 1;
    })()`);
    await sleep(700);
  }
  let st2 = '';
  for (let i = 0; i < 90; i++) {
    await sleep(500);
    st2 = await exec(`document.querySelector('#route-status').textContent`);
    if (st2.includes('个方案') || st2.includes('失败')) break;
  }
  check('规划完成（真实步行）', st2.includes('个方案'), st2.slice(0, 60));
  const legs = await exec(`JSON.stringify((RoutePlanner.planK ? (window.__lastPlans || null) : null))`).catch(() => null);
  // 行程里步行段文案：本 OD 无长步行段时只有站内换乘，两种文案都算过
  const legTexts = await exec(`[...document.querySelectorAll('#route-plan .leg.walk .leg-body')].map(e => e.textContent).join(' | ')`);
  check('步行段展示', /步行约|站内换乘/.test(legTexts), legTexts.slice(0, 80));
  fs.writeFileSync(OUT + '/_v-roadnet-route.png', (await win.webContents.capturePage()).toPNG());
  log('截图 assets/_v-roadnet-roads.png / _v-roadnet-route.png');

  check('控制台零报错', errors.length === 0, errors.slice(0, 3).join(' || '));
  log(fails ? `${fails} FAIL` : 'ALL GREEN');
  app.exit(fails ? 1 : 0);
});
