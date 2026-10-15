// 公交数据全量审计：坐标合法性 / 同城纯度 / 索引几何一致 / 站点覆盖 / 疑点清单
const fs = require('fs');
const path = require('path');
const { pointInGZ } = require('./gz-polygon');

const DATA = path.join(__dirname, '..', 'data');
const idx = JSON.parse(fs.readFileSync(path.join(DATA, 'bus-index-snapshot.json'), 'utf-8')).data;
const snap = JSON.parse(fs.readFileSync(path.join(DATA, 'bus-lines-snapshot.json'), 'utf-8'));

const report = { totalIdx: idx.length, totalRefs: Object.keys(snap.lines).length, totalVariants: 0 };

// ① 坐标合法性（数值 + 广州及邻域范围）
let badPts = 0, badVariants = [];
const ratioById = new Map();
for (const [ref, vs] of Object.entries(snap.lines)) {
  report.totalVariants += vs.length;
  for (const v of vs) {
    let n = 0, gz = 0, bad = 0;
    for (const seg of v.segments) {
      for (const [la, ln] of seg) {
        n++;
        if (pointInGZ(la, ln)) gz++;
        if (!Number.isFinite(la) || !Number.isFinite(ln) || la < 17 || la > 27 || ln < 111 || ln > 117) { bad++; badPts++; }
      }
    }
    ratioById.set(v.id, n ? gz / n : -1);
    if (bad > 0) badVariants.push(ref + '#' + v.id + ':' + bad);
  }
}
report.badPoints = badPts;
report.badVariants = badVariants.slice(0, 5);

// ② 同城纯度：每条 ref 的变体要么在广州多边形内有点，要么明确是跨市线；
//    混杂 = 同 ref 里既有 0% 广州又有 >0% 广州的变体（可能误并线）
const mixed = [];
for (const [ref, vs] of Object.entries(snap.lines)) {
  const rs = vs.map(v => ratioById.get(v.id)).filter(r => r >= 0);
  if (rs.length > 1 && rs.some(r => r === 0) && rs.some(r => r > 0.3)) mixed.push(ref);
}
report.mixedCityRefs = mixed.length;

// ③ 索引 ↔ 几何一致
const idxRefs = new Set(idx.map(l => l.ref));
const geoRefs = new Set(Object.keys(snap.lines));
let idxNoGeo = [...idxRefs].filter(r => !geoRefs.has(r));
report.idxRefsNoGeometry = idxNoGeo.length;
report.geoRefsNotInIndex = [...geoRefs].filter(r => !idxRefs.has(r)).length;

// ④ 站点覆盖
let noStops = 0;
const noStopRefs = [];
for (const [ref, vs] of Object.entries(snap.lines)) {
  if (vs.every(v => !v.stops.length)) { noStops++; if (noStopRefs.length < 10) noStopRefs.push(ref); }
}
report.refsWithoutStops = noStops;
report.noStopSamples = noStopRefs;

// ⑤ 疑点：名称含外市关键词（应只剩真跨市线）
const FOREIGN_WORDS = ['深圳', '东莞', '惠州', '佛山', '清远', '中山', '珠海', '肇庆', '香港', 'KMB', '城巴', '顺德', '南海', '高明', '鹤山', '桃源', '西樵'];
const suspects = [];
for (const l of idx) {
  const hay = (l.name || '') + (l.operator || '');
  const hit = FOREIGN_WORDS.find(w => hay.includes(w));
  if (hit) suspects.push(l.ref + '(' + hit + ')');
}
report.nameSuspects = suspects.length;
report.nameSuspectSamples = suspects.slice(0, 12);

console.log(JSON.stringify(report, null, 1));
