// 截图证明: 线号模式无色起步(黑槽+灰胶囊) + 放一枚整线自动补齐上色
const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: 1400, height: 900, show: true,
    webPreferences: {
      preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true,
      backgroundThrottling: false
    }
  });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));
  const shot = async name => {
    win.webContents.invalidate();
    await new Promise(r => setTimeout(r, 300));
    const img = await win.webContents.capturePage();
    fs.writeFileSync(path.join(__dirname, '..', 'data', name), img.toPNG());
  };

  // ① 全网线号模式开局: 41 黑槽 + 灰色线号胶囊池
  await win.webContents.executeJavaScript(`(async () => {
    document.querySelector('#mode-nav [data-mode="metro"]').click();
    await new Promise(r => setTimeout(r, 300));
    document.querySelector('#metro-setup .opt-card[data-v="badge"]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 3000));
  })()`);
  await shot('_proof-mbslot-network-start.png');

  // ② 放 1号线: 选中池里"1号线"牌（池是洗过的，不能点第一枚），点西塱端槽位 → 两端自动补齐上色
  await win.webContents.executeJavaScript(`(async () => {
    const g = MetroQuiz.__game();
    const it = g.renderer.__internals;
    const key = [...it.slots.keys()].find(k => k === '1号线|西塱');
    const chip = [...document.querySelectorAll('#chip-pool .mchip-badge')]
      .find(e => e.textContent === '1号线');
    chip.click();
    it.slots.get(key).el.click();
    await new Promise(r => setTimeout(r, 400));
    // 视野推近 1 号线西塱端看上色效果
    const st = window.QUIZ_NETWORK_DATA.stations['西塱'];
    it.map.setView([-st.y, st.x], 0.5, { animate: false });
    await new Promise(r => setTimeout(r, 400));
  })()`);
  await shot('_proof-mbslot-line1-filled.png');

  console.log('shots done');
  app.exit(0);
}).catch(e => { console.error(e); app.exit(2); });
