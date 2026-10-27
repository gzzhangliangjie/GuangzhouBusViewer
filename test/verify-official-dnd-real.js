// 官方棋盘真实拖放链验收（Puppeteer 同款 intercept 模式，全程浏览器 DragController 状态机）：
//   setInterceptDrags → 真实鼠标按下牌池名牌（真 dragstart，载荷=页面自己 setData）
//   → dispatchDragEvent dragEnter/dragOver（真实 dragover 事件、可被 preventDefault 取消）
//   → type:'drop' + mouseReleased（真实松手，由 dragover 是否被取消决定 drop 是否派发）。
// 背景：dragover 未被 preventDefault 的区域浏览器判 no-drop、松手不派发 drop；
// 合成 dispatchEvent(new DragEvent('drop')) 是直派发、绕过这道门，测不出该类假绿
// （2026-10-27 用户报"判定圆圈亮了却放不进"即此因）。
// 三场景（2026-10-27 用户令双向一致 + 单线他线站屏蔽）:
//   A 本线站45px近失点: 圈亮→drop 派发→+100（圈亮↔可放）
//   B 他线淡化站45px:   圈不亮→零反应不扣分不闪红（单线他线站无热区不响应）
//   C 空白区(60px内无站): 圈不亮→drop 不派发=no-drop🚫光标（未取消 dragover 才对）
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

  // ---- 页面侧：开局（官方棋盘·站名模式·1号线）并选三个场景投放点 ----
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
    const SCOPE = '1号线';
    const inScope = nm => QD.stations[nm].lines.includes(SCOPE);
    const canvas = document.getElementById('metro-canvas');
    const crect = canvas.getBoundingClientRect();
    const ctr = st => it.map.latLngToContainerPoint(L.latLng(-st.y, st.x));
    // 距(cx,cy)最近的本线站距离(except 排除自身)/任意站距离
    const clear = (cx, cy, except) => {
      let dIn = 1e9, dAny = 1e9;
      for (const [m2, s2] of Object.entries(QD.stations)) {
        const p2 = ctr(s2);
        const d = Math.hypot(cx - p2.x, cy - p2.y);
        dAny = Math.min(dAny, d);
        if (inScope(m2) && m2 !== except) dIn = Math.min(dIn, d);
      }
      return { dIn, dAny };
    };
    const usable = (vx, vy) => {
      if (vx < 4 || vy < 4 || vx > crect.width - 4 || vy > crect.height - 4) return false;
      const el = document.elementFromPoint(crect.left + vx, crect.top + vy);
      return !!el && !(el.closest && el.closest('.mb-slot, .leaflet-interactive, .leaflet-control, .map-caption'));
    };
    const scan = (filter, exceptSelf, needInFar) => {
      for (const nm of Object.keys(QD.stations)) {
        if (!filter(nm) || (exceptSelf && !it.hotspots.has(nm))) continue;
        const p = ctr(QD.stations[nm]);
        for (let a = 0; a < 360; a += 15) {
          const rad = a * Math.PI / 180;
          const cx = p.x + 45 * Math.cos(rad), cy = p.y + 45 * Math.sin(rad);
          const dSelf = Math.hypot(cx - p.x, cy - p.y);
          if (dSelf < 26 || dSelf > 58) continue;
          const { dIn } = clear(cx, cy, exceptSelf ? nm : null);
          if (dIn <= 60) continue;             // 60px 内无其它本线站=判定无歧义
          if (!usable(cx, cy)) continue;
          return { nm, vx: crect.left + cx, vy: crect.top + cy, d: Math.round(dSelf), nearIn: Math.round(dIn) };
        }
      }
      return null;
    };
    const A = scan(nm => inScope(nm), true, true);
    const B = scan(nm => !inScope(nm), false, true);
    let C = null;
    for (let gx = 30; gx < crect.width && !C; gx += 40) {
      for (let gy = 30; gy < crect.height && !C; gy += 40) {
        const { dAny } = clear(gx, gy, null);
        if (dAny <= 60 || !usable(gx, gy)) continue;
        C = { vx: crect.left + gx, vy: crect.top + gy, d: 0, nearIn: Math.round(dAny) };
      }
    }
    if (!A || !B || !C) return { err: 'point scan failed', A: !!A, B: !!B, C: !!C };
    const chipEl = [...document.querySelectorAll('#chip-pool .mchip')]
      .find(e => e.textContent === A.nm);
    if (!chipEl) return { err: 'no chip for ' + A.nm };
    const cr = chipEl.getBoundingClientRect();
    return { A, B, C, score0: g.score, dock0: document.querySelectorAll('#chip-pool .mchip').length,
      chipX: cr.left + cr.width / 2, chipY: cr.top + cr.height / 2 };
  })()`);
  if (setup.err) { console.log('SETUP-FAIL ' + JSON.stringify(setup)); app.exit(2); return; }
  const chipNm = setup.A.nm;
  console.log('场景点: A本线=' + setup.A.nm + '@' + setup.A.d + 'px(他本线站' + setup.A.nearIn + 'px) ' +
    'B他线=' + setup.B.nm + '@' + setup.B.d + 'px(最近本线站' + setup.B.nearIn + 'px) ' +
    'C空白=最近站' + setup.C.nearIn + 'px  拖牌=' + chipNm);

  // Electron debugger 事件统一走 'message'（带 method），无按方法名分发
  let dragData = null;
  dbg.on('message', (_event, method, params) => {
    if (method === 'Input.dragIntercepted') dragData = params && params.data;
  });
  await dbg.sendCommand('Input.setInterceptDrags', { enabled: true });
  await win.webContents.executeJavaScript(`(() => {
    window.__dbg = { enter: 0, over: 0, drop: 0, lastOver: null, lastDrop: null };
    const cv = document.getElementById('metro-canvas');
    cv.addEventListener('dragenter', () => window.__dbg.enter++);
    cv.addEventListener('dragover', e => {
      window.__dbg.over++;
      // 本监听器挂在 board 之后: defaultPrevented 已反映 board 是否取消
      window.__dbg.lastOver = { x: e.clientX, y: e.clientY, prevented: e.defaultPrevented };
    });
    cv.addEventListener('drop', e => {
      window.__dbg.drop++;
      const t = e.target;
      window.__dbg.lastDrop = { x: e.clientX, y: e.clientY,
        cls: (t.className && t.className.baseVal !== undefined) ? t.className.baseVal :
          (typeof t.className === 'string' ? t.className : t.tagName) };
    });
  })()`);

  const cx = Math.round(setup.chipX), cy = Math.round(setup.chipY);
  const mv = (x, y, buttons) => dbg.sendCommand('Input.dispatchMouseEvent', {
    type: 'mouseMoved', x, y, button: buttons ? 'left' : 'none', buttons: buttons || 0 });
  const nmJs = nm => JSON.stringify(nm);
  const finState = nm => win.webContents.executeJavaScript(`(() => {
    const g = MetroQuiz.__game();
    return { score: g.score, placed: g.placedNames.has(${JSON.stringify(nm)}),
      drop: window.__dbg.drop, dock: document.querySelectorAll('#chip-pool .mchip').length };
  })()`);

  async function dragScenario(tag, pt) {
    await win.webContents.executeJavaScript('window.__dbg = { enter: 0, over: 0, drop: 0 }');
    dragData = null;
    await mv(cx, cy, 0);
    await dbg.sendCommand('Input.dispatchMouseEvent',
      { type: 'mousePressed', x: cx, y: cy, button: 'left', buttons: 1, clickCount: 1 });
    await mv(cx + 6, cy + 6, 1);
    await mv(cx + 14, cy + 10, 1);
    for (let i = 0; i < 20 && !dragData; i++) await new Promise(r => setTimeout(r, 50));
    if (!dragData) return { tag, err: 'no dragstart' };
    const px = Math.round(pt.vx), py = Math.round(pt.vy);
    await dbg.sendCommand('Input.dispatchDragEvent', { type: 'dragEnter', x: px, y: py, data: dragData });
    await new Promise(r => setTimeout(r, 100));
    await dbg.sendCommand('Input.dispatchDragEvent', { type: 'dragOver', x: px, y: py, data: dragData });
    await new Promise(r => setTimeout(r, 300));
    const mid = await win.webContents.executeJavaScript(`(() => {
      const g = MetroQuiz.__game();
      const it = g.renderer.__internals;
      const mk = it.hotspots.get(${nmJs(chipNm)});
      const el = mk && mk.getElement && mk.getElement();
      // 复刻 nearestTarget: 该点最近热区站与距离(容器坐标)
      const crect = document.getElementById('metro-canvas').getBoundingClientRect();
      const mx = ${Math.round(pt.vx)} - crect.left, my = ${Math.round(pt.vy)} - crect.top;
      let best = null, bd = 1e9;
      for (const [m2, s2] of Object.entries(window.QUIZ_NETWORK_DATA.stations)) {
        if (!it.hotspots.has(m2)) continue;
        const p2 = it.map.latLngToContainerPoint(L.latLng(-s2.y, s2.x));
        const d = Math.hypot(p2.x - mx, p2.y - my);
        if (d < bd) { bd = d; best = m2; }
      }
      return { circleShown: !!el && el.getAttribute('fill-opacity') === '0.2',
        over: window.__dbg.over, lastOver: window.__dbg.lastOver,
        near: best ? best + '@' + Math.round(bd) : 'none', score: g.score };
    })()`);
    await dbg.sendCommand('Input.dispatchDragEvent', { type: 'drop', x: px, y: py, data: dragData });
    await new Promise(r => setTimeout(r, 250));
    let fin = await win.webContents.executeJavaScript(`(() => {
      const g = MetroQuiz.__game();
      return { score: g.score, placed: g.placedNames.has(${nmJs(chipNm)}),
        drop: window.__dbg.drop, lastDrop: window.__dbg.lastDrop,
        dock: document.querySelectorAll('#chip-pool .mchip').length };
    })()`);
    if (fin.drop === 0) {   // CDP 直发 drop 无效时用真实 mouseReleased 兜底再试
      await dbg.sendCommand('Input.dispatchMouseEvent',
        { type: 'mouseReleased', x: px, y: py, button: 'left', buttons: 1, clickCount: 1 });
      await new Promise(r => setTimeout(r, 350));
      fin = await win.webContents.executeJavaScript(`(() => {
        const g = MetroQuiz.__game();
        return { score: g.score, placed: g.placedNames.has(${nmJs(chipNm)}),
          drop: window.__dbg.drop, lastDrop: window.__dbg.lastDrop,
          dock: document.querySelectorAll('#chip-pool .mchip').length };
      })()`);
      await dbg.sendCommand('Input.dispatchDragEvent',
        { type: 'dragCancel', x: px, y: py, data: dragData }).catch(() => {});
    }
    return { tag, mid, fin, score0: setup.score0, dock0: setup.dock0 };
  }

  const resC = await dragScenario('C空白', setup.C);
  const resB = await dragScenario('B他线站', setup.B);
  const resA = await dragScenario('A本线站', setup.A);
  for (const r of [resC, resB, resA]) {
    if (r.err) { console.log(r.tag + ': ERR ' + r.err); continue; }
    console.log(r.tag + '(' + (r === resA ? setup.A.nm : r === resB ? setup.B.nm : '—') +
      '): 圈亮=' + r.mid.circleShown + ' 近目标=' + r.mid.near + ' lastOver=' +
      JSON.stringify(r.mid.lastOver) + ' drop=' + r.fin.drop + ' lastDrop=' +
      JSON.stringify(r.fin.lastDrop) + ' 分' + r.score0 + '→' + r.fin.score +
      (r === resA ? ' 放置=' + r.fin.placed : ''));
  }
  const okC = resC.mid && !resC.mid.circleShown && resC.mid.over >= 1 && resC.fin.drop === 0 &&
    resC.fin.score === setup.score0;
  const okB = resB.mid && !resB.mid.circleShown && resB.fin.drop === 0 &&
    resB.fin.score === setup.score0 && resB.fin.dock === setup.dock0;
  const okA = resA.mid && resA.mid.circleShown && resA.fin.drop >= 1 && resA.fin.placed &&
    resA.fin.score === setup.score0 + 100 && resA.fin.dock === setup.dock0 - 1;
  win.webContents.invalidate();
  await new Promise(r => setTimeout(r, 300));
  fs.writeFileSync(path.join(SHOT, '_quiz-dnd-real.png'), (await win.webContents.capturePage()).toPNG());
  const ok = okC && okB && okA;
  console.log(ok ? 'PASS: 圈亮即可放 / 不亮即no-drop / 他线淡化站零响应'
    : 'FAIL: ' + JSON.stringify({ okC, okB, okA }));
  app.exit(ok ? 0 : 1);
}).catch(e => { console.error(e); app.exit(2); });
