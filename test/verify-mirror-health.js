// 启动离线口径验收（2026-10-27 用户令：启动只用本地数据，联网只走手动刷新）：
//   ① 启动阶段（全新隔离 userData）：线路列表从随包快照秒出（<3s、>1000 条）、
//      状态栏为"本地数据"文案、镜像健康记录为空（=一次 Overpass 请求都没发过）；
//   ② 手动阶段：点「刷新」→ 走 force 在线竞速，成功更新或优雅降级报错，均不崩。
// stderr 的 handshake failed 行只可能来自②（手动竞速撞被掐主机），属预期噪音。
// 用法: ./node_modules/.bin/electron test/verify-mirror-health.js
const { app, BrowserWindow } = require('electron');
const path = require('path');

app.setPath('userData', path.join(__dirname, '..', '.tmp-userdata-mirrorhealth'));
app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');

app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1360, height: 860, show: false,
    webPreferences: { preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true } });
  const t0 = Date.now();
  await win.loadFile(path.join(__dirname, '..', 'index.html'));
  // 轮询等列表首帧（本地路径应秒出；若误回在线路径会拖到 30s 级=FAIL）
  let boot = null;
  for (let i = 0; i < 60; i++) {
    boot = await win.webContents.executeJavaScript(`({
      count: parseInt(document.getElementById('line-count').textContent, 10) || 0,
      status: document.querySelector('#status, .status') ?
        document.querySelector('#status, .status').textContent : '',
      health: localStorage.getItem('gzbus.mirror-health.v1') })`);
    if (boot.count > 0) break;
    await new Promise(r => setTimeout(r, 250));
  }
  boot.ms = Date.now() - t0;
  await new Promise(r => setTimeout(r, 1500));   // 再静置 1.5s 确认无迟发联网
  boot.healthLate = await win.webContents.executeJavaScript(
    `localStorage.getItem('gzbus.mirror-health.v1')`);

  // 手动刷新：force 在线竞速（成功/优雅失败皆可，不允许挂死/抛错）
  await win.webContents.executeJavaScript(`document.getElementById('refresh').click()`);
  let manual = null;
  for (let i = 0; i < 160; i++) {   // 最长 40s（30s 超时 + 余量）
    await new Promise(r => setTimeout(r, 250));
    manual = await win.webContents.executeJavaScript(`({
      status: document.querySelector('#status, .status').textContent,
      count: parseInt(document.getElementById('line-count').textContent, 10) || 0,
      busy: document.getElementById('refresh').disabled,
      health: localStorage.getItem('gzbus.mirror-health.v1') })`);
    if (!manual.busy) break;
  }
  console.log('[boot]   ' + JSON.stringify(boot));
  console.log('[manual] ' + JSON.stringify(manual));
  const okBoot = boot.count > 1000 && boot.ms < 3000 && boot.status.indexOf('本地数据') >= 0 &&
    !boot.health && !boot.healthLate;
  const okManual = manual && !manual.busy && manual.count > 1000 &&
    (manual.status.indexOf('已加载') >= 0 || manual.status.indexOf('失败') >= 0);
  console.log(okBoot && okManual ? 'PASS: 启动零联网秒出列表 / 手动刷新可用' :
    'FAIL: ' + JSON.stringify({ okBoot, okManual }));
  app.exit(okBoot && okManual ? 0 : 1);
}).catch(e => { console.error(e); app.exit(2); });
