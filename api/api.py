"""统一封装 repo、entity、search 与 detect 接口适配逻辑的顶层模块。"""

from __future__ import annotations

from typing import Any


class RepoApi:
    """用于处理仓库相关接口操作的异步适配器。"""

    # 保存仓库接口操作共用的 HTTP 客户端。
    def __init__(self, client):
        self.client = client

    # 内部请求封装，统一转发到共享 HTTP 客户端。
    async def _request(self, default_method: str, payload: dict[str, Any] | None, **meta):
        method = meta.pop("method", default_method)
        path = meta.pop("path", "/repositories")
        return await self.client.request_json(method, path, payload, **meta)

    # 实现当前模块的核心逻辑。
    async def create(self, payload: dict[str, Any], **meta):
        return await self._request("POST", payload, **meta)

    # 实现当前模块的核心逻辑。
    async def get(self, payload: dict[str, Any] | None = None, **meta):
        return await self._request("GET", None, **meta)

    # 实现当前模块的核心逻辑。
    async def list(self, payload: dict[str, Any] | None = None, **meta):
        return await self._request("GET", None, **meta)

    # 实现当前模块的核心逻辑。
    async def update(self, payload: dict[str, Any], **meta):
        return await self._request("PUT", payload, **meta)

    # 实现当前模块的核心逻辑。
    async def compare(self, payload: dict[str, Any], **meta):
        method = meta.pop("method", "POST")
        path = meta.pop("path", "/repositories/compare")
        return await self.client.request_json(method, path, payload, **meta)

    # 实现当前模块的核心逻辑。
    async def delete(self, payload: dict[str, Any] | None = None, **meta):
        return await self._request("DELETE", payload, **meta)


class EntityApi:
    """用于处理实体相关接口操作的异步适配器。"""

    # 保存实体接口操作共用的 HTTP 客户端。
    def __init__(self, client):
        self.client = client

    # 内部请求封装，统一转发到共享 HTTP 客户端。
    async def _request(self, default_method: str, payload: dict[str, Any] | None, **meta):
        method = meta.pop("method", default_method)
        path = meta.pop("path", "/repositories/testrepo-entity/entities")
        return await self.client.request_json(method, path, payload, **meta)

    # 实现当前模块的核心逻辑。
    async def create(self, payload: dict[str, Any], **meta):
        return await self._request("POST", payload, **meta)

    # 实现当前模块的核心逻辑。
    async def get(self, payload: dict[str, Any] | None = None, **meta):
        return await self._request("GET", None, **meta)

    # 实现当前模块的核心逻辑。
    async def update(self, payload: dict[str, Any], **meta):
        return await self._request("PUT", payload, **meta)

    # 实现当前模块的核心逻辑。
    async def delete(self, payload: dict[str, Any] | None = None, **meta):
        return await self._request("DELETE", payload, **meta)


class SearchApi:
    """用于处理仓库搜索接口操作的异步适配器。"""

    # 保存搜索接口操作共用的 HTTP 客户端。
    def __init__(self, client):
        self.client = client

    # 实现当前模块的核心逻辑。
    async def query(self, payload: dict[str, Any], **meta):
        method = meta.pop("method", "POST")
        path = meta.pop("path", "/repositories/search")
        return await self.client.request_json(method, path, payload, **meta)


class DetectApi:
    """用于处理检测服务接口操作的异步适配器。"""

    # 保存检测接口操作共用的 HTTP 客户端。
    def __init__(self, client):
        self.client = client

    # 实现当前模块的核心逻辑。
    async def run(self, payload: dict[str, Any], **meta):
        method = meta.pop("method", "POST")
        path = meta.pop("path", None)
        if path is None:
            detect_type = meta.pop("detect_type", None) or payload.get("detect_type") or "all"
            path = f"/ai/detect/{detect_type}"
        return await self.client.request_json(method, path, payload, **meta)
