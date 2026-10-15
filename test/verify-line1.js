// 隔离实例复现：点 1 路 → 读 fit bounds 日志 + 点击后的瓦片坐标（必须回到广州区域）
const { app, BrowserWindow } = require('electron');
const path = require('path');

app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
app.setPath('userData', require('path').join(__dirname, '..', 'assets', '_test-profile'));
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1400, height: 860, show: true,
    webPreferences: { preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true } });
  const logs = [];
  win.webContents.on('console-message', (_e, _l, m) => { if (m.includes('[fit]')) logs.push(m.trim()); });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));

  const r = await win.webContents.executeJavaScript(`(async () => {
    for (let i = 0; i < 60; i++) {
      if (document.querySelectorAll('#line-list li').length > 100) break;
      await new Promise(r => setTimeout(r, 1000));
    }
    const search = document.querySelector('#search');
    search.value = '1';
    search.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise(r => setTimeout(r, 300));
    const li = [...document.querySelectorAll('#line-list li')].find(x => x.dataset.ref === '1');
    if (!li) return { err: 'no li' };
    li.click();
    await new Promise(r => setTimeout(r, 5000));
    const tiles = [...document.querySelectorAll('#map .leaflet-tile')].map(t =>
      (t.src.match(/[?&](x=[0-9]+&y=[0-9]+&z=[0-9]+)/) || [])[1]).filter(Boolean);
    return {
      status: document.querySelector('#status').textContent.slice(0, 50),
      tileSample: [...new Set(tiles)].slice(0, 4),
      // 广州 z13 应为 x≈2650-2660, y≈1335-1345
      gzTiles: tiles.some(t => /x=26[0-9]{2}&y=13[0-9]{2}&z=13/.test(t) || /x=132[0-9]&y=66[0-9]&z=12/.test(t))
    };
  })()`);
  console.log('[line1]', JSON.stringify(r, null, 1));
  console.log('[fit-logs]', JSON.stringify(logs));
  app.exit(0);
});
