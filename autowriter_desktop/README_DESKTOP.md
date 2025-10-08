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

## 常见问题
- 登录失效或验证码，打开 `automation_logs/` 中对应日期目录查看截图与 summary.json。
- 自动化运行报错时，可在桌面应用的日志窗口查看实时输出。
- 若桌面应用无法连接浏览器，请确认使用 `--remote-debugging-port` 启动 Chromium/Chrome。
