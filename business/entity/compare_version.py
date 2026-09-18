"""用于比较两个实体版本值的业务场景脚本（legacy 兼容版）。"""
# 流程：
# 1. 直接构造 m_objects/entity1 与 n_objects/entity2 的 compare payload，使用同一份合法特征值。
# 2. 场景一：两个实体版本均为 v1，调用 compare 接口；预期 HTTP 200，且响应 results 非空。
# 3. 场景二：两个实体版本分别为 v1/v2，再次调用 compare 接口；预期 HTTP 400 且响应包含 error。
# 4. 如果版本不一致时接口仍返回 200，该步骤判定失败。
# compare：
# payload 需要设置 type 使用 face，m_repo_id 设置为 m_objects，m_objects 里面的 id 设置为 entity1，
# data 里面设置 value 特征和 type=feature；n_repo_id 设置为 n_objects，n_objects 里面的 id 设置为 entity2，
# data 里面设置 value 特征和 type=feature。
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

from API_TEST.business.support import build_business_runtime, finalize_business_summary, load_reference_feature, open_business_apis


# 内部辅助函数，封装当前模块的局部逻辑。
def _build_compare_payload(feature_value: str, m_version: str, n_version: str) -> dict[str, object]:
    return {
        "type": "face",
        "m_repo_id": "m_objects",
        "m_objects": [
            {
                "id": "entity1",
                "data": {"type": "feature", "value": feature_value, "version": m_version},
            }
        ],
        "n_repo_id": "n_objects",
        "n_objects": [
            {
                "id": "entity2",
                "data": {"type": "feature", "value": feature_value, "version": n_version},
            }
        ],
    }


# 内部辅助函数，封装当前模块的局部逻辑。
def _expected_status_code(m_version: str, n_version: str) -> int:
    return 200 if m_version == n_version else 400


# 内部辅助函数，封装当前模块的局部逻辑。
def _actual_outcome(status_code: int | None, expected_status: int) -> str:
    if status_code is None:
        return "failed"
    return "passed" if status_code == expected_status else "failed"


# 执行当前场景的核心流程。
async def run_scenario(*, repo_api, output_root: Path | None = None) -> dict[str, object]:
    collector, store, summary_path, _ = build_business_runtime(Path(__file__), "entity", "compare_version", output_root)
    feature_value = load_reference_feature()
    cases = [
        {"case_id": "compare-same-version", "m_version": "v1", "n_version": "v1"},
        {"case_id": "compare-different-version", "m_version": "v1", "n_version": "v2"},
    ]
    overall_status = "passed"
    case_results: list[dict[str, object]] = []

    for case in cases:
        m_version = str(case["m_version"])
        n_version = str(case["n_version"])
        expected_status = _expected_status_code(m_version, n_version)
        case_id = str(case["case_id"])

        try:
            record = await repo_api.compare(
                _build_compare_payload(feature_value, m_version, n_version),
                case_id=case_id,
                module="repo",
                action="compare",
                name=case_id,
                path="/repositories/compare",
            )
            store.save(record)

            actual_status = record.status_code
            actual_outcome = _actual_outcome(actual_status, expected_status)
            failure_reason = None
            if actual_status != expected_status:
                overall_status = "failed"
                detail = f"expected {expected_status}, got {actual_status}"
                collector.record_failure(case_id, detail)
                failure_reason = detail
            elif expected_status == 200:
                if not isinstance(record.response_body, dict) or not record.response_body.get("results"):
                    overall_status = "failed"
                    failure_reason = "missing compare results"
                    collector.record_failure(case_id, failure_reason)
                else:
                    collector.record_success(case_id)
            else:
                if not isinstance(record.response_body, dict) or not record.response_body.get("error"):
                    overall_status = "failed"
                    failure_reason = "missing error payload for mismatch response"
                    collector.record_failure(case_id, failure_reason)
                else:
                    collector.record_success(case_id)

            if failure_reason is None and actual_outcome == "failed" and isinstance(record.response_body, dict):
                failure_reason = str(record.response_body.get("error") or record.response_body)

            print(
                f"[compare_version_] {case_id}: expected={expected_status}, actual={actual_status}, "
                f"actual_outcome={actual_outcome}{f', reason={failure_reason}' if failure_reason else ''}"
            )

            case_results.append(
                {
                    "case_id": case_id,
                    "expected_status": expected_status,
                    "actual_status": actual_status,
                    "actual_outcome": actual_outcome,
                    "failure_reason": failure_reason,
                    "passed": actual_status == expected_status,
                }
            )
        except Exception as exc:
            overall_status = "failed"
            collector.record_failure(case_id, str(exc))
            case_results.append(
                {
                    "case_id": case_id,
                    "expected_status": expected_status,
                    "actual_status": None,
                    "actual_outcome": "failed",
                    "failure_reason": str(exc),
                    "passed": False,
                }
            )

    summary = finalize_business_summary(collector, summary_path, overall_status=overall_status, extra={"case_total": len(cases), "case_results": case_results})

    return summary


# 程序入口，用于串起当前模块的执行流程。
async def main() -> None:
    async with open_business_apis(repo=True) as apis:
        summary = await run_scenario(repo_api=apis["repo_api"])
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if os.environ.get("API_TEST_IMPORT_ONLY") == "1":
        raise SystemExit(0)
    asyncio.run(main())
