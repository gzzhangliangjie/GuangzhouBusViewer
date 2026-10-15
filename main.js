const { app, BrowserWindow, shell } = require('electron');
const path = require('path');

// 本机 GPU 合成器对纯色层渲染异常（地图区一片米白、内容被盖住）。
// 关闭硬件加速改走软件合成。
app.disableHardwareAcceleration();

function createWindow() {
  const win = new BrowserWindow({
    width: 1360,
    height: 860,
    minWidth: 960,
    minHeight: 640,
    title: '广州公交 · 地铁拼图',
    backgroundColor: '#101418',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });

  // 页内新开链接交给系统浏览器，而不是占用应用窗口
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  win.loadFile(path.join(__dirname, 'index.html'));
}

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
