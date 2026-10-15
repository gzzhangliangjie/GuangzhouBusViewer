// 全市公交数据定量分批拉取（Electron 网络栈）
// A: 每分片轻量拉 relation id 集（响应小、成功率高） → 合并 ids + tags 索引
// B: 按每批 120 个 id 拉完整几何（server 负载可预测）→ 断点续拉
// 产出 assets/_pull/ids.json + batch-NNN.json
// 用法: electron test/pull-bus.js
const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

const OUTDIR = path.join(__dirname, '..', 'assets', '_pull');
const MIRRORS = [
  'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
  'https://overpass-api.de/api/interpreter',
  'https://overpass.kumi.systems/api/interpreter',
  'https://overpass.private.coffee/api/interpreter'
];
const BATCH = 120;

app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
app.on('ready', () => {});
const pathMod = require('path');
app.setPath && app.setPath('userData', pathMod.join(__dirname, '..', 'assets', '_pull-profile'));
app.whenReady().then(async () => {
  if (!fs.existsSync(OUTDIR)) fs.mkdirSync(OUTDIR, { recursive: true });
  const win = new BrowserWindow({ width: 500, height: 300, show: false });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));
  const log = (...a) => console.log('[pull]', ...new Date().toISOString().slice(11, 19), ...a);

  async function runInPage(query, timeoutMs = 300000) {
    return JSON.parse(await win.webContents.executeJavaScript(`(async () => {
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
          return { mirror: m, text };
        } finally { clearTimeout(to) }
      };
      try { return JSON.stringify(await Promise.any(${JSON.stringify(MIRRORS)}.map(attempt))); }
      catch (e) { return JSON.stringify({ error: true }); }
    })()`));
  }
  async function ask(query, tries, timeoutMs) {
    for (let t = 0; t < tries; t++) {
      const r = await runInPage(query, timeoutMs);
      if (!r.error) return r;
      log('  失败', JSON.stringify(r.error).slice(0, 160), t + 1 + '/' + tries);
      if (t < tries - 1) await new Promise(res => setTimeout(res, 12000));
    }
    return null;
  }

  // ---------- A: 全量 relation id+tags（分片轻查询，每片独立落盘断点续拉） ----------
  const LAT0 = 22.40, LAT1 = 23.95, LON0 = 112.90, LON1 = 114.50, N = 3;
  const idFile = path.join(OUTDIR, 'ids.json');
  let rels = new Map();   // id -> tags
  if (fs.existsSync(idFile)) {
    rels = new Map(JSON.parse(fs.readFileSync(idFile, 'utf-8')).map(t => [t.id, t.tags]));
    log('ids.json 已有', rels.size, '条');
  } else {
    for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) {
      const tf = path.join(OUTDIR, `ids-tile-${i}-${j}.json`);
      let tileEls = null;
      if (fs.existsSync(tf) && fs.statSync(tf).size > 10) {
        tileEls = JSON.parse(fs.readFileSync(tf, 'utf-8'));
        log(`A: tile-${i}-${j} 已有 ${tileEls.length} 条`);
      } else {
        const s = (LAT0 + (LAT1 - LAT0) / N * i).toFixed(4), n = (LAT0 + (LAT1 - LAT0) / N * (i + 1)).toFixed(4);
        const w = (LON0 + (LON1 - LON0) / N * j).toFixed(4), e = (LON0 + (LON1 - LON0) / N * (j + 1)).toFixed(4);
        log(`A: tile-${i}-${j} ids+tags…`);
        const r = await ask(`[out:json][timeout:120];rel(${s},${w},${n},${e})["route"="bus"];out tags;`, 4, 180000);
        if (!r) { log('tile', i, j, '四次全败，终止（重跑可续）'); app.exit(1); return; }
        tileEls = (JSON.parse(r.text).elements || []).map(el => ({ id: el.id, tags: el.tags || {} }));
        fs.writeFileSync(tf, JSON.stringify(tileEls));
      }
      for (const t of tileEls) rels.set(t.id, t.tags);
      log(`  累计 ${rels.size}`);
    }
    fs.writeFileSync(idFile, JSON.stringify([...rels.entries()].map(([id, tags]) => ({ id, tags }))));
    log('A 完成：', rels.size, '条线路 relation');
  }

  // ---------- B: 分批拉几何 ----------
  const ids = [...rels.keys()].sort((a, b) => a - b);
  const batches = Math.ceil(ids.length / BATCH);
  log('B: 共', ids.length, '条 /', batches, '批');
  for (let b = 0; b < batches; b++) {
    const f = path.join(OUTDIR, `batch-${String(b).padStart(3, '0')}.json`);
    if (fs.existsSync(f) && fs.statSync(f).size > 100) continue;
    const idList = ids.slice(b * BATCH, (b + 1) * BATCH).join(',');
    const q = `[out:json][timeout:180];rel(id:${idList});out geom;node(r);out;way(r:"platform");out geom;`;
    const t0 = Date.now();
    const r = await ask(q, 5, 300000);
    if (!r) { log('batch', b, '三次全败，终止（重跑可续）'); app.exit(1); return; }
    fs.writeFileSync(f, r.text);
    log(`batch ${b + 1}/${batches} 保存 ${(r.text.length / 1048576).toFixed(2)}MB ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  log('全部完成');
  app.exit(0);
});
