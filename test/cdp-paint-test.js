// 在真实实例里逐层测绘制：DOM div / data:URI 图片 / https 瓦片
async function main() {
  const list = await (await fetch('http://127.0.0.1:9222/json/list')).json();
  const page = list.find(t => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0;
  const pending = new Map();
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); }
  };
  const send = (method, params = {}) => new Promise(res => {
    const i = ++id; pending.set(i, res);
    ws.send(JSON.stringify({ id: i, method, params }));
  });
  await send('Page.enable');
  const evalJS = async expr => {
    const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    return r && r.result ? r.result.value : undefined;
  };
  const shot = async () => {
    const s = await send('Page.captureScreenshot', { format: 'png' });
    require('fs').writeFileSync('E:/GuangzhouBusViewer/assets/_paint-test.png', Buffer.from(s.data, 'base64'));
  };

  // ① 红色 div 盖在地图区
  await evalJS(`(function () {
    const d = document.createElement('div');
    d.id = '__t1'; d.style.cssText = 'position:fixed;left:700px;top:300px;width:300px;height:200px;background:#e02020;z-index:99999';
    document.body.appendChild(d);
    return 'ok';
  })()`);
  await shot();
  const hasRed = countRed();
  function countRed() { return true; }  // 像素统计放 python，这里先落图
  console.log('[t1] div-plotted, shot saved');

  // ② data:URI 小图
  await evalJS(`(function () {
    const d = document.createElement('div');
    d.id = '__t2'; d.style.cssText = 'position:fixed;left:1050px;top:300px;width:300px;height:200px;z-index:99999;background:#ffffff';
    const img = document.createElement('img');
    img.src = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
    img.style.cssText = 'width:300px;height:200px;object-fit:none;image-rendering:pixelated';
    img.onload = () => { d.dataset.loaded = '1'; };
    d.appendChild(img); document.body.appendChild(d);
    return 'ok';
  })()`);
  await new Promise(r => setTimeout(r, 1500));
  const t2 = await evalJS(`document.getElementById('__t2').dataset.loaded || 'no-load'`);
  await shot();
  console.log('[t2] data-img load:', t2);

  // ③ https 瓦片直接放页面上
  await evalJS(`(function () {
    const d = document.createElement('div');
    d.id = '__t3'; d.style.cssText = 'position:fixed;left:1400px;top:300px;width:300px;height:200px;z-index:99999;background:#ffffff';
    const img = document.createElement('img');
    img.src = 'https://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x=4095&y=3554&z=12';
    img.style.cssText = 'width:300px;height:200px';
    img.onload = () => { d.dataset.loaded = '1'; };
    img.onerror = () => { d.dataset.err = '1'; };
    d.appendChild(img); document.body.appendChild(d);
    return 'ok';
  })()`);
  await new Promise(r => setTimeout(r, 3000));
  const t3 = await evalJS(`document.getElementById('__t3').dataset.loaded || document.getElementById('__t3').dataset.err || 'pending'`);
  await shot();
  console.log('[t3] https-tile load:', t3);

  // 清理
  await evalJS(`['__t1','__t2','__t3'].forEach(i => { const e = document.getElementById(i); e && e.remove(); })`);
  process.exit(0);
}
main().catch(e => { console.log('err', e.message); process.exit(1); });
