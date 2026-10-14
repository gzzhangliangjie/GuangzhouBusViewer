const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('appInfo', {
  name: '广州公交路线预览',
  version: process.env.npm_package_version || '1.0.0',
  platform: process.platform
});
