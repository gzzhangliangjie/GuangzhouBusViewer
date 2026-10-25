// 官方线网图拼图验收：MetroBoard 渲染/判分/单线/编号模式/答案图 全流程（真实 UI 事件）
// 用法: ./node_modules/.bin/electron test/verify-official-board.js
const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

const SHOT_DIR = path.join(__dirname, '..', 'data');

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: 1400, height: 900, show: true,   // capturePage 对隐藏窗口会截空白，必须可见
    webPreferences: {
      preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true
    }
  });
  const errors = [];
  win.webContents.on('console-message', (_e, _lvl, msg) => {
    if (/error|failed/i.test(msg) && !/_quiz-verify/.test(msg)) errors.push(msg);
  });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));

  const shot = async name => {
    const img = await win.webContents.capturePage();
    fs.writeFileSync(path.join(SHOT_DIR, '_quiz-official-' + name + '.png'), img.toPNG());
  };
  const results = [];
  const check = (name, ok, detail) => {
    results.push({ name, ok, detail });
    console.log((ok ? '  ok  ' : '  FAIL ') + name + (detail ? '  [' + detail + ']' : ''));
  };

  // ---------- ① 答案图（codes 全图，无隐藏） ----------
  const step1 = await win.webContents.executeJavaScript(`(async () => {
    document.querySelector('#mode-nav [data-mode="metro"]').click();
    await new Promise(r => setTimeout(r, 300));
    document.getElementById('metro-answer').click();
    await new Promise(r => setTimeout(r, 2500));
    const g = MetroQuiz.__game();
    const it = g.renderer.__internals;
    const svg = it.svg;
    return {
      kind: g.renderer.kind,
      loaded: !!svg,
      hasChips: !!(svg && svg.querySelector('#编号牌')),
      chipRects: svg ? svg.querySelectorAll('#编号牌 rect[fill="#FFFFFF"]').length : 0,
      texts: svg ? svg.querySelectorAll('#站名标注 text').length : 0,
      badges: svg ? svg.querySelectorAll('[data-badge="header"]').length : 0,
      hidden: it.hiddenCount
    };
  })()`);
  check('①答案图 codes 载入', step1.loaded && step1.hasChips, JSON.stringify(step1));
  check('①答案图 400 牌/318 文/41 徽标全可见',
    step1.chipRects === 400 && step1.texts === 318 && step1.badges === 41 && step1.hidden === 0,
    `牌${step1.chipRects} 文${step1.texts} 徽${step1.badges} 藏${step1.hidden}`);
  await shot('answer');

  // ---------- ② 站名模式（全网）：318 藏名 + 热区 + 正误判分 ----------
  const step2 = await win.webContents.executeJavaScript(`(async () => {
    document.getElementById('mq-back').click();
    await new Promise(r => setTimeout(r, 300));
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 2500));
    const g = MetroQuiz.__game();
    const it = g.renderer.__internals;
    return { kind: g.renderer.kind, hidden: it.hiddenCount, hotspots: it.hotspots.size,
      dock: document.querySelectorAll('#chip-pool .mchip').length,
      score: g.score, prog: document.getElementById('mq-prog').textContent };
  })()`);
  check('②站名模式 318 名隐藏/热区318/池318',
    step2.kind === 'official' && step2.hidden === 318 && step2.hotspots === 318 && step2.dock === 318,
    JSON.stringify(step2));

  const step3 = await win.webContents.executeJavaScript(`(async () => {
    const g = MetroQuiz.__game();
    const hot = g.renderer.__internals.hotspots;
    const pick = nm => [...document.querySelectorAll('#chip-pool .mchip')]
      .find(e => e.textContent === nm);
    // 放对：西塱
    pick('西塱').click();
    hot.get('西塱').fire('click');
    await new Promise(r => setTimeout(r, 200));
    const afterOk = { score: g.score, prog: document.getElementById('mq-prog').textContent,
      hot: hot.size };
    // 放错：公园前 -> 广州东站
    pick('公园前').click();
    hot.get('广州东站').fire('click');
    await new Promise(r => setTimeout(r, 200));
    const afterBad = { score: g.score, wrongs: g.wrongs };
    // 提示：自动放置一枚
    document.getElementById('mq-hint').click();
    await new Promise(r => setTimeout(r, 200));
    return { afterOk, afterBad, afterHint: { score: g.score, hints: g.hints,
      dock: document.querySelectorAll('#chip-pool .mchip').length } };
  })()`);
  check('②放对 +100', step3.afterOk.score === 100 && step3.afterOk.prog === '1/318' && step3.afterOk.hot === 317,
    JSON.stringify(step3.afterOk));
  check('②放错 −10（牌不消耗）', step3.afterBad.score === 90 && step3.afterBad.wrongs === 1, JSON.stringify(step3.afterBad));
  check('②提示 −50 自动放置', step3.afterHint.score === 40 && step3.afterHint.hints === 1 && step3.afterHint.dock === 316,
    JSON.stringify(step3.afterHint));

  // ---------- ③ 放置复原 = 原位元素（可见性翻转，坐标可解析） ----------
  const step4 = await win.webContents.executeJavaScript(`(async () => {
    const it = MetroQuiz.__game().renderer.__internals;
    const t = [...it.svg.querySelectorAll('#站名标注 text')].find(e => e.textContent === '西塱');
    return { visible: t && t.style.visibility !== 'hidden',
      x: t && parseFloat(t.getAttribute('x')), y: t && parseFloat(t.getAttribute('y')) };
  })()`);
  check('③西塱站名原位复原', step4.visible && isFinite(step4.x) && isFinite(step4.y), JSON.stringify(step4));

  // ---------- ④ 单线模式（3号线）：本线谜面+他线背景 + 走廊按色淡化 ----------
  const step5 = await win.webContents.executeJavaScript(`(async () => {
    document.getElementById('mq-back').click();
    await new Promise(r => setTimeout(r, 300));
    document.querySelector('#scope-picker .scope-pill[data-v="3"]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 2500));
    const g = MetroQuiz.__game();
    const it = g.renderer.__internals;
    const total = [...it.svg.querySelectorAll('#走廊 line')].length;
    const dimmed = [...it.svg.querySelectorAll('#走廊 line')]
      .filter(e => e.style.opacity && parseFloat(e.style.opacity) < 0.5).length;
    const kept = total - dimmed;
    const lineSt = Object.values(window.QUIZ_NETWORK_DATA.stations)
      .filter(s => s.lines.includes('3号线')).length;
    return { hotspots: it.hotspots.size, dock: document.querySelectorAll('#chip-pool .mchip').length,
      hidden: it.hiddenCount, lineSt, dimmed, kept, total };
  })()`);
  check('④3号线 池=本线站数(谜面)', step5.dock === step5.lineSt && step5.hidden === step5.lineSt,
    `池${step5.dock} 藏${step5.hidden} 本线${step5.lineSt} 热区${step5.hotspots}`);
  check('④走廊按色淡化(本线保留)', step5.kept > 5 && step5.dimmed === step5.total - step5.kept,
    `淡${step5.dimmed} 留${step5.kept}/总${step5.total}`);
  await shot('scope-line3');

  // ---------- ⑤ 编号模式：codes 棋盘 400 槽 + 正确放置复原 ----------
  const step6 = await win.webContents.executeJavaScript(`(async () => {
    document.getElementById('mq-back').click();
    await new Promise(r => setTimeout(r, 300));
    document.querySelector('#metro-setup .opt-card[data-v="code"]').click();
    document.querySelector('#scope-picker .scope-pill[data-v=""]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 3000));
    const g = MetroQuiz.__game();
    const it = g.renderer.__internals;
    const slots = it.slots.size;
    const pills = document.querySelectorAll('#dock-lines .dock-pill').length;
    // 放对：公园前|1号线（公园前是 1/2 号线换乘站，title 精确到线；牌坐标从配对数据取）
    const slotsBefore = it.slots.size;
    const dockBefore = document.querySelectorAll('#chip-pool .mchip').length;
    const rec = window.QUIZ_NETWORK_DATA.chips.find(c => c.nm === '公园前' && c.line === '1号线');
    const chipEl = [...document.querySelectorAll('#chip-pool .mchip-code')]
      .find(e => e.title === '公园前 · 1号线');
    chipEl.click();
    it.slots.get('公园前|1号线').el.click();
    await new Promise(r => setTimeout(r, 200));
    const rects = [...it.svg.querySelectorAll('#编号牌 rect[fill="#FFFFFF"]')].filter(r =>
      Math.abs(parseFloat(r.getAttribute('x')) - rec.x) < 0.05 &&
      Math.abs(parseFloat(r.getAttribute('y')) - rec.y) < 0.05);
    return { kind: g.renderer.kind, slotsBefore, dockBefore,
      slotsAfter: it.slots.size, pills: document.querySelectorAll('#dock-lines .dock-pill').length,
      score: g.score, prog: document.getElementById('mq-prog').textContent,
      placedVisible: rects.length === 1 && rects.every(r => r.style.visibility !== 'hidden') };
  })()`);
  check('⑤编号模式 400 槽/池400/线号过滤19+1', step6.slotsBefore === 400 && step6.dockBefore === 400 && step6.pills === 20,
    `槽${step6.slotsBefore} 池${step6.dockBefore} 药${step6.pills}`);
  check('⑤编号牌放对 +100 且原位复原',
    step6.score === 100 && step6.prog === '1/400' && step6.placedVisible &&
    step6.slotsAfter === 399,
    JSON.stringify({ score: step6.score, prog: step6.prog, placedVisible: step6.placedVisible, slotsAfter: step6.slotsAfter }));
  await shot('code-mode');

  // ---------- ⑥ 线号模式（广佛线）：徽标槽 + 放置 ----------
  const step7 = await win.webContents.executeJavaScript(`(async () => {
    document.getElementById('mq-back').click();
    await new Promise(r => setTimeout(r, 300));
    document.querySelector('#metro-setup .opt-card[data-v="badge"]').click();
    document.querySelector('#scope-picker .scope-pill[data-v="GF"]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 2500));
    const g = MetroQuiz.__game();
    const it = g.renderer.__internals;
    const slotOk = it.slots.has('广佛线');
    const badgeEl = document.querySelector('#chip-pool .mchip-badge');
    badgeEl.click();
    it.slots.get('广佛线').el.click();
    await new Promise(r => setTimeout(r, 200));
    const vis = [...it.svg.querySelectorAll('[data-badge="header"]')]
      .filter(gf => [...gf.querySelectorAll('text')].some(t => t.textContent.trim() === '广佛线'))
      .every(gf => gf.style.visibility !== 'hidden');
    return { slotOk, dock: document.querySelectorAll('#chip-pool .mchip').length,
      score: g.score, finished: g.finished, badgeVisible: vis };
  })()`);
  check('⑥广佛线徽标放对=完成', step7.slotOk && step7.dock === 0 && step7.score === 100 && step7.finished && step7.badgeVisible,
    JSON.stringify(step7));

  // ---------- ⑦ 真实地图风格回归（geo：站名模式照常可玩） ----------
  const step8 = await win.webContents.executeJavaScript(`(async () => {
    document.getElementById('mq-back').click();
    await new Promise(r => setTimeout(r, 300));
    document.querySelector('#metro-setup .opt-card[data-v="name"]').click();
    document.querySelector('#metro-setup .opt-card[data-v="geo"]').click();
    document.querySelector('#scope-picker .scope-pill[data-v=""]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 2500));
    const g = MetroQuiz.__game();
    return { kind: g.renderer.kind, dock: document.querySelectorAll('#chip-pool .mchip').length,
      expect: MetroData.allStations().length,
      tilesVisible: !document.getElementById('metro-view').querySelector('.metro-tiles').hidden };
  })()`);
  check('⑦geo 真实地图回归', step8.kind === 'geo' && step8.dock === step8.expect && step8.tilesVisible,
    JSON.stringify(step8));

  await win.webContents.executeJavaScript(
    `console.log('_quiz-verify done')`);
  console.log('\\nconsole errors:', errors.length ? errors : 'none');
  const fails = results.filter(r => !r.ok);
  console.log(fails.length ? 'VERIFY FAIL (' + fails.length + ')' : 'VERIFY ALL PASS (' + results.length + ')');
  app.exit(fails.length ? 1 : 0);
}).catch(e => { console.error(e); app.exit(2); });
