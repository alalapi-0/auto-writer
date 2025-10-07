"""导出目录的打包工具。"""

from __future__ import annotations

import zipfile
from pathlib import Path

from .common import ensure_dir


def zip_dir(src_dir: str | Path, zip_path: str | Path) -> Path:
    """将目录压缩为 ZIP，保持相对路径且统一换行。"""

    src_path = Path(src_dir)
    zip_file_path = Path(zip_path)
    ensure_dir(zip_file_path.parent)
    with zipfile.ZipFile(zip_file_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in sorted(src_path.rglob("*")):
            arcname = item.relative_to(src_path)
            if item.is_dir():
                if str(arcname):
                    zf.write(item, arcname=str(arcname) + "/")
                continue
            data = item.read_bytes()
            zf.writestr(str(arcname), data)
    return zip_file_path


def bundle_all(date_dir_wechat: str | Path, date_dir_zhihu: str | Path, out_zip: str | Path) -> Path:
    """将两个平台的导出目录打包为单个 ZIP，便于一次交付。"""

    wechat_path = Path(date_dir_wechat)
    zhihu_path = Path(date_dir_zhihu)
    out_path = Path(out_zip)
    ensure_dir(out_path.parent)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for base, prefix in ((wechat_path, "wechat"), (zhihu_path, "zhihu")):
            if not base.exists():
                continue
            for item in sorted(base.rglob("*")):
                arcname = Path(prefix) / item.relative_to(base)
                if item.is_dir():
                    if item != base:
                        zf.write(item, arcname=str(arcname) + "/")
                    continue
                data = item.read_bytes()
                zf.writestr(str(arcname), data)
    return out_path


__all__ = ["bundle_all", "zip_dir"]
