// 优先补拉：指定 ref 集合的几何（按 ids.json 反查 id，避免 area 重查询）
// 用法: electron test/pull-priority.js ref1,ref2,...
const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

const PULL = path.join(__dirname, '..', 'assets', '_pull');
const MIRRORS = [
  'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
  'https://overpass-api.de/api/interpreter',
  'https://overpass.kumi.systems/api/interpreter',
  'https://overpass.private.coffee/api/interpreter'
];

app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
app.on('ready', () => {});
const pathMod = require('path');
app.setPath && app.setPath('userData', pathMod.join(__dirname, '..', 'assets', '_pull-profile'));
app.whenReady().then(async () => {
  const refs = new Set(process.argv[2].split(',').map(s => s.trim()).filter(Boolean));
  const idsData = JSON.parse(fs.readFileSync(path.join(PULL, 'ids.json'), 'utf-8'));
  const picked = idsData.filter(t => refs.has((t.tags && t.tags.ref) || ''));
  console.log('[prio] 目标 ref:', [...refs].join(','), '命中 relation:', picked.length);
  if (!picked.length) { app.exit(0); return; }

  const win = new BrowserWindow({ width: 500, height: 300, show: true });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));
  const idList = picked.map(t => t.id).join(',');
  const q = `[out:json][timeout:180];rel(id:${idList});out geom;node(r);out;way(r:"platform");out geom;`;

  for (let t = 0; t < 5; t++) {
    const r = JSON.parse(await win.webContents.executeJavaScript(`(async () => {
      for (const m of ${JSON.stringify(MIRRORS)}) {
        try {
          const res = await fetch(m, { method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: 'data=' + encodeURIComponent(${JSON.stringify(q)}) });
          const text = await res.text();
          if (res.ok) { const j = JSON.parse(text); if (!j.remark || !/error/i.test(j.remark)) return JSON.stringify({ ok: 1, text }); }
        } catch (e) {}
      }
      return '{"ok":0}';
    })()`));
    if (r.ok) {
      const f = path.join(PULL, 'batch-990.json');
      fs.writeFileSync(f, r.text);
      console.log('[prio] 保存', f, (r.text.length / 1048576).toFixed(2) + 'MB');
      app.exit(0);
      return;
    }
    console.log('[prio] 重试', t + 1);
    await new Promise(res => setTimeout(res, 10000));
  }
  app.exit(1);
});
