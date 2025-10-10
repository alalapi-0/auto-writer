"""文章生成器模块，封装与大语言模型交互逻辑。"""

from __future__ import annotations  # 引入未来注解特性以支持前向引用

import json  # 读取风格配置文件
import random  # 提供随机选择心理特质的能力
from collections.abc import Mapping, Sequence  # 处理嵌套风格指令
from datetime import datetime, timedelta, timezone  # TODO: 支持软锁过期计算
from typing import Any, Dict, Mapping, Optional  # 描述文章返回结构

import structlog  # 结构化日志记录器，便于追踪生成状态
from sqlalchemy import text  # TODO: 引入 text 以执行原生 SQL
from sqlalchemy.orm import Session  # 类型提示，便于静态检查

from config.settings import BASE_DIR, settings  # TODO: 引入 settings 读取软锁配置
from app.db.migrate import SessionLocal  # 数据库会话工厂
from app.generator import character_selector  # 角色选择工具模块
from app.prompting.registry import (  # Prompt 选择工具
    choose_prompt_variant,
    get_prompt,
    list_variants,
)
from app.prompting.guards import evaluate_quality  # 质量闸门

LOGGER = structlog.get_logger()  # 初始化日志器
ARTICLE_PROMPT_PATH = (  # 心理学影评提示词模板路径
    BASE_DIR / "app" / "generator" / "prompts" / "article_prompt_template.txt"
)  # 通过路径拼装定位模板
STYLE_PROFILE_PATH = BASE_DIR / "app" / "generator" / "style_profile.json"  # 风格配置文件路径
MAX_VARIANT_ATTEMPTS = 3  # 最多尝试的 Prompt Variant 次数
MAX_ARTICLE_LENGTH = 2300  # 输出字数上限保持与质量闸门一致


def lease_theme_for_run(db: Session, run_id: str) -> Optional[dict]:
    """从主题库领取一个可用主题，但仅做软锁，不标记 used。"""

    now = datetime.now(timezone.utc)  # TODO: 获取当前 UTC 时间
    expire_at = now - timedelta(minutes=settings.lock_expire_minutes)  # TODO: 计算软锁过期阈值
    try:
        row = (
            db.execute(
                text(
                    """
                    SELECT id, psychology_keyword, psychology_definition, character_name, show_name,
                           locked_by_run_id, locked_at, used
                    FROM psychology_themes
                    WHERE (used IS NULL OR used = 0)
                      AND (locked_by_run_id IS NULL OR locked_at < :expire)
                    ORDER BY id
                    LIMIT 1
                    """
                ),
                {"expire": expire_at.isoformat()},
            )
            .mappings()
            .first()
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("TODO: 无法从数据库领取主题，请确认 psychology_themes 表存在且结构正确。") from exc

    if row is None:
        return None

    db.execute(
        text(
            """
            UPDATE psychology_themes
            SET locked_by_run_id = :run_id,
                locked_at = :now
            WHERE id = :theme_id
            """
        ),
        {"run_id": run_id, "now": now.isoformat(), "theme_id": row["id"]},
    )
    db.commit()

    result = dict(row)
    result["locked_by_run_id"] = run_id
    result["locked_at"] = now
    return result


def release_theme_lock(db: Session, theme_id: int) -> None:
    """在失败或放弃时释放软锁。"""

    try:
        db.execute(
            text(
                """
                UPDATE psychology_themes
                SET locked_by_run_id = NULL,
                    locked_at = NULL
                WHERE id = :theme_id
                """
            ),
            {"theme_id": theme_id},
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("TODO: 释放主题软锁失败，请检查数据库权限与结构。") from exc


def _load_theme_detail(db: Session, theme_id: int) -> Optional[dict]:
    """辅助函数：重新读取主题详情，确保字段齐全。"""

    stmt = text(
        """
        SELECT id, psychology_keyword, psychology_definition, character_name, show_name
        FROM psychology_themes
        WHERE id = :theme_id
        """
    )
    row = db.execute(stmt, {"theme_id": theme_id}).mappings().first()
    return dict(row) if row else None


class ArticleGenerator:
    """使用占位实现模拟文章生成行为。"""

    def __init__(self, api_key: str) -> None:
        """存储 API Key，供真实实现调用大模型服务。"""

        self.api_key = api_key  # 保存 API Key；真实场景需校验是否为空
        self._style_profiles: Dict[str, Any] | None = None  # 缓存风格配置，避免重复读取

    def _load_prompt_template(self) -> str:
        """读取心理学影评提示词模板。"""

        template = ARTICLE_PROMPT_PATH.read_text(  # 从文件系统读取模板文本
            encoding="utf-8"
        )  # 以 UTF-8 读取模板文本
        LOGGER.debug(  # 输出模板长度用于调试与监控
            "prompt_loaded",
            template_length=len(template),
            template_path=str(ARTICLE_PROMPT_PATH),
        )
        return template  # 返回模板字符串供 generate_article 使用

    def _get_session(self) -> Session:
        """创建数据库会话，方便在单元测试中重载 Session 工厂。"""

        return SessionLocal()  # 返回新的数据库会话实例

    def _load_style_profiles(self) -> Dict[str, Any]:
        """从磁盘加载风格配置并缓存。"""

        if self._style_profiles is None:
            profile_text = STYLE_PROFILE_PATH.read_text(encoding="utf-8")
            self._style_profiles = json.loads(profile_text)
            LOGGER.debug(
                "style_profile_loaded",
                profile_path=str(STYLE_PROFILE_PATH),
                available_profiles=list(self._style_profiles.keys()),
            )
        return self._style_profiles

    def _get_style_profile(self, style_key: str) -> Dict[str, Any]:
        """根据键名获取具体风格配置，不存在时抛出异常提醒补齐。"""

        profiles = self._load_style_profiles()
        if style_key not in profiles:
            LOGGER.error("style_profile_missing", requested=style_key)
            raise KeyError(f"未找到名为 {style_key} 的风格配置，请在 style_profile.json 中补充。")
        return profiles[style_key]

    def _flatten_style_directives(self, style_profile: Mapping[str, Any]) -> Dict[str, str]:
        """将嵌套的风格配置展开为模板可替换的键值。"""

        flattened: Dict[str, str] = {}

        def _walk(value: Any, path: str) -> None:
            if isinstance(value, Mapping):
                for key, nested in value.items():
                    next_path = f"{path}.{key}" if path else key
                    _walk(nested, next_path)
                return
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                rendered = "、".join(str(item) for item in value)
            else:
                rendered = str(value)
            placeholder = f"{{{{{path}}}}}"
            flattened[placeholder] = rendered

        _walk(style_profile, "STYLE")
        return flattened

    def _acquire_theme(self) -> dict:
        """获取一条未使用的心理学主题记录并仅做软锁。"""

        run_id = "article-generator-local"  # TODO: 本地生成器固定软锁 ID
        with self._get_session() as session:
            leased = lease_theme_for_run(session, run_id)
            if leased is None:
                LOGGER.error("no_available_theme")
                raise RuntimeError("没有可用的心理学影评主题，请补充数据库种子数据。")
            detail = _load_theme_detail(session, leased["id"]) or leased
            LOGGER.debug(
                "theme_leased",
                theme_id=detail.get("id"),
                keyword=detail.get("psychology_keyword"),
                character=detail.get("character_name"),
                show=detail.get("show_name"),
            )
            return detail

    def generate_article(
        self,
        topic: str,
        style_key: str = "psychology_analysis",
        profile_config: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """根据主题生成文章草稿。"""

        template = self._load_prompt_template()  # 加载提示词模板
        theme = self._acquire_theme()  # 获取未使用的心理学主题
        character_profile = character_selector.get_random_character()  # 随机抽取角色资料
        chosen_trait = random.choice(character_profile["traits"])  # 从角色特质中随机选择一项
        style_profile = self._get_style_profile(style_key)  # 读取指定风格配置
        style_replacements = self._flatten_style_directives(style_profile)  # 展开风格指令
        replacements = {  # 构造模板占位符与实际内容的映射
            "{{心理学关键词}}": theme.get("psychology_keyword", "未知关键词"),
            "{{心理学定义}}": theme.get("psychology_definition", "未知定义"),
            "{{角色名}}": character_profile["name"],
            "{{影视剧名}}": character_profile["work"],
            "{{角色心理特质}}": chosen_trait,
            "{{TAGS}}": chosen_trait,
        }
        replacements.update(style_replacements)  # 合并风格指令占位符
        prompt_section = (profile_config or {}).get("prompting", {})  # 读取 Profile 中的 Prompt 策略
        strategy_config = prompt_section.get("strategy") if isinstance(prompt_section, Mapping) else {}
        max_attempts = int(prompt_section.get("max_attempts", MAX_VARIANT_ATTEMPTS)) if isinstance(prompt_section, Mapping) else MAX_VARIANT_ATTEMPTS  # 读取最大尝试次数
        available_variants = list(list_variants())  # 列出全部 Prompt Variant
        if not available_variants:  # 若缺少 Prompt 模板
            raise RuntimeError("缺少 Prompt 模板，请在 app/prompting/prompts 目录下添加至少一个文件。")

        attempt_logs: list[Dict[str, Any]] = []  # 记录每轮质量评估结果
        chosen_variant: str | None = None  # 最终使用的 Variant
        final_report = None  # 记录最终的质量报告
        last_report = None  # 保存最近一次报告供失败时引用
        article_body = ""  # 初始化正文
        manual_review = False  # 标记是否进入人工复核

        tried: set[str] = set()  # 跟踪已尝试的 Variant
        for attempt in range(max(1, min(max_attempts, len(available_variants)))):  # 控制尝试次数
            if attempt == 0:  # 首次尝试按照策略选择
                variant, prompt_text = choose_prompt_variant(profile_config or {}, strategy_config)
            else:  # 后续尝试按未使用的 Variant 顺序回退
                fallback_candidates = [variant for variant in available_variants if variant not in tried]
                if not fallback_candidates:  # 若已尝试所有 Variant，则回退至轮询
                    variant, prompt_text = choose_prompt_variant(profile_config or {}, strategy_config)
                else:
                    variant = fallback_candidates[0]
                    prompt_text = get_prompt(variant)
            tried.add(variant)  # 记录已尝试 Variant

            prompt_instructions = "\n".join(  # 清洗 Prompt 文本，去除注释行
                line for line in prompt_text.splitlines() if not line.strip().startswith("#")
            ).strip()
            rendered_body = template  # 从模板复制一份用于替换
            for placeholder, value in replacements.items():  # 遍历占位符完成替换
                rendered_body = rendered_body.replace(placeholder, value)
            article_body = f"{prompt_instructions}\n\n{rendered_body}" if prompt_instructions else rendered_body  # 将 Prompt 指令前置便于审计
            if len(article_body) > MAX_ARTICLE_LENGTH:  # 控制输出字数上限
                article_body = article_body[:MAX_ARTICLE_LENGTH]

            title = (
                f"{theme.get('psychology_keyword', '心理学主题')}是一种{theme.get('psychology_definition', '概念')} —— "
                f"{character_profile['name']}（{character_profile['work']}）"
            )  # 构造模拟标题

            with self._get_session() as session:  # 打开数据库会话供重复度检查
                report = evaluate_quality(
                    article_body,
                    title=title,
                    keywords=[
                        theme.get("psychology_keyword", "心理学主题"),
                        character_profile["name"],
                        character_profile["work"],
                    ],
                    session=session,
                )

            attempt_logs.append(
                {
                    "variant": variant,
                    "scores": report.scores,
                    "reasons": report.reasons,
                    "passed": report.passed,
                }
            )  # 记录本轮结果
            last_report = report  # 更新最近一次报告

            LOGGER.info(
                "prompt_attempt",
                topic=topic,
                theme_id=theme.get("id"),
                variant=variant,
                passed=report.passed,
                scores=report.scores,
                reasons=report.reasons,
            )  # 记录 Prompt 尝试日志

            if report.passed:  # 若本轮通过质量闸门
                chosen_variant = variant
                final_report = report
                break

        if final_report is None:  # 所有 Variant 均未通过
            manual_review = True
            chosen_variant = attempt_logs[-1]["variant"] if attempt_logs else None
            final_report = last_report

        fallback_count = max(0, len(attempt_logs) - 1)  # 统计回退次数

        LOGGER.info(  # 记录生成完成日志，方便追踪主题与字数
            "article_generated",
            topic=topic,
            content_length=len(article_body),
            theme_id=theme.get("id"),
            variant=chosen_variant,
            manual_review=manual_review,
        )

        result = {
            "title": title,
            "content": article_body,
            "keywords": [
                theme.get("psychology_keyword", "心理学主题"),
                character_profile["name"],
                character_profile["work"],
            ],
            "theme": {
                "id": theme.get("id"),
                "topic": topic,
                "character": character_profile["name"],
                "show": character_profile["work"],
                "definition": theme.get("psychology_definition"),
            },
            "prompt_variant": chosen_variant,
            "quality_audit": {
                "variant": chosen_variant,
                "scores": final_report.scores if final_report else {},
                "reasons": final_report.reasons if final_report else [],
                "passed": bool(final_report.passed) if final_report else False,
                "fallback_count": fallback_count,
                "attempts": attempt_logs,
            },
            "manual_review": manual_review,
        }

        with self._get_session() as session:
            release_theme_lock(session, theme_id=theme["id"])  # TODO: 本地生成后主动释放软锁

        return result
