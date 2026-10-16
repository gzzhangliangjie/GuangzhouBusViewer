// 逐线截图：每条线单独打开纯线路图模式，截图存 assets/lineshots/
const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1600, height: 900, show: true,
    webPreferences: { preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true } });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));

  const OUT = path.join(__dirname, '..', 'assets', 'lineshots');
  fs.mkdirSync(OUT, { recursive: true });

  const REFS = ['1','2','3','4','5','6','7','8','9','10','11','12','13','14','18','21','22','GF','APM'];
  const evalJS = async (expr, ms = 30000) => {
    const pr = win.webContents.executeJavaScript(expr);
    const t = new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), ms));
    return Promise.race([pr, t]);
  };

  for (const ref of REFS) {
    const file = path.join(OUT, `line-${ref}.png`);
    if (fs.existsSync(file) && fs.statSync(file).size > 50000) { console.log('skip', ref); continue; }
    try {
      await evalJS(`(async () => {
        document.querySelector('#mode-nav [data-mode="metro"]').click();
        document.querySelector('#metro-setup .opt-card[data-v="schematic"]').click();
        // 如果有正在进行的游戏，先回设置
        const back = document.querySelector('#metro-back, [data-action="back"]');
        if (back) back.click();
        await new Promise(r => setTimeout(r, 300));
        // 选线
        const pill = document.querySelector('#scope-picker .scope-pill[data-v="${ref}"]');
        if (!pill) return 'no pill ${ref}';
        pill.click();
        await new Promise(r => setTimeout(r, 200));
        document.getElementById('metro-start').click();
        await new Promise(r => setTimeout(r, 4000));
        return 'ok';
      })()`, 40000);
      await new Promise(r => setTimeout(r, 1000));
      fs.writeFileSync(file, (await win.webContents.capturePage()).toPNG());
      console.log('saved line-' + ref + '.png');
    } catch (e) {
      console.log('ERR line-' + ref + ': ' + e.message.slice(0, 60));
    }
  }
  console.log('ALL DONE');
  app.exit(0);
});
