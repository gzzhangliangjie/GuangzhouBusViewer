// 地图渲染层：底图切换（高德 GCJ-02 / OSM WGS-84）、线路与站点绘制

const MapLayer = (() => {
  const GUANGZHOU = [23.1291, 113.2644];

  const tileDefs = {
    amap: {
      // 高德栅格瓦片，GCJ-02 坐标系（叠加 OSM 数据时需纠偏）
      // 子域名必须是 webrd01~webrd04（带前导零），无零形式不解析
      url: 'https://webrd{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
      options: { subdomains: ['01', '02', '03', '04'], maxZoom: 18, attribution: '© 高德地图' },
      needsGcj: true
    },
    osm: {
      url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      options: { maxZoom: 19, attribution: '© OpenStreetMap 贡献者' },
      needsGcj: false
    }
  };

  let map;
  let baseLayer;
  let currentTiles = 'amap';

  function init() {
    map = L.map('map', { zoomControl: true, preferCanvas: true }).setView(GUANGZHOU, 12);
    setTiles(currentTiles);
  }

  function setTiles(name) {
    if (!tileDefs[name]) return;
    currentTiles = name;
    if (baseLayer) map.removeLayer(baseLayer);
    const def = tileDefs[name];
    baseLayer = L.tileLayer(def.url, def.options).addTo(map);
    document.querySelectorAll('.tile-btn').forEach(btn =>
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

    const segs = variant.segments.map(seg => seg.map(([la, ln]) => project(la, ln)));
    if (segs.length) {
      L.polyline(segs, {
        color: '#101418', weight: 7, opacity: 0.55, lineCap: 'round'
      }).addTo(group);
      L.polyline(segs, {
        color: colour, weight: 3.5, opacity: 1, lineCap: 'round'
      }).addTo(group);
    }

    variant.stops.forEach((s, i) => {
      const p = project(s.lat, s.lng);
      const marker = L.circleMarker(p, {
        radius: 5, color: '#ffffff', weight: 1.5,
        fillColor: colour, fillOpacity: 1
      }).addTo(group);
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
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
  }

  function addGroup(group) { group.addTo(map); }
  function removeGroup(group) { map.removeLayer(group); }
  function flyTo(lat, lng, zoom) { map.flyTo(project(lat, lng), zoom == null ? 15 : zoom); }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  return { init, setTiles, needsGcj, drawVariant, addGroup, removeGroup, fitLayerGroup, flyTo };
})();
