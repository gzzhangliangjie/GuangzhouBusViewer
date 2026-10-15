// OCR 名录匹配：ocr-results.json（站名+像素）→ viewBox 坐标 → 最近站名矢量组 → 真实站圆 glyph
// 门：每名只配一组；glyph 唯一占用；与现数据差异清单；1号线零改动。
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
global.window = {};
require(path.join(ROOT, 'data', 'metro-data.js'));
const D = new Function('window',
  fs.readFileSync(path.join(ROOT, 'js', 'metro-data.js'), 'utf-8') + ';return MetroData;')(window);

// ---------- SVG 站名组 bbox ----------
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
const nmSeg = span('站名');
const nameGroups = [];
{
  let pos = 0;
  while (true) {
    const m = /<g\b[^>]*>/.exec(nmSeg.slice(pos));
    if (!m) break;
    const start = pos + m.index;
    let depth = 1, j = start + m[0].length;
    while (depth > 0) {
      const no = nmSeg.indexOf('<g', j), nc = nmSeg.indexOf('</g>', j);
      if (nc < 0) break;
      if (no >= 0 && no < nc) { depth++; j = no + 2; } else { depth--; j = nc + 4; }
    }
    const chunk = nmSeg.slice(start, j);
    const ds = [...chunk.matchAll(/d="M([0-9.]+),([0-9.]+)/g)];
    if (ds.length >= 1) {
      const xs = ds.map(x => parseFloat(x[1])), ys = ds.map(x => parseFloat(x[2]));
      nameGroups.push({ cx: (Math.min(...xs) + Math.max(...xs)) / 2, cy: (Math.min(...ys) + Math.max(...ys)) / 2 });
    }
    pos = j;
  }
}
console.log('站名矢量组:', nameGroups.length);

// ---------- glyph ----------
const stSeg = span('站点');
const glyphs = [];
for (const m of stSeg.matchAll(/<circle[^>]*>/g)) {
  glyphs.push({ x: parseFloat(/cx="([\d.]+)"/.exec(m[0])[1]), y: parseFloat(/cy="([\d.]+)"/.exec(m[0])[1]) });
}
for (const m of stSeg.matchAll(/<path[^>]*?d="([^"]+)"/g)) {
  const nums = [...m[1].matchAll(/-?[0-9.]+/g)].map(x => parseFloat(x[0]));
  if (nums.length >= 4) {
    const xs = nums.filter((_, i) => i % 2 === 0), ys = nums.filter((_, i) => i % 2 === 1);
    glyphs.push({ x: (Math.min(...xs) + Math.max(...xs)) / 2, y: (Math.min(...ys) + Math.max(...ys)) / 2 });
  }
}
console.log('站圆 glyph:', glyphs.length);

// ---------- OCR 结果 → viewBox ----------
const ocr = JSON.parse(fs.readFileSync(path.join(ROOT, 'assets', '_tiles', 'ocr-results.json'), 'utf-8'));
const RAW = 2848.5, RAH = 2054.25, S = 2.2, ov = 0.12;
const COLS = 4, ROWS = 3;
const tw = Math.ceil(RAW / COLS), th = Math.ceil(RAH / ROWS);
// 命中投票：同站多次读数取中位
const byName = {};
for (const [half, entries] of Object.entries(ocr)) {
  const r = parseInt(half[1]), c = parseInt(half[2]), side = half[3];
  const px = side === 'r' ? 1300 - 62 : 0;   // 右半在整块中的 x 偏移 = 1238（重叠 62）
  for (const e of entries) {
    // 像素(在半块内) → 整块像素 → viewBox
    const gx = (px + e.x) / S + (c * tw - tw * ov);
    const gy = e.y / S + (r * th - th * ov);
    (byName[e.name] = byName[e.name] || []).push([gx, gy]);
  }
}
console.log('OCR 读到站名数:', Object.keys(byName).length);

// 数据站名集合（过滤幻觉）
const dataIds = new Set(D.allStations().map(s => s.id));
const stById = new Map(D.allStations().map(s => [s.id, s]));
const fixed = {};
const unmatched = [];
for (const [name, pts] of Object.entries(byName)) {
  if (!dataIds.has(name)) { unmatched.push(name + '(不在数据)'); continue; }
  if (pts.length < 2) { unmatched.push(name + '(单次读数,跳过)'); continue; }
  // 多次读数两两距离 <25px 才可信（跨块重叠验证）
  pts.sort((a, b) => a[0] - b[0]);
  const med = pts[Math.floor(pts.length / 2)];
  const agree = pts.filter(p => Math.hypot(p[0] - med[0], p[1] - med[1]) < 25);
  if (agree.length < 2) { unmatched.push(name + '(读数不一致)'); continue; }
  const vx = agree.reduce((s, p) => s + p[0], 0) / agree.length;
  const vy = agree.reduce((s, p) => s + p[1], 0) / agree.length;
  // → 最近站名矢量组（≤30px）
  let ng = null, nd = 30;
  for (const g of nameGroups) {
    const d = Math.hypot(g.cx - vx, g.cy - vy);
    if (d < nd) { nd = d; ng = g; }
  }
  if (!ng) { unmatched.push(name + '(无矢量组@' + Math.round(vx) + ',' + Math.round(vy) + ')'); continue; }
  // → 矢量组最近 glyph（≤45px）
  let gl = null, gd = 45;
  for (const g of glyphs) {
    const d = Math.hypot(g.x - ng.cx, g.y - ng.cy);
    if (d < gd) { gd = d; gl = g; }
  }
  if (!gl) { unmatched.push(name + '(无glyph)'); continue; }
  fixed[name] = [gl.x, gl.y];
}
console.log('可信匹配站数:', Object.keys(fixed).length, '| 未匹配:', unmatched.length);
unmatched.slice(0, 12).forEach(x => console.log('  ?', x));

// glyph 冲突审计（一站一圆）
const rev = {};
let conflicts = 0;
for (const [n, c] of Object.entries(fixed)) {
  const k = c[0] + ',' + c[1];
  if (rev[k] && rev[k] !== n) { conflicts++; console.log('[glyph冲突]', n, 'vs', rev[k]); }
  rev[k] = n;
}

// 与现数据差异
const moves = [];
for (const [n, c] of Object.entries(fixed)) {
  const s = stById.get(n);
  const d = Math.hypot(s.sx - c[0], s.sy - c[1]);
  if (d > 4) moves.push([d, n]);
}
moves.sort((a, b) => b[0] - a[0]);
console.log('glyph 冲突:', conflicts, '| 位移>4px:', moves.length);
moves.slice(0, 25).forEach(m => console.log('  ', m[1], Math.round(m[0]) + 'px'));

// 门：1号线
const l1 = D.lineStationIds(D.line('1'));
let g1 = 0;
for (const id of l1) {
  if (!fixed[id]) continue;
  const s = stById.get(id);
  if (Math.hypot(fixed[id][0] - s.sx, fixed[id][1] - s.sy) > 4) { console.log('[门1号线偏移]', id); g1++; }
}
console.log('门1号线:', g1 === 0 ? 'PASS' : 'FAIL(' + g1 + ')');

if (conflicts === 0 && g1 === 0) {
  fs.writeFileSync(path.join(ROOT, 'assets', '_ocr-fix.json'), JSON.stringify(fixed, null, 1));
  console.log('写出 _ocr-fix.json');
}
