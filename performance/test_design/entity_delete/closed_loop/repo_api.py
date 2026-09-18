from __future__ import annotations

from typing import Any


# 内部辅助函数，封装当前模块的局部逻辑。
async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


# 构造当前场景所需的数据。
def build_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


# 内部辅助函数，封装当前模块的局部逻辑。
async def _read_response(response: Any) -> tuple[int | None, Any]:
    status = getattr(response, "status", None)
    try:
        json_method = getattr(response, "json")
        body = await _maybe_await(json_method())
    except Exception:
        try:
            text_attr = getattr(response, "text")
            body = await _maybe_await(text_attr() if callable(text_attr) else text_attr)
        except Exception:
            body = None
    return status, body


# 创建当前场景所需的资源或请求负载。
async def create_repo_async(
    session: Any,
    *,
    base_url: str,
    repo_id: str,
    capacity: int,
    level: str,
    index_type: str,
    repo_type: str,
    template: dict[str, Any] | None,
    timeout_seconds: int,
) -> tuple[int | None, Any]:
    payload = dict(template or {})
    payload["id"] = repo_id
    payload["type"] = repo_type
    payload["capacity"] = capacity
    payload["level"] = level
    payload["index_type"] = index_type

    request = session.request(
        method="POST",
        url=build_url(base_url, "/repositories"),
        json=payload,
        timeout=timeout_seconds,
    )
    async with request as response:
        return await _read_response(response)


# 删除当前场景所需的资源或请求负载。
async def delete_repo_async(
    session: Any,
    *,
    base_url: str,
    repo_id: str,
    timeout_seconds: int,
) -> tuple[int | None, Any]:
    request = session.request(
        method="DELETE",
        url=build_url(base_url, f"/repositories/{repo_id}"),
        timeout=timeout_seconds,
    )
    async with request as response:
        return await _read_response(response)
