"""用于校验 API_TEST MVP 矩阵下实体查询场景的真实接口测试模块。"""

from __future__ import annotations

from pathlib import Path

import pytest

from API_TEST.function_test.entity.post_checks import assert_entity_status
from API_TEST.function_test.support import load_function_cases


CASE_FILE = Path(__file__).resolve().parents[2] / "data" / "entity" / "function" / "get" / "cases.json"
CASES = load_function_cases(CASE_FILE)


# 测试当前用例的预期行为。
@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
async def test_entity_get(case, entity_resource_factory, entity_api, response_store_factory, summary_factory) -> None:
    collector = summary_factory("entity get", "entity", "get")
    store = response_store_factory()
    repo_id, entity_id = await entity_resource_factory("apitest-entity-get", "apitest-entity-get")

    if case["expected"]["status_code"] == 200:
        path = f"/repositories/{repo_id}/entities/{entity_id}"
    elif case["scenario_type"] == "非法":
        path = f"/repositories/{repo_id}/entities/not-exist"
    else:
        path = f"/repositories/{repo_id}/entities/"

    try:
        record = await entity_api.get(
            None,
            case_id=case["case_id"],
            module="entity",
            action="get",
            name=case["name"],
            method=case["method"],
            path=path,
        )
        store.save(record)

        assert record.status_code == case["expected"]["status_code"]
        if record.status_code == 200:
            await assert_entity_status(entity_api, repo_id, entity_id, expected_status=200)

        collector.record_success(case["case_id"])
    except AssertionError as exc:
        collector.record_failure(case["case_id"], str(exc))
        raise
    finally:
        collector.write_summary()
