// 目标验证：文字动态化 / 单线模式规则 / 拖拽放置 / 截图确认
// 用法: ./node_modules/.bin/electron test/verify-goal.js
const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');
const OUT = 'E:/GuangzhouBusViewer/assets';

app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1600, height: 1000, show: true,
    webPreferences: { preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true } });
  win.maximize();
  const errors = [];
  win.webContents.on('console-message', (_e, _l, m) => { if (/error|failed/i.test(m)) errors.push(m.slice(0, 120)); });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));
  const log = (...a) => console.log('[goal]', ...a);
  const shot = async name => {
    fs.writeFileSync(`${OUT}/_g-${name}.png`, (await win.webContents.capturePage()).toPNG());
    log('shot', name);
  };

  // ===== ① 全网站名模式：底图无文字 + 序号牌 + 胶囊徽章 =====
  let r = await win.webContents.executeJavaScript(`(async () => {
    document.querySelector('#mode-nav [data-mode="metro"]').click();
    document.querySelector('#metro-setup .opt-card[data-v="schematic"]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 3000));
    const art = document.querySelector('#metro-canvas .board-art');
    const hidden = ['站名','图标','左上图例','左','右','左下','右上'].map(id => {
      const g = art.querySelector('[id="' + id + '"]');
      return g ? getComputedStyle(g).display === 'none' : 'missing';
    });
    return {
      artTextFree: hidden.every(v => v === true),
      nums: [...document.querySelectorAll('#metro-canvas .mnum-wrap')].filter(e => e.style.display !== 'none').length,
      badges: document.querySelectorAll('#metro-canvas .mbadge').length
    };
  })()`);
  log('G1 全网无文字+动态元素', JSON.stringify(r));
  await shot('all');

  // ===== ② 1 号线单线：其他线可见 + 未选线站名显示 + 所选线藏名显序号 + 拖拽放置 =====
  r = await win.webContents.executeJavaScript(`(async () => {
    document.getElementById('mq-back').click();
    document.querySelector('#scope-picker .scope-pill[data-v="1"]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 3000));
    const art = document.querySelector('#metro-canvas .board-art');
    const linesLayer = art.querySelector('[id="线路"]');
    const visibleLineGroups = linesLayer ? [...linesLayer.children].filter(g => g.tagName === 'g' && g.style.display !== 'none').length : -1;
    const g = MetroQuiz.__game();
    // 标签文本抽样：应含未选线站名（如 公园前? 不—公园前在1号线上。用 体育中心(1号线,应无标签) vs 滘口(5号线,应有标签)）
    const labels = [...document.querySelectorAll('#metro-canvas .mlab')].map(e => e.textContent);
    const nums = [...document.querySelectorAll('#metro-canvas .mnum-wrap')].filter(e => e.style.display !== 'none').length;
    return {
      lineGroupsVisible: visibleLineGroups,
      hasHintName: labels.includes('滘口') || labels.includes('广州东站') === false && labels.length > 0,
      labelCount: labels.length,
      scopeLabels: labels.filter(t => ['体育西路','公园前','西塱','杨箕'].includes(t)).length,
      nums
    };
  })()`);
  log('G2 单线规则', JSON.stringify(r));
  await shot('line1');

  // ===== ③ 拖拽放置（合成 DragEvent + DataTransfer） =====
  r = await win.webContents.executeJavaScript(`(async () => {
    const g = MetroQuiz.__game();
    const internals = g.renderer.__internals;
    // 找一个未放置的 1 号线站名名牌
    const chip = [...document.querySelectorAll('#chip-pool .mchip')].find(c => c.textContent === '体育西路');
    if (!chip) return { err: 'chip not found' };
    const mk = internals.stationMk.get('体育西路');
    const el = mk.getElement();
    if (!el) return { err: 'no element' };
    const dt = new DataTransfer();
    chip.dispatchEvent(new DragEvent('dragstart', { bubbles: true, cancelable: true, dataTransfer: dt }));
    const dataAtStart = dt.getData('text/plain');
    el.dispatchEvent(new DragEvent('dragenter', { bubbles: true, cancelable: true, dataTransfer: dt }));
    el.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: dt }));
    const dropOk = el.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }));
    chip.dispatchEvent(new DragEvent('dragend', { bubbles: true, dataTransfer: dt }));
    return { dataAtStart, dropOk, score: g.score, chipGone: !chip.isConnected };
  })()`);
  log('G3 拖拽', JSON.stringify(r));
  await shot('afterdrag');

  // ===== ④ 放置后：所选线该站站名出现 =====
  r = await win.webContents.executeJavaScript(`(async () => {
    await new Promise(r => setTimeout(r, 600));
    const labels = [...document.querySelectorAll('#metro-canvas .mlab')].map(e => e.textContent);
    return { placedLabelShown: labels.includes('体育西路') };
  })()`);
  log('G4 放置后标签', JSON.stringify(r));
  await shot('placed');

  log('ERRORS', JSON.stringify(errors.slice(0, 6)));
  app.exit(0);
}).catch(e => { console.error('[goal] FAIL', e); app.exit(1); });
