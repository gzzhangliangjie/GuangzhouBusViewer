// 路线规划视图：出行模式(公共交通/驾车/步行/公交/地铁) + 起终点/动态中途点
// （联想/钉确认/地图点选）+ 行程卡片 + Leaflet 绘制
// 引擎 = RoutePlanner.planK(fixes[], k, mode)；交互设计见 docs/route-planner-guide.md
(() => {
  const $ = s => document.querySelector(s);
  const GUANGZHOU = [23.1291, 113.2644];

  let map = null;
  let planLayer = null;   // 行程绘制
  let fixLayer = null;    // 起终点/中途点钉
  let mode = 'transit';   // transit | drive | walk | bus | metro
  let pickStop = null;    // 点选模式的目标行
  let pickGhost = null;
  let busy = false;
  let plans = null, selPlan = 0, sortKey = 'time';

  const MODE_LABEL = { transit: '公共交通', drive: '驾车', walk: '步行', bus: '公交', metro: '地铁' };
  const STOP_LABEL = { from: '起点', to: '终点', wp: '中途点' };
  const PIN_COLOUR = { from: '#2ea043', to: '#e5534b', wp: '#d29922' };
  const MAX_WP = 5;

  // 有序途经点模型：stops[0]=起点，中间=中途点，末位=终点
  let stops = [];

  const els = {
    modes: $('#route-modes'),
    wps: $('#route-wps'),
    addwp: $('#route-addwp'),
    swap: $('#route-swap'),
    go: $('#route-go'),
    status: $('#route-status'),
    plan: $('#route-plan')
  };

  // OSM(WGS-84) → 高德底图(GCJ-02)；wgs=false 表示坐标已是 GCJ（高德 POI）
  const project = (la, ln, wgs = true) => (wgs && window.GCJ ? GCJ.wgs84ToGcj02(la, ln) : [la, ln]);

  function status(msg, isErr, isBusy) {
    els.status.textContent = msg;
    els.status.classList.toggle('error', !!isErr);
    els.status.classList.toggle('busy', !!isBusy);
  }

  function ensureMap() {
    if (map) return;
    map = L.map('route-map', { zoomControl: true, preferCanvas: true }).setView(GUANGZHOU, 12);
    Tiles.createLayer('amap').addTo(map);
    planLayer = L.layerGroup().addTo(map);
    fixLayer = L.layerGroup().addTo(map);
    new ResizeObserver(() => map.invalidateSize({ animate: false }))
      .observe(document.querySelector('#route-map'));
    map.on('mousemove', onPickMove);
    map.on('click', onPickClick);
  }

  /* ---------- 行（站点）模型 ---------- */

  function makeStop(role, row) {
    const stop = {
      role, fix: null, row,
      input: row.querySelector('input'),
      sug: row.querySelector('.route-sug'),
      clear: row.querySelector('.io-clear'),
      pick: row.querySelector('.io-pick'),
      rm: row.querySelector('.io-rm')
    };
    wireStop(stop);
    return stop;
  }

  function setStop(stop, fix) {
    stop.fix = fix;
    stop.input.value = fix ? fix.name : '';
    stop.input.classList.toggle('locked', !!fix);
    if (stop.clear) stop.clear.hidden = !fix;
    drawPins();
    updateGo();
  }

  function clearStop(stop) { setStop(stop, null); }

  const fixedFixes = () => stops.filter(s => s.fix).map(s => s.fix);
  const stopLabel = stop => STOP_LABEL[stop.role] + (stop.role === 'wp' ? '：' + stop.fix.name : '');

  function updateGo() {
    const f = stops[0] && stops[0].fix, t = stops[stops.length - 1] && stops[stops.length - 1].fix;
    els.go.disabled = busy || !(f && t);
  }

  function drawPins() {
    fixLayer.clearLayers();
    let wpn = 0;
    for (const s of stops) {
      if (!s.fix) continue;
      const label = s.role === 'wp' ? '中途点' + (++wpn) : STOP_LABEL[s.role];
      const colour = PIN_COLOUR[s.role];
      const p = project(s.fix.lat, s.fix.lng, s.fix.wgs !== false);
      L.circleMarker(p, { radius: 8, color: '#fff', weight: 2.5, fillColor: colour, fillOpacity: 1 })
        .bindTooltip(label + '：' + s.fix.name, { permanent: true, direction: 'top', offset: [0, -8], className: 'blab' })
        .addTo(fixLayer);
      if (mode === 'transit' || mode === 'bus' || mode === 'metro') {
        L.circle(p, { radius: 2000, color: colour, weight: 1, opacity: 0.5, fillOpacity: 0.04, dashArray: '5 6' })
          .addTo(fixLayer);
      }
    }
  }

  /* ---------- 联想下拉（站名即时 + 地名 API 兜底 + 历史） ---------- */

  function wireStop(stop) {
    const { input, sug } = stop;
    let items = [];
    let active = -1;
    let poiTimer = null;
    const close = () => { sug.hidden = true; sug.innerHTML = ''; active = -1; };

    function entryHTML(it) {
      if (it.kind === 'history') {
        return `<span class="sug-badge hist">历史</span>` +
          `<span class="sug-name">${esc(it.text)}</span><span class="sug-meta">点击回填</span>`;
      }
      if (it.kind === 'poi') {
        const p = it.poi;
        return `<span class="sug-badge poi">地标</span>` +
          `<span class="sug-name">${esc(p.name)}</span>` +
          `<span class="sug-meta">${esc(p.district || p.type || '地名')}</span>`;
      }
      const inst = RoutePlanner.instancesOf(it.name);
      const lines = inst.length ? inst[0].lines : [];
      const badges = lines.slice(0, 3).map(l =>
        `<i class="sug-line" style="background:${l.colour}">${esc(l.label)}</i>`).join('');
      const extra = inst.length > 1 ? ` · ${inst.length} 个同名位置` : '';
      const hint = inst.length && inst[0].hint.length ? `邻近 ${inst[0].hint.join('/')}` : '';
      return badges + `<span class="sug-name">${esc(it.name)}</span>` +
        `<span class="sug-meta">${esc(hint + extra)}</span>`;
    }

    function render() {
      if (!items.length) { close(); return; }
      sug.innerHTML = items.map((it, i) =>
        `<div class="sug-item${i === active ? ' active' : ''}" data-i="${i}">${entryHTML(it)}</div>`).join('');
      sug.hidden = false;
      sug.querySelectorAll('.sug-item').forEach(el =>
        el.addEventListener('mousedown', e => { e.preventDefault(); pick(+el.dataset.i); }));
    }

    function pick(i) {
      const it = items[i];
      if (!it) return;
      close();
      if (it.kind === 'history') {
        applyHistory(it.hist);
        return;
      }
      if (it.kind === 'poi') { setStop(stop, it.poi); return; }
      const other = stops.find(s => s !== stop && s.fix);
      const inst = RoutePlanner.resolveInstance(it.name, other ? { lat: other.fix.lat, lng: other.fix.lng } : null);
      if (inst) setStop(stop, { name: it.name, lat: inst.lat, lng: inst.lng, wgs: true });
    }

    async function refresh() {
      const q = input.value.trim();
      if (!q) {
        const h = loadHistory().filter(x => x.fixes && x.mode);   // 兼容旧格式记录（无 fixes 直接丢弃）
        items = h.map(x => ({ kind: 'history', hist: x, text: x.fixes.map(f => f.name).join(' → ') + '（' + MODE_LABEL[x.mode] + '）' }));
        if (!items.length) { close(); return; }
        render();
        return;
      }
      items = RoutePlanner.suggest(q, 8).map(n => ({ kind: 'station', name: n.name }));
      active = -1;
      render();
      clearTimeout(poiTimer);
      if (q.length >= 2 && !items.some(i => i.kind === 'station' && i.name === q)) {
        poiTimer = setTimeout(async () => {
          if (input.value.trim() !== q) return;
          try {
            const r = await RoutePlanner.findPoi(q);
            if (input.value.trim() !== q || !r.items.length) return;
            items = items.filter(i => i.kind !== 'poi')
              .concat(r.items.slice(0, 6).map(p => ({ kind: 'poi', name: p.name, poi: p })));
            render();
          } catch { /* 联想主通道不受影响 */ }
        }, 400);
      }
    }

    async function resolveText(q) {
      const inst = RoutePlanner.resolveInstance(q, null);
      if (inst) return { name: q, lat: inst.lat, lng: inst.lng, wgs: true };
      status(`正在查找地名「${q}」…`, false, true);
      const r = await RoutePlanner.findPoi(q);
      if (r.items.length) {
        const p = r.items[0];
        status(`「${q}」已定位到 ${p.name}${p.district ? '（' + p.district + '）' : ''}`);
        return p;
      }
      return null;
    }

    input.addEventListener('focus', refresh);
    input.addEventListener('input', refresh);
    input.addEventListener('blur', () => setTimeout(close, 120));
    input.addEventListener('keydown', async e => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        if (sug.hidden) return;
        e.preventDefault();
        active = (active + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
        render();
        return;
      }
      if (e.key === 'Escape') { close(); return; }
      if (e.key !== 'Enter') return;
      e.preventDefault();
      const q = input.value.trim();
      if (!q) return;
      if (active >= 0 && !sug.hidden) { pick(active); return; }
      const fix = await resolveText(q);
      if (!fix) { status(`没有找到与「${q}」匹配的站名或地名`, true); return; }
      setStop(stop, fix);
      const idx = stops.indexOf(stop);
      if (idx < stops.length - 1) stops[idx + 1].input.focus();
      else doPlan();
    });

    if (stop.clear) stop.clear.addEventListener('click', () => clearStop(stop));
    if (stop.pick) stop.pick.addEventListener('click', () => pickStop === stop ? exitPick() : enterPick(stop));
    if (stop.rm) stop.rm.addEventListener('click', () => removeWaypoint(stop));
  }

  /* ---------- 中途点行管理 ---------- */

  const WP_ROW = `
    <span class="io-dot io-wp"></span>
    <div class="io-field">
      <input type="text" placeholder="中途点：站名或地名" autocomplete="off" />
      <button class="io-clear" title="清除" hidden>✕</button>
      <button class="io-pick" title="在地图上点选">📍</button>
      <div class="route-sug" hidden></div>
    </div>
    <button class="io-rm" title="删除此中途点">－</button>`;

  function addWaypoint(fix) {
    const wpCount = stops.filter(s => s.role === 'wp').length;
    if (wpCount >= MAX_WP) { status(`中途点最多 ${MAX_WP} 个`); return null; }
    const row = document.createElement('div');
    row.className = 'route-io wp';
    row.innerHTML = WP_ROW;
    els.wps.appendChild(row);
    const stop = makeStop('wp', row);
    stops.splice(stops.length - 1, 0, stop);   // 插到终点之前
    if (fix) setStop(stop, fix);
    return stop;
  }

  function removeWaypoint(stop) {
    if (stop.role !== 'wp') return;
    if (pickStop === stop) exitPick();
    stops = stops.filter(s => s !== stop);
    stop.row.remove();
    drawPins();
    updateGo();
  }

  /* ---------- 地图点选（吸附最近站） ---------- */

  function enterPick(stop) {
    ensureMap();
    pickStop = stop;
    document.querySelector('#route-map').classList.add('picking');
    stops.forEach(s => s.pick && s.pick.classList.toggle('active', s === stop));
    status('点选模式：为「' + STOP_LABEL[stop.role] + '」在地图上点击选位（吸附 800m 内最近站，Esc 取消）');
  }
  function exitPick() {
    pickStop = null;
    document.querySelector('#route-map').classList.remove('picking');
    stops.forEach(s => s.pick && s.pick.classList.remove('active'));
    if (pickGhost) { map.removeLayer(pickGhost); pickGhost = null; }
  }
  function onPickMove(e) {
    if (!pickStop || !RoutePlanner.stats().nodesN) return;
    const w = RoutePlanner.gcjToWgs(e.latlng.lat, e.latlng.lng);
    const nd = RoutePlanner.nearestNode(w[0], w[1], RoutePlanner.P.PICK_RADIUS_M);
    if (pickGhost) { map.removeLayer(pickGhost); pickGhost = null; }
    if (nd) {
      const p = project(nd.lat, nd.lng);
      pickGhost = L.circleMarker(p, { radius: 9, color: '#ffd54a', weight: 3, fillColor: '#fff', fillOpacity: 0.9 })
        .bindTooltip(`${nd.name}（${nd.m}m）`, { permanent: true, direction: 'top', offset: [0, -8], className: 'blab' })
        .addTo(map);
    }
  }
  function onPickClick(e) {
    if (!pickStop) return;
    const w = RoutePlanner.gcjToWgs(e.latlng.lat, e.latlng.lng);
    const nd = RoutePlanner.nearestNode(w[0], w[1], RoutePlanner.P.PICK_RADIUS_M);
    if (!nd) { status('800m 内没有站点，请再靠近一点点击', true); return; }
    const stop = pickStop;
    exitPick();
    setStop(stop, { name: nd.name, lat: nd.lat, lng: nd.lng, wgs: true });
  }
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && pickStop) exitPick(); });

  /* ---------- 出行模式 ---------- */

  function setMode(m) {
    mode = m;
    els.modes.querySelectorAll('.mode-chip').forEach(b => b.classList.toggle('active', b.dataset.m === m));
    els.plan.innerHTML = '';
    if (planLayer) planLayer.clearLayers();
    plans = null;
    drawPins();
    updateGo();
    const hint = {
      transit: '公共交通：步行 + 公交 + 地铁联合规划（可加中途点）',
      drive: '驾车：按路网实测距离与类别车速估算（不含实时路况）',
      walk: '步行：全程沿步行网真实路径',
      bus: '纯公交：只乘公交线路（含步行接驳）',
      metro: '纯地铁：只乘地铁线路（含步行接驳）'
    }[m];
    status(hint + '。输入起点与终点' + (mode === 'transit' || mode === 'drive' ? '，可加中途点' : '。'));
  }

  /* ---------- 规划 ---------- */

  async function doPlan() {
    const fixes = fixedFixes();
    if (busy || !stops[0].fix || !stops[stops.length - 1].fix || fixes.length < 2) return;
    busy = true;
    updateGo();
    ensureMap();
    try {
      status('正在构建路线网络（首次约 1–3 秒）…', false, true);
      const info = await RoutePlanner.ready();
      status(`网络就绪（${info.nodesN} 站 · ${info.variantsN} 线）规划中…`, false, true);
      // sortKey 即逐段选拔口径（2026-11-03 用户令"优先时间那几段都优先时间，优先换乘
      // 那几段都优先换乘"）：途经点链每段按同一口径独立选段；偏好跨查询持久
      const r = RoutePlanner.planK(fixes, 3, mode, sortKey);
      if (r.error) { status(r.error, true); return; }
      if (!r.plans.length) {
        els.plan.innerHTML = '';
        planLayer.clearLayers();
        status('起点与终点很近（<150m），步行即可');
        return;
      }
      plans = r.plans;
      selPlan = 0;
      renderPlan();
      drawPlan(plans[0]);
      pushHistory(fixes, mode);
      const s = plans[0].summary;
      const head = plans.length > 1 ? `共 ${plans.length} 个方案按${sortKey === 'xfer' ? '换乘' : '耗时'}排序 · ` : '';
      status(head + summarize(s));
    } catch (err) {
      status('规划失败：' + err.message, true);
    } finally {
      busy = false;
      updateGo();
    }
  }

  function summarize(s) {
    if (mode === 'drive') return `驾车约 ${s.totalMin} 分钟 · ${s.rideKm} km（估算，不含实时路况）`;
    if (mode === 'walk') return `步行约 ${s.totalMin} 分钟 · ${s.walkM}m`;
    return `最优约 ${s.totalMin} 分钟 · 换乘 ${s.transfers} 次 · 步行 ${s.walkM}m · 乘车 ${s.rideKm} km（点击分段可在地图定位）`;
  }

  function fmtMin(m) { return Math.max(1, Math.round(m)) + ' 分钟'; }
  function fmtDist(m) { return m >= 1000 ? (m / 1000).toFixed(1) + ' km' : Math.round(m) + 'm'; }

  function renderPlan() {
    const r = plans[selPlan];
    const s = r.summary;
    let html = '';
    // 途经点链（公共交通族）单方案也要出排序行：sortKey 是逐段选拔口径，切换即重算
    const perSeg = mode !== 'drive' && mode !== 'walk' && r.segments;
    if (plans.length > 1 || perSeg) {
      const order = plans.map((p, i) => i);
      if (sortKey === 'xfer') order.sort((a, b) =>
        plans[a].summary.transfers - plans[b].summary.transfers ||
        plans[a].summary.totalMin - plans[b].summary.totalMin);
      const minXfer = plans.reduce((m, p) =>
        p.summary.transfers < m.summary.transfers ? p : m, plans[0]).summary.transfers;
      html += '<div class="plan-sort">排序：' +
        `<button class="sort-btn${sortKey === 'time' ? ' active' : ''}" data-k="time">耗时</button>` +
        `<button class="sort-btn${sortKey === 'xfer' ? ' active' : ''}" data-k="xfer">换乘</button></div>`;
      if (plans.length > 1) html += '<div class="plan-alts">' + order.map(i => {
        const p = plans[i];
        const xferTag = mode !== 'drive' && mode !== 'walk' && p.summary.transfers === minXfer ? ' ·换乘少' : '';
        const ptag = p.tag ? ' ·' + p.tag : '';
        const dist = mode === 'walk' ? ' · ' + fmtDist(p.summary.walkM) : ' · ' + p.summary.rideKm + ' km';
        return `<button class="alt-chip${i === selPlan ? ' active' : ''}" data-i="${i}">` +
          `方案${i + 1} · 约${p.summary.totalMin}分钟${ptag}${xferTag}${dist}</button>`;
      }).join('') + '</div>';
    }
    html += `<div class="plan-summary"><b>${summarize(s)}</b></div>`;
    html += '<div class="plan-legs">';
    r.legs.forEach((leg, i) => {
      if (leg.type === 'wp') {
        html += `<div class="leg wpmark">📍 中途点：${esc(leg.name)}</div>`;
        return;
      }
      if (leg.type === 'walk') {
        const edge = i === 0 || i === r.legs.length - 1;   // 仅首末位 <30m 贴站步行隐藏，中段站内换乘照常显示
        if (leg.m < 30 && edge) return;
        const text = leg.m < 30 ? `站内换乘 → ${esc(leg.to.name)}`
          : `步行约 ${fmtDist(leg.m)}：${esc(leg.from.name)} → ${esc(leg.to.name)}`;
        html += `<div class="leg walk${leg.m < 30 ? ' xfer' : ''}">` +
          `<span class="leg-icon">${leg.m < 30 ? '⇄' : '🚶'}</span>` +
          `<span class="leg-body">${text}</span>` +
          (leg.m < 30 ? '' : `<span class="leg-min">${fmtMin(leg.min)}</span>`) +
          `</div>`;
      } else if (leg.type === 'drive') {
        html += `<div class="leg drive">` +
          `<span class="leg-icon">🚗</span>` +
          `<span class="leg-ref" style="background:#4a9eff">驾车</span>` +
          `<span class="leg-body">${esc(leg.from.name)} → ${esc(leg.to.name)}<i>${fmtDist(leg.m)} · 沿通行路网</i></span>` +
          `<span class="leg-min">${fmtMin(leg.min)}</span></div>`;
      } else {
        html += `<div class="leg ride">` +
          `<span class="leg-bar" style="background:${leg.colour}"></span>` +
          `<span class="leg-ref" style="background:${leg.colour}">${esc(shortRef(leg))}</span>` +
          `<span class="leg-body">${esc(leg.from.name)} → ${esc(leg.to.name)}<i>${leg.stops} 站 · ${esc(leg.direction)}</i></span>` +
          `<span class="leg-min">${fmtMin(leg.min)}</span></div>`;
      }
    });
    html += '</div>';
    els.plan.innerHTML = html;
    els.plan.querySelectorAll('.sort-btn').forEach(el =>
      el.addEventListener('click', () => {
        sortKey = el.dataset.k;
        // 途经点链（公共交通族）的 sortKey 是逐段选拔口径：切换即重算；两点/驾车/步行只重排
        if (mode !== 'drive' && mode !== 'walk' && plans && plans[0] && plans[0].segments) doPlan();
        else renderPlan();
      }));
    els.plan.querySelectorAll('.alt-chip').forEach(el =>
      el.addEventListener('click', () => {
        selPlan = +el.dataset.i;
        renderPlan();
        drawPlan(plans[selPlan]);
      }));
    const legEls = [...els.plan.querySelectorAll('.leg')];
    legEls.forEach(el => {
      const idx = legEls.indexOf(el);
      const leg = r.legs[idx];
      if (leg && (leg.type === 'ride' || leg.type === 'drive' || leg.type === 'walk'))
        el.addEventListener('click', () => flyLeg(leg));
    });
  }

  function shortRef(leg) {
    const m = String(leg.ref || '').match(/^(GF|APM线|\d+号线?|\d+)/);
    return m ? m[1] : leg.ref;
  }

  function flyLeg(leg) {
    const pts = (leg.pts || [[leg.from.lat, leg.from.lng], [leg.to.lat, leg.to.lng]])
      .map(([la, ln]) => project(la, ln));
    map.fitBounds(L.latLngBounds(pts), { padding: [60, 60], maxZoom: 16 });
  }

  function drawPlan(r) {
    planLayer.clearLayers();
    const bounds = L.latLngBounds([]);
    for (const leg of r.legs) {
      if (leg.type === 'wp') continue;
      const pts = (leg.pts || [[leg.from.lat, leg.from.lng], [leg.to.lat, leg.to.lng]])
        .map(([la, ln]) => project(la, ln));
      bounds.extend(L.latLngBounds(pts));
      if (leg.type === 'walk') {
        L.polyline(pts, { color: '#aab4be', weight: 3.5, opacity: 0.95, dashArray: '6 8', lineCap: 'round' }).addTo(planLayer);
        if (leg.keep !== true) for (const p of [pts[0], pts[pts.length - 1]]) {
          L.circleMarker(p, { radius: 4.5, color: '#101418', weight: 1.5, fillColor: '#fff', fillOpacity: 1, interactive: false }).addTo(planLayer);
        }
      } else if (leg.type === 'drive') {
        L.polyline(pts, { color: '#0d3b66', weight: 8, opacity: 0.6, lineCap: 'round', lineJoin: 'round', interactive: false }).addTo(planLayer);
        L.polyline(pts, { color: '#4a9eff', weight: 4.5, opacity: 1, lineCap: 'round', lineJoin: 'round', interactive: false }).addTo(planLayer);
      } else {
        L.polyline(pts, { color: '#101418', weight: 7.5, opacity: 0.55, lineCap: 'round', lineJoin: 'round', interactive: false }).addTo(planLayer);
        L.polyline(pts, { color: leg.colour, weight: 4.5, opacity: 1, lineCap: 'round', lineJoin: 'round', interactive: false }).addTo(planLayer);
      }
    }
    drawPins();
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [50, 50], maxZoom: 15 });
  }

  /* ---------- 最近查询历史 ---------- */

  const HIST_KEY = 'gzbus.route.recent.v1';
  function loadHistory() {
    try { return JSON.parse(localStorage.getItem(HIST_KEY)) || []; } catch { return []; }
  }
  function pushHistory(fixes, m) {
    try {
      const pick = f => ({ name: f.name, lat: f.lat, lng: f.lng, wgs: f.wgs, poi: f.poi });
      let h = loadHistory().filter(x => !(x.fixes[0].name === fixes[0].name && x.fixes[fixes.length - 1].name === fixes[fixes.length - 1].name));
      h.unshift({ mode: m, fixes: fixes.map(pick) });
      localStorage.setItem(HIST_KEY, JSON.stringify(h.slice(0, 5)));
    } catch { /* 配额满放弃 */ }
  }
  function applyHistory(h) {
    setMode(h.mode || 'transit');
    // 需要的中途点行数
    while (stops.filter(s => s.role === 'wp').length < h.fixes.length - 2) addWaypoint();
    while (stops.filter(s => s.role === 'wp').length > h.fixes.length - 2) {
      removeWaypoint(stops.find(s => s.role === 'wp'));
    }
    const withFix = stops.filter(s => s.role === 'wp');
    h.fixes.slice(1, -1).forEach((f, i) => setStop(withFix[i], f));
    setStop(stops[0], h.fixes[0]);
    setStop(stops[stops.length - 1], h.fixes[h.fixes.length - 1]);
    doPlan();
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /* ---------- 初始化 ---------- */

  function init() {
    ensureMapOrder();
    stops.push(makeStop('from', document.querySelector('#route-io-from')));
    stops.push(makeStop('to', document.querySelector('#route-io-to')));
    els.modes.querySelectorAll('.mode-chip').forEach(b =>
      b.addEventListener('click', () => setMode(b.dataset.m)));
    els.addwp.addEventListener('click', () => { addWaypoint(); updateGo(); });
    els.go.addEventListener('click', doPlan);
    els.swap.addEventListener('click', () => {
      const fixes = stops.map(s => s.fix).reverse();
      stops.forEach((s, i) => setStop(s, fixes[i]));
      els.plan.innerHTML = '';
      if (planLayer) planLayer.clearLayers();
    });
  }
  // 保证 from 行在最前、to 行在最后（HTML 静态顺序即如此）
  function ensureMapOrder() {}

  function show() {
    ensureMap();
    setTimeout(() => map.invalidateSize({ animate: false }), 60);
  }

  init();
  window.RouteView = { show };
})();
