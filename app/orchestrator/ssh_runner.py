"""通过 SSH 执行远程 worker 的占位实现。"""

from __future__ import annotations  # 启用未来注解语法

import os  # TODO: 继承并更新当前环境变量
import shutil  # 复制文件到临时目录
import subprocess  # 启动子进程模拟远程执行
import sys  # 获取当前 Python 解释器
from pathlib import Path  # 处理路径对象
from typing import Tuple  # 类型标注

from config.settings import SSHConfig  # 导入 SSH 配置数据类


class SSHRunner:
    """负责将作业文件传输到 VPS 并触发 worker。"""

    def __init__(self, ssh_config: SSHConfig):
        self.ssh_config = ssh_config  # 保存 SSH 配置
        self.workdir = Path(ssh_config.workdir or "/tmp/autowriter_run")  # 解析远程工作目录（此处视为本地路径模拟）
        self.workdir.mkdir(parents=True, exist_ok=True)  # 确保目录存在
        self.remote_job_path = self.workdir / "job.json"  # 约定远程 job.json 路径
        self.remote_env_path = self.workdir / ".env.runtime"  # 约定远程环境变量文件
        self.remote_result_path = self.workdir / "result.json"  # 约定远程 result.json 路径
        self.remote_log_path = self.workdir / "worker.log.txt"  # 约定远程日志路径

    @property
    def is_configured(self) -> bool:
        """判断 SSH 信息是否完整，用于决定是否执行远程步骤。"""

        return bool(self.ssh_config.host and self.ssh_config.user)  # 同时存在 host 与 user 时视为已配置

    def stage_files(self, job_path: Path, env_path: Path) -> None:
        """拷贝 job.json 与 .env.runtime 到工作目录。"""

        shutil.copy2(job_path, self.remote_job_path)  # 拷贝 job.json
        shutil.copy2(env_path, self.remote_env_path)  # 拷贝 .env.runtime

    def run_remote_worker(self) -> subprocess.CompletedProcess[bytes]:
        """通过本地子进程模拟 SSH 执行 remote_worker。"""

        command = [  # 构造命令行参数列表
            sys.executable,
            "-m",
            "app.worker.remote_worker",
            "--job",
            str(self.remote_job_path),
            "--env",
            str(self.remote_env_path),
            "--output",
            str(self.remote_result_path),
            "--log",
            str(self.remote_log_path),
        ]
        return subprocess.run(command, check=True, capture_output=True)  # 执行命令并捕获输出

    def collect_results(self) -> Tuple[Path, Path]:
        """返回远程执行生成的结果与日志路径。"""

        return self.remote_result_path, self.remote_log_path  # 直接返回本地模拟路径

    def cleanup_remote_env(self) -> None:
        """删除远程环境变量文件以避免密钥残留。"""

        if self.remote_env_path.exists():  # 若文件存在
            self.remote_env_path.unlink()  # 删除文件


def run_remote_job(temp_dir: Path, env_file: Path, command: list[str]) -> int:
    """使用生成的 env_file 与 command 运行远程作业（或本地模拟）。"""

    try:
        env: dict[str, str] = {}  # TODO: 收集凭据键值
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():  # TODO: 跳过空行
                continue
            key, value = line.split("=", 1)
            env[key] = value
        full_env = dict(os.environ)  # TODO: 复制当前环境
        full_env.update(env)  # TODO: 覆盖敏感变量
        proc = subprocess.run(command, env=full_env, capture_output=True, text=True)
        # TODO: 把 stdout/stderr 写入 logs_dir（下一轮扩展）
        return proc.returncode
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)  # TODO: 无论结果如何都要删除临时目录
