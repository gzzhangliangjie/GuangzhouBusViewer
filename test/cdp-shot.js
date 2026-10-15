// CDP 截图真实实例：看用户到底看到什么
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
  await send('Page.enable');
  const shot = await send('Page.captureScreenshot', { format: 'png' });
  require('fs').writeFileSync('E:/GuangzhouBusViewer/assets/_real-shot.png', Buffer.from(shot.data, 'base64'));
  console.log('saved _real-shot.png');
  // 顺带抓 tile 实际加载状态（多少张成功/失败）
  const st = await send('Runtime.evaluate', { expression: `JSON.stringify((() => {
    const ts = [...document.querySelectorAll('.leaflet-tile')];
    return { total: ts.length, loaded: ts.filter(t => t.classList.contains('leaflet-tile-loaded')).length,
      src0: ts[0] ? ts[0].src.slice(0, 90) : '', status: document.querySelector('#status').textContent.slice(0, 60) };
  })())`, returnByValue: true });
  console.log('[tiles]', JSON.stringify(st.result.value));
  process.exit(0);
}
main().catch(e => { console.log('err', e.message); process.exit(1); });
