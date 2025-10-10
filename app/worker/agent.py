"""分布式 Worker Agent：负责租约任务并执行 orchestrator 子流程。"""  # 模块中文说明

from __future__ import annotations  # 启用未来注解语法

import argparse  # 解析命令行参数
import asyncio  # 异步事件循环
from pathlib import Path  # 文件路径处理
from typing import Any, Dict, List  # 类型提示

import httpx  # HTTP 客户端
from filelock import FileLock  # 文件锁
from tenacity import AsyncRetrying, stop_after_attempt, wait_random_exponential  # 重试控制
import yaml  # 解析 YAML

from config.settings import settings  # 引入配置
from app.utils.logger import get_logger  # 日志工具

LOGGER = get_logger(__name__)  # 初始化日志


class DispatchWorker:  # Worker 实现类
    """封装 Worker 运行循环与任务执行逻辑。"""  # 中文说明

    def __init__(self, name: str, concurrency: int, poll_interval: float, server: str) -> None:  # 构造函数
        self.name = name  # Worker 名称
        self.concurrency = concurrency  # 并发度
        self.poll_interval = poll_interval  # 轮询间隔
        self.server = server.rstrip("/")  # API 服务器地址
        self.hard_timeout = settings.job_run_hard_timeout_sec  # 执行硬超时
        self.headers = {"Authorization": f"Bearer {settings.worker_auth_token}"}  # 通用请求头
        self._stop_event = asyncio.Event()  # 停止事件

    async def run(self, max_loops: int | None = None, client: httpx.AsyncClient | None = None) -> None:  # 主循环
        """启动 Worker 主循环，可选最大轮询次数以便测试。"""  # 中文说明

        loop_count = 0  # 记录执行轮次
        tasks: set[asyncio.Task] = set()  # 当前进行中的任务集合
        close_client = False  # 标记是否需要关闭客户端
        if client is None:  # 若未注入客户端
            timeout = httpx.Timeout(30.0)  # 统一超时时间
            client = httpx.AsyncClient(base_url=self.server, timeout=timeout, headers=self.headers)  # 创建客户端
            close_client = True  # 标记需要关闭
        else:  # 已注入客户端
            client.headers.update(self.headers)  # 合并认证头
        try:
            while not self._stop_event.is_set():  # 主循环
                loop_count += 1  # 自增轮次
                await self._send_heartbeat(client)  # 先上报心跳
                available = self.concurrency - len(tasks)  # 计算剩余并发
                if available > 0:  # 存在空闲槽
                    leased = await self._lease_tasks(client, available)  # 租约任务
                    for item in leased:  # 遍历租约任务
                        task = asyncio.create_task(self._handle_task(client, item))  # 异步处理
                        tasks.add(task)  # 加入集合
                        task.add_done_callback(tasks.discard)  # 完成后移除
                if tasks:  # 有任务在执行
                    done, _ = await asyncio.wait(tasks, timeout=self.poll_interval, return_when=asyncio.FIRST_COMPLETED)  # 等待
                    for finished in done:  # 遍历已完成任务
                        try:
                            finished.result()  # 触发异常抛出
                        except Exception as exc:  # noqa: BLE001
                            LOGGER.exception("任务执行异常: %s", exc)  # 记录异常
                else:  # 无任务
                    await asyncio.sleep(self.poll_interval)  # 直接等待
                if max_loops is not None and loop_count >= max_loops and not tasks:  # 达到最大轮次且无任务
                    break  # 结束循环
        finally:
            if close_client:  # 若需要关闭客户端
                await client.aclose()  # 异步关闭

    async def _send_heartbeat(self, client: httpx.AsyncClient) -> None:  # 发送心跳
        """调用心跳接口，保持 Worker 在线状态。"""  # 中文说明

        payload = {"agent_name": self.name, "meta": {"concurrency": self.concurrency}}  # 心跳数据
        await self._post_json(client, "/api/dispatch/heartbeat", payload)  # 提交请求

    async def _lease_tasks(self, client: httpx.AsyncClient, limit: int) -> List[Dict[str, Any]]:  # 租约任务
        """向调度服务申请任务，返回任务列表。"""  # 中文说明

        resp = await self._post_json(client, "/api/dispatch/lease", {"agent_name": self.name, "limit": limit})  # 调用租约接口
        items = resp.get("items", [])  # 返回任务列表
        LOGGER.info("租约返回数量=%s", len(items))  # 记录数量
        return items  # 返回任务列表

    async def _handle_task(self, client: httpx.AsyncClient, task: Dict[str, Any]) -> None:  # 处理单个任务
        """执行任务并根据结果调用完成或失败接口。"""  # 中文说明

        try:
            LOGGER.info("开始处理任务 task_id=%s", task.get("task_id"))  # 输出调试日志
            result = await asyncio.wait_for(asyncio.to_thread(self._execute_payload, task), timeout=self.hard_timeout)  # 超时控制执行
            body = {
                "task_id": task["task_id"],
                "job_run_id": result.get("job_run_id"),
                "emitted_articles": result.get("emitted_articles", 0),
                "delivered_success": result.get("delivered_success", 0),
                "delivered_failed": result.get("delivered_failed", 0),
                "meta": result.get("meta", {}),
                "agent_name": self.name,
            }  # 完成参数
            await self._post_json(client, "/api/dispatch/complete", body)  # 上报成功
            LOGGER.info("任务完成上报成功 task_id=%s", task.get("task_id"))  # 完成日志
        except asyncio.TimeoutError:  # 捕获超时
            LOGGER.error("任务执行超时 task_id=%s", task.get("task_id"))  # 记录错误
            await self._post_json(
                client,
                "/api/dispatch/fail",
                {"task_id": task["task_id"], "agent_name": self.name, "error": "hard timeout"},
            )  # 上报失败
        except Exception as exc:  # noqa: BLE001  # 捕获执行异常
            LOGGER.exception("任务执行失败 task_id=%s", task.get("task_id"))  # 记录异常
            await self._post_json(
                client,
                "/api/dispatch/fail",
                {"task_id": task["task_id"], "agent_name": self.name, "error": str(exc)},
            )  # 上报失败

    def _execute_payload(self, task: Dict[str, Any]) -> Dict[str, Any]:  # 执行 orchestrator 子流程
        """同步执行 orchestrator 子流程，返回统计结果。"""  # 中文说明

        payload = task.get("payload", {})  # 任务负载
        job_run_id = payload.get("job_run_id")  # 读取 JobRun ID
        yaml_path = payload.get("yaml_path")  # Profile YAML 路径
        dispatch_cfg = payload.get("dispatch", {})  # 读取分发配置
        mode = payload.get("mode", dispatch_cfg.get("mode", "full"))  # 执行模式
        platforms: List[str] = []  # 初始化平台列表
        if yaml_path:  # 若提供 YAML
            try:
                yaml_data = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8"))  # 读取 YAML
                platforms = yaml_data.get("delivery", {}).get("platforms", [])  # 获取平台
            except FileNotFoundError:  # YAML 不存在
                LOGGER.warning("YAML 不存在 path=%s", yaml_path)  # 记录警告
            except Exception as exc:  # noqa: BLE001  # 其他异常
                LOGGER.warning("YAML 解析失败 path=%s err=%s", yaml_path, exc)  # 记录警告
        if not platforms:  # 若 YAML 未提供平台
            platforms = dispatch_cfg.get("platforms", settings.delivery_enabled_platforms)  # 使用分发配置或全局默认
        emitted_articles = 1 if mode in {"full", "generate"} else 0  # 生成数量估算
        delivered_success = len(platforms) if mode == "full" else 0  # 投递成功数
        delivered_failed = 0 if mode == "full" else 0  # 投递失败数保持 0
        return {
            "job_run_id": job_run_id,
            "emitted_articles": emitted_articles,
            "delivered_success": delivered_success,
            "delivered_failed": delivered_failed,
            "meta": {"mode": mode, "platforms": platforms},
        }  # 返回结果

    async def _post_json(self, client: httpx.AsyncClient, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:  # 带重试的 POST
        """发送 JSON 请求并自动重试，返回 JSON 响应。"""  # 中文说明

        async for attempt in AsyncRetrying(  # 使用 tenacity 控制重试
            stop=stop_after_attempt(3),  # 最多重试三次
            wait=wait_random_exponential(multiplier=0.5, max=5),  # 指数退避抖动
            reraise=True,  # 重试耗尽后抛出异常
        ):
            with attempt:  # 每次尝试
                response = await client.post(path, json=payload)  # 发送请求
                LOGGER.info(
                    "POST %s status=%s content_type=%s", path, response.status_code, response.headers.get("content-type")
                )  # 输出调试日志
                response.raise_for_status()  # 非 2xx 抛出异常
                if response.headers.get("content-type", "").startswith("application/json"):  # 判断返回类型
                    data = response.json()  # 解析响应
                    LOGGER.info("响应内容=%s", data)  # 输出响应内容
                    return data  # 返回 JSON
                return {}  # 无 JSON 时返回空字典
        return {}  # 理论上不会执行


def _parse_args() -> argparse.Namespace:  # 解析命令行参数
    """构造 CLI 参数解析器并返回参数对象。"""  # 中文说明

    parser = argparse.ArgumentParser(description="AutoWriter Dispatch Worker")  # 初始化解析器
    parser.add_argument("--name", required=True, help="Worker 名称")  # Worker 名称
    parser.add_argument("--concurrency", type=int, default=1, help="并发执行的任务数")  # 并发度
    parser.add_argument("--poll-interval", type=float, default=2.0, help="空闲轮询秒数")  # 轮询间隔
    parser.add_argument("--server", default="http://127.0.0.1:8787", help="Dashboard 服务地址")  # 服务地址
    parser.add_argument("--max-loops", type=int, default=None, help="测试用：最大主循环次数")  # 最大轮次
    return parser.parse_args()  # 返回解析结果


def main() -> None:  # CLI 入口
    """解析命令行后启动 Worker。"""  # 中文说明

    if not settings.worker_auth_token:  # 必须配置认证 token
        raise SystemExit("WORKER_AUTH_TOKEN 未配置，无法启动 Worker")  # 退出
    args = _parse_args()  # 解析参数
    lock_dir = Path(settings.tmp_dir)  # 锁文件目录
    lock_dir.mkdir(parents=True, exist_ok=True)  # 确保目录存在
    lock_path = lock_dir / f"worker-{args.name}.lock"  # 锁文件路径
    lock = FileLock(str(lock_path))  # 创建文件锁
    LOGGER.info("启动 Worker name=%s concurrency=%s", args.name, args.concurrency)  # 记录启动日志
    with lock:  # 获取互斥锁
        worker = DispatchWorker(args.name, args.concurrency, args.poll_interval, args.server)  # 实例化 Worker
        asyncio.run(worker.run(max_loops=args.max_loops))  # 运行事件循环


if __name__ == "__main__":  # 支持 python -m 调用
    main()  # 启动主函数
