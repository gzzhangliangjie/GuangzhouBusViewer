// 均匀分布：每条线的站均匀放在SVG画线路径上（跟官图一样干净）
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
global.window = {};
require(path.join(ROOT, 'data', 'metro-data.js'));
const D = new Function('window', fs.readFileSync(path.join(ROOT, 'js', 'metro-data.js'), 'utf-8') + ';return MetroData;')(window);
const raw = fs.readFileSync(path.join(ROOT, 'data', 'metro-data.js'), 'utf-8');
const data = JSON.parse(raw.substring(raw.indexOf('{'), raw.lastIndexOf(';')));
const svg = fs.readFileSync(path.join(ROOT, 'assets', 'tim-gzfmetro.svg'), 'utf-8');

const GIDS = {'1':'_x31_','2':'_x32_','3':'_x33_','4':'_x34_','5':'_x35_','6':'_x36_','7':'_x37_','8':'_x38_','9':'_x39__3_','10':'_x31_0_1_','11':'_x31_1','12':'_x31_2','13':'_x31_3','14':'_x31_4','18':'_x31_8','21':'_x32_1','22':'_x32_2','GF':'GF','APM':'APM_3_'};

function extractSegs(gid) {
  const gi = svg.indexOf('id="' + gid + '"');
  if (gi < 0) return [];
  let i = svg.indexOf('>', gi) + 1, d = 1, j = i;
  while (d > 0) { const no = svg.indexOf('<g', j), nc = svg.indexOf('</g>', j); if (nc < 0) break; if (no >= 0 && no < nc) { d++; j = no + 2; } else { d--; j = nc + 4; } }
  const seg = svg.slice(i, j - 4);
  const out = [];
  for (const m of seg.matchAll(/<line[^>]*?x1="([\d.]+)"[^>]*?y1="([\d.]+)"[^>]*?x2="([\d.]+)"[^>]*?y2="([\d.]+)"/g))
    out.push([[+m[1], +m[2]], [+m[3], +m[4]]]);
  for (const m of seg.matchAll(/<path[^>]*?d="M([\d.-]+),([\d.-]+)([^"]*)"/g)) {
    let cx = +m[1], cy = +m[2];
    const nums = [];
    let tok = '';
    for (const ch of m[3]) { if (/[-0-9.]/.test(ch)) tok += ch; else if (tok) { nums.push(+tok); tok = ''; } }
    if (tok) nums.push(+tok);
    const pts = [[cx, cy]];
    for (let k = 4; k + 1 < nums.length; k += 6) { cx += nums[k]; cy += nums[k+1]; pts.push([cx, cy]); }
    if (pts.length >= 2) out.push(pts);
  }
  return out;
}

function chain(segs, maxGap = 30) {
  if (!segs.length) return [];
  const pool = segs.map(s => s.slice());
  pool.sort((a, b) => a[0][0] + a[0][1] - b[0][0] - b[0][1]);
  const chain = pool.shift().slice();
  let grew = true;
  while (grew) {
    grew = false;
    let changed = true;
    while (changed) {
      changed = false;
      const head = chain[chain.length - 1];
      let bi = -1, rev = false, bd = maxGap;
      pool.forEach((s, k) => {
        const dA = Math.hypot(s[0][0]-head[0], s[0][1]-head[1]);
        const dB = Math.hypot(s[s.length-1][0]-head[0], s[s.length-1][1]-head[1]);
        if (Math.min(dA,dB) < bd) { bd = Math.min(dA,dB); bi = k; rev = dB < dA; }
      });
      if (bi >= 0) {
        const s = pool.splice(bi, 1)[0];
        const add = rev ? s.reverse() : s;
        for (const p of add) {
          const last = chain[chain.length-1];
          if (Math.hypot(p[0]-last[0], p[1]-last[1]) > 0.5) chain.push(p.slice());
        }
        changed = true; grew = true;
      }
    }
    changed = true;
    while (changed) {
      changed = false;
      const tail = chain[0];
      let bi = -1, rev = false, bd = maxGap;
      pool.forEach((s, k) => {
        const dA = Math.hypot(s[0][0]-tail[0], s[0][1]-tail[1]);
        const dB = Math.hypot(s[s.length-1][0]-tail[0], s[s.length-1][1]-tail[1]);
        if (Math.min(dA,dB) < bd) { bd = Math.min(dA,dB); bi = k; rev = dA < dB; }
      });
      if (bi >= 0) {
        const s = pool.splice(bi, 1)[0];
        const add = rev ? s.slice() : s.slice().reverse();
        for (const p of add) {
          if (Math.hypot(p[0]-chain[0][0], p[1]-chain[0][1]) > 0.5) chain.unshift(p.slice());
        }
        changed = true; grew = true;
      }
    }
  }
  return chain;
}

function arcPositions(chain, n) {
  if (!chain.length || n < 1) return [];
  const arcs = [0];
  for (let k = 1; k < chain.length; k++)
    arcs.push(arcs[k-1] + Math.hypot(chain[k][0]-chain[k-1][0], chain[k][1]-chain[k-1][1]));
  const total = arcs[arcs.length - 1];
  const positions = [];
  for (let i = 0; i < n; i++) {
    const target = n === 1 ? total / 2 : total * i / (n - 1);
    let lo = 0, hi = arcs.length - 1;
    while (hi - lo > 1) { const mid = (lo+hi)>>1; if (arcs[mid] < target) lo = mid; else hi = mid; }
    const t = (target - arcs[lo]) / (arcs[hi] - arcs[lo] || 1);
    positions.push([chain[lo][0] + (chain[hi][0]-chain[lo][0]) * t, chain[lo][1] + (chain[hi][1]-chain[lo][1]) * t]);
  }
  return positions;
}

const l1set = new Set(D.lineStationIds(D.line('1')));
const assigned = {};
const lineOrder = ['1','6','5','2','8','3','4','7','GF','APM','10','12','13','14','21','18','11','22'];

for (const ref of lineOrder) {
  const l = D.line(ref);
  if (!l) continue;
  const ids = D.lineStationIds(l);
  let segs = extractSegs(GIDS[ref] || ref);
  if (ref === '10') segs = segs.concat(extractSegs('_x31_0_2_'));
  if (!segs.length) { console.log(ref + ': 无段跳过'); continue; }

  if (ref === '1') {
    for (const id of ids) {
      const st = data.stations.find(x => x.id === id);
      assigned[id] = [st.sx, st.sy];
    }
    console.log('1: 锁定' + ids.length + '站');
    continue;
  }

  const path = chain(segs);
  if (path.length < 3) { console.log(ref + ': 链太短'); continue; }
  const positions = arcPositions(path, ids.length);
  if (positions.length !== ids.length) { console.log(ref + ': 位置数不匹配'); continue; }

  const lockedIdx = [];
  ids.forEach((id, i) => { if (assigned[id]) lockedIdx.push({ i, id, pos: assigned[id] }); });

  if (lockedIdx.length === 0) {
    ids.forEach((id, i) => { assigned[id] = positions[i]; });
  } else {
    const arcs = [0];
    for (let k = 1; k < path.length; k++)
      arcs.push(arcs[k-1] + Math.hypot(path[k][0]-path[k-1][0], path[k][1]-path[k-1][1]));
    function arcOf(px, py) {
      let bd = 1e9, ba = 0;
      for (let k = 0; k + 1 < path.length; k++) {
        const [x1,y1] = path[k], [x2,y2] = path[k+1];
        const vx=x2-x1, vy=y2-y1, L2=vx*vx+vy*vy||1;
        const t = Math.max(0, Math.min(1, ((px-x1)*vx+(py-y1)*vy)/L2));
        const d = Math.hypot(px-(x1+t*vx), py-(y1+t*vy));
        if (d < bd) { bd = d; ba = arcs[k] + t*(arcs[k+1]-arcs[k]); }
      }
      return ba;
    }
    const anchors = lockedIdx.map(a => ({ i: a.i, arc: arcOf(a.pos[0], a.pos[1]) }));
    anchors.sort((a, b) => a.arc - b.arc);
    const total = arcs[arcs.length-1];
    const bounds = [{ i: 0, arc: 0 }, ...anchors, { i: ids.length, arc: total }];
    for (let k = 0; k + 1 < bounds.length; k++) {
      const a = bounds[k], b = bounds[k+1];
      const gapIds = [];
      for (let idx = a.i; idx < b.i; idx++) if (!assigned[ids[idx]]) gapIds.push(idx);
      if (!gapIds.length) continue;
      const arcPer = (b.arc - a.arc) / (gapIds.length + 1);
      gapIds.forEach((idx, q) => {
        const target = a.arc + arcPer * (q + 1);
        let lo = 0, hi = arcs.length - 1;
        while (hi - lo > 1) { const mid = (lo+hi)>>1; if (arcs[mid] < target) lo = mid; else hi = mid; }
        const t = (target - arcs[lo]) / (arcs[hi] - arcs[lo] || 1);
        assigned[ids[idx]] = [path[lo][0] + (path[hi][0]-path[lo][0])*t, path[lo][1] + (path[hi][1]-path[lo][1])*t];
      });
    }
  }
  console.log(ref + ': ' + ids.filter(id => assigned[id]).length + '/' + ids.length + ' 均匀');
}

let applied = 0;
for (const st of data.stations) {
  if (assigned[st.id] && Math.hypot(assigned[st.id][0]-st.sx, assigned[st.id][1]-st.sy) > 4) {
    st.sx = assigned[st.id][0]; st.sy = assigned[st.id][1]; applied++;
  }
}
for (let round = 0; round < 5; round++) {
  let has = false;
  for (let i = 0; i < data.stations.length; i++) for (let j = i + 1; j < data.stations.length; j++) {
    const a = data.stations[i], b = data.stations[j];
    if (Math.hypot(a.sx-b.sx, a.sy-b.sy) < 8) {
      has = true;
      const go = a.id < b.id ? b : a;
      go.sx += 40; go.sy += 40;
    }
  }
  if (!has) break;
}
fs.writeFileSync(path.join(ROOT, 'data', 'metro-data.js'), 'window.METRO_DATA = ' + JSON.stringify(data) + ';\n');
let dup = 0;
for (let i = 0; i < data.stations.length; i++) for (let j = i + 1; j < data.stations.length; j++)
  if (Math.hypot(data.stations[i].sx-data.stations[j].sx, data.stations[i].sy-data.stations[j].sy) < 8) dup++;
console.log('\n应用:' + applied + ' 重合:' + dup);
