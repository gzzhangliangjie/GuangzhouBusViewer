// 在用户真实 profile（默认 userData）里验证 108：先清今天的 gzbus 缓存残骸再测
const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1400, height: 860, show: true,
    webPreferences: { preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true } });
  const errs = [];
  win.webContents.on('console-message', (_e, _l, m) => { if (/error|uncaught/i.test(m)) errs.push(m.slice(0, 200)); });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));
  // 清掉今天各种实验留下的公交缓存（数据会从随包快照即时重建）
  await win.webContents.executeJavaScript(`(function(){
    const doomed = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith('gzbus')) doomed.push(k);
    }
    doomed.forEach(k => localStorage.removeItem(k));
    return doomed.length;
  })()`).then(n => console.log('[real] cleared', n, 'gzbus keys'));
  await win.loadFile(path.join(__dirname, '..', 'index.html'));

  const r = await win.webContents.executeJavaScript(`(async () => {
    const t0 = performance.now();
    for (let i = 0; i < 60; i++) {
      if (document.querySelectorAll('#line-list li').length > 100) break;
      await new Promise(r => setTimeout(r, 1000));
    }
    const search = document.querySelector('#search');
    search.value = '108';
    search.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise(r => setTimeout(r, 300));
    const lis = [...document.querySelectorAll('#line-list li')].filter(x => x.dataset.ref === '108');
    lis[0].click();
    for (let i = 0; i < 60; i++) {
      const st = document.querySelector('#status').textContent;
      if (/已加载 108|未在 OSM|失败/.test(st)) {
        return { lis: lis.length, status: st.slice(0, 60), ms: Math.round(performance.now() - t0),
          paths: document.querySelectorAll('#map svg path').length,
          detail: (document.querySelector('#line-detail h3, #line-detail b, #line-detail') || {}).textContent || '' };
      }
      await new Promise(r => setTimeout(r, 1000));
    }
    return { timeout: true };
  })()`);
  console.log('[real]', JSON.stringify(r), 'errs:', JSON.stringify(errs.slice(0, 3)));
  fs.writeFileSync('E:/GuangzhouBusViewer/assets/_v-real108.png', (await win.webContents.capturePage()).toPNG());
  const ok = r.status && /已加载 108/.test(r.status) && r.paths >= 1;
  console.log(ok ? 'PASS' : 'FAIL');
  app.exit(ok ? 0 : 1);
});
