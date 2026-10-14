// UI 主逻辑：线路列表、搜索、选中线路 → 加载几何 → 地图绘制

(() => {
  const $ = sel => document.querySelector(sel);

  const els = {
    list: $('#line-list'),
    count: $('#line-count'),
    search: $('#search'),
    refresh: $('#refresh'),
    status: $('#status'),
    detail: $('#line-detail'),
    active: $('#active-lines'),
    loading: $('#loading')
  };

  const PALETTE = ['#e5534b', '#4a9eff', '#2ea043', '#d29922', '#bf63ff',
                   '#39c5cf', '#ff7b72', '#f0883e', '#7ee787', '#79c0ff'];

  const state = {
    index: [],            // [{id, ref, name, from, to, operator, colour}]
    filtered: [],
    active: new Map(),    // ref -> { variants, current, group, colour }
    selectedRef: null,
    colourSeq: 0
  };

  window.AppHooks = { onStopClick: null };

  /* ---------- 初始化 ---------- */

  MapLayer.init();

  document.querySelectorAll('.tile-btn').forEach(btn =>
    btn.addEventListener('click', () => {
      MapLayer.setTiles(btn.dataset.tiles);
      redrawAll(); // 底图坐标系变化，全部线路重画
    }));

  els.search.addEventListener('input', () => renderList());
  els.search.addEventListener('keydown', e => {
    if (e.key !== 'Enter') return;
    const q = els.search.value.trim();
    if (!q || state.index.length > 0) return;
    // 索引尚未就绪（拉取失败/进行中）时，直接按线路号查询该线路
    setStatus(`线路列表未就绪，直接查询「${q}」的路线几何…`);
    selectLine(q);
  });
  els.refresh.addEventListener('click', () => loadIndex(true));
  els.search.focus();

  loadIndex(false);

  /* ---------- 线路索引 ---------- */

  async function loadIndex(force) {
    setStatus(force ? '正在刷新线路列表…' : '正在从 Overpass 拉取全市线路列表（首次约 10-30 秒）…');
    els.refresh.disabled = true;
    setLoading(true);
    try {
      state.index = await Overpass.fetchLineIndex({
        force,
        onMirrorFail: (m, e) => setStatus(`镜像 ${hostOf(m)} 失败（${e.message}），尝试下一个…`)
      });
      state.index.sort((a, b) => a.ref.localeCompare(b.ref, 'zh-Hans-CN', { numeric: true }));
      els.count.textContent = state.index.length;
      setStatus(`已加载 ${state.index.length} 条线路记录（每 24 小时自动更新缓存）`);
      renderList();
    } catch (err) {
      setStatus('线路列表获取失败：' + err.message + '，可点击“刷新”重试', true);
    } finally {
      els.refresh.disabled = false;
      setLoading(false);
    }
  }

  function renderList() {
    const q = els.search.value.trim().toLowerCase();
    const kw = q.replace(/\s+/g, '');

    state.filtered = !kw ? state.index : state.index.filter(l => {
      const hay = (l.ref + ' ' + l.name + ' ' + l.from + ' ' + l.to + ' ' + l.operator).toLowerCase();
      return hay.replace(/\s+/g, '').includes(kw);
    });

    const frag = document.createDocumentFragment();
    for (const l of state.filtered.slice(0, 500)) {
      const li = document.createElement('li');
      li.dataset.ref = l.ref;
      const badgeColour = state.active.has(l.ref) ? colourOf(l.ref) : '';
      li.innerHTML =
        `<span class="ref-badge"${badgeColour ? ` style="background:${badgeColour}"` : ''}>${esc(l.ref)}</span>` +
        `<span class="line-name">${esc(l.name || ((l.from || '?') + ' → ' + (l.to || '?')))}</span>`;
      li.addEventListener('click', () => selectLine(l.ref));
      if (l.ref === state.selectedRef) li.classList.add('active');
      frag.appendChild(li);
    }
    els.list.innerHTML = '';
    els.list.appendChild(frag);

    if (state.filtered.length > 500) {
      const tip = document.createElement('li');
      tip.innerHTML = `<span class="line-name">… 共 ${state.filtered.length} 条，仅显示前 500 条，请继续输入筛选</span>`;
      tip.style.cursor = 'default';
      els.list.appendChild(tip);
    }
    if (state.filtered.length === 0 && state.index.length > 0) {
      els.list.innerHTML = '<li style="cursor:default"><span class="line-name">没有匹配的线路</span></li>';
    }
  }

  /* ---------- 选中线路 ---------- */

  async function selectLine(ref, preloadedVariants) {
    if (state.active.has(ref)) {
      openDetail(ref);
      highlightListItem(ref);
      return;
    }
    setLoading(true);
    setStatus(`正在查询 ${ref} 路线几何…`);
    try {
      const variants = preloadedVariants || await Overpass.fetchLineByRef(ref, {
        onMirrorFail: (m, e) => setStatus(`镜像 ${hostOf(m)} 失败，尝试下一个…`)
      });
      if (!variants || variants.length === 0) {
        setStatus(`未在 OSM 中找到「${ref}」的路线几何数据`, true);
        return;
      }
      const colour = variants[0].colour || PALETTE[state.colourSeq++ % PALETTE.length];
      state.active.set(ref, { variants, current: variants[0], group: null, colour });
      drawActive(ref);
      openDetail(ref);
      renderChips();
      renderList();
      setStatus(`已加载 ${ref}（${variants.length} 个方向/变体）`);
    } catch (err) {
      setStatus(`加载 ${ref} 失败：` + err.message, true);
    } finally {
      setLoading(false);
      highlightListItem(ref);
    }
  }

  // 离线/测试注入：加载与 Overpass.fetchLineByRef 同结构的 JSON 并直接绘制
  window.GzBusDebug = {
    async loadFixture(url) {
      const res = await fetch(url);
      if (!res.ok) throw new Error('fixture HTTP ' + res.status);
      const variants = await res.json();
      if (!Array.isArray(variants) || !variants.length) throw new Error('fixture 为空');
      await selectLine(variants[0].ref, variants);
      return variants[0].ref;
    }
  };

  function drawActive(ref) {
    const entry = state.active.get(ref);
    if (!entry) return;
    if (entry.group) MapLayer.removeGroup(entry.group);
    entry.group = MapLayer.drawVariant(entry.current, entry.colour, false);
    MapLayer.addGroup(entry.group);
  }

  function openDetail(ref) {
    const entry = state.active.get(ref);
    if (!entry) return;
    state.selectedRef = ref;

    const v = entry.current;
    const dirBtns = entry.variants.map((vt, i) =>
      `<button data-vi="${i}" class="${vt.id === v.id ? 'active' : ''}">${esc(dirLabel(vt))}</button>`
    ).join('');

    const stopItems = v.stops.map((s, i) =>
      `<div class="stop-item" data-i="${i}"><span class="stop-idx">${i + 1}</span><span>${esc(s.name)}</span></div>`
    ).join('');

    els.detail.innerHTML =
      `<div class="detail-head">` +
        `<span class="ref-badge" style="background:${entry.colour}">${esc(v.ref)}</span>` +
        `<div class="detail-title">` +
          `<div>${esc(v.name || '')}</div>` +
          `<div style="color:#8b949e;font-size:11.5px;margin-top:2px">` +
            `${esc(v.operator || '未知运营方')}${v.note ? ' · ' + esc(v.note) : ''}</div>` +
        `</div>` +
        `<button class="detail-close" title="关闭详情">✕</button>` +
      `</div>` +
      `<div class="dir-tabs">${dirBtns}</div>` +
      `<div class="stop-list">${stopItems || '<div class="stop-item" style="cursor:default">该路线在 OSM 中未标注站点</div>'}</div>`;

    els.detail.hidden = false;

    els.detail.querySelector('.detail-close').addEventListener('click', () => { els.detail.hidden = true; });
    els.detail.querySelectorAll('.dir-tabs button').forEach(btn => {
      btn.addEventListener('click', () => {
        entry.current = entry.variants[+btn.dataset.vi];
        drawActive(ref);
        openDetail(ref);
      });
    });
    els.detail.querySelectorAll('.stop-item[data-i]').forEach(item => {
      item.addEventListener('click', () => {
        const s = entry.current.stops[+item.dataset.i];
        if (s) MapLayer.flyTo(s.lat, s.lng, 16);
      });
    });

    if (entry.group) MapLayer.fitLayerGroup(entry.group);
  }

  function dirLabel(vt) {
    if (vt.to) return '往 ' + vt.to;
    const m = (vt.name || '').split('：');
    return m[1] || vt.name || '方向 ' + vt.id;
  }

  /* ---------- 已加载线路 chips ---------- */

  function renderChips() {
    els.active.innerHTML = '';
    for (const [ref, entry] of state.active) {
      const chip = document.createElement('span');
      chip.className = 'chip';
      chip.innerHTML =
        `<span class="dot" style="background:${entry.colour}"></span>${esc(ref)}` +
        `<span class="rm" title="移除">✕</span>`;
      chip.querySelector('.rm').addEventListener('click', () => removeLine(ref));
      chip.addEventListener('click', e => {
        if (e.target.classList.contains('rm')) return;
        openDetail(ref);
        highlightListItem(ref);
      });
      els.active.appendChild(chip);
    }
  }

  function removeLine(ref) {
    const entry = state.active.get(ref);
    if (entry && entry.group) MapLayer.removeGroup(entry.group);
    state.active.delete(ref);
    if (state.selectedRef === ref) {
      state.selectedRef = null;
      els.detail.hidden = true;
    }
    renderChips();
    renderList();
  }

  function redrawAll() {
    for (const [ref] of state.active) drawActive(ref);
  }

  function colourOf(ref) {
    const e = state.active.get(ref);
    return e ? e.colour : '';
  }

  function highlightListItem(ref) {
    els.list.querySelectorAll('li').forEach(li =>
      li.classList.toggle('active', li.dataset.ref === ref));
  }

  /* ---------- 工具 ---------- */

  function setStatus(msg, isErr) {
    els.status.textContent = msg;
    els.status.classList.toggle('error', !!isErr);
  }
  function setLoading(on) { els.loading.hidden = !on; }
  function hostOf(url) { try { return new URL(url).host; } catch { return url; } }
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
})();
