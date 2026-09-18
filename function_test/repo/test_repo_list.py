"""用于校验 API_TEST MVP 矩阵下仓库列表场景的真实接口测试模块。"""

from __future__ import annotations

from pathlib import Path

import pytest

from API_TEST.function_test.support import load_function_cases


CASE_FILE = Path(__file__).resolve().parents[2] / "data" / "repo" / "function" / "list" / "cases.json"
CASES = load_function_cases(CASE_FILE)


# 实现当前模块的核心逻辑。
async def maybe_create_seed_repo(case: dict[str, object], repo_resource_factory) -> str | None:
    if case["expected"]["status_code"] == 200:
        return await repo_resource_factory("apitest-repo-list")
    return None


# 测试当前用例的预期行为。
@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
async def test_repo_list(case, repo_api, repo_resource_factory, response_store_factory, summary_factory) -> None:
    collector = summary_factory("repo list", "repo", "list")
    store = response_store_factory()
    seed_repo_id = await maybe_create_seed_repo(case, repo_resource_factory)

    try:
        record = await repo_api.list(
            None,
            case_id=case["case_id"],
            module="repo",
            action="list",
            name=case["name"],
            method=case["method"],
            path=case["path"],
        )
        store.save(record)

        assert record.status_code == case["expected"]["status_code"]
        if seed_repo_id is not None:
            repos = record.response_body.get("repos", []) if isinstance(record.response_body, dict) else []
            assert any(isinstance(repo, dict) and repo.get("id") == seed_repo_id for repo in repos)

        collector.record_success(case["case_id"])
    except AssertionError as exc:
        collector.record_failure(case["case_id"], str(exc))
        raise
    finally:
        collector.write_summary()
