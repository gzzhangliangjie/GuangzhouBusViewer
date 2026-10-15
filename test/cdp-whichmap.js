// 分辨：藏区瓦片属于 #map(公交) 还是 #metro-canvas(地铁geo)？
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

  const out = await evalJS(`(function () {
    function info(sel) {
      const wrap = document.querySelector(sel);
      if (!wrap) return null;
      const tiles = wrap.querySelectorAll('.leaflet-tile');
      const first = tiles[0] ? (tiles[0].src.match(/[?&](x=[0-9]+&y=[0-9]+&z=[0-9]+)/) || [])[1] : null;
      return { tiles: tiles.length, first, visible: wrap.offsetParent !== null,
        w: wrap.offsetWidth, h: wrap.offsetHeight };
    }
    // Leaflet 实例：renderer 存在于 overlay svg 上（Leaflet 1.9 SVG renderer 有 _leaflet_events, map 在 renderer._map）
    let center = null, zoom = null;
    const svg = document.querySelector('#map .leaflet-overlay-pane svg');
    if (svg) {
      // Leaflet 把 renderer 实例挂在容器上不容易直接取；改用已渲染 path 的 bbox + layerCenter
      // 终极 hack: map 实器可以从任意 layer 的 _renderer 往上… 1.9 没有直接引用。
      // 用 requestAnimationFrame 期间记录的 mousemove target._map 不可行（无鼠标）。
    }
    return { bus: info('#map'), metro: info('#metro-canvas') };
  })()`);
  console.log(JSON.stringify(out, null, 1));
  process.exit(0);
}
main().catch(e => { console.log('err', e.message); process.exit(1); });
