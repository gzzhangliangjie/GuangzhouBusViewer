// 干净流程徽章验收：重载 → 开局 → fit 态测量 → 放大两级再测量
async function main() {
  const list = await (await fetch('http://127.0.0.1:9222/json/list')).json();
  const page = list.find(t => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0;
  const pending = new Map();
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } };
  const send = (method, params = {}) => new Promise(res => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
  const evalJS = async (expr, ms = 60000) => {
    const pr = send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    const t = new Promise((_, rej) => setTimeout(() => rej(new Error('to')), ms));
    return (await Promise.race([pr, t])).result.value;
  };

  // 重载页面清一切状态
  await send('Page.reload');
  await new Promise(r => setTimeout(r, 3000));

  const measure = async (label) => {
    const r = await evalJS(`(async () => {
      // 等游戏就绪（重载后脚本与数据需加载）
      let g = null;
      for (let i = 0; i < 20; i++) {
        try { g = MetroQuiz.__game(); if (g && g.renderer) break; } catch (e) {}
        await new Promise(r => setTimeout(r, 500));
      }
      if (!g) return { nogame: 1 };
      const I = g.renderer.__internals;
      const out = { zoom: I.map.getZoom(), badges: 0, near: 0, hidden: 0, far: [], overlap: 0 };
      const terminalPt = {};
      for (const l of MetroData.allLines()) {
        const seq = (l.loop && l.stations.length > 2) ? l.stations : [...l.stations].reverse();
        const t = MetroData.station(seq[0]);
        if (t) terminalPt[l.ref] = I.map.latLngToContainerPoint([-t.sy, t.sx]);
      }
      const obstacles = [];
      document.querySelectorAll('#metro-canvas .mnum-wrap').forEach(el => {
        if (el.style.display !== 'none') { const r = el.getBoundingClientRect(); if (r.width > 6) obstacles.push(r); }
      });
      document.querySelectorAll('#metro-canvas .mbadge-wrap').forEach(wrap => {
        const pill = wrap.querySelector('.mbadge');
        if (!pill) return;
        out.badges++;
        if (pill.style.visibility === 'hidden') out.hidden++;
        // 药丸中心到所属 marker（wrap 中心）距离：纯轴向 48/70px 偏移 + 居中误差，≤90px 为贴终点
        const wr = wrap.getBoundingClientRect();
        const pr = pill.getBoundingClientRect();
        const d = Math.hypot((pr.x + pr.width / 2) - (wr.x + wr.width / 2), (pr.y + pr.height / 2) - (wr.y + wr.height / 2));
        if (d <= 90) out.near++; else out.far.push(pill.textContent.trim() + ':' + Math.round(d));
        if (obstacles.some(o => r.left < o.right - 2 && r.right > o.left + 2 && r.top < o.bottom - 2 && r.bottom > o.top + 2)) out.overlap++;
      });
      return out;
    })()`, 90000);
    console.log('[' + label + ']', JSON.stringify(r));
    return r;
  };

  // 开局
  await evalJS(`(async () => {
    document.querySelector('#mode-nav [data-mode="metro"]').click();
    document.querySelector('#metro-setup .opt-card[data-v="schematic"]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 5000));
    return 1;
  })()`);
  const fit = await measure('fit态');
  // 放大两级
  await evalJS(`(async () => {
    const I = MetroQuiz.__game().renderer.__internals;
    I.map.setZoom(I.map.getZoom() + 2);
    await new Promise(r => setTimeout(r, 1500));
    return 1;
  })()`);
  const zin = await measure('放大+2');
  const ok = fit.badges >= 15 && fit.hidden === 0 && fit.near / fit.badges >= 0.85 && zin.hidden === 0 && zin.near / zin.badges >= 0.85;
  console.log(ok ? 'PASS' : 'FAIL');
  process.exit(ok ? 0 : 1);
}
main().catch(e => { console.log('err', e.message); process.exit(1); });
