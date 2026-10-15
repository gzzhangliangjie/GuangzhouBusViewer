// 合并 _pull 分片 → data/bus-index-snapshot.json + data/bus-lines-snapshot.json
// 转换逻辑与 js/overpass.js fetchLineByRef 逐行同构；坐标四舍五入 5 位小数（~1m）
const fs = require('fs');
const path = require('path');

const PULL = path.join(__dirname, '..', 'assets', '_pull');
const DATA = path.join(__dirname, '..', 'data');

const r5 = v => Math.round(v * 1e5) / 1e5;

// ---------- ① 索引：从 batch relation tags 生成（与几何完全同源，避免两次拉取间 OSM 编辑导致的错位） ----------
const _batchesForIdx = fs.readdirSync(PULL).filter(f => /^batch-\d+\.json$/.test(f)).sort();
const _relTags = new Map();
for (const t of _batchesForIdx) {
  const j = JSON.parse(fs.readFileSync(path.join(PULL, t), 'utf-8'));
  for (const el of (j.elements || [])) {
    if (el.type === 'relation' && el.tags && el.tags.route === 'bus') _relTags.set(el.id, el.tags);
  }
}
const idsData = [..._relTags.entries()].map(([id, tags]) => ({ id, tags }));
console.log('relation 总数(batch 源):', idsData.length);

const index = idsData.map(({ id, tags }) => ({
  id,
  ref: (tags && (tags.ref || (tags.name || '').split(/[：（]/)[0])) || '未知',
  name: (tags && tags.name) || '',
  from: (tags && tags.from) || '',
  to: (tags && tags.to) || '',
  operator: (tags && tags.operator) || '',
  colour: (tags && tags.colour) || ''
}));
const nums = new Set(index.map(l => parseInt(l.ref, 10)).filter(n => !isNaN(n)));
const miss = [];
for (let i = 90; i <= 120; i++) if (!nums.has(i)) miss.push(i);
console.log('完整索引记录:', index.length, '| 90-120 缺:', miss.join(',') || '无');
fs.writeFileSync(path.join(DATA, 'bus-index-snapshot.json'),
  JSON.stringify({ at: Date.now(), data: index }));
console.log('bus-index-snapshot.json 写入', index.length, '条');

// ---------- ② 几何合并：batch-*.json ----------
const els = new Map();
const batches = fs.readdirSync(PULL).filter(f => /^batch-\d+\.json$/.test(f)).sort();
console.log('批文件数:', batches.length);
for (const t of batches) {
  const j = JSON.parse(fs.readFileSync(path.join(PULL, t), 'utf-8'));
  if (j.remark && /error/i.test(j.remark)) console.log('警告', t, j.remark);
  for (const el of (j.elements || [])) els.set(el.type + '/' + el.id, el);
}
const all = [...els.values()];
console.log('去重后元素:', all.length,
  'rel:', all.filter(e => e.type === 'relation').length,
  'node:', all.filter(e => e.type === 'node').length,
  'way:', all.filter(e => e.type === 'way').length);

// id -> {lat,lng,name} 查表（与 overpass.js 相同）
const nodeById = new Map();
const wayGeomById = new Map();
for (const el of all) {
  if (el.type === 'node' && el.tags) {
    nodeById.set(el.id, { lat: el.lat, lng: el.lon, name: el.tags.name || el.tags['name:zh'] || '' });
  } else if (el.type === 'way' && el.geometry && el.geometry.length) {
    wayGeomById.set(el.id, { lat: el.geometry[0].lat, lng: el.geometry[0].lon });
  }
}

const lines = {};
let nVar = 0;
for (const el of all) {
  if (el.type !== 'relation' || !el.members || !el.tags || el.tags.route !== 'bus') continue;
  const segments = [];
  const stops = [];
  for (const m of el.members) {
    if (m.type === 'way' && m.geometry && m.geometry.length >= 2 &&
        !(m.role || '').startsWith('platform')) {
      segments.push(m.geometry.map(g => [r5(g.lat), r5(g.lon)]));
    }
    if ((m.role || '').startsWith('platform')) {
      let pt = null, name = '';
      if (m.type === 'node' && m.lat != null) {
        pt = { lat: m.lat, lng: m.lon };
        const info = nodeById.get(m.ref);
        if (info) { name = info.name; if (!pt) pt = { lat: info.lat, lng: info.lng }; }
      } else if (m.type === 'way' && wayGeomById.has(m.ref)) {
        pt = wayGeomById.get(m.ref);
        const el2 = all.find(x => x.type === 'way' && x.id === m.ref);
        if (el2 && el2.tags) name = el2.tags.name || '';
      }
      if (pt) stops.push({ name: name || '未命名站点', lat: r5(pt.lat), lng: r5(pt.lng) });
    }
  }
  const ref = el.tags.ref || (el.tags.name || '').split(/[：（]/)[0] || '未知';
  // 站点兜底：无角色标注的关系（如广州108），node 成员即站点
  if (stops.length === 0) {
    const seen = new Set();
    for (const mm of el.members) {
      if (mm.type !== 'node' || seen.has(mm.ref)) continue;
      seen.add(mm.ref);
      const role = mm.role || '';
      if (role.startsWith('platform') || role === 'stop') continue;
      const info = nodeById.get(mm.ref);
      const pt = (mm.lat != null) ? { lat: mm.lat, lng: mm.lon } : (info ? { lat: info.lat, lng: info.lng } : null);
      if (pt) stops.push({ name: (info && info.name) || '未命名站点', lat: r5(pt.lat), lng: r5(pt.lng) });
    }
  }
  (lines[ref] = lines[ref] || []).push({
    id: el.id, ref,
    name: el.tags.name || '', from: el.tags.from || '', to: el.tags.to || '',
    operator: el.tags.operator || '', colour: el.tags.colour || '', note: el.tags.note || '',
    segments, stops
  });
  nVar++;
}
console.log('线路 ref 数:', Object.keys(lines).length, '变体总数:', nVar);
const withGeom = Object.entries(lines).filter(([, v]) => v.some(x => x.segments.length || x.stops.length));
console.log('有几何的 ref:', withGeom.length);
fs.writeFileSync(path.join(DATA, 'bus-lines-snapshot.json'),
  JSON.stringify({ at: Date.now(), lines }));
console.log('bus-lines-snapshot.json 写入',
  (fs.statSync(path.join(DATA, 'bus-lines-snapshot.json')).size / 1048576).toFixed(1) + 'MB');
