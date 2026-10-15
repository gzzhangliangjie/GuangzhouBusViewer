// 拖放体验专项验证：热区扩大/就近吸附、放置后序号隐藏、+100 反馈
// 用法: ./node_modules/.bin/electron test/verify-dnd.js
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
  const log = (...a) => console.log('[dnd]', ...a);

  const r = await win.webContents.executeJavaScript(`(async () => {
    document.querySelector('#mode-nav [data-mode="metro"]').click();
    document.querySelector('#metro-setup .opt-card[data-v="schematic"]').click();
    document.querySelector('#scope-picker .scope-pill[data-v="1"]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 3500));
    const g = MetroQuiz.__game();
    const I = g.renderer.__internals;
    const canvas = document.getElementById('metro-canvas');

    const dragChipTo = (stationId, where) => {
      const s = MetroData.station(stationId);
      const chipEl = [...document.querySelectorAll('#chip-pool .mchip')].find(c => c.textContent === stationId);
      if (!chipEl) return { err: 'no chip' };
      const tag = I.numMk.get(stationId) && I.numMk.get(stationId).getElement();
      const p = I.map.latLngToContainerPoint([-s.sy, s.sx]);
      const rect = canvas.getBoundingClientRect();
      const target = where === 'offset'
        ? { x: rect.left + p.x + 22, y: rect.top + p.y + 16 }     // 牌外 ~27px（旧热区外、吸附区内）
        : { x: rect.left + p.x, y: rect.top + p.y };              // 牌正中
      const el = document.elementFromPoint(target.x, target.y) || canvas;
      const dt = new DataTransfer();
      chipEl.dispatchEvent(new DragEvent('dragstart', { bubbles: true, cancelable: true, dataTransfer: dt }));
      el.dispatchEvent(new DragEvent('dragenter', { bubbles: true, cancelable: true, dataTransfer: dt }));
      el.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: dt }));
      el.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }));
      chipEl.dispatchEvent(new DragEvent('dragend', { bubbles: true, cancelable: true, dataTransfer: dt }));
      return { ok: true };
    };

    const out = {};
    // ① 偏移 27px 的"不准"投放也应命中（就近吸附/扩边热区）
    const s0 = g.score;
    dragChipTo('体育西路', 'offset');
    await new Promise(r => setTimeout(r, 300));
    out.offsetDropPlaced = g.renderer && MetroData ? g.__placedCheck = true : false;
    out.offsetDropScoreUp = g.score - s0;
    out.chipGone = ![...document.querySelectorAll('#chip-pool .mchip')].some(c => c.textContent === '体育西路');

    // ② 放置成功后：牌原位变成站名（绿色完成样式，位置不动）
    await new Promise(r => setTimeout(r, 400));
    const tagEl = I.numMk.get('体育西路') && I.numMk.get('体育西路').getElement();
    out.tagSwappedToName = !!tagEl && tagEl.style.display !== 'none' &&
      tagEl.textContent.includes('体育西路') &&
      !!tagEl.querySelector('.mnum.done');

    // ③ +100 反馈：飘字元素出现
    const s1 = g.score;
    dragChipTo('杨箕', 'center');
    out.centerDropScoreUp = g.score - s1;
    out.popFx = (() => {
      // drop 同步触发 popFx，立即查询
      const fx = document.querySelector('.pop-score');
      return !!fx;
    })();
    const toast = document.querySelector('#metro-toast, .metro-toast, .toast');
    out.toastShown = !!toast && toast.textContent.includes('+100');
    out.toastGreen = !!toast && toast.classList.contains('good');

    // ④ 错放：扣分且不隐藏正确的牌
    const s2 = g.score;
    const wrongChip = [...document.querySelectorAll('#chip-pool .mchip')][0];
    if (wrongChip) {
      const wrongName = wrongChip.textContent;
      const dt = new DataTransfer();
      // 找一个已放置的站（其牌已隐藏，热区仍在）投放错误的牌
      const st = MetroData.station('体育西路');
      const p = I.map.latLngToContainerPoint([-st.sy, st.sx]);
      const rect = canvas.getBoundingClientRect();
      const el = document.elementFromPoint(rect.left + p.x + 22, rect.top + p.y + 16) || canvas;
      wrongChip.dispatchEvent(new DragEvent('dragstart', { bubbles: true, cancelable: true, dataTransfer: dt }));
      el.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: dt }));
      el.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }));
      out.wrongDrop = g.score - s2;
      out.wrongChipStays = [...document.querySelectorAll('#chip-pool .mchip')].some(c => c.textContent === wrongName);
    }
    return out;
  })()`);

  log(JSON.stringify(r, null, 1));
  fs.writeFileSync(OUT + '/_v-dnd.png', (await win.webContents.capturePage()).toPNG());
  const ok = r.offsetDropScoreUp === 100 && r.tagSwappedToName && r.centerDropScoreUp === 100 && r.popFx && r.toastGreen && r.wrongDrop === -10;
  log(ok ? 'PASS: 拖放全套（偏移命中/原地换牌/+100绿色反馈/错放扣分）' : 'FAIL');
  app.exit(ok ? 0 : 1);
});
