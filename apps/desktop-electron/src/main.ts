// 中文注释：从 electron 导入应用生命周期控制、窗口构造、托盘与菜单等 API，并处理渲染进程通知。
import { app, BrowserWindow, Tray, Menu, nativeImage, dialog, ipcMain } from 'electron';
// 中文注释：导入 Node.js 的 child_process 模块以便启动后端 Python 服务。
import { spawn, ChildProcess } from 'node:child_process';
// 中文注释：导入 Node.js 的 path 模块以处理图标路径等跨平台问题。
import { join, dirname } from 'node:path';
// 中文注释：导入 Node.js 的 url 模块用于计算 ESM 环境下的 __dirname。
import { fileURLToPath } from 'node:url';
// 中文注释：导入 Node.js 的 process 模块便于读取平台信息。
import process from 'node:process';

// 中文注释：在 ESModule 环境中手动还原 __filename 与 __dirname，确保路径解析跨平台可用。
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// 中文注释：声明主窗口变量，方便在不同函数中访问和控制。
let mainWindow: BrowserWindow | null = null;
// 中文注释：保存 Dashboard 与 Scheduler 子进程引用，方便退出时清理。
let dashboardProcess: ChildProcess | null = null;
let schedulerProcess: ChildProcess | null = null;
// 中文注释：托盘对象引用用于避免被垃圾回收导致托盘消失。
let tray: Tray | null = null;

// 中文注释：统一定义服务地址，避免硬编码多个位置。
const DASHBOARD_URL = 'http://127.0.0.1:8787/';
// 中文注释：定义调用 Dashboard API 的基础路径，后续托盘菜单需要。
const DASHBOARD_API_RUN_PROFILE = 'http://127.0.0.1:8787/api/profiles/run/default';
// 中文注释：预加载脚本路径，electron-vite 在开发态会输出到 dist/preload/main.js。
const PRELOAD_PATH = join(__dirname, '../preload/main.js');

// 中文注释：根据平台决定是否使用 shell 启动进程，Windows 上需要 shell 才能解析 python 命令。
const shouldUseShell = process.platform === 'win32';

// 中文注释：封装通用的子进程启动逻辑，便于记录日志与处理异常。
const startService = (label: string, args: string[]): ChildProcess => {
  // 中文注释：通过 spawn 启动 python 子进程，继承当前终端输出便于调试。
  const child = spawn('python', args, { stdio: 'inherit', shell: shouldUseShell });
  // 中文注释：监听子进程异常，记录并弹窗提醒开发者。
  child.on('error', (error) => {
    // 中文注释：在控制台打印错误方便日志分析。
    console.error(`[${label}] 子进程启动异常`, error);
    // 中文注释：使用对话框提示，提醒开发者注意服务状态。
    dialog.showErrorBox(`${label} 服务异常`, `无法启动 ${label}：${error.message}`);
  });
  // 中文注释：监听子进程退出，非手动退出时提示开发者。
  child.on('exit', (code, signal) => {
    // 中文注释：输出退出信息帮助定位问题。
    console.warn(`[${label}] 子进程退出，代码：${code}，信号：${signal}`);
    // 中文注释：如果窗口仍在运行且非正常退出，则提示用户。
    if (mainWindow && code !== 0) {
      dialog.showMessageBox(mainWindow, {
        type: 'warning',
        title: `${label} 服务已退出`,
        message: `${label} 已退出，代码：${code}，信号：${signal}`,
      });
    }
  });
  // 中文注释：返回子进程引用供外部保存。
  return child;
};

// 中文注释：封装优雅关闭逻辑，确保多平台都能安全退出。
const stopService = (child: ChildProcess | null, label: string) => {
  // 中文注释：若进程不存在则无需处理。
  if (!child) {
    return;
  }
  // 中文注释：根据平台决定发送的信号，Windows 上 SIGTERM 会转换为 TerminateProcess。
  const signal = process.platform === 'win32' ? undefined : 'SIGTERM';
  try {
    // 中文注释：发送退出信号，避免强制杀死导致资源未释放。
    child.kill(signal);
  } catch (error) {
    // 中文注释：捕获潜在异常，输出到控制台协助排查。
    console.error(`[${label}] 关闭时出现异常`, error);
  }
};

// 中文注释：创建浏览器窗口，加载 Dashboard 页面。
const createWindow = () => {
  // 中文注释：新建窗口时移除菜单以贴近桌面客户端体验。
  mainWindow = new BrowserWindow({
    width: 1280, // 中文注释：设置默认宽度，兼顾可视性。
    height: 800, // 中文注释：设置默认高度，方便展示 Dashboard。
    autoHideMenuBar: true, // 中文注释：隐藏默认菜单栏，保持界面简洁。
    webPreferences: {
      preload: PRELOAD_PATH, // 中文注释：指定预加载脚本，确保安全通信。
    },
  });

  // 中文注释：确保窗口可缩放以满足不同屏幕需求。
  mainWindow.setResizable(true);
  // 中文注释：在窗口就绪后加载 Dashboard 服务地址。
  mainWindow.loadURL(DASHBOARD_URL).catch((error) => {
    // 中文注释：捕获加载错误提示开发者服务可能未启动。
    console.error('加载 Dashboard 失败', error);
  });

  // 中文注释：监听窗口关闭事件以清理资源。
  mainWindow.on('closed', () => {
    // 中文注释：关闭窗口时清理引用，避免内存泄漏。
    mainWindow = null;
  });
};

// 中文注释：创建托盘菜单，提供快捷操作。
const createTray = () => {
  // 中文注释：使用 1x1 像素透明图片作为占位，避免未提供图标导致某些平台报错。
  const trayIcon = nativeImage.createFromDataURL('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYGD4DwABAwEAffOjGQAAAABJRU5ErkJggg==');
  // 中文注释：初始化托盘对象，防止在 macOS 上未设置图标导致托盘不可见。
  tray = new Tray(trayIcon);
  // 中文注释：设置托盘提示文字，帮助用户区分应用。
  tray.setToolTip('Auto Writer 桌面壳');

  // 中文注释：定义托盘菜单项。
  const contextMenu = Menu.buildFromTemplate([
    {
      label: '打开窗口', // 中文注释：点击可重新显示主窗口。
      click: () => {
        if (mainWindow) {
          // 中文注释：若窗口隐藏则显示并聚焦。
          mainWindow.show();
          // 中文注释：调用 focus 以确保窗口在最前。
          mainWindow.focus();
        } else {
          // 中文注释：窗口不存在时重新创建。
          createWindow();
        }
      },
    },
    {
      label: '立即运行某 Profile', // 中文注释：调用本地 Dashboard API 触发指定 Profile。
      click: async () => {
        try {
          // 中文注释：使用 Node.js 原生 fetch 发送请求，避免额外依赖。
          const response = await fetch(DASHBOARD_API_RUN_PROFILE, { method: 'POST' });
          // 中文注释：根据响应状态给出反馈。
          if (response.ok) {
            // 中文注释：displayBalloon 仅在 Windows 支持，使用可选链避免其他平台异常。
            tray?.displayBalloon?.({
              title: '任务已触发', // 中文注释：气泡标题提示成功。
              content: '成功请求 Dashboard 执行 Profile。', // 中文注释：气泡内容说明已触发。
            });
          } else {
            // 中文注释：同理，在 macOS/Linux 上该方法不存在，需判空处理。
            tray?.displayBalloon?.({
              title: '任务触发失败', // 中文注释：失败时提示标题。
              content: `服务响应状态：${response.status}`, // 中文注释：展示具体的 HTTP 状态码。
            });
          }
        } catch (error) {
          // 中文注释：请求失败时打印错误并提示用户。
          console.error('调用 Dashboard API 失败', error);
          // 中文注释：Windows 上弹气泡提示，其他平台则忽略该方法。
          tray?.displayBalloon?.({
            title: '任务触发失败', // 中文注释：重复使用失败标题保持一致性。
            content: '无法连接 Dashboard 服务，请检查后端状态。', // 中文注释：提示用户检查本地服务。
          });
        }
      },
    },
    {
      label: '退出', // 中文注释：托盘退出选项确保子进程被清理。
      click: () => {
        // 中文注释：主动触发应用退出，统一走 app.quit 流程。
        app.quit();
      },
    },
  ]);

  // 中文注释：将菜单绑定到托盘图标，兼容 Windows / Linux。
  tray.setContextMenu(contextMenu);
  // 中文注释：在 macOS 上支持点击图标显示菜单。
  tray.on('click', () => tray?.popUpContextMenu());
};

// 中文注释：监听预加载脚本发送的通知事件，用对话框进行兜底提示。
ipcMain.on('desktop-electron:notify', (_event, payload: { title: string; body: string }) => {
  // 中文注释：优先在已有窗口上弹出消息框，保持用户感知一致。
  const window = BrowserWindow.getFocusedWindow() || mainWindow;
  if (window) {
    // 中文注释：窗口存在时使用模态提示，避免窗口隐藏后用户错过信息。
    dialog.showMessageBox(window, {
      type: 'info', // 中文注释：使用信息类型窗口提示。
      title: payload.title, // 中文注释：采用渲染进程传递的标题。
      message: payload.body, // 中文注释：正文显示详细内容。
    });
  } else {
    // 中文注释：无窗口时使用系统级错误框提示，确保信息可见。
    dialog.showErrorBox(payload.title, payload.body);
  }
});

// 中文注释：应用就绪后启动服务并创建窗口。
app.whenReady().then(() => {
  // 中文注释：先启动后端服务，确保 Dashboard 可访问。
  dashboardProcess = startService('Dashboard', ['-m', 'app.dashboard.server']); // 中文注释：启动 Dashboard FastAPI 服务。
  schedulerProcess = startService('Scheduler', ['-m', 'app.scheduler.service']); // 中文注释：启动 Scheduler 调度服务。
  // 中文注释：创建前端窗口与托盘。
  createWindow(); // 中文注释：构建主窗口并加载 Dashboard。
  createTray(); // 中文注释：初始化托盘图标与菜单。

  // 中文注释：macOS 上应用激活时若无窗口则重新创建。
  app.on('activate', () => {
    // 中文注释：若当前无可见窗口则重新构建。
    if (BrowserWindow.getAllWindows().length === 0) {
      // 中文注释：调用封装函数创建新窗口。
      createWindow();
    }
  });
});

// 中文注释：监听所有窗口关闭事件，Windows/Linux 直接退出，macOS 继续保留进程。
app.on('window-all-closed', () => {
  // 中文注释：仅在非 macOS 平台执行完全退出。
  if (process.platform !== 'darwin') {
    // 中文注释：非 macOS 平台直接退出应用。
    app.quit();
  }
});

// 中文注释：在应用退出前确保清理所有子进程。
app.on('before-quit', () => {
  // 中文注释：停止 Dashboard 服务。
  stopService(dashboardProcess, 'Dashboard');
  // 中文注释：停止 Scheduler 服务。
  stopService(schedulerProcess, 'Scheduler');
  // 中文注释：销毁托盘图标，避免应用退出后残留。
  tray?.destroy();
  // 中文注释：重置托盘引用，防止悬挂指针。 
  tray = null;
});

// 中文注释：捕获未处理异常与 Promise 拒绝，避免进程崩溃并输出调试信息。
process.on('uncaughtException', (error) => {
  // 中文注释：将未捕获异常输出到控制台，方便开发态定位问题。
  console.error('主进程未捕获异常', error);
});
process.on('unhandledRejection', (reason) => {
  // 中文注释：记录未处理的 Promise 拒绝原因，避免静默失败。
  console.error('主进程未处理的 Promise 拒绝', reason);
});

// 中文注释：在进程即将退出时再次尝试清理子进程，防止出现僵尸进程。
process.on('exit', () => {
  // 中文注释：重复调用以确保 Dashboard 进程被终止。
  stopService(dashboardProcess, 'Dashboard');
  // 中文注释：同理，确保 Scheduler 进程退出。
  stopService(schedulerProcess, 'Scheduler');
});
