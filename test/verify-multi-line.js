// 多线路共存场景：先加载 1、2 号线，再点 108 —— 地图必须保持存活且 108 出图
const { app, BrowserWindow } = require('electron');
const path = require('path');

app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
app.setPath('userData', require('path').join(__dirname, '..', 'assets', '_test-profile'));
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1400, height: 860, show: true,
    webPreferences: { preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true } });
  const errs = [];
  win.webContents.on('console-message', (_e, _l, m) => { if (/error|uncaught/i.test(m)) errs.push(m.slice(0, 200)); });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));

  const clickRef = async ref => {
    const r = await win.webContents.executeJavaScript(`(async () => {
      const search = document.querySelector('#search');
      search.value = ${JSON.stringify(ref)};
      search.dispatchEvent(new Event('input', { bubbles: true }));
      await new Promise(r => setTimeout(r, 250));
      const li = [...document.querySelectorAll('#line-list li')].find(x => x.dataset.ref === ${JSON.stringify(ref)});
      if (!li) return { err: 'no li' };
      li.click();
      for (let i = 0; i < 45; i++) {
        const st = document.querySelector('#status').textContent;
        if (/已加载|未在 OSM|失败/.test(st)) {
          return { st: st.slice(0, 50),
            paths: document.querySelectorAll('#map svg path').length,
            tiles: document.querySelectorAll('.leaflet-tile').length,
            actives: document.querySelectorAll('#active-lines .tag, #active-lines li, #active-lines span').length };
        }
        await new Promise(r => setTimeout(r, 1000));
      }
      return { timeout: true, st: document.querySelector('#status').textContent.slice(0, 50) };
    })()`);
    console.log('[multi]', JSON.stringify(r));
    return r;
  };

  await new Promise(r => setTimeout(r, 6000));   // 等列表就绪
  const a = await clickRef('1');
  const b = await clickRef('B7');
  const c = await clickRef('108');
  const ok = a.paths > 0 && c.paths > 0 && c.st && /已加载 108/.test(c.st) && c.tiles > 0;
  console.log('[multi]', ok ? 'PASS: 多线共存+108 正常' : 'FAIL');
  console.log('[errs]', JSON.stringify(errs.slice(0, 5)));
  app.exit(ok ? 0 : 1);
});
