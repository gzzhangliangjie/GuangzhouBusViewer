// 线路图查看：按线浏览官图提取卡（assets/lines/），主卡 + 分段/来源卡
// 数据由 tools/gen-lines-view-data.py 生成 -> data/lines-view-data.js
(() => {
  const $ = s => document.querySelector(s);
  let built = false;
  let lines = [];
  let curLine = -1;
  let curFile = '';

  // ---- 缩放/平移（相对原始像素：1 = 1:1）----
  const stage = () => $('#lines-stage');
  const img = () => $('#lines-img');
  let scale = 1, tx = 0, ty = 0, fitScale = 1, imgW = 0, imgH = 0;

  function apply() {
    img().style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
    $('#lines-zoom-pct').textContent = Math.round(scale * 100) + '%';
  }

  function clampScale(s) { return Math.min(8, Math.max(fitScale * 0.3, s)); }

  function center() {
    const r = stage().getBoundingClientRect();
    tx = (r.width - imgW * scale) / 2;
    ty = (r.height - imgH * scale) / 2;
    apply();
  }

  function fit() {
    const r = stage().getBoundingClientRect();
    if (!imgW || !r.width) return;
    fitScale = Math.min((r.width - 24) / imgW, (r.height - 24) / imgH);
    scale = clampScale(fitScale);
    center();
  }

  function zoomAt(mx, my, factor) {
    const s2 = clampScale(scale * factor);
    if (s2 === scale) return;
    tx = mx - (mx - tx) * (s2 / scale);
    ty = my - (my - ty) * (s2 / scale);
    scale = s2;
    apply();
  }

  // ---- 展示 ----
  // 查看站点编号: 换用 *.codes.svg 变体(站圆/换乘胶囊 -> 「线路|编号」编号牌), 默认不勾选
  let showCodes = false;

  function showFile(file) {
    curFile = file;
    const base = file;
    const eff = showCodes ? file.replace(/\.svg$/, '.codes.svg') : file;
    const im = img();
    im.style.transform = 'none';
    im.onload = () => {
      imgW = im.naturalWidth; imgH = im.naturalHeight;
      fit();
      $('#lines-caption').innerHTML =
        `<span class="cap-chip" style="background:${lines[curLine].color}"></span>` +
        `${eff.split('/').pop()} · ${imgW}×${imgH} · ` +
        (lines[curLine].kind === 'network' ? '全网合成图(全部站名)' : '官图提取卡') +
        (eff !== base ? ' · 站点编号' : '');
    };
    im.onerror = () => {   // 编号变体缺失时回退原图
      if (im.src !== encodeURI(base)) im.src = encodeURI(base) + '?v=' + Date.now();
    };
    im.src = encodeURI(eff) + '?v=' + Date.now();  // 破进程内图缓存: 同URL改盘后img仍吃旧字节
  }

  $('#lines-codes').addEventListener('change', e => {
    showCodes = e.target.checked;
    if (curFile) showFile(curFile);
  });

  function selectLine(i) {
    curLine = i;
    const line = lines[i];
    [...$('#lines-list').children].forEach((c, k) => c.classList.toggle('active', k === i));
    showFile(line.card);
  }

  function build() {
    if (built) return;
    built = true;
    lines = (window.LINES_VIEW && window.LINES_VIEW.lines) || [];
    $('#lines-count').textContent = `${lines.filter(l => l.kind !== 'network').length} 条线`;
    const ul = $('#lines-list');
    lines.forEach((line, i) => {
      const li = document.createElement('li');
      li.innerHTML = `<span class="line-dot" style="background:${line.color}"></span>` +
        `<span class="line-name">${line.name}</span>`;
      li.addEventListener('click', () => selectLine(i));
      ul.appendChild(li);
    });
    if (lines.length) selectLine(0);
  }

  // ---- 交互 ----
  $('#lines-zoom-in').addEventListener('click', () => { const r = stage().getBoundingClientRect(); zoomAt(r.width / 2, r.height / 2, 1.25); });
  $('#lines-zoom-out').addEventListener('click', () => { const r = stage().getBoundingClientRect(); zoomAt(r.width / 2, r.height / 2, 1 / 1.25); });
  $('#lines-zoom-fit').addEventListener('click', fit);
  $('#lines-zoom-1x').addEventListener('click', () => { scale = 1; center(); });
  stage().addEventListener('wheel', e => {
    e.preventDefault();
    const r = stage().getBoundingClientRect();
    zoomAt(e.clientX - r.left, e.clientY - r.top, e.deltaY < 0 ? 1.15 : 1 / 1.15);
  }, { passive: false });
  let drag = null;
  stage().addEventListener('pointerdown', e => {
    drag = { x: e.clientX, y: e.clientY, tx, ty };
    stage().setPointerCapture(e.pointerId);
  });
  stage().addEventListener('pointermove', e => {
    if (!drag) return;
    tx = drag.tx + e.clientX - drag.x;
    ty = drag.ty + e.clientY - drag.y;
    apply();
  });
  stage().addEventListener('pointerup', () => { drag = null; });
  window.addEventListener('resize', () => { if (built && !$('#lines-view').hidden) fit(); });

  function show() {
    build();
    // 切入时尺寸才定，重新适应
    setTimeout(fit, 60);
  }

  window.LinesView = { show };
})();
