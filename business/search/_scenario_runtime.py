"""search 业务场景的通用运行时辅助模块。"""

from __future__ import annotations

from typing import Any

from API_TEST.business.repo._scenario_support import failure_reason_from_body, poll_and_save, record_case_result
from API_TEST.core.models import HttpResponseRecord


# 实现当前模块的核心逻辑。
def body_dict(record: Any) -> dict[str, Any]:
    return record.response_body if isinstance(record.response_body, dict) else {}


# 实现当前模块的核心逻辑。
def repo_status(record: Any) -> str | None:
    value = body_dict(record).get("status")
    return str(value) if isinstance(value, str) else None


# 等待当前场景所需的资源进入目标状态。
async def wait_repo_ready(repo_api, store, *, repo_id: str, timeout_s: float = 30.0) -> HttpResponseRecord:
    # 实现当前模块的核心逻辑。
    async def getter() -> HttpResponseRecord:
        return await repo_api.get(None, case_id=f"repo-ready-{repo_id}", module="repo", action="get", name=f"wait repo {repo_id} ready", path=f"/repositories/{repo_id}")

    return await poll_and_save(store, getter, lambda record: record.status_code == 200 and repo_status(record) in {None, "READY", "ACTIVE", "SUCCESS"}, timeout_s=timeout_s)


# 确保当前场景依赖或状态满足要求。
async def ensure_repo_deleted(repo_api, store, *, repo_id: str, timeout_s: float = 60.0) -> HttpResponseRecord:
    # 实现当前模块的核心逻辑。
    async def getter() -> HttpResponseRecord:
        return await repo_api.get(None, case_id=f"repo-delete-{repo_id}", module="repo", action="get", name=f"wait repo {repo_id} deleted", path=f"/repositories/{repo_id}")

    return await poll_and_save(store, getter, lambda record: record.status_code in {400, 404}, timeout_s=timeout_s)


# 清理当前场景产生的临时资源。
async def cleanup_repo(repo_api, store, *, repo_id: str, name: str, timeout_s: float = 60.0) -> HttpResponseRecord:
    delete = await repo_api.delete(None, case_id=f"cleanup-{repo_id}", module="repo", action="delete", name=name, path=f"/repositories/{repo_id}")
    store.save(delete)
    if delete.status_code not in {200, 202, 204, 404}:
        raise AssertionError(delete.response_body)
    if delete.status_code != 404:
        await ensure_repo_deleted(repo_api, store, repo_id=repo_id, timeout_s=timeout_s)
    return delete


# 创建当前场景所需的资源或请求负载。
async def create_repo(repo_api, store, *, repo_id: str, payload: dict[str, Any], case_id: str, name: str, path: str = "/repositories") -> HttpResponseRecord:
    record = await repo_api.create(payload, case_id=case_id, module="repo", action="create", name=name, path=path)
    store.save(record)
    return record


# 创建当前场景所需的资源或请求负载。
async def create_entity(entity_api, store, *, repo_id: str, entity_id: str, payload: dict[str, Any], case_id: str, name: str) -> HttpResponseRecord:
    record = await entity_api.create(payload, case_id=case_id, module="entity", action="create", name=name, path=f"/repositories/{repo_id}/entities")
    store.save(record)
    return record


# 实现当前模块的核心逻辑。
async def search_query(search_api, store, *, payload: dict[str, Any], case_id: str, name: str) -> HttpResponseRecord:
    record = await search_api.query(payload, case_id=case_id, module="search", action="query", name=name, path="/repositories/search")
    store.save(record)
    return record


# 记录当前场景的案例结果。
def record_step(
    collector,
    case_results: list[dict[str, object]],
    *,
    prefix: str,
    case_id: str,
    expected_status: int | str,
    actual_status: int | str | None,
    passed: bool,
    failure_reason: str | None = None,
    collector_case_id: str | None = None,
    extra: dict[str, object] | None = None,
) -> bool:
    collector_case_id = collector_case_id or case_id
    if failure_reason is None and not passed:
        failure_reason = f"expected {expected_status}, got {actual_status}"
    if passed:
        collector.record_success(collector_case_id)
    else:
        collector.record_failure(collector_case_id, failure_reason or f"expected {expected_status}, got {actual_status}")
    return record_case_result(
        case_results,
        prefix=prefix,
        case_id=case_id,
        expected_status=expected_status,
        actual_status=actual_status if isinstance(actual_status, (int, str)) or actual_status is None else str(actual_status),
        passed=passed,
        failure_reason=failure_reason,
        extra=extra,
    )


# 实现当前模块的核心逻辑。
def failure_reason_or_body(response_body: Any, fallback: str) -> str:
    return failure_reason_from_body(response_body, fallback)
