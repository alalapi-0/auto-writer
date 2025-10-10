// 中文注释：导入 electron-vite 提供的配置函数，用于统一主进程与预加载脚本的开发体验。
import { defineConfig } from 'electron-vite';
// 中文注释：导入 Node.js 的 path 模块，确保在各平台路径解析一致。
import { resolve } from 'node:path';

// 中文注释：导出默认配置，供 electron-vite 在开发态读取。
export default defineConfig({
  // 中文注释：配置主进程入口，electron-vite 会处理 TypeScript 并在开发态提供 HMR。
  main: {
    // 中文注释：指定主进程文件路径，使用 resolve 保证跨平台路径正确。
    entry: resolve(__dirname, 'src/main.ts')
  },
  // 中文注释：配置预加载脚本，确保在渲染进程安全地注入桥接 API。
  preload: {
    // 中文注释：同样指定预加载脚本入口。
    input: {
      // 中文注释：命名预加载入口为 main，便于 electron-vite 识别。
      main: resolve(__dirname, 'src/preload.ts')
    }
  },
  // 中文注释：配置渲染进程，electron-vite 底层会调用 Vite 以支持现代前端能力。
  renderer: {
    // 中文注释：指定 HTML 模板目录，后续由 Vite 处理静态资源。
    root: resolve(__dirname, 'src/renderer')
  }
});
