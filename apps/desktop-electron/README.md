# Auto Writer Electron 桌面壳（开发态）

## 启动步骤
1. 确保本仓库 Python 依赖已安装，并能运行 `python -m app.dashboard.server` 与 `python -m app.scheduler.service`。
2. 进入目录 `apps/desktop-electron` 执行 `npm install` 安装 Electron 与 Vite 基础依赖。
3. 运行 `npm run dev` 启动开发态 Electron，应用会自动并行启动 Dashboard 与 Scheduler，并在窗口中加载 `http://127.0.0.1:8787/`。

## 开发说明
- 本项目仅面向开发态调试，未提供任何打包配置，也不会产出二进制可执行文件。
- 关闭 Electron 应用或托盘菜单中的“退出”后，会向 Python 子进程发送终止信号并等待退出，避免残留僵尸进程。
- 通过托盘菜单可在任何平台快速显示窗口或请求 Dashboard 立即执行默认 Profile，便于验证调度功能。

## 常见问题
- 如果窗口持续显示“正在等待本地服务…”，请检查后端 Python 依赖是否正确安装，或端口 `8787` 是否被占用。
- Windows 平台会使用 `shell` 模式启动 Python，若系统无法识别 `python` 命令，请确认 PATH 设置或改用 `py` 命令。
- macOS 关闭全部窗口后应用仍常驻菜单栏，符合系统交互习惯，需通过托盘选择“退出”彻底关闭。
