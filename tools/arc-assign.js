// 用有序链做站序分配：沿链弧长排序站圆，一一对应站序
// 适用于链质量好的线（1, 5, 6, 10）
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
global.window = {};
require(path.join(ROOT, 'data', 'metro-data.js'));
const D = new Function('window',
  fs.readFileSync(path.join(ROOT, 'js', 'metro-data.js'), 'utf-8') + ';return MetroData;')(window);

// 有序链
const chains = JSON.parse(fs.readFileSync(path.join(ROOT, 'assets', 'tim-vector-ordered.json'), 'utf-8'));

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
const moves = [];

// 只处理链质量好的线
const goodLines = ['1', '5', '6', '10'];
for (const ref of goodLines) {
  const chain = chains[ref];
  if (!chain || chain.length < 5) { console.log(ref + ': 链不足'); continue; }
  const ids = D.lineStationIds(D.line(ref));

  // ① 站在链上的弧长
  const arcs = [];   // 累积弧长
  arcs.push(0);
  for (let k = 1; k < chain.length; k++) {
    arcs.push(arcs[k - 1] + Math.hypot(chain[k][0] - chain[k-1][0], chain[k][1] - chain[k-1][1]));
  }

  // ② 每个站圆到链的投影弧长
  const proj = [];
  for (let gi = 0; gi < glyphs.length; gi++) {
    const g = glyphs[gi];
    let bd = 15, barc = 0;
    for (let k = 0; k + 1 < chain.length; k++) {
      const [x1,y1] = chain[k], [x2,y2] = chain[k+1];
      const vx=x2-x1,vy=y2-y1,L2=vx*vx+vy*vy||1;
      const t = Math.max(0, Math.min(1, ((g.x-x1)*vx+(g.y-y1)*vy)/L2));
      const dd = Math.hypot(g.x-(x1+t*vx), g.y-(y1+t*vy));
      if (dd < bd) { bd = dd; barc = arcs[k] + t * (arcs[k+1] - arcs[k]); }
    }
    if (bd <= 15) proj.push({ gi, arc: barc, d: bd });
  }
  proj.sort((a, b) => a.arc - b.arc);
  // 去重（弧长相近的取最近的）
  const deduped = [];
  for (const p of proj) {
    const last = deduped[deduped.length - 1];
    if (last && Math.abs(last.arc - p.arc) < 3) {
      if (p.d < last.d) deduped[deduped.length - 1] = p;
    } else deduped.push(p);
  }

  console.log(ref + '号线: 链' + chain.length + '点 弧长' + Math.round(arcs[arcs.length-1]) + 'px, 投影glyph ' + deduped.length + '/站' + ids.length);

  if (deduped.length === ids.length) {
    // 完美匹配
    ids.forEach((id, q) => {
      const g = glyphs[deduped[q].gi];
      g.used = id;
      const s = stById.get(id);
      const d = Math.hypot(s.sx - g.x, s.sy - g.y);
      if (d > 4) moves.push([ref, id, Math.round(s.sx) + ',' + Math.round(s.sy), Math.round(g.x) + ',' + Math.round(g.y), Math.round(d)]);
      XY[id] = [g.x, g.y];
    });
    console.log('  ✓ 一一对应');
  } else if (deduped.length > ids.length) {
    // glyph 多于站：按弧长等分选取
    const step = deduped.length / ids.length;
    ids.forEach((id, q) => {
      const idx = Math.floor(q * step + step / 2);
      const g = glyphs[deduped[Math.min(idx, deduped.length - 1)].gi];
      if (g.used) return;
      g.used = id;
      const s = stById.get(id);
      const d = Math.hypot(s.sx - g.x, s.sy - g.y);
      if (d > 4) moves.push([ref, id, Math.round(s.sx) + ',' + Math.round(s.sy), Math.round(g.x) + ',' + Math.round(g.y), Math.round(d)]);
      XY[id] = [g.x, g.y];
    });
    console.log('  ≈ glyph多，等分选取');
  } else {
    console.log('  ✗ glyph少 ' + deduped.length + '<' + ids.length);
  }
}

// 应用
const raw = fs.readFileSync(path.join(ROOT, 'data', 'metro-data.js'), 'utf-8');
const data = JSON.parse(raw.substring(raw.indexOf('{'), raw.lastIndexOf(';')));
let applied = 0;
for (const st of data.stations) {
  if (XY[st.id] && Math.hypot(XY[st.id][0] - st.sx, XY[st.id][1] - st.sy) > 4) {
    st.sx = XY[st.id][0]; st.sy = XY[st.id][1];
    applied++;
  }
}
fs.writeFileSync(path.join(ROOT, 'data', 'metro-data.js'), 'window.METRO_DATA = ' + JSON.stringify(data) + ';\n');

// 重合审计
let dup = 0;
for (let i = 0; i < data.stations.length; i++) for (let j = i + 1; j < data.stations.length; j++) {
  const a = data.stations[i], b = data.stations[j];
  if (Math.hypot(a.sx-b.sx, a.sy-b.sy) < 6) dup++;
}
console.log('\n应用:', applied, '站 | 重合:', dup);
moves.sort((a, b) => b[4] - a[4]);
console.log('位移 top10:');
moves.slice(0, 10).forEach(m => console.log('  [' + m[0] + ']', m[1], m[2], '→', m[3], m[4] + 'px'));
