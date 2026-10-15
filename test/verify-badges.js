// 线路徽章位置验收：每个徽章必须贴近所属线的终点站，且不与可见编号牌/站名重叠
// 用法: electron test/verify-badges.js
const { app, BrowserWindow } = require('electron');
const path = require('path');

app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
app.setPath('userData', require('path').join(__dirname, '..', 'assets', '_test-profile'));
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1400, height: 860, show: true,
    webPreferences: { preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true } });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));
  const r = await win.webContents.executeJavaScript(`(async () => {
    document.querySelector('#mode-nav [data-mode="metro"]').click();
    document.querySelector('#metro-setup .opt-card[data-v="schematic"]').click();
    // 全网 + 站名模式（徽章 filled 全展示，标签多，重叠压力最大）
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 4500));
    const g = MetroQuiz.__game();
    const I = g.renderer.__internals;

    // 线 -> 终点站屏幕点
    const terminalPt = {};
    for (const l of MetroData.allLines()) {
      const seq = (l.loop && l.stations.length > 2) ? l.stations : [...l.stations].reverse();
      const t = MetroData.station(seq[0]);
      if (t) terminalPt[l.ref] = I.map.latLngToContainerPoint([-t.sy, t.sx]);
    }

    const obstacles = [];
    const pushOb = el => {
      const r = el.getBoundingClientRect();
      if (r.width > 6 && r.height > 6) obstacles.push({ r, label: el.className.slice(0, 12) + ':' + (el.textContent || '').trim().slice(0, 8) });
    };
    document.querySelectorAll('#metro-canvas .mnum-wrap').forEach(el => {
      if (el.style.display !== 'none') pushOb(el);
    });
    document.querySelectorAll('#metro-canvas .mlab').forEach(el => pushOb(el));

    const report = { badges: 0, nearTerminal: 0, hidden: 0, overlap: [], ownDist: [] };
    document.querySelectorAll('#metro-canvas .mbadge-wrap').forEach(el => {
      const txt = el.textContent.replace(/\\s+/g, '');
      const r = el.getBoundingClientRect();
      report.badges++;
      // 距离最近终点
      let bestRef = null, bestD = 1e9;
      for (const [ref, pt] of Object.entries(terminalPt)) {
        const d = Math.hypot(r.x + r.width / 2 - pt.x, r.y + r.height / 2 - pt.y);
        if (d < bestD) { bestD = d; bestRef = ref; }
      }
      // 到自己线终点的距离（终判指标）
      const ownLine = MetroData.allLines().find(l => l.zh === txt);
      const ownTerm = ownLine ? terminalPt[ownLine.ref] : null;
      report.ownDist.push({ txt, d: ownTerm ? Math.round(Math.hypot(r.x + r.width/2 - ownTerm.x, r.y + r.height/2 - ownTerm.y)) : -1,
        pill: [Math.round(r.x + r.width/2), Math.round(r.y + r.height/2)],
        term: ownTerm ? [Math.round(ownTerm.x), Math.round(ownTerm.y)] : null,
        tx: el.style.getPropertyValue('--tx'), ty: el.style.getPropertyValue('--ty') });
      if (el.style.visibility === 'hidden' || (el.offsetParent === null)) report.hidden++;
      else report.overlap.push({ txt, issue: '距最近终点 ' + Math.round(bestD) + 'px(' + bestRef + ')' });
      // 与编号牌/站名重叠
      for (const o of obstacles) {
        if (r.left < o.r.right - 2 && r.right > o.r.left + 2 && r.top < o.r.bottom - 2 && r.bottom > o.r.top + 2) {
          report.overlap.push({ txt, issue: '重叠 ' + o.label });
          break;
        }
      }
    });
    // 徽章 marker 实际坐标 vs 其线终点艺术坐标
    try {
      report.anchors = [];
      for (const [ref, mk] of (I.badgeMk || new Map())) {
        if (!mk || !mk.getLatLng) continue;
        const ll = mk.getLatLng();
        const l = MetroData.line(ref);
        if (!l) continue;
        const seq = (l.loop && l.stations.length > 2) ? l.stations : [...l.stations].reverse();
        const t = MetroData.station(seq[0]);
        report.anchors.push({ ref, mkAt: [Math.round(ll.lat), Math.round(ll.lng)],
          termArt: t ? [Math.round(t.sy), Math.round(t.sx)] : null });
      }
    } catch (e) { report.anchorErr = String(e.message).slice(0, 60); }
    return report;
  })()`);
  console.log('[badges]', JSON.stringify(r, null, 1));
  const ok = r.badges > 0 && r.nearTerminal / r.badges >= 0.85 && r.hidden === 0 && r.overlap.length <= Math.ceil(r.badges * 0.15);
  console.log(ok ? 'PASS: 徽章贴终点且基本无重叠' : 'FAIL');
  app.exit(ok ? 0 : 1);
});
