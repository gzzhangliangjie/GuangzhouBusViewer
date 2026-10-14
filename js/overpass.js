// Overpass API 数据层：镜像站轮询 + 本地缓存
// 数据来源 OpenStreetMap（ODbL 许可）

const Overpass = (() => {
  const MIRRORS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
    'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
    'https://overpass.openstreetmap.ru/api/interpreter'
  ];

  const AREA_GUANGZHOU = 'area["name"="广州市"]["boundary"="administrative"]';
  const INDEX_TTL = 24 * 60 * 60 * 1000;      // 线路列表缓存 24 小时
  const LINE_CACHE_MAX = 20;                  // 线路几何最多缓存 20 条
  const TIMEOUT_MS = 45000;
  const ROUNDS = 2;                           // 镜像整体轮询两轮，应对瞬时 504
  const ROUND_PAUSE_MS = 2500;

  const sleep = ms => new Promise(r => setTimeout(r, ms));

  /**
   * 依次尝试各镜像站执行查询（共 ROUNDS 轮），全部失败时抛出最后一个错误。
   * onMirrorFail(mirror, err) 可用于展示进度。
   */
  async function runQuery(query, { onMirrorFail } = {}) {
    let lastErr = null;
    for (let round = 0; round < ROUNDS; round++) {
      if (round > 0) await sleep(ROUND_PAUSE_MS);
      for (const mirror of MIRRORS) {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
        try {
          const res = await fetch(mirror, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: 'data=' + encodeURIComponent(query),
            signal: ctrl.signal
          });
          if (!res.ok) throw new Error('HTTP ' + res.status);
          const json = await res.json();
          if (json.remark && json.elements && json.elements.length === 0) {
            throw new Error('服务端提示: ' + String(json.remark).slice(0, 120));
          }
          return json;
        } catch (err) {
          lastErr = err;
          if (onMirrorFail) onMirrorFail(mirror, err);
        } finally {
          clearTimeout(timer);
        }
      }
    }
    throw lastErr || new Error('所有 Overpass 镜像均不可用');
  }

  /* ---------- 线路索引 ---------- */

  function loadCache(key) {
    try { return JSON.parse(localStorage.getItem(key)); } catch { return null; }
  }
  function saveCache(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch { /* 配额满则放弃缓存 */ }
  }

  /** 全市公交线路上索引（仅 tags，体积小） */
  async function fetchLineIndex({ force = false, onMirrorFail } = {}) {
    const key = 'gzbus.index.v1';
    const cached = loadCache(key);
    if (!force && cached && Date.now() - cached.at < INDEX_TTL) return cached.data;

    const query = `[out:json][timeout:90];${AREA_GUANGZHOU}->.gz;rel(area.gz)["route"="bus"];out tags;`;
    const json = await runQuery(query, { onMirrorFail });

    const data = json.elements.map(el => ({
      id: el.id,
      ref: el.tags.ref || (el.tags.name || '').split(/[：（]/)[0] || '未知',
      name: el.tags.name || '',
      from: el.tags.from || '',
      to: el.tags.to || '',
      operator: el.tags.operator || '',
      colour: el.tags.colour || ''
    }));

    saveCache(key, { at: Date.now(), data });
    // 写入新索引时顺手清理旧线路几何缓存，避免超配额
    pruneLineCache();
    return data;
  }

  /* ---------- 单条线路（含几何与站名） ---------- */

  function lineCacheKey(ref) { return 'gzbus.line.' + encodeURIComponent(ref) + '.v1'; }

  function pruneLineCache() {
    const entries = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith('gzbus.line.')) {
        let at = 0;
        try { at = (JSON.parse(localStorage.getItem(k)) || {}).at || 0; } catch {}
        entries.push([k, at]);
      }
    }
    entries.sort((a, b) => b[1] - a[1]);
    for (let i = LINE_CACHE_MAX; i < entries.length; i++) localStorage.removeItem(entries[i][0]);
  }

  /**
   * 按线路号取该号下所有方向/变体的完整几何。
   * 返回 [{ id, ref, name, from, to, operator, colour, note,
   *         segments: [[ [lat,lng], ... ]], stops: [{ name, lat, lng }] }]
   */
  async function fetchLineByRef(ref, { force = false, onMirrorFail } = {}) {
    const key = lineCacheKey(ref);
    if (!force) {
      const cached = loadCache(key);
      if (cached) return cached;
    }

    const query =
      `[out:json][timeout:90];${AREA_GUANGZHOU}->.gz;` +
      `rel(area.gz)["route"="bus"]["ref"=${JSON.stringify(ref)}]->.r;` +
      `.r out geom;` +
      `node(r.r);out;` +                          // 节点成员完整输出（带站名 tags）
      `way(r.r:"platform");out geom;`;            // 面状站台的几何

    const json = await runQuery(query, { onMirrorFail });

    // id -> {lat,lng,name} 查表：node 成员补站名，way 站台取几何首点
    const nodeById = new Map();
    const wayGeomById = new Map();
    for (const el of json.elements) {
      if (el.type === 'node' && el.tags) {
        nodeById.set(el.id, { lat: el.lat, lng: el.lon, name: el.tags.name || el.tags['name:zh'] || '' });
      } else if (el.type === 'way' && el.geometry && el.geometry.length) {
        wayGeomById.set(el.id, { lat: el.geometry[0].lat, lng: el.geometry[0].lon });
      }
    }

    const variants = [];
    for (const el of json.elements) {
      if (el.type !== 'relation' || !el.members) continue;
      const segments = [];
      const stops = [];
      for (const m of el.members) {
        if (m.type === 'way' && m.geometry && m.geometry.length >= 2 &&
            !(m.role || '').startsWith('platform')) {
          segments.push(m.geometry.map(g => [g.lat, g.lng]));
        }
        if ((m.role || '').startsWith('platform')) {
          let pt = null, name = '';
          if (m.type === 'node' && m.lat != null) {
            pt = { lat: m.lat, lng: m.lon };
            const info = nodeById.get(m.ref);
            if (info) { name = info.name; if (!pt) pt = { lat: info.lat, lng: info.lng }; }
          } else if (m.type === 'way' && wayGeomById.has(m.ref)) {
            pt = wayGeomById.get(m.ref);
            const el2 = json.elements.find(x => x.type === 'way' && x.id === m.ref);
            if (el2 && el2.tags) name = el2.tags.name || '';
          }
          if (pt) stops.push({ name: name || '未命名站点', lat: pt.lat, lng: pt.lng });
        }
      }
      variants.push({
        id: el.id,
        ref: (el.tags && el.tags.ref) || ref,
        name: (el.tags && el.tags.name) || '',
        from: (el.tags && el.tags.from) || '',
        to: (el.tags && el.tags.to) || '',
        operator: (el.tags && el.tags.operator) || '',
        colour: (el.tags && el.tags.colour) || '',
        note: (el.tags && el.tags.note) || '',
        segments, stops
      });
    }

    if (variants.length === 0) return null;
    saveCache(key, variants);
    pruneLineCache();
    return variants;
  }

  return { fetchLineIndex, fetchLineByRef };
})();
