// 站名矢量解码：站名组的每个字是独立 path，同字同形（d 属性平移归一后可做指纹）。
// 用已知正确站（1号线16站+验证过的站）的名字组建 字指纹→汉字 表，识别全部站名 → 配对站圆 → 全量坐标修复。
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
global.window = {};
require(path.join(ROOT, 'data', 'metro-data.js'));
const D = new Function('window',
  fs.readFileSync(path.join(ROOT, 'js', 'metro-data.js'), 'utf-8') + ';return MetroData;')(window);
const svg = fs.readFileSync(path.join(ROOT, 'assets', 'tim-gzfmetro.svg'), 'utf-8');

// ---------- ① 站名组的 path 元素 → 按字聚类 ----------
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
const nm = span('站名');
// 每个 path: d 的全部数值 → 平移归一（首点为原点）→ 指纹
const charPaths = [];
for (const m of nm.matchAll(/<path[^>]*?d="([^"]+)"/g)) {
  const nums = [...m[1].matchAll(/-?[0-9.]+/g)].map(x => parseFloat(x[0]));
  if (nums.length < 4) continue;
  const ox = nums[0], oy = nums[1];
  const rel = nums.map((v, i) => i % 2 === 0 ? v - ox : v - oy);
  charPaths.push({
    x: ox, y: oy,
    w: Math.max(...rel.filter((_, i) => i % 2 === 0)) - Math.min(...rel.filter((_, i) => i % 2 === 0)),
    h: Math.max(...rel.filter((_, i) => i % 2 === 1)) - Math.min(...rel.filter((_, i) => i % 2 === 1)),
    fp: rel.map(v => Math.round(v * 10) / 10).join(',')
  });
}
console.log('站名 path 数（字）:', charPaths.length);

// 字聚类成词：x 距 < 16px 且 y 差 < 4px（横向词）；竖排词 y 距 < 16 且 x 差 < 4
const used = new Set();
const words = [];
for (const cp of charPaths) {
  if (used.has(cp)) continue;
  // 找同行的邻居（横排）
  const row = [cp];
  used.add(cp);
  let moved = true;
  while (moved) {
    moved = false;
    for (const q of charPaths) {
      if (used.has(q)) continue;
      const last = row[row.length - 1];
      if (Math.abs(q.y - last.y) < 5 && q.x > last.x - 2 && q.x - last.x < 18) {
        row.push(q); used.add(q); moved = true;
      }
      const first = row[0];
      if (Math.abs(q.y - first.y) < 5 && first.x - q.x > -2 && first.x - q.x < 18) {
        row.unshift(q); used.add(q); moved = true;
      }
    }
  }
  row.sort((a, b) => a.x - b.x);
  const xs = row.map(c => c.x), ys = row.map(c => c.y);
  words.push({
    chars: row,
    cx: (Math.min(...xs) + Math.max(...xs)) / 2,
    cy: (Math.min(...ys) + Math.max(...ys)) / 2,
    n: row.length
  });
}
console.log('聚类词组数:', words.length);

// ---------- ② 字指纹表（用全部数据站的已知名 + 当前坐标就近原则建表） ----------
// 对每个词组：找当前坐标 60px 内的数据站，站名字数==词组字数 且 词组中心在站坐标附近 → 全字配对入表
const stById = new Map(D.allStations().map(s => [s.id, s]));
const all = D.allStations();
const fp2char = new Map();   // fingerprint -> 汉字
const conflict = [];
for (const w of words) {
  const cands = all.filter(s => Math.hypot(s.sx - w.cx, s.sy - w.cy) <= 55 && s.zh.length === w.n);
  if (cands.length !== 1) continue;
  const st = cands[0];
  w.chars.forEach((c, i) => {
    const ch = st.zh[i];
    if (fp2char.has(c.fp) && fp2char.get(c.fp) !== ch) conflict.push(c.fp.slice(0, 30) + ' ' + fp2char.get(c.fp) + '≠' + ch);
    else fp2char.set(c.fp, ch);
  });
}
console.log('字指纹表:', fp2char.size, '| 冲突:', conflict.length);
conflict.slice(0, 5).forEach(c => console.log('  ?', c));

// ---------- ③ 解码全部词组 → 站名 → 站圆 ----------
// 站圆 = 站点组的全部 circle（全局正则，不依赖层级遍历）
const circles = [];
for (const m of span('站点').matchAll(/<circle[^>]*?cx="([\d.]+)"[^>]*?cy="([\d.]+)"/g)) {
  circles.push([parseFloat(m[1]), parseFloat(m[2])]);
}
console.log('站圆:', circles.length);

const decoded = {};
const undecoded = [];
for (const w of words) {
  const name = w.chars.map(c => fp2char.get(c.fp)).join('');
  if (!name || name.includes('undefined')) { undecoded.push(w); continue; }
  // 词组中心 → 最近站圆 ≤35px
  let best = null, bd = 35;
  for (const c of circles) {
    const d = Math.hypot(c[0] - w.cx, c[1] - w.cy);
    if (d < bd) { bd = d; best = c; }
  }
  if (!best) { undecoded.push(w); continue; }
  if (decoded[name] && Math.hypot(decoded[name][0] - best[0], decoded[name][1] - best[1]) > 3) {
    console.log('[重名]', name, decoded[name], best);
  }
  decoded[name] = best;
}
console.log('解码站名:', Object.keys(decoded).length, '| 未解码词组:', undecoded.length);

// 与数据对账
const inData = Object.keys(decoded).filter(n => stById.has(n));
const notInData = Object.keys(decoded).filter(n => !stById.has(n));
const missing = all.map(s => s.id).filter(id => !decoded[id]);
console.log('数据命中:', inData.length, '| 非站名(图例等):', notInData.length, '| 数据站缺:', missing.length);
console.log('缺的站:', missing.join(',') || '无');
if (notInData.length) console.log('非站名样例:', notInData.slice(0, 8).join(','));

// ---------- 修复表：站名 → 站圆 ----------
const fix = {};
let moved = 0;
for (const id of inData) {
  const s = stById.get(id);
  fix[id] = decoded[id];
  if (Math.hypot(s.sx - decoded[id][0], s.sy - decoded[id][1]) > 4) moved++;
}
console.log('坐标将移动的站:', moved);

// 门：1号线
let g1 = 0;
for (const id of D.lineStationIds(D.line('1'))) {
  if (!fix[id]) { console.log('[门1缺失]', id); g1++; continue; }
  const s = stById.get(id);
  if (Math.hypot(fix[id][0] - s.sx, fix[id][1] - s.sy) > 4) { console.log('[门1偏移]', id); g1++; }
}
console.log('门1号线:', g1 === 0 ? 'PASS' : 'FAIL(' + g1 + ')');

if (g1 === 0 && missing.length === 0) {
  fs.writeFileSync(path.join(ROOT, 'assets', '_glyph-fix.json'), JSON.stringify(fix, null, 1));
  console.log('写出 _glyph-fix.json:', Object.keys(fix).length, '站');
} else {
  // 即使有缺也写出（人工补缺）
  fs.writeFileSync(path.join(ROOT, 'assets', '_glyph-fix.json'), JSON.stringify(fix, null, 1));
  console.log('写出（含缺口）_glyph-fix.json:', Object.keys(fix).length, '站');
}
