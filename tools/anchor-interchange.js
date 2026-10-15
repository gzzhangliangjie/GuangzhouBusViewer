// 换乘锚定两阶段修复（用户思路）：
// ① 换乘站 ↔ 艺术图换乘 glyph（站点组的直接子 circle/path = 换乘样式）全局 1:1 贪心锁定
// ② 两换乘锚点间普通站按弦序填（一级子组 circle = 普通站池）
// 门：1号线零改动；重合审计；全部位移打印。
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
global.window = {};
require(path.join(ROOT, 'data', 'metro-data.js'));
const D = new Function('window',
  fs.readFileSync(path.join(ROOT, 'js', 'metro-data.js'), 'utf-8') + ';return MetroData;')(window);

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

// ---------- glyph 双池 ----------
const interGlyphs = [];
const singleGlyphs = [];
{
  let pos = 0;
  while (pos < stSeg.length) {
    const rest = stSeg.slice(pos);
    const gM = /<g\b[^>]*>/.exec(rest);
    const cM = /<circle[^>]*>/.exec(rest);
    const pM = /<path[^>]*>/.exec(rest);
    const opts = [];
    if (gM) opts.push({ m: gM, k: 'g' });
    if (cM) opts.push({ m: cM, k: 'c' });
    if (pM) opts.push({ m: pM, k: 'p' });
    if (!opts.length) break;
    opts.sort((a, b) => a.m.index - b.m.index);
    const { m, k } = opts[0];
    const start = m.index;
    if (k === 'g') {
      let depth = 1, j = start + m[0].length;
      while (depth > 0) {
        const no = stSeg.indexOf('<g', pos + j), nc = stSeg.indexOf('</g>', pos + j);
        if (nc < 0) break;
        if (no >= 0 && no < nc) { depth++; j = no + 2; } else { depth--; j = nc + 4; }
      }
      const chunk = stSeg.slice(pos + start, pos + j);
      for (const cm of chunk.matchAll(/<circle[^>]*?cx="([\d.]+)"[^>]*?cy="([\d.]+)"/g)) {
        singleGlyphs.push({ x: parseFloat(cm[1]), y: parseFloat(cm[2]) });
      }
      pos = pos + j;
    } else if (k === 'c') {
      const t = m[0];
      interGlyphs.push({
        x: parseFloat(/cx="([\d.]+)"/.exec(t)[1]),
        y: parseFloat(/cy="([\d.]+)"/.exec(t)[1])
      });
      pos = pos + start + t.length;
    } else {
      const t = m[0];
      const dm = /d="([^"]+)"/.exec(t);
      if (dm) {
        const nums = [...dm[1].matchAll(/-?[0-9.]+/g)].map(x => parseFloat(x[0]));
        if (nums.length >= 4) {
          const xs = nums.filter((_, i) => i % 2 === 0), ys = nums.filter((_, i) => i % 2 === 1);
          interGlyphs.push({ x: (Math.min(...xs) + Math.max(...xs)) / 2, y: (Math.min(...ys) + Math.max(...ys)) / 2 });
        }
      }
      pos = pos + start + t.length;
    }
  }
}
console.log('换乘池:', interGlyphs.length, '| 普通池:', singleGlyphs.length);

const stById = new Map(D.allStations().map(s => [s.id, s]));
const inters = D.allStations().filter(s => s.lines.length > 1);
const singles = D.allStations().filter(s => s.lines.length === 1);
console.log('数据换乘:', inters.length, '| 数据普通:', singles.length);

// ---------- ① 换乘 1:1 贪心 ----------
const pairs = [];
interGlyphs.forEach((g, gi) => inters.forEach((s, si) => {
  pairs.push({ gi, si, d: Math.hypot(g.x - s.sx, g.y - s.sy) });
}));
pairs.sort((a, b) => a.d - b.d);
const gT = new Set(), sT = new Set();
const anchor = {};
let snap12 = 0, snap25 = 0;
for (const p of pairs) {
  if (gT.has(p.gi) || sT.has(p.si)) continue;
  gT.add(p.gi); sT.add(p.si);
  const s = inters[p.si];
  anchor[s.id] = [interGlyphs[p.gi].x, interGlyphs[p.gi].y];
  if (p.d <= 12) snap12++;
  else if (p.d <= 25) snap25++;
}
console.log('换乘锚定:', Object.keys(anchor).length, '| ≤12px:', snap12, '| 13-25px:', snap25);
const farMoves = Object.entries(anchor).map(([id, c]) => {
  const s = stById.get(id);
  return [Math.hypot(s.sx - c[0], s.sy - c[1]), id, s, c];
}).filter(x => x[0] > 15).sort((a, b) => b[0] - a[0]);
console.log('锚点位移>15px:', farMoves.length);
farMoves.slice(0, 20).forEach(x => console.log('  ', x[1], Math.round(x[2].sx) + ',' + Math.round(x[2].sy), '→', Math.round(x[3][0]) + ',' + Math.round(x[3][1]), Math.round(x[0]) + 'px'));

// 普通池占用表
const pool = singleGlyphs.map(g => ({ x: g.x, y: g.y, used: null }));

// ---------- ② 锚点间普通站弦序填充 ----------
const moves = [];
for (const l of D.allLines()) {
  const ids = D.lineStationIds(l);
  const aIdx = [];
  ids.forEach((id, i) => { if (anchor[id]) aIdx.push(i); });
  if (aIdx.length < 2) continue;
  for (let k = 0; k + 1 < aIdx.length; k++) {
    const i0 = aIdx[k], i1 = aIdx[k + 1];
    const A = anchor[ids[i0]], B = anchor[ids[i1]];
    const vx = B[0] - A[0], vy = B[1] - A[1], L = Math.hypot(vx, vy) || 1;
    const ux = vx / L, uy = vy / L;
    const gap = [];
    for (let i = i0 + 1; i < i1; i++) if (!anchor[ids[i]]) gap.push(ids[i]);
    if (!gap.length) continue;
    const cands = [];
    for (const g of pool) {
      if (g.used) continue;
      const rx = g.x - A[0], ry = g.y - A[1];
      const t = rx * ux + ry * uy;
      const perp = Math.abs(rx * uy - ry * ux);
      if (t >= -25 && t <= L + 25 && perp <= 42) cands.push({ g, t, perp });
    }
    cands.sort((a, b) => a.t - b.t);
    if (cands.length < gap.length) {
      moves.push(['缺', l.ref, gap.join('/') + ' 需' + gap.length + ' 有' + cands.length]);
      continue;
    }
    if (cands.length === gap.length) {
      gap.forEach((id, q) => {
        const g = cands[q].g;
        g.used = id;
        const s = stById.get(id);
        const d = Math.hypot(s.sx - g.x, s.sy - g.y);
        if (d > 4) moves.push([l.ref, id, Math.round(s.sx) + ',' + Math.round(s.sy) + '→' + Math.round(g.x) + ',' + Math.round(g.y), d]);
        anchor[id] = [g.x, g.y];
      });
    } else {
      gap.forEach((id, q) => {
        const tt = gap.length === 1 ? L / 2 : L * (q + 1) / (gap.length + 1);
        let best = null;
        for (const c of cands) {
          if (c.g.used) continue;
          const dd = Math.abs(c.t - tt) + c.perp * 0.4;
          if (!best || dd < best.dd) best = { c, dd };
        }
        if (best) {
          best.c.g.used = id;
          const s = stById.get(id);
          const d = Math.hypot(s.sx - best.c.g.x, s.sy - best.c.g.y);
          if (d > 4) moves.push([l.ref, id, Math.round(s.sx) + ',' + Math.round(s.sy) + '→' + Math.round(best.c.g.x) + ',' + Math.round(best.c.g.y), d]);
          anchor[id] = [best.c.g.x, best.c.g.y];
        }
      });
    }
  }
}

const unresolved = singles.filter(s => !anchor[s.id]);
console.log('端点段未覆盖普通站:', unresolved.length, unresolved.slice(0, 10).map(s => s.id).join(',') + (unresolved.length > 10 ? '…' : ''));

// ---------- 门 ----------
let g1 = 0;
for (const id of D.lineStationIds(D.line('1'))) {
  const a = anchor[id];
  const s = stById.get(id);
  if (a && Math.hypot(a[0] - s.sx, a[1] - s.sy) > 4) { console.log('[门1号线]', id); g1++; }
}
const final = {};
for (const s of D.allStations()) final[s.id] = anchor[s.id] || [s.sx, s.sy];
const all = Object.keys(final);
let dup = 0;
for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) {
  if (Math.hypot(final[all[i]][0] - final[all[j]][0], final[all[i]][1] - final[all[j]][1]) < 6) {
    dup++;
    if (dup <= 10) console.log('[重合]', all[i], all[j]);
  }
}
console.log('门1号线:', g1 === 0 ? 'PASS' : 'FAIL', '| 重合对:', dup);
console.log('普通站位移数:', moves.filter(m => m[0] !== '缺').length, '| 缺口:', moves.filter(m => m[0] === '缺').length);
moves.slice(0, 30).forEach(m => console.log('  ', m[0] === '缺' ? '[缺]' : '[' + m[0] + ']', m[1], m[2] || '', m[3] ? Math.round(m[3]) + 'px' : ''));

if (g1 === 0) {
  fs.writeFileSync(path.join(ROOT, 'assets', '_inter-fix.json'), JSON.stringify(final, null, 1));
  console.log('写出 _inter-fix.json');
}
