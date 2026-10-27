// 官方棋盘真实拖放链验收（Puppeteer 同款 intercept 模式，全程浏览器 DragController 状态机）：
//   setInterceptDrags → 真实鼠标按下牌池名牌（真 dragstart，载荷=页面自己 setData）
//   → dispatchDragEvent dragEnter/dragOver（真实 dragover 事件、可被 preventDefault 取消）
//   → type:'drop' + mouseReleased（真实松手，由 dragover 是否被取消决定 drop 是否派发）。
// 背景：dragover 未被 preventDefault 的区域浏览器判 no-drop、松手不派发 drop；
// 合成 dispatchEvent(new DragEvent('drop')) 是直派发、绕过这道门，测不出该类假绿
// （2026-10-27 用户报"判定圆圈亮了却放不进"即此因）。
// 断言: 判定圆圈亮起(≤SNAP_PX)的点位松手必须 drop 事件真到达且放置生效。
// 用法: ./node_modules/.bin/electron test/verify-official-dnd-real.js
const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

const SHOT = path.join(__dirname, '..', 'data');
app.setPath('userData', path.join(__dirname, '..', '.tmp-userdata-dndreal'));
app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');

app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1400, height: 900, show: true,
    webPreferences: { preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true,
      backgroundThrottling: false } });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));
  const dbg = win.webContents.debugger;
  await dbg.attach('1.1');

  // ---- 页面侧：开局（官方棋盘·站名模式·1号线）并选一个"只能走容器级就近"的投放点 ----
  const setup = await win.webContents.executeJavaScript(`(async () => {
    document.querySelector('#mode-nav [data-mode="metro"]').click();
    await new Promise(r => setTimeout(r, 300));
    document.querySelector('#scope-picker .scope-pill[data-v="1"]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 3000));
    const g = MetroQuiz.__game();
    const it = g.renderer.__internals;
    if (g.renderer.kind !== 'official') return { err: 'renderer not official: ' + g.renderer.kind };
    const QD = window.QUIZ_NETWORK_DATA;
    const canvas = document.getElementById('metro-canvas');
    const crect = canvas.getBoundingClientRect();
    const ctr = st => it.map.latLngToContainerPoint(L.latLng(-st.y, st.x));
    // 投放点条件: 距站心 26~58px（元素热区外、SNAP_PX 内）、60px 内无更近其它目标、
    // 命中元素不是槽/热区等自身处理链（逼真事件只可能走容器级就近判定）
    const okPt = nm => {
      const p = ctr(QD.stations[nm]);
      for (let a = 0; a < 360; a += 20) {
        const rad = a * Math.PI / 180;
        const cx = p.x + 45 * Math.cos(rad), cy = p.y + 45 * Math.sin(rad);
        if (cx < 4 || cy < 4 || cx > crect.width - 4 || cy > crect.height - 4) continue;
        const dSelf = Math.hypot(cx - p.x, cy - p.y);
        if (dSelf < 26 || dSelf > 58) continue;
        let other = 1e9;
        for (const [m2, s2] of Object.entries(QD.stations)) {
          if (m2 === nm || !it.hotspots.has(m2)) continue;
          const p2 = ctr(s2);
          other = Math.min(other, Math.hypot(cx - p2.x, cy - p2.y));
        }
        if (other <= 60) continue;
        const vx = crect.left + cx, vy = crect.top + cy;
        const el = document.elementFromPoint(vx, vy);
        if (!el) continue;
        if (el.closest && el.closest('.mb-slot, .leaflet-interactive, .leaflet-control, .map-caption')) continue;
        return { vx, vy, d: Math.round(dSelf), other: Math.round(other) };
      }
      return null;
    };
    for (const nm of Object.keys(QD.stations)) {
      if (!it.hotspots.has(nm)) continue;
      const chipEl = [...document.querySelectorAll('#chip-pool .mchip')]
        .find(e => e.textContent === nm);
      if (!chipEl) continue;
      const pt = okPt(nm);
      if (pt) {
        const cr = chipEl.getBoundingClientRect();
        return Object.assign({ nm, score: g.score,
          dock: document.querySelectorAll('#chip-pool .mchip').length,
          chipX: cr.left + cr.width / 2, chipY: cr.top + cr.height / 2 }, pt);
      }
    }
    return { err: 'no usable drop point' };
  })()`);
  if (setup.err) { console.log('SETUP-FAIL ' + setup.err); app.exit(2); return; }
  console.log('投放点: ' + setup.nm + ' 距站心=' + setup.d + 'px(元素热区26px外) 最近其它目标=' +
    setup.other + 'px 视口=(' + Math.round(setup.vx) + ',' + Math.round(setup.vy) + ') 牌位于(' +
    Math.round(setup.chipX) + ',' + Math.round(setup.chipY) + ')');

  // 事件埋点 + 开启拖放拦截
  await win.webContents.executeJavaScript(`(() => {
    window.__dbg = { enter: 0, over: 0, drop: 0, lastOverXY: null };
    const cv = document.getElementById('metro-canvas');
    cv.addEventListener('dragenter', () => window.__dbg.enter++);
    cv.addEventListener('dragover', e => { window.__dbg.over++; window.__dbg.lastOverXY = [e.clientX, e.clientY]; });
    cv.addEventListener('drop', () => window.__dbg.drop++);
  })()`);
  // Electron debugger 事件统一走 'message'（带 method），无按方法名分发
  let dragData = null;
  dbg.on('message', (_event, method, params) => {
    if (method === 'Input.dragIntercepted') dragData = params && params.data;
  });
  await dbg.sendCommand('Input.setInterceptDrags', { enabled: true });

  // ---- 真实鼠标链: 按下名牌 → 微移触发真 dragstart（载荷由页面 setData） ----
  const cx = Math.round(setup.chipX), cy = Math.round(setup.chipY);
  const mv = (x, y, buttons) => dbg.sendCommand('Input.dispatchMouseEvent', {
    type: 'mouseMoved', x, y, button: buttons ? 'left' : 'none', buttons: buttons || 0 });
  await mv(cx, cy, 0);
  await dbg.sendCommand('Input.dispatchMouseEvent',
    { type: 'mousePressed', x: cx, y: cy, button: 'left', buttons: 1, clickCount: 1 });
  await mv(cx + 6, cy + 6, 1);
  await mv(cx + 14, cy + 10, 1);
  await new Promise(r => setTimeout(r, 500));
  if (!dragData) { console.log('SETUP-FAIL dragstart 未被拦截（无 Input.dragIntercepted）'); app.exit(2); return; }
  const item = (dragData.items || []).find(i => i.mimeType === 'text/plain');
  console.log('真dragstart载荷: ' + (item ? item.data : JSON.stringify(dragData.items || [])) +
    (item && item.data === 'name:' + setup.nm ? '' : '  ←⚠与预期 name:' + setup.nm + ' 不符'));

  // ---- 移到投放点，真实 dragover（可被 preventDefault）→ 圈亮断言 ----
  const px = Math.round(setup.vx), py = Math.round(setup.vy);
  const dragData2 = dragData;
  await dbg.sendCommand('Input.dispatchDragEvent', { type: 'dragEnter', x: px, y: py, data: dragData2 });
  await new Promise(r => setTimeout(r, 100));
  await dbg.sendCommand('Input.dispatchDragEvent', { type: 'dragOver', x: px, y: py, data: dragData2 });
  await new Promise(r => setTimeout(r, 300));
  const nmJson = JSON.stringify(setup.nm);
  const mid = await win.webContents.executeJavaScript(`(() => {
    const g = MetroQuiz.__game();
    const el = g.renderer.__internals.hotspots.get(${nmJson}).getElement();
    return { circleShown: el && el.getAttribute('fill-opacity') === '0.2', dbg: window.__dbg,
      score: g.score, dock: document.querySelectorAll('#chip-pool .mchip').length };
  })()`);
  console.log('dragOver后: 圈亮=' + mid.circleShown + ' 事件=' + JSON.stringify(mid.dbg) +
    ' 分=' + mid.score + ' 牌池=' + mid.dock);

  // ---- 真实松手（drop 派发与否由浏览器 DragController 依 dragover 是否被取消决定） ----
  await dbg.sendCommand('Input.dispatchDragEvent', { type: 'drop', x: px, y: py, data: dragData2 });
  await new Promise(r => setTimeout(r, 300));
  let fin = await win.webContents.executeJavaScript(`(() => {
    const g = MetroQuiz.__game();
    return { placed: g.placedNames.has(${nmJson}), score: g.score, drop: window.__dbg.drop,
      dock: document.querySelectorAll('#chip-pool .mchip').length };
  })()`);
  let via = fin.drop > 0 ? 'CDP-drop' : null;
  if (!fin.placed) {
    await dbg.sendCommand('Input.dispatchMouseEvent',
      { type: 'mouseReleased', x: px, y: py, button: 'left', buttons: 1, clickCount: 1 });
    await new Promise(r => setTimeout(r, 400));
    fin = await win.webContents.executeJavaScript(`(() => {
      const g = MetroQuiz.__game();
      return { placed: g.placedNames.has(${nmJson}), score: g.score, drop: window.__dbg.drop,
        dock: document.querySelectorAll('#chip-pool .mchip').length };
    })()`);
    if (fin.drop > 0) via = 'mouseReleased';
  }
  const out = { point: setup.nm + '@' + setup.d + 'px', circleShown: mid.circleShown,
    dropEvents: fin.drop, via: via || 'none', scoreDelta: fin.score - setup.score,
    placed: fin.placed, dockDelta: fin.dock - setup.dock };
  win.webContents.invalidate();
  await new Promise(r => setTimeout(r, 300));
  fs.writeFileSync(path.join(SHOT, '_quiz-dnd-real.png'), (await win.webContents.capturePage()).toPNG());
  console.log(JSON.stringify(out));
  const ok = mid.circleShown && out.dropEvents > 0 && fin.placed &&
    out.scoreDelta === 100 && out.dockDelta === -1;
  console.log(ok ? 'PASS: 圈亮即可放（真实拖放链近失命中, drop 经 ' + via + '）'
    : 'FAIL: 圈亮但真实松手未派发 drop/未放置');
  app.exit(ok ? 0 : 1);
}).catch(e => { console.error(e); app.exit(2); });
