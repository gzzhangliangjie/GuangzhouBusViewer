// 底图分块渲染：全图切 N 块放大渲染 PNG（站名文字足够清晰供 OCR）
// 用法: node test/crop-tiles.js  —— 输出 assets/_tiles/tile-R-C.png
const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
app.whenReady().then(async () => {
  const RAW = 2848.5, RAH = 2054.25, S = 2.2;      // viewBox 尺寸与放大倍率
  const COLS = 4, ROWS = 3;
  const tw = Math.ceil(RAW / COLS), th = Math.ceil(RAH / ROWS);
  const OUT = path.join(__dirname, '..', 'assets', '_tiles');
  fs.mkdirSync(OUT, { recursive: true });

  // 窗口略大于块尺寸（带 12% 重叠，防止站名跨块被切）
  const ov = 0.12;
  const win = new BrowserWindow({
    width: Math.ceil(tw * S * (1 + ov * 2)) + 4, height: Math.ceil(th * S * (1 + ov * 2)) + 4,
    show: true, useContentSize: true,
    webPreferences: { preload: path.join(__dirname, '..', 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true }
  });
  await win.loadFile(path.join(__dirname, '..', 'index.html'));
  let raw = '';
  await win.webContents.executeJavaScript(`(async () => {
    document.body.innerHTML = '';
    document.body.style.cssText = 'margin:0;overflow:hidden';
    const res = await fetch('assets/tim-gzfmetro.svg');
    const raw = await res.text();
    const wrap = document.createElement('div');
    wrap.id = 'wrap';
    wrap.style.cssText = 'position:fixed;left:0;top:0;width:100vw;height:100vh;overflow:hidden;background:#fff';
    const inner = document.createElement('div');
    inner.id = 'inner';
    wrap.appendChild(inner);
    document.body.appendChild(wrap);
    window.__raw = raw;
    return raw.length;
  })()`);

  for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
    const x0 = c * tw - tw * ov, y0 = r * th - th * ov;
    const outPath = path.join(OUT, `tile-${r}-${c}.png`);
    if (fs.existsSync(outPath) && fs.statSync(outPath).size > 50000) continue;
    await win.webContents.executeJavaScript(`(function () {
      const inner = document.getElementById('inner');
      inner.innerHTML = window.__raw;
      const svg = inner.firstElementChild;
      svg.setAttribute('width', ${RAW} * ${S});
      svg.setAttribute('height', ${RAH} * ${S});
      svg.style.cssText = 'display:block';
      inner.style.cssText = 'position:absolute;left:' + (${-x0} * ${S}) + 'px;top:' + (${-y0} * ${S}) + 'px';
      return 1;
    })()`);
    await new Promise(res => setTimeout(res, 4000));
    fs.writeFileSync(outPath, (await win.webContents.capturePage()).toPNG());
    console.log('saved', path.basename(outPath), r + '-' + c);
  }
  console.log('TILES DONE');
  app.exit(0);
});
