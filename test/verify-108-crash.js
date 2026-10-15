// 复现"选108后无路线且地图消失"：控制台错误 + 地图 DOM 状态 + 截图
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
  win.webContents.on('console-message', (_e, _l, m) => { if (/error|uncaught|failed|异常/i.test(m)) errs.push(m.slice(0, 300)); });
  win.webContents.on('render-process-gone', (_e, d) => errs.push('RENDER-GONE: ' + d.reason));
  await win.loadFile(path.join(__dirname, '..', 'index.html'));

  const r = await win.webContents.executeJavaScript(`(async () => {
    for (let i = 0; i < 100; i++) {
      if (document.querySelectorAll('#line-list li').length > 100) break;
      await new Promise(r => setTimeout(r, 1000));
    }
    const before = {
      tiles: document.querySelectorAll('.leaflet-tile').length,
      container: !!document.querySelector('#map .leaflet-container'),
      mapVisible: (() => { const m = document.querySelector('#map'); return m && m.offsetParent !== null; })()
    };
    const search = document.querySelector('#search');
    search.value = '108';
    search.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise(r => setTimeout(r, 300));
    const li = [...document.querySelectorAll('#line-list li')].find(x => x.dataset.ref === '108');
    if (!li) return { err: 'no 108 li', status: document.querySelector('#status').textContent.slice(0, 60) };
    li.click();
    await new Promise(r => setTimeout(r, 4000));
    return {
      before,
      status: document.querySelector('#status').textContent.slice(0, 90),
      after: {
        tiles: document.querySelectorAll('.leaflet-tile').length,
        container: !!document.querySelector('#map .leaflet-container'),
        containerChildren: document.querySelector('#map') ? document.querySelector('#map').children.length : -1,
        svgPaths: document.querySelectorAll('#map svg path').length,
        detail: document.querySelector('#line-detail') ? document.querySelector('#line-detail').textContent.slice(0, 60) : null
      }
    };
  })()`);
  console.log('[v108c]', JSON.stringify(r, null, 1));
  console.log('[console errors]', JSON.stringify(errs.slice(0, 8), null, 1));
  fs.writeFileSync('E:/GuangzhouBusViewer/assets/_v-108.png', (await win.webContents.capturePage()).toPNG());
  app.exit(0);
});
