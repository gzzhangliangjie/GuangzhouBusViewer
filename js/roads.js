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

  // 同名路段首尾拼接：OSM 按路口切段，拼回连续长线（视觉上是一条路）
  function mergeWays(ways) {
    const key = p => p[0].toFixed(6) + ',' + p[1].toFixed(6);
    const ends = new Map();          // endpoint key -> [{way, end}]
    const used = new Set();
    const register = (w, end) => {
      const k = key(end);
      if (!ends.has(k)) ends.set(k, []);
      ends.get(k).push({ w, end });
    };
    ways.forEach(w => { register(w, w[0]); register(w, w[w.length - 1]); });

    const chains = [];
    const takeChain = startWay => {
      let chain = startWay.slice();
      used.add(startWay);
      // 两端各自延伸
      for (let side = 0; side < 2; side++) {
        for (let guard = 0; guard < 500; guard++) {
          const end = side === 0 ? chain[0] : chain[chain.length - 1];
          const cands = (ends.get(key(end)) || []).filter(c => !used.has(c.w));
          if (!cands.length) break;
          const seg = cands[0].w;
          used.add(seg);
          if (key(seg[0]) === key(end)) chain = side === 0 ? seg.slice().reverse().concat(chain) : chain.concat(seg.slice(1));
          else chain = side === 0 ? seg.slice().concat(chain.slice(1)) : chain.slice(0, -1).concat(seg.slice().reverse());
        }
      }
      return chain;
    };
    for (const w of ways) {
      if (used.has(w)) continue;
      chains.push(takeChain(w));
    }
    return chains;
  }

  function drawRoads(roads, idx) {
    ensureMap();
    if (layer) { map.removeLayer(layer); layer = null; }
    layer = L.layerGroup();
    const target = roads[idx];
    const bounds = L.latLngBounds([]);
    roads.forEach((r, i) => {
      const st = CLS_STYLE[r.cls] || { color: '#8ab4d6', weight: 3 };
      // 整条路统一风格：拼段 + 深色描边 + 主色，选中路加粗
      const chains = mergeWays(r.ways);
      for (const chain of chains) {
        const pts = chain.map(([la, ln]) => project(la, ln));
        if (i === idx) {
          L.polyline(pts, { color: '#101418', weight: st.weight + 3, opacity: 0.5, lineCap: 'round', lineJoin: 'round', interactive: false }).addTo(layer);
          L.polyline(pts, { color: st.color, weight: st.weight + 1.5, opacity: 1, lineCap: 'round', lineJoin: 'round', interactive: false }).addTo(layer);
          bounds.extend(L.latLngBounds(pts));
        } else {
          L.polyline(pts, { color: st.color, weight: Math.max(1.5, st.weight * 0.55), opacity: 0.3, lineCap: 'round', interactive: false }).addTo(layer);
        }
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

  let searching = false;
  async function doSearch() {
    const kw = $('#road-search').value.trim();
    if (!kw || searching) return;
    searching = true;
    try { await doSearchInner(kw); }
    finally { searching = false; }
  }

  async function doSearchInner(kw) {
    status(`正在查询「${kw}」…`);
    let roads = [];
    try { roads = await searchRoads(kw); } catch (e) {
      status('Overpass 查询失败：' + e.message + '（可稍后重试）');
      return;
    }
    if (roads.length) {
      roads.sort((a, b) => b.ways.length - a.ways.length);
      status(`「${kw}」匹配 ${roads.length} 条道路 / ${roads.reduce((s, r) => s + r.ways.length, 0)} 个路段`);
      renderList(roads, 0);
      drawRoads(roads, 0);
      return;
    }
    // OSM 未收录该路名：高德定位兜底（真实新路 OSM 常滞后，高德有道路名 POI）
    const amapHit = await locateByAmap(kw);
    if (amapHit) {
      renderAmapHit(kw, amapHit);
      status(`OSM 未收录「${kw}」，已用高德定位到 ${amapHit.district}（无路形数据，仅标点）`);
    } else {
      status(`没有找到与「${kw}」匹配的道路（OSM 与高德均无）`);
    }
  }

  // 高德地名定位：v3/place/text 找"道路名"类 POI
  async function locateByAmap(kw) {
    const c = (window.AMapLine && AMapLine.getCreds()) || null;
    if (!c || !c.key) return null;
    try {
      const res = await fetch('https://restapi.amap.com/v3/place/text?key=' + encodeURIComponent(c.key) +
        '&keywords=' + encodeURIComponent(kw) + '&city=' + encodeURIComponent('广州') + '&citylimit=true&offset=10');
      const j = await res.json();
      if (String(j.status) !== '1' || !Array.isArray(j.pois)) return null;
      const roadPoi = j.pois.find(p => /道路名/.test(p.type || '')) || j.pois[0];
      if (!roadPoi) return null;
      const [lng, lat] = String(roadPoi.location || ',').split(',').map(Number);
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) return null;
      return { name: roadPoi.name, district: roadPoi.address || roadPoi.pname || '', lat, lng,
        crossings: j.pois.filter(p => /路口名/.test(p.type || '')).slice(0, 3).map(p => p.name.replace('与' + kw + '交叉口', '').replace(kw + '与', '')) };
    } catch { return null; }
  }

  function renderAmapHit(kw, hit) {
    ensureMap();
    if (layer) { map.removeLayer(layer); layer = null; }
    layer = L.layerGroup();
    L.marker([hit.lat, hit.lng], {
      title: kw
    }).addTo(layer).bindPopup(
      `<div class="popup-stop-name">${kw}（高德定位）</div>` +
      `<div class="popup-stop-meta">${hit.district} · OSM 尚未收录该路名</div>`
    ).openPopup();
    layer.addTo(map);
    map.flyTo([hit.lat, hit.lng], 15);

    const ul = $('#road-list');
    ul.innerHTML = '';
    const li = document.createElement('li');
    li.className = 'active';
    li.innerHTML = `<span class="road-chip" style="background:#4a9eff"></span>` +
      `<span class="road-name">${kw} · ${hit.district}</span>` +
      `<span class="road-meta">高德定位</span>`;
    li.addEventListener('click', () => map.flyTo([hit.lat, hit.lng], 15));
    ul.appendChild(li);
    if (hit.crossings.length) {
      const li2 = document.createElement('li');
      li2.style.cursor = 'default';
      li2.innerHTML = `<span class="road-chip" style="background:#2f3742"></span>` +
        `<span class="road-name" style="color:#8b949e">相交路口：${hit.crossings.join('、')}</span>`;
      ul.appendChild(li2);
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
