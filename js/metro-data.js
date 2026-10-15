// 地铁数据访问层：加载打包在 data/metro-data.js 的 2026 年线网数据
// （来源 OpenStreetMap 贡献者 ODbL，经 guangzhou-metro-typing 快照 + Overpass 补齐，
//  由姊妹项目 GuangzhouMetroQuiz 的 tools/gen_layout.py 生成）

const MetroData = (() => {
  let stations = [];
  let lines = [];
  const byId = new Map();   // 站名 -> station
  const byRef = new Map();  // 线路编号 -> line

  function load() {
    if (stations.length) return true;
    const d = window.METRO_DATA;
    if (!d) return false;
    stations = d.stations;
    lines = d.lines;
    stations.forEach(s => byId.set(s.id, s));
    lines.forEach(l => byRef.set(l.ref, l));
    return true;
  }

  function allStations() { load(); return stations; }
  function allLines() { load(); return lines; }
  function station(id) { load(); return byId.get(id); }
  function line(ref) { load(); return byRef.get(ref); }

  /** 一条线的全部车站（主线 + 支线，按出现顺序去重） */
  function lineStationIds(l) {
    const seen = new Set();
    const out = [];
    for (const id of l.stations) {
      if (!seen.has(id)) { seen.add(id); out.push(id); }
    }
    for (const br of l.branches || []) {
      for (const id of br) {
        if (!seen.has(id)) { seen.add(id); out.push(id); }
      }
    }
    return out;
  }

  /** 线路折线的各段（示意坐标 [sx,sy]）：主线一段，每条支线一段 */
  function schematicSegments(l) {
    const segs = [];
    const pts = arr => arr.map(id => {
      const s = byId.get(id);
      return s ? [s.sx, s.sy] : null;
    }).filter(Boolean);
    if (l.stations.length) {
      const main = pts(l.stations);
      if (l.loop && main.length > 2) main.push(main[0]);
      segs.push(main);
    }
    for (const br of l.branches || []) if (br.length) segs.push(pts(br));
    return segs;
  }

  /** 线路折线的各段（经纬度 [lat,lon]） */
  function geoSegments(l) {
    const segs = [];
    const pts = arr => arr.map(id => {
      const s = byId.get(id);
      return s ? [s.lat, s.lon] : null;
    }).filter(Boolean);
    if (l.stations.length) {
      const main = pts(l.stations);
      if (l.loop && main.length > 2) main.push(main[0]);
      segs.push(main);
    }
    for (const br of l.branches || []) if (br.length) segs.push(pts(br));
    return segs;
  }

  /** 线号徽章的显示文案：GF → 广佛，APM → APM，其余为数字 */
  function refLabel(ref) {
    if (ref === 'GF') return '广佛';
    return ref;
  }

  /** 徽章/名牌槽所在站：环线取首站，其余取末站 */
  function badgeAnchorStation(l) {
    const arr = (l.loop && l.stations.length > 2) ? l.stations : [...l.stations].reverse();
    for (const id of arr) if (byId.has(id)) return byId.get(id);
    return null;
  }

  return {
    load, allStations, allLines, station, line,
    lineStationIds, schematicSegments, geoSegments,
    refLabel, badgeAnchorStation
  };
})();
