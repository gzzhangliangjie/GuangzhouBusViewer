// 地铁拼图游戏逻辑：模式/风格/范围选择、名牌池、判分计时、历史最佳
// 渲染层（官方线网图 / 真实地图）通过统一接口注入，UI 逻辑不感知差异
// 官方线网图 = 整理版 network-全网 SVG 自锚定拼图（metro-board.js）：
//   站名/线号/编号牌都是图上真实元素，放对即原位字节级复原

const MetroQuiz = (() => {
  const BEST_KEY = 'gzmetro.best.v1';
  const RESULT_DELAY_MS = 1000;   // 最后一枚放完后延迟弹结算，让玩家看清补完的整图
  const $ = sel => document.querySelector(sel);

  const MODE_NAMES = { name: '站名模式', code: '编号模式', badge: '线号模式', both: '挑战模式' };

  const els = {
    setup: $('#metro-setup'), game: $('#metro-game'), result: $('#metro-result'),
    scopePicker: $('#scope-picker'), best: $('#metro-best'),
    canvas: $('#metro-canvas'), tilesBar: $('#metro-view .metro-tiles'),
    title: $('#mq-title'), scopeLbl: $('#mq-scope'),
    score: $('#mq-score'), time: $('#mq-time'), prog: $('#mq-prog'),
    hint: $('#mq-hint'), restart: $('#mq-restart'), giveup: $('#mq-giveup'), back: $('#mq-back'),
    form: $('#mq-form'),
    dock: $('#metro-dock'), pool: $('#chip-pool'), filter: $('#dock-filter'), count: $('#dock-count'),
    linePills: $('#dock-lines'),
    toast: $('#mq-toast'),
    rsTitle: $('#rs-title'), rsSub: $('#rs-sub'), rsBody: $('#rs-body'),
    rsAgain: $('#rs-again'), rsMenu: $('#rs-menu'), rsView: $('#rs-view')
  };

  const cfg = { mode: 'name', style: 'official', form: 'circle', scope: null };
  let game = null;        // 进行中/已结束的一局；{answer:true} 表示答案图浏览
  let selectedChip = null;
  let lineFilter = null;  // 名牌池线号快捷过滤（仅官方棋盘的编号/线号模式）
  let toastTimer = null;

  /* ---------- 官方棋盘数据 ---------- */

  function QD() { return window.QUIZ_NETWORK_DATA; }
  // 挑战范围在官方棋盘用线名（zh），真实地图用 MetroData ref
  function scopeName() {
    return cfg.scope ? (MetroData.line(cfg.scope)?.zh || null) : null;
  }
  function lineColor(name) {
    const l = QD() && QD().lines.find(x => x.name === name);
    return l ? l.color : '#4a9eff';
  }

  /* ---------- 初始化 ---------- */

  function init() {
    if (!MetroData.load()) return;
    // 配对数据版本戳：设置页副标题上可见，核对窗口跑的是哪版 quiz 数据
    const headP = document.querySelector('#metro-setup .setup-head p');
    if (headP && QD() && QD().gen) headP.textContent += ' · 牌配对 v' + QD().gen;
    wireModeNav();
    wireSetup();
    wireGame();
    buildScopePicker();
  }

  function wireModeNav() {
    document.querySelectorAll('#mode-nav [data-mode]').forEach(btn =>
      btn.addEventListener('click', () => showMode(btn.dataset.mode)));
  }

  function showMode(name) {
    document.querySelectorAll('#mode-nav [data-mode]').forEach(b =>
      b.classList.toggle('active', b.dataset.mode === name));
    $('#bus-view').hidden = name !== 'bus';
    $('#metro-view').hidden = name !== 'metro';
    $('#roads-view').hidden = name !== 'roads';
    $('#lines-view').hidden = name !== 'lines';
    if (name === 'roads' && window.RoadsView) RoadsView.show();
    if (name === 'lines' && window.LinesView) LinesView.show();
    if (name === 'metro') {
      if (!game) showSetup();
      else if (game.renderer && game.renderer.invalidate) game.renderer.invalidate();
    }
  }

  function wireSetup() {
    document.querySelectorAll('#metro-setup .opt-block').forEach(block => {
      const key = block.dataset.block;   // mode | style | form
      block.querySelectorAll('.opt-card').forEach(card =>
        card.addEventListener('click', () => {
          if (key === 'style' && card.dataset.v === 'geo' && cfg.mode === 'code') {
            toast('编号模式基于官方编号牌，仅官方线网图可用');
            return;
          }
          block.querySelectorAll('.opt-card').forEach(c => c.classList.remove('selected'));
          card.classList.add('selected');
          cfg[key] = card.dataset.v;
          // 站点显示形式只在官方线网图有意义（真实地图无圆圈/胶囊之分）
          if (key === 'style') syncFormBlock();
          // 编号模式自动切官方线网图 + 数字胶囊（两处都可在选项里改回）
          if (key === 'mode' && card.dataset.v === 'code') {
            if (cfg.style === 'geo') {
              cfg.style = 'official';
              const styleBlock = document.querySelector('#metro-setup .opt-block[data-block="style"]');
              styleBlock.querySelectorAll('.opt-card').forEach(c =>
                c.classList.toggle('selected', c.dataset.v === 'official'));
              syncFormBlock();
            }
            if (cfg.form !== 'capsule') {
              cfg.form = 'capsule';
              document.querySelectorAll('#metro-setup .opt-block[data-block="form"] .opt-card')
                .forEach(c => c.classList.toggle('selected', c.dataset.v === 'capsule'));
            }
          }
          updateBestLine();
        }));
    });
    syncFormBlock();
    $('#metro-start').addEventListener('click', startGame);
    $('#metro-answer').addEventListener('click', showAnswerView);
  }

  function syncFormBlock() {
    const fb = document.querySelector('#metro-setup .opt-block[data-block="form"]');
    if (fb) fb.classList.toggle('disabled', cfg.style !== 'official');
  }

  function buildScopePicker() {
    const mk = (value, label, colour, title) => {
      const b = document.createElement('button');
      b.className = 'scope-pill' + (value === cfg.scope ? ' selected' : '');
      b.dataset.v = value || '';
      b.innerHTML = colour
        ? `<span class="scope-badge" style="background:${colour}">${label}</span>`
        : `<span>${label}</span>`;
      if (title) b.title = title;
      b.addEventListener('click', () => {
        cfg.scope = value;
        els.scopePicker.querySelectorAll('.scope-pill').forEach(p => p.classList.remove('selected'));
        b.classList.add('selected');
        updateBestLine();
      });
      return b;
    };
    els.scopePicker.appendChild(mk(null, '全网挑战', '', '官方线网图 19 条线 / 318 座车站'));
    for (const l of MetroData.allLines()) {
      els.scopePicker.appendChild(mk(l.ref, MetroData.refLabel(l.ref), l.color, l.zh));
    }
  }

  /* ---------- 开局 ---------- */

  function startGame() {
    teardown();
    const items = buildItems();
    if (!items.length) return;
    lineFilter = null;

    // 先显示游戏区再创建地图，否则容器 0 尺寸导致 fitBounds 视野错误
    els.setup.hidden = true;
    els.game.hidden = false;
    els.result.hidden = true;

    const official = cfg.style === 'official';
    game = {
      answer: false, renderer: null, official, items,
      chips: new Map(),           // chipKey -> {kind, value, el}
      placedNames: new Set(), placedBadges: new Set(), placedChips: new Set(),
      score: 0, corrects: 0, wrongs: 0, hints: 0,
      startTime: Date.now(), timerId: null, finished: false, revealed: false
    };

    if (official) {
      initBoard();
    } else {
      const renderer = MetroMapView.create(els.canvas, { simple: false });
      game.renderer = renderer;
      renderer.onStationClick((id, payload) => pickTarget('name', id, payload));
      renderer.onBadgeClick((ref, payload) => pickTarget('badge', ref, payload));
      renderer.render({
        scopeRef: cfg.scope, interactive: true,
        showStationNames: cfg.mode === 'badge',
        showBadges: cfg.mode === 'name' ? 'filled' : 'slots',
        placedNames: game.placedNames, placedBadges: game.placedBadges
      });
    }

    renderChips(items);
    els.title.textContent = MODE_NAMES[cfg.mode];
    els.scopeLbl.textContent =
      (cfg.scope ? (MetroData.line(cfg.scope)?.zh || cfg.scope) : '全网挑战') +
      (official ? ' · 官方线网图 · ' + (cfg.form === 'capsule' ? '数字胶囊' : '站点圆圈') : ' · 高德底图');

    els.tilesBar.hidden = official;
    els.form.hidden = !official;
    els.form.textContent = cfg.form === 'capsule' ? '形式：数字胶囊' : '形式：站点圆圈';
    els.dock.hidden = false;
    els.filter.value = '';
    els.filter.hidden = items.length <= 30;
    els.hint.disabled = false;
    els.hint.hidden = els.restart.hidden = els.giveup.hidden = false;

    updateHud();
    game.timerId = setInterval(updateHud, 1000);
  }

  // 官方棋盘装配（开局与局内形式切换共用；进度集挂在 game 上，重挂不丢进度）
  function initBoard() {
    const renderer = MetroBoard.create(els.canvas);
    game.renderer = renderer;
    renderer.onStationClick((kind, value, payload) => pickTarget(kind, value, payload));
    renderer.onBadgeClick((kind, value, payload) => pickTarget(kind, value, payload));
    renderer.onChipClick((kind, value, payload) => pickTarget(kind, value, payload));
    renderer.render({
      mode: cfg.mode, form: cfg.form, scope: scopeName(), interactive: true,
      placedNames: game.placedNames, placedBadges: game.placedBadges,
      placedChips: game.placedChips
    });
  }

  // 局内切换 站点圆圈 / 数字胶囊（保留分数、计时与已放置进度）
  function toggleForm() {
    if (!game || game.answer || game.finished || !game.official) return;
    cfg.form = cfg.form === 'capsule' ? 'circle' : 'capsule';
    if (game.renderer) game.renderer.destroy();
    initBoard();
    els.form.textContent = cfg.form === 'capsule' ? '形式：数字胶囊' : '形式：站点圆圈';
    els.scopeLbl.textContent =
      (cfg.scope ? (MetroData.line(cfg.scope)?.zh || cfg.scope) : '全网挑战') +
      ' · 官方线网图 · ' + (cfg.form === 'capsule' ? '数字胶囊' : '站点圆圈');
    toast(cfg.form === 'capsule' ? '已切换：数字胶囊' : '已切换：站点圆圈', true);
  }

  function buildItems() {
    const items = [];
    if (cfg.style === 'official') {
      const scope = scopeName();
      if (cfg.mode === 'name' || cfg.mode === 'both') {
        for (const nm of officialLineStations2(scope)) items.push({ kind: 'name', value: nm });
      }
      if (cfg.mode === 'badge' || cfg.mode === 'both') {
        const lines = scope ? [scope] : QD().lines.map(l => l.name);
        for (const ln of lines) {
          // 一线多枚终点徽标算一块（任意一枚终点位都判对）
          if (!QD().lines.find(l => l.name === ln)) continue;
          items.push({ kind: 'badge', value: ln });
        }
      }
      if (cfg.mode === 'code') {
        for (const c of QD().chips) {
          if (scope && c.line !== scope) continue;
          items.push({ kind: 'chip', value: c.nm + '|' + c.line });
        }
      }
    } else {
      if (cfg.mode === 'name' || cfg.mode === 'both') {
        const stations = cfg.scope
          ? MetroData.lineStationIds(MetroData.line(cfg.scope))
          : MetroData.allStations().map(s => s.id);
        for (const id of stations) items.push({ kind: 'name', value: id });
      }
      if (cfg.mode === 'badge' || cfg.mode === 'both') {
        const lines = cfg.scope ? [cfg.scope] : MetroData.allLines().map(l => l.ref);
        for (const ref of lines) items.push({ kind: 'badge', value: ref });
      }
    }
    // 洗牌：名牌顺序不泄露站点顺序
    for (let i = items.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [items[i], items[j]] = [items[j], items[i]];
    }
    return items;
  }

  function officialLineStations2(scope) {
    const st = QD().stations;
    const all = Object.keys(st);
    if (!scope) return all;
    return all.filter(nm => st[nm].lines.includes(scope));
  }

  /* ---------- 名牌池 ---------- */

  function chipKey(it) { return it.kind + ':' + it.value; }

  function renderChips(items) {
    els.pool.innerHTML = '';
    renderLinePills(items);
    for (const it of items) {
      const key = chipKey(it);
      const el = document.createElement('span');
      if (it.kind === 'badge') {
        const color = game.official ? lineColor(it.value) : (MetroData.line(it.value)?.color || '#4a9eff');
        el.className = 'mchip mchip-badge';
        el.style.setProperty('--c', color);
        el.textContent = game.official ? it.value : (MetroData.refLabel(it.value) || it.value);
        el.title = '线路徽章';
      } else if (it.kind === 'chip') {
        const [nm, ln] = it.value.split('|');
        const rec = QD().chips.find(c => c.nm === nm && c.line === ln);
        const disp = QD().lines.find(l => l.name === ln)?.disp || ln;
        el.className = 'mchip mchip-code';
        el.style.setProperty('--c', lineColor(ln));
        el.innerHTML = `<b>${esc(disp)}</b><em></em><b>${esc(rec ? rec.serial : '??')}</b>`;
        el.title = nm + ' · ' + ln;
      } else {
        el.className = 'mchip';
        el.textContent = it.value;
      }
      el.draggable = true;
      el.addEventListener('click', () => selectChip(el));
      el.addEventListener('dragstart', e => {
        selectChip(el, true);
        e.dataTransfer.setData('text/plain', key);
        e.dataTransfer.effectAllowed = 'move';
      });
      els.pool.appendChild(el);
      game.chips.set(key, { kind: it.kind, value: it.value, el });
    }
    updateHud();
  }

  // 线号快捷过滤（官方棋盘的编号/线号模式；站名模式会泄露归属所以不提供）
  function renderLinePills(items) {
    els.linePills.innerHTML = '';
    if (!game.official || !(cfg.mode === 'code' || cfg.mode === 'badge')) {
      els.linePills.hidden = true;
      return;
    }
    els.linePills.hidden = false;
    const mk = (label, color, v) => {
      const b = document.createElement('button');
      b.className = 'dock-pill' + (lineFilter === v ? ' selected' : '');
      b.textContent = label;
      if (color) b.style.setProperty('--c', color);
      b.addEventListener('click', () => {
        lineFilter = lineFilter === v ? null : v;
        els.linePills.querySelectorAll('.dock-pill').forEach(p =>
          p.classList.toggle('selected', p.dataset.v === (lineFilter || '')));
        applyDockFilter();
      });
      b.dataset.v = v || '';
      return b;
    };
    els.linePills.appendChild(mk('全部', null, null));
    const used = new Set(items.map(it => it.kind === 'chip' ? it.value.split('|')[1] : it.value));
    for (const l of QD().lines) {
      if (!used.has(l.name)) continue;
      els.linePills.appendChild(mk(l.disp, l.color, l.name));
    }
  }

  function selectChip(el, silent) {
    if (selectedChip === el) {
      selectedChip.classList.remove('selected');
      selectedChip = null;
      return;
    }
    if (selectedChip) selectedChip.classList.remove('selected');
    selectedChip = el;
    if (el) el.classList.add('selected');
  }

  function clearSelection() {
    if (selectedChip) selectedChip.classList.remove('selected');
    selectedChip = null;
  }

  /* ---------- 判定 ---------- */

  // targetType: 'name'（站点）| 'badge'（线路槽）| 'chip'（编号牌槽）；payload 为拖拽带来的 "kind:value"
  function pickTarget(targetType, targetValue, payload) {
    if (!game || game.finished || game.answer) return;
    let chip = null;
    if (payload && game.chips.has(payload)) chip = game.chips.get(payload);
    else if (selectedChip) {
      for (const [, c] of game.chips) {
        if (c.el === selectedChip) { chip = c; break; }
      }
    }
    if (!chip) return;

    if (chip.kind === targetType && chip.value === targetValue) {
      game.score += 100;
      game.corrects++;
      toast('✓ ' + chipLabel(chip) + ' +100', true);
      if (chip.kind === 'name' && game.renderer.popFx) game.renderer.popFx(chip.value, '+100');
      place(chip);
      clearSelection();
      if (game.chips.size === 0) scheduleFinish();
    } else {
      game.wrongs++;
      game.score = Math.max(0, game.score - 10);
      if (game.renderer.kind === 'official') game.renderer.wrongFeedback(targetType, targetValue);
      else game.renderer.wrongFeedback(targetValue);
      toast('放错了 −10');
      clearSelection();
    }
    updateHud();
  }

  function chipLabel(chip) {
    if (chip.kind === 'name') return chip.value;
    if (chip.kind === 'badge') return chip.value;
    const [nm, ln] = chip.value.split('|');
    const rec = QD().chips.find(c => c.nm === nm && c.line === ln);
    const disp = QD().lines.find(l => l.name === ln)?.disp || ln;
    return disp + '|' + (rec ? rec.serial : '??') + ' ' + nm;
  }

  function place(chip) {
    game.chips.delete(chipKey(chip));
    chip.el.remove();
    if (chip.kind === 'name') {
      game.placedNames.add(chip.value);
      game.renderer.placeName(chip.value);
    } else if (chip.kind === 'badge') {
      game.placedBadges.add(chip.value);
      game.renderer.placeBadge(chip.value);
    } else {
      game.placedChips.add(chip.value);
      game.renderer.placeChip(chip.value);
    }
  }

  function useHint() {
    if (!game || game.finished || game.answer || !game.chips.size) return;
    const keys = [...game.chips.keys()];
    const chip = game.chips.get(keys[Math.floor(Math.random() * keys.length)]);
    game.hints++;
    game.score = Math.max(0, game.score - 50);
    place(chip);
    clearSelection();
    toast('已自动放置「' + chipLabel(chip) + '」 −50');
    if (game.chips.size === 0) scheduleFinish();
    else updateHud();
  }

  /* ---------- 结算 ---------- */

  // 全部放完不立刻弹结算窗：先冻结局面（finished=true 停输入停计时），
  // 延迟 RESULT_DELAY_MS 再弹；用时按最后一枚落定时刻冻结，延迟不扣时间加成。
  // 期间重开/返回会 teardown 换掉 game，回调用身份比对失效，不会误弹新局。
  function scheduleFinish() {
    game.finished = true;
    game.endAt = Date.now();
    clearInterval(game.timerId);
    game.timerId = null;
    const g = game;
    updateHud();
    setTimeout(() => { if (game === g) finish(); }, RESULT_DELAY_MS);
  }

  function finish() {
    game.finished = true;
    clearInterval(game.timerId);
    const elapsed = Math.floor(((game.endAt || Date.now()) - game.startTime) / 1000);
    const quota = 150 + game.items.length * 25;   // 每个名牌 25s + 150s 起步
    const bonus = Math.round(Math.max(0, quota - elapsed) * 3 / 10) * 10;
    const total = game.score + bonus;
    const best = saveBest(total, elapsed);
    showResult({
      title: '🎉 拼图完成！',
      sub: MODE_NAMES[cfg.mode] + ' · ' + (cfg.scope ? MetroData.line(cfg.scope)?.zh : '全网挑战') +
        ' · 官方线网图 · ' + (cfg.form === 'capsule' ? '数字胶囊' : '站点圆圈'),
      rows: [
        ['答对', `${game.corrects} 个 · +${game.corrects * 100}`],
        ['放错', `${game.wrongs} 次 · −${game.wrongs * 10}`],
        ['提示', `${game.hints} 次 · −${game.hints * 50}`],
        ['用时', fmtTime(elapsed)],
        ['时间加成', '+' + bonus],
        ['总分', String(total)],
        ['历史最佳', best.isNew ? '⭐ 新纪录！' : String(best.prev)]
      ],
      record: best.isNew
    });
  }

  function giveUp() {
    if (!game || game.finished || game.answer) return;
    game.finished = true;
    game.revealed = true;
    clearInterval(game.timerId);
    game.renderer.revealAll();
    els.dock.hidden = true;
    showResult({
      title: '已揭示答案',
      sub: '再接再厉，下一局一定行',
      rows: [
        ['已放置', `${game.items.length - game.chips.size} / ${game.items.length}`],
        ['用时', fmtTime(Math.floor((Date.now() - game.startTime) / 1000))]
      ],
      record: false
    });
  }

  function showResult(r) {
    els.rsTitle.textContent = r.title;
    els.rsSub.textContent = r.sub;
    els.rsBody.innerHTML = r.rows.map(([k, v], i) =>
      `<div class="rs-row${i === r.rows.length - 1 ? ' total' : ''}"><span>${k}</span><b>${esc(v)}</b></div>`
    ).join('');
    els.rsView.hidden = !!r.noView;
    els.result.hidden = false;
  }

  /* ---------- 历史最佳 ---------- */

  function bestKeyOf() {
    // 形式计入最佳键：圆圈/胶囊的可玩性与提示密度不同，成绩分开记
    return `${cfg.mode}|${cfg.style}|${cfg.scope || '全网'}|${cfg.style === 'official' ? cfg.form : 'geo'}`;
  }
  function readBests() {
    try { return JSON.parse(localStorage.getItem(BEST_KEY)) || {}; }
    catch { return {}; }
  }
  function saveBest(total, elapsed) {
    const all = readBests();
    const key = bestKeyOf();
    const prev = all[key];
    const isNew = !prev || total > prev.score;
    if (isNew) {
      all[key] = { score: total, time: elapsed, date: new Date().toISOString().slice(0, 10) };
      try { localStorage.setItem(BEST_KEY, JSON.stringify(all)); } catch { /* 忽略 */ }
    }
    return { isNew, prev: prev ? prev.score : null };
  }
  function updateBestLine() {
    const b = readBests()[bestKeyOf()];
    els.best.textContent = b
      ? `该组合历史最佳：${b.score} 分 · 用时 ${fmtTime(b.time)}（${b.date}）`
      : '该组合历史最佳：暂无纪录';
  }

  /* ---------- 答案图（整理版线网全图，仅浏览） ---------- */

  function showAnswerView() {
    teardown();
    // 先显示游戏区再创建地图，保证容器尺寸正确、答案图能正确聚焦
    els.setup.hidden = true;
    els.game.hidden = false;
    els.result.hidden = true;

    const renderer = MetroBoard.create(els.canvas);
    game = { answer: true, official: true, renderer, chips: new Map(),
      placedNames: new Set(), placedBadges: new Set(), placedChips: new Set() };
    renderer.render({ mode: 'answer', form: 'capsule', interactive: false });

    els.title.textContent = '答案图';
    els.scopeLbl.textContent = '整理版广州地铁线网（2026 · 官方编号）· 可缩放查看';
    els.tilesBar.hidden = true;
    els.form.hidden = true;
    els.dock.hidden = true;
    els.hint.hidden = els.restart.hidden = els.giveup.hidden = true;
  }

  /* ---------- 通用 ---------- */

  function wireGame() {
    els.back.addEventListener('click', () => { teardown(); showSetup(); });
    els.restart.addEventListener('click', () => { if (!game?.answer) startGame(); });
    els.hint.addEventListener('click', useHint);
    els.giveup.addEventListener('click', giveUp);
    els.form.addEventListener('click', toggleForm);
    els.rsAgain.addEventListener('click', startGame);
    els.rsMenu.addEventListener('click', () => { els.result.hidden = true; teardown(); showSetup(); });
    els.rsView.addEventListener('click', () => { els.result.hidden = true; });
    els.filter.addEventListener('input', applyDockFilter);
    els.tilesBar.querySelectorAll('.tile-btn').forEach(btn =>
      btn.addEventListener('click', () => game?.renderer.setTiles(btn.dataset.tiles)));
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && !$('#metro-view').hidden) clearSelection();
    });
  }

  function applyDockFilter() {
    if (!game || game.answer) return;
    const q = els.filter.value.trim();
    let shown = 0;
    for (const [, c] of game.chips) {
      const lineOK = !lineFilter ||
        (c.kind === 'chip' ? c.value.split('|')[1] : c.kind === 'badge' ? c.value : null) === lineFilter;
      const hit = lineOK && (!q || chipSearchText2(c).includes(q));
      c.el.style.display = hit ? '' : 'none';
      if (hit) shown++;
    }
    updateHud(shown);
  }

  function chipSearchText2(c) {
    if (c.kind === 'name') return c.value;
    if (c.kind === 'badge') return c.value;
    const [nm, ln] = c.value.split('|');
    const rec = QD().chips.find(k => k.nm === nm && k.line === ln);
    const disp = QD().lines.find(l => l.name === ln)?.disp || ln;
    return (disp ? disp + '|' + (rec ? rec.serial : '') : '') + ln + nm;
  }

  function showSetup() {
    els.setup.hidden = false;
    els.game.hidden = true;
    els.result.hidden = true;
    updateBestLine();
  }

  function teardown() {
    if (game) {
      if (game.timerId) clearInterval(game.timerId);
      if (game.renderer) game.renderer.destroy();
    }
    game = null;
    selectedChip = null;
    lineFilter = null;
    els.canvas.innerHTML = '';
    els.pool.innerHTML = '';
    if (els.linePills) els.linePills.innerHTML = '';
    els.form.hidden = true;
  }

  function updateHud(shownOverride) {
    if (!game || game.answer) return;
    const total = game.items.length;
    const placed = total - game.chips.size;
    els.score.textContent = game.score;
    els.prog.textContent = `${placed}/${total}`;
    els.time.textContent = fmtTime(Math.floor((Date.now() - game.startTime) / 1000));
    const shown = shownOverride != null ? shownOverride : game.chips.size;
    els.count.textContent = game.chips.size
      ? `剩余 ${game.chips.size} / ${total} 个名牌${shown !== game.chips.size ? `（筛选出 ${shown}）` : ''}`
      : '全部放置完毕';
  }

  function toast(msg, good) {
    els.toast.textContent = msg;
    els.toast.classList.toggle('good', !!good);
    els.toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { els.toast.hidden = true; }, 1800);
  }

  function fmtTime(sec) {
    const m = Math.floor(sec / 60), s = sec % 60;
    return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
  }
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  return { init, showMode, __game: () => game };
})();

MetroQuiz.init();
