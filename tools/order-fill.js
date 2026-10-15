// 站序重排：换乘锚定（交叉点/已验证位置）→ 区间内站圆按序号顺序分配
// 每条线：先锁定换乘站位置 → 相邻锚点之间的站圆按空间投影排序 → 依序分配
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

for (const l of D.allLines()) {
  const ids = D.lineStationIds(l);
  const spec = B.lines[l.ref];
  if (!spec) continue;

  // ① 找锚站：换乘站且坐标在本线路径上 ≤15px
  const polys = spec.polys;
  const distToPath = (px, py) => {
    let bd = 1e9;
    for (const poly of polys) for (let k = 0; k + 1 < poly.length; k++) {
      const [x1,y1] = poly[k], [x2,y2] = poly[k+1];
      const vx=x2-x1,vy=y2-y1,L2=vx*vx+vy*vy||1;
      const t = Math.max(0, Math.min(1, ((px-x1)*vx+(py-y1)*vy)/L2));
      bd = Math.min(bd, Math.hypot(px-(x1+t*vx), py-(y1+t*vy)));
    }
    return bd;
  };

  const anchors = [];   // {i, id, xy}
  ids.forEach((id, i) => {
    const s = stById.get(id);
    const dPath = distToPath(s.sx, s.sy);
    if (dPath <= 15) anchors.push({ i, id, xy: [s.sx, s.sy] });
  });
  if (anchors.length < 2) { console.log(l.ref + ': 锚站不足(' + anchors.length + ')'); continue; }

  // ② 锚站占用 glyph
  for (const g of glyphs) {
    if (g.used) continue;
    for (const a of anchors) {
      if (Math.hypot(g.x - a.xy[0], g.y - a.xy[1]) <= 8) { g.used = a.id; break; }
    }
  }

  // ③ 相邻锚点区间：站圆按空间投影排序 → 依序分配
  for (let k = 0; k + 1 < anchors.length; k++) {
    const A = anchors[k], Bn = anchors[k + 1];
    const gapIds = [];
    for (let i = A.i + 1; i < Bn.i; i++) gapIds.push(ids[i]);
    if (!gapIds.length) continue;

    // 两锚连线方向
    const vx = Bn.xy[0] - A.xy[0], vy = Bn.xy[1] - A.xy[1];
    const L = Math.hypot(vx, vy) || 1;
    const ux = vx / L, uy = vy / L;
    const mx = (A.xy[0] + Bn.xy[0]) / 2, my = (A.xy[1] + Bn.xy[1]) / 2;
    const halfW = Math.abs(vx) / 2 + 60, halfH = Math.abs(vy) / 2 + 60;

    // 找区间内未占用 glyph
    const cands = [];
    for (const g of glyphs) {
      if (g.used) continue;
      const rx = g.x - mx, ry = g.y - my;
      if (Math.abs(rx) > halfW || Math.abs(ry) > halfH) continue;
      const t = (g.x - A.xy[0]) * ux + (g.y - A.xy[1]) * uy;   // 沿锚连线投影
      const perp = Math.abs((g.x - A.xy[0]) * uy - (g.y - A.xy[1]) * ux);
      if (t >= 10 && t <= L - 10 && perp <= 40) cands.push({ g, t });
    }
    cands.sort((a, b) => a.t - b.t);

    if (cands.length === gapIds.length) {
      // 完美匹配：按序分配
      gapIds.forEach((id, q) => {
        const g = cands[q].g;
        g.used = id;
        const s = stById.get(id);
        const d = Math.hypot(s.sx - g.x, s.sy - g.y);
        if (d > 4) moves.push([l.ref, id, Math.round(s.sx) + ',' + Math.round(s.sy), Math.round(g.x) + ',' + Math.round(g.y), Math.round(d)]);
        XY[id] = [g.x, g.y];
      });
    } else if (cands.length > gapIds.length) {
      // glyph 多于站：等分投影位置选最近
      gapIds.forEach((id, q) => {
        const tt = gapIds.length === 1 ? L / 2 : L * (q + 1) / (gapIds.length + 1);
        let best = null;
        for (const c of cands) {
          if (c.g.used) continue;
          const dd = Math.abs(c.t - tt);
          if (!best || dd < best.dd) best = { c, dd };
        }
        if (best) {
          best.c.g.used = id;
          const s = stById.get(id);
          const d = Math.hypot(s.sx - best.c.g.x, s.sy - best.c.g.y);
          if (d > 4) moves.push([l.ref, id, Math.round(s.sx) + ',' + Math.round(s.sy), Math.round(best.c.g.x) + ',' + Math.round(best.c.g.y), Math.round(d)]);
          XY[id] = [best.c.g.x, best.c.g.y];
        }
      });
    } else {
      // glyph 少于站：跳过（保持现状）
      // console.log(l.ref + ': ' + A.id + '→' + Bn.id + ' 缺glyph ' + (gapIds.length - cands.length));
    }
  }
}

// ---------- 门 ----------
let g1 = 0;
for (const id of D.lineStationIds(D.line('1'))) {
  const s = stById.get(id);
  if (Math.hypot(XY[id][0] - s.sx, XY[id][1] - s.sy) > 4) { console.log('[门1]', id); g1++; }
}
const all = Object.keys(XY);
let dup = 0;
for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) {
  if (Math.hypot(XY[all[i]][0] - XY[all[j]][0], XY[all[i]][1] - XY[all[j]][1]) < 6) dup++;
}
console.log('门1:', g1 === 0 ? 'PASS' : 'FAIL', '| 位移:', moves.length, '| 重合:', dup);
moves.sort((a, b) => b[4] - a[4]);
moves.slice(0, 20).forEach(m => console.log('  [' + m[0] + ']', m[1], m[2], '→', m[3], m[4] + 'px'));

if (g1 === 0) {
  const fix = {};
  for (const m of moves) fix[m[1]] = XY[m[1]];
  fs.writeFileSync(path.join(ROOT, 'assets', '_order-fix.json'), JSON.stringify(fix, null, 1));
  console.log('写出 _order-fix.json:', Object.keys(fix).length, '站');
}
