// 层级验证：单线模式（1号线）下，编号牌必须压住一切站名标签
// 判定标准 = document.elementFromPoint：标签中心点能命中的元素必须是编号牌自己
// 用法: ./node_modules/.bin/electron test/verify-layers.js
const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

const OUT = 'E:/GuangzhouBusViewer/assets';

app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1400, height: 860, show: true,
    webPreferences: { preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true } });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));
  const log = (...a) => console.log('[layers]', ...a);

  const r = await win.webContents.executeJavaScript(`(async () => {
    document.querySelector('#mode-nav [data-mode="metro"]').click();
    document.querySelector('#metro-setup .opt-card[data-v="schematic"]').click();
    document.querySelector('#scope-picker .scope-pill[data-v="1"]').click();
    document.getElementById('metro-start').click();
    await new Promise(r => setTimeout(r, 3500));

    // ① 每个可见编号牌：中心点 elementFromPoint 必须命中编号牌元素（.mnum-wrap 或其子）
    const bad = [];
    const tags = [...document.querySelectorAll('#metro-canvas .mnum-wrap')]
      .filter(el => el.offsetParent !== null && el.style.display !== 'none');
    for (const el of tags) {
      const r = el.getBoundingClientRect();
      const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      const hit = document.elementFromPoint(cx, cy);
      if (!hit || (!el.contains(hit) && hit !== el)) {
        bad.push({ tag: el.textContent, hitBy: hit ? (hit.className + '|' + hit.textContent).slice(0, 60) : 'null' });
      }
    }

    // ② pane 归属审计：.mlab / .mnum-wrap 各自挂在哪个 pane
    const paneOf = el => {
      let n = el;
      while (n && n !== document.body) {
        if (n.classList && n.classList.contains('leaflet-pane')) return n.className + '[z=' + (n.style.zIndex || getComputedStyle(n).zIndex) + ']';
        n = n.parentElement;
      }
      return 'NOT-IN-PANE';
    };
    const mnumPanes = [...new Set([...document.querySelectorAll('#metro-canvas .mnum-wrap')].map(paneOf))];
    const mlabPanes = [...new Set([...document.querySelectorAll('#metro-canvas .mlab.dim')].map(paneOf))];
    const labPanes = [...new Set([...document.querySelectorAll('#metro-canvas .mlab:not(.dim)')].map(paneOf))];
    const dotPanes = [...new Set([...document.querySelectorAll('#metro-canvas .mst-scope')].map(paneOf))];
    const artPaths = document.querySelectorAll('#metro-canvas .leaflet-scopeArt-pane path').length;

    // ④ 用户规定的层级次序：未选名(550) < 选中线(560) < 选中圆(570) < 选中名(580) < 编号牌(600)
    const z = p => p ? parseInt((p.match(/z=([0-9]+)/) || [])[1]) : -1;
    const order = { dimLab: z(mlabPanes[0]), scopeArt: 560, scopeDot: z(dotPanes[0]), scopeLab: z(labPanes[0]), tag: z(mnumPanes[0]) };
    const orderOk = order.dimLab < 560 && order.scopeDot >= 560 && (order.scopeLab < 0 || order.scopeLab > order.scopeDot) && order.tag > 580 && artPaths > 0;

    // ③ 猎德专项：猎德标签 与 杨箕编号牌 的矩形是否相交、谁在上面
    const lieDe = [...document.querySelectorAll('#metro-canvas .mlab')].find(e => e.textContent === '猎德');
    const yangJi = tags.find(e => /杨箕/.test(e.closest('[data-station]')?.dataset?.station || '') || e.textContent === '杨箕');
    // 编号牌文本是 "1-xx"，找不到就用坐标：猎德标签矩形与所有牌求交
    let overlap = null;
    if (lieDe) {
      const lr = lieDe.getBoundingClientRect();
      for (const el of tags) {
        const tr = el.getBoundingClientRect();
        if (lr.left < tr.right && lr.right > tr.left && lr.top < tr.bottom && lr.bottom > tr.top) {
          const hit = document.elementFromPoint(tr.left + tr.width / 2, tr.top + tr.height / 2);
          overlap = { label: '猎德', tag: el.textContent,
            tagOnTop: hit ? (el.contains(hit) || hit === el) : false,
            hitClass: hit ? String(hit.className).slice(0, 40) : 'null' };
          break;
        }
      }
    }

    return { tagTotal: tags.length, blockedTags: bad, mnumPanes, mlabPanes, labPanes, dotPanes, artPaths, order, orderOk, lieDe: overlap,
      lieDeFound: !!lieDe };
  })()`);

  log(JSON.stringify(r, null, 1));
  fs.writeFileSync(OUT + '/_v-layers.png', (await win.webContents.capturePage()).toPNG());
  const ok = r.blockedTags.length === 0 && r.orderOk;
  log(ok ? 'PASS: 编号牌最上 + 层级次序符合规范' : ('FAIL: blocked=' + r.blockedTags.length + ' orderOk=' + r.orderOk + ' ' + JSON.stringify(r.order)));
  app.exit(ok ? 0 : 1);
});
