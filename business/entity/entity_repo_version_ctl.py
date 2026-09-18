"""用于校验实体仓库版本控制的业务场景脚本。"""
# 流程：
# 1. 先 DELETE 动态生成的 entity-repo-version-test-* 仓库；404 或已删除均视为清理成功。
# 2. 创建 face/int8/ram 仓库；创建 payload 包含 default_version={name:v1, feature_length:512}。
# 3. 等待仓库 READY。
# 4. 创建 version=v1 的实体，预期 HTTP 201。
# 5. 创建 version=v2 的实体，预期 HTTP 400；实际 201 时判定失败。
# 6. DELETE 仓库并轮询确认已删除；成功清理也属于测试步骤。
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
        f"[entity_repo_version_ctl] {case_id}: expected={expected_status}, actual={actual_status}"
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
    config = load_business_config("entity", "entity_repo_version_ctl")
    collector, store, summary_path, _ = build_business_runtime(Path(__file__), "entity", "entity_repo_version_ctl", output_root)
    repo_payload = dict(config["repo"])
    repo_id = make_repo_id(str(repo_payload.pop("id_prefix")))
    repo_payload["id"] = repo_id
    feature_value = load_reference_feature()
    entity_ok = dict(config["entity_ok"])
    entity_bad = dict(config["entity_bad"])
    entity_ok["id"] = make_entity_id(str(entity_ok.pop("id_prefix")))
    entity_bad["id"] = make_entity_id(str(entity_bad.pop("id_prefix")))
    entity_ok["data"]["value"] = feature_value
    entity_bad["data"]["value"] = feature_value
    overall_status = "passed"
    case_results: list[dict[str, object]] = []

    cleanup_before = await repo_api.delete(None, case_id="cleanup-before", module="repo", action="delete", name="cleanup before version control", path=f"/repositories/{repo_id}")
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

    entity_ok_created = await entity_api.create(
        entity_ok,
        case_id="entity-ok-create",
        module="entity",
        action="create",
        name="create entity with valid version",
        path=f"/repositories/{repo_id}/entities",
    )
    store.save(entity_ok_created)
    if entity_ok_created.status_code == 201:
        collector.record_success("entity_ok_create")
    else:
        overall_status = "failed"
        entity_ok_reason = f"expected 201, got {entity_ok_created.status_code}"
        collector.record_failure("entity_ok_create", entity_ok_reason)
    _record_case_result(case_results, case_id="entity-ok-create", expected_status=201, actual_status=entity_ok_created.status_code, passed=entity_ok_created.status_code == 201, failure_reason=None if entity_ok_created.status_code == 201 else entity_ok_reason)

    entity_bad_created = await entity_api.create(
        entity_bad,
        case_id="entity-bad-create",
        module="entity",
        action="create",
        name="create entity with blocked version",
        path=f"/repositories/{repo_id}/entities",
    )
    store.save(entity_bad_created)
    if entity_bad_created.status_code == 400:
        collector.record_success("entity_bad_blocked")
    else:
        overall_status = "failed"
        entity_bad_reason = f"expected 400, got {entity_bad_created.status_code}"
        collector.record_failure("entity_bad_blocked", entity_bad_reason)
    _record_case_result(case_results, case_id="entity-bad-create", expected_status=400, actual_status=entity_bad_created.status_code, passed=entity_bad_created.status_code == 400, failure_reason=None if entity_bad_created.status_code == 400 else entity_bad_reason)

    cleanup_after = await repo_api.delete(None, case_id="cleanup-after", module="repo", action="delete", name="cleanup after version control", path=f"/repositories/{repo_id}")
    store.save(cleanup_after)
    if cleanup_after.status_code in {200, 202, 204, 404}:
        try:
            await ensure_repo_deleted(repo_api, repo_id, timeout_s=60.0)
            collector.record_success("cleanup_after")
            _record_case_result(case_results, case_id="cleanup-after", expected_status="200/202/204/404", actual_status=cleanup_after.status_code, passed=True, failure_reason=None)
        except Exception as exc:
            overall_status = "failed"
            collector.record_failure("cleanup_after", str(exc))
            _record_case_result(case_results, case_id="cleanup-after", expected_status="200/202/204/404", actual_status=cleanup_after.status_code, passed=cleanup_after.status_code in {200, 202, 204, 404}, failure_reason=str(exc))
    else:
        overall_status = "failed"
        cleanup_after_reason = f"expected 200/202/204/404, got {cleanup_after.status_code}"
        collector.record_failure("cleanup_after", cleanup_after_reason)
        _record_case_result(case_results, case_id="cleanup-after", expected_status="200/202/204/404", actual_status=cleanup_after.status_code, passed=cleanup_after.status_code in {200, 202, 204, 404}, failure_reason=cleanup_after_reason)

    summary = finalize_business_summary(collector, summary_path, overall_status=overall_status, extra={"repo_id": repo_id, "entity_ids": [entity_ok["id"], entity_bad["id"]], "case_results": case_results})
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
