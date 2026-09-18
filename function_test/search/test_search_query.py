"""用于校验 API_TEST MVP 矩阵下搜索查询场景的真实接口测试模块。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from API_TEST.function_test.support import cleanup_repo_resource, load_function_cases, wait_repo_ready


CASE_FILE = Path(__file__).resolve().parents[2] / "data" / "search" / "function" / "query" / "cases.json"
CASES = load_function_cases(CASE_FILE)


# 为每个搜索用例构造独立载荷副本，避免参数化执行之间相互污染。
def build_search_payload(case: dict[str, object]) -> dict[str, object]:
    return deepcopy(case["payload"])


# 从搜索载荷中提取需要提前创建的仓库标识，仅对内置测试仓库执行种子准备。
def collect_search_seed_repo_ids(payload: dict[str, object]) -> list[str]:
    repositories = payload.get("repositories")
    if not isinstance(repositories, list):
        return []

    repo_ids: list[str] = []
    for repo_id in repositories:
        if isinstance(repo_id, str) and repo_id.startswith("testrepo-search-") and repo_id not in repo_ids:
            repo_ids.append(repo_id)

    return repo_ids


# 预置当前场景所需的数据。
async def seed_search_repositories(repo_api, repo_ids: list[str]) -> list[str]:
    seeded: list[str] = []
    for repo_id in repo_ids:
        await cleanup_repo_resource(repo_api, repo_id, timeout_s=60.0)
        record = await repo_api.create(
            {
                "id": repo_id,
                "type": "face",
                "index_type": "int8",
                "level": "ram",
            },
            case_id=f"search-seed-{repo_id}",
            module="repo",
            action="create",
            name=f"seed search repo {repo_id}",
            path="/repositories",
        )
        assert record.status_code == 202, record.response_body
        await wait_repo_ready(repo_api, repo_id, timeout_s=60.0)
        seeded.append(repo_id)

    return seeded


# 测试当前用例的预期行为。
@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
async def test_search_query(case, repo_api, search_api, response_store_factory, summary_factory) -> None:
    collector = summary_factory("search query", "search", "query")
    store = response_store_factory()
    payload = build_search_payload(case)
    seeded_repo_ids = collect_search_seed_repo_ids(payload)

    try:
        if seeded_repo_ids:
            await seed_search_repositories(repo_api, seeded_repo_ids)

        record = await search_api.query(
            payload,
            case_id=case["case_id"],
            module="search",
            action="query",
            name=case["name"],
            method=case["method"],
            path=case["path"],
        )
        store.save(record)

        assert record.status_code == case["expected"]["status_code"]
        collector.record_success(case["case_id"])
    except AssertionError as exc:
        collector.record_failure(case["case_id"], str(exc))
        raise
    finally:
        collector.write_summary()
        for repo_id in reversed(seeded_repo_ids):
            await cleanup_repo_resource(repo_api, repo_id, timeout_s=60.0)
