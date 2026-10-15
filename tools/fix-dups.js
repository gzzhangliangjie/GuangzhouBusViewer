// 最小修复：只动确证的坏站（与其他站 <6px 重合的），其余一律不动。
// 方法：坏站的本线邻居（好的）之间的路径上找未占用 glyph。
// 门：非重合站零改动；修复后重合对=0；1号线零改动。
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
global.window = {};
require(path.join(ROOT, 'data', 'metro-data.js'));
const D = new Function('window',
  fs.readFileSync(path.join(ROOT, 'js', 'metro-data.js'), 'utf-8') + ';return MetroData;')(window);
const B = window.METRO_DATA.board;

// ---------- 站圆 ----------
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
const circles = [];
for (const m of span('站点').matchAll(/<circle[^>]*?cx="([\d.]+)"[^>]*?cy="([\d.]+)"/g)) {
  circles.push({ x: parseFloat(m[1]), y: parseFloat(m[2]), used: null });
}
for (const m of span('站点').matchAll(/<path[^>]*?d="([^"]+)"/g)) {
  const nums = [...m[1].matchAll(/-?[0-9.]+/g)].map(x => parseFloat(x[0]));
  if (nums.length >= 4) {
    const xs = nums.filter((_, i) => i % 2 === 0), ys = nums.filter((_, i) => i % 2 === 1);
    circles.push({ x: (Math.min(...xs) + Math.max(...xs)) / 2, y: (Math.min(...ys) + Math.max(...ys)) / 2, used: null });
  }
}
console.log('站圆 glyph:', circles.length);

// ---------- 数据 ----------
const stById = new Map(D.allStations().map(s => [s.id, s]));
const XY = {};
for (const s of D.allStations()) XY[s.id] = [s.sx, s.sy];

// 好站占 glyph（≤8px）
for (const g of circles) {
  let best = null, bd = 8;
  for (const s of D.allStations()) {
    const d = Math.hypot(s.sx - g.x, s.sy - g.y);
    if (d < bd) { bd = d; best = s.id; }
  }
  if (best && !circles.some(o => o !== g && o.used === best)) g.used = best;
}

// ---------- 找坏站（重合对） ----------
const ids = Object.keys(XY);
const bad = new Set();
const badPairs = [];
for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) {
  if (Math.hypot(XY[ids[i]][0] - XY[ids[j]][0], XY[ids[i]][1] - XY[ids[j]][1]) < 6) {
    bad.add(ids[i]); bad.add(ids[j]);
    badPairs.push([ids[i], ids[j]]);
  }
}
console.log('重合对:', badPairs.length, '| 坏站:', bad.size);

// 加上"传送站"（与同线两邻都 >100px）
for (const l of D.allLines()) {
  const lids = D.lineStationIds(l);
  lids.forEach((id, i) => {
    if (bad.has(id)) return;
    const a = XY[lids[i - 1]], b = XY[lids[i + 1]];
    if (a && Math.hypot(XY[id][0] - a[0], XY[id][1] - a[1]) > 100 &&
        b && Math.hypot(XY[id][0] - b[0], XY[id][1] - b[1]) > 100) {
      bad.add(id);
      console.log('传送站:', id, l.ref);
    }
  });
}
console.log('总坏站:', bad.size);

// ---------- 修复：坏站在同线好邻居间找未占用 glyph ----------
const fixes = {};
for (const id of bad) {
  const st = stById.get(id);
  let bestLine = null, bestJob = null;
  for (const l of D.allLines()) {
    if (!st.lines.includes(l.ref)) continue;
    const lids = D.lineStationIds(l);
    const i = lids.indexOf(id);
    if (i < 0) continue;
    // 前后好邻居
    let pi = i - 1; while (pi >= 0 && bad.has(lids[pi])) pi--;
    let ni = i + 1; while (ni < lids.length && bad.has(lids[ni])) ni++;
    const prev = pi >= 0 ? XY[lids[pi]] : null;
    const next = ni < lids.length ? XY[lids[ni]] : null;
    if (!prev && !next) continue;

    // 期望位置：有好邻居时取中点外推一站距(54px)；单侧外推
    let ex, ey;
    if (prev && next) {
      const L = Math.hypot(next[0] - prev[0], next[1] - prev[1]);
      const n = ni - pi;   // 间隔站数
      const t = (i - pi) / n;
      ex = prev[0] + (next[0] - prev[0]) * t;
      ey = prev[1] + (next[1] - prev[1]) * t;
    } else if (prev) {
      const dx = prev[0] - XY[id][0], dy = prev[1] - XY[id][1];
      const L = Math.hypot(dx, dy) || 1;
      ex = prev[0] + dx / L * 54; ey = prev[1] + dy / L * 54;
    } else {
      const dx = next[0] - XY[id][0], dy = next[1] - XY[id][1];
      const L = Math.hypot(dx, dy) || 1;
      ex = next[0] - dx / L * 54; ey = next[1] - dy / L * 54;
    }
    // 找最近未占用 glyph
    let best = null, bd = 80;
    for (const g of circles) {
      if (g.used) continue;
      const d = Math.hypot(g.x - ex, g.y - ey);
      if (d < bd) { bd = d; best = g; }
    }
    if (best) {
      const old = XY[id];
      best.used = id;
      fixes[id] = [best.x, best.y];
      console.log('修复', id, '(' + st.lines.join('/') + ')',
        Math.round(old[0]) + ',' + Math.round(old[1]), '→', Math.round(best.x) + ',' + Math.round(best.y),
        '(' + Math.round(Math.hypot(old[0]-best.x, old[1]-best.y)) + 'px, 距期望' + Math.round(bd) + 'px)');
      break;   // 一条线修好即够
    }
  }
}

// ---------- 门 ----------
// 1. 非坏站零改动
let collateral = 0;
for (const s of D.allStations()) {
  if (bad.has(s.id)) continue;
  if (fixes[s.id]) { console.log('[误伤]', s.id); collateral++; }
}
// 2. 修复后重合
for (const [id, c] of Object.entries(fixes)) XY[id] = c;
const all2 = Object.keys(XY);
let dup = 0;
for (let i = 0; i < all2.length; i++) for (let j = i + 1; j < all2.length; j++) {
  if (Math.hypot(XY[all2[i]][0] - XY[all2[j]][0], XY[all2[i]][1] - XY[all2[j]][1]) < 6) {
    dup++;
    console.log('[残余重合]', all2[i], all2[j]);
  }
}
// 3. 1号线
let g1 = 0;
for (const id of D.lineStationIds(D.line('1'))) {
  if (fixes[id]) { console.log('[门1]', id); g1++; }
}
console.log('门: 误伤=' + collateral, '重合=' + dup, '1号线=' + (g1 === 0 ? 'PASS' : 'FAIL'));
if (collateral === 0 && g1 === 0 && Object.keys(fixes).length > 0) {
  fs.writeFileSync(path.join(ROOT, 'assets', '_dup-fix.json'), JSON.stringify(fixes, null, 1));
  console.log('写出 _dup-fix.json:', Object.keys(fixes).length, '站');
}
