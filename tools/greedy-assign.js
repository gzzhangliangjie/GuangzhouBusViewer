// 逐线贪心站圆分配：按线置信度顺序，已分配的站跳过，
// 未分配的找最近未占圆，或邻站圆之间的圆
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
console.log('glyph池:', glyphs.length);

const stById = new Map(D.allStations().map(s => [s.id, s]));
const assignment = {};   // stationId -> [x, y]
const raw = fs.readFileSync(path.join(ROOT, 'data', 'metro-data.js'), 'utf-8');
const data = JSON.parse(raw.substring(raw.indexOf('{'), raw.lastIndexOf(';')));

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

// 线处理顺序：锚站多的先（1号线最多已验证站）
const lineOrder = ['1', '6', '5', '2', '8', '3', '4', '7', 'GF', 'APM', '10', '13', '14', '21', '18', '11', '22', '12'];

const moves = [];
for (const ref of lineOrder) {
  const l = D.line(ref);
  if (!l) continue;
  const ids = D.lineStationIds(l);
  const spec = B.lines[ref];
  if (!spec) continue;

  // 该线的候选圆：距线 ≤15px 的未占圆
  const lineCircles = glyphs.filter(g => !g.used && distToLine(g.x, g.y, ref) <= 15);

  for (let pass = 0; pass < 3; pass++) {   // 多轮：已分配的邻站帮未分配的
    let assignedThisPass = 0;
    for (let i = 0; i < ids.length; i++) {
      const id = ids[i];
      if (assignment[id]) continue;   // 已分配

      const s = stById.get(id);
      // 策略A：当前坐标附近的未占圆（≤30px 且在线上）
      let best = null, bd = 30;
      for (const g of lineCircles) {
        if (g.used) continue;
        const dd = Math.hypot(g.x - s.sx, g.y - s.sy);
        if (dd < bd) { bd = dd; best = g; }
      }

      // 策略B：如果A没找到，看邻站的圆之间的圆
      if (!best) {
        const prevAssigned = i > 0 ? assignment[ids[i-1]] : null;
        const nextAssigned = i < ids.length - 1 ? assignment[ids[i+1]] : null;
        let ex, ey;
        if (prevAssigned && nextAssigned) {
          ex = (prevAssigned[0] + nextAssigned[0]) / 2;
          ey = (prevAssigned[1] + nextAssigned[1]) / 2;
        } else if (prevAssigned) {
          const dirx = prevAssigned[0] - s.sx, diry = prevAssigned[1] - s.sy;
          const L = Math.hypot(dirx, diry) || 1;
          ex = prevAssigned[0] + dirx / L * 54;
          ey = prevAssigned[1] + diry / L * 54;
        } else if (nextAssigned) {
          const dirx = nextAssigned[0] - s.sx, diry = nextAssigned[1] - s.sy;
          const L = Math.hypot(dirx, diry) || 1;
          ex = nextAssigned[0] - dirx / L * 54;
          ey = nextAssigned[1] - diry / L * 54;
        } else continue;

        bd = 80;
        for (const g of lineCircles) {
          if (g.used) continue;
          const dd = Math.hypot(g.x - ex, g.y - ey);
          if (dd < bd && dd > 5) { bd = dd; best = g; }
        }
      }

      if (best) {
        best.used = id;
        assignment[id] = [best.x, best.y];
        assignedThisPass++;
        const dd = Math.hypot(s.sx - best.x, s.sy - best.y);
        if (dd > 4) moves.push([ref, id, Math.round(s.sx) + ',' + Math.round(s.sy), Math.round(best.x) + ',' + Math.round(best.y), Math.round(dd)]);
      }
    }
    if (!assignedThisPass) break;
  }
  const assigned = ids.filter(id => assignment[id]).length;
  console.log(ref.padEnd(4), assigned + '/' + ids.length, assigned === ids.length ? '✓' : '缺' + (ids.length - assigned));
}

// 应用
let applied = 0;
for (const st of data.stations) {
  if (assignment[st.id] && Math.hypot(assignment[st.id][0] - st.sx, assignment[st.id][1] - st.sy) > 4) {
    st.sx = assignment[st.id][0];
    st.sy = assignment[st.id][1];
    applied++;
  }
}

// 门
let g1 = 0;
for (const id of D.lineStationIds(D.line('1'))) {
  const s = stById.get(id);
  const a = assignment[id];
  if (a && Math.hypot(a[0] - s.sx, a[1] - s.sy) > 4) g1++;
}

// 重合审计
let dup = 0;
for (let i = 0; i < data.stations.length; i++) for (let j = i + 1; j < data.stations.length; j++) {
  const a = data.stations[i], b = data.stations[j];
  if (Math.hypot(a.sx-b.sx, a.sy-b.sy) < 6) dup++;
}

console.log('\n门1:', g1 === 0 ? 'PASS' : 'FAIL(' + g1 + ')', '| 应用:', applied, '| 重合:', dup);
moves.sort((a, b) => b[4] - a[4]);
console.log('位移 top15:');
moves.slice(0, 15).forEach(m => console.log('  [' + m[0] + ']', m[1], m[2], '→', m[3], m[4] + 'px'));

if (g1 === 0) {
  fs.writeFileSync(path.join(ROOT, 'data', 'metro-data.js'), 'window.METRO_DATA = ' + JSON.stringify(data) + ';\n');
  console.log('已写回 metro-data.js');
}
