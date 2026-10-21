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
  function showFile(file) {
    curFile = file;
    const im = img();
    im.style.transform = 'none';
    im.onload = () => {
      imgW = im.naturalWidth; imgH = im.naturalHeight;
      fit();
      $('#lines-caption').innerHTML =
        `<span class="cap-chip" style="background:${lines[curLine].color}"></span>` +
        `${file.split('/').pop()} · ${imgW}×${imgH} · 官图提取卡`;
    };
    im.src = encodeURI(file) + '?v=' + Date.now();  // 破进程内图缓存: 同URL改盘后img仍吃旧字节
    [...$('#line-segs').children].forEach(c =>
      c.classList.toggle('active', c.dataset.file === file));
  }

  function selectLine(i) {
    curLine = i;
    const line = lines[i];
    [...$('#lines-list').children].forEach((c, k) => c.classList.toggle('active', k === i));
    // 分段行：主卡 + 来源卡
    const segs = $('#line-segs');
    segs.innerHTML = '';
    const mk = (file, label) => {
      const b = document.createElement('button');
      b.className = 'seg-chip';
      b.dataset.file = file;
      b.textContent = label;
      b.addEventListener('click', () => showFile(file));
      segs.appendChild(b);
    };
    mk(line.card, '主卡');
    line.segs.forEach(s => mk(s.file, `来源 ${s.tag}`));
    showFile(line.card);
  }

  function build() {
    if (built) return;
    built = true;
    lines = (window.LINES_VIEW && window.LINES_VIEW.lines) || [];
    $('#lines-count').textContent = `${lines.length} 条线`;
    const ul = $('#lines-list');
    lines.forEach((line, i) => {
      const li = document.createElement('li');
      li.innerHTML = `<span class="line-dot" style="background:${line.color}"></span>` +
        `<span class="line-name">${line.name}</span>` +
        (line.segs.length ? `<span class="line-meta">+${line.segs.length}卡</span>` : '');
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
