// 路线规划验收：模式切换 → 联想/选站 → 规划 → 行程卡片 + 地图绘制断言 + 截图
// 用法: ./node_modules/.bin/electron test/verify-route.js
const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

const OUT = 'E:/GuangzhouBusViewer/assets';

app.disableHardwareAcceleration();
app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');

app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1400, height: 860, show: true,
    webPreferences: { preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true } });
  const consoleErrors = [];
  win.webContents.on('console-message', (_e, level, message) => {
    const m = String(message);
    // 测试脚本自身 getImageData 采样触发的性能提示，非应用报错
    if (level >= 2 && !m.includes('willReadFrequently')) consoleErrors.push(m.slice(0, 200));
  });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));
  const exec = js => win.webContents.executeJavaScript(js);
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const log = (...a) => console.log('[route]', ...a);

  let fails = 0;
  const check = (name, cond, detail) => {
    log((cond ? 'PASS' : 'FAIL') + ' ' + name + (detail ? '  → ' + detail : ''));
    if (!cond) fails++;
  };

  /* ① 引擎级断言（页面上下文内） */
  const eng = await exec(`(async () => {
    const info = await RoutePlanner.ready();
    const sug = RoutePlanner.suggest('体育西', 8).map(x => x.name);
    const inst = RoutePlanner.instancesOf('体育西路');
    const a = inst[0], b = RoutePlanner.instancesOf('公园前')[0];
    const r = RoutePlanner.plan(
      { name: '体育西路', lat: a.lat, lng: a.lng, wgs: true },
      { name: '公园前', lat: b.lat, lng: b.lng, wgs: true });
    const ride = r.legs && r.legs.find(l => l.type === 'ride');
    return {
      nodesN: info.nodesN, buildMs: info.buildMs,
      sugOk: sug.includes('体育西路'), instN: inst.length,
      planErr: r.error || '', transfers: r.summary ? r.summary.transfers : -1,
      totalMin: r.summary ? r.summary.totalMin : -1,
      rideKm: r.summary ? r.summary.rideKm : -1,
      rideKind: ride ? ride.lineKind : 'none',
      ptsN: ride && ride.pts ? ride.pts.length : 0
    };
  })()`);
  check('引擎建图', eng.nodesN > 30000, `${eng.nodesN} 节点 / ${eng.buildMs}ms`);
  check('联想命中', eng.sugOk);
  check('同名实例', eng.instN >= 1, eng.instN + ' 个');
  check('地铁直达规划', !eng.planErr && eng.transfers === 0 && eng.rideKind === 'metro' && eng.ptsN >= 2,
    `${eng.totalMin}min / ${eng.rideKm}km / ${eng.ptsN}点`);

  /* ② 模式切换 + 地图创建 */
  await exec(`document.querySelector('#mode-nav [data-mode="route"]').click()`);
  await sleep(400);
  const vis = await exec(`(() => ({
    shown: !document.querySelector('#route-view').hidden,
    mapInited: !!document.querySelector('#route-map ._leaflet_map') ||
              document.querySelector('#route-map').classList.contains('leaflet-container')
  }))()`);
  check('视图切换', vis.shown && vis.mapInited);

  /* ③ 瓦片加载（防灰底） */
  let tiles = 0;
  for (let i = 0; i < 20 && tiles === 0; i++) {
    await sleep(300);
    tiles = await exec(`document.querySelectorAll('#route-map .leaflet-tile-loaded').length`);
  }
  check('底图瓦片铺开', tiles > 0, tiles + ' 块');

  /* ④ 输入起终点（联想回车链路） */
  await exec(`(() => {
    const from = document.querySelector('#route-from');
    from.focus(); from.value = '体育西路';
    from.dispatchEvent(new Event('input', { bubbles: true }));
    from.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    return 1;
  })()`);
  await sleep(500);
  await exec(`(() => {
    const to = document.querySelector('#route-to');
    to.focus(); to.value = '公园前';
    to.dispatchEvent(new Event('input', { bubbles: true }));
    to.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    return 1;
  })()`);

  /* ⑤ 等规划完成（回车即查） */
  let st = '';
  for (let i = 0; i < 60; i++) {
    await sleep(500);
    st = await exec(`document.querySelector('#route-status').textContent`);
    if (st.includes('个方案') || st.includes('总耗时') || st.includes('步行即可') || st.includes('失败')) break;
  }
  check('规划完成', st.includes('个方案') || st.includes('总耗时'), st.slice(0, 80));

  const ui = await exec(`(() => {
    // preferCanvas 模式下线路画在 overlay 的 canvas 上，程序化数非透明像素采样
    const cv = document.querySelector('#route-map .leaflet-overlay-pane canvas');
    let ink = 0;
    if (cv) {
      const ctx = cv.getContext('2d');
      const img = ctx.getImageData(0, 0, cv.width, cv.height).data;
      for (let i = 3; i < img.length; i += 40) if (img[i] > 0) ink++;
    }
    return {
      legs: document.querySelectorAll('#route-plan .leg').length,
      rides: document.querySelectorAll('#route-plan .leg.ride').length,
      summary: (document.querySelector('.plan-summary') || {}).textContent || '',
      alts: document.querySelectorAll('#route-plan .alt-chip').length,
      ink
    };
  })()`);
  check('行程卡片', ui.rides >= 1, `${ui.legs} 段（乘 ${ui.rides}）`);
  check('摘要行', /分钟/.test(ui.summary), ui.summary.slice(0, 60));
  check('方案切换条', ui.alts >= 1, ui.alts + ' 个方案');
  check('地图绘制', ui.ink > 50, `canvas 墨迹采样 ${ui.ink} 点`);

  /* ⑤a-2 方案切换：点第 2 方案，行程与墨迹都应变化 */
  if (ui.alts >= 2) {
    const before = await exec(`document.querySelector('.plan-summary').textContent`);
    await exec(`document.querySelectorAll('#route-plan .alt-chip')[1].click()`);
    await sleep(400);
    const after = await exec(`(() => ({
      sum: document.querySelector('.plan-summary').textContent,
      active: document.querySelectorAll('#route-plan .alt-chip')[1].classList.contains('active'),
      ink: (() => { const cv = document.querySelector('#route-map .leaflet-overlay-pane canvas'); if (!cv) return 0;
        const ctx = cv.getContext('2d'); const img = ctx.getImageData(0, 0, cv.width, cv.height).data;
        let n = 0; for (let i = 3; i < img.length; i += 40) if (img[i] > 0) n++; return n; })()
    }))()`);
    check('方案切换生效', after.active && after.sum !== before && after.ink > 0,
      `摘要变化=${before.slice(6, 14)}→${after.sum.slice(6, 14)} 墨迹${after.ink}`);
  }

  /* ⑤b 跨城多段：岗顶(BRT) → 芳村，至少 2 乘段 1 换乘 */
  await exec(`(() => {
    const set = (sel, val) => {
      const el = document.querySelector(sel);
      el.focus(); el.value = val;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    };
    set('#route-from', '岗顶');
    return 1;
  })()`);
  await sleep(400);
  await exec(`(() => {
    const to = document.querySelector('#route-to');
    to.focus(); to.value = '芳村';
    to.dispatchEvent(new Event('input', { bubbles: true }));
    to.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    return 1;
  })()`);
  st = '';
  for (let i = 0; i < 60; i++) {
    await sleep(500);
    st = await exec(`document.querySelector('#route-status').textContent`);
    if (st.includes('个方案') || st.includes('总耗时') || st.includes('失败')) break;
  }
  const ui2 = await exec(`(() => ({
    status: document.querySelector('#route-status').textContent,
    rides: document.querySelectorAll('#route-plan .leg.ride').length,
    walks: document.querySelectorAll('#route-plan .leg.walk').length,
    kinds: [...document.querySelectorAll('#route-plan .leg.ride .leg-ref')].map(e => e.textContent).join(',')
  }))()`);
  check('跨城规划完成', ui2.status.includes('个方案') || ui2.status.includes('总耗时'), ui2.status.slice(0, 70));
  check('跨城多段+换乘', ui2.rides >= 2 && ui2.walks >= 1, `乘 ${ui2.rides} 段 / 步行 ${ui2.walks} 段 [${ui2.kinds}]`);
  fs.writeFileSync(OUT + '/_v-route-multi.png', (await win.webContents.capturePage()).toPNG());
  log('截图 assets/_v-route-multi.png');

  /* ⑥ 截图 */
  fs.writeFileSync(OUT + '/_v-route.png', (await win.webContents.capturePage()).toPNG());
  log('截图 assets/_v-route.png');

  check('控制台零报错', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' || '));
  log(fails ? `${fails} FAIL` : 'ALL GREEN');
  app.exit(fails ? 1 : 0);
});
