// 用 Chromium 网络栈探测/拉取 Overpass（curl 指纹被中间盒拦，Electron fetch 可通过）
// 用法: electron test/probe-mirrors.js [queryfile] [outjson]
const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

const MIRRORS = [
  'https://overpass-api.de/api/interpreter',
  'https://overpass.kumi.systems/api/interpreter',
  'https://overpass.private.coffee/api/interpreter',
  'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
  'https://overpass.openstreetmap.ru/api/interpreter'
];

app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 500, height: 300, show: true });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));

  const query = process.argv[2]
    ? fs.readFileSync(process.argv[2], 'utf-8')
    : '[out:json][timeout:20];node(23.13,113.27,23.13,113.271);out 1;';
  const outPath = process.argv[3];

  const r = await win.webContents.executeJavaScript(`(async () => {
    const q = ${JSON.stringify(query)};
    const results = [];
    for (const m of ${JSON.stringify(MIRRORS)}) {
      const t0 = Date.now();
      try {
        const ctrl = new AbortController();
        const to = setTimeout(() => ctrl.abort(), 300000);
        const res = await fetch(m, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: 'data=' + encodeURIComponent(q),
          signal: ctrl.signal
        });
        const text = await res.text();
        clearTimeout(to);
        let n = -1;
        try { n = (JSON.parse(text).elements || []).length; } catch (e) {}
        results.push({ m, status: res.status, elems: n, ms: Date.now() - t0, bytes: text.length });
        if (res.ok && n >= 0) {
          if (${outPath ? 'true' : 'false'}) {
            window.__okText = text;
          }
          break;
        }
      } catch (e) {
        results.push({ m, status: 0, err: String(e.message || e).slice(0, 80), ms: Date.now() - t0 });
      }
    }
    return { results, okText: window.__okText || null };
  })()`);

  console.log(JSON.stringify(r.results, null, 1));
  if (outPath && r.okText) {
    fs.writeFileSync(outPath, r.okText);
    console.log('saved', outPath, r.okText.length, 'bytes');
  }
  app.exit(r.results.some(x => x.status === 200) ? 0 : 1);
});
