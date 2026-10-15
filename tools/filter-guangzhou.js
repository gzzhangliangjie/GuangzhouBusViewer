// 数据清洗：剔除非广州公交线路（索引 + 几何快照），只保留广州线路
// 规则：operator 含"广州" → 留；operator 命中外市/香港名单 → 删；
//       operator 空或未知 → 几何质心落在广州市域 bbox → 留
const fs = require('fs');
const path = require('path');

const PULL = path.join(__dirname, '..', 'assets', '_pull');
const DATA = path.join(__dirname, '..', 'data');

const { pointInGZ } = require('./gz-polygon');

// 显式拉黑：人工核过的误判线路（广佛界线跨界线，用户确认不属广州公交）
const BLACKLIST = new Set([9699418]);   // "108路(绿地未来城-星晖园)" 张槎路口终点=佛山禅城

const FOREIGN = /深圳|东莞|惠州|佛山|清远|中山|珠海|肇庆|韶关|江门|顺德|南海|三水|高明|鹤山|四会|香港|九巴|KMB|城巴|Citybus|龍運|Long Win|龙运|新大嶼山|新大屿山|嶼巴|屿巴|澳門|澳门|新福利|惠阳|博罗|龙门|增城?巴|從化巴士/;
// 注：增城/从化是广州辖区，其运营方一般含"广州"或"增城/从化"字样，单独白名单
const GZ_EXTRA = /^增城|^从化|^番禺|^花都|^南沙|^广州/;
const GZ_BBOX = [22.35, 112.95, 23.94, 114.03];   // 南北纬，西东经（广州市域近似）

// 判定源与几何同源：batch relations 的 tags（ids.json 属更早一轮拉取，中途被编辑的线路会错位）
const _fs = require('fs');
const _batchFiles = _fs.readdirSync(PULL).filter(f => /^batch-\d+\.json$/.test(f)).sort();
const _tmap = new Map();
for (const bf of _batchFiles) {
  const j = JSON.parse(_fs.readFileSync(path.join(PULL, bf), 'utf-8'));
  for (const el of (j.elements || [])) {
    if (el.type === 'relation' && el.tags && el.tags.route === 'bus') _tmap.set(el.id, el.tags);
  }
}
const ids = [..._tmap.entries()].map(([id, tags]) => ({ id, tags }));
const linesSnap = JSON.parse(fs.readFileSync(path.join(DATA, 'bus-lines-snapshot.json'), 'utf-8'));

// relation id -> tags
const tagById = new Map(ids.map(t => [t.id, t.tags || {}]));

const verdict = new Map();   // relId -> 'gz' | 'foreign' | 'pending-geo'
const stats = { gzOp: 0, gzGeo: 0, foreignOp: 0, foreignGeo: 0, noData: 0 };
for (const [id, tags] of tagById) {
  if (BLACKLIST.has(id)) { verdict.set(id, 'foreign'); continue; }
  const op = tags.operator || '';
  if (op.includes('广州') || GZ_EXTRA.test(op)) { verdict.set(id, 'gz'); stats.gzOp++; continue; }
  if (FOREIGN.test(op)) { verdict.set(id, 'foreign'); stats.foreignOp++; continue; }
  verdict.set(id, 'pending-geo');
}
// 几何点集（多边形判定用）
const pointsByRel = new Map();
for (const variants of Object.values(linesSnap.lines)) {
  for (const v of variants) {
    const pts = [];
    for (const seg of v.segments) for (const [la, ln] of seg) pts.push([la, ln]);
    pointsByRel.set(v.id, pts);
  }
}
const inGzRatio = id => {
  const pts = pointsByRel.get(id) || [];
  if (!pts.length) return -1;
  return pts.reduce((s, p) => s + (pointInGZ(p[0], p[1]) ? 1 : 0), 0) / pts.length;
};

// 几何补判：空/未知运营方 → ≥50% 点在广州市域多边形内才算广州线（防狮山/桂城贴边漏入）
for (const [id, v] of verdict) {
  if (v !== 'pending-geo') continue;
  const r = inGzRatio(id);
  if (r < 0) { verdict.set(id, 'foreign'); stats.noData++; }
  else if (r >= 0.5) { verdict.set(id, 'gz'); stats.gzGeo++; }
  else { verdict.set(id, 'foreign'); stats.foreignGeo++; }
}

// 跨市线路回捞：外市运营但在广州有实际站点序列（≥5 个点且 ≥2%）才留——
// 贴边/跨江而过碰一下的（深中通道类）不算
let crossCity = 0;
for (const [id, v] of verdict) {
  if (v !== 'foreign') continue;
  const pts = pointsByRel.get(id) || [];
  const gzPts = pts.reduce((s2, p) => s2 + (pointInGZ(p[0], p[1]) ? 1 : 0), 0);
  if (pts.length && gzPts >= 5 && gzPts / pts.length >= 0.02) { verdict.set(id, 'gz'); crossCity++; }
}
stats.crossCityKept = crossCity;

// 终扫：与广州不接壤的城市（深圳/香港/中山/珠海/江门/肇庆…）——其线路在广州多边形内的点
// 只可能是跨海/贴边误判（如深中通道贴南沙海角），真有广州站的联营线运营方必含广州
const FAR_CITIES = /香港|九巴|KMB|城巴|Citybus|龍運|龙运|深圳|中山|珠海|江门|肇庆|四会|鹤山|高明|云浮|新兴|韶关|清远市/;
let farDropped = 0;
for (const [id, v] of verdict) {
  if (v !== 'gz') continue;
  const t = tagById.get(id) || {};
  const hay = (t.operator || '') + (t.name || '') + (t.ref || '');
  if (FAR_CITIES.test(hay)) { verdict.set(id, 'foreign'); farDropped++; }
}
stats.farDropped = farDropped;


console.log('判定统计:', JSON.stringify(stats));

// ---------- 过滤索引 ----------
const idxSnap = JSON.parse(fs.readFileSync(path.join(DATA, 'bus-index-snapshot.json'), 'utf-8'));
const idxKeep = idxSnap.data.filter(l => verdict.get(l.id) === 'gz');
// 若同 ref 还有任何 gz 记录，把 foreign 记录剔除；ref 全 foreign 则整组剔除（已覆盖）
// 有几何的 ref 集合（过滤后）
const geoRefsSet = new Set();
for (const [ref, variants] of Object.entries(linesSnap.lines)) {
  const keep = variants.filter(v => verdict.get(v.id) === 'gz');
  if (keep.length) geoRefsSet.add(ref);
}
const idxFinal = idxKeep.filter(l => geoRefsSet.has(l.ref));
fs.writeFileSync(path.join(DATA, 'bus-index-snapshot.json'),
  JSON.stringify({ at: Date.now(), data: idxFinal }));
console.log('索引:', idxSnap.data.length, '->', idxKeep.length, '-> 有几何的', idxFinal.length);

// ---------- 过滤几何 ----------
let vKeep = 0, vDrop = 0;
const newLines = {};
for (const [ref, variants] of Object.entries(linesSnap.lines)) {
  const keep = variants.filter(v => verdict.get(v.id) === 'gz');
  vKeep += keep.length; vDrop += variants.length - keep.length;
  if (keep.length) newLines[ref] = keep;
}
fs.writeFileSync(path.join(DATA, 'bus-lines-snapshot.json'),
  JSON.stringify({ at: Date.now(), lines: newLines }));
console.log('几何 ref:', Object.keys(linesSnap.lines).length, '->', Object.keys(newLines).length,
  '| 变体:', vKeep + vDrop, '->', vKeep);

// 抽样报告被删的外市线
const dropped = idxSnap.data.filter(l => verdict.get(l.id) === 'foreign').slice(0, 8);
console.log('删除样例:', dropped.map(l => l.ref + ' ' + (l.name || '').slice(0, 18)).join(' | '));
