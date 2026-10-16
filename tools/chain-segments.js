// 矢量段排序 v2：正确解析 SVG path（相对坐标弧线），把每条线的段建成有序链
// 输出：assets/tim-vector-ordered.json（每线一条有序折线）
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const svg = fs.readFileSync(path.join(ROOT, 'assets', 'tim-gzfmetro.svg'), 'utf-8');

function groupSpan(gid) {
  const gi = svg.indexOf('id="' + gid + '"');
  if (gi < 0) return null;
  let i = svg.indexOf('>', gi) + 1, depth = 1, j = i;
  while (depth > 0) {
    const no = svg.indexOf('<g', j), nc = svg.indexOf('</g>', j);
    if (nc < 0) break;
    if (no >= 0 && no < nc) { depth++; j = no + 2; } else { depth--; j = nc + 4; }
  }
  return svg.slice(i, j - 4);
}

// 解析 path d 属性：M 绝对起点 + c 相对贝塞尔 → 绝对端点序列
function parsePath(d) {
  const pts = [];
  // 拆 M 和后续 c 命令
  const mMatch = /M([\d.-]+),([\d.-]+)/.exec(d);
  if (!mMatch) return pts;
  let cx = parseFloat(mMatch[1]), cy = parseFloat(mMatch[2]);
  pts.push([cx, cy]);
  // 提取所有 c 命令的数字（每 6 个一组：dx1,dy1 dx2,dy2 dx,dy）
  const rest = d.substring(mMatch[0].length);
  const nums = [];
  let tok = '';
  for (const ch of rest) {
    if (/[-0-9.]/.test(ch)) tok += ch;
    else if (tok) { nums.push(parseFloat(tok)); tok = ''; }
  }
  if (tok) nums.push(parseFloat(tok));
  for (let k = 4; k + 1 < nums.length; k += 6) {
    cx += nums[k]; cy += nums[k + 1];
    pts.push([cx, cy]);
  }
  return pts;
}

// 从组提取所有几何段（line + path）
function extractSegments(gid) {
  const seg = groupSpan(gid);
  if (!seg) return [];
  const out = [];
  for (const m of seg.matchAll(/<line[^>]*?x1="([\d.-]+)"[^>]*?y1="([\d.-]+)"[^>]*?x2="([\d.-]+)"[^>]*?y2="([\d.-]+)"/g)) {
    const pts = [[parseFloat(m[1]), parseFloat(m[2])], [parseFloat(m[3]), parseFloat(m[4])]];
    if (Math.hypot(pts[1][0]-pts[0][0], pts[1][1]-pts[0][1]) > 1) out.push(pts);
  }
  for (const m of seg.matchAll(/<path[^>]*?d="(M[^"]+)"/g)) {
    const pts = parsePath(m[1]);
    if (pts.length >= 2) out.push(pts);
  }
  return out;
}

// 链式拼接：从起点开始贪心连接
function chain(segs, maxGap = 30) {
  if (!segs.length) return { chain: [], leftover: 0 };
  const pool = segs.map(s => s.slice());
  // 起点选择：最西（或最南）段的起点
  pool.sort((a, b) => a[0][0] + a[0][1] - b[0][0] - b[0][1]);
  const first = pool.shift();
  const chain = first.slice();
  // 尝试两个方向增长
  let grown = true;
  while (grown) {
    grown = false;
    // 尾部增长
    let changed = true;
    while (changed) {
      changed = false;
      const head = chain[chain.length - 1];
      let bi = -1, rev = false, bd = maxGap;
      pool.forEach((s, k) => {
        const dA = Math.hypot(s[0][0]-head[0], s[0][1]-head[1]);
        const dB = Math.hypot(s[s.length-1][0]-head[0], s[s.length-1][1]-head[1]);
        if (Math.min(dA, dB) < bd) { bd = Math.min(dA, dB); bi = k; rev = dB < dA; }
      });
      if (bi >= 0) {
        const s = pool.splice(bi, 1)[0];
        const add = rev ? s.slice().reverse() : s;
        for (const p of add) {
          const last = chain[chain.length - 1];
          if (Math.hypot(p[0]-last[0], p[1]-last[1]) > 0.5) chain.push(p.slice());
        }
        changed = true; grown = true;
      }
    }
    // 头部增长
    changed = true;
    while (changed) {
      changed = false;
      const tail = chain[0];
      let bi = -1, rev = false, bd = maxGap;
      pool.forEach((s, k) => {
        const dA = Math.hypot(s[0][0]-tail[0], s[0][1]-tail[1]);
        const dB = Math.hypot(s[s.length-1][0]-tail[0], s[s.length-1][1]-tail[1]);
        if (Math.min(dA, dB) < bd) { bd = Math.min(dA, dB); bi = k; rev = dA < dB; }
      });
      if (bi >= 0) {
        const s = pool.splice(bi, 1)[0];
        const add = rev ? s.slice() : s.slice().reverse();  // 从头接，方向反转
        for (const p of add) {
          if (Math.hypot(p[0]-chain[0][0], p[1]-chain[0][1]) > 0.5) chain.unshift(p.slice());
        }
        changed = true; grown = true;
      }
    }
  }
  return { chain, leftover: pool.length };
}

const LINE_GIDS = {
  '1': '_x31_', '2': '_x32_', '3': '_x33_', '4': '_x34_', '5': '_x35_',
  '6': '_x36_', '7': '_x37_', '8': '_x38_', '9': '_x39__3_',
  '10': '_x31_0_1_', '11': '_x31_1', '12': '_x31_2', '13': '_x31_3',
  '14': '_x31_4', '18': '_x31_8', '21': '_x32_1', '22': '_x32_2',
  'GF': 'GF', 'APM': 'APM_3_'
};

global.window = {};
require(path.join(ROOT, 'data', 'metro-data.js'));
const D = new Function('window',
  fs.readFileSync(path.join(ROOT, 'js', 'metro-data.js'), 'utf-8') + ';return MetroData;')(window);

const ordered = {};
console.log('=== 矢量段有序化 ===');
for (const l of D.allLines()) {
  const gid = LINE_GIDS[l.ref];
  if (!gid) { console.log(l.ref + ': 无GID'); continue; }
  // 也尝试 _x31_0_2_（10号线可能有两个组）
  let segs = extractSegments(gid);
  if (l.ref === '10') {
    const segs2 = extractSegments('_x31_0_2_');
    segs = segs.concat(segs2);
  }
  if (!segs.length) { console.log(l.ref + ': 无段(' + gid + ')'); continue; }
  const { chain: c, leftover } = chain(segs);
  // 方向校正：确保链头靠近站序第1站
  const first = D.station(l.stations[0]);
  const last = D.station(l.stations[l.stations.length - 1]);
  const dHead = Math.hypot(c[0][0] - first.sx, c[0][1] - first.sy);
  const dTail = Math.hypot(c[c.length - 1][0] - first.sx, c[c.length - 1][1] - first.sy);
  const final = dTail < dHead ? c.slice().reverse() : c;
  ordered[l.ref] = final;
  // 质量指标：剩余段数 + 首末站与链端对齐
  const d1 = Math.hypot(final[0][0] - first.sx, final[0][1] - first.sy);
  const dN = Math.hypot(final[final.length-1][0] - last.sx, final[final.length-1][1] - last.sy);
  const ok = leftover === 0 && d1 < 100 && dN < 100;
  console.log(l.ref.padEnd(4), '段' + String(segs.length).padStart(2), '→ 链' + String(final.length).padStart(3) + '点',
    '余' + String(leftover).padStart(2),
    '首站距' + Math.round(d1) + 'px', '末站距' + Math.round(dN) + 'px',
    ok ? '✓' : (leftover <= 2 ? '≈' : '✗'));
}

fs.writeFileSync(path.join(ROOT, 'assets', 'tim-vector-ordered.json'), JSON.stringify(ordered, null, 1));
console.log('\n写出 assets/tim-vector-ordered.json');
