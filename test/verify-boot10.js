// 启动10秒验收：瓦片可见 + 列表就绪 + 截图
const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
app.setPath('userData', require('path').join(__dirname, '..', 'assets', '_test-profile'));
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1400, height: 860, show: true,
    webPreferences: { preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true } });
  const errs = [];
  win.webContents.on('console-message', (_e, _l, m) => { if (/error|uncaught|failed/i.test(m)) errs.push(m.slice(0, 200)); });
  win.webContents.on('render-process-gone', (_e, d) => errs.push('RENDER-GONE: ' + d.reason));
  const t0 = Date.now();
  await win.loadFile(path.join(__dirname, '..', 'index.html'));
  await new Promise(r => setTimeout(r, 10000));   // 满 10 秒
  let r = null;
  try {
    r = await win.webContents.executeJavaScript(`(function () {
      try {
        return {
          tiles: document.querySelectorAll('.leaflet-tile').length,
          tilesLoaded: document.querySelectorAll('.leaflet-tile-loaded').length,
          hasMap: (document.getElementById('map') || {}).classList ? document.getElementById('map').classList.contains('leaflet-container') : false,
          mapSize: (function () { const m = document.getElementById('map'); return m ? m.offsetWidth + 'x' + m.offsetHeight : 'null'; })(),
          listLi: document.querySelectorAll('#line-list li').length,
          status: (document.querySelector('#status') || {}).textContent || '',
          count: (document.querySelector('#line-count') || {}).textContent || ''
        };
      } catch (e) { return { evalErr: String(e && e.message || e) }; }
    })()`);
  } catch (e) {
    r = { scriptErr: String(e && e.message || e).slice(0, 150) };
  }
  const line = '[boot10] ' + ((Date.now() - t0) / 1000).toFixed(1) + 's ' + JSON.stringify(r) + ' errors=' + JSON.stringify(errs.slice(0, 5));
  fs.appendFileSync('E:/GuangzhouBusViewer/assets/_boot10.log', line + '\n');
  console.log(line);
  fs.writeFileSync('E:/GuangzhouBusViewer/assets/_v-boot10.png', (await win.webContents.capturePage()).toPNG());
  app.exit(0);
});
