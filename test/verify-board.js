// 纯线路图（向量棋盘）验证：全网 + 1号线单线 + 官方图浏览
// 用法: ./node_modules/.bin/electron test/verify-board.js
const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

const OUT = 'E:/GuangzhouBusViewer/assets';

app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1400, height: 860, show: true,
    webPreferences: { preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true } });
  const errors = [];
  win.webContents.on('console-message', (_e, _l, m) => { if (/error|failed/i.test(m)) errors.push(m); });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));
  const log = (...a) => console.log('[verify]', ...a);

  // ① 1 号线单线（含多级缩放稳定性 + 底图对齐）
  let r = await win.webContents.executeJavaScript(`(async () => {
    document.querySelector('#mode-nav [data-mode="metro"]').click();
    document.querySelector('#metro-setup .opt-card[data-v="schematic"]').click();
    document.querySelector('#scope-picker .scope-pill[data-v="1"]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 3000));
    const g = MetroQuiz.__game();
    const chip = [...document.querySelectorAll('#chip-pool .mchip')].find(c => c.textContent === '体育西路');
    chip.click();
    g.renderer.__internals.stationMk.get('体育西路').fire('click');
    const art = document.querySelector('#metro-canvas .board-art');
    // 对齐校验: 底图两角与地图投影一致
    const map = g.renderer.__internals.map;
    const p1 = map.latLngToContainerPoint(L.latLng(0, 0));
    const p2 = map.latLngToContainerPoint(L.latLng(-2054.25, 2848.5));
    const rect = art.getBoundingClientRect();
    const canvas = document.getElementById('metro-canvas').getBoundingClientRect();
    const align = {
      dx: Math.round(rect.left - (canvas.left + p1.x)),
      dy: Math.round(rect.top - (canvas.top + p1.y)),
      dw: Math.round(rect.width - (p2.x - p1.x)),
      dh: Math.round(rect.height - (p2.y - p1.y))
    };
    return { score: g.score, kind: g.renderer.kind,
      artLoaded: !!art, align,
      visibleLineGroups: (() => { const lg = art.querySelector('[id="线路"]'); return lg ? [...lg.children].filter(g => g.tagName === 'g' && g.style.display !== 'none').length : 0; })(),
      artTextFree: ['站名','图标','左上图例'].every(id => { const g = art.querySelector('[id="' + id + '"]'); return !g || getComputedStyle(g).display === 'none'; }) };
  })()`);
  log('line1', JSON.stringify(r));
  fs.writeFileSync(OUT + '/_v3-line1.png', (await win.webContents.capturePage()).toPNG());
  // 缩放稳定性: 在 0 / 1 / -1 级各截一次检查线仍在
  const zoomShots = [];
  for (const z of [0, 1, -1, 0.5]) {
    await win.webContents.executeJavaScript(`(async () => {
      MetroQuiz.__game().renderer.__internals.map.setZoom(${z});
      await new Promise(r => setTimeout(r, 700));
    })()`);
    const f = OUT + '/_v3-z' + z + '.png';
    fs.writeFileSync(f, (await win.webContents.capturePage()).toPNG());
    zoomShots.push(f);
  }
  log('zoom shots ok');

  // ② 全网（站名模式：底图站名应隐藏；线号徽章可见）
  r = await win.webContents.executeJavaScript(`(async () => {
    document.getElementById('mq-back').click();
    document.querySelector('#scope-picker .scope-pill[data-v]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 3000));
    const art = document.querySelector('#metro-canvas .board-art');
    return { artTextFree: ['站名','图标','左上图例'].every(id => { const g = art.querySelector('[id="' + id + '"]'); return !g || getComputedStyle(g).display === 'none'; }),
             nums: [...document.querySelectorAll('#metro-canvas .mnum-wrap')].filter(e => e.style.display !== 'none').length,
             badges: document.querySelectorAll('#metro-canvas .mbadge').length,
             hotZones: document.querySelectorAll('#metro-canvas path.mst-hot').length };
  })()`);
  log('all-name-mode', JSON.stringify(r));
  fs.writeFileSync(OUT + '/_v3-all.png', (await win.webContents.capturePage()).toPNG());

  // ③ 线号模式（站名可见、徽章隐藏）
  r = await win.webContents.executeJavaScript(`(async () => {
    document.getElementById('mq-back').click();
    document.querySelector('#metro-setup .opt-card[data-v="badge"]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 3000));
    const labels = [...document.querySelectorAll('#metro-canvas .mlab')].map(e => e.textContent);
    return { labelCount: labels.length, hintNames: labels.length > 30 };
  })()`);
  log('badge-mode', JSON.stringify(r));
  fs.writeFileSync(OUT + '/_v3-badge.png', (await win.webContents.capturePage()).toPNG());

  // ③ 官方图浏览（内联矢量，无 img 元素，检查 board-art 存在）
  r = await win.webContents.executeJavaScript(`(async () => {
    document.getElementById('mq-back').click();
    document.getElementById('metro-answer').click();
    await new Promise(r => setTimeout(r, 1200));
    document.getElementById('mq-official').click();
    await new Promise(r => setTimeout(r, 3000));
    const art = document.querySelector('#metro-canvas .board-art');
    return { artLoaded: !!art, groups: art ? art.querySelectorAll('g').length : 0 };
  })()`);
  log('official', JSON.stringify(r));
  fs.writeFileSync(OUT + '/_v3-official.png', (await win.webContents.capturePage()).toPNG());

  log('ERRORS', JSON.stringify(errors.slice(0, 5)));
  app.exit(0);
}).catch(e => { console.error('[verify] FAIL', e); app.exit(1); });
