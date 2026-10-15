// 徽章 marker 坐标 vs 终点艺术坐标 对照
async function main() {
  const list = await (await fetch('http://127.0.0.1:9222/json/list')).json();
  const page = list.find(t => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0;
  const pending = new Map();
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } };
  const send = (method, params = {}) => new Promise(res => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
  const r = await send('Runtime.evaluate', { expression: `(function () {
    const g = MetroQuiz.__game();
    const I = g.renderer.__internals;
    const out = [];
    for (const [ref, mk] of (I.badgeMk || new Map())) {
      if (!mk || !mk.getLatLng) continue;
      const ll = mk.getLatLng();
      const l = MetroData.line(ref);
      if (!l) { out.push(ref + ': 无线数据'); continue; }
      const seq = (l.loop && l.stations.length > 2) ? l.stations : [...l.stations].reverse();
      const t = MetroData.station(seq[0]);
      const okMatch = t && Math.abs(ll.lat + t.sy) < 2 && Math.abs(ll.lng - t.sx) < 2;
      out.push(ref + ': marker(' + Math.round(ll.lat) + ',' + Math.round(ll.lng) + ')' +
        ' 终点' + (t ? '(' + t.id + ' ' + Math.round(-t.sy) + ',' + Math.round(t.sx) + ')' : '无') +
        (okMatch ? ' OK' : ' BAD'));
    }
    return out.join('\\n');
  })()`, returnByValue: true });
  console.log(r.result.value);
  process.exit(0);
}
main().catch(e => { console.log('err', e.message); process.exit(1); });
