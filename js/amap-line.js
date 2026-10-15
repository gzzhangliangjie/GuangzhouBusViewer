// 高德公交线路查询源（第二数据源）
// 接口：restapi.amap.com/v3/bus/linename（Web服务 key，纯 REST，无安全密钥要求）
// 返回：polyline 真实路径（GCJ-02，与底图一致）+ busstops 站点（名称/坐标/序号）
// 用途：OSM（随包快照/镜像）查不到的线路自动走这里补

const AMapLine = (() => {
  const KEY_STORE = 'gzbus.amap.key.v1';       // {key}
  const CITY = '广州';
  const CITY_CODE = '020';                      // 过滤同号的外市线

  function getCreds() {
    try { return JSON.parse(localStorage.getItem(KEY_STORE)) || null; } catch { return null; }
  }
  function setCreds(key) {
    localStorage.setItem(KEY_STORE, JSON.stringify({ key: (key || '').trim() }));
  }
  function available() {
    const c = getCreds();
    return !!(c && c.key);
  }

  /**
   * 按线路号查线路，返回与 Overpass.fetchLineByRef 同构的变体数组。
   * 只保留名称与线路号精确匹配（防 108 匹配到 108A）且属广州的结果。
   */
  async function fetchLine(ref) {
    const c = getCreds();
    if (!c || !c.key) return [];
    const url = 'https://restapi.amap.com/v3/bus/linename?key=' + encodeURIComponent(c.key) +
      '&city=' + encodeURIComponent(CITY) +
      '&keywords=' + encodeURIComponent(ref) + '&extensions=all';
    const res = await fetch(url);
    if (!res.ok) throw new Error('高德 HTTP ' + res.status);
    const j = await res.json();
    if (String(j.status) !== '1' || !Array.isArray(j.buslines)) {
      throw new Error('高德: ' + (j.info || j.infocode || '未知错误'));
    }
    const esc = String(ref).split('').map(ch => /[.*+?^${}()|[\]\\]/.test(ch) ? '\\' + ch : ch).join('');
    const exact = new RegExp('^' + esc + '([路(]|$)');
    return j.buslines
      .filter(b => exact.test(b.name || '') && (!b.citycode || b.citycode === CITY_CODE))
      .map((b, i) => {
        const segments = [];
        if (b.polyline) {
          // polyline 形如 "lng,lat;lng,lat;..."，多段以 "|" 分隔
          for (const part of String(b.polyline).split('|')) {
            const pts = part.split(';').map(p => p.split(',').map(Number))
              .filter(([lng, lat]) => Number.isFinite(lng) && Number.isFinite(lat))
              .map(([lng, lat]) => [lat, lng]);   // 转 [lat,lng]（Leaflet 序）
            if (pts.length >= 2) segments.push(pts);
          }
        }
        const stops = (b.busstops || []).map(s => {
          const [lng, lat] = String(s.location || ',').split(',').map(Number);
          return { name: s.name || '未命名站点', lat, lng };
        }).filter(s => Number.isFinite(s.lat) && Number.isFinite(s.lng));
        return {
          id: 'amap-' + (b.id || ref + '-' + i),
          ref,
          name: b.name || ref,
          from: (b.start_stop || '').trim(),
          to: (b.end_stop || '').trim(),
          operator: b.company || '',
          colour: '', note: '高德',
          segments, stops
        };
      })
      .filter(v => v.segments.length || v.stops.length);
  }

  return { available, getCreds, setCreds, fetchLine };
})();

window.AMapLine = AMapLine;
