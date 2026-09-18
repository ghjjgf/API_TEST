"""用于校验仓库 rotate 配置与淘汰行为的业务场景脚本。"""
# 流程：
# 1. 创建动态 id 的 business-rotate-repo-* 仓库，capacity=5、Rotate=true。
# 2. 连续创建 rotate-1 ~ rotate-6，6 次均预期 HTTP 201。
# 3. GET rotate-1，预期 HTTP 404。
# 4. GET rotate-2，预期 HTTP 404。
# 5. 最后删除测试仓库。
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
def _repo_option(record, key: str) -> str | None:
    value = _body_dict(record).get("options", {})
    if isinstance(value, dict):
        option = value.get(key)
        return str(option) if isinstance(option, str) else None
    return None


# 内部辅助函数，封装当前模块的局部逻辑。
async def _wait_repo_ready(repo_api, store, *, repo_id: str, timeout_s: float = 30.0):
    # 实现当前模块的核心逻辑。
    async def getter():
        return await repo_api.get(None, case_id=f"repo-ready-{repo_id}", module="repo", action="get", name=f"wait repo {repo_id} ready", path=f"/repositories/{repo_id}")

    return await poll_and_save(store, getter, lambda record: record.status_code == 200, timeout_s=timeout_s)


# 内部辅助函数，封装当前模块的局部逻辑。
async def _ensure_repo_deleted(repo_api, store, *, repo_id: str, timeout_s: float = 60.0):
    # 实现当前模块的核心逻辑。
    async def getter():
        return await repo_api.get(None, case_id=f"repo-delete-{repo_id}", module="repo", action="get", name=f"wait repo {repo_id} deleted", path=f"/repositories/{repo_id}")

    return await poll_and_save(store, getter, lambda record: record.status_code in {400, 404}, timeout_s=timeout_s)


# 内部辅助函数，封装当前模块的局部逻辑。
async def _cleanup_repo(repo_api, store, *, repo_id: str):
    cleanup = await repo_api.delete(None, case_id="cleanup", module="repo", action="delete", name="cleanup rotate repo", path=f"/repositories/{repo_id}")
    store.save(cleanup)
    if cleanup.status_code not in {200, 202, 204, 404}:
        raise RuntimeError(f"expected 200/202/204/404, got {cleanup.status_code}")
    if cleanup.status_code != 404:
        await _ensure_repo_deleted(repo_api, store, repo_id=repo_id, timeout_s=60.0)
    return cleanup


# 内部辅助函数，封装当前模块的局部逻辑。
async def _create_entity(entity_api, store, *, repo_id: str, entity_id: str, value: str):
    record = await entity_api.create({"id": entity_id, "data": {"type": "feature", "value": value}, "location_id": "loc-001"}, case_id=f"entity-create-{entity_id}", module="entity", action="create", name=f"create entity {entity_id}", path=f"/repositories/{repo_id}/entities")
    store.save(record)
    return record


# 内部辅助函数，封装当前模块的局部逻辑。
async def _get_entity(entity_api, store, *, repo_id: str, entity_id: str, case_id: str):
    record = await entity_api.get(None, case_id=case_id, module="entity", action="get", name=f"get entity {entity_id}", path=f"/repositories/{repo_id}/entities/{entity_id}")
    store.save(record)
    return record


# 执行当前场景的核心流程。
async def run_scenario(*, repo_api, entity_api, output_root: Path | None = None) -> dict[str, object]:
    config = load_business_config("repo", "rotate")
    collector, store, summary_path, _ = build_business_runtime(Path(__file__), "repo", "rotate", output_root)
    repo_payload = dict(config["repo"])
    repo_id = make_repo_id(str(repo_payload.pop("id_prefix")))
    repo_payload["id"] = repo_id
    feature_value = load_reference_feature()
    overall_status = "passed"
    case_results: list[dict[str, object]] = []

    try:
        created = await repo_api.create(repo_payload, case_id="create", module="repo", action="create", name="create rotate repo", path="/repositories")
        store.save(created)
        create_ok = created.status_code == 202
        if create_ok:
            collector.record_success("create")
        else:
            overall_status = "failed"
            create_reason = failure_reason_from_body(created.response_body, f"expected 200/201/202, got {created.status_code}")
            collector.record_failure("create", create_reason)
        record_case_result(case_results, prefix="rotate", case_id="create", expected_status="200/201/202", actual_status=created.status_code, passed=create_ok, failure_reason=None if create_ok else create_reason)

        ready = await _wait_repo_ready(repo_api, store, repo_id=repo_id, timeout_s=30.0)
        ready_ok = ready.status_code == 200
        if not ready_ok:
            overall_status = "failed"
            ready_reason = failure_reason_from_body(ready.response_body, f"expected 200, got {ready.status_code}")
            collector.record_failure("create-ready", ready_reason)
            record_case_result(case_results, prefix="rotate", case_id="create-ready", expected_status=200, actual_status=ready.status_code, passed=False, failure_reason=ready_reason)

        option_ok = _repo_option(ready, "Rotate") == "true"
        if not option_ok:
            overall_status = "failed"
            option_reason = f"expected Rotate=true, got {_repo_option(ready, 'Rotate')}"
            collector.record_failure("create-option", option_reason)
            record_case_result(case_results, prefix="rotate", case_id="create-option", expected_status="Rotate=true", actual_status=_repo_option(ready, "Rotate"), passed=False, failure_reason=option_reason)

        for idx in range(1, 7):
            entity_record = await _create_entity(entity_api, store, repo_id=repo_id, entity_id=f"rotate-{idx}", value=feature_value)
            entity_ok = entity_record.status_code == 201
            if entity_ok:
                collector.record_success(f"entity_{idx}")
            else:
                overall_status = "failed"
                entity_reason = failure_reason_from_body(entity_record.response_body, f"expected 201, got {entity_record.status_code}")
                collector.record_failure(f"entity_{idx}", entity_reason)
            record_case_result(case_results, prefix="rotate", case_id=f"entity-create-{idx}", expected_status=201, actual_status=entity_record.status_code, passed=entity_ok, failure_reason=None if entity_ok else entity_reason)

        first_get = await _get_entity(entity_api, store, repo_id=repo_id, entity_id="rotate-1", case_id="entity-get-first")
        first_get_ok = first_get.status_code == 404
        if first_get_ok:
            collector.record_success("entity_first_evicted")
        else:
            overall_status = "failed"
            first_get_reason = f"expected 404, got {first_get.status_code}"
            collector.record_failure("entity_first_evicted", first_get_reason)
        record_case_result(case_results, prefix="rotate", case_id="entity-get-first", expected_status=404, actual_status=first_get.status_code, passed=first_get_ok, failure_reason=None if first_get_ok else first_get_reason)
        second_get = await _get_entity(entity_api, store, repo_id=repo_id, entity_id="rotate-2", case_id="entity-get-second")
        second_get_ok = second_get.status_code == 404
        if second_get_ok:
            collector.record_success("entity_second_evicted")
        else:
            overall_status = "failed"
            second_get_reason = f"expected 404, got {second_get.status_code}"
            collector.record_failure("entity_second_evicted", second_get_reason)
        record_case_result(case_results, prefix="rotate", case_id="entity-get-second", expected_status=404, actual_status=second_get.status_code, passed=second_get_ok, failure_reason=None if second_get_ok else second_get_reason)
    except Exception as exc:
        overall_status = "failed"
        collector.record_failure("rotate", str(exc))
        record_case_result(case_results, prefix="rotate", case_id="scenario-error", expected_status="no exception", actual_status=None, passed=False, failure_reason=str(exc))
    finally:
        try:
            cleanup_record = await _cleanup_repo(repo_api, store, repo_id=repo_id)
            collector.record_success("cleanup")
            record_case_result(case_results, prefix="rotate", case_id="cleanup", expected_status="200/202/204/404", actual_status=cleanup_record.status_code, passed=True, failure_reason=None)
        except Exception as exc:
            overall_status = "failed"
            collector.record_failure("cleanup", str(exc))
            record_case_result(case_results, prefix="rotate", case_id="cleanup-error", expected_status="cleanup ok", actual_status=None, passed=False, failure_reason=str(exc))
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
