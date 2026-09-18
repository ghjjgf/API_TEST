"""用于校验搜索接口版本类型约束的业务场景脚本。"""
# 流程：
# 1. 清理并创建动态 id 的 repo-version-type-check-* 仓库，PreFilter=false，等待 READY。
# 2. 写入 entity1-1~3，数据 version=1.1.1，均预期 HTTP 201。
# 3. 使用 version=1.1.1 搜索；预期 HTTP 200，结果必须包含 entity1-1/2/3，且 similarity 非递增。
# 4. 使用 version=1.1.2 搜索；预期 HTTP 400 或 409 表示版本不匹配被拒绝。
# 5. 如果 1.1.2 搜索返回 HTTP 200，无论结果内容如何，该步骤和整体场景均判定失败。
# 6. 最后删除仓库并确认不存在。
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    repo_root = str(Path(__file__).resolve().parents[3])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

from API_TEST.business.search._scenario_runtime import cleanup_repo, create_entity, create_repo, failure_reason_or_body, record_step, search_query, wait_repo_ready
from API_TEST.business.search._scenario_support import describe_search_failure, extract_result_ids, finalize_search_summary
from API_TEST.business.support import build_business_runtime, extract_result_similarities, extract_search_results, is_nonincreasing, load_reference_feature, make_repo_id, open_business_apis


EXPECTED_RESULT_IDS = ["entity1-1", "entity1-2", "entity1-3"]


# 内部辅助函数，封装当前模块的局部逻辑。
def _build_search_payload(*, repo_id: str, version: str) -> dict[str, object]:
    return {
        "type": "face",
        "include": [
            {
                "data": {
                    "value": load_reference_feature(),
                    "type": "feature",
                    "version": version,
                }
            }
        ],
        "repositories": [repo_id],
    }


# 内部辅助函数，封装当前模块的局部逻辑。
def _missing_expected_ids(result_ids: list[str]) -> list[str]:
    return [entity_id for entity_id in EXPECTED_RESULT_IDS if entity_id not in result_ids]


# 内部辅助函数，封装当前模块的局部逻辑。
def _assert_same_version_results(payload: dict[str, Any]) -> list[str]:
    results = extract_search_results(payload)
    if not results:
        raise AssertionError("expected same-version search results")
    similarities = extract_result_similarities(results)
    if not similarities:
        raise AssertionError("expected same-version search similarities")
    if not is_nonincreasing(similarities):
        raise AssertionError(f"expected nonincreasing similarities, got {similarities}")
    result_ids = extract_result_ids(results)
    missing_expected_ids = _missing_expected_ids(result_ids)
    if missing_expected_ids:
        raise AssertionError(f"expected same-version search to include {EXPECTED_RESULT_IDS}, got {result_ids}; missing {missing_expected_ids}")
    return result_ids


# 执行当前场景的核心流程。
async def run_scenario(*, repo_api, entity_api, search_api, output_root: Path | None = None) -> dict[str, object]:
    collector, store, summary_path, _ = build_business_runtime(Path(__file__), "search", "version_type_check", output_root)
    repo_id = make_repo_id("repo-version-type-check")
    feature_value = load_reference_feature()
    overall_status = "passed"
    case_results: list[dict[str, object]] = []
    same_version_result_ids: list[str] = []
    mismatch_result_ids: list[str] = []
    mismatch_behavior = ""

    try:
        try:
            cleanup_before = await cleanup_repo(repo_api, store, repo_id=repo_id, name="cleanup version_type_check repo before run")
            record_step(collector, case_results, prefix="version_type_check", case_id="cleanup-before", expected_status="200/202/204/404", actual_status=cleanup_before.status_code, passed=True)
        except Exception as exc:
            overall_status = "failed"
            record_step(collector, case_results, prefix="version_type_check", case_id="cleanup-before-error", expected_status="cleanup ok", actual_status=None, passed=False, failure_reason=str(exc))

        created = await create_repo(repo_api, store, repo_id=repo_id, payload={"id": repo_id, "type": "face", "index_type": "int8", "level": "ram", "options": {"PreFilter": "false"}}, case_id="create", name="create version_type_check repo")
        create_ok = created.status_code in {200, 201, 202}
        if not create_ok:
            overall_status = "failed"
        create_reason = None if create_ok else failure_reason_or_body(created.response_body, f"expected 200/201/202, got {created.status_code}")
        record_step(collector, case_results, prefix="version_type_check", case_id="create", expected_status="200/201/202", actual_status=created.status_code, passed=create_ok, failure_reason=create_reason)

        if create_ok:
            ready = await wait_repo_ready(repo_api, store, repo_id=repo_id, timeout_s=30.0)
            ready_ok = ready.status_code == 200
            if not ready_ok:
                overall_status = "failed"
            ready_reason = None if ready_ok else failure_reason_or_body(ready.response_body, f"expected 200, got {ready.status_code}")
            record_step(collector, case_results, prefix="version_type_check", case_id="ready", expected_status=200, actual_status=ready.status_code, passed=ready_ok, failure_reason=ready_reason)

            if ready_ok:
                for idx in range(1, 4):
                    entity_record = await create_entity(entity_api, store, repo_id=repo_id, entity_id=f"entity1-{idx}", payload={"id": f"entity1-{idx}", "data": {"type": "feature", "value": feature_value, "version": "1.1.1"}, "location_id": "1"}, case_id=f"entity1-{idx}", name=f"create entity1 {idx}")
                    entity_ok = entity_record.status_code == 201
                    if not entity_ok:
                        overall_status = "failed"
                    entity_reason = None if entity_ok else failure_reason_or_body(entity_record.response_body, f"expected 201, got {entity_record.status_code}")
                    record_step(collector, case_results, prefix="version_type_check", case_id=f"entity1-{idx}", expected_status=201, actual_status=entity_record.status_code, passed=entity_ok, failure_reason=entity_reason)

                same_version_record = await search_query(search_api, store, payload=_build_search_payload(repo_id=repo_id, version="1.1.1"), case_id="search-same-version", name="search same version")
                same_version_ok = same_version_record.status_code == 200
                same_version_reason = None
                if same_version_ok:
                    try:
                        same_version_result_ids = _assert_same_version_results(same_version_record.response_body)
                    except Exception as exc:
                        same_version_ok = False
                        same_version_reason = str(exc)
                else:
                    same_version_reason = describe_search_failure(same_version_record.response_body, f"expected 200, got {same_version_record.status_code}")
                if not same_version_ok:
                    overall_status = "failed"
                    same_version_reason = same_version_reason or describe_search_failure(same_version_record.response_body, "same-version search validation failed")
                record_step(
                    collector,
                    case_results,
                    prefix="version_type_check",
                    case_id="search-same-version",
                    expected_status="200 + expected ids",
                    actual_status=same_version_record.status_code,
                    passed=same_version_ok,
                    failure_reason=same_version_reason,
                    extra={"returned_result_ids": list(same_version_result_ids), "expected_result_ids": list(EXPECTED_RESULT_IDS), "missing_expected_ids": _missing_expected_ids(same_version_result_ids)},
                )

                mismatch_record = await search_query(search_api, store, payload=_build_search_payload(repo_id=repo_id, version="1.1.2"), case_id="search-mismatch-version", name="search mismatch version")
                mismatch_ok = False
                mismatch_reason = None
                observed_error = None
                if mismatch_record.status_code in {400, 409}:
                    mismatch_behavior = "error_response"
                    observed_error = describe_search_failure(mismatch_record.response_body, f"expected version mismatch response, got {mismatch_record.status_code}")
                    mismatch_ok = True
                elif mismatch_record.status_code == 200:
                    mismatch_result_ids = extract_result_ids(extract_search_results(mismatch_record.response_body))
                    observed_error = None
                    if mismatch_result_ids == same_version_result_ids and mismatch_result_ids:
                        mismatch_behavior = "unexpected_success"
                        mismatch_reason = "expected mismatch search to fail, but backend returned the same ids"
                    else:
                        mismatch_behavior = "unexpected_results"
                        mismatch_reason = f"expected same ids as same-version search, got {mismatch_result_ids}"
                else:
                    mismatch_behavior = "unexpected_status"
                    mismatch_reason = describe_search_failure(mismatch_record.response_body, f"expected 200 or 400, got {mismatch_record.status_code}")

                if mismatch_record.status_code == 200 and not mismatch_result_ids:
                    mismatch_reason = mismatch_reason or "expected mismatch search results"
                if mismatch_record.status_code == 200:
                    overall_status = "failed"
                elif mismatch_record.status_code not in {200, 400, 409}:
                    overall_status = "failed"

                if not mismatch_ok:
                    overall_status = "failed"
                    mismatch_reason = mismatch_reason or describe_search_failure(mismatch_record.response_body, "mismatch-version search validation failed")

                record_step(
                    collector,
                    case_results,
                    prefix="version_type_check",
                    case_id="search-mismatch-version",
                    expected_status="200 or 400/409 depending on backend version rule",
                    actual_status=mismatch_record.status_code,
                    passed=mismatch_ok,
                    failure_reason=mismatch_reason,
                    extra={
                        "mismatch_behavior": mismatch_behavior,
                        "returned_result_ids": list(mismatch_result_ids),
                        "same_version_result_ids": list(same_version_result_ids),
                        "observed_error": observed_error,
                    },
                )

                if mismatch_ok:
                    print("Version type check validation completed successfully.")
                    print(f"Same version ids: {same_version_result_ids}")
                    print(f"Mismatch behavior: {mismatch_behavior}")
    except Exception as exc:
        overall_status = "failed"
        record_step(collector, case_results, prefix="version_type_check", case_id="scenario-error", expected_status="no exception", actual_status=None, passed=False, failure_reason=str(exc))
    finally:
        try:
            cleanup_after = await cleanup_repo(repo_api, store, repo_id=repo_id, name="cleanup version_type_check repo after run")
            record_step(collector, case_results, prefix="version_type_check", case_id="cleanup-after", expected_status="200/202/204/404", actual_status=cleanup_after.status_code, passed=True)
        except Exception as exc:
            overall_status = "failed"
            record_step(collector, case_results, prefix="version_type_check", case_id="cleanup-after-error", expected_status="cleanup ok", actual_status=None, passed=False, failure_reason=str(exc))

        summary = finalize_search_summary(
            collector,
            summary_path,
            overall_status=overall_status,
            extra={
                "repo_id": repo_id,
                "case_total": len(case_results),
                "case_results": case_results,
                "same_version_result_ids": list(same_version_result_ids),
                "mismatch_result_ids": list(mismatch_result_ids),
                "mismatch_behavior": mismatch_behavior,
            },
        )
    return summary


# 程序入口，用于串起当前模块的执行流程。
async def main() -> None:
    async with open_business_apis(repo=True, entity=True, search=True) as apis:
        summary = await run_scenario(repo_api=apis["repo_api"], entity_api=apis["entity_api"], search_api=apis["search_api"])
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if os.environ.get("API_TEST_IMPORT_ONLY") == "1":
        raise SystemExit(0)
    asyncio.run(main())
