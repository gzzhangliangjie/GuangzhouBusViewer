// CDP 点击 522 并回报状态与瓦片
async function main() {
  const list = await (await fetch('http://127.0.0.1:9222/json/list')).json();
  const page = list.find(t => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0;
  const pending = new Map();
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } };
  const send = (method, params = {}) => new Promise(res => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
  const evalJS = async expr => (await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result.value;
  const r = await evalJS(`(async () => {
    for (let i = 0; i < 60; i++) {
      if (document.querySelectorAll('#line-list li').length > 100) break;
      await new Promise(r => setTimeout(r, 1000));
    }
    const search = document.querySelector('#search');
    search.value = '522';
    search.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise(r => setTimeout(r, 400));
    const lis = [...document.querySelectorAll('#line-list li')].filter(x => x.dataset.ref === '522');
    if (!lis.length) return { err: 'no li', status: document.querySelector('#status').textContent.slice(0, 60) };
    lis[0].click();
    await new Promise(r => setTimeout(r, 5000));
    const t = document.querySelector('#map .leaflet-tile');
    return { n: lis.length, status: document.querySelector('#status').textContent.slice(0, 60),
      tile: t ? (t.src.match(/(x=[0-9]+&y=[0-9]+&z=[0-9]+)/) || [])[1] : null };
  })()`);
  console.log('[click522]', JSON.stringify(r));
  process.exit(0);
}
main().catch(e => { console.log('err', e.message); process.exit(1); });
