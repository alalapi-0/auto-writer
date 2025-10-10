// 中文注释：从 electron 导入 contextBridge 以创建受控的渲染进程桥。
import { contextBridge, ipcRenderer } from 'electron';

// 中文注释：定义健康检查函数，调用本地 Dashboard 健康接口。
const checkHealth = async (): Promise<boolean> => {
  try {
    // 中文注释：向 Dashboard 根路径发送 GET 请求，默认端口 8787。
    const response = await fetch('http://127.0.0.1:8787/');
    // 中文注释：只要返回 200-299 即视为健康。
    return response.ok;
  } catch (error) {
    // 中文注释：捕获网络异常，返回 false 表示未就绪。
    console.error('健康检查失败', error);
    return false;
  }
};

// 中文注释：定义通知函数，利用 HTML5 Notification API。
const notify = (title: string, body: string) => {
  // 中文注释：在渲染进程请求通知权限不足时，使用 IPC 请求主进程展示对话框作为降级方案。
  if (Notification.permission === 'granted') {
    // 中文注释：直接创建通知显示给用户。
    new Notification(title, { body });
  } else {
    // 中文注释：通过 IPC 通知主进程使用对话框提示，避免暴露 Node API。
    ipcRenderer.send('desktop-electron:notify', { title, body });
  }
};

// 中文注释：将安全 API 暴露给渲染进程，避免访问完整 Node 能力。
contextBridge.exposeInMainWorld('desktopAPI', {
  // 中文注释：暴露健康检查方法供前端轮询后台状态。
  checkHealth,
  // 中文注释：暴露简单通知方法，保持接口最小化。
  notify,
});

// 中文注释：声明全局 Window 接口，方便渲染进程在 TypeScript 下获得类型提示。
declare global {
  // 中文注释：扩展 Window，描述 desktopAPI 的结构。
  interface Window {
    // 中文注释：desktopAPI 提供给渲染进程的受限接口集合。
    desktopAPI: {
      // 中文注释：健康检查方法返回 Dashboard 是否可访问。
      checkHealth: () => Promise<boolean>;
      // 中文注释：通知方法允许渲染进程提示用户。
      notify: (title: string, body: string) => void;
    };
  }
}
