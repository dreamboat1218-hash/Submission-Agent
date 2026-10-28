const { app, BrowserWindow, shell } = require('electron');
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const path = require('path');

const RENDERER_URL = process.env.ELECTRON_RENDERER_URL;

let mainWindow = null;
let backendProcess = null;
let backendPort = null;

function backendExecutable() {
  const exeName = process.platform === 'win32' ? 'bid-agent-backend.exe' : 'bid-agent-backend';
  const candidate = path.join(process.resourcesPath || '', 'backend', exeName);
  return fs.existsSync(candidate) ? candidate : null;
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function checkHealth(port) {
  return new Promise((resolve) => {
    const req = http.get(
      { host: '127.0.0.1', port, path: '/api/health', timeout: 2000 },
      (res) => {
        res.resume();
        resolve(res.statusCode === 200);
      },
    );
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
    req.on('error', () => resolve(false));
  });
}

async function waitForPort(timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (backendPort) return backendPort;
    await wait(200);
  }
  throw new Error('未能获取内置后端服务端口');
}

async function waitForHealth(port, timeoutMs = 120000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await checkHealth(port)) return;
    await wait(500);
  }
  throw new Error('内置后端启动超时，请检查是否被杀毒软件拦截');
}

async function startBackend() {
  const exe = backendExecutable();
  if (!exe) {
    throw new Error('未找到内置后端，请使用完整安装包或先执行 npm run dev:electron');
  }
  backendProcess = spawn(exe, [], {
    cwd: path.dirname(exe),
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  backendProcess.stdout.on('data', (chunk) => {
    const text = chunk.toString();
    process.stdout.write(text);
    const match = text.match(/BID_AGENT_PORT=(\d+)/);
    if (match) backendPort = Number(match[1]);
  });
  backendProcess.stderr.on('data', (chunk) => process.stderr.write(chunk.toString()));
  backendProcess.on('exit', (code) => {
    console.log(`内置后端已退出：${code}`);
    backendProcess = null;
  });

  const port = await waitForPort();
  await waitForHealth(port);
  return port;
}

function stopBackend() {
  if (!backendProcess) return;
  const pid = backendProcess.pid;
  backendProcess = null;
  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', String(pid), '/T', '/F'], { windowsHide: true });
  } else {
    try {
      process.kill(pid, 'SIGTERM');
    } catch (error) {
      // 进程已退出时忽略
    }
  }
}

function splashPage(message) {
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
    html,body{margin:0;height:100%;background:#0f172a;color:#e2e8f0;
      font-family:-apple-system,BlinkMacSystemFont,"Microsoft YaHei",sans-serif}
    .wrap{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px}
    .spinner{width:38px;height:38px;border:3px solid rgba(148,163,184,.25);
      border-top-color:#38bdf8;border-radius:50%;animation:spin 1s linear infinite}
    @keyframes spin{to{transform:rotate(360deg)}}
    .title{font-size:16px;font-weight:600}.msg{font-size:13px;color:#94a3b8;max-width:80vw;text-align:center}
  </style></head><body><div class="wrap"><div class="spinner"></div>
  <div class="title">招投标智能体集成系统</div><div class="msg">${message}</div></div></body></html>`;
  return `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: '招投标智能体集成系统',
    show: false,
    backgroundColor: '#0f172a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
  return mainWindow;
}

async function bootstrap() {
  const win = createWindow();
  if (RENDERER_URL) {
    await win.loadURL(RENDERER_URL);
    return;
  }
  await win.loadURL(splashPage('正在启动本地服务，请稍候…'));
  try {
    const port = await startBackend();
    await win.loadURL(`http://127.0.0.1:${port}/`);
  } catch (error) {
    await win.loadURL(splashPage(`启动失败：${error.message}`));
  }
}

app.whenReady().then(bootstrap);

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    void bootstrap();
  }
});

app.on('window-all-closed', () => {
  stopBackend();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', stopBackend);
