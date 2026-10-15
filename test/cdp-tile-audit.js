// 抓取 app 当前视口的瓦片 URL 列表 + 每张的屏幕位置，供拼接比对
async function main() {
  const list = await (await fetch('http://127.0.0.1:9222/json/list')).json();
  const page = list.find(t => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0;
  const pending = new Map();
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); }
  };
  const send = (method, params = {}) => new Promise(res => {
    const i = ++id; pending.set(i, res);
    ws.send(JSON.stringify({ id: i, method, params }));
  });
  const r = await send('Runtime.evaluate', { expression: `JSON.stringify([...document.querySelectorAll('.leaflet-tile')].slice(0, 40).map(t => ({
    src: t.src, x: Math.round(t.getBoundingClientRect().x), y: Math.round(t.getBoundingClientRect().y),
    w: t.width, h: t.height, cls: t.className.includes('loaded') ? 'L' : (t.className.includes('error') ? 'E' : '?')
  })))`, returnByValue: true });
  require('fs').writeFileSync('E:/GuangzhouBusViewer/assets/_tiles.json', r.result.value);
  const info = JSON.parse(r.result.value);
  console.log('tiles:', info.length, 'loaded:', info.filter(t => t.cls === 'L').length,
    'err:', info.filter(t => t.cls === 'E').length);
  info.slice(0, 4).forEach(t => console.log(' ', t.src.replace(/.*x=/, 'x=') , 'at', t.x, t.y));
  process.exit(0);
}
main().catch(e => { console.log('err', e.message); process.exit(1); });
