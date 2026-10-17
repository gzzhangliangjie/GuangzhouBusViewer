// 全局最优站圆分配：最小费用贪心+多轮修正
// 不同于逐线贪心，这里同时考虑所有线的约束
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
for (const m of stSeg.matchAll(/<circle[^>]*?cx="([\d.]+)"[^>]*?cy="([\d.]+)"/g)) glyphs.push({ x: parseFloat(m[1]), y: parseFloat(m[2]), used: null });
for (const m of stSeg.matchAll(/<path[^>]*?d="([^"]+)"/g)) {
  const nums = [...m[1].matchAll(/-?[0-9.]+/g)].map(x => parseFloat(x[0]));
  if (nums.length >= 4) {
    const xs = nums.filter((_, i) => i % 2 === 0), ys = nums.filter((_, i) => i % 2 === 1);
    glyphs.push({ x: (Math.min(...xs) + Math.max(...xs)) / 2, y: (Math.min(...ys) + Math.max(...ys)) / 2, used: null });
  }
}
console.log('glyph池:', glyphs.length, '| 站数:', D.allStations().length);

function distToLine(px, py, ref) {
  const spec = B.lines[ref]; if (!spec) return 1e9;
  let bd = 1e9;
  for (const poly of spec.polys) for (let k = 0; k + 1 < poly.length; k++) {
    const [x1,y1] = poly[k], [x2,y2] = poly[k+1];
    const vx=x2-x1,vy=y2-y1,L2=vx*vx+vy*vy||1;
    const t = Math.max(0, Math.min(1, ((px-x1)*vx+(py-y1)*vy)/L2));
    bd = Math.min(bd, Math.hypot(px-(x1+t*vx), py-(y1+t*vy)));
  }
  return bd;
}

const raw = fs.readFileSync(path.join(ROOT, 'data', 'metro-data.js'), 'utf-8');
const data = JSON.parse(raw.substring(raw.indexOf('{'), raw.lastIndexOf(';')));
const stById = new Map(D.allStations().map(s => [s.id, s]));
const l1set = new Set(D.lineStationIds(D.line('1')));

// ========== 全局分配 ==========
// 步骤1：所有站按置信度排序（距所有所属线路径的最小距离）
const stationScores = [];
for (const st of data.stations) {
  let bestDist = 1e9;
  for (const ref of st.lines) {
    bestDist = Math.min(bestDist, distToLine(st.sx, st.sy, ref));
  }
  stationScores.push({ id: st.id, score: bestDist, lines: st.lines });
}
stationScores.sort((a, b) => a.score - b.score);   // 好的先分

// 步骤2：按置信度顺序，每站选全局最优圆（考虑所有线路径距离+与邻站一致性）
const assignment = {};
const glyphUsed = new Array(glyphs.length).fill(null);

for (const { id, lines } of stationScores) {
  if (l1set.has(id)) {
    // 1号线站锁原位
    const st = stById.get(id);
    const gi = glyphs.findIndex(g => Math.hypot(g.x - st.sx, g.y - st.sy) <= 6 && !glyphUsed[glyphs.indexOf(g)]);
    if (gi >= 0) { glyphUsed[gi] = id; assignment[id] = [glyphs[gi].x, glyphs[gi].y]; }
    else assignment[id] = [st.sx, st.sy];
    continue;
  }

  const st = stById.get(id);
  // 费用函数 = 到当前距离*0.4 + 到最远线路径距离*2.0 + 邻站不匹配惩罚
  let bestGi = -1, bestCost = 1e18;
  for (let gi = 0; gi < glyphs.length; gi++) {
    if (glyphUsed[gi]) continue;
    const g = glyphs[gi];
    const dCurrent = Math.hypot(g.x - st.sx, g.y - st.sy);
    if (dCurrent > 300) continue;
    const dLines = Math.max(...lines.map(ref => distToLine(g.x, g.y, ref)));
    if (dLines > 30) continue;

    // 邻站一致性：检查该站的所有线上的邻站是否已分配
    let neighborPenalty = 0;
    for (const ref of lines) {
      const l = D.line(ref);
      const idx = l.stations.indexOf(id);
      if (idx < 0) continue;
      for (const nb of [l.stations[idx-1], l.stations[idx+1]]) {
        if (!nb) continue;
        const nbPos = assignment[nb];
        if (nbPos) {
          const d = Math.hypot(g.x - nbPos[0], g.y - nbPos[1]);
          if (d > 150) neighborPenalty += (d - 150) * 2;
        }
      }
    }

    const cost = dCurrent * 0.4 + dLines * 2.0 + neighborPenalty;
    if (cost < bestCost) { bestCost = cost; bestGi = gi; }
  }

  if (bestGi >= 0) {
    glyphUsed[bestGi] = id;
    assignment[id] = [glyphs[bestGi].x, glyphs[bestGi].y];
  }
  // 找不到圆的站保持原位
  if (!assignment[id]) assignment[id] = [st.sx, st.sy];
}

// 步骤3：多轮修正——检查邻站距离异常并重新分配
for (let round = 0; round < 5; round++) {
  let changes = 0;
  for (const { id, lines } of stationScores) {
    if (l1set.has(id)) continue;
    const pos = assignment[id];
    // 检查每条线上与邻站的距离
    let badNeighbor = false;
    for (const ref of lines) {
      const l = D.line(ref);
      const idx = l.stations.indexOf(id);
      if (idx < 0) continue;
      for (const nb of [l.stations[idx-1], l.stations[idx+1]]) {
        if (!nb || !assignment[nb]) continue;
        const d = Math.hypot(pos[0] - assignment[nb][0], pos[1] - assignment[nb][1]);
        if (d > 200 || d < 8) { badNeighbor = true; break; }
      }
      if (badNeighbor) break;
    }
    if (!badNeighbor) continue;

    // 尝试换到更好的圆
    const st = stById.get(id);
    // 释放当前圆
    const curGi = glyphs.findIndex((g, i) => glyphUsed[i] === id);
    if (curGi >= 0) glyphUsed[curGi] = null;

    let bestGi = -1, bestCost = 1e18;
    for (let gi = 0; gi < glyphs.length; gi++) {
      if (glyphUsed[gi]) continue;
      const g = glyphs[gi];
      const dLines = Math.max(...lines.map(ref => distToLine(g.x, g.y, ref)));
      if (dLines > 25) continue;
      const dCurrent = Math.hypot(g.x - st.sx, g.y - st.sy);
      if (dCurrent > 350) continue;
      let neighborPenalty = 0;
      for (const ref of lines) {
        const l = D.line(ref);
        const idx = l.stations.indexOf(id);
        if (idx < 0) continue;
        for (const nb of [l.stations[idx-1], l.stations[idx+1]]) {
          if (!nb || !assignment[nb]) continue;
          const d = Math.hypot(g.x - assignment[nb][0], g.y - assignment[nb][1]);
          if (d > 150) neighborPenalty += (d - 150) * 2;
          if (d < 8) neighborPenalty += 100;
        }
      }
      const cost = dCurrent * 0.3 + dLines * 2.0 + neighborPenalty;
      if (cost < bestCost) { bestCost = cost; bestGi = gi; }
    }
    if (bestGi >= 0) {
      glyphUsed[bestGi] = id;
      assignment[id] = [glyphs[bestGi].x, glyphs[bestGi].y];
      changes++;
    } else if (curGi >= 0) {
      glyphUsed[curGi] = id;   // 换不了就恢复
    }
  }
  if (!changes) break;
  console.log('修正轮' + (round + 1) + ': ' + changes + '站调整');
}

// 应用
let applied = 0;
for (const st of data.stations) {
  const a = assignment[st.id];
  if (a && Math.hypot(a[0] - st.sx, a[1] - st.sy) > 4) {
    st.sx = a[0]; st.sy = a[1]; applied++;
  }
}

// 清残余重合
for (let round = 0; round < 5; round++) {
  let has = false;
  for (let i = 0; i < data.stations.length; i++) for (let j = i + 1; j < data.stations.length; j++) {
    const a = data.stations[i], b = data.stations[j];
    if (Math.hypot(a.sx-b.sx, a.sy-b.sy) < 8) {
      has = true;
      const aD = Math.min(...a.lines.map(r => distToLine(a.sx, a.sy, r)));
      const bD = Math.min(...b.lines.map(r => distToLine(b.sx, b.sy, r)));
      const go = aD <= bD ? b : a;
      const ang = ((go.id.charCodeAt(0) * 13 + round * 43) % 360) * Math.PI / 180;
      go.sx += Math.cos(ang) * 40; go.sy += Math.sin(ang) * 40;
    }
  }
  if (!has) break;
}

fs.writeFileSync(path.join(ROOT, 'data', 'metro-data.js'), 'window.METRO_DATA = ' + JSON.stringify(data) + ';\n');

// 审计
let dup = 0, bad = 0, jumpy = 0;
for (let i = 0; i < data.stations.length; i++) for (let j = i + 1; j < data.stations.length; j++) {
  if (Math.hypot(data.stations[i].sx-data.stations[j].sx, data.stations[i].sy-data.stations[j].sy) < 8) dup++;
}
for (const l of D.allLines()) {
  const lids = D.lineStationIds(l);
  for (const id of lids) {
    const s = data.stations.find(x => x.id === id);
    if (distToLine(s.sx, s.sy, l.ref) > 25) bad++;
  }
  for (let i = 0; i + 1 < lids.length; i++) {
    const a = data.stations.find(x => x.id === lids[i]);
    const b = data.stations.find(x => x.id === lids[i+1]);
    if (Math.hypot(a.sx-b.sx, a.sy-b.sy) > 200) jumpy++;
  }
}
let g1 = 0;
for (const id of l1set) {
  const st = data.stations.find(s => s.id === id);
  const orig = stById.get(id);
  if (Math.hypot(st.sx - orig.sx, st.sy - orig.sy) > 4) g1++;
}
console.log('\n门1:', g1 === 0 ? 'PASS' : 'FAIL', '| 位移:', applied, '| 重合:', dup, '| 距线>25px:', bad, '| 跳>200px:', jumpy);
