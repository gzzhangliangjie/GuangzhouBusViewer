// 地铁拼图地图渲染器（双风格）：
//   真实地图   —— Leaflet + 高德/OSM 底图（GCJ-02 纠偏），与公交浏览同款视觉
//   纯线路图   —— L.CRS.Simple 平面坐标 + 数据自带 45° 折线示意坐标（sx/sy），白底官方风格
// 两种风格共享：站点/徽章/编号牌绘制、站名缩放分级 + 碰撞去重、游戏增量更新接口

const MetroMapView = (() => {
  const GUANGZHOU = [23.1291, 113.2644];

  // 真实地图风格：与公交 map-layer.js 保持一致
  const CASING = { color: '#101418', weight: 7, opacity: 0.55, lineCap: 'round', lineJoin: 'round' };
  const STROKE_W = 3.5;
  // 真实地图的灰化背景线（单线模式）
  const DIAG_GREY_STYLE = { color: '#d4dbe2', weight: 3, opacity: 1, lineCap: 'round', lineJoin: 'round' };

  /* ---------- Tim 原图内联矢量底图（完整还原：配色/徽章/底图/图例） ---------- */
  const SCH = (window.METRO_DATA && window.METRO_DATA.schematic) || { width: 2848.5, height: 2054.25 };
  // 不能放进 Leaflet pane（pane 的 scale 变换会让 GPU 按纹理上限裁切这个大 SVG）：
  // 直接挂地图容器首节点，手动同步 translate + 显式宽高（无 scale 变换 → 分块渲染，稳定）。
  function injectBoardArt(map) {
    const wrap = document.createElement('div');
    wrap.className = 'board-art text-free';
    wrap.style.cssText = 'position:absolute;left:0;top:0;transform-origin:0 0;pointer-events:none;overflow:hidden;';
    return fetch('assets/tim-gzfmetro.svg')
      .then(r => { if (!r.ok) throw new Error('board svg HTTP ' + r.status); return r.text(); })
      .then(txt => {
        const holder = document.createElement('div');
        holder.style.cssText = 'width:100%;height:100%;';
        holder.innerHTML = txt;
        const svgEl = holder.querySelector('svg');
        if (svgEl) {
          svgEl.removeAttribute('width'); svgEl.removeAttribute('height');
          svgEl.style.width = '100%'; svgEl.style.height = '100%';
        }
        wrap.appendChild(holder);
        map.getContainer().insertBefore(wrap, map.getPane('mapPane'));
        return wrap;
      });
  }

  // 把底图对齐到当前视野（只用 translate + 显式尺寸，规避 GPU 大层裁切）
  // 注意 CRS.Simple 的纬度向上为北：图面顶部 sy=0 → lat=0，底部 → lat=-height
  function syncBoardArt(map, wrap) {
    const tl = map.latLngToContainerPoint(L.latLng(0, 0));                          // 左上
    const br = map.latLngToContainerPoint(L.latLng(-SCH.height, SCH.width));        // 右下
    wrap.style.transform = `translate(${tl.x}px, ${tl.y}px)`;
    wrap.style.width = (br.x - tl.x) + 'px';
    wrap.style.height = (br.y - tl.y) + 'px';
  }

  function bindBoardArt(map, wrap) {
    const fn = () => syncBoardArt(map, wrap);
    map.on('move zoom end resize', fn);
    fn();
  }

  function create(container, opts = {}) {
    const simple = !!opts.simple;   // true = 纯线路图（Tim 棋盘）
    const view = {};
    let boardWrap = null;
    let map, overlay, currentTiles = 'amap';
    let stationMk = new Map(), badgeMk = new Map(), numMk = new Map();
    let scopeArtLines = [];                 // 选中线重描（scopeArt pane）
    let scopeDots = new Map();              // 选中站圆（scopeDot pane）: id -> {mk, placed}
    let lastOpts = null;
    let stationCb = null, badgeCb = null;

    /* ---------- 底图分层透明化：单线模式其他线路半透明 ---------- */
    // scopeKey 为 null 时全部恢复；注意 CRS GPU 蒙层雷区——这里只改 SVG 组的 opacity，
    // 不叠加半透明矩形蒙层
    function applyArtScope(opts) {
      if (!boardWrap) return;
      const linesLayer = boardWrap.querySelector('[id="线路"]');
      if (linesLayer) {
        const scopeKey = opts.scopeRef;
        for (const g of linesLayer.children) {
          if (g.tagName.toLowerCase() !== 'g') continue;
          const raw = g.getAttribute('id') || '';
          let dec = raw;
          for (let d = 0; d < 10; d++) dec = dec.replace(`_x3${d}_`, String(d));
          const norm = dec.replace(/(?:_\d+)+_?$/, '');   // '10_1_'→'10', '9_3_'→'9', 'APM_3_'→'APM'
          g.style.display = '';
          g.style.opacity = (scopeKey && norm !== scopeKey) ? '0.18' : '1';
        }
      }
      const dotsLayer = boardWrap.querySelector('[id="站点"]');
      if (dotsLayer) dotsLayer.style.opacity = opts.scopeRef ? '0.55' : '1';
      // 远期/虚线层同样淡化
      for (const lid of ['远期线路', '虚线']) {
        const g = boardWrap.querySelector(`[id="${lid}"]`);
        if (g) g.style.opacity = opts.scopeRef ? '0.12' : '1';
      }
    }

    /* ---------- 坐标与数据适配 ---------- */

    function project(lat, lon) {
      return Tiles.defs[currentTiles].needsGcj ? GCJ.wgs84ToGcj02(lat, lon) : [lat, lon];
    }
    // 站点 → 地图坐标（示意坐标 y 轴取反适配 CRS.Simple 的 [y, x]）
    function pointOf(s) {
      return simple ? [-s.sy, s.sx] : project(s.lat, s.lon);
    }
    function segmentsOf(l) {
      const segs = simple ? MetroData.schematicSegments(l) : MetroData.geoSegments(l);
      return segs.map(seg => seg.map(([a, b]) => (simple ? [-b, a] : [a, b])));
    }

    /* ---------- 底图 ---------- */

    function setTiles(name) {
      if (simple || !Tiles.defs[name]) return;
      currentTiles = name;
      if (map) {
        map.eachLayer(l => { if (l instanceof L.TileLayer) map.removeLayer(l); });
        Tiles.createLayer(name).addTo(map);
        if (lastOpts) render(lastOpts);  // 坐标系变化，全部重画
      }
      container.parentElement.querySelectorAll('.metro-tiles .tile-btn').forEach(btn =>
        btn.classList.toggle('active', btn.dataset.tiles === name));
    }

    /* ---------- 网络绘制 ---------- */

    function render(opts) {
      lastOpts = opts;
      if (!map) {
        if (simple) {
          container.classList.add('schematic-canvas');
          map = L.map(container, {
            crs: L.CRS.Simple, renderer: L.svg(),
            zoomControl: true, zoomSnap: 0.25, zoomDelta: 0.5,
            minZoom: -5, maxZoom: 3,
            zoomAnimation: false   // 负数缩放的瞬时切换更干净，且不依赖 rAF
          }).setView([-SCH.height / 2, SCH.width / 2], -1);
          // 非选线站名的底层 pane；选中元素分层（用户规定的次序）：
          // 未选线(底图) < 未选名(550) < 选中线(560) < 选中圆(570) < 选中名(580) < 编号牌(600)
          map.createPane('dimTooltip');
          map.getPane('dimTooltip').style.zIndex = 550;
          map.createPane('scopeArt');
          map.getPane('scopeArt').style.zIndex = 560;
          map.createPane('scopeDot');
          map.getPane('scopeDot').style.zIndex = 570;
          map.createPane('scopeLabel');
          map.getPane('scopeLabel').style.zIndex = 580;
          injectBoardArt(map)
            .then(w => { boardWrap = w; bindBoardArt(map, w); applyArtScope(opts); })
            .catch(() => {});
          const cap = document.createElement('div');
          cap.className = 'map-caption';
          cap.innerHTML = '底图 © Guangzhou-Foshan Metro Diagram by Tim Wu · CC BY-SA 4.0';
          container.appendChild(cap);
        } else {
          map = L.map(container, { zoomControl: true, renderer: L.svg() }).setView(GUANGZHOU, 11);
          Tiles.createLayer(currentTiles).addTo(map);
        }
        overlay = L.layerGroup().addTo(map);
        map.on('zoomend moveend', refreshLabels);
      } else {
        overlay.clearLayers();
      }
      for (const mk of badgeMk.values()) if (mk && mk.remove) mk.remove();
      badgeMk.clear();
      stationMk.clear(); numMk.clear();
      for (const pl of scopeArtLines) pl.remove();
      scopeArtLines = [];
      for (const d of scopeDots.values()) d.mk.remove();
      scopeDots.clear();

      const grey = ref => opts.scopeRef && ref !== opts.scopeRef;

      // 单线模式：底图其他线路半透明、站点层淡化；全网模式全部恢复
      if (simple) applyArtScope(opts);

      if (simple) {
        // 底图 = Tim 原图内联矢量（永久无文字）；单线模式用 applyArtScope 半透明化其余线。
        // 选中线在 scopeArt(560) 重描——必须压在未选线站名(dimTooltip 550)之上；
        // 重描会盖住底图其他线的圆圈，但选中线自己的圆在 scopeDot(570) 再画一层补回
        if (opts.scopeRef) {
          const B = window.METRO_DATA.board;
          const l = MetroData.line(opts.scopeRef);
          const spec = B && B.lines[opts.scopeRef];
          if (l && spec) {
            for (const poly of spec.polys) {
              const pts = poly.map(([x, y]) => [-y, x]);
              if (pts.length >= 2) {
                scopeArtLines.push(L.polyline(pts, {
                  pane: 'scopeArt', color: spec.color || l.color,
                  weight: 7, opacity: 1, lineCap: 'round', lineJoin: 'round', interactive: false
                }).addTo(map));
              }
            }
          }
        }
      } else {
        for (const l of MetroData.allLines()) {
          const isGrey = grey(l.ref);
          for (const seg of segmentsOf(l)) {
            if (seg.length < 2) continue;
            if (isGrey) {
              L.polyline(seg, DIAG_GREY_STYLE).addTo(overlay);
            } else {
              L.polyline(seg, CASING).addTo(overlay);
              L.polyline(seg, { color: l.color, weight: STROKE_W, opacity: 1, lineCap: 'round', lineJoin: 'round' }).addTo(overlay);
            }
          }
        }
      }

      if (opts.showBadges !== 'none') {
        for (const l of MetroData.allLines()) {
          if (grey(l.ref)) continue;
          drawBadge(l, opts);
        }
      }

      // 单线模式：全部站点画热区（未选线站点也可作为错误目标），序号牌只画所选线
      for (const s of MetroData.allStations()) {
        drawStation(s, opts);
        if (!opts.scopeRef || s.lines.includes(opts.scopeRef)) drawNumberTag(s, opts);
      }

      frame(opts.scopeRef);
      wireContainerDnD(opts);
      refreshLabels();
    }

    function drawStation(s, opts) {
      const inter = s.lines.length > 1;
      const inScope = !opts.scopeRef || s.lines.includes(opts.scopeRef);
      const l0 = MetroData.line(s.lines.find(r => MetroData.line(r)));
      let mk;
      if (simple) {
        // 棋盘模式：站点圆由底图绘制，这里只放透明热区（点击/拖放目标）
        mk = L.circleMarker(pointOf(s), {
          radius: 12, stroke: false, fill: true,
          fillColor: '#2f7fd1', fillOpacity: 0,
          className: 'mst mst-hot'
        }).addTo(overlay);
        // 选中线的站圆在 scopeDot(570) 重画：保证在未选线站名(550)与选中线重描(560)之上
        if (opts.scopeRef && inScope) {
          const lc = (MetroData.line(opts.scopeRef) || {}).color || '#2f7fd1';
          const u = Math.pow(2, map.getZoom());
          const placed = opts.placedNames.has(s.id);
          const dot = L.circleMarker(pointOf(s), {
            pane: 'scopeDot', radius: (placed ? 6 : 4.5) * u, interactive: false,
            fillColor: placed ? '#2f7fd1' : '#ffffff', fillOpacity: 1,
            color: placed ? '#ffffff' : lc, weight: 2 * u,
            className: 'mst mst-scope'
          }).addTo(map);
          scopeDots.set(s.id, { mk: dot, placed });
        }
      } else {
        mk = L.circleMarker(pointOf(s), inter ? {
          // 换乘站：白芯黑环，突出枢纽（官方线网图样式）
          radius: 6.5, color: '#101418', weight: 2.5,
          fillColor: '#ffffff', fillOpacity: 1, className: 'mst'
        } : {
          radius: 4.5, color: '#ffffff', weight: 1.5,
          fillColor: inScope ? (l0 ? l0.color : '#4a9eff') : '#7a838d',
          fillOpacity: 1, className: 'mst'
        }).addTo(overlay);
        if (opts.placedNames.has(s.id)) mk.setStyle({ radius: (inter ? 6.5 : 4.5) + 1.5, weight: 3 });
      }

      if (opts.interactive) {
        const fire = () => stationCb && stationCb(s.id);
        mk.on('click', fire);
        wireDnD(mk, fire);
      }
      stationMk.set(s.id, mk);
    }

    function bindLabel(mk, s, dim) {
      // 纯线路图分层：未选线站名 → dimTooltip(550)；所选线站名 → scopeLabel(580)
      // 真实地图保持 tooltipPane（z 650）
      mk.bindTooltip(s.zh, {
        permanent: true, direction: 'right', offset: [8, 0],
        className: 'mlab' + (s.lines.length > 1 ? ' inter' : '') + (dim ? ' dim' : '') + (simple ? ' light' : ''),
        pane: simple ? (dim ? 'dimTooltip' : 'scopeLabel') : 'tooltipPane'
      });
    }

    // 选中线重描/站圆的尺寸按底图单位随缩放同步（底图 1 viewBox 单位 = 2^zoom px）
    function rescaleScopeArt() {
      if (!map || !simple) return;
      const u = Math.pow(2, map.getZoom());
      for (const pl of scopeArtLines) pl.setStyle({ weight: 7 * u });
      for (const { mk, placed } of scopeDots.values()) {
        mk.setStyle({ radius: (placed ? 6 : 4.5) * u, weight: 2 * u });
      }
    }

    const badgePosOrder = new Map();   // ref -> ['R','L','D','U'] 优先序
    const BADGE_DIST = 48;
    function cardinalXY(dir, dist) {
      switch (dir) {
        case 'R': return [dist, 0];
        case 'L': return [-dist, 0];
        case 'U': return [0, -dist];
        default:  return [0, dist];
      }
    }

    function drawBadge(l, opts) {
      const anchor = MetroData.badgeAnchorStation(l);
      if (!anchor) return;
      // 'filled'：线号直接可见（站名模式 / 答案图）；'slots'：待填的问号槽
      const placed = opts.showBadges === 'filled' || opts.placedBadges.has(l.ref);
      // 沿线路走出方向平移固定屏幕距离，避免盖住端点站圆点/编号牌
      const p = pointOf(anchor);
      const seq = (l.loop && l.stations.length > 2) ? l.stations : [...l.stations].reverse();
      const prev = MetroData.station(seq[1] || seq[0]);
      let ux = 0.7, uy = -0.7;   // 无参照站时默认右上方向
      if (prev && prev !== anchor) {
        const q = pointOf(prev);
        // 屏幕系方向 = 终点减邻近站；simple 模式 latLng 为 [-sy, sx]：
        // 屏幕 x = sx 差 = p[1]-q[1]，屏幕 y = sy 差 = (−p[0])−(−q[0]) = q[0]-p[0]
        // （旧实现 dy 用了 p[0]-q[0]，垂直翻转导致徽章常落在线路内侧/压线）
        const dx = simple ? (p[1] - q[1]) : (p[1] - q[1]) * Math.cos(anchor.lat * Math.PI / 180);
        const dy = simple ? (q[0] - p[0]) : -(p[0] - q[0]);
        const len = Math.hypot(dx, dy) || 1;   // Math.hypot 直接用全局，防局部遮蔽
        ux = dx / len; uy = dy / len;
      }
      // 四方位放置（用户规范）：横向走向的线优先左右、纵向优先上下，出线侧先试；
      // 与编号牌/站名冲突时按序换方位，全占则隐藏（resolveBadgeOverlaps 兜底）
      const horizontal = Math.abs(ux) >= Math.abs(uy);
      const R = ['R', 'L', 'D', 'U'], Dn = ['D', 'U', 'R', 'L'];
      let order = horizontal ? R.slice() : Dn.slice();
      // 出线侧优先：横向且向右 → R 在前；纵向且向下 → D 在前
      if (horizontal ? ux < 0 : uy < 0) { order = order.slice(); order[0] = order[0] === 'R' ? 'L' : (order[0] === 'D' ? 'U' : order[0]); order[1] = order[1] === 'L' ? 'R' : (order[1] === 'U' ? 'D' : order[1]); }
      const DIST = 48;
      badgePosOrder.set(l.ref, order);
      const first = cardinalXY(order[0], DIST);
      const off = `--tx:${Math.round(first[0])}px;--ty:${Math.round(first[1])}px`;
      // 官方样式：线路色胶囊 + 白字（1号线 / 广佛线 / APM线）
      const html = `<div class="mbadge${placed ? ' placed' : ''}"${placed ? ` style="--c:${l.color};${off}"` : ` style="${off}"`}>` +
        (placed ? l.zh : '？') + '</div>';
      const mk = L.marker(p, {
        icon: L.divIcon({ className: 'mbadge-wrap', html, iconSize: null }),
        keyboard: false, zIndexOffset: 500
      }).addTo(overlay);

      if (opts.interactive && !placed) {
        const fire = () => badgeCb && badgeCb(l.ref);
        mk.on('click', fire);
        wireDnD(mk, fire);
      }
      badgeMk.set(l.ref, mk);
    }

    // SVG 渲染器下 marker 有 DOM 元素，直接挂 HTML5 拖放事件
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
          e.stopPropagation();   // 已由牌本体处理，别再触发容器的就近吸附
          el.classList.remove('drop-hover');
          fire(e.dataTransfer.getData('text/plain'));
        });
      };
      tryWire();
      setTimeout(tryWire, 200);
    }

    // 容器级拖放兜底：牌热区(含扩边)外松手时，吸附到最近的可见编号牌（≤46px）
    // 解决"判定很小、拖了没效果"——拖到大概位置即可命中
    function wireContainerDnD(opts) {
      if (!opts.interactive || !map) return;
      const c = map.getContainer();
      if (c.__dndFallback) return;
      c.__dndFallback = true;
      c.addEventListener('dragover', e => e.preventDefault());
      c.addEventListener('drop', e => {
        e.preventDefault();
        if (!stationCb) return;
        const payload = e.dataTransfer.getData('text/plain') || undefined;
        const rect = c.getBoundingClientRect();
        const px = { x: e.clientX - rect.left, y: e.clientY - rect.top };
        let best = null, bd = 46;
        for (const [id, mk] of numMk) {
          const el = mk.getElement();
          if (!el || el.style.display === 'none' || !el.offsetParent) continue;
          const s = MetroData.station(id);
          if (!s || lastOpts && lastOpts.placedNames.has(id)) continue;
          const p = map.latLngToContainerPoint(pointOf(s));
          const d = Math.hypot(p.x - px.x, p.y - px.y);
          if (d < bd) { bd = d; best = id; }
        }
        if (best) stationCb(best, payload);
      });
    }

    /* ---------- 站点编号牌：「线号-序号」小标签（如 1-14） ---------- */

    function stationNumberTag(s, scopeRef) {
      // 单线模式下优先用所选线的序号，全网用首条（主）线
      // 换乘站显示全部线编号（用户要求：多条线路交汇的站把多条线路的编号都列出来）
      const parts = [];
      const refs = scopeRef
        ? [scopeRef, ...s.lines.filter(r => r !== scopeRef)]
        : s.lines;
      for (const ref of refs) {
        const l = MetroData.line(ref);
        if (!l) continue;
        const idx = l.stations.indexOf(s.id);
        if (idx < 0) continue;
        parts.push(MetroData.refLabel(ref) + '-' + String(idx + 1).padStart(2, '0'));
      }
      if (!parts.length) return null;
      return parts;
    }

    function drawNumberTag(s, opts) {
      const tag = stationNumberTag(s, opts.scopeRef);
      if (!tag) return;
      // 所选线编号牌层级高于非选线站名(tooltip-pane 650)：用 pane 提升
      const inScope = !opts.scopeRef || s.lines.includes(opts.scopeRef);
      // 已放置：牌原位变成站名（绿色完成样式），不再作为投放目标
      const placed = opts.placedNames.has(s.id);
      const mk = L.marker(pointOf(s), {
        interactive: opts.interactive && !placed,
        keyboard: false,
        zIndexOffset: inScope ? 1000 : 200,
        icon: L.divIcon({
          className: 'mnum-wrap' + (inScope && opts.scopeRef ? ' scope-num' : ''),
          html: `<span class="mnum${placed ? ' done' : ''}">${placed ? s.zh : (Array.isArray(tag) ? tag.join('<br>') : tag)}</span>`,
          iconSize: null  // 由内容撑开，锚点在左下
        })
      }).addTo(overlay);
      if (opts.interactive && !placed) {
        const fire = (payload) => stationCb && stationCb(s.id, payload);
        mk.on('click', () => fire());
        wireDnD(mk, fire);
      }
      numMk.set(s.id, mk);
    }

    /* ---------- 站名标签：缩放分级 + 碰撞去重 ---------- */
    // 编号牌（游戏线索）常显；站名按 已放置/换乘站 优先，
    // 低缩放只给高优先级，矩形碰撞放不下就不显示，放大后逐级补全。
    // 两种风格的缩放刻度不同：真实地图 z11~13，纯线路图 z-2~0（CRS.Simple）。

    function zoomGates(zoom) {
      // Tim 棋盘（2848×2054，fit≈-1.8）：编号牌常显，站名全景即显（碰撞去重控密度）
      return simple
        ? { num: -6, hi: -2.6, normal: -1.5 }
        : { num: 11, hi: 11, normal: 12.5 };
    }

    function refreshLabels() {
      if (!map || !lastOpts) return;
      rescaleScopeArt();
      const zoom = map.getZoom();
      const gates = zoomGates(zoom);
      // 单线模式提示站名更积极：上限放宽、门槛降低
      const MAX_LABELS = simple ? (lastOpts.scopeRef ? 170 : 110) : 60, MAX_NUMS = 140;

      // ① 编号牌（游戏线索，常显）：所选线全部显示（无碰撞剔除），其余按碰撞去重
      const numRects = [];
      const keepNums = new Set();
      if (zoom >= gates.num) {
        const nums = [];
        for (const s of MetroData.allStations()) {
          if (lastOpts.scopeRef && !s.lines.includes(lastOpts.scopeRef)) continue;
          if (!numMk.has(s.id)) continue;
          // 已放置的站：序号牌隐藏（站名标签接管该位置），不再作为投放目标
          if (lastOpts.placedNames.has(s.id)) continue;
          // 所选线的序号牌必显(不参与碰撞/上限)；全网模式换乘站优先
          const inScope = !lastOpts.scopeRef || s.lines.includes(lastOpts.scopeRef);
          nums.push({ s, prio: (inScope ? 0 : 10) + (s.lines.length > 1 ? 0 : 1), must: !!lastOpts.scopeRef && inScope });
        }
        nums.sort((a, b) => a.prio - b.prio);
        for (const { s, must } of nums) {
          if (!must && keepNums.size >= MAX_NUMS) break;
          const p = map.latLngToContainerPoint(pointOf(s));
          const tagTexts = Array.isArray(stationNumberTag(s, lastOpts.scopeRef)) ? stationNumberTag(s, lastOpts.scopeRef) : [stationNumberTag(s, lastOpts.scopeRef) || ''];
          const w = Math.max(...tagTexts.map(t => t.length)) * 6.5 + 8, h = tagTexts.length * 13;
          const x = p.x - w - 7, y = p.y + 3;
          if (!must) {
            const clash = numRects.some(o => x < o.x + o.w && x + w > o.x && y < o.y + o.h && y + h > o.y);
            if (clash) continue;
          }
          numRects.push({ x, y, w, h });
          keepNums.add(s.id);
        }
      }
      for (const [id, mk] of numMk) {
        const el = mk.getElement();
        if (!el) continue;
        // 已放置的牌已原位变成站名，保持显示；其余按碰撞结果
        el.style.display = (keepNums.has(id) || lastOpts.placedNames.has(id)) ? '' : 'none';
      }

      // ② 站名标签：已放置/换乘优先，缩放分级 + 碰撞（含编号牌占位）
      // 单线模式：未选线站名正常显示（提示背景），所选线站名仅放置后/线号模式显示（谜题）
      // 站名永不隐藏（用户要求）：不做碰撞剔除、无数量上限；仍遵守游戏规则
      // （单线模式：所选线未放置的站名是谜题，保持隐藏）与最低缩放门槛
      const keep = new Set();
      const minZoom = simple ? -6 : gates.hi;
      for (const s of MetroData.allStations()) {
        const placed = lastOpts.placedNames.has(s.id);
        if (simple && placed) continue;          // 已放置：编号牌原位显示站名
        const inScope = !lastOpts.scopeRef || s.lines.includes(lastOpts.scopeRef);
        let nameVisible = lastOpts.scopeRef
          ? (placed || (lastOpts.showStationNames && inScope) || !inScope)
          : (lastOpts.showStationNames || placed);
        if (!nameVisible) continue;
        if (zoom < minZoom) continue;
        keep.add(s.id);
      }

      for (const [id, mk] of stationMk) {
        const has = !!mk.getTooltip();
        // 单线模式：非所选线站名用 dim 类降低存在感；已有 tooltip 但类需更新时重绑
        const s = MetroData.station(id);
        const dim = !!(lastOpts.scopeRef && !s.lines.includes(lastOpts.scopeRef));
        if (keep.has(id) && !has) bindLabel(mk, s, dim);
        else if (keep.has(id) && has) {
          const cls = mk.getTooltip().getContent() && mk.getTooltip().getElement() ? mk.getTooltip().getElement().className : '';
          if (dim !== cls.includes('dim')) { mk.unbindTooltip(); bindLabel(mk, s, dim); }
        }
        else if (!keep.has(id) && has) mk.unbindTooltip();
      }

      resolveBadgeOverlaps();
    }

    /* ---------- 徽章×编号牌碰撞解析（渲染后 DOM 检测 + 花瓣分布兜底） ---------- */
    // 障碍物 = 可见编号牌 + 站名标签 + 已落位的其他徽章；
    // 徽章按线序逐个处理：先试出线方向，撞则按 30° 步进扫描整圈找空位（半径渐进加大）。
    function resolveBadgeOverlaps() {
      if (!map) return;
      const obstacles = [];
      container.querySelectorAll('.mnum-wrap').forEach(el => {
        if (el.style.display === 'none') return;
        const r = el.getBoundingClientRect();
        if (r.width > 0) obstacles.push(r);
      });
      container.querySelectorAll('.mlab').forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.width > 0) obstacles.push(r);
      });
      if (!obstacles.length) return;

      const pad = 3;
      const overlapsPad = (r) => obstacles.some(t =>
        r.left - pad < t.right && r.right + pad > t.left && r.top - pad < t.bottom && r.bottom + pad > t.top);

      for (const [ref, mk] of badgeMk) {
        const el = mk.getElement && mk.getElement();
        const badge = el && el.querySelector('.mbadge');
        if (!badge) continue;
        if (!overlapsPad(badge.getBoundingClientRect())) {
          badge.style.visibility = '';
          obstacles.push(badge.getBoundingClientRect());
          continue;
        }
        // 四方位按优先序找空位（横向线左右优先/纵向上下优先）；
        // 全占则拉远一档再试（含四个斜角）；仍无空位选重叠面积最小的位置——线路信息永不隐藏
        const order = badgePosOrder.get(ref) || ['R', 'L', 'D', 'U'];
        badge.style.visibility = '';
        let done = false;
        for (const dist of [BADGE_DIST, BADGE_DIST + 22]) {
          for (const dir of order) {
            const [x, y] = cardinalXY(dir, dist);
            badge.style.setProperty('--tx', x + 'px');
            badge.style.setProperty('--ty', y + 'px');
            if (!overlapsPad(badge.getBoundingClientRect())) { done = true; break; }
          }
          if (done) break;
        }
        if (!done) {
          const area = (r, t) => Math.max(0, Math.min(r.right, t.right) - Math.max(r.left, t.left)) *
                                 Math.max(0, Math.min(r.bottom, t.bottom) - Math.max(r.top, t.top));
          let best = null;
          for (const dist of [BADGE_DIST, BADGE_DIST + 22]) {
            for (const dir of order) {
              const [x, y] = cardinalXY(dir, dist);
              badge.style.setProperty('--tx', x + 'px');
              badge.style.setProperty('--ty', y + 'px');
              const r = badge.getBoundingClientRect();
              const ov = obstacles.reduce((s2, t) => s2 + area(r, t), 0);
              if (!best || ov < best.ov) best = { ov, x, y };
            }
          }
          badge.style.setProperty('--tx', best.x + 'px');
          badge.style.setProperty('--ty', best.y + 'px');
        }
        obstacles.push(badge.getBoundingClientRect());
      }
    }

    /* ---------- 游戏过程中的增量更新 ---------- */

    /* ---------- 得分反馈：+100 飘字 + 站圆脉冲（纯线路图） ---------- */
    function popFx(id, text) {
      if (!map || !simple) return;
      const s = MetroData.station(id);
      if (!s) return;
      const p = map.latLngToContainerPoint(pointOf(s));
      const fx = document.createElement('div');
      fx.className = 'pop-score';
      fx.textContent = text || '+100';
      fx.style.left = p.x + 'px';
      fx.style.top = (p.y - 14) + 'px';
      map.getContainer().appendChild(fx);
      setTimeout(() => fx.remove(), 950);
      const d = scopeDots.get(id);
      if (d && d.mk.getElement) {
        const el = d.mk.getElement();
        if (el) {
          el.classList.remove('dot-pop');
          el.getBoundingClientRect();   // 重排以重启动画
          el.classList.add('dot-pop');
          setTimeout(() => el.classList.remove('dot-pop'), 700);
        }
      }
    }

    function placeName(id) {
      if (lastOpts) lastOpts.placedNames.add(id);
      const mk = stationMk.get(id);
      if (!mk) return;
      if (simple) {
        // 高亮画在 scopeDot 的站圆上（顶层），热区保持透明
        const d = scopeDots.get(id);
        if (d) {
          d.placed = true;
          const u = Math.pow(2, map.getZoom());
          d.mk.setStyle({ fillColor: '#2f7fd1', fillOpacity: 1, radius: 6 * u, color: '#ffffff', weight: 2 * u });
        }
        // 原地换牌：编号牌内容替换为站名（绿色完成样式），位置不动
        const tagMk = numMk.get(id);
        const el = tagMk && tagMk.getElement && tagMk.getElement();
        if (el) {
          const span = el.querySelector('.mnum');
          if (span) {
            span.textContent = MetroData.station(id).zh;
            span.classList.add('done');
          }
          el.classList.remove('dnd-target');
          el.style.display = '';
        }
      } else {
        mk.setStyle({ radius: mk.options.radius + 1.5, weight: 3 });
      }
      refreshLabels();
    }
    function placeBadge(ref) {
      if (lastOpts) lastOpts.placedBadges.add(ref);
      const l = MetroData.line(ref);
      const mk = badgeMk.get(ref);
      const el = mk && mk.getElement && mk.getElement();
      const b = el && el.querySelector('.mbadge');
      if (b) {
        b.classList.add('placed');
        if (l) b.style.setProperty('--c', l.color);
        b.textContent = l ? l.zh : ref;
      }
    }
    function wrongFeedback(target) {
      const mk = stationMk.get(target) || badgeMk.get(target);
      if (!mk) return;
      if (mk.setStyle) {
        if (simple && stationMk.has(target)) {
          // 透明热区闪红后还原为不可见
          mk.setStyle({ fillOpacity: 0.85, fillColor: '#f85149', stroke: true, color: '#f85149', weight: 1.5 });
          setTimeout(() => {
            const placed = lastOpts && lastOpts.placedNames.has(target);
            if (!placed) mk.setStyle({ fillOpacity: 0, stroke: false });
          }, 500);
        } else {
          const orig = { color: mk.options.color, fillColor: mk.options.fillColor };
          mk.setStyle({ color: '#f85149', fillColor: '#f85149' });
          setTimeout(() => mk.setStyle(orig), 500);
        }
      }
      const el = mk.getElement && mk.getElement();
      if (el) {
        el.classList.remove('wrong');
        void el.getBoundingClientRect();
        el.classList.add('wrong');
        setTimeout(() => el.classList.remove('wrong'), 500);
      }
    }
    function revealAll() {
      if (lastOpts) {
        for (const id of MetroData.allStations().map(s => s.id)) lastOpts.placedNames.add(id);
      }
      refreshLabels();
      for (const [ref, mk] of badgeMk) {
        const el = mk.getElement && mk.getElement();
        const b = el && el.querySelector('.mbadge');
        const l = MetroData.line(ref);
        if (b && l) {
          b.classList.add('placed');
          b.style.setProperty('--c', l.color);
          b.textContent = l.zh;
        }
      }
    }

    /* ---------- 视口 ---------- */

    function frame(scopeRef) {
      let pts;
      if (scopeRef) {
        const l = MetroData.line(scopeRef);
        pts = l ? MetroData.lineStationIds(l)
          .map(id => MetroData.station(id))
          .filter(Boolean)
          .map(pointOf) : [];
      } else {
        pts = MetroData.allStations().map(pointOf);
      }
      // 真实地图：单线放大聚焦（上限 13），全网概览（上限 11）；纯线路图自然取景
      // 纯线路图要给底部名牌池 dock 让位（西塱 1-01 曾被面板盖住无法拖放）
      const dockH = (document.getElementById('metro-dock') || {}).offsetHeight || 0;
      const opts = simple
        ? { paddingTopLeft: [24, 10], paddingBottomRight: [24, dockH ? dockH + 18 : 10] }
        : { padding: [50, 50], maxZoom: scopeRef ? 13 : 11 };
      // animate:false —— 聚焦不依赖动画帧，窗口遮挡/后台时也能正确落位
      const fit = () => { if (pts.length) map.fitBounds(L.latLngBounds(pts), { ...opts, animate: false }); };
      fit();
      // 容器刚显示时尺寸可能仍为 0，校正后再聚焦一次
      setTimeout(() => { map.invalidateSize(); fit(); }, 60);
    }

    function destroy() {
      if (map) { map.remove(); map = null; }
      if (simple) {
        container.classList.remove('schematic-canvas');
        container.querySelector('.map-caption')?.remove();
      }
      for (const mk of badgeMk.values()) if (mk && mk.remove) mk.remove();
      badgeMk.clear();
      stationMk.clear(); numMk.clear();
    }

    Object.assign(view, {
      kind: simple ? 'schematic' : 'geo',
      render, placeName, placeBadge, wrongFeedback, revealAll, frame, destroy, setTiles, popFx,
      onStationClick(cb) { stationCb = cb; },
      onBadgeClick(cb) { badgeCb = cb; },
      invalidate() { if (map) setTimeout(() => { map.invalidateSize(); refreshLabels(); }, 50); },
      __internals: { get map() { return map; }, get stationMk() { return stationMk; }, get badgeMk() { return badgeMk; }, get numMk() { return numMk; }, get scopeDots() { return scopeDots; } }
    });
    return view;
  }

  /* ---------- 完整线网图查看器（内联矢量，全部图层可见，仅浏览） ---------- */

  function createImageViewer(container) {
    const map = L.map(container, {
      crs: L.CRS.Simple, zoomControl: true,
      zoomSnap: 0.25, zoomDelta: 0.5, minZoom: -6, maxZoom: 4,
      zoomAnimation: false
    });
    injectBoardArt(map).then(w => bindBoardArt(map, w)).catch(() => {});
    const bounds = [[-SCH.height, 0], [0, SCH.width]];
    map.fitBounds(bounds, { animate: false });
    const t = setTimeout(() => { map.invalidateSize(); map.fitBounds(bounds, { animate: false }); }, 60);
    return {
      kind: 'image',
      destroy() { clearTimeout(t); map.remove(); },
      invalidate() { setTimeout(() => map.invalidateSize(), 50); },
      setTiles() {}
    };
  }

  return { create, createImageViewer };
})();
