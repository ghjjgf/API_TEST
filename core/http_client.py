"""为 API_TEST 中所有 Python 侧接口调用提供统一异步 HTTP 客户端的模块。"""

from __future__ import annotations

import asyncio
from time import perf_counter

import aiohttp

from API_TEST.core.models import HttpResponseRecord
from API_TEST.core.utils import utc_timestamp


class AioHttpClient:
    """提供规范化 JSON 响应处理能力的最小共享 aiohttp 客户端。"""

    # 创建支持注入会话工厂的异步客户端，便于测试。
    def __init__(self, base_url: str, *, timeout_s: float = 30.0, session_factory=None):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._session_factory = session_factory
        self._session = None

    # 根据配置的基础地址与路径构造绝对请求地址。
    def build_url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    # 按需创建或复用底层会话。
    async def _get_session(self):
        if self._session is None:
            if self._session_factory is not None:
                self._session = self._session_factory()
            else:
                timeout = aiohttp.ClientTimeout(total=self.timeout_s)
                self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    # 实现当前模块的核心逻辑。
    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    # 进入异步上下文时初始化资源。
    async def __aenter__(self):
        await self._get_session()
        return self

    # 退出异步上下文时释放资源。
    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    # 实现当前模块的核心逻辑。
    async def request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
        *,
        timeout_s: float | None = None,
        **meta,
    ) -> HttpResponseRecord:
        session = await self._get_session()
        started = perf_counter()

        try:
            request_timeout = aiohttp.ClientTimeout(total=timeout_s) if timeout_s is not None else None
            response = await session.request(
                method=method.upper(),
                url=self.build_url(path),
                json=payload,
                timeout=request_timeout,
            )
            elapsed_ms = (perf_counter() - started) * 1000
            try:
                response_body = await response.json()
            except Exception:
                response_body = await response.text()

            return HttpResponseRecord(
                case_id=meta.get("case_id", ""),
                module=meta.get("module", ""),
                action=meta.get("action", ""),
                name=meta.get("name", ""),
                method=method.upper(),
                path=path,
                payload=payload,
                status_code=response.status,
                response_body=response_body,
                elapsed_ms=elapsed_ms,
                error_type=None,
                timestamp=utc_timestamp(),
            )
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            elapsed_ms = (perf_counter() - started) * 1000
            return HttpResponseRecord(
                case_id=meta.get("case_id", ""),
                module=meta.get("module", ""),
                action=meta.get("action", ""),
                name=meta.get("name", ""),
                method=method.upper(),
                path=path,
                payload=payload,
                status_code=None,
                response_body={"error": str(exc)},
                elapsed_ms=elapsed_ms,
                error_type=exc.__class__.__name__,
                timestamp=utc_timestamp(),
            )
