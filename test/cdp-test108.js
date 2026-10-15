// 端到端验证：搜索 108 回车 → 直查 → 高德补源 → 画线出站
async function main() {
  const list = await (await fetch('http://127.0.0.1:9222/json/list')).json();
  const page = list.find(t => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0;
  const pending = new Map();
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } };
  const send = (method, params = {}) => new Promise(res => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
  const evalJS = async (expr, ms = 40000) => {
    const pr = send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    const t = new Promise((_, rej) => setTimeout(() => rej(new Error('eval-timeout')), ms));
    return (await Promise.race([pr, t])).result.value;
  };

  await evalJS('localStorage.setItem("gzbus.amap.key.v1", JSON.stringify({key:"04f065a4e72d55a1f150454d361122c4"})); localStorage.removeItem("gzbus.line.108.v1"); "ok"');
  const r = await evalJS(`(async () => {
    for (let i = 0; i < 60; i++) {
      if (document.querySelectorAll('#line-list li').length > 100) break;
      await new Promise(r => setTimeout(r, 1000));
    }
    const s = document.querySelector('#search');
    s.value = '108';
    s.dispatchEvent(new Event('input', { bubbles: true }));
    s.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    for (let i = 0; i < 30; i++) {
      const st = document.querySelector('#status').textContent;
      if (/已加载 108|未在 OSM|失败|无法/.test(st)) break;
      await new Promise(r => setTimeout(r, 1000));
    }
    const t = document.querySelector('#map .leaflet-tile');
    return {
      status: document.querySelector('#status').textContent.slice(0, 60),
      stops: document.querySelectorAll('#line-detail .stop-item').length,
      tabs: [...document.querySelectorAll('#line-detail .dir-tabs button')].map(b => b.textContent.trim().slice(0, 24)),
      tile: t ? (t.src.match(/x=[0-9]+&y=[0-9]+&z=[0-9]+/) || [])[0] : null
    };
  })()`, 120000);
  console.log('[test108]', JSON.stringify(r, null, 1));
  process.exit(0);
}
main().catch(e => { console.log('err', e.message); process.exit(1); });
