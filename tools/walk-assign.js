// 站点坐标全量校准：从验证锚站出发，沿站序贪心分配最近站圆
// 每条线从已验证的换乘锚站开始，向两端逐站分配，约束相邻站距 ≤200px
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
global.window = {};
require(path.join(ROOT, 'data', 'metro-data.js'));
const D = new Function('window',
  fs.readFileSync(path.join(ROOT, 'js', 'metro-data.js'), 'utf-8') + ';return MetroData;')(window);
const B = window.METRO_DATA.board;

// 站圆
const svg = fs.readFileSync(path.join(ROOT, 'assets', 'tim-gzfmetro.svg'), 'utf-8');
const stM = svg.indexOf('id="站点"');
let si = svg.indexOf('>', stM) + 1, d = 1, sj = si;
while (d > 0) { const no = svg.indexOf('<g', sj), nc = svg.indexOf('</g>', sj); if (no >= 0 && no < nc) { d++; sj = no + 2; } else { d--; sj = nc + 4; } }
const stSeg = svg.substring(si, sj - 4);
const glyphs = [];
for (const m of stSeg.matchAll(/<circle[^>]*?cx="([\d.]+)"[^>]*?cy="([\d.]+)"/g)) {
  glyphs.push({ x: parseFloat(m[1]), y: parseFloat(m[2]), used: null });
}
for (const m of stSeg.matchAll(/<path[^>]*?d="([^"]+)"/g)) {
  const nums = [...m[1].matchAll(/-?[0-9.]+/g)].map(x => parseFloat(x[0]));
  if (nums.length >= 4) {
    const xs = nums.filter((_, i) => i % 2 === 0), ys = nums.filter((_, i) => i % 2 === 1);
    glyphs.push({ x: (Math.min(...xs) + Math.max(...xs)) / 2, y: (Math.min(...ys) + Math.max(...ys)) / 2, used: null });
  }
}

const stById = new Map(D.allStations().map(s => [s.id, s]));
const XY = {};
for (const s of D.allStations()) XY[s.id] = [s.sx, s.sy];

// 1号线站（已验证）先占 glyph
const l1ids = D.lineStationIds(D.line('1'));
for (const g of glyphs) {
  for (const id of l1ids) {
    const s = stById.get(id);
    if (Math.hypot(s.sx - g.x, s.sy - g.y) <= 5) { g.used = id; break; }
  }
}

// 到线路径的距离
function distToLine(px, py, ref) {
  const spec = B.lines[ref];
  if (!spec) return 1e9;
  let bd = 1e9;
  for (const poly of spec.polys) for (let k = 0; k + 1 < poly.length; k++) {
    const [x1,y1] = poly[k], [x2,y2] = poly[k+1];
    const vx=x2-x1,vy=y2-y1,L2=vx*vx+vy*vy||1;
    const t = Math.max(0, Math.min(1, ((px-x1)*vx+(py-y1)*vy)/L2));
    bd = Math.min(bd, Math.hypot(px-(x1+t*vx), py-(y1+t*vy)));
  }
  return bd;
}

const allMoves = [];

// 按线处理：优先处理锚站多的线
const lineOrder = D.allLines().sort((a, b) => {
  const ac = D.lineStationIds(a).filter(id => glyphs.some(g => g.used === id)).length;
  const bc = D.lineStationIds(b).filter(id => glyphs.some(g => g.used === id)).length;
  return bc - ac;
});

for (const l of lineOrder) {
  const ids = D.lineStationIds(l);
  if (l.ref === '1') continue;   // 1号线已验证

  // 找已占 glyph 的锚站
  const anchorIdx = [];
  ids.forEach((id, i) => {
    if (glyphs.some(g => g.used === id)) anchorIdx.push(i);
  });
  if (!anchorIdx.length) { console.log(l.ref + ': 无锚站跳过'); continue; }

  // 从每个锚站向两端扩展
  for (const ai of anchorIdx) {
    const anchorId = ids[ai];
    const ag = glyphs.find(g => g.used === anchorId);
    if (!ag) continue;

    // 向后扩展
    for (let i = ai - 1; i >= 0; i--) {
      const id = ids[i];
      if (glyphs.some(g => g.used === id)) break;   // 碰到另一个锚站
      const nextId = ids[i + 1];
      const nextG = glyphs.find(g => g.used === nextId);
      if (!nextG) break;
      // 找 nextG 附近最近的未占 glyph，且在本线路径上
      let best = null, bd = 200;
      for (const g of glyphs) {
        if (g.used) continue;
        const d = Math.hypot(g.x - nextG.x, g.y - nextG.y);
        const onLine = distToLine(g.x, g.y, l.ref) <= 15;
        if (d < bd && onLine && d > 8) { bd = d; best = g; }
      }
      if (best) {
        best.used = id;
        const s = stById.get(id);
        const d = Math.hypot(s.sx - best.x, s.sy - best.y);
        if (d > 4) allMoves.push([l.ref, id, Math.round(s.sx) + ',' + Math.round(s.sy), Math.round(best.x) + ',' + Math.round(best.y), Math.round(d)]);
        XY[id] = [best.x, best.y];
      } else break;
    }
    // 向前扩展
    for (let i = ai + 1; i < ids.length; i++) {
      const id = ids[i];
      if (glyphs.some(g => g.used === id)) break;
      const prevId = ids[i - 1];
      const prevG = glyphs.find(g => g.used === prevId);
      if (!prevG) break;
      let best = null, bd = 200;
      for (const g of glyphs) {
        if (g.used) continue;
        const d = Math.hypot(g.x - prevG.x, g.y - prevG.y);
        const onLine = distToLine(g.x, g.y, l.ref) <= 15;
        if (d < bd && onLine && d > 8) { bd = d; best = g; }
      }
      if (best) {
        best.used = id;
        const s = stById.get(id);
        const d = Math.hypot(s.sx - best.x, s.sy - best.y);
        if (d > 4) allMoves.push([l.ref, id, Math.round(s.sx) + ',' + Math.round(s.sy), Math.round(best.x) + ',' + Math.round(best.y), Math.round(d)]);
        XY[id] = [best.x, best.y];
      } else break;
    }
  }
}

// ---------- 门 ----------
let g1 = 0;
for (const id of l1ids) {
  const s = stById.get(id);
  if (Math.hypot(XY[id][0] - s.sx, XY[id][1] - s.sy) > 4) { console.log('[门1]', id); g1++; }
}
const all = Object.keys(XY);
let dup = 0;
for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) {
  if (Math.hypot(XY[all[i]][0] - XY[all[j]][0], XY[all[i]][1] - XY[all[j]][1]) < 6) {
    dup++;
    if (dup <= 8) console.log('[重合]', all[i], all[j]);
  }
}
// 站距异常统计
let jumpy = 0;
for (const l of D.allLines()) {
  const lids = D.lineStationIds(l);
  for (let i = 0; i + 1 < lids.length; i++) {
    const d = Math.hypot(XY[lids[i]][0] - XY[lids[i+1]][0], XY[lids[i]][1] - XY[lids[i+1]][1]);
    if (d > 200) jumpy++;
  }
}
console.log('门1:', g1 === 0 ? 'PASS' : 'FAIL', '| 位移:', allMoves.length, '| 重合:', dup, '| 跳跃>200px:', jumpy);
allMoves.sort((a, b) => b[4] - a[4]);
console.log('位移 top10:');
allMoves.slice(0, 10).forEach(m => console.log('  [' + m[0] + ']', m[1], m[2], '→', m[3], m[4] + 'px'));

if (g1 === 0) {
  const fix = {};
  for (const m of allMoves) fix[m[1]] = XY[m[1]];
  fs.writeFileSync(path.join(ROOT, 'assets', '_walk-fix.json'), JSON.stringify(fix, null, 1));
  console.log('写出 _walk-fix.json:', Object.keys(fix).length, '站');
}
