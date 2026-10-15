// 弦线锚定迭代修复：好站(与两邻弦线一致)作锚；坏站(偏离弦线>55px 或 <6px 重合)
// 在两好邻居弦段上按序填充最近未占用 glyph；修好即成新锚点迭代传播。
// 门：1号线零改动；重合对清零；全部位移清单打印。
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
global.window = {};
require(path.join(ROOT, 'data', 'metro-data.js'));
const D = new Function('window',
  fs.readFileSync(path.join(ROOT, 'js', 'metro-data.js'), 'utf-8') + ';return MetroData;')(window);

// ---------- glyph ----------
const svg = fs.readFileSync(path.join(ROOT, 'assets', 'tim-gzfmetro.svg'), 'utf-8');
function span(gid) {
  const m = new RegExp('<g id="' + gid + '"').exec(svg);
  let i = svg.indexOf('>', m.index) + 1, depth = 1, j = i;
  while (depth > 0) {
    const no = svg.indexOf('<g', j), nc = svg.indexOf('</g>', j);
    if (nc < 0) break;
    if (no >= 0 && no < nc) { depth++; j = no + 2; } else { depth--; j = nc + 4; }
  }
  return svg.slice(i, j - 4);
}
const stSeg = span('站点');
const glyphs = [];
for (const m of stSeg.matchAll(/<circle[^>]*>/g)) {
  glyphs.push({ x: parseFloat(/cx="([\d.]+)"/.exec(m[0])[1]), y: parseFloat(/cy="([\d.]+)"/.exec(m[0])[1]), used: null });
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

// 好站占用自身 glyph（≤10px，一站一 glyph）
for (const g of glyphs) {
  let best = null, bd = 10;
  for (const s of D.allStations()) {
    const d = Math.hypot(s.sx - g.x, s.sy - g.y);
    if (d < bd) { bd = d; best = s.id; }
  }
  if (best !== null && !glyphs.some(o => o.used === best)) g.used = best;
}

function badness() {
  const bad = new Set();
  for (const l of D.allLines()) {
    const ids = D.lineStationIds(l);
    ids.forEach((id, i) => {
      const a = XY[ids[i - 1]], b = XY[ids[i + 1]], p = XY[id];
      if (a && b) {
        const vx = b[0] - a[0], vy = b[1] - a[1], L2 = vx * vx + vy * vy || 1;
        const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2));
        const d = Math.hypot(p[0] - (a[0] + t * vx), p[1] - (a[1] + t * vy));
        if (d > 55) bad.add(id);
      }
    });
  }
  const ids = Object.keys(XY);
  for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) {
    if (Math.hypot(XY[ids[i]][0] - XY[ids[j]][0], XY[ids[i]][1] - XY[ids[j]][1]) < 6) { bad.add(ids[i]); bad.add(ids[j]); }
  }
  return bad;
}

const moves = [];
for (let round = 0; round < 12; round++) {
  const bad = badness();
  if (!bad.size) break;
  const jobs = [];
  for (const l of D.allLines()) {
    const ids = D.lineStationIds(l);
    ids.forEach((id, i) => {
      if (!bad.has(id)) return;
      let pi = i - 1, ni = i + 1;
      while (pi >= 0 && bad.has(ids[pi])) pi--;
      while (ni < ids.length && bad.has(ids[ni])) ni++;
      const a = pi >= 0 ? { id: ids[pi], xy: XY[ids[pi]] } : null;
      const b = ni < ids.length ? { id: ids[ni], xy: XY[ids[ni]] } : null;
      jobs.push({ id, line: l.ref, i, a, b, span: (a && b) ? Math.hypot(b.xy[0] - a.xy[0], b.xy[1] - a.xy[1]) : 1e9 });
    });
  }
  jobs.sort((x, y) => x.span - y.span);
  let fixedThis = 0;
  for (const job of jobs) {
    if (fixedThis >= 14) break;
    const { a, b } = job;
    let base, dirx, diry;
    if (a && b) { base = a.xy; dirx = b.xy[0] - a.xy[0]; diry = b.xy[1] - a.xy[1]; }
    else if (a) { base = a.xy; dirx = a.xy[0] - XY[job.id][0]; diry = a.xy[1] - XY[job.id][1]; }
    else if (b) { base = b.xy; dirx = b.xy[0] - XY[job.id][0]; diry = b.xy[1] - XY[job.id][1]; }
    else continue;
    const L = Math.hypot(dirx, diry) || 1;
    dirx /= L; diry /= L;
    let t;
    if (a && b) {
      const si = D.lineStationIds(D.line(job.line)).indexOf(a.id);
      const sj = D.lineStationIds(D.line(job.line)).indexOf(b.id);
      t = (job.i - si) / ((sj - si) || 1);
    } else t = 1;
    const chordLen = (a && b) ? L : 54;
    const ex = base[0] + dirx * t * chordLen;
    const ey = base[1] + diry * t * chordLen;
    let best = null;
    for (const g of glyphs) {
      if (g.used) continue;
      const d = Math.hypot(g.x - ex, g.y - ey);
      if (d <= 70 && (!best || d < best.d)) best = { g, d };
    }
    if (best) {
      const old = XY[job.id];
      best.g.used = job.id;
      XY[job.id] = [best.g.x, best.g.y];
      moves.push([job.line, job.id, Math.round(old[0]) + ',' + Math.round(old[1]), Math.round(best.g.x) + ',' + Math.round(best.g.y), Math.round(Math.hypot(old[0] - best.g.x, old[1] - best.g.y))]);
      fixedThis++;
    }
  }
  if (!fixedThis) break;
}

// ---------- 门 ----------
const l1ids = D.lineStationIds(D.line('1'));
let g1bad = 0;
for (const id of l1ids) {
  const s = stById.get(id);
  if (Math.hypot(XY[id][0] - s.sx, XY[id][1] - s.sy) > 3) { console.log('[门1号线被改动!]', id); g1bad++; }
}
const all = Object.keys(XY);
let dup = 0;
for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) {
  if (Math.hypot(XY[all[i]][0] - XY[all[j]][0], XY[all[i]][1] - XY[all[j]][1]) < 6) {
    dup++;
    if (dup <= 8) console.log('[残余重合]', all[i], all[j]);
  }
}
console.log('门1号线:', g1bad === 0 ? 'PASS' : 'FAIL', '| 修复后重合对:', dup, '| 位移数:', moves.length);
moves.forEach(m => console.log('  [' + m[0] + ']', m[1], m[2], '→', m[3], '(' + m[4] + 'px)'));
if (g1bad === 0) {
  const out = {};
  for (const m of moves) out[m[1]] = XY[m[1]];
  fs.writeFileSync(path.join(ROOT, 'assets', '_chord-fix.json'), JSON.stringify(out, null, 1));
  console.log('写出 _chord-fix.json:', Object.keys(out).length, '站');
}
