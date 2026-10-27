// 官方线网图拼图验收：MetroBoard 渲染/判分/单线/胶囊形式/答案揭示 全流程（真实 UI 事件）
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
      contextIsolation: true, nodeIntegration: false, sandbox: true,
      backgroundThrottling: false   // 后台节流会让 capturePage 返回陈旧帧
    }
  });
  const errors = [];
  win.webContents.on('console-message', (_e, _lvl, msg) => {
    if (/error|failed/i.test(msg) && !/_quiz-verify/.test(msg)) errors.push(msg);
  });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));

  const shot = async name => {
    win.webContents.invalidate();   // 强制重绘，避免 capturePage 拿到陈旧帧
    await new Promise(r => setTimeout(r, 300));
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
    // 放错：公园前 -> 广州东站（放错不清选中，2026-10-27 用户令：方便连续换站点试）
    pick('公园前').click();
    hot.get('广州东站').fire('click');
    await new Promise(r => setTimeout(r, 200));
    const afterBad = { score: g.score, wrongs: g.wrongs,
      stillSel: pick('公园前').className.includes('selected') };
    // 提示：自动放置一枚
    document.getElementById('mq-hint').click();
    await new Promise(r => setTimeout(r, 200));
    return { afterOk, afterBad, afterHint: { score: g.score, hints: g.hints,
      dock: document.querySelectorAll('#chip-pool .mchip').length } };
  })()`);
  check('②放对 +100', step3.afterOk.score === 100 && step3.afterOk.prog === '1/318' && step3.afterOk.hot === 317,
    JSON.stringify(step3.afterOk));
  check('②放错 −10（牌不消耗, 保留选中）', step3.afterBad.score === 90 && step3.afterBad.wrongs === 1 && step3.afterBad.stillSel === true, JSON.stringify(step3.afterBad));
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
  check('④3号线 池=藏=热区=本线站数(他线站不设热区不响应)',
    step5.dock === step5.lineSt && step5.hidden === step5.lineSt && step5.hotspots === step5.lineSt,
    `池${step5.dock} 藏${step5.hidden} 本线${step5.lineSt} 热区${step5.hotspots}`);
  check('④走廊按色淡化(本线保留)', step5.kept > 5 && step5.dimmed === step5.total - step5.kept,
    `淡${step5.dimmed} 留${step5.kept}/总${step5.total}`);
  await shot('scope-line3');

  // ---------- ⑤ 线号模式：范围多选（2026-10-27 用户令）+ 无数字胶囊（形式强制圆圈）
  //   + 双终点槽位/无色起步/任一终点放置整线自动补齐 ----------
  const step7 = await win.webContents.executeJavaScript(`(async () => {
    document.getElementById('mq-back').click();
    await new Promise(r => setTimeout(r, 300));
    // 清掉④的3号线单选，切线号模式：范围块仍可用（多选），形式块禁用（胶囊=提示）
    document.querySelector('#scope-picker .scope-pill[data-v=""]').click();
    document.querySelector('#metro-setup .opt-card[data-v="badge"]').click();
    const scopeVisible = !document.querySelector('#metro-setup .opt-block[data-block="scope"]').hidden;
    const formDisabled = document.querySelector('#metro-setup .opt-block[data-block="form"]')
      .classList.contains('disabled');
    document.querySelector('#scope-picker .scope-pill[data-v="GF"]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 2500));
    const g = MetroQuiz.__game();
    const it = g.renderer.__internals;
    const gfKeys = [...it.slots.keys()];
    const pool0 = document.querySelectorAll('#chip-pool .mchip').length;
    const formBtnHidden = document.getElementById('mq-form').hidden;
    const svg0 = it.svg;
    const circleBoard = !!svg0.querySelector('#站圆') && !svg0.querySelector('#编号牌');
    // 牌池洗过牌：按牌面找广佛线牌
    const chip = [...document.querySelectorAll('#chip-pool .mchip-badge')]
      .find(c => c.textContent.trim() === '广佛线');
    const chipBg = getComputedStyle(chip).backgroundColor;            // 灰（不带线色）
    const slotBorder = getComputedStyle(it.slots.get('广佛线|沥滘').el).borderTopColor;   // 黑
    chip.click();
    it.slots.get('广佛线|沥滘').el.click();
    await new Promise(r => setTimeout(r, 200));
    // 只放了一枚（沥滘槽）：新城东槽也应被自动补齐=同线全部徽标原位上色
    const vis = [...it.svg.querySelectorAll('[data-badge="header"]')]
      .filter(gf => [...gf.querySelectorAll('text')].some(t => t.textContent.trim() === '广佛线'))
      .every(gf => gf.style.visibility !== 'hidden');
    const single = { scopeVisible, formDisabled, formBtnHidden, circleBoard,
      gfTerms: gfKeys.map(k => k.split('|')[1]).sort().join(','), pool0, chipBg, slotBorder,
      slotsAfter: it.slots.size, dock: document.querySelectorAll('#chip-pool .mchip').length,
      score: g.score, finished: g.finished, badgeVisible: vis };
    // ---- 多选：返回后加选1号线，槽=两线并集 池=2 ----
    document.getElementById('mq-back').click();
    await new Promise(r => setTimeout(r, 300));
    document.querySelector('#scope-picker .scope-pill[data-v="1"]').click();
    const selPills = [...document.querySelectorAll('#scope-picker .scope-pill.selected')]
      .map(p => p.dataset.v).sort().join(',');
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 2500));
    const g2 = MetroQuiz.__game();
    const it2 = g2.renderer.__internals;
    const keys2 = [...it2.slots.keys()].sort();
    let guard = 0;
    while (document.querySelectorAll('#chip-pool .mchip-badge').length && guard++ < 5) {
      const c2 = document.querySelector('#chip-pool .mchip-badge');
      const line = c2.textContent.trim();
      c2.click();
      [...it2.slots.values()].find(s2 => s2.value.split('|')[0] === line).el.click();
      await new Promise(r => setTimeout(r, 100));
    }
    await new Promise(r => setTimeout(r, 300));
    return { single, selPills, keys2, score2: g2.score, finished2: g2.finished,
      slots2: it2.slots.size, dock2: document.querySelectorAll('#chip-pool .mchip').length };
  })()`);
  const s7 = step7.single;
  check('⑤线号模式范围多选可用 形式块禁用(无数字胶囊)',
    s7.scopeVisible && s7.formDisabled, '范围' + s7.scopeVisible + ' 形式禁用' + s7.formDisabled);
  check('⑤单选广佛线 圆圈板 双终点槽 池=1 黑框灰胶囊',
    s7.formBtnHidden && s7.circleBoard && s7.gfTerms === '新城东,沥滘' && s7.pool0 === 1 &&
    s7.chipBg === 'rgb(154, 163, 173)' && s7.slotBorder === 'rgb(17, 17, 17)',
    JSON.stringify(s7));
  check('⑤任一终点放置=整线自动补齐+完成',
    s7.slotsAfter === 0 && s7.dock === 0 && s7.score === 100 && s7.finished && s7.badgeVisible,
    JSON.stringify({ slotsAfter: s7.slotsAfter, dock: s7.dock, score: s7.score,
      finished: s7.finished, badgeVisible: s7.badgeVisible }));
  check('⑤多选广佛线+1号线 槽=并集4枚 池=2 一线一填全清',
    step7.selPills === '1,GF' && step7.keys2.length === 4 &&
    step7.keys2.join('|') === '1号线|广州东站|1号线|西塱|广佛线|新城东|广佛线|沥滘' &&
    step7.slots2 === 0 && step7.dock2 === 0 && step7.finished2,
    JSON.stringify({ sel: step7.selPills, keys: step7.keys2, slots: step7.slots2,
      dock: step7.dock2, finished: step7.finished2 }));

  // ---------- ⑥ 真实地图风格回归（geo：站名模式照常可玩）+ 范围多选冒烟 ----------
  const step8 = await win.webContents.executeJavaScript(`(async () => {
    document.getElementById('mq-back').click();
    await new Promise(r => setTimeout(r, 300));
    document.querySelector('#metro-setup .opt-card[data-v="name"]').click();
    document.querySelector('#metro-setup .opt-card[data-v="geo"]').click();
    document.querySelector('#scope-picker .scope-pill[data-v=""]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 2500));
    const g = MetroQuiz.__game();
    const base = { kind: g.renderer.kind, dock: document.querySelectorAll('#chip-pool .mchip').length,
      expect: MetroData.allStations().length,
      tilesVisible: !document.getElementById('metro-view').querySelector('.metro-tiles').hidden };
    // geo 范围多选冒烟：1号线+3号线并集（2026-10-27 用户令：范围可多选）
    document.getElementById('mq-back').click();
    await new Promise(r => setTimeout(r, 300));
    document.querySelector('#scope-picker .scope-pill[data-v="1"]').click();
    document.querySelector('#scope-picker .scope-pill[data-v="3"]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 2500));
    const g2 = MetroQuiz.__game();
    const uni = new Set();
    for (const ref of ['1', '3'])
      for (const id of (MetroData.lineStationIds(MetroData.line(ref)) || [])) uni.add(id);
    const multi = { kind: g2.renderer.kind, dock: document.querySelectorAll('#chip-pool .mchip').length,
      expect: uni.size };
    // 恢复全网，后续步骤依赖
    document.getElementById('mq-back').click();
    await new Promise(r => setTimeout(r, 300));
    document.querySelector('#scope-picker .scope-pill[data-v=""]').click();
    return { base, multi };
  })()`);
  check('⑥geo 真实地图回归', step8.base.kind === 'geo' && step8.base.dock === step8.base.expect &&
    step8.base.tilesVisible, JSON.stringify(step8.base));
  check('⑥geo 多选1+3号线 池=并集站数',
    step8.multi.kind === 'geo' && step8.multi.dock === step8.multi.expect,
    JSON.stringify(step8.multi));

  // ---------- ⑦ 站点显示形式=数字胶囊：站名模式跑在 codes 板（400 牌可见作站标记） ----------
  const step9 = await win.webContents.executeJavaScript(`(async () => {
    document.getElementById('mq-back').click();
    await new Promise(r => setTimeout(r, 300));
    document.querySelector('#metro-setup .opt-card[data-v="official"]').click();
    document.querySelector('#metro-setup .opt-card[data-v="name"]').click();
    document.querySelector('#metro-setup .opt-block[data-block="form"] .opt-card[data-v="capsule"]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 3000));
    const g = MetroQuiz.__game();
    const svg = g.renderer.__internals.svg;
    const pick = nm => [...document.querySelectorAll('#chip-pool .mchip')]
      .find(e => e.textContent === nm);
    pick('西塱').click();
    g.renderer.__internals.hotspots.get('西塱').fire('click');
    await new Promise(r => setTimeout(r, 200));
    return { hasChips: !!svg.querySelector('#编号牌'), hasCircles: !!svg.querySelector('#站圆'),
      chipsVisible: [...svg.querySelectorAll('#编号牌 rect[fill="#FFFFFF"]')]
        .filter(r => r.style.visibility !== 'hidden').length,
      hidden: g.renderer.__internals.hiddenCount,
      dock: document.querySelectorAll('#chip-pool .mchip').length,
      score: g.score, formBtn: document.getElementById('mq-form').textContent };
  })()`);
  check('⑦胶囊形式 codes 板 400 牌可见+站名隐藏+可判分',
    step9.hasChips && !step9.hasCircles && step9.chipsVisible === 400 &&
    step9.hidden === 317 && step9.dock === 317 && step9.score === 100 &&
    step9.formBtn.indexOf('数字胶囊') >= 0,
    JSON.stringify(step9));
  await shot('form-capsule-names');

  // ---------- ⑧ 局内形式切换（胶囊→圆圈）：进度保留，站名层原位复原 ----------
  const step11 = await win.webContents.executeJavaScript(`(async () => {
    document.getElementById('mq-form').click();
    await new Promise(r => setTimeout(r, 3000));
    const g = MetroQuiz.__game();
    const svg = g.renderer.__internals.svg;
    const t = [...svg.querySelectorAll('#站名标注 text')].find(e => e.textContent === '西塱');
    return { hasChips: !!svg.querySelector('#编号牌'), hasCircles: !!svg.querySelector('#站圆'),
      placedVisible: !!t && t.style.visibility !== 'hidden',
      score: g.score, dock: document.querySelectorAll('#chip-pool .mchip').length,
      formBtn: document.getElementById('mq-form').textContent };
  })()`);
  check('⑧局内切换圆圈 进度保留 站名层复原', step11.hasCircles && !step11.hasChips &&
    step11.placedVisible && step11.score === 100 && step11.dock === 317 &&
    step11.formBtn.indexOf('站点圆圈') >= 0, JSON.stringify(step11));

  // ---------- ⑨ 圆圈形式基础板 + 放弃揭示（revealAll 只复原本局谜面，
  //   不注入编号牌——圆点与胶囊两套站标记不得叠画, 2026-10-27 用户令） ----------
  const step10 = await win.webContents.executeJavaScript(`(async () => {
    document.getElementById('mq-back').click();
    await new Promise(r => setTimeout(r, 300));
    document.querySelector('#metro-setup .opt-block[data-block="form"] .opt-card[data-v="circle"]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 3000));
    const g = MetroQuiz.__game();
    const svg = g.renderer.__internals.svg;
    const basic = { hasCircles: !!svg.querySelector('#站圆'), hasChips: !!svg.querySelector('#编号牌'),
      dock: document.querySelectorAll('#chip-pool .mchip').length,
      hidden: g.renderer.__internals.hiddenCount };
    document.getElementById('mq-giveup').click();
    await new Promise(r => setTimeout(r, 500));
    const gongyuan = [...svg.querySelectorAll('#站名标注 text')].find(e => e.textContent === '公园前');
    return { basic, revealed: !document.getElementById('metro-result').hidden,
      rsTitle: document.getElementById('rs-title').textContent,
      injected: document.querySelectorAll('#metro-canvas .mb-chip-svg').length,
      hiddenAfter: g.renderer.__internals.hiddenCount,
      gongyuanVisible: !!gongyuan && gongyuan.style.visibility !== 'hidden' };
  })()`);
  check('⑨圆圈形式基础板 站名模式开局', step10.basic.hasCircles && !step10.basic.hasChips &&
    step10.basic.dock === 318 && step10.basic.hidden === 318, JSON.stringify(step10.basic));
  check('⑨放弃揭示 只复原站名 零胶囊注入(圆点胶囊不叠画)',
    step10.revealed && step10.rsTitle.indexOf('已揭示答案') >= 0 &&
    step10.injected === 0 && step10.hiddenAfter === 0 && step10.gongyuanVisible,
    JSON.stringify({ revealed: step10.revealed, rsTitle: step10.rsTitle,
      injected: step10.injected, hiddenAfter: step10.hiddenAfter,
      gongyuanVisible: step10.gongyuanVisible }));
  await shot('form-circle-reveal');

  // ---------- ⑨b 一局正式结束后范围复位全网（2026-10-27 用户令：玩家一般不会再来一遍）：
  //   带范围开局→放弃揭示（正式结束=复位点）→结算页直接「再来一局」=全网挑战开局 ----------
  const step10b = await win.webContents.executeJavaScript(`(async () => {
    document.getElementById('mq-back').click();
    await new Promise(r => setTimeout(r, 300));
    document.querySelector('#scope-picker .scope-pill[data-v="GF"]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 2500));
    const scope0 = document.getElementById('mq-scope').textContent;
    document.getElementById('mq-giveup').click();
    await new Promise(r => setTimeout(r, 400));
    document.getElementById('rs-again').click();
    await new Promise(r => setTimeout(r, 2500));
    const g2 = MetroQuiz.__game();
    return { scope0, scopeRe: document.getElementById('mq-scope').textContent,
      pillsSel: [...document.querySelectorAll('#scope-picker .scope-pill.selected')]
        .map(p => p.dataset.v).join(','),
      dockRe: document.querySelectorAll('#chip-pool .mchip').length };
  })()`);
  check('⑨b揭示结束后再来一局 默认全网挑战(药丸复位)',
    step10b.scope0.indexOf('广佛线') >= 0 &&
    step10b.scopeRe.indexOf('全网挑战') >= 0 && step10b.pillsSel === '' &&
    step10b.dockRe === 318,
    JSON.stringify(step10b));

  // ---------- ⑩ 单线×胶囊（2026-10-26 用户令：单线展示时本线数字亮、他线数字灰）：
  //   站名模式+胶囊+1号线（选择线路仅站名模式提供，2026-10-27 用户令）：400 牌全作背景，
  //   换乘站亮牌必须=本线（牌面配对哨兵：体育西路 1|14 亮 / 3|11 灰）----------
  const step12 = await win.webContents.executeJavaScript(`(async () => {
    document.getElementById('mq-back').click();
    await new Promise(r => setTimeout(r, 300));
    document.querySelector('#metro-setup .opt-card[data-v="name"]').click();
    document.querySelector('#metro-setup .opt-block[data-block="form"] .opt-card[data-v="capsule"]').click();
    document.querySelector('#scope-picker .scope-pill[data-v=""]').click();   // 清掉⑤的多选
    const scopeVisible = !document.querySelector('#metro-setup .opt-block[data-block="scope"]').hidden;
    document.querySelector('#scope-picker .scope-pill[data-v="1"]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 3000));
    const g = MetroQuiz.__game();
    const it = g.renderer.__internals;
    const rects = [...it.svg.querySelectorAll('#编号牌 rect[fill="#FFFFFF"]')];
    const at = (x, y) => rects.find(r => Math.abs(parseFloat(r.getAttribute('x')) - x) < 0.05 &&
      Math.abs(parseFloat(r.getAttribute('y')) - y) < 0.05);
    const rec1 = window.QUIZ_NETWORK_DATA.chips.find(c => c.nm === '体育西路' && c.line === '1号线');
    const rec3 = window.QUIZ_NETWORK_DATA.chips.find(c => c.nm === '体育西路' && c.line === '3号线');
    const st = r => ({ vis: r.style.visibility !== 'hidden', op: parseFloat(r.style.opacity || '1') });
    return {
      scopeVisible,
      allKept: rects.every(r => r.style.visibility !== 'hidden'),
      othersDim: window.QUIZ_NETWORK_DATA.chips.filter(c => c.line !== '1号线')
        .every(c => parseFloat(at(c.x, c.y).style.opacity || '1') < 0.5),
      s1: st(at(rec1.x, rec1.y)), s3: st(at(rec3.x, rec3.y)),
      pillsRow: !!document.getElementById('dock-lines') };
  })()`);
  check('⑩站名模式保留选择线路 药丸行已移除', step12.scopeVisible && !step12.pillsRow,
    '范围可见' + step12.scopeVisible + ' 药丸残留' + step12.pillsRow);
  check('⑩1号线胶囊 400牌全留 他线全淡化',
    step12.allKept && step12.othersDim,
    `留${step12.allKept} 淡${step12.othersDim}`);
  check('⑩体育西路 本线1|14亮 他线3|11灰(牌面配对哨兵)',
    step12.s1.vis && step12.s1.op > 0.9 && step12.s3.vis && step12.s3.op < 0.5,
    JSON.stringify(step12.s1) + ' vs ' + JSON.stringify(step12.s3));

  // ---------- ⑪ 定位未填写（2026-10-27 用户令）：聚焦居中+闪烁，洗牌袋连点零重复 ----------
  const step13 = await win.webContents.executeJavaScript(`(async () => {
    document.getElementById('mq-back').click();
    await new Promise(r => setTimeout(r, 300));
    // 还原成 全网×站名模式（沿用残留的胶囊形式即可，定位与形式无关）
    document.querySelector('#metro-setup .opt-card[data-v="name"]').click();
    document.querySelector('#scope-picker .scope-pill[data-v=""]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 3000));
    const g = MetroQuiz.__game();
    const it = g.renderer.__internals;
    const map = it.map;
    const btn = document.getElementById('mq-locate');
    const hiddenAtStart = btn.hidden;
    const nearestNm = c => {
      let bn = null, bd = 1e9;
      for (const [nm, st] of Object.entries(window.QUIZ_NETWORK_DATA.stations)) {
        const d = Math.hypot(st.x - c.lng, st.y + c.lat);
        if (d < bd) { bd = d; bn = nm; }
      }
      return [bn, bd];
    };
    btn.click();
    await new Promise(r => setTimeout(r, 150));
    const [hitNm, hitDist] = nearestNm(map.getCenter());
    const blinkPaths = document.querySelectorAll('#metro-canvas path.mb-blink').length;
    const blinkSlots = document.querySelectorAll('#metro-canvas .mb-slot.mb-blink').length;
    // 连点共 318 次 = 洗牌袋恰好一轮：全部去重后应为 318（纯随机必有约 40 次撞车）
    const seen = new Set([hitNm]);
    for (let i = 0; i < 317; i++) {
      btn.click();
      seen.add(nearestNm(map.getCenter())[0]);
    }
    return { hiddenAtStart, unfilled: g.renderer.unfilledList().length,
      hitNm, hitDist: hitDist.toFixed(3), blinkTotal: blinkPaths + blinkSlots,
      distinct: seen.size };
  })()`);
  check('⑪定位按钮局内可见', step13.hiddenAtStart === false && step13.unfilled === 318,
    JSON.stringify({ hidden: step13.hiddenAtStart, unfilled: step13.unfilled }));
  check('⑪点击聚焦居中到未填站+闪烁', step13.hitDist < 0.5 && step13.blinkTotal === 1,
    '命中' + step13.hitNm + ' 偏差' + step13.hitDist + ' 闪烁' + step13.blinkTotal);
  check('⑪连点318次零重复(洗牌袋一轮)', step13.distinct === 318,
    '去重' + step13.distinct + '/318');

  // ---------- ⑫ 徽标槽定位（全网线号）：居中+闪烁；一线一填整线全清，填完后提示无未填 ----------
  const step14 = await win.webContents.executeJavaScript(`(async () => {
    document.getElementById('mq-back').click();
    await new Promise(r => setTimeout(r, 300));
    document.querySelector('#metro-setup .opt-card[data-v="badge"]').click();   // 范围块隐藏=强制全网
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 3000));
    const g = MetroQuiz.__game();
    const it = g.renderer.__internals;
    const openOk = it.slots.size === 41 &&
      document.querySelectorAll('#chip-pool .mchip-badge').length === 19;
    const btn = document.getElementById('mq-locate');
    btn.click();
    await new Promise(r => setTimeout(r, 150));
    const c = it.map.getCenter();
    const dist = Math.min(...[...it.slots.values()].map(s => Math.hypot(s.bx - c.lng, s.by + c.lat)));
    const blink = document.querySelectorAll('#metro-canvas .mb-slot.mb-blink').length;
    // 一线一填整线全清：每枚牌放到本线任一槽位（放对一枚同线槽全消）
    let guard = 0;
    while (document.querySelectorAll('#chip-pool .mchip-badge').length && guard++ < 25) {
      const chip = document.querySelector('#chip-pool .mchip-badge');
      const line = chip.textContent.trim();
      chip.click();
      const slot = [...it.slots.values()].find(s2 => s2.value.split('|')[0] === line);
      slot.el.click();
      await new Promise(r => setTimeout(r, 60));
    }
    await new Promise(r => setTimeout(r, 200));
    const listAfter = g.renderer.unfilledList().length;
    btn.click();
    await new Promise(r => setTimeout(r, 150));
    const toast = document.getElementById('mq-toast').textContent;
    return { openOk, dist: dist.toFixed(3), blink, slotsAfter: it.slots.size,
      dockAfter: document.querySelectorAll('#chip-pool .mchip').length,
      listAfter, toast, guard };
  })()`);
  check('⑫全网线号开局 槽=41 池=19', step14.openOk,
    JSON.stringify({ openOk: step14.openOk }));
  check('⑫徽标槽定位=居中+闪烁', Math.abs(parseFloat(step14.dist)) < 0.5 && step14.blink === 1,
    '偏差' + step14.dist + ' 闪烁' + step14.blink);
  check('⑫一线一填整线全清 填完后定位提示无未填',
    step14.slotsAfter === 0 && step14.dockAfter === 0 && step14.listAfter === 0 &&
    step14.toast.indexOf('没有未填写') >= 0,
    JSON.stringify({ slotsAfter: step14.slotsAfter, dockAfter: step14.dockAfter,
      listAfter: step14.listAfter, toast: step14.toast, guard: step14.guard }));

  // ---------- ⑬ 板级徽标单线口径保留（quiz 层线号/挑战已全网-only，单线徽标能力
  //   保留为 board 能力，板级直测）：他线徽标只淡化不收槽，本线徽标=谜面 ----------
  const step15 = await win.webContents.executeJavaScript(`(async () => {
    document.getElementById('mq-back').click();
    await new Promise(r => setTimeout(r, 300));
    const cv = document.getElementById('metro-canvas');
    const r = MetroBoard.create(cv);
    r.render({ mode: 'badge', form: 'circle', scope: '广佛线', interactive: false,
      placedNames: new Set(), placedBadges: new Set(), placedChips: new Set() });
    await new Promise(r2 => setTimeout(r2, 2500));
    const it = r.__internals;
    const keys = [...it.slots.keys()];
    const isGf = g => [...g.querySelectorAll('text')].some(t => t.textContent.trim() === '广佛线');
    const badges = [...it.svg.querySelectorAll('[data-badge="header"]')];
    const gfHidden = badges.filter(isGf).every(g => g.style.visibility === 'hidden');
    const others = badges.filter(g => !isGf(g) && g.style.visibility !== 'hidden');
    const otherDim = others.length > 0 &&
      others.every(g => parseFloat(g.style.opacity || '1') < 0.5);
    r.destroy();
    cv.innerHTML = '';
    return { n: keys.length, allGf: keys.every(k => k.indexOf('广佛线|') === 0),
      gfHidden, others: others.length, otherDim };
  })()`);
  check('⑬板级单线徽标口径 GF槽=2 他线徽标淡化不收槽',
    step15.n === 2 && step15.allGf && step15.gfHidden && step15.otherDim,
    JSON.stringify(step15));

  await win.webContents.executeJavaScript(
    `console.log('_quiz-verify done')`);
  console.log('\\nconsole errors:', errors.length ? errors : 'none');
  const fails = results.filter(r => !r.ok);
  console.log(fails.length ? 'VERIFY FAIL (' + fails.length + ')' : 'VERIFY ALL PASS (' + results.length + ')');
  app.exit(fails.length ? 1 : 0);
}).catch(e => { console.error(e); app.exit(2); });
