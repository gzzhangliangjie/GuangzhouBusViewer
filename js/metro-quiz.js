// 地铁拼图游戏逻辑：模式/风格/范围选择、名牌池、判分计时、历史最佳
// 渲染层（示意图 / 真实地图）通过统一接口注入，UI 逻辑不感知差异

const MetroQuiz = (() => {
  const BEST_KEY = 'gzmetro.best.v1';
  const $ = sel => document.querySelector(sel);

  const MODE_NAMES = { name: '站名模式', badge: '线号模式', both: '挑战模式' };

  const els = {
    setup: $('#metro-setup'), game: $('#metro-game'), result: $('#metro-result'),
    scopePicker: $('#scope-picker'), best: $('#metro-best'),
    canvas: $('#metro-canvas'), tilesBar: $('#metro-view .metro-tiles'),
    title: $('#mq-title'), scopeLbl: $('#mq-scope'),
    score: $('#mq-score'), time: $('#mq-time'), prog: $('#mq-prog'),
    hint: $('#mq-hint'), restart: $('#mq-restart'), giveup: $('#mq-giveup'), back: $('#mq-back'),
    official: $('#mq-official'),
    dock: $('#metro-dock'), pool: $('#chip-pool'), filter: $('#dock-filter'), count: $('#dock-count'),
    toast: $('#mq-toast'),
    rsTitle: $('#rs-title'), rsSub: $('#rs-sub'), rsBody: $('#rs-body'),
    rsAgain: $('#rs-again'), rsMenu: $('#rs-menu'), rsView: $('#rs-view')
  };

  const cfg = { mode: 'name', style: 'geo', scope: null };
  let game = null;        // 进行中/已结束的一局；{answer:true} 表示答案图浏览
  let selectedChip = null;
  let toastTimer = null;

  /* ---------- 初始化 ---------- */

  function init() {
    if (!MetroData.load()) return;
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
    if (name === 'roads' && window.RoadsView) RoadsView.show();
    if (name === 'metro') {
      if (!game) showSetup();
      else if (game.renderer && game.renderer.invalidate) game.renderer.invalidate();
    }
  }

  function wireSetup() {
    document.querySelectorAll('#metro-setup .opt-block').forEach(block => {
      const key = block.dataset.block;   // mode | style
      block.querySelectorAll('.opt-card').forEach(card =>
        card.addEventListener('click', () => {
          block.querySelectorAll('.opt-card').forEach(c => c.classList.remove('selected'));
          card.classList.add('selected');
          cfg[key] = card.dataset.v;
          updateBestLine();
        }));
    });
    $('#metro-start').addEventListener('click', startGame);
    $('#metro-answer').addEventListener('click', showAnswerView);
  }

  function buildScopePicker() {
    const mk = (value, label, colour, title) => {
      const b = document.createElement('button');
      b.className = 'scope-pill' + (value === cfg.scope ? ' selected' : '');
      b.dataset.v = value;
      // 线路用官方胶囊标识（线路色 + 白字），全网用中性样式
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
    els.scopePicker.appendChild(mk(null, '全网挑战', '', '全部 19 条线'));
    for (const l of MetroData.allLines()) {
      els.scopePicker.appendChild(mk(l.ref, MetroData.refLabel(l.ref), l.color, l.zh));
    }
  }

  /* ---------- 开局 ---------- */

  function startGame() {
    teardown();
    const items = buildItems();
    if (!items.length) return;

    // 先显示游戏区再创建地图，否则容器 0 尺寸导致 fitBounds 视野错误
    els.setup.hidden = true;
    els.game.hidden = false;
    els.result.hidden = true;

    const renderer = MetroMapView.create(els.canvas, { simple: cfg.style === 'schematic' });
    renderer.onStationClick((id, payload) => pickTarget('name', id, payload));
    renderer.onBadgeClick((ref, payload) => pickTarget('badge', ref, payload));

    game = {
      answer: false, renderer, items,
      chips: new Map(),           // chipKey -> {kind, value, el}
      placedNames: new Set(), placedBadges: new Set(),
      score: 0, corrects: 0, wrongs: 0, hints: 0,
      startTime: Date.now(), timerId: null, finished: false, revealed: false
    };

    renderer.render({
      scopeRef: cfg.scope,
      interactive: true,
      showStationNames: cfg.mode === 'badge',
      showBadges: cfg.mode === 'name' ? 'filled' : 'slots',
      placedNames: game.placedNames,
      placedBadges: game.placedBadges
    });

    renderChips(items);
    els.title.textContent = MODE_NAMES[cfg.mode];
    els.scopeLbl.textContent = (cfg.scope
      ? (MetroData.line(cfg.scope)?.zh || cfg.scope)
      : '全网挑战') + (cfg.style === 'schematic' ? ' · 纯线路图' : ' · 高德底图');

    els.tilesBar.hidden = cfg.style !== 'geo';
    els.dock.hidden = false;
    els.filter.value = '';
    els.filter.hidden = items.length <= 30;
    els.hint.disabled = false;
    els.hint.hidden = els.restart.hidden = els.giveup.hidden = false;
    els.official.hidden = true;

    updateHud();
    game.timerId = setInterval(updateHud, 1000);
  }

  function buildItems() {
    const items = [];
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
    // 洗牌：名牌顺序不泄露站点顺序
    for (let i = items.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [items[i], items[j]] = [items[j], items[i]];
    }
    return items;
  }

  /* ---------- 名牌池 ---------- */

  function chipKey(it) { return it.kind + ':' + it.value; }

  function renderChips(items) {
    els.pool.innerHTML = '';
    for (const it of items) {
      const key = chipKey(it);
      const el = document.createElement('span');
      el.className = 'mchip' + (it.kind === 'badge' ? ' mchip-badge' : '');
      el.draggable = true;
      if (it.kind === 'badge') {
        const l = MetroData.line(it.value);
        if (l) el.style.setProperty('--c', l.color);
        el.textContent = l ? l.zh : MetroData.refLabel(it.value);
        el.title = '线路徽章';
      } else {
        el.textContent = it.value;
      }
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

  // targetType: 'name'（站点）| 'badge'（线路槽）；payload 为拖拽带来的 "kind:value"
  function pickTarget(targetType, targetValue, payload) {
    if (!game || game.finished || game.answer) return;
    let chip = null;
    if (payload && game.chips.has(payload)) chip = game.chips.get(payload);
    else if (selectedChip) {
      for (const [key, c] of game.chips) {
        if (c.el === selectedChip) { chip = c; break; }
      }
    }
    if (!chip) return;

    if (chip.kind === targetType && chip.value === targetValue) {
      game.score += 100;
      game.corrects++;
      const label = chip.kind === 'name' ? chip.value : MetroData.refLabel(chip.value);
      toast(`✓ ${label} +100`, true);
      if (chip.kind === 'name') game.renderer.popFx && game.renderer.popFx(chip.value, '+100');
      place(chip);
      clearSelection();
      if (game.chips.size === 0) finish();
    } else {
      game.wrongs++;
      game.score = Math.max(0, game.score - 10);
      game.renderer.wrongFeedback(targetValue);
      toast('放错了 −10');
      clearSelection();
    }
    updateHud();
  }

  function place(chip) {
    game.chips.delete(chipKey(chip));
    chip.el.remove();
    if (chip.kind === 'name') {
      game.placedNames.add(chip.value);
      game.renderer.placeName(chip.value);
    } else {
      game.placedBadges.add(chip.value);
      game.renderer.placeBadge(chip.value);
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
    toast(`已自动放置「${chip.kind === 'name' ? chip.value : MetroData.refLabel(chip.value)}」 −50`);
    if (game.chips.size === 0) finish();
    else updateHud();
  }

  /* ---------- 结算 ---------- */

  function finish() {
    game.finished = true;
    clearInterval(game.timerId);
    const elapsed = Math.floor((Date.now() - game.startTime) / 1000);
    const quota = 150 + game.items.length * 25;   // 每个名牌 25s + 150s 起步
    const bonus = Math.round(Math.max(0, quota - elapsed) * 3 / 10) * 10;
    const total = game.score + bonus;
    const best = saveBest(total, elapsed);
    showResult({
      title: '🎉 拼图完成！',
      sub: `${MODE_NAMES[cfg.mode]} · ${cfg.scope ? MetroData.line(cfg.scope)?.zh : '全网挑战'}`,
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
        ['已放置', `${game.placedNames.size + game.placedBadges.size} / ${game.items.length}`],
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
    return `${cfg.mode}|${cfg.style}|${cfg.scope || '全网'}`;
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

  /* ---------- 答案图 ---------- */

  function showAnswerView() {
    teardown();
    // 先显示游戏区再创建地图，保证容器尺寸正确、答案图能正确聚焦
    els.setup.hidden = true;
    els.game.hidden = false;
    els.result.hidden = true;

    buildAnswerRenderer(false);

    els.title.textContent = '答案图';
    els.tilesBar.hidden = true;
    els.dock.hidden = true;
    els.hint.hidden = els.restart.hidden = els.giveup.hidden = true;
    els.official.hidden = false;
    els.official.textContent = '官方线网图';
  }

  // official=true 时显示完整版 Tim 线网图（矢量、带全部站名，仅浏览）
  function buildAnswerRenderer(official) {
    if (game && game.renderer) game.renderer.destroy();
    const renderer = official
      ? MetroMapView.createImageViewer(els.canvas)
      : MetroMapView.create(els.canvas, { simple: cfg.style === 'schematic' });
    game = { answer: true, official, renderer };
    if (!official) {
      renderer.render({
        scopeRef: cfg.scope, interactive: false,
        showStationNames: true, showBadges: 'filled',
        placedNames: new Set(), placedBadges: new Set()
      });
    }
    els.scopeLbl.textContent = official
      ? '完整线网图（Tim · 2026-07-30）· 可缩放查看'
      : (cfg.style === 'schematic' ? '纯线路图 · ' : '') +
        (cfg.scope ? MetroData.line(cfg.scope)?.zh : '全网') + ' · 可缩放查看';
  }

  function toggleOfficialMap() {
    if (!game || !game.answer) return;
    buildAnswerRenderer(!game.official);
    els.official.textContent = game.official ? '数据答案图' : '官方线网图';
  }

  /* ---------- 通用 ---------- */

  function wireGame() {
    els.back.addEventListener('click', () => { teardown(); showSetup(); });
    els.restart.addEventListener('click', () => { if (!game?.answer) startGame(); });
    els.hint.addEventListener('click', useHint);
    els.giveup.addEventListener('click', giveUp);
    els.rsAgain.addEventListener('click', startGame);
    els.rsMenu.addEventListener('click', () => { els.result.hidden = true; teardown(); showSetup(); });
    els.rsView.addEventListener('click', () => { els.result.hidden = true; });
    els.official.addEventListener('click', toggleOfficialMap);
    els.filter.addEventListener('input', () => {
      const q = els.filter.value.trim();
      let shown = 0;
      for (const [, c] of game.chips) {
        const hit = !q || (c.kind === 'name' ? c.value : MetroData.refLabel(c.value) + MetroData.line(c.value)?.zh).includes(q);
        c.el.style.display = hit ? '' : 'none';
        if (hit) shown++;
      }
      updateHud(shown);
    });
    els.tilesBar.querySelectorAll('.tile-btn').forEach(btn =>
      btn.addEventListener('click', () => game?.renderer.setTiles(btn.dataset.tiles)));
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && !$('#metro-view').hidden) clearSelection();
    });
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
    els.canvas.innerHTML = '';
    els.pool.innerHTML = '';
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
