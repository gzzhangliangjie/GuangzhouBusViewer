// 检查编号牌：换乘站是否显示多行编号
async function main() {
  const list = await (await fetch('http://127.0.0.1:9222/json/list')).json();
  const page = list.find(t => t.type === 'page');
  if (!page) { console.log('no page'); process.exit(1); }
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0;
  const pending = new Map();
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } };
  const send = (method, params = {}) => new Promise(res => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
  const r = await send('Runtime.evaluate', { expression: `(function () {
    try {
      const tags = [...document.querySelectorAll('.mnum')].map(e => e.textContent.trim());
      const multi = tags.filter(t => t.length > 6);
      return JSON.stringify({ total: tags.length, multi: multi.length, sample: multi.slice(0, 5) });
    } catch (e) { return 'ERR:' + e.message.slice(0, 50); }
  })()`, returnByValue: true });
  console.log('[tags]', r.result.value);
  process.exit(0);
}
main().catch(e => { console.log('err', e.message); process.exit(1); });
