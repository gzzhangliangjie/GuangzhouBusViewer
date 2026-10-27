// 探测 5 个 Overpass 镜像的 TLS/HTTP 连通性（与 App 同为 Chromium fetch 栈）
// 用法: ./node_modules/.bin/electron test/probe-overpass-mirrors.js
const { app, BrowserWindow } = require('electron');
const path = require('path');

app.setPath('userData', path.join(__dirname, '..', '.tmp-userdata-probe'));
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 800, height: 600, show: false,
    webPreferences: { contextIsolation: true, sandbox: true } });
  await win.loadURL('data:text/html,<html></html>');
  const MIRRORS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
    'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
    'https://overpass.openstreetmap.ru/api/interpreter'
  ];
  const out = [];
  for (const m of MIRRORS) {
    const t0 = Date.now();
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 12000);
    try {
      const res = await fetch(m, { method: 'GET', signal: ctrl.signal });
      out.push({ m: m.replace('https://', '').split('/')[0], ok: res.ok,
        status: res.status, ms: Date.now() - t0 });
    } catch (e) {
      out.push({ m: m.replace('https://', '').split('/')[0], ok: false,
        err: String(e && e.message).slice(0, 80), ms: Date.now() - t0 });
    } finally { clearTimeout(timer); }
  }
  for (const r of out) console.log((r.ok ? 'OK  ' : 'FAIL') + ' ' + r.m +
    (r.status ? ' HTTP ' + r.status : '') + ' ' + r.ms + 'ms' + (r.err ? '  ' + r.err : ''));
  app.exit(0);
}).catch(e => { console.error(e); app.exit(2); });
