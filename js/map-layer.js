// 地图渲染层：底图切换（高德 GCJ-02 / OSM WGS-84）、线路与站点绘制

const MapLayer = (() => {
  const GUANGZHOU = [23.1291, 113.2644];
  const tileDefs = Tiles.defs;

  let map;
  let baseLayer;
  let currentTiles = 'amap';

  function init() {
    map = L.map('map', { zoomControl: true, preferCanvas: true }).setView(GUANGZHOU, 12);
    map.on('zoomend moveend', refreshStopLabels);
    setTiles(currentTiles);
  }

  function setTiles(name) {
    if (!tileDefs[name]) return;
    currentTiles = name;
    if (baseLayer) map.removeLayer(baseLayer);
    const def = tileDefs[name];
    baseLayer = Tiles.createLayer(name).addTo(map);
    document.querySelectorAll('#bus-view .tile-btn').forEach(btn =>
      btn.classList.toggle('active', btn.dataset.tiles === name));
  }

  /** 当前底图是否 GCJ-02：是则所有 OSM(WGS-84) 坐标需先转换 */
  function needsGcj() { return tileDefs[currentTiles].needsGcj; }

  function project(lat, lng) {
    return needsGcj() ? GCJ.wgs84ToGcj02(lat, lng) : [lat, lng];
  }

  /**
   * 绘制一条线路变体，返回 L.layerGroup。
   * variant: { segments, stops, ref, name, colour }
   */
  function drawVariant(variant, colour, stopsClickable) {
    const group = L.layerGroup();

    // 最终防线：任何路径漏进来的非法坐标（null/越界）都不能进图层——
    // 历史上 null 经度曾把视口 fitBounds 到经度 0 导致全白
    const okLL = (la, ln) => Number.isFinite(la) && Number.isFinite(ln) && la > 17 && la < 27 && ln > 111 && ln < 117;
    const segs = variant.segments
      .map(seg => (seg || []).filter(p => okLL(p[0], p[1])).map(([la, ln]) => project(la, ln)))
      .filter(seg => seg.length >= 2);
    if (segs.length) {
      L.polyline(segs, {
        color: '#101418', weight: 7, opacity: 0.55, lineCap: 'round'
      }).addTo(group);
      L.polyline(segs, {
        color: colour, weight: 3.5, opacity: 1, lineCap: 'round'
      }).addTo(group);
    }

    (variant.stops || []).filter(s => okLL(s.lat, s.lng)).forEach((s, i) => {
      const p = project(s.lat, s.lng);
      const marker = L.circleMarker(p, {
        radius: 5, color: '#ffffff', weight: 1.5,
        fillColor: colour, fillOpacity: 1
      }).addTo(group);
      marker.__stopName = s.name;
      marker.bindPopup(
        `<div class="popup-stop-name">${escapeHtml(s.name)}</div>` +
        `<div class="popup-stop-meta">${escapeHtml(variant.ref)} 路 · 第 ${i + 1} 站</div>`
      );
      if (stopsClickable) marker.on('click', () => {
        if (window.AppHooks && AppHooks.onStopClick) AppHooks.onStopClick(variant, i);
      });
    });

    return group;
  }

  function fitLayerGroup(group) {
    const bounds = L.latLngBounds([]);
    group.eachLayer(l => {
      if (l.getBounds) bounds.extend(l.getBounds());
    });
    console.log('[fit]', bounds.isValid()
      ? [bounds.getSouth(), bounds.getWest(), bounds.getNorth(), bounds.getEast()].map(v => Number(v).toFixed(4)).join(',')
      : 'invalid');
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
  }

  function addGroup(group) {
    group.addTo(map);
    refreshStopLabels();
  }

  /* 站点名标签：z>=14 显示（参考地铁 mlab.light 效果），矩形碰撞放不下就不显示 */
  const LABEL_ZOOM = 14;
  function refreshStopLabels() {
    if (!map) return;
    const show = map.getZoom() >= LABEL_ZOOM;
    const rects = [];
    const taken = new Set();
    for (const layer of []) {}   // 占位防误删
    map.eachLayer(l => {
      if (!(l instanceof L.CircleMarker) || !l.__stopName || !l._map) return;
      if (!show) {
        if (l.getTooltip()) l.unbindTooltip();
        return;
      }
      if (l.getTooltip()) return;   // 已显示
      const p = map.latLngToContainerPoint(l.getLatLng());
      if (p.x < -80 || p.y < -30 || p.x > map.getSize().x + 80 || p.y > map.getSize().y + 30) return;
      const w = l.__stopName.length * 13 + 16, h = 20;
      const r = { x: p.x + 9, y: p.y - 10, w, h };
      const clash = rects.some(o => r.x < o.x + o.w && r.x + r.w > o.x && r.y < o.y + o.h && r.y + r.h > o.y);
      if (clash) return;
      rects.push(r);
      taken.add(l);
      l.bindTooltip(l.__stopName, {
        permanent: true, direction: 'right', offset: [8, 0],
        className: 'blab', opacity: 1
      }).openTooltip();
    });
  }
  function removeGroup(group) { map.removeLayer(group); }
  function flyTo(lat, lng, zoom) { map.flyTo(project(lat, lng), zoom == null ? 15 : zoom); }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  return { init, setTiles, needsGcj, drawVariant, addGroup, removeGroup, fitLayerGroup, flyTo };
})();
