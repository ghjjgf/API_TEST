"""用于校验重复添加实体的业务场景脚本。"""
# 流程：
# 1. 先 DELETE 动态生成的 testrepo-readd-* 仓库；404 或已删除均视为清理成功。
# 2. 创建比对库并等待 READY。
# 3. 使用 entity_id 插入第一条实体，预期返回 201。
# 4. 使用相同 entity_id 再次插入实体，预期第二次返回 409。
# 5. DELETE 比对库并确认仓库已不存在。
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

from API_TEST.business.support import build_business_runtime, finalize_business_summary, load_business_config, load_reference_feature, make_entity_id, make_repo_id, open_business_apis
from API_TEST.function_test.support import ensure_repo_deleted, wait_repo_ready


# 内部辅助函数，封装当前模块的局部逻辑。
def _record_case_result(case_results: list[dict[str, object]], *, case_id: str, expected_status: int | str, actual_status: int | None, passed: bool, failure_reason: str | None = None) -> bool:
    if failure_reason is None and not passed:
        failure_reason = f"expected {expected_status}, got {actual_status}"

    print(
        f"[readd_entity] {case_id}: expected={expected_status}, actual={actual_status}"
        f"{f', reason={failure_reason}' if failure_reason else ''}"
    )
    case_results.append(
        {
            "case_id": case_id,
            "expected_status": expected_status,
            "actual_status": actual_status,
            "failure_reason": failure_reason,
            "passed": passed,
        }
    )
    return passed


# 执行当前场景的核心流程。
async def run_scenario(*, repo_api, entity_api, output_root: Path | None = None) -> dict[str, object]:
    config = load_business_config("entity", "readd_entity")
    collector, store, summary_path, _ = build_business_runtime(Path(__file__), "entity", "readd_entity", output_root)
    repo_payload = dict(config["repo"])
    repo_id = make_repo_id(str(repo_payload.pop("id_prefix")))
    repo_payload["id"] = repo_id
    entity_payload = dict(config["entity"])
    entity_id = make_entity_id(str(entity_payload.pop("id")))
    entity_payload["id"] = entity_id
    entity_payload["data"]["value"] = load_reference_feature()
    overall_status = "passed"
    case_results: list[dict[str, object]] = []

    cleanup_before = await repo_api.delete(None, case_id="cleanup-before", module="repo", action="delete", name="cleanup before readd", path=f"/repositories/{repo_id}")
    store.save(cleanup_before)
    if cleanup_before.status_code in {200, 202, 204, 404}:
        if cleanup_before.status_code != 404:
            await ensure_repo_deleted(repo_api, repo_id, timeout_s=60.0)
        collector.record_success("cleanup_before")
    else:
        overall_status = "failed"
        cleanup_before_reason = f"expected 200/202/204/404, got {cleanup_before.status_code}"
        collector.record_failure("cleanup_before", cleanup_before_reason)
    _record_case_result(case_results, case_id="cleanup-before", expected_status="200/202/204/404", actual_status=cleanup_before.status_code, passed=cleanup_before.status_code in {200, 202, 204, 404}, failure_reason=None if cleanup_before.status_code in {200, 202, 204, 404} else cleanup_before_reason)

    created = await repo_api.create(repo_payload, case_id="create", module="repo", action="create", name="create repository", path="/repositories")
    store.save(created)
    if created.status_code in {200, 201, 202}:
        collector.record_success("create")
    else:
        overall_status = "failed"
        create_reason = f"expected 200/201/202, got {created.status_code}"
        collector.record_failure("create", create_reason)
    _record_case_result(case_results, case_id="create", expected_status="200/201/202", actual_status=created.status_code, passed=created.status_code in {200, 201, 202}, failure_reason=None if created.status_code in {200, 201, 202} else create_reason)

    ready = await wait_repo_ready(repo_api, repo_id, timeout_s=30.0)
    store.save(ready)
    if ready.status_code == 200:
        collector.record_success("ready")
    else:
        overall_status = "failed"
        ready_reason = f"expected 200, got {ready.status_code}"
        collector.record_failure("ready", ready_reason)
    _record_case_result(case_results, case_id="ready", expected_status=200, actual_status=ready.status_code, passed=ready.status_code == 200, failure_reason=None if ready.status_code == 200 else ready_reason)

    first_create = await entity_api.create(
        entity_payload,
        case_id="entity-create-first",
        module="entity",
        action="create",
        name="create entity first time",
        path=f"/repositories/{repo_id}/entities",
    )
    store.save(first_create)
    if first_create.status_code == 201:
        collector.record_success("entity_create_first")
    else:
        overall_status = "failed"
        first_reason = f"expected 201, got {first_create.status_code}"
        collector.record_failure("entity_create_first", first_reason)
    _record_case_result(case_results, case_id="entity-create-first", expected_status=201, actual_status=first_create.status_code, passed=first_create.status_code == 201, failure_reason=None if first_create.status_code == 201 else first_reason)

    second_create = await entity_api.create(
        entity_payload,
        case_id="entity-create-second",
        module="entity",
        action="create",
        name="create entity second time",
        path=f"/repositories/{repo_id}/entities",
    )
    store.save(second_create)
    if second_create.status_code == 409:
        collector.record_success("entity_create_blocked")
    else:
        overall_status = "failed"
        second_reason = f"expected 409, got {second_create.status_code}"
        collector.record_failure("entity_create_blocked", second_reason)
    _record_case_result(case_results, case_id="entity-create-second", expected_status=409, actual_status=second_create.status_code, passed=second_create.status_code == 409, failure_reason=None if second_create.status_code == 409 else second_reason)

    cleanup_after = await repo_api.delete(None, case_id="cleanup-after", module="repo", action="delete", name="cleanup after readd", path=f"/repositories/{repo_id}")
    store.save(cleanup_after)
    if cleanup_after.status_code in {200, 202, 204, 404}:
        try:
            await ensure_repo_deleted(repo_api, repo_id, timeout_s=60.0)
            collector.record_success("cleanup_after")
            _record_case_result(case_results, case_id="cleanup-after", expected_status="200/202/204/404", actual_status=cleanup_after.status_code, passed=True)
        except Exception as exc:
            overall_status = "failed"
            collector.record_failure("cleanup_after", str(exc))
            _record_case_result(case_results, case_id="cleanup-after", expected_status="200/202/204/404", actual_status=cleanup_after.status_code, passed=cleanup_after.status_code in {200, 202, 204, 404}, failure_reason=str(exc))
    else:
        overall_status = "failed"
        cleanup_after_reason = f"expected 200/202/204/404, got {cleanup_after.status_code}"
        collector.record_failure("cleanup_after", cleanup_after_reason)
        _record_case_result(case_results, case_id="cleanup-after", expected_status="200/202/204/404", actual_status=cleanup_after.status_code, passed=cleanup_after.status_code in {200, 202, 204, 404}, failure_reason=cleanup_after_reason)

    summary = finalize_business_summary(collector, summary_path, overall_status=overall_status, extra={"repo_id": repo_id, "entity_id": entity_id, "case_results": case_results})
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
