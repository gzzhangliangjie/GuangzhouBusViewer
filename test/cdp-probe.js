// CDP 探针：驱动真实 app 实例（--remote-debugging-port=9222），点 108 抓真实错误
// 用法: node test/cdp-probe.js [ref]
const REF = process.argv[2] || '108';

async function main() {
  const list = await (await fetch('http://127.0.0.1:9222/json/list')).json();
  const page = list.find(t => t.type === 'page');
  if (!page) { console.log('no page target'); process.exit(1); }
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

  let id = 0;
  const pending = new Map();
  const consoleMsgs = [];
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); }
    if (m.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(m.params.type)) {
      consoleMsgs.push(m.params.type + ': ' + m.params.args.map(a => a.value || a.description || '').join(' ').slice(0, 300));
    }
    if (m.method === 'Runtime.exceptionThrown') {
      consoleMsgs.push('EXCEPTION: ' + JSON.stringify(m.params.exceptionDetails).slice(0, 400));
    }
  };
  const send = (method, params = {}) => new Promise(res => {
    const i = ++id;
    pending.set(i, res);
    ws.send(JSON.stringify({ id: i, method, params }));
  });
  await send('Runtime.enable');

  const evalJS = async expr => {
    const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    return r && r.result ? r.result.value : undefined;
  };

  // 等列表就绪
  await evalJS(`(async () => {
    for (let i = 0; i < 60; i++) {
      if (document.querySelectorAll('#line-list li').length > 100) return true;
      await new Promise(r => setTimeout(r, 1000));
    }
    return false;
  })()`);

  const before = await evalJS(`({
    lis: document.querySelectorAll('#line-list li').length,
    tiles: document.querySelectorAll('.leaflet-tile').length,
    status: document.querySelector('#status').textContent.slice(0, 80),
    statusRed: document.querySelector('#status').className
  })`);
  console.log('[before]', JSON.stringify(before));

  const result = await evalJS(`(async () => {
    const search = document.querySelector('#search');
    search.value = ${JSON.stringify(REF)};
    search.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise(r => setTimeout(r, 300));
    const lis = [...document.querySelectorAll('#line-list li')].filter(x => x.dataset.ref === ${JSON.stringify(REF)});
    if (!lis.length) return { err: 'no li' };
    lis[0].click();
    for (let i = 0; i < 45; i++) {
      const st = document.querySelector('#status');
      if (/已加载|未在 OSM|失败/.test(st.textContent)) {
        return { lis: lis.length, status: st.textContent.slice(0, 90), red: st.className,
          paths: document.querySelectorAll('#map svg path').length,
          tiles: document.querySelectorAll('.leaflet-tile').length,
          mapKids: document.getElementById('map') ? document.getElementById('map').children.length : -1 };
      }
      await new Promise(r => setTimeout(r, 1000));
    }
    return { timeout: true, status: document.querySelector('#status').textContent.slice(0, 90) };
  })()`);
  console.log('[click]', JSON.stringify(result));
  await new Promise(r => setTimeout(r, 2000));
  console.log('[console]', JSON.stringify(consoleMsgs.slice(0, 10), null, 1));
  ws.close();
  process.exit(0);
}
main().catch(e => { console.log('probe error', e.message); process.exit(1); });
