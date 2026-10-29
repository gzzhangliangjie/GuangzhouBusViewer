// 路由图共享层（Valhalla 式预处理 + App 端轻解码）
// 数据 = data/routing-graph.json（test/pull-roadnet.js 合并期产出：路口压缩图 + CSR 邻接 +
// 边形状差分编码 + 每边 类别枚举/oneway/maxspeed/路名id）——压缩在构建期做，这里只解码
// 消费方：①RoutePlanner 首末步行段真实路径（有界 Dijkstra） ②RoadsView 道路本地检索
// 驾车模式（未来）：同一张图，按 oneway/类别速度过滤与计价
const RoadNet = (() => {
  // 步行排除类别（机动车专用）；其余 highway 一律可步行
  const WALK_EXCLUDE = new Set([0, 1, 2, 3, 22, 23, 24]);
  const CODE2CLS = {
    0: 'motorway', 1: 'motorway_link', 2: 'trunk', 3: 'trunk_link', 4: 'primary',
    5: 'primary_link', 6: 'secondary', 7: 'secondary_link', 8: 'tertiary', 9: 'tertiary_link',
    10: 'residential', 11: 'unclassified', 12: 'living_street', 13: 'service', 14: 'track',
    15: 'footway', 16: 'path', 17: 'pedestrian', 18: 'steps', 19: 'cycleway', 20: 'road',
    21: 'busway', 22: 'bus_guideway', 23: 'raceway', 24: 'construction'
  };

  let g = null;              // 解码后的图（类型化数组）
  let loadPromise = null;
  let walkGrid = null;       // 路口网格索引（计数排序 CSR）
  let nameEdgeIdx = null;    // nameId -> [edgeId...]（惰性建）
  // Dijkstra 复用缓冲（代际戳免重填）；prevSlot=父邻接槽位（形状方向），prevNode=父路口（回溯链）
  let distBuf = null, prevSlotBuf = null, prevNodeBuf = null, stampBuf = null, gen = 0;

  const cosLat = Math.cos(23.1 * Math.PI / 180);
  const jLat = j => g.nodes[2 * j] / 1e5;
  const jLng = j => g.nodes[2 * j + 1] / 1e5;

  /** 装载 + 解码（缺失/失败返回 false，消费方自行降级） */
  function ready() {
    if (loadPromise) return loadPromise;
    loadPromise = (async () => {
      try {
        const res = await fetch('data/routing-graph.json');
        if (!res.ok) return false;
        const raw = await res.json();
        if (!raw.J) return false;
        g = {
          J: raw.J, E: raw.E,
          nodes: Int32Array.from(raw.nodes),
          eOff: Int32Array.from(raw.eOff),
          adjNbr: Int32Array.from(raw.adjNbr),
          adjE: Int32Array.from(raw.adjE),
          adjRev: Int8Array.from(raw.adjRev),
          eM: Int32Array.from(raw.eM),
          eCls: Int32Array.from(raw.eCls),
          eOw: Int8Array.from(raw.eOw),
          eMs: Int32Array.from(raw.eMs),
          eName: Int32Array.from(raw.eName),
          shOff: Int32Array.from(raw.shOff),
          shapes: Int32Array.from(raw.shapes),
          names: raw.names
        };
        buildGrid();
        distBuf = new Float64Array(g.J);
        prevSlotBuf = new Int32Array(g.J);
        prevNodeBuf = new Int32Array(g.J);
        stampBuf = new Int32Array(g.J);
        return true;
      } catch { return false; }
    })();
    return loadPromise;
  }

  function buildGrid() {
    // 路口网格索引：cell 0.005°，计数排序 CSR（无 Map）
    const CELL = 0.005, GW = 512;
    const keyOf = (la, ln) => {
      const cx = Math.floor((la / 1e5 - 22) / CELL), cy = Math.floor((ln / 1e5 - 112) / CELL);
      return cx * GW + cy;
    };
    const nCells = GW * 512;   // cy 最大 = (114.03-112)/0.005 = 406 < 512（GW*258 曾把广州东部路口挤出网格）
    const counts = new Int32Array(nCells);
    for (let j = 0; j < g.J; j++) counts[keyOf(g.nodes[2 * j], g.nodes[2 * j + 1])]++;
    const start = new Int32Array(nCells + 1);
    for (let i = 0; i < nCells; i++) start[i + 1] = start[i] + counts[i];
    const idx = new Int32Array(g.J);
    const cur = Int32Array.from(start);
    for (let j = 0; j < g.J; j++) {
      const k = keyOf(g.nodes[2 * j], g.nodes[2 * j + 1]);
      idx[cur[k]] = j;
      cur[k]++;
    }
    walkGrid = { start, idx, GW, CELL };
  }

  function nearestJunction(lat, lng, maxM) {
    const CELL = walkGrid.CELL, GW = walkGrid.GW;
    const cx = Math.floor((lat - 22) / CELL), cy = Math.floor((lng - 112) / CELL);
    let best = -1, bestD = Infinity;
    for (let x = cx - 1; x <= cx + 1; x++) {
      if (x < 0 || x >= GW) continue;
      for (let y = cy - 1; y <= cy + 1; y++) {
        if (y < 0) continue;
        const key = x * GW + y;
        if (key >= walkGrid.start.length - 1) continue;
        for (let p = walkGrid.start[key]; p < walkGrid.start[key + 1]; p++) {
          const j = walkGrid.idx[p];
          const dy = (jLat(j) - lat) * 110540, dx = (jLng(j) - lng) * cosLat * 111320;
          const d = Math.hypot(dx, dy);
          if (d < bestD) { bestD = d; best = j; }
        }
      }
    }
    if (best < 0 || bestD > maxM) return null;
    return { j: best, m: bestD };
  }

  /** 边形状解码（差分→绝对度数点列）：flat 布局 = [la0, ln0, dla1, dln1, ...] */
  function shapeOf(e) {
    const s = g.shOff[e], t = g.shOff[e + 1];
    const out = [];
    let pla = 0, pln = 0;
    for (let p = s; p < t; p += 2) {
      if (p === s) { pla = g.shapes[p]; pln = g.shapes[p + 1]; }
      else { pla += g.shapes[p]; pln += g.shapes[p + 1]; }
      out.push([pla / 1e5, pln / 1e5]);
    }
    return out;
  }

  /**
   * 两点间真实步行路径（有界 Dijkstra，步行类别过滤）。
   * 返回 { m: 实走米数, pts: [[lat,lng]...] }；不可达/超界返回 null。
   */
  function walkPath(from, to, maxM = 2500) {
    if (!g) return null;
    const na = nearestJunction(from.lat, from.lng, 500);
    const nb = nearestJunction(to.lat, to.lng, 500);
    if (!na || !nb) return null;
    const cap = maxM + na.m + nb.m;
    gen++;
    const stamp = gen;
    distBuf[na.j] = na.m;
    stampBuf[na.j] = stamp;
    prevSlotBuf[na.j] = -1;
    prevNodeBuf[na.j] = -1;
    const heap = [[na.m, na.j]];
    const push = (d, nd) => {
      heap.push([d, nd]);
      let i = heap.length - 1;
      while (i > 0) { const p = (i - 1) >> 1; if (heap[p][0] <= heap[i][0]) break; const t = heap[p]; heap[p] = heap[i]; heap[i] = t; i = p; }
    };
    const pop = () => {
      const top = heap[0]; const last = heap.pop();
      if (heap.length) {
        heap[0] = last;
        let i = 0;
        for (;;) {
          const l = 2 * i + 1, r = l + 1; let m = i;
          if (l < heap.length && heap[l][0] < heap[m][0]) m = l;
          if (r < heap.length && heap[r][0] < heap[m][0]) m = r;
          if (m === i) break;
          const t = heap[m]; heap[m] = heap[i]; heap[i] = t; i = m;
        }
      }
      return top;
    };
    let found = -1;
    while (heap.length) {
      const [d, j] = pop();
      if (stampBuf[j] !== stamp || distBuf[j] !== d) continue;
      if (j === nb.j) { found = j; break; }
      if (d > cap) break;
      for (let s = g.eOff[j]; s < g.eOff[j + 1]; s++) {
        const e = g.adjE[s];
        if (WALK_EXCLUDE.has(g.eCls[e])) continue;
        const nbr = g.adjNbr[s];
        const nd = d + g.eM[e];
        if (nd > cap) continue;
        if (stampBuf[nbr] !== stamp || nd < distBuf[nbr]) {
          distBuf[nbr] = nd; stampBuf[nbr] = stamp; prevSlotBuf[nbr] = s; prevNodeBuf[nbr] = j;
          push(nd, nbr);
        }
      }
    }
    if (found < 0) return null;
    // 回溯槽位链 → 拼形状（注意槽位方向：rev=1 时边形状要反向）
    // 守卫：链长封顶 + 非法槽位即断（防脏数据成环疯转，2026-10-29 RangeError 判例）
    const slots = [];
    let cur = found;
    const onChain = new Set();
    while (cur !== na.j) {
      const s = prevSlotBuf[cur];
      if (!Number.isInteger(s) || s < 0 || s >= g.eOff[g.J]) { console.error('[roadnet] 断链 cur=' + cur + ' s=' + s + ' dist=' + distBuf[cur]); break; }
      if (onChain.has(cur)) { console.error('[roadnet] 环! cur=' + cur); break; }
      onChain.add(cur);
      slots.push(s);
      if (slots.length > 200000) { console.error('[roadnet] 回溯链超长', cur, s); break; }
      cur = prevNodeBuf[cur];
    }
    slots.reverse();
    const pts = [[from.lat, from.lng]];
    for (const s of slots) {
      const e = g.adjE[s];
      const sh = shapeOf(e);
      if (g.adjRev[s]) sh.reverse();
      // 槽位起点=当前节点：形状首点应与当前节点重合；为省体积直接跳过与上一点重复的首点
      for (let i = 0; i < sh.length; i++) {
        const p = sh[i];
        const lastP = pts[pts.length - 1];
        if (Math.abs(p[0] - lastP[0]) < 1e-9 && Math.abs(p[1] - lastP[1]) < 1e-9) continue;
        pts.push(p);
      }
    }
    pts.push([to.lat, to.lng]);
    return { m: Math.round(distBuf[found] + nb.m), pts };
  }

  /** 道路查看：按关键词本地检索（与 roads.js 的 Overpass 结果同构：{name, cls, km, ways}） */
  function searchRoads(kw) {
    if (!g) return [];
    if (!nameEdgeIdx) {
      nameEdgeIdx = new Map();
      for (let e = 0; e < g.E; e++) {
        const nid = g.eName[e];
        if (nid < 0) continue;
        let arr = nameEdgeIdx.get(nid);
        if (!arr) { arr = []; nameEdgeIdx.set(nid, arr); }
        arr.push(e);
      }
    }
    const key = String(kw).toLowerCase();
    const out = [];
    for (const [nid, eids] of nameEdgeIdx) {
      const name = g.names[nid];
      if (!name || !name.toLowerCase().includes(key)) continue;
      let km = 0;
      const ways = [];
      const cls = CODE2CLS[g.eCls[eids[0]]] || 'road';
      const seen = new Set();
      for (const e of eids) {
        km += g.eM[e];
        if (!seen.has(e)) { seen.add(e); ways.push(shapeOf(e)); }
      }
      out.push({ name, cls, km: Math.round(km / 100) / 10, ways });
      if (out.length >= 200) break;
    }
    return out;
  }

  function stats() { return g ? { nodeN: g.J, wayN: g.E, at: 0 } : null; }

  return { ready, walkPath, searchRoads, stats };
})();

window.RoadNet = RoadNet;
