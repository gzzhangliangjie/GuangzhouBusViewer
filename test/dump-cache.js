// 从 app 同源 localStorage 导出 gzbus 缓存（索引 + 已缓存线路几何）
const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

const OUT = 'E:/GuangzhouBusViewer/assets';

app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 900, height: 600, show: false,
    webPreferences: { preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true } });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));
  const dump = await win.webContents.executeJavaScript(`(() => {
    const out = {};
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k.startsWith('gzbus')) out[k] = localStorage.getItem(k);
    }
    return out;
  })()`);
  for (const [k, v] of Object.entries(dump)) {
    const file = OUT + '/_ls-' + k.replace(/[^a-z0-9.]/gi, '_') + '.json';
    fs.writeFileSync(file, v);
    let info = '';
    try {
      const d = JSON.parse(v);
      info = (Array.isArray(d) ? 'array:' + d.length : Object.keys(d).join(',')) +
             (d && d.data ? ' data:' + (d.data.length || Object.keys(d.data).length) : '') +
             (d && d.at ? ' at:' + new Date(d.at).toISOString() : '');
    } catch (e) { info = 'parse-fail ' + e.message.slice(0, 60); }
    console.log(k, '->', file, v.length + 'B', info);
  }
  app.exit(0);
});
