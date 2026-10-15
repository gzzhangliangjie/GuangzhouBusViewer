// 验证：点广州 1 路后详情面板只显示本线方向（不再混东莞/深圳等同号城市线）
const { app, BrowserWindow } = require('electron');
const path = require('path');

app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
app.setPath('userData', require('path').join(__dirname, '..', 'assets', '_test-profile'));
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1400, height: 860, show: true,
    webPreferences: { preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true } });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));
  const r = await win.webContents.executeJavaScript(`(async () => {
    for (let i = 0; i < 60; i++) {
      if (document.querySelectorAll('#line-list li').length > 100) break;
      await new Promise(r => setTimeout(r, 1000));
    }
    // 搜"1路：" 精确找广州 1 路（名称以"1路："开头的记录）
    const search = document.querySelector('#search');
    search.value = '1路：芳村';
    search.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise(r => setTimeout(r, 300));
    const lis = [...document.querySelectorAll('#line-list li')];
    const li = lis.find(x => x.dataset.ref === '1') || lis[0];
    li.click();
    await new Promise(r => setTimeout(r, 3000));
    const tabs = [...document.querySelectorAll('#line-detail .dir-tabs button')].map(b => b.textContent.trim());
    const title = (document.querySelector('#line-detail .detail-title, #line-detail') || {}).textContent || '';
    return { tabs, n: tabs.length, title: title.slice(0, 50) };
  })()`);
  console.log('[tabs]', JSON.stringify(r, null, 1));
  const ok = r.n >= 1 && r.n <= 4 && r.tabs.every(t => /东山署前路|芳村花园/.test(t));
  console.log(ok ? 'PASS: 只剩本线方向' : 'FAIL: 仍有混入方向');
  app.exit(ok ? 0 : 1);
});
