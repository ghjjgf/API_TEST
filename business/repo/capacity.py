"""用于校验仓库容量限制的业务场景脚本。"""
# 流程：
# 1. 创建动态 id 的 business-capacity-repo-* 仓库，capacity=7，预期创建状态 200/201/202。
# 2. 校验 capacity 回显为 7。
# 3. 连续创建 capacity-1 ~ capacity-7，7 次均预期 HTTP 201。
# 4. GET 仓库并确认 size 为 7。
# 5. 创建第 8 条实例 capacity-8，预期容量溢出返回 HTTP 409（兼容旧服务 500）。
# 6. 最后删除测试仓库。
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    repo_root = str(Path(__file__).resolve().parents[3])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

from API_TEST.business.repo._scenario_support import failure_reason_from_body, finalize_repo_summary, poll_and_save, record_case_result
from API_TEST.business.support import build_business_runtime, load_business_config, load_reference_feature, make_repo_id, open_business_apis


# 内部辅助函数，封装当前模块的局部逻辑。
def _body_dict(record) -> dict[str, object]:
    return record.response_body if isinstance(record.response_body, dict) else {}


# 内部辅助函数，封装当前模块的局部逻辑。
def _repo_capacity(record) -> int | None:
    body = _body_dict(record)
    value = body.get("capacity")
    return value if isinstance(value, int) else None


def _repo_size(record) -> int | None:
    body = _body_dict(record)
    value = body.get("size")
    return value if isinstance(value, int) else None


# 内部辅助函数，封装当前模块的局部逻辑。
def _repo_status(record) -> str | None:
    body = _body_dict(record)
    value = body.get("status")
    return str(value) if isinstance(value, str) else None


# 内部辅助函数，封装当前模块的局部逻辑。
async def _create_entity(entity_api, store, *, repo_id: str, entity_id: str, feature_value: str, location_id: str = "loc-001"):
    record = await entity_api.create(
        {
            "id": entity_id,
            "data": {
                "type": "feature",
                "value": feature_value,
            },
            "location_id": location_id,
        },
        case_id=f"entity-create-{entity_id}",
        module="entity",
        action="create",
        name=f"create entity {entity_id}",
        path=f"/repositories/{repo_id}/entities",
    )
    store.save(record)
    return record


# 内部辅助函数，封装当前模块的局部逻辑。
async def _repo_get(repo_api, store, *, repo_id: str, case_id: str):
    record = await repo_api.get(
        None,
        case_id=case_id,
        module="repo",
        action="get",
        name=f"get repo {repo_id}",
        path=f"/repositories/{repo_id}",
    )
    store.save(record)
    return record


# 内部辅助函数，封装当前模块的局部逻辑。
async def _wait_repo_ready(repo_api, store, *, repo_id: str, timeout_s: float = 30.0):
    # 实现当前模块的核心逻辑。
    async def getter():
        return await repo_api.get(
            None,
            case_id=f"repo-ready-{repo_id}",
            module="repo",
            action="get",
            name=f"wait repo {repo_id} ready",
            path=f"/repositories/{repo_id}",
        )

    return await poll_and_save(store, getter, lambda record: record.status_code == 200 and _repo_status(record) in {None, "READY", "ACTIVE", "SUCCESS"}, timeout_s=timeout_s)


async def _wait_repo_size(repo_api, store, *, repo_id: str, expected_size: int, timeout_s: float = 30.0):
    async def getter():
        return await _repo_get(repo_api, store, repo_id=repo_id, case_id="repo-after-seed")

    return await poll_and_save(
        store,
        getter,
        lambda record: record.status_code == 200 and _repo_size(record) == expected_size,
        timeout_s=timeout_s,
    )


# 内部辅助函数，封装当前模块的局部逻辑。
async def _ensure_repo_deleted(repo_api, store, *, repo_id: str, timeout_s: float = 60.0):
    # 实现当前模块的核心逻辑。
    async def getter():
        return await repo_api.get(
            None,
            case_id=f"repo-delete-{repo_id}",
            module="repo",
            action="get",
            name=f"wait repo {repo_id} deleted",
            path=f"/repositories/{repo_id}",
        )

    return await poll_and_save(store, getter, lambda record: record.status_code in {400, 404}, timeout_s=timeout_s)


# 内部辅助函数，封装当前模块的局部逻辑。
async def _cleanup_repo(repo_api, store, *, repo_id: str):
    cleanup = await repo_api.delete(
        None,
        case_id="cleanup",
        module="repo",
        action="delete",
        name="cleanup capacity repo",
        path=f"/repositories/{repo_id}",
    )
    store.save(cleanup)
    if cleanup.status_code not in {200, 202, 204, 404}:
        raise RuntimeError(f"expected 200/202/204/404, got {cleanup.status_code}")
    if cleanup.status_code != 404:
        await _ensure_repo_deleted(repo_api, store, repo_id=repo_id, timeout_s=60.0)
    return cleanup


# 执行当前场景的核心流程。
async def run_scenario(*, repo_api, entity_api, output_root: Path | None = None) -> dict[str, object]:
    config = load_business_config("repo", "capacity")
    collector, store, summary_path, _ = build_business_runtime(Path(__file__), "repo", "capacity", output_root)
    repo_payload = dict(config["repo"])
    repo_id = make_repo_id(str(repo_payload.pop("id_prefix")))
    repo_payload["id"] = repo_id
    expected_capacity = int(repo_payload.get("capacity", 7))
    feature_value = load_reference_feature()
    overall_status = "passed"
    case_results: list[dict[str, object]] = []

    try:
        created = await repo_api.create(
            repo_payload,
            case_id="create",
            module="repo",
            action="create",
            name="create capacity repo",
            path="/repositories",
        )
        store.save(created)
        create_ok = created.status_code in {200, 201, 202}
        if create_ok:
            collector.record_success("create")
        else:
            overall_status = "failed"
            create_reason = failure_reason_from_body(created.response_body, f"expected 200/201/202, got {created.status_code}")
            collector.record_failure("create", create_reason)
        record_case_result(case_results, prefix="capacity", case_id="create", expected_status="200/201/202", actual_status=created.status_code, passed=create_ok, failure_reason=None if create_ok else create_reason)

        ready = await _wait_repo_ready(repo_api, store, repo_id=repo_id, timeout_s=30.0)
        ready_ok = ready.status_code == 200
        if not ready_ok:
            overall_status = "failed"
            ready_reason = failure_reason_from_body(ready.response_body, f"expected 200, got {ready.status_code}")

        capacity_record = await _repo_get(repo_api, store, repo_id=repo_id, case_id="capacity-check")
        capacity_ok = capacity_record.status_code == 200 and _repo_capacity(capacity_record) == expected_capacity
        if capacity_ok:
            collector.record_success("capacity")
        else:
            overall_status = "failed"
            capacity_reason = f"expected capacity {expected_capacity}, got {_repo_capacity(capacity_record)}"
            collector.record_failure("capacity", capacity_reason)
        if not ready_ok and capacity_ok:
            capacity_ok = False
            capacity_reason = ready_reason
        record_case_result(case_results, prefix="capacity", case_id="capacity-check", expected_status=expected_capacity, actual_status=_repo_capacity(capacity_record), passed=capacity_ok, failure_reason=None if capacity_ok else capacity_reason)

        for idx in range(1, 8):
            entity_record = await _create_entity(entity_api, store, repo_id=repo_id, entity_id=f"capacity-{idx}", feature_value=feature_value)
            entity_ok = entity_record.status_code == 201
            if entity_ok:
                collector.record_success(f"entity_{idx}")
            else:
                overall_status = "failed"
                entity_reason = failure_reason_from_body(entity_record.response_body, f"expected 201, got {entity_record.status_code}")
                collector.record_failure(f"entity_{idx}", entity_reason)
            record_case_result(case_results, prefix="capacity", case_id=f"entity-create-capacity-{idx}", expected_status=201, actual_status=entity_record.status_code, passed=entity_ok, failure_reason=None if entity_ok else entity_reason)

        try:
            repo_get = await _wait_repo_size(
                repo_api,
                store,
                repo_id=repo_id,
                expected_size=expected_capacity,
                timeout_s=30.0,
            )
        except Exception:
            repo_get = await _repo_get(repo_api, store, repo_id=repo_id, case_id="repo-after-seed")
        size_ok = repo_get.status_code == 200 and _repo_size(repo_get) == expected_capacity
        if size_ok:
            collector.record_success("repo_after_seed")
        else:
            overall_status = "failed"
            size_reason = failure_reason_from_body(repo_get.response_body, f"expected size {expected_capacity}, got {_repo_size(repo_get)}")
            collector.record_failure("repo_after_seed", size_reason)
        record_case_result(case_results, prefix="capacity", case_id="repo-after-seed", expected_status=expected_capacity, actual_status=_repo_size(repo_get), passed=size_ok, failure_reason=None if size_ok else size_reason)

        overflow = await _create_entity(entity_api, store, repo_id=repo_id, entity_id="capacity-8", feature_value=feature_value)
        overflow_ok = overflow.status_code in {409, 500}
        overflow_reason = None
        if overflow_ok:
            collector.record_success("overflow_blocked")
        else:
            overall_status = "failed"
            overflow_reason = failure_reason_from_body(overflow.response_body, f"expected 409/500, got {overflow.status_code}")
            collector.record_failure("overflow_blocked", overflow_reason)
        if overflow_reason is None and not overflow_ok:
            overflow_reason = failure_reason_from_body(overflow.response_body, "overflow request failed")
        record_case_result(case_results, prefix="capacity", case_id="entity-create-capacity-8", expected_status="409/500", actual_status=overflow.status_code, passed=overflow_ok, failure_reason=None if overflow_ok else overflow_reason)
    except Exception as exc:
        overall_status = "failed"
        collector.record_failure("capacity", str(exc))
        record_case_result(case_results, prefix="capacity", case_id="scenario-error", expected_status="no exception", actual_status=None, passed=False, failure_reason=str(exc))
    finally:
        try:
            cleanup_record = await _cleanup_repo(repo_api, store, repo_id=repo_id)
            collector.record_success("cleanup")
            record_case_result(case_results, prefix="capacity", case_id="cleanup", expected_status="200/202/204/404", actual_status=cleanup_record.status_code, passed=True, failure_reason=None)
        except Exception as exc:
            overall_status = "failed"
            collector.record_failure("cleanup", str(exc))
            record_case_result(case_results, prefix="capacity", case_id="cleanup-error", expected_status="cleanup ok", actual_status=None, passed=False, failure_reason=str(exc))
        summary = finalize_repo_summary(collector, summary_path, overall_status=overall_status, extra={"repo_id": repo_id, "case_total": len(case_results), "case_results": case_results})

    return summary


# 程序入口，用于串起当前模块的执行流程。
async def main() -> None:
    async with open_business_apis(repo=True, entity=True) as apis:
        summary = await run_scenario(repo_api=apis["repo_api"], entity_api=apis["entity_api"])
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if os.environ.get("API_TEST_IMPORT_ONLY") == "1":
        raise SystemExit(0)
    asyncio.run(main())
