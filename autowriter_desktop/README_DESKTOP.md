# AutoWriter 桌面版

## 环境准备
```bash
pip install -r requirements.txt
# 首次安装 Playwright 内核（如未安装）
playwright install chromium

# 启动桌面应用（开发）
python autowriter_desktop/main.py
```

## 启动带调试端口的 Chrome
- Windows:
  ```powershell
  "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
  ```
- macOS:
  ```bash
  /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
  ```
- Linux:
  ```bash
  google-chrome --remote-debugging-port=9222
  ```

## 打包
```bash
pyinstaller --noconfirm --name "AutoWriter" --onefile autowriter_desktop/main.py
# 产物在 dist/AutoWriter[.exe]
```

## 定时任务
- 在桌面端左侧导航打开“定时任务”页，可配置启用开关、运行时间、频率（每日/工作日/自定义星期）以及执行内容（全流程、仅送草稿或自定义 CLI）。
- 配置保存后会在不同平台生成对应计划任务：
  - **Windows**：调用 `schtasks` 创建计划任务，任务文件与脚本位于 `~/.autowriter/scheduler/`。
  - **macOS**：生成 LaunchAgent `plist` 并加载，配置文件同时保存在 `~/.autowriter/scheduler/`。
  - **Linux**：优先创建 `systemd --user` service/timer，若不可用则自动写入带 `# AUTOWRITER` 标记的 `crontab` 项。
- 顶部状态栏可快速启用/停用定时任务，并显示下一次预计运行时间。所有生成的脚本/配置均保存在 `~/.autowriter/scheduler/` 目录，请勿提交到仓库。
- 失败重试次数与间隔可在页面中设置，定时任务执行脚本会按配置自动重试。

## 通知与异常
- 应用启动时会注册系统托盘图标，任务完成后会弹出通知，失败时点击通知可快速打开对应日期的日志目录。
- 当自动化检测到“需要登录”“验证码”“批量失败”等关键提示时，会弹出阻塞的 `QMessageBox` 提醒用户及时处理。
- 通知功能使用 Qt 原生托盘接口，无需额外依赖，如需关闭托盘图标可退出应用。

## 常见问题
- 登录失效或验证码，打开 `automation_logs/` 中对应日期目录查看截图与 summary.json。
- 自动化运行报错时，可在桌面应用的日志窗口查看实时输出。
- 若桌面应用无法连接浏览器，请确认使用 `--remote-debugging-port` 启动 Chromium/Chrome。
