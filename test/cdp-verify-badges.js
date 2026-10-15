// 在用户真实实例上验收徽章：贴自己线终点 ≤80px、永不隐藏、无重叠
async function main() {
  const list = await (await fetch('http://127.0.0.1:9222/json/list')).json();
  const page = list.find(t => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0;
  const pending = new Map();
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } };
  const send = (method, params = {}) => new Promise(res => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
  const evalJS = async (expr, ms = 90000) => {
    const pr = send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    const t = new Promise((_, rej) => setTimeout(() => rej(new Error('to')), ms));
    return (await Promise.race([pr, t])).result.value;
  };

  const r = await evalJS(`(async () => {
    document.querySelector('#mode-nav [data-mode="metro"]').click();
    document.querySelector('#metro-setup .opt-card[data-v="schematic"]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 5000));
    const g = MetroQuiz.__game();
    const I = g.renderer.__internals;

    const terminalPt = {};
    for (const l of MetroData.allLines()) {
      const seq = (l.loop && l.stations.length > 2) ? l.stations : [...l.stations].reverse();
      const t = MetroData.station(seq[0]);
      if (t && Number.isFinite(t.sx)) terminalPt[l.ref] = I.map.latLngToContainerPoint([-t.sy, t.sx]);
    }
    const obstacles = [];
    const pushOb = el => {
      const r = el.getBoundingClientRect();
      if (r.width > 6 && r.height > 6) obstacles.push({ r, label: el.className.slice(0, 10) + ':' + (el.textContent || '').trim().slice(0, 8) });
    };
    document.querySelectorAll('#metro-canvas .mnum-wrap').forEach(el => { if (el.style.display !== 'none') pushOb(el); });
    document.querySelectorAll('#metro-canvas .mlab').forEach(el => pushOb(el));

    const report = { badges: 0, near: 0, hidden: 0, overlap: [], far: [], names: document.querySelectorAll('#metro-canvas .mlab').length };
    document.querySelectorAll('#metro-canvas .mbadge-wrap').forEach(wrap => {
      const el = wrap.querySelector('.mbadge') || wrap;
      const txt = (el.textContent || '').trim();
      const r = el.getBoundingClientRect();
      report.badges++;
      if (el.style.visibility === 'hidden') report.hidden++;
      const ownLine = MetroData.allLines().find(l => l.zh === txt);
      const tp = ownLine && terminalPt[ownLine.ref];
      if (!tp) return;
      const d = Math.hypot(r.x + r.width / 2 - tp.x, r.y + r.height / 2 - tp.y);
      if (d <= 80) report.near++;
      else report.far.push(txt + ':' + Math.round(d) + 'px');
      for (const o of obstacles) {
        if (r.left < o.r.right - 2 && r.right > o.r.left + 2 && r.top < o.r.bottom - 2 && r.bottom > o.r.top + 2) {
          report.overlap.push(txt + ' × ' + o.label);
          break;
        }
      }
    });
    return report;
  })()`, 120000);
  console.log('[真实实例徽章]', JSON.stringify(r, null, 1));
  const shot = await send('Page.captureScreenshot', { format: 'png' });
  require('fs').writeFileSync('E:/GuangzhouBusViewer/assets/_badges-real.png', Buffer.from(shot.data, 'base64'));
  const ok = r.badges >= 15 && r.hidden === 0 && r.near / r.badges >= 0.85 && r.overlap.length <= 3;
  console.log(ok ? 'PASS' : 'FAIL');
  process.exit(ok ? 0 : 1);
}
main().catch(e => { console.log('err', e.message); process.exit(1); });
