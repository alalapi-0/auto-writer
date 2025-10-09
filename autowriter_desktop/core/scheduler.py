"""跨平台定时任务管理工具。"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta
from pathlib import Path
from string import Template
from typing import Dict, Iterable, Optional

from . import paths

# 计划任务名称常量，保持多平台一致，便于识别
TASK_NAME = "AutoWriter Daily"
# LaunchAgent 的唯一标识符
LAUNCH_AGENT_LABEL = "xyz.autowriter.autowriter"
# systemd service 与 timer 的名称
SYSTEMD_SERVICE = "autowriter.service"
SYSTEMD_TIMER = "autowriter.timer"
# 存储使用的后端类型文件
BACKEND_MARKER = "backend.txt"


def ensure_scheduler_dir() -> Path:
    """返回调度器目录并确保存在。"""

    # 计算家目录下的调度器目录路径
    scheduler_dir = Path.home() / ".autowriter" / "scheduler"
    # 创建目录，允许已存在
    scheduler_dir.mkdir(parents=True, exist_ok=True)
    # 返回目录路径供调用方使用
    return scheduler_dir


def _write_runner_script(config: Dict[str, object]) -> Path:
    """生成执行具体任务的 Python 脚本。"""

    # 确保调度器目录存在
    scheduler_dir = ensure_scheduler_dir()
    # 需要写出的脚本路径
    script_path = scheduler_dir / "run_task.py"
    # 配置 JSON 文件路径
    config_path = scheduler_dir / "task_config.json"
    # 准备写入脚本的配置数据
    payload = {
        "schedule_cmd": config.get("schedule_cmd", "full"),
        "schedule_custom_cli": config.get("schedule_custom_cli", ""),
        "fail_retry": int(config.get("fail_retry", 0)),
        "fail_interval": int(config.get("fail_interval", 60)),
    }
    # 将配置写入 JSON 供脚本读取
    config_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    # 使用 Template 构建脚本，避免花括号冲突
    template = Template(
        """
#!/usr/bin/env python3
# AutoWriter 调度任务脚本，由桌面端生成。
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path($project_root)
CONFIG_FILE = Path($config_path)
CLI_PATH = PROJECT_ROOT / "autowriter_text" / "cli.py"


def _load_schedule() -> dict:
    with CONFIG_FILE.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _run_cli(args: list[str]) -> int:
    command = [sys.executable, str(CLI_PATH), *args]
    process = subprocess.run(command, cwd=str(PROJECT_ROOT), check=False)
    return process.returncode


def _run_full(count: int, date: str, cdp_port: int, retry_max: int | None, min_interval: int | None, max_interval: int | None) -> int:
    code = _run_cli(["daily", "--count", str(count)])
    if code != 0:
        return code
    code = _run_cli(["export", "all", "--date", date])
    if code != 0:
        return code
    args = [
        "auto",
        "all",
        "--date",
        date,
        "--cdp",
        "http://127.0.0.1:{}".format(cdp_port),
    ]
    if retry_max is not None:
        args.extend(["--max-retries", str(retry_max)])
    if min_interval is not None:
        args.extend(["--min-interval", str(min_interval)])
    if max_interval is not None:
        args.extend(["--max-interval", str(max_interval)])
    return _run_cli(args)


def main() -> int:
    sys.path.insert(0, str(PROJECT_ROOT))
    from autowriter_desktop.core import config as desktop_config  # noqa: PLC0415

    cfg = desktop_config.load_config()
    schedule_cfg = _load_schedule()
    date = datetime.now().strftime("%Y-%m-%d")
    schedule_cmd = schedule_cfg.get("schedule_cmd", "full")
    fail_retry = int(schedule_cfg.get("fail_retry", 0))
    fail_interval = int(schedule_cfg.get("fail_interval", 60))

    if schedule_cmd == "full":
        code = _run_full(
            int(cfg.get("default_count", 5)),
            date,
            int(cfg.get("cdp_port", 9222)),
            cfg.get("retry_max"),
            cfg.get("min_interval"),
            cfg.get("max_interval"),
        )
    elif schedule_cmd == "auto_only":
        args = [
            "auto",
            "all",
            "--date",
            date,
            "--cdp",
            "http://127.0.0.1:{}".format(int(cfg.get("cdp_port", 9222))),
        ]
        if cfg.get("retry_max") is not None:
            args.extend(["--max-retries", str(cfg.get("retry_max"))])
        if cfg.get("min_interval") is not None:
            args.extend(["--min-interval", str(cfg.get("min_interval"))])
        if cfg.get("max_interval") is not None:
            args.extend(["--max-interval", str(cfg.get("max_interval"))])
        code = _run_cli(args)
    else:
        custom_cmd = str(schedule_cfg.get("schedule_custom_cli", "")).strip()
        if not custom_cmd:
            print("未配置自定义命令", file=sys.stderr)
            return 1
        command = custom_cmd.replace("{date}", date)
        code = subprocess.call(command, cwd=str(PROJECT_ROOT), shell=True)

    if code != 0 and fail_retry > 0:
        for index in range(1, fail_retry + 1):
            print("任务失败，准备第 {} 次重试".format(index), flush=True)
            time.sleep(max(fail_interval, 1))
            if schedule_cmd == "full":
                code = _run_full(
                    int(cfg.get("default_count", 5)),
                    date,
                    int(cfg.get("cdp_port", 9222)),
                    cfg.get("retry_max"),
                    cfg.get("min_interval"),
                    cfg.get("max_interval"),
                )
            elif schedule_cmd == "auto_only":
                args = [
                    "auto",
                    "all",
                    "--date",
                    date,
                    "--cdp",
                    "http://127.0.0.1:{}".format(int(cfg.get("cdp_port", 9222))),
                ]
                if cfg.get("retry_max") is not None:
                    args.extend(["--max-retries", str(cfg.get("retry_max"))])
                if cfg.get("min_interval") is not None:
                    args.extend(["--min-interval", str(cfg.get("min_interval"))])
                if cfg.get("max_interval") is not None:
                    args.extend(["--max-interval", str(cfg.get("max_interval"))])
                code = _run_cli(args)
            else:
                command = custom_cmd.replace("{date}", date)
                code = subprocess.call(command, cwd=str(PROJECT_ROOT), shell=True)
            if code == 0:
                break
    return code


if __name__ == "__main__":
    raise SystemExit(main())
"""
    )
    script_content = template.substitute(
        project_root=repr(paths.PROJECT_ROOT),
        config_path=repr(config_path),
    )
    # 将脚本写入磁盘
    script_path.write_text(script_content, encoding="utf-8")
    # 设置可执行权限（Unix 平台需要）
    try:
        script_path.chmod(0o755)
    except PermissionError:
        pass
    # 提示脚本位置
    print(f"任务执行脚本位于: {script_path}")
    # 返回脚本路径
    return script_path


def _parse_custom_days(custom: str) -> list[int]:
    """解析自定义星期设置。"""

    # 结果列表
    result: list[int] = []
    # 遍历逗号分隔的值
    for item in custom.split(","):
        # 去除空白
        item = item.strip()
        if not item:
            continue
        try:
            # 转换成整数
            value = int(item)
        except ValueError:
            continue
        # 只接受 1-7
        if 1 <= value <= 7:
            result.append(value)
    # 去重保持顺序
    return sorted(set(result))


def _weekday_names(days: Iterable[int]) -> list[str]:
    """将数字星期转换成英文缩写。"""

    # 映射表
    mapping = {1: "MON", 2: "TUE", 3: "WED", 4: "THU", 5: "FRI", 6: "SAT", 7: "SUN"}
    # 按顺序转换
    return [mapping.get(day, "MON") for day in days]


def _store_backend(name: str) -> None:
    """记录当前使用的计划任务后端。"""

    # 写入标记文件
    marker = ensure_scheduler_dir() / BACKEND_MARKER
    marker.write_text(name, encoding="utf-8")


def _read_backend() -> str:
    """读取当前使用的计划任务后端。"""

    marker = ensure_scheduler_dir() / BACKEND_MARKER
    if marker.exists():
        return marker.read_text(encoding="utf-8").strip()
    return ""


def create_task(config: Dict[str, object]) -> None:
    """根据配置创建计划任务。"""

    # 写入执行脚本
    script_path = _write_runner_script(config)
    # 解析执行时间
    time_str = str(config.get("schedule_time", "09:00"))
    try:
        hour, minute = map(int, time_str.split(":")[:2])
    except ValueError:
        raise ValueError("时间格式应为 HH:MM") from None
    # 解析星期设置
    schedule_days = str(config.get("schedule_days", "daily"))
    custom_days = _parse_custom_days(str(config.get("schedule_custom_days", "")))
    # 获取当前平台
    system = platform.system()

    if system == "Windows":
        # 确保 .cmd 文件存在
        cmd_file = ensure_scheduler_dir() / "run_task.cmd"
        cmd_content = textwrap.dedent(
            f"""
            @echo off
            "{sys.executable}" "{script_path}"
            """
        ).strip()
        cmd_file.write_text(cmd_content, encoding="utf-8")
        print(f"Windows 批处理文件已生成: {cmd_file}")
        # 构建 schtasks 参数
        base_command = [
            "schtasks",
            "/Create",
            "/F",
            "/TN",
            TASK_NAME,
            "/TR",
            f'"{cmd_file}"',
            "/ST",
            f"{hour:02d}:{minute:02d}",
        ]
        if schedule_days == "weekdays":
            base_command.extend(["/SC", "WEEKLY", "/D", "MON,TUE,WED,THU,FRI"])
        elif schedule_days == "custom" and custom_days:
            weekdays = ",".join(_weekday_names(custom_days))
            base_command.extend(["/SC", "WEEKLY", "/D", weekdays])
        else:
            base_command.extend(["/SC", "DAILY"])
        # 先删除旧任务
        remove_task()
        # 调用系统命令
        result = subprocess.run(base_command, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"创建计划任务失败: {result.stderr.strip()}")
        print("Windows 计划任务创建成功，请在任务计划程序中查看。")
        _store_backend("windows")
        return

    if system == "Darwin":
        # LaunchAgents 目录
        agent_dir = Path.home() / "Library" / "LaunchAgents"
        agent_dir.mkdir(parents=True, exist_ok=True)
        # plist 文件存储在调度目录，随后复制到 LaunchAgents
        scheduler_dir = ensure_scheduler_dir()
        plist_source = scheduler_dir / "autowriter.plist"
        intervals: list[dict[str, int]] = []
        if schedule_days == "daily":
            intervals.append({"Hour": hour, "Minute": minute})
        elif schedule_days == "weekdays":
            mac_mapping = {1: 2, 2: 3, 3: 4, 4: 5, 5: 6}
            for weekday in range(1, 6):
                intervals.append({"Weekday": mac_mapping.get(weekday, 2), "Hour": hour, "Minute": minute})
        else:
            days = custom_days or [1, 2, 3, 4, 5, 6, 7]
            mac_mapping = {1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 1}
            for weekday in days:
                intervals.append({"Weekday": mac_mapping.get(weekday, 2), "Hour": hour, "Minute": minute})
        program_args = [sys.executable, str(script_path)]
        plist_content = textwrap.dedent(
            """
            <?xml version="1.0" encoding="UTF-8"?>
            <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
            <plist version="1.0">
            <dict>
                <key>Label</key>
                <string>{label}</string>
                <key>ProgramArguments</key>
                <array>
            """
        ).format(label=LAUNCH_AGENT_LABEL)
        for arg in program_args:
            plist_content += f"        <string>{arg}</string>\n"
        plist_content += "    </array>\n    <key>StartCalendarInterval</key>\n"
        if len(intervals) == 1:
            interval = intervals[0]
            plist_content += "    <dict>\n"
            for key, value in interval.items():
                plist_content += f"        <key>{key}</key>\n        <integer>{value}</integer>\n"
            plist_content += "    </dict>\n"
        else:
            plist_content += "    <array>\n"
            for interval in intervals:
                plist_content += "        <dict>\n"
                for key, value in interval.items():
                    plist_content += f"            <key>{key}</key>\n            <integer>{value}</integer>\n"
                plist_content += "        </dict>\n"
            plist_content += "    </array>\n"
        plist_content += textwrap.dedent(
            """
                <key>StandardOutPath</key>
                <string>{log_dir}/launchd.stdout.log</string>
                <key>StandardErrorPath</key>
                <string>{log_dir}/launchd.stderr.log</string>
            </dict>
            </plist>
            """
        ).format(log_dir=ensure_scheduler_dir())
        plist_source.write_text(plist_content, encoding="utf-8")
        plist_target = agent_dir / f"{LAUNCH_AGENT_LABEL}.plist"
        shutil.copy(plist_source, plist_target)
        print(f"LaunchAgent 文件已复制到: {plist_target}")
        subprocess.run(["launchctl", "unload", plist_target], check=False)
        result = subprocess.run(["launchctl", "load", "-w", plist_target], check=False, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"加载 LaunchAgent 失败: {result.stderr.strip()}")
        print("macOS LaunchAgent 已加载，可在 launchctl list 查询。")
        _store_backend("mac")
        return

    if system == "Linux":
        # 优先尝试 systemd --user
        service_dir = Path.home() / ".config" / "systemd" / "user"
        service_dir.mkdir(parents=True, exist_ok=True)
        scheduler_dir = ensure_scheduler_dir()
        service_source = scheduler_dir / SYSTEMD_SERVICE
        timer_source = scheduler_dir / SYSTEMD_TIMER
        service_content = textwrap.dedent(
            f"""
            [Unit]
            Description=AutoWriter scheduled task

            [Service]
            Type=oneshot
            ExecStart={sys.executable} {script_path}
            WorkingDirectory={paths.PROJECT_ROOT}
            """
        )
        service_source.write_text(service_content, encoding="utf-8")
        calendar_entries: list[str] = []
        base_time = f"{hour:02d}:{minute:02d}:00"
        if schedule_days == "daily":
            calendar_entries.append(f"*-*-* {base_time}")
        elif schedule_days == "weekdays":
            calendar_entries.append(f"Mon..Fri {base_time}")
        else:
            days = custom_days or [1, 2, 3, 4, 5, 6, 7]
            mapping = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}
            for day in days:
                calendar_entries.append(f"{mapping.get(day, 'Mon')} {base_time}")
        on_calendar = "\n".join(f"OnCalendar={entry}" for entry in calendar_entries)
        timer_content = textwrap.dedent(
            f"""
            [Unit]
            Description=AutoWriter schedule timer

            [Timer]
            {on_calendar}
            Persistent=false

            [Install]
            WantedBy=timers.target
            """
        )
        timer_source.write_text(timer_content, encoding="utf-8")
        service_target = service_dir / SYSTEMD_SERVICE
        timer_target = service_dir / SYSTEMD_TIMER
        shutil.copy(service_source, service_target)
        shutil.copy(timer_source, timer_target)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        subprocess.run(["systemctl", "--user", "disable", SYSTEMD_TIMER], check=False)
        result = subprocess.run(["systemctl", "--user", "enable", "--now", SYSTEMD_TIMER], check=False, capture_output=True, text=True)
        if result.returncode == 0:
            print("systemd --user 定时器已启用，可通过 systemctl --user status 查看。")
            _store_backend("systemd")
            return
        print(f"systemd 创建失败: {result.stderr.strip()}，尝试使用 crontab。")
        # fallback 到 crontab
        cron_entry = f"{minute} {hour} * * "
        if schedule_days == "weekdays":
            cron_entry += "1-5"
        elif schedule_days == "custom" and custom_days:
            cron_entry += ",".join(str((day % 7)) for day in custom_days)
        else:
            cron_entry += "*"
        cron_entry += f" python {script_path} # AUTOWRITER"
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False)
        lines = []
        if existing.returncode == 0:
            lines = [line for line in existing.stdout.splitlines() if "AUTOWRITER" not in line]
        lines.append(cron_entry)
        cron_text = "\n".join(lines) + "\n"
        proc = subprocess.run(["crontab", "-"], input=cron_text, text=True, capture_output=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"写入 crontab 失败: {proc.stderr.strip()}")
        print("已写入用户 crontab，可使用 crontab -l 查看。")
        _store_backend("cron")
        return

    raise RuntimeError(f"当前平台 {system} 暂不支持自动创建计划任务")


def remove_task() -> None:
    """移除计划任务。"""

    backend = _read_backend()
    system = platform.system()

    if system == "Windows":
        subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], check=False)
        print("已尝试删除 Windows 计划任务。")
        return

    if system == "Darwin":
        plist_path = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"
        subprocess.run(["launchctl", "unload", plist_path], check=False)
        if plist_path.exists():
            plist_path.unlink()
        print("已卸载 LaunchAgent。")
        return

    if system == "Linux":
        if backend == "systemd" or backend == "":
            subprocess.run(["systemctl", "--user", "disable", "--now", SYSTEMD_TIMER], check=False)
            service_target = Path.home() / ".config" / "systemd" / "user" / SYSTEMD_SERVICE
            timer_target = Path.home() / ".config" / "systemd" / "user" / SYSTEMD_TIMER
            if service_target.exists():
                service_target.unlink()
            if timer_target.exists():
                timer_target.unlink()
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
            print("已移除 systemd --user 定时器。")
        if backend == "cron":
            existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False)
            if existing.returncode == 0:
                lines = [line for line in existing.stdout.splitlines() if "AUTOWRITER" not in line]
                cron_text = "\n".join(lines) + "\n"
                subprocess.run(["crontab", "-"], input=cron_text, text=True, check=False)
            print("已清理 crontab 条目。")
        return

    print("当前平台无需额外清理。")


def run_now() -> None:
    """立即触发任务执行。"""

    backend = _read_backend()
    system = platform.system()

    if system == "Windows":
        subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME], check=False)
        print("已请求 Windows 计划任务立即执行。")
        return

    if system == "Darwin":
        uid = os.getuid()
        subprocess.run(["launchctl", "kickstart", "-k", f"gui/{uid}/{LAUNCH_AGENT_LABEL}"], check=False)
        print("已触发 LaunchAgent 立即执行。")
        return

    if system == "Linux":
        if backend == "systemd" or backend == "":
            subprocess.run(["systemctl", "--user", "start", SYSTEMD_SERVICE], check=False)
            print("已启动 systemd --user 服务。")
        else:
            script_path = ensure_scheduler_dir() / "run_task.py"
            subprocess.Popen([sys.executable, str(script_path)], cwd=str(paths.PROJECT_ROOT))
            print("已直接运行调度脚本。")
        return

    script_path = ensure_scheduler_dir() / "run_task.py"
    subprocess.Popen([sys.executable, str(script_path)], cwd=str(paths.PROJECT_ROOT))
    print("已直接运行调度脚本。")


def task_status() -> str:
    """返回当前计划任务状态文本。"""

    backend = _read_backend()
    system = platform.system()

    if system == "Windows":
        result = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return result.stdout
        return result.stderr

    if system == "Darwin":
        uid = os.getuid()
        result = subprocess.run(["launchctl", "print", f"gui/{uid}/{LAUNCH_AGENT_LABEL}"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return result.stdout
        return result.stderr

    if system == "Linux":
        if backend == "systemd" or backend == "":
            result = subprocess.run(["systemctl", "--user", "status", SYSTEMD_TIMER], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout
            return result.stderr
        if backend == "cron":
            result = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout
            return result.stderr

    return "未检测到计划任务，可尝试重新保存。"


def calculate_next_run(config: Dict[str, object], now: Optional[datetime] = None) -> Optional[datetime]:
    """根据配置估算下次运行时间。"""

    # 若未启用则直接返回 None
    if not config.get("schedule_enabled"):
        return None
    # 当前时间
    current = now or datetime.now()
    # 解析目标时间
    time_str = str(config.get("schedule_time", "09:00"))
    try:
        hour, minute = map(int, time_str.split(":")[:2])
    except ValueError:
        return None
    # 构造目标日期时间
    target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= current:
        target += timedelta(days=1)
    # 解析星期设置
    schedule_days = str(config.get("schedule_days", "daily"))
    custom_days = _parse_custom_days(str(config.get("schedule_custom_days", "")))
    # 循环查找下一个符合条件的日期
    for _ in range(14):
        if schedule_days == "daily":
            return target
        weekday = target.isoweekday()
        if schedule_days == "weekdays" and 1 <= weekday <= 5:
            return target
        if schedule_days == "custom":
            days = custom_days or list(range(1, 8))
            if weekday in days:
                return target
        target += timedelta(days=1)
    return None
