// 共享底图瓦片配置：公交地图与地铁拼图的真实地图模式都从这里取定义

const Tiles = (() => {
  const defs = {
    amap: {
      // 高德栅格瓦片，GCJ-02 坐标系（叠加 OSM 数据时需纠偏）
      // 子域名必须是 webrd01~webrd04（带前导零），无零形式不解析
      url: 'https://webrd{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
      options: { subdomains: ['01', '02', '03', '04'], maxZoom: 18, attribution: '© 高德地图' },
      needsGcj: true
    },
    osm: {
      url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      options: { maxZoom: 19, attribution: '© OpenStreetMap 贡献者' },
      needsGcj: false
    }
  };

  function createLayer(name) {
    const d = defs[name];
    return L.tileLayer(d.url, d.options);
  }

  return { defs, createLayer };
})();
