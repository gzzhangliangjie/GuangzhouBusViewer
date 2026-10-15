// 一次性验证脚本：纯线路图模式完整流程（不依赖 IAB 浏览器）
// 用法: ./node_modules/.bin/electron test/verify-schematic.js
const { app, BrowserWindow } = require('electron');
const path = require('path');

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: 1400, height: 860, show: false,
    webPreferences: {
      preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true
    }
  });
  const errors = [];
  win.webContents.on('console-message', (_e, _lvl, msg) => {
    if (/error|failed/i.test(msg)) errors.push(msg);
  });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));

  const out = await win.webContents.executeJavaScript(`(async () => {
    const log = [];
    const canvas = document.getElementById('metro-canvas');
    const counts = () => ({
      labels: canvas.querySelectorAll('.mlab').length,
      nums: [...canvas.querySelectorAll('.mnum-wrap')].filter(el => el.style.display !== 'none').length
    });
    document.querySelector('#mode-nav [data-mode="metro"]').click();

    // ① 纯线路图答案图：全景应有编号牌 + 换乘站名
    document.querySelector('#metro-setup .opt-card[data-v="schematic"]').click();
    document.getElementById('metro-answer').click();
    await new Promise(r => setTimeout(r, 1500));
    let map = MetroQuiz.__game().renderer.__internals.map;
    log.push({ step: 'sc-answer', zoom: map.getZoom(), ...counts() });

    map.setZoom(-0.5);
    await new Promise(r => setTimeout(r, 400));
    log.push({ step: 'sc-zoom-in', zoom: map.getZoom(), ...counts() });

    // ② 官方线网图切换
    document.getElementById('mq-official').click();
    await new Promise(r => setTimeout(r, 1000));
    const img = canvas.querySelector('img.leaflet-image-layer');
    log.push({ step: 'official', kind: MetroQuiz.__game().renderer.kind,
      imgLoaded: !!(img && img.complete && img.naturalWidth > 0),
      btnText: document.getElementById('mq-official').textContent });

    document.getElementById('mq-official').click();
    await new Promise(r => setTimeout(r, 1000));
    log.push({ step: 'back-to-data', kind: MetroQuiz.__game().renderer.kind });

    // ③ 纯线路图游戏（1号线）：放置一个站
    document.getElementById('mq-back').click();
    document.querySelector('#scope-picker .scope-pill[data-v="1"]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 1500));
    const g = MetroQuiz.__game();
    map = g.renderer.__internals.map;
    const zoomAtStart = map.getZoom();
    const chip = [...document.querySelectorAll('#chip-pool .mchip')][0];
    chip.click();
    g.renderer.__internals.stationMk.get(chip.textContent).fire('click');
    log.push({ step: 'sc-game-1line', kind: g.renderer.kind, zoom: zoomAtStart,
      score: g.score, chipGone: !chip.isConnected, ...counts() });

    // ④ 回归：真实地图模式仍正常
    document.getElementById('mq-back').click();
    document.querySelector('#metro-setup .opt-card[data-v="geo"]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 1500));
    const g2 = MetroQuiz.__game();
    log.push({ step: 'geo-regression', kind: g2.renderer.kind,
      zoom: g2.renderer.__internals.map.getZoom(),
      tilesBarVisible: !document.querySelector('#metro-view .metro-tiles').hidden });
    return log;
  })()`);

  console.log('VERIFY_RESULT ' + JSON.stringify(out));
  console.log('CONSOLE_ERRORS ' + JSON.stringify(errors.slice(0, 5)));
  app.exit(0);
}).catch(err => { console.error('VERIFY_FAIL', err); app.exit(1); });
