"""Playwright 投递烟囱测试（需本地 Cookie 才可运行）。"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import pytest


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("PLAYWRIGHT_SMOKE") != "1",
    reason="需在本地设置 PLAYWRIGHT_SMOKE=1 并完成扫码登录后运行",
)
def test_publish_smoke(tmp_path):
    """在本地环境运行 publish_one 验证流程是否打通。"""

    day = datetime.now().strftime("%Y%m%d")
    outbox_root = Path("./outbox")
    wechat_title = "测试公众号草稿"
    zhihu_title = "测试知乎草稿"
    wechat_dir = outbox_root / "wechat_mp" / day / wechat_title
    zhihu_dir = outbox_root / "zhihu" / day / zhihu_title
    for folder in [wechat_dir, zhihu_dir]:
        folder.mkdir(parents=True, exist_ok=True)
    (wechat_dir / "draft.md").write_text(f"# {wechat_title}\n\n正文", encoding="utf-8")
    (wechat_dir / "draft.html").write_text("<p>正文</p>", encoding="utf-8")
    (wechat_dir / "meta.json").write_text(json.dumps({"title": wechat_title}, ensure_ascii=False), encoding="utf-8")
    (zhihu_dir / "draft.md").write_text(f"# {zhihu_title}\n\n正文", encoding="utf-8")
    (zhihu_dir / "meta.json").write_text(json.dumps({"title": zhihu_title}, ensure_ascii=False), encoding="utf-8")

    for platform, title in [("wechat_mp", wechat_title), ("zhihu", zhihu_title)]:
        cmd = [
            "python",
            "-m",
            "scripts.publish_one",
            "--platform",
            platform,
            "--title",
            title,
            "--day",
            day,
            "--headful",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            pytest.skip(f"需本地有效 Cookie 才能运行，命令失败: {result.stderr}")
