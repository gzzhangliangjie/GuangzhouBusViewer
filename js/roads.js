// 广州市道路查看工具：按道路名查 OSM 路段并绘制
// 数据：Overpass way["highway"]["name"~关键词]（复用公交侧的镜像并发竞速与缓存策略）
(() => {
  const GUANGZHOU = [23.1291, 113.2644];
  const GZ_BBOX = '22.35,112.95,23.94,114.03';
  // GCJ-02 纠偏（与公交侧一致：高德底图上叠 OSM 数据需纠偏）
  let map = null, layer = null;

  const $ = s => document.querySelector(s);
  const status = t => { $('#road-status').textContent = t; };

  // OSM WGS84 → GCJ02（沿用 coords.js 的 GCJ）
  const project = (la, ln) => (window.GCJ ? GCJ.wgs84ToGcj02(la, ln) : [la, ln]);
  const okLL = (la, ln) => Number.isFinite(la) && Number.isFinite(ln) && la > 22 && la < 24 && ln > 112.8 && ln < 114.3;

  const cacheKey = kw => 'gzroad.' + encodeURIComponent(kw) + '.v1';
  const loadCache = k => { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } };
  const saveCache = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* 配额满放弃 */ } };

  function ensureMap() {
    if (map) return;
    map = L.map('roads-map', { zoomControl: true, preferCanvas: true }).setView(GUANGZHOU, 12);
    Tiles.createLayer('amap').addTo(map);
  }

  /** 按关键词查道路段，返回 [{ name, cls, ways: [[[lat,lng],...] ] }] */
  async function searchRoads(kw) {
    const key = cacheKey(kw);
    const cached = loadCache(key);
    if (cached && Array.isArray(cached) && cached.length) return cached;

    const q = `[out:json][timeout:90];way(${GZ_BBOX})["highway"]["name"~"${kw.replace(/"/g, '')}",i];out geom tags;`;
    const json = await Overpass.runQuery(q);
    const byName = new Map();
    for (const el of (json.elements || [])) {
      if (el.type !== 'way' || !el.geometry) continue;
      const pts = el.geometry
        .map(g => [g.lat, g.lon])
        .filter(p => okLL(p[0], p[1]));
      if (pts.length < 2) continue;
      const name = (el.tags && el.tags.name) || '未命名';
      const cls = (el.tags && el.tags.highway) || 'road';
      if (!byName.has(name)) byName.set(name, { name, cls, ways: [] });
      byName.get(name).ways.push(pts);
    }
    const roads = [...byName.values()];
    if (roads.length) saveCache(key, roads);
    return roads;
  }

  const CLS_STYLE = {
    motorway: { color: '#d45d51', weight: 5 },
    trunk:    { color: '#e08a3c', weight: 4.5 },
    primary:  { color: '#e0b23c', weight: 4 },
    secondary:{ color: '#7ec07e', weight: 3.5 },
    tertiary: { color: '#6fa8c9', weight: 3 },
    residential: { color: '#9aa3ad', weight: 2.5 }
  };

  function drawRoads(roads, idx) {
    ensureMap();
    if (layer) { map.removeLayer(layer); layer = null; }
    layer = L.layerGroup();
    const target = roads[idx];
    const bounds = L.latLngBounds([]);
    roads.forEach((r, i) => {
      const st = CLS_STYLE[r.cls] || { color: '#8ab4d6', weight: 3 };
      for (const way of r.ways) {
        const pts = way.map(([la, ln]) => project(la, ln));
        L.polyline(pts, {
          color: st.color, weight: i === idx ? st.weight + 1.5 : st.weight * 0.6,
          opacity: i === idx ? 1 : 0.35,
          lineCap: 'round', interactive: false
        }).addTo(layer);
        if (i === idx) bounds.extend(L.latLngBounds(pts));
      }
    });
    layer.addTo(map);
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 15 });
  }

  function renderList(roads, active) {
    const ul = $('#road-list');
    ul.innerHTML = '';
    roads.forEach((r, i) => {
      const li = document.createElement('li');
      li.className = i === active ? 'active' : '';
      const st = CLS_STYLE[r.cls] || { color: '#8ab4d6' };
      li.innerHTML = `<span class="road-chip" style="background:${st.color}"></span>` +
        `<span class="road-name">${r.name}</span>` +
        `<span class="road-meta">${r.ways.length} 段 · ${r.cls}</span>`;
      li.addEventListener('click', () => {
        [...ul.children].forEach(x => x.classList.remove('active'));
        li.classList.add('active');
        drawRoads(roads, i);
      });
      ul.appendChild(li);
    });
  }

  async function doSearch() {
    const kw = $('#road-search').value.trim();
    if (!kw) return;
    status(`正在查询「${kw}」…`);
    try {
      const roads = await searchRoads(kw);
      if (!roads.length) { status(`没有找到与「${kw}」匹配的道路`); return; }
      roads.sort((a, b) => b.ways.length - a.ways.length);
      status(`「${kw}」匹配 ${roads.length} 条道路 / ${roads.reduce((s, r) => s + r.ways.length, 0)} 个路段`);
      renderList(roads, 0);
      drawRoads(roads, 0);
    } catch (e) {
      status('查询失败：' + e.message);
    }
  }

  function show() {
    ensureMap();
    setTimeout(() => map.invalidateSize(), 60);
  }

  $('#road-go').addEventListener('click', doSearch);
  $('#road-search').addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });

  window.RoadsView = { show };
})();
