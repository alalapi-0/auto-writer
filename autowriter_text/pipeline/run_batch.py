"""执行批量文章生成任务。"""

from __future__ import annotations

import hashlib
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autowriter_text.logging import logger

from autowriter_text.configuration import load_config
from autowriter_text.db import ensure_pair_usage_scope, ensure_schema, get_connection
from autowriter_text.db.utils import record_usage
from autowriter_text.generator.llm_client import generate
from autowriter_text.pipeline.select_next_batch import select_next_batch
from autowriter_text.prompt_builder import build_prompt
from autowriter_text.sanitizer import sanitize
from autowriter_text.validator import validate


def _persist_article(conn, pair: dict[str, Any], content: str) -> None:
    """写入 articles 表。"""

    title = f"{pair['role_name']} · {pair['keyword_term']}"
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    conn.execute(
        "INSERT INTO articles(role_id, keyword_id, title, content, content_hash) VALUES(?,?,?,?,?)",
        (pair["role_id"], pair["keyword_id"], title, content, content_hash),
    )
    conn.commit()


def _store_rejected(pair: dict[str, Any], prompt: str, reason: str) -> None:
    """将失败记录写入 rejected 目录。"""

    rejected_dir = Path(__file__).resolve().parent.parent / "rejected"
    rejected_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    file_path = rejected_dir / f"{timestamp}_role{pair['role_id']}_kw{pair['keyword_id']}.txt"
    body = (
        f"角色: {pair['role_name']}\n关键词: {pair['keyword_term']}\n"
        f"原因: {reason}\n\nPrompt:\n{prompt}\n"
    )
    file_path.write_text(body, encoding="utf-8")


def run_batch() -> list[dict[str, Any]]:
    """执行批处理，返回成功文章元数据。"""

    config = load_config()
    with closing(get_connection()) as conn:
        ensure_schema(conn)
        ensure_pair_usage_scope(conn, config.dedup.scope)
        pairs = select_next_batch(conn)
        results: list[dict[str, Any]] = []
        for pair in pairs:
            prompt = build_prompt(pair)
            success = False
            response_text = ""
            for attempt in range(1, 3):
                try:
                    llm_output = generate(
                        prompt,
                        max_tokens=config.llm.max_tokens,
                        temperature=config.llm.temperature,
                        timeout_s=config.llm.timeout_s,
                    )
                    response_text = sanitize(llm_output, pair)
                    validate(response_text, pair)
                    _persist_article(conn, pair, response_text)
                    record_usage(
                        conn,
                        pair["role_id"],
                        pair["keyword_id"],
                        status="success",
                        message=f"attempt={attempt}",
                        success=True,
                    )
                    results.append(
                        {
                            "role_id": pair["role_id"],
                            "keyword_id": pair["keyword_id"],
                            "title": f"{pair['role_name']} · {pair['keyword_term']}",
                            "content": response_text,
                        }
                    )
                    success = True
                    break
                except Exception as exc:  # noqa: BLE001
                    logger.exception("生成文章失败: %s", exc)
                    if attempt == 2:
                        record_usage(
                            conn,
                            pair["role_id"],
                            pair["keyword_id"],
                            status="failed",
                            message=str(exc),
                            success=False,
                        )
                        _store_rejected(pair, prompt, str(exc))
            if not success:
                logger.error(
                    "组合 (role=%s, keyword=%s) 生成失败", pair["role_id"], pair["keyword_id"]
                )
        return results


__all__ = ["run_batch"]
