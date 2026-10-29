// 路线规划视图：起终点输入（联想/钉确认/地图点选）+ 行程卡片 + Leaflet 绘制
// 引擎 = RoutePlanner（纯本地计算）；交互设计见 docs/route-planner-design.md §1.2
(() => {
  const $ = s => document.querySelector(s);
  const GUANGZHOU = [23.1291, 113.2644];

  let map = null;
  let planLayer = null;   // 行程绘制
  let fixLayer = null;    // 起终点钉
  let fromFix = null, toFix = null;
  let pickMode = null;    // 'from' | 'to' | null
  let pickGhost = null;
  let busy = false;
  let plans = null, selPlan = 0;   // Top-K 备选与当前选中
  let sortKey = 'time';            // 方案排序维度：'time' 耗时 | 'xfer' 换乘

  const els = {
    from: $('#route-from'), to: $('#route-to'),
    fromSug: $('#route-from-sug'), toSug: $('#route-to-sug'),
    fromClear: $('#route-from-clear'), toClear: $('#route-to-clear'),
    swap: $('#route-swap'), go: $('#route-go'),
    pickFrom: $('#route-pick-from'), pickTo: $('#route-pick-to'),
    status: $('#route-status'), plan: $('#route-plan')
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
    // 视图隐藏/切回/窗口缩放都会让 Leaflet 拿到 0 或旧尺寸（灰底旧账），ResizeObserver 兜底
    new ResizeObserver(() => map.invalidateSize({ animate: false }))
      .observe(document.querySelector('#route-map'));
    map.on('mousemove', onPickMove);
    map.on('click', onPickClick);
  }

  /* ---------- 起终点状态 ---------- */

  function setFix(side, fix) {
    if (side === 'from') { fromFix = fix; els.from.value = fix.name; }
    else { toFix = fix; els.to.value = fix.name; }
    const input = side === 'from' ? els.from : els.to;
    const clear = side === 'from' ? els.fromClear : els.toClear;
    input.classList.add('locked');
    clear.hidden = false;
    drawPins();
    updateGo();
    const p = project(fix.lat, fix.lng, fix.wgs !== false);
    map.flyTo(p, Math.max(map.getZoom(), 14));
    const r = fix.poi ? RoutePlanner.P.WALK_RADIUS_POI_M : RoutePlanner.P.WALK_RADIUS_STATION_M;
    status(`已选${side === 'from' ? '起点' : '终点'}：${fix.name}（接驳范围 ${r}m，可在地图核对位置）`);
  }

  function clearFix(side) {
    if (side === 'from') { fromFix = null; els.from.value = ''; els.from.classList.remove('locked'); els.fromClear.hidden = true; }
    else { toFix = null; els.to.value = ''; els.to.classList.remove('locked'); els.toClear.hidden = true; }
    drawPins();
    updateGo();
  }

  function updateGo() {
    els.go.disabled = busy || !(fromFix && toFix);
  }

  function drawPins() {
    fixLayer.clearLayers();
    const draw = (fix, colour, label) => {
      const p = project(fix.lat, fix.lng, fix.wgs !== false);
      L.circleMarker(p, { radius: 8, color: '#fff', weight: 2.5, fillColor: colour, fillOpacity: 1 })
        .bindTooltip(label + '：' + fix.name, { permanent: true, direction: 'top', offset: [0, -8], className: 'blab' })
        .addTo(fixLayer);
      L.circle(p, {
        radius: 2000,   // 步行接驳半径（站名/地名统一 2km，2026-10-29 用户令）
        color: colour, weight: 1, opacity: 0.5, fillOpacity: 0.04, dashArray: '5 6'
      }).addTo(fixLayer);
    };
    if (fromFix) draw(fromFix, '#2ea043', '起点');
    if (toFix) draw(toFix, '#e5534b', '终点');
  }

  /* ---------- 联想下拉（本地站名即时 + 地名 API 延迟补充 + 历史） ---------- */

  function wireInput(input, sug, side) {
    let items = [];       // {kind:'station'|'poi'|'history', name, poi?, histFrom?, histTo?}
    let active = -1;
    let poiTimer = null;

    const close = () => { sug.hidden = true; sug.innerHTML = ''; active = -1; };
    const others = side === 'from' ? els.toSug : els.fromSug;

    function entryHTML(it) {
      if (it.kind === 'history') {
        return `<span class="sug-badge hist">历史</span>` +
          `<span class="sug-name">${esc(it.histFrom.name)} → ${esc(it.histTo.name)}</span>` +
          `<span class="sug-meta">点击回填</span>`;
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
      return badges +
        `<span class="sug-name">${esc(it.name)}</span>` +
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
        setFix('from', it.histFrom);
        setFix('to', it.histTo);
        return;
      }
      if (it.kind === 'poi') {
        setFix(side, it.poi);
        return;
      }
      // 站名：同名多实例时取离对方端点最近的
      const other = side === 'from' ? toFix : fromFix;
      const otherPt = other ? { lat: other.lat, lng: other.lng } : null;
      const inst = RoutePlanner.resolveInstance(it.name, otherPt);
      if (inst) setFix(side, { name: it.name, lat: inst.lat, lng: inst.lng, wgs: true });
    }

    async function refresh() {
      const q = input.value.trim();
      if (!q) {
        const h = loadHistory();
        items = h.map(x => ({ kind: 'history', histFrom: x.from, histTo: x.to }));
        if (!items.length) { close(); return; }
        render();
        return;
      }
      items = RoutePlanner.suggest(q, 8).map(n => ({ kind: 'station', name: n.name }));
      active = -1;
      render();
      // 地名补充：本地没有精确命中时再查（防 API 抖动，缓存兜底）
      clearTimeout(poiTimer);
      if (q.length >= 2 && !items.some(i => i.kind === 'station' && i.name === q)) {
        poiTimer = setTimeout(async () => {
          const snapshot = input.value.trim();
          if (snapshot !== q) return;
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
      // 直接回车：精确站名 → 就近实例；否则按地名解析
      const fix = await resolveText(q);
      if (!fix) { status(`没有找到与「${q}」匹配的站名或地名`, true); return; }
      setFix(side, fix);
      if (side === 'from' && !toFix) els.to.focus();
      else if (fromFix && toFix) doPlan();
    });
  }

  /* ---------- 地图点选（吸附最近站） ---------- */

  function enterPick(side) {
    ensureMap();
    pickMode = side;
    document.querySelector('#route-map').classList.add('picking');
    els.pickFrom.classList.toggle('active', side === 'from');
    els.pickTo.classList.toggle('active', side === 'to');
    status('点选模式：在地图上点击选' + (side === 'from' ? '起点' : '终点') + '（自动吸附 800m 内最近站，Esc 取消）');
  }
  function exitPick() {
    pickMode = null;
    document.querySelector('#route-map').classList.remove('picking');
    els.pickFrom.classList.remove('active');
    els.pickTo.classList.remove('active');
    if (pickGhost) { map.removeLayer(pickGhost); pickGhost = null; }
  }
  // 地图坐标是 GCJ（高德底图），站网是 WGS：先反算再找最近站
  function onPickMove(e) {
    if (!pickMode || !RoutePlanner.stats().nodesN) return;
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
    if (!pickMode) return;
    const w = RoutePlanner.gcjToWgs(e.latlng.lat, e.latlng.lng);
    const nd = RoutePlanner.nearestNode(w[0], w[1], RoutePlanner.P.PICK_RADIUS_M);
    if (!nd) { status('800m 内没有站点，请再靠近一点点击', true); return; }
    const side = pickMode;
    exitPick();
    setFix(side, { name: nd.name, lat: nd.lat, lng: nd.lng, wgs: true });
    if (fromFix && toFix) status('起终点已就绪，点「查询路线」');
  }
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && pickMode) exitPick(); });

  /* ---------- 规划 ---------- */

  async function doPlan() {
    if (busy || !fromFix || !toFix) return;
    busy = true;
    updateGo();
    ensureMap();
    try {
      status('正在构建路线网络（首次约 1–2 秒）…', false, true);
      const info = await RoutePlanner.ready();
      status(`网络就绪（${info.nodesN} 站 · ${info.variantsN} 线）规划中…`, false, true);
      const r = RoutePlanner.planK ? RoutePlanner.planK(fromFix, toFix, 3) : { plans: [RoutePlanner.plan(fromFix, toFix)] };
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
      pushHistory(fromFix, toFix);
      const s = plans[0].summary;
      status(`共 ${plans.length} 个方案按耗时排序 · 最优约 ${s.totalMin} 分钟 · 换乘 ${s.transfers} 次 · 步行 ${s.walkM}m · 乘车 ${s.rideKm} km（点击分段可在地图定位）`);
    } catch (err) {
      status('规划失败：' + err.message, true);
    } finally {
      busy = false;
      updateGo();
    }
  }

  function fmtMin(m) { return Math.max(1, Math.round(m)) + ' 分钟'; }

  function renderPlan() {
    const r = plans[selPlan];
    const s = r.summary;
    let html = '';
    if (plans.length > 1) {
      // 双维度排序（2026-10-29 用户令：换乘数与耗时都要看），默认按耗时
      const order = plans.map((p, i) => i);
      if (sortKey === 'xfer') order.sort((a, b) =>
        plans[a].summary.transfers - plans[b].summary.transfers ||
        plans[a].summary.totalMin - plans[b].summary.totalMin);
      const minXfer = plans.reduce((m, p) =>
        p.summary.transfers < m.summary.transfers ? p : m, plans[0]).summary.transfers;
      html += '<div class="plan-sort">排序：' +
        `<button class="sort-btn${sortKey === 'time' ? ' active' : ''}" data-k="time">耗时</button>` +
        `<button class="sort-btn${sortKey === 'xfer' ? ' active' : ''}" data-k="xfer">换乘</button></div>`;
      html += '<div class="plan-alts">' + order.map(i => {
        const p = plans[i];
        const tag = p.summary.transfers === minXfer ? ' ·换乘少' : '';
        return `<button class="alt-chip${i === selPlan ? ' active' : ''}" data-i="${i}">` +
          `方案${i + 1} · 约${p.summary.totalMin}分钟 · 换乘${p.summary.transfers}${tag}</button>`;
      }).join('') + '</div>';
    }
    html += `<div class="plan-summary">` +
      `<b>约 ${s.totalMin} 分钟</b><span>换乘 ${s.transfers} 次 · 步行 ${s.walkM}m · 乘车 ${s.rideKm} km</span></div>`;
    html += '<div class="plan-legs">';
    r.legs.forEach((leg, i) => {
      if (leg.type === 'walk') {
        const edge = i === 0 || i === r.legs.length - 1;
        if (leg.m < 30 && edge) return;   // 起终点贴站的 0m 步行不显示
        const text = leg.m < 30 ? `站内换乘 → ${esc(leg.to.name)}`
          : `步行约 ${leg.m >= 1000 ? (leg.m / 1000).toFixed(1) + ' km' : Math.round(leg.m) + 'm'}：${esc(leg.from.name)} → ${esc(leg.to.name)}`;
        html += `<div class="leg walk${leg.m < 30 ? ' xfer' : ''}" data-kind="walk">` +
          `<span class="leg-icon">${leg.m < 30 ? '⇄' : '🚶'}</span>` +
          `<span class="leg-body">${text}</span>` +
          (leg.m < 30 ? '' : `<span class="leg-min">${fmtMin(leg.min)}</span>`) +
          `</div>`;
      } else {
        html += `<div class="leg ride" data-kind="ride">` +
          `<span class="leg-bar" style="background:${leg.colour}"></span>` +
          `<span class="leg-ref" style="background:${leg.colour}">${esc(shortRef(leg))}</span>` +
          `<span class="leg-body">${esc(leg.from.name)} → ${esc(leg.to.name)}<i>${leg.stops} 站 · ${esc(leg.direction)}</i></span>` +
          `<span class="leg-min">${fmtMin(leg.min)}</span></div>`;
      }
    });
    html += '</div>';
    els.plan.innerHTML = html;
    els.plan.querySelectorAll('.sort-btn').forEach(el =>
      el.addEventListener('click', () => { sortKey = el.dataset.k; renderPlan(); }));
    els.plan.querySelectorAll('.alt-chip').forEach(el =>
      el.addEventListener('click', () => {
        selPlan = +el.dataset.i;
        renderPlan();
        drawPlan(plans[selPlan]);
      }));
    const legEls = [...els.plan.querySelectorAll('.leg')];
    legEls.forEach(el =>
      el.addEventListener('click', () => flyLeg(r.legs[legEls.indexOf(el)])));
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
      // 步行段有真实路网折线（路网快照）则走真路，否则起终点直线
      const pts = (leg.pts || [[leg.from.lat, leg.from.lng], [leg.to.lat, leg.to.lng]])
        .map(([la, ln]) => project(la, ln));
      bounds.extend(L.latLngBounds(pts));
      if (leg.type === 'walk') {
        L.polyline(pts, { color: '#aab4be', weight: 3.5, opacity: 0.95, dashArray: '6 8', lineCap: 'round' }).addTo(planLayer);
        // 换乘接驳点：空心小圆
        for (const p of [pts[0], pts[pts.length - 1]]) {
          L.circleMarker(p, { radius: 4.5, color: '#101418', weight: 1.5, fillColor: '#fff', fillOpacity: 1, interactive: false }).addTo(planLayer);
        }
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
  function pushHistory(from, to) {
    try {
      let h = loadHistory().filter(x =>
        !(x.from.name === from.name && x.to.name === to.name));
      h.unshift({ from: pick(from), to: pick(to) });
      h = h.slice(0, 5);
      localStorage.setItem(HIST_KEY, JSON.stringify(h));
    } catch { /* 配额满放弃 */ }
    function pick(f) { return { name: f.name, lat: f.lat, lng: f.lng, wgs: f.wgs, poi: f.poi }; }
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /* ---------- 接线 ---------- */

  wireInput(els.from, els.fromSug, 'from');
  wireInput(els.to, els.toSug, 'to');
  els.fromClear.addEventListener('click', () => clearFix('from'));
  els.toClear.addEventListener('click', () => clearFix('to'));
  els.go.addEventListener('click', doPlan);
  els.pickFrom.addEventListener('click', () => pickMode === 'from' ? exitPick() : enterPick('from'));
  els.pickTo.addEventListener('click', () => pickMode === 'to' ? exitPick() : enterPick('to'));
  els.swap.addEventListener('click', () => {
    const f = fromFix, t = toFix;
    clearFix('from'); clearFix('to');
    if (t) setFix('from', t);
    if (f) setFix('to', f);
    els.plan.innerHTML = '';
    if (planLayer) planLayer.clearLayers();
  });

  function show() {
    ensureMap();
    setTimeout(() => map.invalidateSize({ animate: false }), 60);
  }

  window.RouteView = { show };
})();
