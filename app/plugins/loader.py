"""插件加载器，实现过滤与导出 Hook。"""  # 模块中文说明

from __future__ import annotations  # 启用未来注解语法

import importlib.util  # 动态加载模块
from dataclasses import dataclass  # 使用 dataclass 存储插件信息
from pathlib import Path  # 处理路径
from typing import Callable, Dict, List, Tuple  # 类型提示

from config.settings import settings  # 引入配置
from app.db.migrate_sched import sched_session_scope  # 调度库 Session
from app.db.models_sched import PluginRegistry  # 插件注册表模型
from app.utils.logger import get_logger  # 日志工具
from app.telemetry.metrics import inc_plugin_error  # 引入插件错误指标

LOGGER = get_logger(__name__)  # 初始化日志


@dataclass
class PluginInfo:  # 定义插件信息数据类
    """存储插件的基本属性和可调用 Hook。"""  # 中文说明

    name: str  # 插件名称
    kind: str  # 插件类型 filters/exporters
    module: object  # 加载后的模块对象
    hooks: Dict[str, Callable]  # 可用的 Hook 函数字典
    version: str  # 插件版本


class PluginManager:  # 插件管理器
    """负责扫描目录、加载插件并提供 Hook。"""  # 中文说明

    def __init__(self) -> None:  # 构造函数
        self._plugins: Dict[str, List[PluginInfo]] = {"filters": [], "exporters": []}  # 初始化插件容器
        self._enabled = self._parse_enabled(settings.plugins_enabled)  # 解析启用配置

    def _parse_enabled(self, raw: str) -> Dict[str, List[str]]:  # 解析启用配置
        """将配置字符串解析成 {kind: [name]} 结构。"""  # 中文说明

        result: Dict[str, List[str]] = {}
        if not raw:
            return result
        for chunk in raw.split(";"):
            if not chunk:
                continue
            try:
                kind, name = chunk.split(",", 1)
            except ValueError:
                LOGGER.warning("插件启用配置格式错误 chunk=%s", chunk)
                continue
            result.setdefault(kind.strip(), []).append(name.strip())
        return result

    def load(self) -> None:  # 加载插件
        """扫描插件目录并加载符合配置的插件。"""  # 中文说明

        base = Path(settings.plugins_dir).expanduser()
        base.mkdir(parents=True, exist_ok=True)
        for kind_dir in base.iterdir():
            if not kind_dir.is_dir():
                continue
            kind = kind_dir.name
            for plugin_dir in kind_dir.iterdir():
                if not plugin_dir.is_dir():
                    continue
                if self._enabled and plugin_dir.name not in self._enabled.get(kind, []):
                    LOGGER.debug("插件未在启用列表中，跳过 kind=%s name=%s", kind, plugin_dir.name)
                    continue
                module_path = plugin_dir / "plugin.py"
                if not module_path.exists():
                    LOGGER.warning("插件缺少 plugin.py path=%s", module_path)
                    continue
                info = self._load_plugin(kind, plugin_dir.name, module_path)
                if info:
                    self._plugins.setdefault(kind, []).append(info)
                    self._record_registry(info, str(module_path))

    def _load_plugin(self, kind: str, name: str, path: Path) -> PluginInfo | None:  # 加载单个插件
        """通过 importlib 加载插件模块并提取 Hook。"""  # 中文说明

        try:
            spec = importlib.util.spec_from_file_location(f"plugins.{kind}.{name}", path)
            if spec is None or spec.loader is None:
                raise ImportError(f"无法加载插件 {name}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            meta = module.meta() if hasattr(module, "meta") else {"name": name, "version": "0.0.0"}
            hooks = {
                attr: getattr(module, attr)
                for attr in [
                    "on_before_generate",
                    "on_after_generate",
                    "on_before_publish",
                    "on_after_publish",
                ]
                if hasattr(module, attr)
            }
            info = PluginInfo(name=meta.get("name", name), kind=kind, module=module, hooks=hooks, version=meta.get("version", "0.0.0"))
            LOGGER.info("插件加载成功 kind=%s name=%s version=%s", kind, info.name, info.version)
            return info
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("插件加载失败 kind=%s name=%s error=%s", kind, name, exc)
            self._record_registry_error(kind, name, str(path), str(exc))
            return None

    def _record_registry(self, info: PluginInfo, path: str) -> None:  # 写入注册表
        """将插件元数据写入数据库，幂等更新。"""  # 中文说明

        with sched_session_scope() as session:
            record = (
                session.query(PluginRegistry)
                .filter(PluginRegistry.name == info.name, PluginRegistry.kind == info.kind)
                .one_or_none()
            )
            if record is None:
                record = PluginRegistry(name=info.name, kind=info.kind, path=path, version=info.version, enabled=True)
                session.add(record)
            else:
                record.path = path
                record.version = info.version
                record.enabled = True
                record.last_error = None

    def _record_registry_error(self, kind: str, name: str, path: str, error: str) -> None:  # 记录错误
        """当插件加载失败时更新注册表，方便在 Dashboard 查看原因。"""  # 中文说明

        with sched_session_scope() as session:
            record = (
                session.query(PluginRegistry)
                .filter(PluginRegistry.name == name, PluginRegistry.kind == kind)
                .one_or_none()
            )
            if record is None:
                record = PluginRegistry(name=name, kind=kind, path=path, version="0.0.0", enabled=False, last_error=error)
                session.add(record)
            else:
                record.enabled = False
                record.last_error = error

    def iter_hooks(self, kind: str, hook_name: str) -> List[Tuple[str, Callable]]:  # 返回 Hook 列表
        """按照类型返回指定 Hook 的可调用列表与插件名称。"""  # 中文说明

        return [
            (plugin.name, plugin.hooks[hook_name])  # 返回插件名称与 Hook
            for plugin in self._plugins.get(kind, [])  # 遍历注册插件
            if hook_name in plugin.hooks  # 过滤缺少 Hook 的插件
        ]  # 结果列表


_manager: PluginManager | None = None  # 模块级缓存管理器


def get_manager() -> PluginManager:  # 对外暴露获取管理器函数
    """返回全局插件管理器实例，首次调用会触发加载。"""  # 中文说明

    global _manager
    if _manager is None:
        _manager = PluginManager()
        _manager.load()
    return _manager


def apply_filter_hooks(stage: str, payload: Dict) -> Dict:  # 过滤 Hook 调用工具
    """根据阶段调用 filter 插件并返回处理后的 payload。"""  # 中文说明

    manager = get_manager()
    for plugin_name, hook in manager.iter_hooks("filters", stage):  # 遍历插件 Hook
        try:
            payload = hook(payload) or payload
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("过滤插件执行失败 stage=%s error=%s", stage, exc)
            inc_plugin_error(plugin_name)  # 记录插件错误
    return payload


def run_exporter_hook(stage: str, payload: Dict, platform: str) -> None:  # 导出 Hook 调用工具
    """触发 exporters 插件，忽略异常以保护主流程。"""  # 中文说明

    manager = get_manager()
    for plugin_name, hook in manager.iter_hooks("exporters", stage):  # 遍历导出 Hook
        try:
            hook(payload, platform)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("导出插件执行失败 stage=%s error=%s", stage, exc)
            inc_plugin_error(plugin_name)  # 记录插件错误
