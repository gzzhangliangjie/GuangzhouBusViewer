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
  const TIMEOUT_MS = 30000;
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  /**
   * 所有镜像并发竞速，最先返回有效结果者胜（串行轮询太慢：4 镜像 × 30s = 2 分钟，
   * 本机网络对镜像时通时断，竞速把上限压到单个超时 30s）。
   */
  async function runQuery(query, { onMirrorFail } = {}) {
    const attempt = async mirror => {
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
        if (json.remark && /error/i.test(json.remark)) {
          throw new Error('服务端: ' + String(json.remark).slice(0, 80));
        }
        return json;
      } finally {
        clearTimeout(timer);
      }
    };
    try {
      return await Promise.any(MIRRORS.map(attempt));
    } catch (agg) {
      const errs = (agg && agg.errors) || [];
      const msg = errs.length ? errs[errs.length - 1].message : '全部超时';
      if (onMirrorFail) onMirrorFail('并发竞速', new Error(msg));
      throw new Error('所有 Overpass 镜像均失败（' + msg + '）');
    }
  }

  /* ---------- 线路索引 ---------- */

  function loadCache(key) {
    try { return JSON.parse(localStorage.getItem(key)); } catch { return null; }
  }
  function saveCache(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch { /* 配额满则放弃缓存 */ }
  }

  /** 全市公交线路上索引（仅 tags，体积小）。
   *  兜底链：在线镜像 → 过期也用的本地缓存 → 随安装包的离线快照。
   *  本机网络到 Overpass 镜像常被拦（406/500），永远不能让线路列表空白。 */
  async function fetchLineIndex({ force = false, onMirrorFail } = {}) {
    const key = 'gzbus.index.v1';
    const cached = loadCache(key);

    // 本地先行：缓存/随包快照任一有数据 → 立即返回并集（秒出列表），
    // 在线刷新转后台静默做。首次加载绝不能让 UI 等镜像（本机到镜像时通时断）。
    if (!force) {
      const snap = await loadIndexSnapshot();
      const local = (cached && Array.isArray(cached.data) && cached.data.length) ? cached.data : null;
      if ((local && local.length) || (snap && snap.data.length)) {
        refreshIndexInBackground();
        if (snap) return mergeWithSnapshot(local || []);
        return local;
      }
    }

    const query = `[out:json][timeout:90];${AREA_GUANGZHOU}->.gz;rel(area.gz)["route"="bus"];out tags;`;
    let data = null;
    try {
      const json = await runQuery(query, { onMirrorFail });
      data = json.elements.map(el => ({
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
      return mergeWithSnapshot(data);
    } catch (err) {
      // 镜像全挂：先用本地缓存（过期也用），再退到随包快照
      if (cached && Array.isArray(cached.data) && cached.data.length) {
        if (onMirrorFail) onMirrorFail('所有镜像', new Error(`全部失败，使用本地缓存（${new Date(cached.at).toLocaleString()}）`));
        return mergeWithSnapshot(cached.data);
      }
      const snap = await loadIndexSnapshot();
      if (snap) {
        if (onMirrorFail) onMirrorFail('所有镜像', new Error(`全部失败，使用离线快照（${new Date(snap.at).toLocaleString()}）`));
        return snap.data;
      }
      throw err;
    }
  }

  // 后台静默刷新索引（成功只写缓存，不影响已显示的列表）
  let idxRefreshing = false;
  async function refreshIndexInBackground() {
    if (idxRefreshing) return;
    idxRefreshing = true;
    try {
      const query = `[out:json][timeout:90];${AREA_GUANGZHOU}->.gz;rel(area.gz)["route"="bus"];out tags;`;
      const json = await runQuery(query);
      if (!json || !json.elements) return;
      const data = json.elements.map(el => ({
        id: el.id,
        ref: el.tags.ref || (el.tags.name || '').split(/[：（]/)[0] || '未知',
        name: el.tags.name || '',
        from: el.tags.from || '',
        to: el.tags.to || '',
        operator: el.tags.operator || '',
        colour: el.tags.colour || ''
      }));
      if (data.length > 1000) saveCache('gzbus.index.v1', { at: Date.now(), data });
    } catch { /* 静默 */ }
    finally { idxRefreshing = false; }
  }

  // 缓存/在线结果 与 随包快照按 id 并集：旧缓存缺线（曾遇响应截断缺 90-120 段）也能补全
  async function mergeWithSnapshot(data) {
    const snap = await loadIndexSnapshot();
    if (!snap || !Array.isArray(data)) return data;
    const have = new Set(data.map(l => l.id));
    const add = snap.data.filter(l => !have.has(l.id));
    return add.length ? data.concat(add) : data;
  }

  let idxSnap = null;
  async function loadIndexSnapshot() {
    if (idxSnap !== null) return idxSnap;
    try {
      const res = await fetch('data/bus-index-snapshot.json');
      const snap = res.ok ? await res.json() : null;
      idxSnap = (snap && Array.isArray(snap.data) && snap.data.length) ? snap : null;
    } catch { idxSnap = null; }
    return idxSnap;
  }

  /* ---------- 单条线路（含几何与站名） ---------- */

  function lineCacheKey(ref) { return 'gzbus.line.' + encodeURIComponent(ref) + '.v1'; }

  // 随包几何快照（data/bus-lines-snapshot.json：{at, lines:{ref: variants[]}}）
  // 网络全挂时的最终兜底——线路几天不变，离线也要能画
  let linesSnap = null;
  async function loadLinesSnapshot() {
    if (linesSnap !== null) return linesSnap;
    try {
      const res = await fetch('data/bus-lines-snapshot.json');
      const snap = res.ok ? await res.json() : null;
      linesSnap = (snap && snap.lines) || {};
    } catch { linesSnap = {}; }
    return linesSnap;
  }

  // 后台静默刷新某条线（不阻塞 UI；成功只写缓存）
  async function refreshLineInBackground(ref) {
    try {
      const query =
        `[out:json][timeout:90];${AREA_GUANGZHOU}->.gz;` +
        `rel(area.gz)["route"="bus"]["ref"=${JSON.stringify(ref)}]->.r;` +
        `.r out geom;node(r.r);out;way(r.r:"platform");out geom;`;
      const json = await runQuery(query);
      if (!json || !json.elements) return;
      const variants = parseLineVariants(json, ref).map(sanitizeVariant).filter(Boolean);
      if (variants.length) saveCache(lineCacheKey(ref), variants);
    } catch { /* 静默：后台刷新失败不影响已显示的快照数据 */ }
  }

  // Overpass JSON → 变体列表（segments + stops），fetchLineByRef 与后台刷新共用
  function parseLineVariants(json, ref) {
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
          segments.push(m.geometry.map(g => [g.lat, g.lon]));
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
      // 站点兜底：OSM 里不少关系（如广州108）完全没写角色，
      // node 成员实际就是站——platform/stop 都没有时全量收 node 成员
      if (stops.length === 0) {
        const seen = new Set();
        for (const m of el.members) {
          if (m.type !== 'node' || seen.has(m.ref)) continue;
          seen.add(m.ref);
          const role = m.role || '';
          if (role.startsWith('platform') || role === 'stop') continue;  // 上面已处理
          const info = nodeById.get(m.ref);
          const pt = (m.lat != null) ? { lat: m.lat, lng: m.lon } : (info ? { lat: info.lat, lng: info.lng } : null);
          if (pt) stops.push({ name: (info && info.name) || '未命名站点', lat: pt.lat, lng: pt.lng });
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
    return variants;
  }

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
   * 数据是并集不是二选一：在线 ∪ 本地缓存 ∪ 随包快照，按变体 id 去重、
   * 同 id 优先更新鲜的来源（在线 > 缓存 > 快照）。本地已有即秒回，后台静默补在线。
   */
  async function fetchLineByRef(ref, { force = false, onMirrorFail } = {}) {
    const key = lineCacheKey(ref);
    const cached = (!force && loadCache(key)) || null;
    const snap = await loadLinesSnapshot();
    const snapVariants = snap[ref] || [];

    let merged = unionVariants(cached, snapVariants);
    if (merged.length) {
      if (!force) refreshLineInBackground(ref);
      return merged;
    }

    const query =
      `[out:json][timeout:90];${AREA_GUANGZHOU}->.gz;` +
      `rel(area.gz)["route"="bus"]["ref"=${JSON.stringify(ref)}]->.r;` +
      `.r out geom;` +
      `node(r.r);out;` +                          // 节点成员完整输出（带站名 tags）
      `way(r.r:"platform");out geom;`;            // 面状站台的几何

    let variants = [];
    try {
      const json = await runQuery(query, { onMirrorFail });
      variants = parseLineVariants(json, ref);
    } catch (e) {
      // OSM 镜像全挂：本地也没有 → 第二数据源（高德 LineSearch）兜底
    }
    if (!variants.length && !merged.length && typeof AMapLine !== 'undefined' && AMapLine.available()) {
      try {
        const amapVariants = await AMapLine.fetchLine(ref);
        if (amapVariants.length) {
          saveCache(key, amapVariants);
          pruneLineCache();
          return amapVariants;
        }
      } catch { /* 高德也失败则走下面返回 */ }
    }
    if (variants.length === 0 && !merged.length) return null;
    merged = unionVariants(variants, cached, snapVariants);
    if (merged.length) saveCache(key, merged);
    pruneLineCache();
    return merged;
  }

  // 多来源变体按 id 去重合并；靠前的参数优先（同 id 保留先出现的版本）
  function unionVariants(...lists) {
    const byId = new Map();
    for (const list of lists) {
      if (!Array.isArray(list)) continue;
      for (const v of list) {
        if (v && v.id != null && !byId.has(v.id)) byId.set(v.id, v);
      }
    }
    // 净化：历史缓存/异常镜像可能带 null 经度（曾导致视口飞到经度 0 全白）——
    // 非法点直接剔除；一条线段全坏则丢弃该段；变体无任何有效几何/站点则整体排除
    return [...byId.values()].map(sanitizeVariant).filter(Boolean);
  }

  // 运行时黑名单：与 tools/filter-guangzhou.js 的打包黑名单保持一致
  // （人工核过的误判线路：OSM 里标错归属，在线查回来也要拦）
  const RUNTIME_BLACKLIST = new Set([9699418]);   // "108路(绿地未来城-星晖园)" 终点张槎=佛山禅城

  const validLL = (la, ln) => Number.isFinite(la) && Number.isFinite(ln) &&
    la > 17 && la < 27 && ln > 111 && ln < 117;   // 广州及邻市域（跨市线也在此范围）
  const validStop = s => s && validLL(s.lat, s.lng);

  function sanitizeVariant(v) {
    if (!v || RUNTIME_BLACKLIST.has(v.id)) return null;
    const segments = (v.segments || [])
      .map(seg => (seg || []).filter(p => Array.isArray(p) && validLL(p[0], p[1])))
      .filter(seg => seg.length >= 2);
    const stops = (v.stops || []).filter(validStop);
    if (!segments.length && !stops.length) return null;
    return Object.assign({}, v, { segments, stops });
  }

  return { fetchLineIndex, fetchLineByRef, runQuery };
})();
