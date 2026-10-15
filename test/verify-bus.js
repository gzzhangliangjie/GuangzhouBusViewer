// 公交模式离线兜底验证：清空缓存 → 镜像失败 → 必须用随包快照把线路列表填出来
// 用法: ./node_modules/.bin/electron test/verify-bus.js
const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

const OUT = 'E:/GuangzhouBusViewer/assets';

app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1400, height: 860, show: true,
    webPreferences: { preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true } });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));
  const log = (...a) => console.log('[bus]', ...a);

  // 清掉 localStorage 里的公交缓存，强制走兜底链
  await win.webContents.executeJavaScript(`localStorage.removeItem('gzbus.index.v1'); 'cleared'`);

  // 重载页面触发 loadIndex
  await win.loadFile(path.join(__dirname, '..', 'index.html'));

  // 轮询最多 240s：等镜像轮询失败后落到快照
  let r = null;
  for (let i = 0; i < 80; i++) {
    await new Promise(res => setTimeout(res, 3000));
    r = await win.webContents.executeJavaScript(`(() => ({
      items: document.querySelectorAll('#line-list li').length,
      status: document.querySelector('#status') ? document.querySelector('#status').textContent : '',
      count: document.querySelector('#line-count') ? document.querySelector('#line-count').textContent : ''
    }))()`);
    if (r.items > 100) break;
  }
  log(JSON.stringify(r, null, 1));
  fs.writeFileSync(OUT + '/_v-bus.png', (await win.webContents.capturePage()).toPNG());
  const ok = r.items > 100 && !/失败/.test(r.status) ;
  log(ok ? `PASS: 离线兜底生效，列表 ${r.items} 条` : 'FAIL: 列表未加载（' + r.status.slice(0, 80) + '）');
  app.exit(ok ? 0 : 1);
});
