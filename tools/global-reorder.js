// 全局站序重排：每条线的站圆按起→终方向投影排序，站序一一对应
// 环线（11号线）用锚站分段处理
// 门：1号线零改动；重合对=0；全部位移打印
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
const allMoves = [];

for (const l of D.allLines()) {
  const ids = D.lineStationIds(l);
  const spec = B.lines[l.ref];
  if (!spec) continue;
  const isLoop = l.loop && ids.length > 2;

  // 线路路径附近的 glyph（≤15px）
  const distToPath = (px, py) => {
    let bd = 1e9;
    for (const poly of spec.polys) for (let k = 0; k + 1 < poly.length; k++) {
      const [x1,y1] = poly[k], [x2,y2] = poly[k+1];
      const vx=x2-x1,vy=y2-y1,L2=vx*vx+vy*vy||1;
      const t = Math.max(0, Math.min(1, ((px-x1)*vx+(py-y1)*vy)/L2));
      bd = Math.min(bd, Math.hypot(px-(x1+t*vx), py-(y1+t*vy)));
    }
    return bd;
  };
  const lineGlyphs = glyphs.filter(g => !g.used && distToPath(g.x, g.y) <= 15);
  if (lineGlyphs.length < ids.length) {
    console.log(l.ref + ': glyph' + lineGlyphs.length + '<站' + ids.length + ' 跳过');
    continue;
  }

  if (isLoop) {
    // 环线：找已验证的换乘锚站分段
    const anchors = [];
    ids.forEach((id, i) => {
      const s = stById.get(id);
      if (s.lines.length > 1 && distToPath(s.sx, s.sy) <= 15) anchors.push({ i, id, xy: [s.sx, s.sy] });
    });
    if (anchors.length < 2) { console.log(l.ref + '(环): 锚不足'); continue; }
    // 锚间区间处理
    for (let k = 0; k < anchors.length; k++) {
      const A = anchors[k];
      const Bn = anchors[(k + 1) % anchors.length];
      const gapCount = k === anchors.length - 1
        ? (ids.length - A.i - 1) + Bn.i
        : Bn.i - A.i - 1;
      if (gapCount <= 0) continue;
      const gapIds = [];
      if (k === anchors.length - 1) {
        for (let i = A.i + 1; i < ids.length; i++) gapIds.push(ids[i]);
        for (let i = 0; i < Bn.i; i++) gapIds.push(ids[i]);
      } else {
        for (let i = A.i + 1; i < Bn.i; i++) gapIds.push(ids[i]);
      }
      assignInRange(l.ref, gapIds, A.xy, Bn.xy, lineGlyphs);
    }
  } else {
    // 非环线：按起→终方向投影排序
    const first = stById.get(ids[0]);
    const last = stById.get(ids[ids.length - 1]);
    const vx = last.sx - first.sx, vy = last.sy - first.sy;
    const L = Math.hypot(vx, vy) || 1;
    const ux = vx / L, uy = vy / L;
    lineGlyphs.sort((a, b) => ((a.x - first.sx) * ux + (a.y - first.sy) * uy) - ((b.x - first.sx) * ux + (b.y - first.sy) * uy));
    // 站数 == glyph 数时一一对应
    if (lineGlyphs.length === ids.length) {
      ids.forEach((id, q) => {
        const g = lineGlyphs[q];
        g.used = id;
        const s = stById.get(id);
        const d = Math.hypot(s.sx - g.x, s.sy - g.y);
        if (d > 4) allMoves.push([l.ref, id, Math.round(s.sx) + ',' + Math.round(s.sy), Math.round(g.x) + ',' + Math.round(g.y), Math.round(d)]);
        XY[id] = [g.x, g.y];
      });
    } else {
      // glyph > 站数：按比例选取
      const step = lineGlyphs.length / ids.length;
      ids.forEach((id, q) => {
        const g = lineGlyphs[Math.floor(q * step)];
        if (!g || g.used) return;
        g.used = id;
        const s = stById.get(id);
        const d = Math.hypot(s.sx - g.x, s.sy - g.y);
        if (d > 4) allMoves.push([l.ref, id, Math.round(s.sx) + ',' + Math.round(s.sy), Math.round(g.x) + ',' + Math.round(g.y), Math.round(d)]);
        XY[id] = [g.x, g.y];
      });
    }
  }
}

function assignInRange(ref, gapIds, A, Bn, pool) {
  if (!gapIds.length) return;
  const vx = Bn[0] - A[0], vy = Bn[1] - A[1], L = Math.hypot(vx, vy) || 1;
  const ux = vx / L, uy = vy / L;
  const mx = (A[0] + Bn[0]) / 2, my = (A[1] + Bn[1]) / 2;
  const hw = Math.abs(vx) / 2 + 50, hh = Math.abs(vy) / 2 + 50;
  const cands = pool.filter(g => !g.used &&
    Math.abs(g.x - mx) <= hw && Math.abs(g.y - my) <= hh &&
    Math.abs((g.x - A[0]) * uy - (g.y - A[1]) * ux) <= 35);
  cands.sort((a, b) => ((a.x - A[0]) * ux + (a.y - A[1]) * uy) - ((b.x - A[0]) * ux + (b.y - A[1]) * uy));
  const n = Math.min(gapIds.length, cands.length);
  for (let q = 0; q < n; q++) {
    const g = cands[Math.floor(q * cands.length / n)];
    if (g.used) continue;
    g.used = gapIds[q];
    const s = stById.get(gapIds[q]);
    const d = Math.hypot(s.sx - g.x, s.sy - g.y);
    if (d > 4) allMoves.push([ref, gapIds[q], Math.round(s.sx) + ',' + Math.round(s.sy), Math.round(g.x) + ',' + Math.round(g.y), Math.round(d)]);
    XY[gapIds[q]] = [g.x, g.y];
  }
}

// 门
let g1 = 0;
for (const id of D.lineStationIds(D.line('1'))) {
  const s = stById.get(id);
  if (Math.hypot(XY[id][0] - s.sx, XY[id][1] - s.sy) > 4) { console.log('[门1]', id); g1++; }
}
const all = Object.keys(XY);
let dup = 0;
for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) {
  if (Math.hypot(XY[all[i]][0] - XY[all[j]][0], XY[all[i]][1] - XY[all[j]][1]) < 6) {
    dup++;
    if (dup <= 10) console.log('[重合]', all[i], all[j]);
  }
}
console.log('门1:', g1 === 0 ? 'PASS' : 'FAIL', '| 位移:', allMoves.length, '| 重合:', dup);
allMoves.sort((a, b) => b[4] - a[4]);
console.log('位移 top15:');
allMoves.slice(0, 15).forEach(m => console.log('  [' + m[0] + ']', m[1], m[2], '→', m[3], m[4] + 'px'));

if (g1 === 0) {
  const fix = {};
  for (const m of allMoves) fix[m[1]] = XY[m[1]];
  fs.writeFileSync(path.join(ROOT, 'assets', '_global-fix.json'), JSON.stringify(fix, null, 1));
  console.log('写出 _global-fix.json:', Object.keys(fix).length, '站');
}
