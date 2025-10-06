"""文章生成器模块，封装与大语言模型交互逻辑。"""

from __future__ import annotations  # 引入未来注解特性以支持前向引用

import json  # 读取风格配置文件
import random  # 提供随机选择心理特质的能力
from collections.abc import Mapping, Sequence  # 处理嵌套风格指令
from typing import Any, Dict  # 描述文章返回结构

import structlog  # 结构化日志记录器，便于追踪生成状态
from sqlalchemy import select  # 查询数据库以获取心理学主题
from sqlalchemy.orm import Session  # 类型提示，便于静态检查

from config.settings import BASE_DIR  # 提供项目根目录路径以定位模板文件
from app.db.migrate import SessionLocal  # 数据库会话工厂
from app.db.models import PsychologyTheme  # 心理学主题模型
from app.generator import character_selector  # 角色选择工具模块

LOGGER = structlog.get_logger()  # 初始化日志器
ARTICLE_PROMPT_PATH = (  # 心理学影评提示词模板路径
    BASE_DIR / "app" / "generator" / "prompts" / "article_prompt_template.txt"
)  # 通过路径拼装定位模板
STYLE_PROFILE_PATH = BASE_DIR / "app" / "generator" / "style_profile.json"  # 风格配置文件路径


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

    def _acquire_theme(self) -> PsychologyTheme:
        """获取一条未使用的心理学主题记录并标记为已使用。"""

        with self._get_session() as session:  # 使用上下文管理器确保会话释放
            stmt = (  # 构造查询语句，获取未使用的主题
                select(PsychologyTheme)
                .where(PsychologyTheme.used.is_(False))
                .order_by(PsychologyTheme.id)
                .limit(1)
            )
            theme = session.execute(stmt).scalar_one_or_none()  # 执行查询获取主题
            if theme is None:  # 若没有可用主题则记录错误并抛出异常
                LOGGER.error("no_available_theme")
                raise RuntimeError("没有可用的心理学影评主题，请补充数据库种子数据。")
            theme.used = True  # 标记主题已被使用
            session.add(theme)  # 将修改写入会话
            session.commit()  # 提交事务持久化状态
            session.refresh(theme)  # 刷新实例以确保属性更新
            LOGGER.debug(  # 记录成功获取主题的调试信息
                "theme_acquired",
                theme_id=theme.id,
                keyword=theme.psychology_keyword,
                character=theme.character_name,
                show=theme.show_name,
            )
            return theme  # 返回主题对象供后续使用

    def generate_article(self, topic: str, style_key: str = "psychology_analysis") -> Dict[str, str]:
        """根据主题生成文章草稿。"""

        template = self._load_prompt_template()  # 加载提示词模板
        theme = self._acquire_theme()  # 获取未使用的心理学主题
        character_profile = character_selector.get_random_character()  # 随机抽取角色资料
        chosen_trait = random.choice(character_profile["traits"])  # 从角色特质中随机选择一项
        style_profile = self._get_style_profile(style_key)  # 读取指定风格配置
        style_replacements = self._flatten_style_directives(style_profile)  # 展开风格指令
        replacements = {  # 构造模板占位符与实际内容的映射
            "{{心理学关键词}}": theme.psychology_keyword,
            "{{心理学定义}}": theme.psychology_definition,
            "{{角色名}}": character_profile["name"],
            "{{影视剧名}}": character_profile["work"],
            "{{角色心理特质}}": chosen_trait,
            "{{TAGS}}": chosen_trait,
        }
        replacements.update(style_replacements)  # 合并风格指令占位符
        article_body = template  # 初始化文章正文为模板内容
        for placeholder, value in replacements.items():  # 遍历占位符完成替换
            article_body = article_body.replace(placeholder, value)
        LOGGER.info(  # 记录生成完成日志，方便追踪主题与字数
            "article_generated",
            topic=topic,
            content_length=len(article_body),
            theme_id=theme.id,
        )
        title = (  # 构造模拟文章标题
            f"{theme.psychology_keyword}是一种{theme.psychology_definition} —— "
            f"{character_profile['name']}（{character_profile['work']}）"
        )
        return {
            "title": title,  # 模拟生成文章标题
            "content": article_body,  # 模拟生成文章正文
            "keywords": [
                theme.psychology_keyword,
                character_profile["name"],
                character_profile["work"],
            ],  # 根据主题构造关键词列表
            "theme": {
                "id": theme.id,
                "topic": topic,
                "character": character_profile["name"],
                "show": character_profile["work"],
                "definition": theme.psychology_definition,
            },
        }
