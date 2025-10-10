#!/usr/bin/env python3  # 指定解释器
"""从备份目录恢复 SQLite 数据库，需要显式 --force 且二次确认。"""  # 模块中文说明

from __future__ import annotations  # 启用未来注解语法

import argparse  # 解析命令行参数
import shutil  # 执行文件复制
from pathlib import Path  # 路径操作


def restore_sqlite(snapshot_dir: Path, target_dir: Path) -> None:
    """将备份目录内的 .db 文件覆盖到目标目录。"""  # 函数中文说明

    if not snapshot_dir.exists():  # 快照目录不存在
        raise FileNotFoundError(f"快照目录不存在: {snapshot_dir}")  # 抛出异常
    target_dir.mkdir(parents=True, exist_ok=True)  # 确保目标目录存在
    for db_file in sorted(snapshot_dir.glob("*.db")):  # 遍历备份中的 SQLite 文件
        dest = target_dir / db_file.name  # 计算目标路径
        shutil.copy2(db_file, dest)  # 覆盖复制
        checksum_file = db_file.with_suffix(db_file.suffix + ".sha256")  # 对应校验文件
        if checksum_file.exists():  # 若存在校验文件
            dest_checksum = dest.with_suffix(dest.suffix + ".sha256")  # 目标校验文件路径
            shutil.copy2(checksum_file, dest_checksum)  # 同步校验文件便于核验


def main() -> None:
    """命令行入口。"""  # 函数中文说明

    parser = argparse.ArgumentParser(description="从备份目录恢复 SQLite 数据库")  # 构建解析器
    parser.add_argument("snapshot", help="备份快照目录路径")  # 必填快照参数
    parser.add_argument("--target", default=".data", help="恢复目标目录，默认 .data")  # 目标目录参数
    parser.add_argument("--force", action="store_true", help="确认覆盖现有数据库")  # 强制标志
    args = parser.parse_args()  # 解析参数
    if not args.force:  # 未传入 --force
        raise SystemExit("未指定 --force，出于安全考虑终止恢复。")  # 终止执行
    answer = input("此操作将覆盖现有 SQLite 数据，输入 yes 继续: ")  # 提示二次确认
    if answer.strip().lower() != "yes":  # 用户未确认
        raise SystemExit("用户取消恢复操作。")  # 终止执行
    snapshot_dir = Path(args.snapshot).resolve()  # 解析快照路径
    target_dir = Path(args.target).resolve()  # 解析目标路径
    restore_sqlite(snapshot_dir, target_dir)  # 执行恢复
    print(f"已从 {snapshot_dir} 恢复到 {target_dir}")  # 输出结果


if __name__ == "__main__":  # 脚本直接执行时
    main()  # 调用入口函数
