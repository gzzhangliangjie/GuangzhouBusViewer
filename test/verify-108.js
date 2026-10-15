// 复现用户操作：公交模式点 108 → 必须秒出几何（快照优先）
const { app, BrowserWindow } = require('electron');
const path = require('path');

app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1400, height: 860, show: true,
    webPreferences: { preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true } });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));
  const t0 = Date.now();
  const r = await win.webContents.executeJavaScript(`(async () => {
    // 等索引就绪
    for (let i = 0; i < 100; i++) {
      if (document.querySelectorAll('#line-list li').length > 100) break;
      await new Promise(r => setTimeout(r, 1000));
    }
    // 列表默认只渲染前 500 条，先用搜索过滤出 108
    const search = document.querySelector('#search');
    search.value = '108';
    search.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise(r => setTimeout(r, 300));
    const li = [...document.querySelectorAll('#line-list li')].find(x => x.dataset.ref === '108');
    if (!li) return { err: '列表中无 108', status: document.querySelector('#status').textContent.slice(0, 60) };
    li.click();
    const t1 = performance.now();
    // 等加载完成（状态含"已加载"或超时 150s）
    for (let i = 0; i < 150; i++) {
      const st = document.querySelector('#status').textContent;
      if (/已加载 108|未在 OSM|失败/.test(st)) return { status: st, ms: Math.round(performance.now() - t1) };
      await new Promise(r => setTimeout(r, 1000));
    }
    return { err: '超时', status: document.querySelector('#status').textContent };
  })()`);
  console.log('[v108]', JSON.stringify(r), 'total', Date.now() - t0, 'ms');
  app.exit(r.status && /已加载 108/.test(r.status) && r.ms < 10000 ? 0 : 1);
});
