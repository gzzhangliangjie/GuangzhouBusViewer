// 全市路网快照拉取（Electron 网络栈，分片断点续拉 → 合并压缩为 data/road-network-snapshot.json）
// 一份数据两个消费方：①路线规划步行段真实路网 ②道路查看本地检索（离线秒出）
// 范围：way["highway"] 全类别（含无名小径——步行网必需；motorway/trunk 由消费方自行排除）
// 用法: electron test/pull-roadnet.js
const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

const ROOT = path.join(__dirname, '..');
const OUTDIR = path.join(ROOT, 'assets', '_pull-roadnet');
const FINAL = path.join(ROOT, 'data', 'road-network-snapshot.json');
const MIRRORS = [
  'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
  'https://overpass-api.de/api/interpreter',
  'https://overpass.kumi.systems/api/interpreter',
  'https://overpass.private.coffee/api/interpreter'
];
// 8x8 分片（单片 0.2°×0.2° 级别，响应 5-25MB 量级；4x4 曾单片超时全败）
const LAT0 = 22.35, LAT1 = 23.94, LON0 = 112.95, LON1 = 114.03, N = 8;

app.disableHardwareAcceleration();
app.setPath('userData', path.join(ROOT, 'assets', '_pull-roadnet-profile'));
app.whenReady().then(async () => {
  if (!fs.existsSync(OUTDIR)) fs.mkdirSync(OUTDIR, { recursive: true });
  const win = new BrowserWindow({ width: 500, height: 300, show: false });
  await win.loadFile(path.join(ROOT, 'index.html'));
  const log = (...a) => console.log('[roadnet]', ...new Date().toISOString().slice(11, 19), ...a);

  async function ask(query, tries = 4, timeoutMs = 240000) {
    for (let t = 0; t < tries; t++) {
      const r = await win.webContents.executeJavaScript(`(async () => {
        const q = ${JSON.stringify(query)};
        const attempt = async m => {
          const ctrl = new AbortController();
          const to = setTimeout(() => ctrl.abort(), ${timeoutMs});
          try {
            const res = await fetch(m, {
              method: 'POST',
              headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
              body: 'data=' + encodeURIComponent(q),
              signal: ctrl.signal
            });
            const text = await res.text();
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const j = JSON.parse(text);
            if (j.remark && /error/i.test(j.remark)) throw new Error(String(j.remark).slice(0, 60));
            return text;
          } finally { clearTimeout(to) }
        };
        try { return JSON.stringify(await Promise.any(${JSON.stringify(MIRRORS)}.map(attempt))); }
        catch (e) { return JSON.stringify({ error: true, msg: String(e && e.message || e).slice(0, 120) }); }
      })()`);
      const parsed = JSON.parse(r);
      if (!parsed.error) return parsed;
      log('  失败', (parsed.msg || '').slice(0, 100), t + 1 + '/' + tries);
      if (t < tries - 1) await new Promise(res => setTimeout(res, 12000));
    }
    return null;
  }

  // ---------- A: 分片拉取（断点续拉：单片文件存在即跳过；ROADNET_MERGE_ONLY=1 跳过拉取直接合并已有片） ----------
  const MERGE_ONLY = process.env.ROADNET_MERGE_ONLY === '1';
  let okTiles = 0, failTiles = [];
  for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) {
    const tf = path.join(OUTDIR, `tile-${i}-${j}.json`);
    if (fs.existsSync(tf) && fs.statSync(tf).size > 100) { okTiles++; continue; }
    if (MERGE_ONLY) continue;
    const s = (LAT0 + (LAT1 - LAT0) / N * i).toFixed(4), n = (LAT0 + (LAT1 - LAT0) / N * (i + 1)).toFixed(4);
    const w = (LON0 + (LON1 - LON0) / N * j).toFixed(4), e = (LON0 + (LON1 - LON0) / N * (j + 1)).toFixed(4);
    log(`tile-${i}-${j} 拉取中…`);
    const q = `[out:json][timeout:200];way(${s},${w},${n},${e})["highway"];out geom tags;`;
    const t0 = Date.now();
    const r = await ask(q);
    if (!r) { log('tile', i, j, '全败（重跑可续）'); failTiles.push(`${i}-${j}`); continue; }
    fs.writeFileSync(tf, r);
    okTiles++;
    log(`tile-${i}-${j} 保存 ${(r.length / 1048576).toFixed(1)}MB ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  log(`已有分片 ${okTiles}/${N * N}${MERGE_ONLY ? '（MERGE_ONLY）' : ''}`);
  if (failTiles.length) { log('分片失败：', failTiles.join(' '), '——重跑续拉'); app.exit(1); return; }

  // ---------- B: 合并 → 紧凑路由图派生物（Valhalla 式：压缩在构建期做，App 端只解码） ----------
  // 节点=交叉路口/端点（非路口形状点降采样进边形状，差分编码）；CSR 邻接双向槽位；
  // 每边携带 类别枚举/oneway/maxspeed/路名id —— 步行与驾车两模式共用同一张图
  log('合并分片（紧凑路由图）…');
  const CLS_CODES = {
    motorway: 0, motorway_link: 1, trunk: 2, trunk_link: 3, primary: 4, primary_link: 5,
    secondary: 6, secondary_link: 7, tertiary: 8, tertiary_link: 9, residential: 10,
    unclassified: 11, living_street: 12, service: 13, track: 14, footway: 15, path: 16,
    pedestrian: 17, steps: 18, cycleway: 19, road: 20, busway: 21, bus_guideway: 22,
    raceway: 23, construction: 24
  };
  const gidMap = new Map();   // 数值键（量化坐标差），避免字符串 Map 的内存开销
  const nLA = [], nLN = [];
  const rawWayPts = [];       // 每路面的 gid 链（普通数组）
  const rawWayMeta = [];      // {c, n, o, ms}
  let rawWays = 0;
  const seenWayIds = new Set();   // ⚠️跨分片去重：一条路横跨多片会在每片各输出一次，
                                  // 不去重则节点计数翻倍→全图被误判为路口（实测 109 万"路口"判例）
  const KEY_BASE_LA = 2235000, KEY_SPAN_LN = 1080000, KEY_BASE_LN = 11295000;
  for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) {
    const tf = path.join(OUTDIR, `tile-${i}-${j}.json`);
    if (!fs.existsSync(tf)) continue;
    const els = JSON.parse(fs.readFileSync(tf, 'utf8')).elements || [];
    for (const el of els) {
      if (el.type !== 'way' || !Array.isArray(el.geometry) || el.geometry.length < 2) continue;
      if (seenWayIds.has(el.id)) continue;
      seenWayIds.add(el.id);
      if (el.tags && el.tags.highway === 'construction') continue;
      const pts = [];
      for (const g of el.geometry) {
        if (!g || !Number.isFinite(g.lat) || !Number.isFinite(g.lon)) continue;
        const la = Math.round(g.lat * 1e5), ln = Math.round(g.lon * 1e5);
        const key = (la - KEY_BASE_LA) * KEY_SPAN_LN + (ln - KEY_BASE_LN);
        let ix = gidMap.get(key);
        if (ix === undefined) { ix = nLA.length; gidMap.set(key, ix); nLA.push(la); nLN.push(ln); }
        pts.push(ix);
      }
      if (pts.length < 2) continue;
      rawWays++;
      const tags = el.tags || {};
      const ow = tags.oneway === 'yes' || tags.oneway === '1' ? 1 : (tags.oneway === '-1' ? -1 : 0);
      const ms = parseInt((tags.maxspeed || '').replace(/[^0-9].*$/, ''), 10);
      rawWayPts.push(pts);
      rawWayMeta.push({ c: CLS_CODES[tags.highway] ?? CLS_CODES.road, n: tags.name || '', o: ow, ms: Number.isFinite(ms) && ms > 0 ? Math.min(ms, 120) : 0 });
    }
  }
  gidMap.clear();
  const nodeN = nLA.length;
  log(`  ${nodeN} 原始节点 / ${rawWayPts.length} 路面`);

  // 交叉路口识别：出现于 ≥2 个位置（跨路面交点/分片边界共享点）或路面端点
  const cnt = new Int32Array(nodeN);
  const isEnd = new Uint8Array(nodeN);
  for (const pts of rawWayPts) {
    for (const g of pts) cnt[g]++;
    isEnd[pts[0]] = 1; isEnd[pts[pts.length - 1]] = 1;
  }
  const jid = new Int32Array(nodeN).fill(-1);
  const jLA = [], jLN = [];
  for (let g = 0; g < nodeN; g++) {
    if (cnt[g] >= 2 || isEnd[g]) { jid[g] = jLA.length; jLA.push(nLA[g]); jLN.push(nLN[g]); }
  }
  const J = jLA.length;
  const SJ = Math.sqrt((J || 1));   // 日志用
  log(`  ${J} 路口节点`);

  // 边提取：每路面沿链在路口处切段；形状自适应抽稀（相邻保留点 ≥~20m）
  const eA = [], eB = [], eM = [], eCls = [], eOw = [], eMs = [], eName = [];
  const shFlat = [];   // 每边形状：首点绝对量化对，后续差分
  const shOff = [0];
  const nameIdMap = new Map();
  const names = [];
  for (let wi = 0; wi < rawWayPts.length; wi++) {
    const pts = rawWayPts[wi], meta = rawWayMeta[wi];
    let nameId = -1;
    if (meta.n) {
      nameId = nameIdMap.get(meta.n);
      if (nameId === undefined) { nameId = names.length; nameIdMap.set(meta.n, nameId); names.push(meta.n); }
    }
    let segStart = pts[0], segM = 0, shape = [[nLA[pts[0]], nLN[pts[0]]]];
    let lastLa = nLA[pts[0]], lastLn = nLN[pts[0]], lastKeepLa = lastLa, lastKeepLn = lastLn;
    for (let k = 1; k < pts.length; k++) {
      const g = pts[k], la = nLA[g], ln = nLN[g];
      const dy = (la - lastLa) * 1e-5 * 110540, dx = (ln - lastLn) * 1e-5 * Math.cos(23.1 * Math.PI / 180) * 111320;
      segM += Math.hypot(dx, dy);
      lastLa = la; lastLn = ln;
      if (Math.hypot((la - lastKeepLa) * 1e-5 * 111320 * Math.cos(23.1 * Math.PI / 180), (ln - lastKeepLn) * 1e-5 * 110540) >= 30) {
        if (shape.length < 4) shape.push([la, ln]);
        lastKeepLa = la; lastKeepLn = ln;
      }
      if (jid[g] >= 0 || k === pts.length - 1) {
        if (jid[g] !== jid[segStart] || segStart !== g) {   // 自环（量化重合点）跳过
          shape.push([la, ln]);
          eA.push(jid[segStart]); eB.push(jid[g]);
          eM.push(Math.max(1, Math.round(segM)));
          eCls.push(meta.c); eOw.push(meta.o); eMs.push(meta.ms); eName.push(nameId);
          let pla = 0, pln = 0;
          for (let si = 0; si < shape.length; si++) {
            const laq = shape[si][0], lnq = shape[si][1];
            if (si === 0) { shFlat.push(laq, lnq); pla = laq; pln = lnq; }
            else { shFlat.push(laq - pla, lnq - pln); pla = laq; pln = lnq; }
          }
          shOff.push(shFlat.length);
        }
        segStart = g; segM = 0; shape = [[la, ln]];
      }
    }
  }
  rawWayPts.length = 0;
  const E = eA.length;

  // CSR 双向槽位：每边占 a、b 两槽；形状只存 a→b 方向，反向槽带 rev 标记
  const deg = new Int32Array(J);
  for (let e = 0; e < E; e++) { deg[eA[e]]++; deg[eB[e]]++; }
  const eOff = new Int32Array(J + 1);
  for (let j = 0; j < J; j++) eOff[j + 1] = eOff[j] + deg[j];
  const slotN = eOff[J];
  const adjNbr = new Int32Array(slotN);
  const adjE = new Int32Array(slotN);
  const adjRev = new Int8Array(slotN);
  const cursor = Int32Array.from(eOff);
  for (let e = 0; e < E; e++) {
    adjNbr[cursor[eA[e]]] = eB[e]; adjE[cursor[eA[e]]] = e; adjRev[cursor[eA[e]]] = 0; cursor[eA[e]]++;
    adjNbr[cursor[eB[e]]] = eA[e]; adjE[cursor[eB[e]]] = e; adjRev[cursor[eB[e]]] = 1; cursor[eB[e]]++;
  }

  const graph = {
    at: Date.now(), ver: 1, bbox: [LAT0, LON0, LAT1, LON1],
    clsCodes: CLS_CODES,
    J, nodeN,
    nodes: [],   // 展开成 flat：[la0, ln0, la1, ln1, ...]
    E, eOff: [...eOff], adjNbr: [...adjNbr], adjE: [...adjE], adjRev: [...adjRev],
    eM: eM.map(v => Math.round(v)),
    eCls, eOw, eMs, eName,
    shOff, shapes: shFlat,
    names
  };
  for (let j = 0; j < J; j++) graph.nodes.push(jLA[j], jLN[j]);
  const FINAL2 = path.join(ROOT, 'data', 'routing-graph.json');
  fs.writeFileSync(FINAL2, JSON.stringify(graph));
  const mb2 = (fs.statSync(FINAL2).size / 1048576).toFixed(1);
  log(`完成：${J} 路口 / ${E} 边（槽位 ${slotN}）/ 形状点 ${shFlat.length} / 名 ${names.length} → ${FINAL2} ${mb2}MB`);
  app.exit(0);
});
