#!/usr/bin/env python3  # 指定解释器
"""SQLite 备份脚本：将 .data 目录下的数据库只读复制到时间戳目录。"""  # 模块中文说明

from __future__ import annotations  # 启用未来注解语法

import argparse  # 解析命令行参数
import hashlib  # 计算 SHA256 校验值
import shutil  # 执行文件复制
from datetime import datetime  # 生成时间戳
from pathlib import Path  # 进行跨平台路径操作


def _compute_sha256(path: Path) -> str:
    """读取文件并返回十六进制 SHA256。"""  # 函数中文说明

    digest = hashlib.sha256()  # 初始化哈希对象
    with path.open("rb") as handle:  # 以只读二进制方式打开文件
        for chunk in iter(lambda: handle.read(65536), b""):  # 分块读取以避免占用大量内存
            digest.update(chunk)  # 累加哈希
    return digest.hexdigest()  # 返回十六进制摘要


def backup_sqlite(source_dir: Path, target_root: Path) -> Path:
    """执行备份并返回快照目录路径。"""  # 函数中文说明

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")  # 生成时间戳
    snapshot_dir = target_root / timestamp  # 组合快照目录
    snapshot_dir.mkdir(parents=True, exist_ok=False)  # 创建快照目录，已存在则抛错
    for db_file in sorted(source_dir.glob("*.db")):  # 遍历所有 SQLite 文件
        dest = snapshot_dir / db_file.name  # 计算目标文件路径
        shutil.copy2(db_file, dest)  # 复制文件并保留元数据
        checksum = _compute_sha256(dest)  # 计算校验值
        checksum_file = dest.with_suffix(dest.suffix + ".sha256")  # 生成校验文件路径
        checksum_file.write_text(checksum + "  " + dest.name, encoding="utf-8")  # 写入校验内容
    return snapshot_dir  # 返回快照目录路径


def main() -> None:
    """命令行入口。"""  # 函数中文说明

    parser = argparse.ArgumentParser(description="备份 .data 目录下的 SQLite 数据库")  # 构建解析器
    parser.add_argument("--source", default=".data", help="源目录，默认 .data")  # 源目录参数
    parser.add_argument("--dest", default="backups", help="备份根目录，默认 backups")  # 目标目录参数
    args = parser.parse_args()  # 解析参数
    source_dir = Path(args.source).resolve()  # 解析源目录路径
    target_root = Path(args.dest).resolve()  # 解析目标根目录
    if not source_dir.exists():  # 源目录不存在
        raise FileNotFoundError(f"源目录不存在: {source_dir}")  # 抛出异常提醒
    target_root.mkdir(parents=True, exist_ok=True)  # 确保目标根目录存在
    snapshot_dir = backup_sqlite(source_dir, target_root)  # 执行备份
    print(f"已完成备份 -> {snapshot_dir}")  # 输出结果路径


if __name__ == "__main__":  # 脚本直接执行时
    main()  # 调用入口函数
