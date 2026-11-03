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

  /* ①b 出行模式与途经点（驾车/步行/纯公交/纯地铁/公共交通链） */
  const modes = await exec(`(async () => {
    await RoutePlanner.ready();
    const F = n => { const c = RoutePlanner.resolveInstance(n, null); return { name: n, lat: c.lat, lng: c.lng, wgs: true }; };
    const gd = F('岗顶'), fc = F('芳村'), xy = F('体育西路'), zx = F('体育中心');
    const kinds = pl => [...new Set(pl.legs.filter(l => l.type === 'ride').map(l => l.lineKind))].join(',') || 'none';
    const drive = RoutePlanner.planK([gd, fc], 2, 'drive');
    const walk = RoutePlanner.planK([xy, zx], 1, 'walk');
    const bus = RoutePlanner.planK([gd, fc], 1, 'bus');
    const metro = RoutePlanner.planK([gd, fc], 1, 'metro');
    const chain = RoutePlanner.planK([gd, xy, fc], 1, 'transit');
    return JSON.stringify({
      driveN: drive.plans ? drive.plans.length : 0,
      driveTags: drive.plans ? drive.plans.map(p => p.tag).join(',') : drive.error || '',
      driveMin: drive.plans ? drive.plans[0].summary.totalMin : 0,
      driveType: drive.plans ? drive.plans[0].legs[0].type : '',
      walkM: walk.plans ? walk.plans[0].summary.walkM : 0,
      walkType: walk.plans ? walk.plans[0].legs[0].type : walk.error || '',
      busKinds: bus.plans ? kinds(bus.plans[0]) : bus.error || '',
      metroKinds: metro.plans ? kinds(metro.plans[0]) : metro.error || '',
      chainWp: chain.plans ? chain.plans[0].legs.filter(l => l.type === 'wp').map(l => l.name).join(',') : chain.error || '',
      chainRides: chain.plans ? chain.plans[0].legs.filter(l => l.type === 'ride').length : 0
    });
  })()`, 300000);
  const md = JSON.parse(modes);
  check('驾车模式', md.driveN >= 1 && /最快/.test(md.driveTags) && md.driveType === 'drive' &&
    md.driveMin >= 8 && md.driveMin <= 90, `${md.driveN} 个 [${md.driveTags}] ${md.driveMin}min`);
  check('纯步行模式', md.walkType === 'walk' && md.walkM >= 500 && md.walkM <= 4000, `${md.walkM}m`);
  check('纯公交模式', md.busKinds === 'bus', md.busKinds);
  check('纯地铁模式', md.metroKinds === 'metro', md.metroKinds);
  check('公共交通途经点链', md.chainWp === '体育西路' && md.chainRides >= 2, `wp=${md.chainWp} rides=${md.chainRides}`);

  /* ①c 回归：逐段选拔口径 + GCJ 纠偏 + 途经点地铁链（2026-11-03 用户判例）
     判例一：链每段按同一口径独立选拔（用户令"优先时间那几段都优先时间，优先换乘
     那几段都优先换乘"）——time=每段最快，xfer=每段最少换乘（同数取最快）；
     配套修复：三 xferMul profile 罚空间必须独立，否则真 0 换乘最优被压在池外；
     判例二：js/coords.js 未挂 window.GCJ → project/gcjToWgs 恒不转换，WGS 数据在
     AMap(GCJ) 瓦片上整体偏约 550m，中大站定位点落珠江。 */
  const wpc = await exec(`(async () => {
    await RoutePlanner.ready();
    const F = n => { const c = RoutePlanner.resolveInstance(n, null); return { name: n, lat: c.lat, lng: c.lng, wgs: true }; };
    const jr = { name: '聚仁坊', lat: 23.12135, lng: 113.27428, wgs: false, poi: true };   // AMap POI 实测值（GCJ）
    const seg = [F('中山大学'), F('广州塔')];
    const chT = RoutePlanner.planK([jr, ...seg], 1, 'metro', 'time');
    const chX = RoutePlanner.planK([jr, ...seg], 1, 'metro', 'xfer');
    const k1t = RoutePlanner.planK(seg, 1, 'metro', 'time');
    const k1x = RoutePlanner.planK(seg, 1, 'metro', 'xfer');
    const k3 = RoutePlanner.planK(seg, 3, 'metro');
    const g = RoutePlanner.gcjToWgs(23.092124, 113.292863);   // 中大站 AMap GCJ 实测
    // k=3 池基准：最快方案 / 最少换乘数 + 该数下最快方案的耗时（池按耗时序）
    const minT = Math.min(...k3.plans.map(p => p.summary.transfers));
    const fastestMinT = k3.plans.find(p => p.summary.transfers === minT);
    const dig = r => {
      const legs = r.plans ? r.plans[0].legs : [];
      const walks = legs.filter(l => l.type === 'walk').map(l => Math.round(l.m));
      return {
        err: r.error || '',
        min: r.plans ? r.plans[0].summary.totalMin : -1,
        xfer: r.plans ? r.plans[0].summary.transfers : -1,
        rides: legs.filter(l => l.type === 'ride' && l.lineKind === 'metro').length,
        wps: legs.filter(l => l.type === 'wp').map(l => l.name).join(','),
        maxWalk: walks.length ? Math.max(...walks) : 9999,
        walkTotal: r.plans ? r.plans[0].summary.walkM : -1
      };
    };
    return JSON.stringify({
      gcjMounted: !!window.GCJ,
      gcjMoved: Math.abs(g[0] - 23.092124) > 0.001 && Math.abs(g[1] - 113.292863) > 0.001,
      chT: dig(chT), chX: dig(chX), k1t: dig(k1t), k1x: dig(k1x),
      poolFastest: k3.plans ? k3.plans[0].summary.totalMin : -1,
      poolFastestXfer: k3.plans ? k3.plans[0].summary.transfers : -1,
      poolMinT: k3.plans ? minT : -1,
      poolFastestMinT: fastestMinT ? fastestMinT.summary.totalMin : -1
    });
  })()`, 300000);
  const wp = JSON.parse(wpc);
  check('GCJ 挂载+纠偏生效', wp.gcjMounted && wp.gcjMoved,
    wp.gcjMounted ? 'wgs84ToGcj02→gcjToWgs 有净位移' : 'window.GCJ 未挂载');
  check('链段口径=时间优先→每段最快', !wp.k1t.err && wp.k1t.min === wp.poolFastest && wp.k1t.xfer === wp.poolFastestXfer,
    `k=1 time ${wp.k1t.min}min/${wp.k1t.xfer}换 vs 池最快 ${wp.poolFastest}min/${wp.poolFastestXfer}换`);
  check('链段口径=换乘优先→每段最少换乘', !wp.k1x.err && wp.k1x.xfer === wp.poolMinT && wp.k1x.min === wp.poolFastestMinT,
    `k=1 xfer ${wp.k1x.min}min/${wp.k1x.xfer}换 vs 池最少换乘基准 ${wp.poolFastestMinT}min/${wp.poolMinT}换`);
  check('途经点链(换乘优先)全程乘车', !wp.chX.err && wp.chX.rides >= 2 && wp.chX.wps === '中山大学' &&
    wp.chX.maxWalk <= 2000 && wp.chX.xfer <= 2,
    `${wp.chX.min}min/${wp.chX.xfer}换 乘${wp.chX.rides} wp=${wp.chX.wps} 最长步行${wp.chX.maxWalk}m 总步行${wp.chX.walkTotal}m`);
  check('途经点链(时间优先)全程乘车', !wp.chT.err && wp.chT.rides >= 2 && wp.chT.wps === '中山大学' &&
    wp.chT.maxWalk <= 1200 && wp.chT.xfer <= 3,
    `${wp.chT.min}min/${wp.chT.xfer}换 乘${wp.chT.rides} wp=${wp.chT.wps} 最长步行${wp.chT.maxWalk}m 总步行${wp.chT.walkTotal}m`);

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
