// 分步诊断高德源：脚本加载 → AMap 全局 → 插件 → LineSearch 查询
async function main() {
  const list = await (await fetch('http://127.0.0.1:9222/json/list')).json();
  const page = list.find(t => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0;
  const pending = new Map();
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } };
  const send = (method, params = {}) => new Promise(res => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
  const evalJS = async (expr, timeoutMs = 30000) => {
    const pr = send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    const t = new Promise((_, rej) => setTimeout(() => rej(new Error('eval-timeout')), timeoutMs));
    return (await Promise.race([pr, t])).result.value;
  };

  // 手动分步：① 注入 script 标签（带 onload/onerror 埋点）
  await evalJS('(function(){ window.__amapdbg = {}; const s=document.createElement("script"); s.src="https://webapi.amap.com/maps?v=1.4.15&key=04f065a4e72d55a1f150454d361122c4"; s.onload=()=>{window.__amapdbg.core=1}; s.onerror=(e)=>{window.__amapdbg.err=String(e.type||"net")}; document.head.appendChild(s); return "injected"; })()');
  await new Promise(r => setTimeout(r, 5000));
  const st = await evalJS('JSON.stringify({ core: window.__amapdbg.core||0, err: window.__amapdbg.err||null, hasAMap: !!window.AMap, hasPluginFn: !!(window.AMap && AMap.plugin), hasLS: !!(window.AMap && AMap.LineSearch) })');
  console.log('[step1]', st);
  if (!JSON.parse(st).hasAMap) { console.log('AMap 核心都没加载'); process.exit(1); }

  // ② 显式挂插件
  const p = await evalJS('(function(){ return new Promise(res => { AMap.plugin("AMap.LineSearch", () => res("done:" + !!AMap.LineSearch)); setTimeout(() => res("timeout:" + !!AMap.LineSearch), 15000); }) })()', 25000);
  console.log('[step2 plugin]', p);

  // ③ 实查 108
  if (String(p).includes('done:true') || String(p).includes('timeout:true')) {
    const q = await evalJS('(function(){ return new Promise(res => { const ls = new AMap.LineSearch({ city: "广州" }); ls.search("108", (status, result) => { res(JSON.stringify({ status, n: result && result.lineInfo ? result.lineInfo.length : -1, name: result && result.lineInfo && result.lineInfo[0] ? result.lineInfo[0].name : null, stOps: result && result.lineInfo && result.lineInfo[0] && result.lineInfo[0].via_stations ? result.lineInfo[0].via_stations.length : 0 })); setTimeout(() => res("timeout"), 15000); }); }) })()', 25000);
    console.log('[step3 search]', q);
  }
  process.exit(0);
}
main().catch(e => { console.log('err', e.message); process.exit(1); });
