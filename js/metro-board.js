// 官方线网图棋盘渲染器（整理版 network-全网 SVG 自锚定拼图）
//   棋盘 = 整理好的线网图产品本身（基础图: 走廊+站圆+站名+徽标 / codes图: 再加编号牌）
//   拼图 = 把图上真实元素（站名文字 / 线路徽标 / 编号牌）藏起来，玩家拖回原位
//   身份 = SVG 自身属性（站圆 data-nm / 徽标 data-term+线名文字 / 编号牌=配对数据文件），
//          无文档序假设；元素原位复原 = 字节级还原已验收状态
// 交互: 站点透明热区 + 牌位槽格（扩边命中）、60px 就近磁吸（拖放与点击共用，
// 点击精确命中槽位/热区时由元素自身处理，落空时容器级就近兜底）、悬停高亮、绿成功红扣分
// 坐标: L.CRS.Simple，latLng=[-y, x]（图面坐标直通），底图 wrapper 只用 translate+显式尺寸
//       （不用 scale 变换——GPU 纹理上限会裁掉大 SVG，见 metro-map.js 同款处理）

const MetroBoard = (() => {
  const QD = () => window.QUIZ_NETWORK_DATA;
  const SNAP_PX = 60;      // 容器级就近判定半径：拖放磁吸与点击兜底共用（2026-10-26 用户令扩大响应区，46→60）

  /* ---------- 棋盘装载 ---------- */

  // 圆圈形式 = 基础图（站圆+换乘胶囊）；胶囊形式/答案图 = codes 变体（官方编号牌替代站圆）
  function boardSvgUrl(m, form) {
    const useCodes = m === 'answer' || form === 'capsule';
    return 'assets/lines/network-全网' + (useCodes ? '.codes' : '') + '.svg';
  }

  function fetchBoard(m, form) {
    return fetch(boardSvgUrl(m, form)).then(r => {
      if (!r.ok) throw new Error('board svg HTTP ' + r.status);
      return r.text();
    }).then(txt => {
      const holder = document.createElement('div');
      holder.style.cssText = 'width:100%;height:100%;';
      holder.innerHTML = txt;
      const svg = holder.querySelector('svg');
      if (!svg) throw new Error('无 <svg> 根');
      svg.removeAttribute('width');
      svg.removeAttribute('height');
      svg.style.width = '100%';
      svg.style.height = '100%';
      return { holder, svg };
    });
  }

  // 编号牌没有身份属性（§1.6 唯一残余文档序通道），配对真源 = gen-quiz-data.py 产出的
  // 数据文件（几何双射校验过）。这里按坐标把 DOM 元素聚到牌键下，聚不全=结构异常，报错。
  function bindChipClusters(svg, chips) {
    const grp = svg.querySelector('#编号牌');
    if (!grp) throw new Error('codes 棋盘缺少编号牌组');
    const geomKey = el => [el.getAttribute('x'), el.getAttribute('y'),
      el.getAttribute('width'), el.getAttribute('height')]
      .map(v => parseFloat(v).toFixed(2)).join(',');
    const clusters = new Map();   // 'x,y,w,h' -> [rect, line, text, text]
    for (const rect of grp.querySelectorAll('rect')) {
      if ((rect.getAttribute('fill') || '').toUpperCase() !== '#FFFFFF') continue;
      const cluster = [rect];
      let sib = rect.nextElementSibling;
      while (sib && cluster.length < 4 && sib.tagName.toLowerCase() !== 'rect') {
        cluster.push(sib);
        sib = sib.nextElementSibling;
      }
      if (cluster.length !== 4) throw new Error('编号牌簇结构异常(非 rect,line,text,text)');
      clusters.set(geomKey(rect), cluster);
    }
    const bound = new Map();      // chipKey -> [elements]
    for (const c of chips) {
      const key = c.nm + '|' + c.line;
      const cluster = clusters.get([c.x, c.y, c.w, c.h].map(v => v.toFixed(2)).join(','));
      if (!cluster) throw new Error('编号牌数据 (' + key + ') 在 DOM 无对应 rect');
      bound.set(key, cluster);
    }
    if (bound.size !== chips.length) throw new Error('编号牌配对数不符');
    return bound;
  }

  /* ---------- 棋盘实例 ---------- */

  function create(container) {
    const view = {};
    let map = null;
    let boardWrap = null;      // 底图 wrapper（translate 同步，位于 mapPane 之下）
    let overlayWrap = null;    // 槽位层（百分比定位，位于 mapPane 之上）
    let svg = null;
    let mode = 'name';
    let lastOpts = null;
    let loadSeq = 0;

    const stationHot = new Map();   // nm -> L.circleMarker 热区
    const slotEls = new Map();      // value -> {el, kind, value}（badge 用线名 / chip 用 键）
    const nameEls = new Map();      // nm -> [text]
    const badgeEls = new Map();     // 线名 -> [g]
    let chipClusters = new Map();   // chipKey -> [elements]（codes 棋盘）
    const injectedChips = new Map(); // chipKey -> svg（圆圈棋盘无编号牌 DOM，按配对数据注入）
    let dimRefs = [];
    let snapRef = null;
    let stationCb = null, badgeCb = null, chipCb = null;

    const VB = () => QD().viewBox;
    const ll = (x, y) => L.latLng(-y, x);
    const px = (x, y) => map.latLngToContainerPoint(ll(x, y));

    /* ---------- 底图同步（translate + 显式尺寸，不用 scale） ---------- */

    function syncArt() {
      if (!map || !boardWrap) return;
      const [vx, vy, vw, vh] = VB();
      const tl = map.latLngToContainerPoint(ll(vx, vy));
      const br = map.latLngToContainerPoint(ll(vx + vw, vy + vh));
      for (const w of [boardWrap, overlayWrap]) {
        w.style.transform = 'translate(' + tl.x + 'px,' + tl.y + 'px)';
        w.style.width = (br.x - tl.x) + 'px';
        w.style.height = (br.y - tl.y) + 'px';
      }
    }

    /* ---------- 拼图元素识别 ---------- */

    function badgeLineOf(g) {
      for (const t of g.querySelectorAll('text')) {
        const s = t.textContent.trim();
        if (/^\d+$/.test(s)) return s + '号线';
        if (s === 'APM') return 'APM线';
        if (s === '广佛线') return '广佛线';
      }
      return null;
    }

    function collectPieces(opts) {
      // 站名文字（拼图块 = 中文名；英文是底图注记不参与）
      nameEls.clear();
      const grp = svg.querySelector('#站名标注');
      if (grp) {
        for (const t of grp.querySelectorAll('text')) {
          const nm = t.textContent;
          if (!nm || /^[\x00-\x7F]*$/.test(nm)) continue;
          if (!nameEls.has(nm)) nameEls.set(nm, []);
          nameEls.get(nm).push(t);
        }
      }
      // 徽标（线名 -> 组列表；一线多枚终点徽标）
      badgeEls.clear();
      for (const g of svg.querySelectorAll('[data-badge="header"]')) {
        const line = badgeLineOf(g);
        if (!line) continue;
        if (!badgeEls.has(line)) badgeEls.set(line, []);
        badgeEls.get(line).push(g);
      }
    }

    function hidePieces(opts) {
      const hide = els => { for (const el of els) el.style.visibility = 'hidden'; };
      const wantName = mode === 'name' || mode === 'both';
      const wantBadge = mode === 'badge' || mode === 'both';
      const wantChip = mode === 'code';
      if (wantName) {
        for (const [nm, els] of nameEls) {
          if (opts.placedNames && opts.placedNames.has(nm)) continue;
          // 单线模式：非本线站名保留为淡化背景（旧玩法口径），本线站名才是谜面
          if (opts.scope && !(QD().stations[nm] || { lines: [] }).lines.includes(opts.scope)) continue;
          hide(els);
        }
      }
      if (wantBadge) {
        for (const [line, els] of badgeEls) {
          if (opts.placedBadges && opts.placedBadges.has(line)) continue;
          hide(els);
          makeBadgeSlot(line, els[0]);
        }
      }
      if (wantChip) {
        for (const c of QD().chips) {
          const key = c.nm + '|' + c.line;
          if (opts.placedChips && opts.placedChips.has(key)) continue;
          // 单线模式：非本线编号牌保留为淡化背景（与站名/徽标同口径），本线牌才是谜面
          if (opts.scope && c.line !== opts.scope) continue;
          const cluster = chipClusters.get(key);
          if (cluster) hide(cluster);   // 圆圈板无 DOM 簇：只建槽位，放置时注入
          makeChipSlot(c);
        }
      }
    }

    /* ---------- 槽位（徽标/编号牌的原位轮廓，百分比定位随底图缩放） ---------- */

    function slotDiv(x, y, w, h, cls) {
      const [vx, vy, vw, vh] = VB();
      const el = document.createElement('div');
      el.className = 'mb-slot' + (cls ? ' ' + cls : '');
      el.style.left = ((x - vx) / vw * 100) + '%';
      el.style.top = ((y - vy) / vh * 100) + '%';
      el.style.width = (w / vw * 100) + '%';
      el.style.height = (h / vh * 100) + '%';
      overlayWrap.appendChild(el);
      return el;
    }

    function makeBadgeSlot(line, g) {
      const tr = (g.getAttribute('transform') || '')
        .match(/translate\(([-\d.]+) ([-\d.]+)\)\s*scale\(([\d.]+)\)/);
      const rect = g.querySelector('rect');
      if (!tr || !rect) return;
      const x = parseFloat(tr[1]), y = parseFloat(tr[2]), s = parseFloat(tr[3]);
      const w = parseFloat(rect.getAttribute('width')) * s;
      const h = parseFloat(rect.getAttribute('height')) * s;
      const line0 = QD().lines.find(l => l.name === line);
      const el = slotDiv(x, y, w, h);
      if (line0) el.style.setProperty('--c', line0.color);
      const s2 = { el, kind: 'badge', value: line };
      slotEls.set(line, s2);
      wireSlot(s2);
    }

    function makeChipSlot(c) {
      const line0 = QD().lines.find(l => l.name === c.line);
      const el = slotDiv(c.x, c.y, c.w, c.h, 'mb-slot-chip');
      if (line0) el.style.setProperty('--c', line0.color);
      const s2 = { el, kind: 'chip', value: c.nm + '|' + c.line };
      slotEls.set(s2.value, s2);
      wireSlot(s2);
    }

    function wireSlot(s2) {
      s2.el.addEventListener('mouseenter', () => setSnap(s2.el));
      s2.el.addEventListener('mouseleave', () => setSnap(null));
      if (!lastOpts || !lastOpts.interactive) return;
      const fire = payload => (s2.kind === 'badge' ? badgeCb : chipCb)(s2.kind, s2.value, payload);
      s2.el.addEventListener('click', () => fire());
      s2.el.addEventListener('dragenter', e => e.preventDefault());
      s2.el.addEventListener('dragover', e => { e.preventDefault(); s2.el.classList.add('drop-hover'); });
      s2.el.addEventListener('dragleave', () => s2.el.classList.remove('drop-hover'));
      s2.el.addEventListener('drop', e => {
        e.preventDefault();
        e.stopPropagation();
        s2.el.classList.remove('drop-hover');
        fire(e.dataTransfer.getData('text/plain'));
      });
    }

    /* ---------- 站点热区（站名模式投放目标，屏幕恒定半径） ---------- */

    function buildHotspots(opts) {
      if (mode !== 'name' && mode !== 'both') return;
      for (const [nm, st] of Object.entries(QD().stations)) {
        // 单线 scope: 他线站=淡化背景, 不设热区不响应(点/拖全屏蔽, 2026-10-27 用户令;
        // 旧口径"他线站可作错误目标−10"废止)
        if (opts.scope && !st.lines.includes(opts.scope)) continue;
        if (opts.placedNames && opts.placedNames.has(nm)) continue;
        const mk = L.circleMarker(ll(st.x, st.y), {
          radius: 20, stroke: false, fill: true, fillColor: '#2f7fd1', fillOpacity: 0,
          className: 'mst mst-hot'
        }).addTo(map);
        mk.on('mouseover', () => setSnap(mk));
        mk.on('mouseout', () => setSnap(null));
        if (opts.interactive) {
          const fire = payload => stationCb && stationCb('name', nm, payload);
          mk.on('click', () => fire());
          wireDnD(mk, fire);
        }
        stationHot.set(nm, mk);
      }
    }

    /* ---------- 就近判定：容器级拖放磁吸 + 点击兜底（≤SNAP_PX） ---------- */

    // mx/my 为地图容器内坐标（拖放从 event.clientX/Y 减容器 rect、点击用 Leaflet containerPoint）
    function nearestTarget(mx, my, maxPx) {
      let best = null, bd = maxPx;
      const all = [];
      for (const [nm, st] of Object.entries(QD().stations)) {
        if (stationHot.has(nm)) all.push({ kind: 'name', value: nm, station: st });
      }
      for (const [, s2] of slotEls) all.push({ kind: s2.kind, value: s2.value, slot: s2 });
      const crect = map.getContainer().getBoundingClientRect();
      for (const t of all) {
        let p;
        if (t.kind === 'name') p = px(t.station.x, t.station.y);
        else {
          const r = t.slot.el.getBoundingClientRect();
          if (!r.width) continue;
          p = { x: r.left + r.width / 2 - crect.left, y: r.top + r.height / 2 - crect.top };
        }
        const d = Math.hypot(p.x - mx, p.y - my);
        if (d < bd) {
          bd = d;
          best = { kind: t.kind, value: t.value, ref: t.kind === 'name' ? stationHot.get(t.value) : t.slot.el };
        }
      }
      return best;
    }

    function setSnap(ref) {
      if (snapRef && snapRef !== ref) {
        if (snapRef.classList) snapRef.classList.remove('snap', 'drop-hover');
        else if (snapRef.setStyle) snapRef.setStyle({ fillColor: '#2f7fd1', fillOpacity: 0 });
      }
      snapRef = ref || null;
      if (!ref) return;
      if (ref.classList) ref.classList.add('snap');
      else ref.setStyle({ fillColor: '#4a9eff', fillOpacity: 0.2 });
    }

    function wireContainerDnD(opts) {
      if (!opts.interactive) return;
      const c = map.getContainer();
      c.addEventListener('dragover', e => {
        const rect = c.getBoundingClientRect();
        const t = nearestTarget(e.clientX - rect.left, e.clientY - rect.top, SNAP_PX);
        // 圈亮(≤SNAP_PX)才取消 dragover 默认: 取消=浏览器允放; 不取消=判 no-drop
        // (光标🚫、松手不派发 drop)——圈亮↔可放双向一致(2026-10-27 用户令)
        if (t) e.preventDefault();
        setSnap(t ? t.ref : null);
      });
      c.addEventListener('drop', e => {
        e.preventDefault();
        const payload = e.dataTransfer.getData('text/plain') || undefined;
        const rect = c.getBoundingClientRect();
        const t = nearestTarget(e.clientX - rect.left, e.clientY - rect.top, SNAP_PX);
        if (!t) return;
        (t.kind === 'name' ? stationCb : t.kind === 'badge' ? badgeCb : chipCb)(t.kind, t.value, payload);
      });
      // 点击就近兜底：此前点击只认槽位本体/13px 热区，站名文字、牌位旁边点上去全部落空。
      // 精确命中槽位/热区时元素自身处理已 fire（且槽位置后即移除），这里只接"点在旁边"的近失。
      map.on('click', e => {
        const oe = e.originalEvent;
        const t0 = oe && oe.target;
        // 双击是缩放，不参与判定；命中交互元素/控件/角标时各自的链路已处理
        if (t0 && t0.closest && t0.closest('.mb-slot, .leaflet-interactive, .leaflet-control, .map-caption')) return;
        if ((oe && oe.detail || 0) > 1) return;
        const p = e.containerPoint;
        const t = nearestTarget(p.x, p.y, SNAP_PX);
        if (!t) return;
        (t.kind === 'name' ? stationCb : t.kind === 'badge' ? badgeCb : chipCb)(t.kind, t.value);
      });
    }

    function wireDnD(mk, fire) {
      const tryWire = () => {
        const el = mk.getElement && mk.getElement();
        if (!el || el.__dnd) return;
        el.__dnd = true;
        el.classList.add('dnd-target');
        el.addEventListener('dragenter', e => e.preventDefault());
        el.addEventListener('dragover', e => { e.preventDefault(); el.classList.add('drop-hover'); });
        el.addEventListener('dragleave', () => el.classList.remove('drop-hover'));
        el.addEventListener('drop', e => {
          e.preventDefault();
          e.stopPropagation();   // 槽本体已处理，别再触发容器就近吸附
          el.classList.remove('drop-hover');
          fire(e.dataTransfer.getData('text/plain'));
        });
      };
      tryWire();
      setTimeout(tryWire, 200);
    }

    /* ---------- 单线模式淡化（走廊按线色，其余按归属） ---------- */

    // 走廊色比较：style.stroke 在 Chromium 会序列化成 rgb() 形式，两种都归一到 hex
    function strokeHex(el) {
      let s = (el.style.stroke || '').trim().toLowerCase();
      let m = s.match(/^#([0-9a-f]{6})$/);
      if (m) return m[1];
      m = s.match(/^rgb\((\d+),\s*(\d+),\s*(\d+)\)$/);
      if (m) return m.slice(1).map(n => (+n).toString(16).padStart(2, '0')).join('');
      return null;
    }

    function applyScope(scope) {
      for (const el of dimRefs) { el.style.opacity = ''; }
      dimRefs = [];
      if (!scope) return;
      const line = QD().lines.find(l => l.name === scope);
      if (!line) return;
      const color = (line.color || '').replace('#', '').toLowerCase();
      const inScope = nm => {
        const st = QD().stations[nm];
        return st && st.lines.includes(scope);
      };
      for (const el of svg.querySelectorAll('#走廊 line')) {
        const cs = el.getAttribute('data-case');   // 环线黑描边: 随所属线淡化(描边色≠线色)
        if (cs) {
          if (cs !== scope) dim(el, 0.12);
          continue;
        }
        if (strokeHex(el) !== color) dim(el, 0.12);
      }
      for (const el of svg.querySelectorAll('#站圆 circle, #换乘标记 [data-nm]')) {
        const nm = el.getAttribute && el.getAttribute('data-nm');
        if (nm && !inScope(nm)) dim(el, 0.22);
      }
      for (const el of svg.querySelectorAll('#站名标注 text')) {
        const nm = el.textContent;
        if (nm && !inScope(nm)) dim(el, 0.25);
      }
      for (const g of svg.querySelectorAll('[data-badge="header"]')) {
        if (badgeLineOf(g) !== scope) dim(g, 0.18);
      }
      // 编号牌背景淡化（所有模式一致）：单线里非本线牌与圈环淡化为背景——
      // 编号模式本线牌是谜面被收起，他线牌留在原位作参照（2026-10-26 用户令：
      // 单线展示时本线数字亮、他线数字灰，不得全图收空）
      if (svg.querySelector('#编号牌')) {
        for (const [key, cluster] of chipClusters) {
          if (key.split('|')[1] !== scope) for (const el of cluster) dim(el, 0.25);
        }
        for (const ring of svg.querySelectorAll('#编号牌 rect[data-ring]')) {
          const nm = ring.getAttribute('data-ring');
          if (nm && !inScope(nm)) dim(ring, 0.3);
        }
      }
    }

    function dim(el, op) {
      el.style.opacity = String(op);
      dimRefs.push(el);
    }

    /* ---------- 渲染主流程 ---------- */

    function render(opts) {
      lastOpts = opts;
      mode = opts.mode || 'name';
      const form = opts.form || 'circle';
      const seq = ++loadSeq;
      if (map) { map.remove(); map = null; }
      for (const w of [boardWrap, overlayWrap]) if (w && w.parentNode) w.parentNode.removeChild(w);
      boardWrap = overlayWrap = svg = null;
      stationHot.clear(); slotEls.clear(); nameEls.clear(); badgeEls.clear();
      chipClusters = new Map(); injectedChips.clear(); dimRefs = []; snapRef = null;

      container.classList.add('official-canvas');
      // 先清再建：地图容器节点即 container 本体（与 metro-map 同模式）
      while (container.firstChild) container.removeChild(container.firstChild);
      const cap = document.createElement('div');
      cap.className = 'map-caption';
      // 牌配对版本戳（QD().gen = quiz 数据生成日）：核对窗口里跑的是哪版配对数据
      const gen = QD().gen ? ' · 牌配对 v' + QD().gen : '';
      cap.textContent = mode === 'answer'
        ? '答案图 · 整理版广州地铁线网（2026 · 官方编号）' + gen
        : '底图：整理版广州地铁线网图 · 官方编号牌' + gen;
      container.appendChild(cap);

      map = L.map(container, {
        crs: L.CRS.Simple, zoomControl: true, zoomSnap: 0.25, zoomDelta: 0.5,
        minZoom: -5, maxZoom: 3, zoomAnimation: false
      });
      const [vx, vy, vw, vh] = VB();
      map.setView([-(vy + vh / 2), vx + vw / 2], -2);

      boardWrap = document.createElement('div');
      boardWrap.className = 'mb-art';
      boardWrap.style.cssText = 'position:absolute;left:0;top:0;transform-origin:0 0;pointer-events:none;overflow:hidden;';
      overlayWrap = document.createElement('div');
      overlayWrap.className = 'mb-overlay';
      overlayWrap.style.cssText = 'position:absolute;left:0;top:0;transform-origin:0 0;pointer-events:none;';
      // 底图在 Leaflet 图层之下、槽位层在其上（都不进 pane——pane 的 scale 变换会裁大 SVG）
      map.getContainer().insertBefore(boardWrap, map.getPane('mapPane'));
      container.appendChild(overlayWrap);
      map.on('move zoom end resize', syncArt);

      fetchBoard(mode, form).then(loaded => {
        if (seq !== loadSeq) return;
        boardWrap.appendChild(loaded.holder);
        svg = loaded.svg;
        // 编号牌 DOM 聚类按板上实际内容判定（胶囊形式才有编号牌组；圆圈板走数据注入）
        if (svg.querySelector('#编号牌')) {
          chipClusters = bindChipClusters(svg, QD().chips);
        }
        collectPieces(opts);
        hidePieces(opts);
        buildHotspots(opts);
        applyScope(opts.scope);
        syncArt();
        wireContainerDnD(opts);
        frame(opts.scope);
      }).catch(err => {
        if (seq !== loadSeq) return;
        container.innerHTML = '<div class="mb-error">棋盘加载失败: ' + err.message + '</div>';
      });
    }

    /* ---------- 游戏增量更新 ---------- */

    function unhide(els) {
      for (const el of els) {
        el.style.visibility = '';
        el.classList.add('mb-placed-pop');
        setTimeout(() => el.classList.remove('mb-placed-pop'), 800);
      }
    }

    function placeName(nm) {
      if (lastOpts) lastOpts.placedNames.add(nm);
      const els = nameEls.get(nm);
      if (els) unhide(els);
      const mk = stationHot.get(nm);
      if (mk) { mk.remove(); stationHot.delete(nm); }
      const st = QD().stations[nm];
      if (st) popFx(nm, '+100');
    }

    function placeBadge(line) {
      if (lastOpts) lastOpts.placedBadges.add(line);
      const els = badgeEls.get(line);
      if (els) unhide(els);
      const s2 = slotEls.get(line);
      if (s2) { s2.el.remove(); slotEls.delete(line); }
      if (els && els[0]) {
        const tr = (els[0].getAttribute('transform') || '')
          .match(/translate\(([-\d.]+) ([-\d.]+)\)/);
        if (tr) popFxAt(parseFloat(tr[1]) + 12, parseFloat(tr[2]) + 6, '+100');
      }
    }

    // 圆圈棋盘无编号牌 DOM：按配对数据携带的产品级内标记原位注入（嵌套 svg，viewBox=牌矩形，
    // 与 codes 板上的官方牌像素级同款）
    function injectHtmlChip(key, pop) {
      if (injectedChips.has(key)) return;
      const c = QD().chips.find(k => k.nm + '|' + k.line === key);
      if (!c || !c.d) return;
      const [vx, vy, vw, vh] = VB();
      const el = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      el.setAttribute('viewBox', c.x + ' ' + c.y + ' ' + c.w + ' ' + c.h);
      el.setAttribute('preserveAspectRatio', 'none');
      el.setAttribute('class', 'mb-chip-svg' + (pop ? ' mb-placed-pop' : ''));
      el.style.left = ((c.x - vx) / vw * 100) + '%';
      el.style.top = ((c.y - vy) / vh * 100) + '%';
      el.style.width = (c.w / vw * 100) + '%';
      el.style.height = (c.h / vh * 100) + '%';
      el.innerHTML = c.d;
      overlayWrap.appendChild(el);
      injectedChips.set(key, el);
    }

    function placeChip(key) {
      if (lastOpts) lastOpts.placedChips.add(key);
      const cluster = chipClusters.get(key);
      if (cluster) unhide(cluster);
      else injectHtmlChip(key, true);
      const s2 = slotEls.get(key);
      if (s2) { s2.el.remove(); slotEls.delete(key); }
      const c = QD().chips.find(k => k.nm + '|' + k.line === key);
      if (c) popFxAt(c.x + c.w / 2, c.y, '+100');
    }

    function popFxAt(bx, by, text) {
      if (!map) return;
      const p = px(bx, by);
      const fx = document.createElement('div');
      fx.className = 'pop-score';
      fx.textContent = text || '+100';
      fx.style.left = p.x + 'px';
      fx.style.top = (p.y - 14) + 'px';
      map.getContainer().appendChild(fx);
      setTimeout(() => fx.remove(), 950);
    }

    function popFx(nm, text) {
      const st = QD().stations[nm];
      if (st) popFxAt(st.x, st.y, text);
    }

    function wrongFeedback(kind, value) {
      let el = null, mk = null;
      if (kind === 'name') mk = stationHot.get(value);
      else { const s2 = slotEls.get(value); if (s2) el = s2.el; }
      if (el) {
        el.classList.remove('wrong');
        void el.getBoundingClientRect();
        el.classList.add('wrong');
        setTimeout(() => el.classList.remove('wrong'), 500);
      }
      if (mk) {
        mk.setStyle({ fillOpacity: 0.85, fillColor: '#f85149', stroke: true, color: '#f85149', weight: 1.5 });
        setTimeout(() => {
          if (stationHot.has(value)) mk.setStyle({ fillOpacity: 0, stroke: false });
        }, 500);
      }
    }

    function revealAll() {
      for (const els of nameEls.values()) for (const el of els) el.style.visibility = '';
      for (const els of badgeEls.values()) for (const el of els) el.style.visibility = '';
      for (const c of QD().chips) {
        const key = c.nm + '|' + c.line;
        const cluster = chipClusters.get(key);
        if (cluster) for (const el of cluster) el.style.visibility = '';
        else injectHtmlChip(key, false);
      }
      for (const [, mk] of stationHot) mk.remove();
      stationHot.clear();
      for (const [, s2] of slotEls) s2.el.remove();
      slotEls.clear();
    }

    /* ---------- 视口 ---------- */

    function frame(scope) {
      let pts;
      if (scope) {
        pts = Object.values(QD().stations).filter(st => st.lines.includes(scope))
          .map(st => ll(st.x, st.y));
      } else {
        const [vx, vy, vw, vh] = VB();
        pts = [ll(vx, vy), ll(vx + vw, vy + vh)];
      }
      const dockH = (document.getElementById('metro-dock') || {}).offsetHeight || 0;
      const opts = { paddingTopLeft: [24, 10], paddingBottomRight: [24, dockH ? dockH + 18 : 10], animate: false };
      const fit = () => { if (pts.length) map.fitBounds(L.latLngBounds(pts), opts); };
      fit();
      setTimeout(() => { map.invalidateSize(); fit(); syncArt(); }, 60);
    }

    function destroy() {
      loadSeq++;
      if (map) { map.remove(); map = null; }
      container.classList.remove('official-canvas');
      container.innerHTML = '';
    }

    Object.assign(view, {
      kind: 'official',
      render, frame, destroy,
      placeName, placeBadge, placeChip, wrongFeedback, revealAll, popFx,
      invalidate() { if (map) setTimeout(() => { map.invalidateSize(); syncArt(); }, 50); },
      setTiles() {},
      onStationClick(cb) { stationCb = cb; },
      onBadgeClick(cb) { badgeCb = cb; },
      onChipClick(cb) { chipCb = cb; },
      __internals: {
        get map() { return map; }, get svg() { return svg; },
        get hiddenCount() {
          let n = 0;
          for (const els of nameEls.values()) if (els[0] && els[0].style.visibility === 'hidden') n++;
          for (const els of badgeEls.values()) if (els[0] && els[0].style.visibility === 'hidden') n += els.length;
          for (const els of chipClusters.values()) if (els[0] && els[0].style.visibility === 'hidden') n += els.length;
          return n;
        },
        get slots() { return slotEls; }, get hotspots() { return stationHot; }
      }
    });
    return view;
  }

  return { create };
})();
