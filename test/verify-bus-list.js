// 公交模式列表秒出验证：断网场景（无缓存、快照兜底）列表必须在 15s 内渲染
const { app, BrowserWindow } = require('electron');
const path = require('path');

app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1400, height: 860, show: true,
    webPreferences: { preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true } });
  // 先正常加载一次（可能种下缓存），再清缓存断网重载模拟最差情况
  await win.loadFile(path.join(__dirname, '..', 'index.html'));
  await win.webContents.executeJavaScript(`localStorage.clear(); 'ok'`);
  const t0 = Date.now();
  try {
    await win.webContents.session.webRequest.onBeforeRequest({ urls: ['https://*/*'] }, (d, cb) => {
      cb({ cancel: true });
    });
  } catch (e) { console.log('webRequest 注册失败（忽略，可能已注册）:', e.message.slice(0, 80)); }
  try {
    await win.loadFile(path.join(__dirname, '..', 'index.html'));
  } catch (e) { console.log('loadFile 异常（继续轮询）:', e.message.slice(0, 80)); }
  let r = null;
  for (let i = 0; i < 15; i++) {
    await new Promise(res => setTimeout(res, 1000));
    r = await win.webContents.executeJavaScript(`({
      n: document.querySelectorAll('#line-list li').length,
      st: document.querySelector('#status').textContent.slice(0, 70),
      c: document.querySelector('#line-count').textContent
    })()`);
    if (r.n > 100) break;
  }
  console.log('[buslist]', JSON.stringify(r), ((Date.now() - t0) / 1000).toFixed(1) + 's');
  const ok = r.n > 100;
  console.log(ok ? 'PASS: 断网+无缓存 列表仍秒出' : 'FAIL');
  app.exit(ok ? 0 : 1);
});
