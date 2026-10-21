// 验收 lines-view 预览页的全网合成图: 独立Edge CDP实例, 不碰用户Electron
// 用法: node tools/_verify-network-view.js [port=9224]
import { writeFileSync, writeSync } from 'node:fs';
const say = m => writeSync(1, m + '\n');
const port = process.argv[2] || '9224';
const list = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const page = list.find(t => t.type === 'page' && t.url.includes('index.html'));
if (!page) { say('no page'); process.exit(1); }
const ws = new WebSocket(page.webSocketDebuggerUrl);
ws.onerror = () => say('WS-ERROR');
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let id = 0; const pending = new Map();
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
const send = (method, params = {}) => new Promise(res => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const evalJson = async expression => {
  const r = await send('Runtime.evaluate', { expression, returnByValue: true });
  if (r.result?.exceptionDetails) return { EXC: r.result.exceptionDetails.exception?.description || 'exc' };
  return r.result?.result?.value;
};

await send('Page.enable');
await sleep(500);
say('ready: ' + JSON.stringify(await evalJson('document.readyState + " LINES=" + (window.LINES_VIEW ? window.LINES_VIEW.lines.length : "MISSING")')));
say('nav: ' + JSON.stringify(await evalJson(`(() => { const b = document.querySelector('#mode-nav [data-mode=lines]'); if (!b) return 'NO-BTN'; b.click(); return 'ok'; })()`)));
await sleep(2500);
say('default-state: ' + JSON.stringify(await evalJson(`JSON.stringify({
  count: document.querySelector('#lines-count').textContent,
  listItems: document.querySelectorAll('#lines-list li').length,
  firstActive: document.querySelector('#lines-list li.active')?.textContent,
  segChips: [...document.querySelectorAll('#line-segs .seg-chip')].map(b => b.textContent),
  img: document.querySelector('#lines-img').naturalWidth + 'x' + document.querySelector('#lines-img').naturalHeight,
  caption: document.querySelector('#lines-caption').textContent,
})`)));
let shot = await send('Page.captureScreenshot', { format: 'png' });
writeFileSync('E:/GuangzhouBusViewer/data/_shot-network-view.png', Buffer.from(shot.result.data, 'base64'));
say('shot network saved');

say('l6: ' + JSON.stringify(await evalJson(`(() => { const li = [...document.querySelectorAll('#lines-list li')].find(li => li.textContent.includes('6号线')); li.click(); return li.textContent; })()`)));
await sleep(1500);
say('l6-state: ' + JSON.stringify(await evalJson(`JSON.stringify({
  caption: document.querySelector('#lines-caption').textContent,
  img: document.querySelector('#lines-img').naturalWidth + 'x' + document.querySelector('#lines-img').naturalHeight,
})`)));
shot = await send('Page.captureScreenshot', { format: 'png' });
writeFileSync('E:/GuangzhouBusViewer/data/_shot-lines-6号线-new.png', Buffer.from(shot.result.data, 'base64'));
say('shot l6 saved');
ws.close();
