"""封装对 CLI 的子进程调用。"""
from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Optional, Tuple

from . import paths

CLI_SCRIPT = paths.PROJECT_ROOT / "autowriter_text" / "cli.py"
_PROCESS_LOCK = threading.Lock()
_CURRENT_PROCESS: Optional[subprocess.Popen[str]] = None


def run_cli(args: list[str], on_line: Callable[[str], None], cwd: Optional[str | Path] = None) -> Tuple[int, Path]:
    """执行 CLI 命令并实时输出。"""
    command = [sys.executable, str(CLI_SCRIPT), *args]
    workdir = str(cwd or paths.PROJECT_ROOT)
    on_line(f"执行命令: {' '.join(command)}")
    # 创建子进程并将 stderr 合并到 stdout，便于统一展示
    process = subprocess.Popen(
        command,
        cwd=workdir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )
    global _CURRENT_PROCESS
    # 记录当前进程，便于外部取消
    with _PROCESS_LOCK:
        _CURRENT_PROCESS = process
    try:
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.rstrip("\n")
            on_line(line)
        process.stdout.close()
        return_code = process.wait()
    finally:
        with _PROCESS_LOCK:
            _CURRENT_PROCESS = None
    log_path = paths.automation_log_dir()
    return return_code, log_path


def cancel_current_process() -> None:
    """尝试终止当前运行的 CLI 进程。"""
    with _PROCESS_LOCK:
        process = _CURRENT_PROCESS
    if process and process.poll() is None:
        process.terminate()


def run_generate(count: int, on_line: Callable[[str], None]) -> Tuple[int, Path]:
    """调用生成命令。"""
    args = ["daily", "--count", str(count)]
    return_code, _ = run_cli(args, on_line)
    target_dir = paths.exports_dir()
    return return_code, target_dir


def run_export(platform: str, date: str, on_line: Callable[[str], None]) -> Tuple[int, Path]:
    """调用导出命令。"""
    args = ["export", platform, "--date", date]
    return_code, _ = run_cli(args, on_line)
    target_dir = paths.exports_dir(date=date, platform=None if platform == "all" else platform)
    return return_code, target_dir


def run_auto(
    platform: str,
    date: str,
    cdp_port: int,
    on_line: Callable[[str], None],
    dry_run: bool = False,
    max_retries: Optional[int] = None,
    min_interval: Optional[int] = None,
    max_interval: Optional[int] = None,
) -> Tuple[int, Path]:
    """调用自动送草稿命令。"""
    args: list[str] = [
        "auto",
        platform,
        "--date",
        date,
        "--cdp",
        f"http://127.0.0.1:{cdp_port}",
    ]
    if dry_run:
        args.append("--dry-run")
    if max_retries is not None:
        args.extend(["--max-retries", str(max_retries)])
    if min_interval is not None:
        args.extend(["--min-interval", str(min_interval)])
    if max_interval is not None:
        args.extend(["--max-interval", str(max_interval)])
    return_code, log_dir = run_cli(args, on_line)
    target_dir = paths.automation_log_dir(date)
    return return_code, target_dir
