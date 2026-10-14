// Electron 渲染层冒烟测试：加载 index.html，等待 did-finish-load，
// 检查 Leaflet 与页面模块是否就绪，输出结果后退出。
// 用法: ./node_modules/.bin/electron test/smoke-main.js
const { app, BrowserWindow } = require('electron');
const path = require('path');

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: 1000, height: 700, show: false,
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

  const result = await win.webContents.executeJavaScript(`({
    leaflet: typeof L !== 'undefined' && !!L.version,
    overpass: typeof Overpass !== 'undefined',
    mapLayer: typeof MapLayer !== 'undefined',
    appHooks: typeof AppHooks !== 'undefined',
    mapContainer: !!document.getElementById('map'),
    statusText: document.getElementById('status') ? document.getElementById('status').textContent.slice(0, 60) : null
  })`);

  console.log('SMOKE_RESULT ' + JSON.stringify(result));
  console.log('CONSOLE_ERRORS ' + JSON.stringify(errors));
  app.exit(0);
}).catch(err => { console.error('SMOKE_FAIL', err); app.exit(1); });
