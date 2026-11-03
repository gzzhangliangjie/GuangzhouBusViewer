// 路线规划引擎（纯本地）：站网图构建 + A* 最短路 + 站名索引
// 数据全部来自随包离线数据：data/metro-data.js（19 线 318 站）+ data/bus-lines-snapshot.json（公交离线快照）
// 设计文档：docs/route-planner-design.md（时间参数/兜底链口径以文档为准）
const RoutePlanner = (() => {
  /* ---------- 参数（集中可调，设计文档 §2） ---------- */
  const P = {
    METRO_KMH: 35, BUS_KMH: 16, WALK_KMH: 4.5,
    WALK_DETOUR: 1.4,                 // 步行绕行系数：直线×1.4 估实走（密集城区经验值，老城略高±30%；
                                      // 排序比相对优劣，统乘不改变结论。2026-10-29 用户指"聚仁坊到团一大广场没那么近"判例）
    TRANSFER_PENALTY_MIN: 4,          // 每次换乘罚时（2026-10-29 用户令"6换怎么可能48分钟"判例：
                                      // 2min 时地铁站内 0 距离换乘几乎免费，严重低估；4min=站内/跨站
                                      // 换乘含候车的均值，叠加真实步行时间之上）
    TRANSFER_RADIUS_M: 250,           // 站间步行换乘最大距离
    GRID_CELL_M: 300,                 // 空间索引网格
    MAX_TRANSFER_PER_STOP: 8,         // 每站最多保留的最近换乘边
    WALK_RADIUS_STATION_M: 2000,      // 站点作起终点的步行候选半径（2026-10-29 用户令：扩到 2km，
                                      // 打通"长距离步行换更少换乘"类方案，如 1号线+5号线）
    WALK_RADIUS_POI_M: 2000,          // 地名/地标作起终点：步行接驳半径
    ENDPOINTS_MAX: 8,                 // 起终点最多接入的站点数
    ENDPOINTS_PER_KIND: 4,            // 每类（公交/地铁）最多名额——防密集公交站挤掉地铁参赛资格
    XFER_PROFILES: [1, 3, 20],        // 换乘罚倍率梯度：1=纯最快 / 3=轻度少换乘 / 20=近乎字典序最少换乘
                                      //（2026-10-29 用户问"为什么找不到1号线转5号线"判例：罚太轻时
                                      // 长步行+1换的总代价永远输给短步行+2换，最少换方案浮不上池）
    NAME_CLUSTER_M: 500,              // 同名站实例判异（>此距算不同实例）
    PICK_RADIUS_M: 800,               // 地图点选吸附半径
    POI_CACHE_TTL: 7 * 24 * 3600 * 1000
  };
  const PALETTE = ['#e5534b', '#4a9eff', '#2ea043', '#d29922', '#bf63ff',
                   '#39c5cf', '#ff7b72', '#f0883e', '#7ee787', '#79c0ff'];
  const GZ_BBOX = '22.35,112.95,23.94,114.03';

  /* ---------- 基础几何 ---------- */
  const cosLat = Math.cos(23.1 * Math.PI / 180);
  function distM(a, b) {
    const dy = (a.lat - b.lat) * 110540;
    const dx = (a.lng - b.lng) * cosLat * 111320;
    return Math.hypot(dx, dy);
  }
  // p 兼容 {lat,lng} 与 [lat,lng] 两种形态（leg.pts 是数组形态）
  const LL = p => Array.isArray(p) ? { lat: p[0], lng: p[1] } : p;
  function pathM(pts) {
    let s = 0;
    for (let i = 1; i < pts.length; i++) s += distM(LL(pts[i - 1]), LL(pts[i]));
    return s;
  }
  const minPerM = kmh => 60 / (kmh * 1000);   // 每米耗时（分钟）

  // GCJ-02 反算 WGS-84（高德 POI 返回 GCJ，路网是 WGS，迭代逼近 <1m）
  function gcjToWgs(lat, lng) {
    let wlat = lat, wlng = lng;
    for (let i = 0; i < 3; i++) {
      const g = (window.GCJ ? GCJ.wgs84ToGcj02(wlat, wlng) : [wlat, wlng]);
      wlat += lat - g[0]; wlng += lng - g[1];
    }
    return [wlat, wlng];
  }

  /* ---------- 站名归一（去括号后缀/空白；索引键与查询共用） ---------- */
  function normName(s) {
    return String(s || '').replace(/[（(].*?$/, '').replace(/\s+/g, '');
  }

  /* ---------- 图数据 ---------- */
  let nodes = [];           // {name, lat, lng, kind:'metro'|'bus', v:variantIdx}
  let adj = [];             // adj[i] = [{to, min, kind:'ride'|'walk', v, ia, ib, walkM}]
  let variants = [];        // {kind, ref, name, to, colour}
  let variantNodeSeq = [];  // variantIdx -> [nodeIdx...]（站点序，画段/取站名用）
  let grid = null;          // "cx,cy" -> [nodeIdx]
  let nameIdx = null;       // normName -> {name, nodeIds:[]}
  let buildMs = 0;

  const CELL_LAT = P.GRID_CELL_M / 110540;
  const CELL_LNG = P.GRID_CELL_M / (111320 * cosLat);
  const cellKey = (lat, lng) => Math.floor(lat / CELL_LAT) + ',' + Math.floor(lng / CELL_LNG);

  function gridAdd(i) {
    const k = cellKey(nodes[i].lat, nodes[i].lng);
    let c = grid.get(k);
    if (!c) { c = []; grid.set(k, c); }
    c.push(i);
  }
  function queryNear(lat, lng, rM) {
    const cx = Math.floor(lat / CELL_LAT), cy = Math.floor(lng / CELL_LNG);
    const dx = Math.ceil(rM / P.GRID_CELL_M);
    const out = [];
    for (let x = cx - dx; x <= cx + dx; x++)
      for (let y = cy - dx; y <= cy + dx; y++) {
        const c = grid.get(x + ',' + y);
        if (c) for (const i of c) {
          const d = distM({ lat, lng }, nodes[i]);
          if (d <= rM) out.push([i, d]);
        }
      }
    return out;
  }

  function addNode(n) { nodes.push(n); adj.push([]); gridAdd(nodes.length - 1); return nodes.length - 1; }

  function addRide(a, b, kmh, v, ia, ib) {
    const min = distM(nodes[a], nodes[b]) * minPerM(kmh);
    const fwd = { to: b, min, kind: 'ride', v, ia, ib };
    const rev = { to: a, min, kind: 'ride', v, ia: ib, ib: ia };
    fwd.tw = rev; rev.tw = fwd;   // 孪生边：多方案惩罚时成对处理
    adj[a].push(fwd);
    adj[b].push(rev);
  }

  /* ---------- 图构建（首次查询触发，进程内缓存） ---------- */
  // 地铁：节点键 = 线ref+站id（同线同站共享节点→支线天然连通；跨线各持实例→靠换乘边连接）
  const metroNodeByKey = new Map();
  function buildMetro() {
    for (const l of MetroData.allLines()) {
      const seqs = [];
      if (l.stations.length) seqs.push(l.stations);
      for (const br of l.branches || []) if (br.length) seqs.push(br);
      const vIdx = variants.length;
      variants.push({ kind: 'metro', ref: l.ref, name: l.zh, to: '', colour: l.color });
      variantNodeSeq.push([]);
      for (let si = 0; si < seqs.length; si++) {
        const base = variantNodeSeq[vIdx].length;   // 本段在变体站序中的起点（主线在前、支线续接）
        const ids = [];
        const seen = new Set();
        for (const id of seqs[si]) { if (!seen.has(id)) { seen.add(id); ids.push(id); } }
        const nids = ids.map(id => {
          const st = MetroData.station(id);
          if (!st) return null;
          const key = l.ref + '|' + id;
          let ni = metroNodeByKey.get(key);
          if (ni === undefined) {
            ni = addNode({ name: st.zh || id, lat: st.lat, lng: st.lon, kind: 'metro', v: vIdx });
            metroNodeByKey.set(key, ni);
          }
          variantNodeSeq[vIdx].push(ni);
          return ni;
        }).filter(x => x !== null);
        for (let i = 1; i < nids.length; i++) addRide(nids[i - 1], nids[i], P.METRO_KMH, vIdx, base + i - 1, base + i);
        // 环线闭合（主线段首尾相接）
        if (l.loop && si === 0 && nids.length > 2) addRide(nids[nids.length - 1], nids[0], P.METRO_KMH, vIdx, nids.length - 1, 0);
      }
    }
  }

  function buildBus(snap) {
    for (const ref in snap.lines) {
      for (const v of snap.lines[ref]) {
        if (!v.stops || v.stops.length < 2) continue;
        const vIdx = variants.length;
        variants.push({
          kind: 'bus', ref: v.ref || ref, name: v.name || '', to: v.to || '',
          colour: v.colour || PALETTE[hashCode(v.ref || ref) % PALETTE.length]
        });
        const seq = [];
        const nids = v.stops.map(s => {
          const ni = addNode({ name: s.name, lat: s.lat, lng: s.lng, kind: 'bus', v: vIdx });
          seq.push(ni);
          return ni;
        });
        variantNodeSeq.push(seq);
        for (let i = 1; i < nids.length; i++) addRide(nids[i - 1], nids[i], P.BUS_KMH, vIdx, i - 1, i);
      }
    }
  }

  function buildTransfers() {
    for (let i = 0; i < nodes.length; i++) {
      const cands = queryNear(nodes[i].lat, nodes[i].lng, P.TRANSFER_RADIUS_M)
        .filter(([j]) => j > i)
        .sort((a, b) => a[1] - b[1])
        .slice(0, P.MAX_TRANSFER_PER_STOP);
      for (const [j, d] of cands) {
        const walkM = d * P.WALK_DETOUR;
        const min = walkM * minPerM(P.WALK_KMH) + P.TRANSFER_PENALTY_MIN;
        adj[i].push({ to: j, min, kind: 'walk', walkM, xf: 1 });
        adj[j].push({ to: i, min, kind: 'walk', walkM, xf: 1 });
      }
    }
  }

  function buildNameIndex() {
    nameIdx = new Map();
    for (let i = 0; i < nodes.length; i++) {
      const k = normName(nodes[i].name);
      if (!k) continue;
      let e = nameIdx.get(k);
      if (!e) { e = { name: nodes[i].name, nodeIds: [] }; nameIdx.set(k, e); }
      e.nodeIds.push(i);
    }
  }

  function hashCode(s) { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return Math.abs(h); }

  let readyPromise = null;
  function ready() {
    if (readyPromise) return readyPromise;
    readyPromise = (async () => {
      const t0 = performance.now();
      nodes = []; adj = []; variants = []; variantNodeSeq = [];
      metroNodeByKey.clear();
      grid = new Map();
      buildMetro();
      const res = await fetch('data/bus-lines-snapshot.json');
      if (!res.ok) throw new Error('公交离线快照加载失败 HTTP ' + res.status);
      buildBus(await res.json());
      buildTransfers();
      buildNameIndex();
      // 路网快照 best-effort（首末步行真实化；缺失/失败自动退化为直线×绕行系数）
      try { if (window.RoadNet) await RoadNet.ready(); } catch { /* 降级 */ }
      buildMs = Math.round(performance.now() - t0);
      return { nodesN: nodes.length, variantsN: variants.length, buildMs };
    })();
    return readyPromise;
  }

  /* ---------- A*（二叉堆，h=直线距离/最高速度，可采纳必最优） ---------- */
  // goalEdges = 候选站→虚拟终点的合成末端步行边（调用方已把虚拟终点 push 进 nodes）
  // penalties: Map<ride边对象, 罚时min>，多方案 Top-K 用（只罚乘车边，逼出不同走法）
  // xferMul: 换乘罚倍率（1=纯最快；>1 搜索向少换乘倾斜，summary 仍按真实时刻计算）
  // kindFilter: 'bus'|'metro'|null——纯公交/纯地铁模式的车型过滤（乘车边按变体类别、换乘边按两端节点类别）
  function astar(startEdges, goalEdges, goalPt, penalties, xferMul = 1, kindFilter = null) {
    const xferExtra = e => (e.xf ? (xferMul - 1) * P.TRANSFER_PENALTY_MIN : 0);
    const n = nodes.length;
    const T = n - 1;                   // 虚拟终点
    const dist = new Float64Array(n).fill(Infinity);
    const prev = new Int32Array(n).fill(-1);
    const prevEdge = new Array(n);
    const done = new Uint8Array(n);
    const heap = [];   // [f, g, node]
    const push = (f, g, nd) => {
      heap.push([f, g, nd]);
      let i = heap.length - 1;
      while (i > 0) { const p = (i - 1) >> 1; if (heap[p][0] <= heap[i][0]) break; const t = heap[p]; heap[p] = heap[i]; heap[i] = t; i = p; }
    };
    const pop = () => {
      const top = heap[0];
      const last = heap.pop();
      if (heap.length) {
        heap[0] = last;
        let i = 0;
        for (;;) {
          const l = 2 * i + 1, r = l + 1;
          let m = i;
          if (l < heap.length && heap[l][0] < heap[m][0]) m = l;
          if (r < heap.length && heap[r][0] < heap[m][0]) m = r;
          if (m === i) break;
          const t = heap[m]; heap[m] = heap[i]; heap[i] = t; i = m;
        }
      }
      return top;
    };
    const h = nd => distM(nodes[nd], goalPt) * minPerM(P.METRO_KMH);
    const goalByNode = new Map();
    for (const ge of goalEdges) goalByNode.set(ge.from, ge);

    for (const e of startEdges) {
      if (e.min < dist[e.to]) { dist[e.to] = e.min; prevEdge[e.to] = e; push(e.min + h(e.to), e.min, e.to); }
    }
    while (heap.length) {
      const top = pop();
      const g = top[1], nd = top[2];
      if (done[nd]) continue;
      done[nd] = 1;
      if (nd === T) {
        const edges = [];
        let cur = nd;
        while (cur !== -1) {
          const e = prevEdge[cur];
          if (!e) break;
          edges.push(e);
          cur = prev[cur];
        }
        return { edges: edges.reverse(), totalMin: g };
      }
      for (const e of adj[nd]) {
        if (done[e.to]) continue;
        if (kindFilter) {
          // 纯公交/纯地铁：乘车边按变体类别过滤；换乘边要求两端均为该类（bus↔metro 换乘边禁行）
          if (e.kind === 'ride' && variants[e.v].kind !== kindFilter) continue;
          if (e.kind === 'walk' && e.xf &&
              (nodes[nd].kind !== kindFilter || nodes[e.to].kind !== kindFilter)) continue;
        }
        const ng = g + e.min + xferExtra(e) + (penalties ? (penalties.get(e) || 0) : 0);
        if (ng < dist[e.to]) {
          dist[e.to] = ng; prev[e.to] = nd; prevEdge[e.to] = e;
          push(ng + h(e.to), ng, e.to);
        }
      }
      // 末端步行边：候选站 → 虚拟终点（门到门，末端距离进寻优代价）
      const ge = goalByNode.get(nd);
      if (ge && !done[T]) {
        const ng = g + ge.min;
        if (ng < dist[T]) {
          dist[T] = ng; prev[T] = nd; prevEdge[T] = ge;
          push(ng, ng, T);
        }
      }
    }
    return null;
  }

  /* ---------- 路径 → 乘段压缩 ---------- */
  // 首段步行边的 from 是虚拟起点（idx=-1），用真实起点坐标替代。
  // ride 边双向都有（反向边站序递减），按旅行顺序记节点链，不做升序假设
  function compress(edges, originPt) {
    const legs = [];
    let cur = null;
    const flush = () => { if (cur) { legs.push(cur); cur = null; } };
    for (const e of edges) {
      if (e.kind === 'ride') {
        if (cur && cur.type === 'ride' && cur.v === e.v) {
          const last = cur.pos[cur.pos.length - 1];
          if (e.ia === last) { cur.pos.push(e.ib); cur.min += e.min; continue; }
          if (e.ib === last) { cur.pos.push(e.ia); cur.min += e.min; continue; }
        }
        flush();
        cur = { type: 'ride', v: e.v, pos: [e.ia, e.ib], min: e.min };
      } else {
        if (cur && cur.type === 'walk') {
          cur.m += e.walkM || 0; cur.min += e.min; cur.toIdx = e.to;
          if (e.pts) cur.pts = (cur.pts || []).concat(e.pts.slice(1));
        } else {
          flush();
          cur = { type: 'walk', fromIdx: e.from, toIdx: e.to, min: e.min, m: e.walkM || 0, pts: e.pts || null };
        }
      }
    }
    flush();

    for (const leg of legs) {
      if (leg.type === 'ride') {
        const v = variants[leg.v];
        const seq = variantNodeSeq[leg.v];
        const pts = leg.pos.map(i => nodes[seq[i]]);
        leg.ref = v.ref; leg.name = v.name; leg.colour = v.colour; leg.lineKind = v.kind;
        leg.direction = v.to ? '往 ' + v.to : v.name;
        leg.i0 = leg.pos[0]; leg.i1 = leg.pos[leg.pos.length - 1];
        leg.stops = leg.pos.length - 1;
        leg.from = { name: pts[0].name, lat: pts[0].lat, lng: pts[0].lng };
        leg.to = { name: pts[pts.length - 1].name, lat: pts[pts.length - 1].lat, lng: pts[pts.length - 1].lng };
        leg.pts = pts.map(p => [p.lat, p.lng]);
      } else {
        leg.from = leg.fromIdx >= 0
          ? { name: nodes[leg.fromIdx].name, lat: nodes[leg.fromIdx].lat, lng: nodes[leg.fromIdx].lng }
          : { name: originPt.name, lat: originPt.lat, lng: originPt.lng };
        leg.to = { name: nodes[leg.toIdx].name, lat: nodes[leg.toIdx].lat, lng: nodes[leg.toIdx].lng };
      }
    }
    return legs;
  }

  /* ---------- 对外：规划 ---------- */
  // fromFix/toFix: {name, lat, lng, wgs:true|false, poi:true|false}
  // planTransitTopK：两点公共交通 Top-K（惩罚已走乘车边逼出不同走法），按总耗时排序
  // mode: 'transit'(步行+公交+地铁) | 'bus'(纯公交) | 'metro'(纯地铁)
  // pref: 'time' | 'xfer'——仅作用于 k=1 选拔（途经点链逐段）；k≥2 恒为"最快k-1+保底最少换乘"
  function planTransitTopK(fromFix, toFix, k = 3, mode = 'transit', pref = 'time') {
    const kindFilter = mode === 'bus' ? 'bus' : mode === 'metro' ? 'metro' : null;
    const kindLabel = mode === 'bus' ? '公交站' : mode === 'metro' ? '地铁站' : '站点';
    if (!grid) throw new Error('网络未构建');
    const toWgs = f => {
      if (f.wgs !== false) return f;
      const [a, b] = gcjToWgs(f.lat, f.lng);
      return { lat: a, lng: b };
    };
    const fromW = toWgs(fromFix), toW = toWgs(toFix);
    if (distM(fromW, toW) < 150) return { plans: [] };

    // 按类型分名额取候选（2026-10-29 用户问"为什么不是1号线+5号线"判例：
    // 只取最近 N 站时，老城密集公交站会占满名额，地铁站永远进不了候选，
    // 低换乘的地铁方案连参赛资格都没有）——公交/地铁各留坑位；
    // 纯公交/纯地铁模式下名额全给该车型
    const pick = (fix, w) => {
      const r = fix.poi ? P.WALK_RADIUS_POI_M : P.WALK_RADIUS_STATION_M;
      const all = queryNear(w.lat, w.lng, r).sort((a, b) => a[1] - b[1]);
      const cands = [];
      const perKind = {};
      for (const [i, d] of all) {
        if (cands.length >= P.ENDPOINTS_MAX) break;
        const k = nodes[i].kind;
        if (kindFilter && k !== kindFilter) continue;
        const quota = kindFilter ? P.ENDPOINTS_MAX : P.ENDPOINTS_PER_KIND;
        if ((perKind[k] || 0) >= quota) continue;
        perKind[k] = (perKind[k] || 0) + 1;
        cands.push([i, d]);
      }
      return { r, cands };
    };
    const fp = pick(fromFix, fromW), tp = pick(toFix, toW);
    if (!fp.cands.length) return { error: `起点「${fromFix.name}」周边 ${Math.round(fp.r)}m 内没有${kindLabel}，无法接入路网` };
    if (!tp.cands.length) return { error: `终点「${toFix.name}」周边 ${Math.round(tp.r)}m 内没有${kindLabel}，无法接入路网` };

    // 首末步行边：优先走路网快照真实路径（Dijkstra），缺失时退化为直线×绕行系数。
    // 真实路径的折线随边携带（walkM 与 pts），行程绘制走真路而非直线
    const roadnetOk = !!(window.RoadNet && RoadNet.stats());
    const walkEdge = (fromPt, nodeIdx, dStraight) => {
      const nd = nodes[nodeIdx];
      let wm = dStraight * P.WALK_DETOUR;
      let pts = null;
      if (roadnetOk) {
        const r = RoadNet.walkPath(fromPt, { lat: nd.lat, lng: nd.lng }, dStraight * 2 + 600);
        if (r && r.m > 0) {
          wm = r.m;
          pts = [[fromPt.lat, fromPt.lng], ...r.pts, [nd.lat, nd.lng]];
        }
      }
      return { min: wm * minPerM(P.WALK_KMH), kind: 'walk', walkM: wm, pts };
    };
    const startEdges = fp.cands.map(([i, d]) => {
      const e = walkEdge(fromW, i, d);
      e.to = i;
      return e;
    });
    // 门到门：虚拟终点 T + 候选站合成末端步行边，末端距离进 A* 代价
    //（否则只寻优到“半径内任一站点”，可能终在离目的地很远的站）
    const T = nodes.length;
    nodes.push({ name: toFix.name, lat: toW.lat, lng: toW.lng, kind: 'virt' });
    adj.push([]);
    try {
      const goalEdges = tp.cands.map(([i, d]) => {
        const e = walkEdge(toW, i, d);
        e.from = i; e.to = T;
        return e;
      });

      const plans = [];
      const seen = new Set();
      // 多目标入池（2026-10-29 用户令：换乘数与耗时都是重要排序因素，都要看）：
      // 倍率 1=纯最快、3=轻度少换乘、20=近乎最少换乘（长步行+1换也能翻盘）。
      // 两/三池合并去重后按时间排序，并保证"换乘最少"的方案始终在池内。
      // ⚠️罚空间每 profile 独立（2026-11-03 判例）：曾共用一张 penalties Map，
      // mul=1 先摸过的乘车边带着罚时进入 mul=20 搜索，把真正的 0 换乘最优压下去
      // （中山大学→广州塔：经中大站 36min/步行2.36km 被 45+ 的搜索代价压住，
      //   浮上来的是经鹭江 39min/步行2.73km 的更差 0 换乘变体）
      for (const xferMul of P.XFER_PROFILES) {
        const penalties = new Map();
        for (let iter = 0; iter < 3; iter++) {
          const r = astar(startEdges, goalEdges, toW, penalties, xferMul, kindFilter);
          if (!r || !r.edges.length) break;

          // 首末虚拟步行边补 from/to 节点（压缩函数依赖；直接写回 adj 边对象，幂等）
          let cur = -1;
          for (const e of r.edges) { e.from = cur; cur = e.to; }
          const legs = compress(r.edges, { name: fromFix.name, lat: fromW.lat, lng: fromW.lng });

          let walkM = 0, rideM = 0, totalMin = 0, rides = 0;
          for (const leg of legs) {
            totalMin += leg.min;
            if (leg.type === 'walk') walkM += leg.m;
            else { rideM += pathM(leg.pts); rides++; }
          }
          const summary = {
            totalMin: Math.round(totalMin), transfers: Math.max(0, rides - 1),
            walkM: Math.round(walkM), rideKm: Math.round(rideM / 100) / 10
          };
          // 方案指纹 = 乘车段序列（去重：惩罚重跑可能收敛回同一走法）
          const sig = legs.filter(l => l.type === 'ride').map(l => l.ref + '@' + l.from.name).join('>')
            + '#' + summary.transfers;
          const dup = seen.has(sig);
          // 惩罚本路径的乘车边（含孪生反向边）：不重复给标准罚，重复给加倍罚
          const delta = Math.max(3, Math.round(totalMin * (dup ? 0.6 : 0.3)));
          for (const e of r.edges) {
            if (e.kind === 'ride' && e.tw) {
              penalties.set(e, (penalties.get(e) || 0) + delta);
              penalties.set(e.tw, (penalties.get(e.tw) || 0) + delta);
            }
          }
          if (!dup) { seen.add(sig); plans.push({ legs, summary, mode }); }
        }
      }
      plans.sort((a, b) => a.summary.totalMin - b.summary.totalMin);
      {
        // 选拔（2026-11-03 用户令"优先时间那几段都优先时间，优先换乘那几段都优先换乘"）：
        // k=1 跟随调用方口径——xfer=换乘最少优先（池按耗时序，reduce 取首个最少换乘=同数最快；
        // 步行换少换乘是显式代价，判例：点名 50min/1换 胜 41min/3换）；time=纯最快。
        // k≥2 = 最快 k-1 + 保底最少换乘必在池内（UI 多方案列表，用户自己挑）。
        const minXfer = plans.reduce((m, p) =>
          p.summary.transfers < m.summary.transfers ? p : m, plans[0]);
        if (k === 1) return { plans: [pref === 'xfer' && minXfer ? minXfer : plans[0]] };
        const kept = plans.slice(0, k);
        if (k > 1 && minXfer && !kept.includes(minXfer)) kept[kept.length - 1] = minXfer;
        kept.sort((a, b) => a.summary.totalMin - b.summary.totalMin);
        return { plans: kept };
      }
    } finally {
      nodes.pop(); adj.pop();   // 虚拟终点用完即撤
    }
  }

  /* ---------- 出行模式分发与途经点链 ---------- */

  const sumLegs = legs => {
    let walkM = 0, rideM = 0, totalMin = 0, rides = 0;
    for (const leg of legs) {
      if (leg.type === 'wp') continue;   // 途经点标记无几何
      totalMin += leg.min;
      if (leg.type === 'walk') walkM += leg.m;
      else { rideM += pathM(leg.pts); rides++; }
    }
    return {
      totalMin: Math.round(totalMin), transfers: Math.max(0, rides - 1),
      walkM: Math.round(walkM), rideKm: Math.round(rideM / 100) / 10
    };
  };
  const wgsOf = f => f.wgs === false
    ? (([a, b]) => ({ lat: a, lng: b }))(gcjToWgs(f.lat, f.lng))
    : { lat: f.lat, lng: f.lng };
  const fixPt = f => ({ name: f.name, lat: f.lat, lng: f.lng });

  /** 纯步行链：全程步行网（每段有界 Dijkstra），途经点顺序连缀 */
  function planWalkChain(fixes) {
    if (!window.RoadNet || !RoadNet.stats())
      return { error: '步行模式需要路网快照（data/routing-graph.json），当前未装载' };
    const legs = [];
    const segments = [];
    for (let i = 0; i < fixes.length - 1; i++) {
      const a = wgsOf(fixes[i]), b = wgsOf(fixes[i + 1]);
      const straight = distM(a, b);
      const r = RoadNet.walkPath(a, b, straight * 1.8 + 3000);
      if (!r) return { error: `「${fixes[i].name}」→「${fixes[i + 1].name}」之间未找到可步行路径（可能隔江或距离过远）` };
      legs.push({
        type: 'walk', keep: true, min: r.m * minPerM(P.WALK_KMH), m: r.m, pts: r.pts,
        from: { name: fixes[i].name, lat: a.lat, lng: a.lng },
        to: { name: fixes[i + 1].name, lat: b.lat, lng: b.lng }
      });
      segments.push({ label: `${fixes[i].name} → ${fixes[i + 1].name}`, totalMin: Math.round(r.m * minPerM(P.WALK_KMH)) });
      if (i < fixes.length - 2) legs.push({ type: 'wp', name: fixes[i + 1].name });
    }
    return { plans: [{ legs, summary: sumLegs(legs), mode: 'walk', segments }] };
  }

  /** 驾车链：路网有向图（oneway+类别速度）。两点时出 最快/最短 双方案，多途经点为顺序连缀 */
  function planDriveChain(fixes) {
    if (!window.RoadNet || !RoadNet.stats())
      return { error: '驾车模式需要路网快照（data/routing-graph.json），当前未装载' };
    const mkDrive = (a, b, r, tag) => ({
      type: 'drive', keep: true, min: r.min, m: r.m, pts: r.pts, tag,
      from: { name: a.name, lat: wgsOf(a).lat, lng: wgsOf(a).lng },
      to: { name: b.name, lat: wgsOf(b).lat, lng: wgsOf(b).lng }
    });
    if (fixes.length === 2) {
      const a = wgsOf(fixes[0]), b = wgsOf(fixes[1]);
      const straight = distM(a, b);
      const cap = straight * 2.5 + 3000;
      const rFast = RoadNet.drivePath(a, b, cap, { cost: 'time' });
      if (!rFast) return { error: `「${fixes[0].name}」→「${fixes[1].name}」之间未找到可驾车路径` };
      const plans = [{
        legs: [mkDrive(fixes[0], fixes[1], rFast, '最快')],
        summary: { totalMin: rFast.min, transfers: 0, walkM: 0, rideKm: Math.round(rFast.m / 100) / 10 },
        mode: 'drive', tag: '最快'
      }];
      const rShort = RoadNet.drivePath(a, b, cap, { cost: 'dist' });
      if (rShort && Math.abs(rShort.m - rFast.m) > rFast.m * 0.02) {
        plans.push({
          legs: [mkDrive(fixes[0], fixes[1], rShort, '最短')],
          summary: { totalMin: rShort.min, transfers: 0, walkM: 0, rideKm: Math.round(rShort.m / 100) / 10 },
          mode: 'drive', tag: '最短'
        });
      }
      plans.sort((x, y) => x.summary.totalMin - y.summary.totalMin);
      return { plans };
    }
    // 多途经点：顺序逐段最快
    const legs = [];
    const segments = [];
    let totalMin = 0, totalM = 0;
    for (let i = 0; i < fixes.length - 1; i++) {
      const a = wgsOf(fixes[i]), b = wgsOf(fixes[i + 1]);
      const r = RoadNet.drivePath(a, b, distM(a, b) * 2.5 + 3000, { cost: 'time' });
      if (!r) return { error: `「${fixes[i].name}」→「${fixes[i + 1].name}」之间未找到可驾车路径` };
      legs.push(mkDrive(fixes[i], fixes[i + 1], r, ''));
      segments.push({ label: `${fixes[i].name} → ${fixes[i + 1].name}`, totalMin: r.min });
      totalMin += r.min; totalM += r.m;
      if (i < fixes.length - 2) legs.push({ type: 'wp', name: fixes[i + 1].name });
    }
    return { plans: [{
      legs,
      summary: { totalMin: Math.round(totalMin), transfers: 0, walkM: 0, rideKm: Math.round(totalM / 100) / 10 },
      mode: 'drive', segments
    }] };
  }

  /** 公共交通链：纯公交/纯地铁为 transit 图的车型过滤；途经点逐段连缀（每段按同一口径独立选拔） */
  function planTransitChain(fixes, k, mode, pref) {
    if (fixes.length === 2) return planTransitTopK(fixes[0], fixes[1], k, mode, pref);
    const legs = [];
    const segments = [];
    let totalMin = 0, walkM = 0, rideKm = 0, transfers = 0;
    for (let i = 0; i < fixes.length - 1; i++) {
      const r = planTransitTopK(fixes[i], fixes[i + 1], 1, mode, pref);
      if (r.error) return { error: r.error };
      const p = r.plans[0];
      if (!p) continue;   // 两点过近
      if (legs.length) legs.push({ type: 'wp', name: fixes[i].name });
      for (const leg of p.legs) legs.push(leg);
      segments.push({ label: `${fixes[i].name} → ${fixes[i + 1].name}`, totalMin: p.summary.totalMin });
      totalMin += p.summary.totalMin;
      walkM += p.summary.walkM;
      rideKm += p.summary.rideKm;
      transfers += p.summary.transfers + (i > 0 ? 1 : 0);
    }
    return { plans: [{
      legs,
      summary: { totalMin: Math.round(totalMin), transfers, walkM: Math.round(walkM), rideKm: Math.round(rideKm * 10) / 10 },
      mode, segments
    }] };
  }

  /**
   * 对外总入口。fixes = 有序途经点数组 [{name,lat,lng,wgs,poi}, ...]（≥2 个，含起终点）。
   * mode: 'transit'(公共交通, 默认) | 'drive'(驾车) | 'walk'(纯步行) | 'bus'(纯公交) | 'metro'(纯地铁)
   * pref: 'time'(每段最快, 默认) | 'xfer'(每段最少换乘, 同数取最快)——途经点链逐段
   *       按同一口径独立选拔（2026-11-03 用户令"优先时间那几段都优先时间，优先换乘
   *       那几段都优先换乘，本质就是当成几段单独计算"）；两点查询走 Top-K 池不受影响。
   */
  function planK(fixes, k = 3, mode = 'transit', pref = 'time') {
    if (!Array.isArray(fixes) || fixes.length < 2) return { error: '起终点缺失' };
    if (fixes.some(f => !f || !Number.isFinite(f.lat) || !Number.isFinite(f.lng)))
      return { error: '存在未解析的起终点' };
    if (mode === 'walk') return planWalkChain(fixes);
    if (mode === 'drive') return planDriveChain(fixes);
    return planTransitChain(fixes, k, mode, pref === 'xfer' ? 'xfer' : 'time');
  }

  /** 单方案便捷口（历史调用方语义：{legs, summary} 或 {error}） */
  function plan(fromFix, toFix) {
    const r = planTransitTopK(fromFix, toFix, 1, 'transit');
    if (r.error) return { error: r.error };
    if (!r.plans.length) return { legs: [], summary: { totalMin: 0, transfers: 0, walkM: 0, rideKm: 0 } };
    return r.plans[0];
  }

  /* ---------- 同名站实例聚类（>500m 算不同实例） ---------- */
  function instancesOf(name) {
    const e = nameIdx && nameIdx.get(normName(name));
    if (!e) return [];
    const clusters = [];
    for (const i of e.nodeIds) {
      const nd = nodes[i];
      let c = clusters.find(c => distM(c, nd) <= P.NAME_CLUSTER_M);
      if (!c) { c = { lat: nd.lat, lng: nd.lng, lines: [], kinds: new Set(), nodeIds: [] }; clusters.push(c); }
      c.nodeIds.push(i);
      c.kinds.add(nd.kind);
      const v = variants[nd.v];
      const label = v.kind === 'metro' ? v.name : v.ref;
      if (!c.lines.some(x => x.label === label)) c.lines.push({ label, kind: v.kind, colour: v.colour });
    }
    return clusters.map(c => ({
      lat: c.lat, lng: c.lng, lines: c.lines.slice(0, 5), kinds: [...c.kinds],
      hint: nearestHint(c, e.name)
    }));
  }

  // 邻近地标：离该实例最近的其他站名前 2 个（同名消歧用）
  function nearestHint(pt, selfName) {
    const self = normName(selfName);
    return queryNear(pt.lat, pt.lng, 600)
      .filter(([i]) => normName(nodes[i].name) !== self)
      .sort((a, b) => a[1] - b[1])
      .slice(0, 2)
      .map(([i]) => nodes[i].name)
      .filter((n, i, a) => a.indexOf(n) === i);
  }

  /** 站名建议：前缀命中在前、包含在后，limit 条（实例信息由视图按需调 instancesOf） */
  function suggest(q, limit = 8) {
    const nq = normName(q);
    if (!nq || !nameIdx) return [];
    const hits = [];
    for (const [k, e] of nameIdx) {
      let score = -1;
      if (k.startsWith(nq)) score = 0;
      else if (k.includes(nq)) score = 1;
      if (score < 0) continue;
      hits.push([score, k.length, k, e.name]);
    }
    hits.sort((a, b) => a[0] - b[0] || a[1] - b[1] || (a[2] < b[2] ? -1 : 1));
    return hits.slice(0, limit).map(h => ({ name: h[3] }));
  }

  /** 自动锚定：同名多实例时取离参照点最近的；无参照取第一个 */
  function resolveInstance(name, refPt) {
    const inst = instancesOf(name);
    if (!inst.length) return null;
    if (!refPt || inst.length === 1) return inst[0];
    return inst.reduce((best, c) => distM(refPt, c) < distM(refPt, best) ? c : best, inst[0]);
  }

  /** 地图拾取：半径内最近站（含距离） */
  function nearestNode(lat, lng, maxM) {
    if (!grid) return null;
    const cands = queryNear(lat, lng, maxM).sort((a, b) => a[1] - b[1]);
    if (!cands.length) return null;
    const [i, d] = cands[0];
    const nd = nodes[i];
    return { name: nd.name, lat: nd.lat, lng: nd.lng, kind: nd.kind, m: Math.round(d) };
  }

  /* ---------- 地名/地标兜底（唯一 API 场景）：高德 → Overpass，结果缓存 ---------- */
  const poiMem = new Map();
  function poiCacheLoad(kw) {
    if (poiMem.has(kw)) return poiMem.get(kw);
    try {
      const j = JSON.parse(localStorage.getItem('gzbus.poi.v1.' + kw));
      if (j && Date.now() - j.at < P.POI_CACHE_TTL) { poiMem.set(kw, j.items); return j.items; }
    } catch { /* 无缓存 */ }
    return null;
  }
  function poiCacheSave(kw, items) {
    poiMem.set(kw, items);
    try {
      localStorage.setItem('gzbus.poi.v1.' + kw, JSON.stringify({ at: Date.now(), items }));
      // 防膨胀：键超 120 条按最旧清到 80
      const keys = Object.keys(localStorage).filter(k => k.startsWith('gzbus.poi.v1.'));
      if (keys.length > 120) {
        keys.map(k => [k, (JSON.parse(localStorage.getItem(k)) || {}).at || 0])
          .sort((a, b) => a[1] - b[1]).slice(0, keys.length - 80)
          .forEach(([k]) => localStorage.removeItem(k));
      }
    } catch { /* 配额满放弃 */ }
  }

  // 关键词降级序列：复合叫法（网易高唐一期 / XX园区2期大厦…）逐级剥掉尾缀通称，
  // 整词查不到时按关联度落到真实 POI，而不是直接报「未找到」
  function kwLadder(nk) {
    const out = [nk];
    let cur = nk;
    while (cur.length > 2) {
      const next = cur
        .replace(/(一|二|三|四|1|2|3|4|[Ii]{1,3}|[Aa-dA-D])期$/, '')
        .replace(/(园区|大厦|大楼|广场|中心|基地|写字楼|新城)$/, '');
      if (next === cur || next.length < 2) break;
      out.push(next);
      cur = next;
    }
    return out;
  }

  async function findPoi(kw) {
    const nk = normName(kw);
    if (!nk) return { items: [] };
    const cached = poiCacheLoad(nk);
    if (cached) return { items: cached, source: 'cache' };

    let items = [];
    let source = '';
    // ① 高德 place/text（内置默认 key，可在「高德补源」覆盖；返回 GCJ-02 与底图同系）
    if (window.AMapLine && AMapLine.available()) {
      const amapQuery = async kwd => {
        const c = AMapLine.getCreds();
        const res = await fetch('https://restapi.amap.com/v3/place/text?key=' + encodeURIComponent(c.key) +
          '&keywords=' + encodeURIComponent(kwd) + '&city=' + encodeURIComponent('广州') +
          '&citylimit=true&offset=8&extensions=base');
        const j = await res.json();
        if (String(j.status) !== '1' || !Array.isArray(j.pois)) return { ok: false, pois: [] };
        return { ok: true, pois: j.pois.map(p => {
          const [lng, lat] = String(p.location || ',').split(',').map(Number);
          return Number.isFinite(lat) && Number.isFinite(lng) ? {
            name: p.name || nk, lat, lng, wgs: false, poi: true,
            district: [p.pname, p.address].filter(Boolean).join(' · '),
            type: p.type || ''
          } : null;
        }).filter(Boolean) };
      };
      for (const kwd of kwLadder(nk)) {
        try {
          const r = await amapQuery(kwd);
          if (!r.ok) break;               // key/配额问题：换词无意义，直接落 Overpass
          items = r.pois;
        } catch { break; }                // 网络不通：同上
        if (items.length) { source = 'amap'; break; }
      }
    }
    // ② Overpass 按名查 POI（免 key 最后手段；OSM 国内 POI 稀疏、更慢）
    //    正则用降级序列的并集（网易高唐一期|网易高唐|网易），整串叫法也能命中
    if (!items.length) {
      const alts = kwLadder(nk).map(s => s.replace(/["\\]/g, ''));
      const safe = alts.join('|');
      const q = '[out:json][timeout:25];(' +
        `node(${GZ_BBOX})["name"~"${safe}",i]["amenity"];` +
        `node(${GZ_BBOX})["name"~"${safe}",i]["shop"];` +
        `node(${GZ_BBOX})["name"~"${safe}",i]["tourism"];` +
        `node(${GZ_BBOX})["name"~"${safe}",i]["leisure"];` +
        `node(${GZ_BBOX})["name"~"${safe}",i]["office"];` +
        `way(${GZ_BBOX})["name"~"${safe}",i]["amenity"];` +
        `way(${GZ_BBOX})["name"~"${safe}",i]["tourism"];` +
        `way(${GZ_BBOX})["name"~"${safe}",i]["building"];` +
        ');out center tags 12;';
      try {
        const json = await Overpass.runQuery(q);
        items = (json.elements || []).map(el => {
          const lat = el.lat != null ? el.lat : el.center && el.center.lat;
          const lng = el.lon != null ? el.lon : el.center && el.center.lon;
          if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
          const t = el.tags || {};
          return { name: t.name || nk, lat, lng, wgs: true, poi: true,
            district: t['addr:district'] || t['addr:street'] || '',
            type: t.amenity || t.shop || t.tourism || t.leisure || t.office || t.building || '' };
        }).filter(Boolean);
        // 关联度排序：名中命中的降级词越长越靠前（「网易总部」> 只命中「网易」的大厦）
        const rank = name => Math.max(0, ...alts.filter(a => name.includes(a)).map(a => a.length));
        items.sort((a, b) => rank(b.name) - rank(a.name));
        source = 'osm';
      } catch { /* 双源皆失败 */ }
    }
    if (items.length) poiCacheSave(nk, items);
    return { items, source, error: items.length ? '' : '未找到该地名' };
  }

  /* ---------- 统计（状态栏展示用） ---------- */
  function stats() { return { nodesN: nodes.length, variantsN: variants.length, buildMs }; }

  return { ready, plan, planK, suggest, instancesOf, resolveInstance, nearestNode, findPoi, stats, P, gcjToWgs };
})();
