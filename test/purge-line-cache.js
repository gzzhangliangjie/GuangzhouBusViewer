// 清除 localStorage 中带 null 经度的坏线路缓存（索引缓存保留）
const { app, BrowserWindow } = require('electron');
const path = require('path');
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 500, height: 300, show: false });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));
  const n = await win.webContents.executeJavaScript(`(function () {
    const doomed = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith('gzbus.line.')) doomed.push(k);
    }
    doomed.forEach(k => localStorage.removeItem(k));
    const keys = [];
    for (let i = 0; i < localStorage.length; i++) keys.push(localStorage.key(i));
    return { n: doomed.length, keys };
  })()`);
  console.log('purge view:', JSON.stringify(n));
  await new Promise(r => setTimeout(r, 1500));   // 等 LevelDB 落盘，防止 app.exit 截断写回
  app.exit(0);
});
