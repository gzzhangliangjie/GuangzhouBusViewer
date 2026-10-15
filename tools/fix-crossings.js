// 换乘站交叉定位：多线站的坐标 = 其所属线几何路径的交点（最基础的约束）
// 门：1号线零改动；每站位移报告；残余重合审计。
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
global.window = {};
require(path.join(ROOT, 'data', 'metro-data.js'));
const D = new Function('window',
  fs.readFileSync(path.join(ROOT, 'js', 'metro-data.js'), 'utf-8') + ';return MetroData;')(window);
const B = window.METRO_DATA.board;

function segInt(a1, a2, b1, b2) {
  const d1x = a2[0]-a1[0], d1y = a2[1]-a1[1], d2x = b2[0]-b1[0], d2y = b2[1]-b1[1];
  const den = d1x*d2y - d1y*d2x;
  if (Math.abs(den) < 0.01) return null;
  const t = ((b1[0]-a1[0])*d2y - (b1[1]-a1[1])*d2x) / den;
  const u = ((b1[0]-a1[0])*d1y - (b1[1]-a1[1])*d1x) / den;
  if (t >= -0.01 && t <= 1.01 && u >= -0.01 && u <= 1.01) return [a1[0]+t*d1x, a1[1]+t*d1y];
  return null;
}

const stById = new Map(D.allStations().map(s => [s.id, s]));
const fixes = {};
const XY = {};
for (const s of D.allStations()) XY[s.id] = [s.sx, s.sy];

for (const s of D.allStations()) {
  if (s.lines.length < 2) continue;
  // 该站所属各线的几何
  const paths = s.lines.map(ref => B.lines[ref]).filter(Boolean).map(spec => spec.polys.flat());
  if (paths.length < 2) continue;
  // 两两求交，取距当前坐标最近的交点
  let best = null;
  for (let i = 0; i < paths.length; i++) for (let j = i + 1; j < paths.length; j++) {
    for (let a = 0; a + 1 < paths[i].length; a++) for (let b = 0; b + 1 < paths[j].length; b++) {
      const pt = segInt(paths[i][a], paths[i][a+1], paths[j][b], paths[j][b+1]);
      if (!pt) continue;
      const d = Math.hypot(pt[0] - s.sx, pt[1] - s.sy);
      if (!best || d < best.d) best = { pt, d, lines: s.lines[i] + '×' + s.lines[j] };
    }
  }
  if (best) {
    // 安全：1号线验证过的站不动；交点距当前位置 >300px 说明可能选错交点，跳过
    if (s.lines.includes('1')) best = null;
    else if (best.d > 300) { console.log('跳', s.id, '距' + Math.round(best.d) + 'px (>300)'); best = null; }
  }
  if (best) {
    if (best.d > 4) {
      fixes[s.id] = best.pt;
      console.log(s.id.padEnd(10), Math.round(s.sx) + ',' + Math.round(s.sy), '→', Math.round(best.pt[0]) + ',' + Math.round(best.pt[1]),
        Math.round(best.d) + 'px', '(' + best.lines + ')');
    }
  } else {
    // 无交点（共线或平行），看是否已在某条线的路径上
    console.log('? ', s.id, '无交叉点');
  }
}

// 门
let g1 = 0;
for (const id of D.lineStationIds(D.line('1'))) {
  if (fixes[id]) { console.log('[门1]', id); g1++; }
}
// 应用后重合审计
for (const [id, c] of Object.entries(fixes)) XY[id] = c;
const all = Object.keys(XY);
let dup = 0;
for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) {
  if (Math.hypot(XY[all[i]][0] - XY[all[j]][0], XY[all[i]][1] - XY[all[j]][1]) < 6) dup++;
}
console.log('门1:', g1 === 0 ? 'PASS' : 'FAIL', '| 修复:', Object.keys(fixes).length, '站 | 重合:', dup);

if (g1 === 0) {
  fs.writeFileSync(path.join(ROOT, 'assets', '_cross-fix.json'), JSON.stringify(fixes, null, 1));
  console.log('写出 _cross-fix.json');
}
