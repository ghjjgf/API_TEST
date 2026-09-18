"""用于校验 API_TEST MVP 矩阵下仓库查询场景的真实接口测试模块。"""

from __future__ import annotations

from pathlib import Path

import pytest

from API_TEST.function_test.support import load_function_cases


CASE_FILE = Path(__file__).resolve().parents[2] / "data" / "repo" / "function" / "get" / "cases.json"
CASES = load_function_cases(CASE_FILE)


# 解析当前场景所需的路径或目标。
async def resolve_get_path(case: dict[str, object], repo_resource_factory) -> str:
    if case["expected"]["status_code"] == 200:
        repo_id = await repo_resource_factory("apitest-repo-get")
        return f"/repositories/{repo_id}"
    return case["path"]


# 测试当前用例的预期行为。
@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
async def test_repo_get(case, repo_api, repo_resource_factory, response_store_factory, summary_factory) -> None:
    collector = summary_factory("repo get", "repo", "get")
    store = response_store_factory()
    path = await resolve_get_path(case, repo_resource_factory)

    try:
        record = await repo_api.get(
            None,
            case_id=case["case_id"],
            module="repo",
            action="get",
            name=case["name"],
            method=case["method"],
            path=path,
        )
        store.save(record)

        assert record.status_code == case["expected"]["status_code"]
        collector.record_success(case["case_id"])
    except AssertionError as exc:
        collector.record_failure(case["case_id"], str(exc))
        raise
    finally:
        collector.write_summary()
