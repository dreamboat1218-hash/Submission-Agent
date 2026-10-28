const { app, BrowserWindow, shell } = require('electron');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const http = require('http');
const path = require('path');

const RENDERER_URL = process.env.ELECTRON_RENDERER_URL;
const LOG_TAIL_LINES = 16;

let mainWindow = null;
let backendProcess = null;
let backendPort = null;
let backendFailure = '';
let logFile = '';
let logStream = null;

function initLog() {
  const dir = path.join(app.getPath('userData'), 'logs');
  fs.mkdirSync(dir, { recursive: true });
  logFile = path.join(dir, 'backend.log');
  logStream = fs.createWriteStream(logFile, { flags: 'a' });
  writeLog(`\n===== ${new Date().toISOString()} 启动桌面版 =====`);
  return logStream;
}

function writeLog(text) {
  if (!logStream) return;
  logStream.write(text.endsWith('\n') ? text : `${text}\n`);
}

function readLogTail() {
  try {
    const content = fs.readFileSync(logFile, 'utf8').trim();
    return content.split('\n').slice(-LOG_TAIL_LINES).join('\n');
  } catch (error) {
    return '';
  }
}

function backendExecutable() {
  const exeName = process.platform === 'win32' ? 'bid-agent-backend.exe' : 'bid-agent-backend';
  const resources = process.resourcesPath || '';
  const candidates = [
    path.join(resources, 'backend', exeName),
    path.join(resources, 'backend', 'bid-agent-backend', exeName),
    path.join(resources, exeName),
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || '';
}

function describeResources() {
  const resources = process.resourcesPath || '';
  const lines = [];
  for (const relative of ['', 'backend']) {
    const dir = path.join(resources, relative);
    try {
      const names = fs
        .readdirSync(dir, { withFileTypes: true })
        .slice(0, 40)
        .map((entry) => entry.name)
        .join(', ');
      lines.push(`${relative || '.'}\\: ${names || '(空目录)'}`);
    } catch (error) {
      lines.push(`${relative || '.'}\\: 读取失败 ${error.message}`);
    }
  }
  return lines.join('\n');
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function checkHealth(port) {
  return new Promise((resolve) => {
    let body = '';
    const req = http.get(
      { host: '127.0.0.1', port, path: '/api/health', timeout: 2000 },
      (res) => {
        res.setEncoding('utf8');
        res.on('data', (chunk) => {
          body += chunk;
        });
        res.on('end', () => {
          resolve(res.statusCode === 200 && body.includes('"status":"ok"'));
        });
      },
    );
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
    req.on('error', () => resolve(false));
  });
}

async function waitForPort(timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (backendPort) return backendPort;
    if (backendFailure) throw new Error(backendFailure);
    await wait(200);
  }
  throw new Error('内置后端未在 60 秒内输出端口，可能被安全软件拦截');
}

async function waitForHealth(port, timeoutMs = 90000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (backendFailure) throw new Error(backendFailure);
    if (await checkHealth(port)) return port;
    await wait(500);
  }
  throw new Error(`内置后端健康检查超时（端口 ${port}）`);
}

async function findRunningBackend() {
  for (let port = 8080; port <= 8089; port += 1) {
    if (await checkHealth(port)) return port;
  }
  return null;
}

async function startBackend() {
  const existing = await findRunningBackend();
  if (existing) {
    writeLog(`[reuse] 复用已在运行的内置后端：端口 ${existing}`);
    return existing;
  }
  const exe = backendExecutable();
  if (!exe) {
    throw new Error(
      `未找到内置后端：${path.join(process.resourcesPath || '', 'backend')}\n${describeResources()}`,
    );
  }
  backendPort = null;
  backendFailure = '';
  writeLog(`[spawn] ${exe}`);

  backendProcess = spawn(exe, [], {
    cwd: path.dirname(exe),
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  backendProcess.on('error', (error) => {
    backendFailure = `无法启动内置后端：${error.message}（可能被杀毒软件拦截）`;
    writeLog(`[spawn error] ${error.message}`);
  });
  backendProcess.stdout.on('data', (chunk) => {
    const text = chunk.toString();
    writeLog(text);
    const match = text.match(/BID_AGENT_PORT=(\d+)/);
    if (match) backendPort = Number(match[1]);
  });
  backendProcess.stderr.on('data', (chunk) => writeLog(chunk.toString()));
  backendProcess.on('exit', (code, signal) => {
    writeLog(`[exit] code=${code} signal=${signal}`);
    if (!backendPort) {
      backendFailure = `内置后端启动后立即退出（code=${code}）`;
    }
    backendProcess = null;
  });

  const port = await waitForPort();
  return waitForHealth(port);
}

function stopBackend() {
  if (!backendProcess) return;
  const pid = backendProcess.pid;
  backendProcess = null;
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/pid', String(pid), '/T', '/F'], { windowsHide: true });
  } else {
    try {
      process.kill(pid, 'SIGTERM');
    } catch (error) {
      // 进程已退出时忽略
    }
  }
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function splashPage(message, detail = '') {
  const detailBlock = detail
    ? `<div class="label">日志：${escapeHtml(logFile)}</div><pre>${escapeHtml(detail)}</pre>`
    : '';
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
    html,body{margin:0;height:100%;background:#0f172a;color:#e2e8f0;
      font-family:-apple-system,BlinkMacSystemFont,"Microsoft YaHei",sans-serif}
    .wrap{min-height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;padding:32px;box-sizing:border-box}
    .spinner{width:38px;height:38px;border:3px solid rgba(148,163,184,.25);
      border-top-color:#38bdf8;border-radius:50%;animation:spin 1s linear infinite}
    @keyframes spin{to{transform:rotate(360deg)}}
    .title{font-size:16px;font-weight:600}.msg{font-size:13px;color:#fca5a5;max-width:80vw;text-align:center}
    .label{font-size:12px;color:#94a3b8;margin-top:10px;word-break:break-all;text-align:center;max-width:90vw}
    pre{max-width:90vw;max-height:38vh;overflow:auto;background:#111c33;border:1px solid #1e3a5f;
      border-radius:6px;padding:12px;font-size:11px;line-height:1.5;color:#cbd5e1;white-space:pre-wrap;word-break:break-all}
  </style></head><body><div class="wrap">
  ${detail ? '' : '<div class="spinner"></div>'}
  <div class="title">招投标智能体集成系统</div>
  <div class="msg">${escapeHtml(message)}</div>${detailBlock}</div></body></html>`;
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
  initLog();
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
    writeLog(`[fatal] ${error.message}`);
    await win.loadURL(splashPage(`启动失败：${error.message}`, readLogTail()));
  }
}

const gotSingleInstanceLock = app.requestSingleInstanceLock();

if (!gotSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  });

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
  app.on('will-quit', stopBackend);
  process.on('exit', stopBackend);
}
