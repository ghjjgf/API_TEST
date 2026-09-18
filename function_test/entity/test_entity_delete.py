"""用于校验 API_TEST MVP 矩阵下实体删除场景的真实接口测试模块。"""

from __future__ import annotations

from pathlib import Path

import pytest

from API_TEST.function_test.entity.post_checks import assert_entity_status
from API_TEST.function_test.support import load_function_cases


CASE_FILE = Path(__file__).resolve().parents[2] / "data" / "entity" / "function" / "delete" / "cases.json"
CASES = load_function_cases(CASE_FILE)


# 测试当前用例的预期行为。
@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
async def test_entity_delete(case, entity_resource_factory, entity_api, response_store_factory, summary_factory) -> None:
    collector = summary_factory("entity delete", "entity", "delete")
    store = response_store_factory()
    repo_id, entity_id = await entity_resource_factory("apitest-entity-delete", "apitest-entity-delete")

    if case["expected"]["status_code"] == 200:
        path = f"/repositories/{repo_id}/entities/{entity_id}"
        target_entity_id = entity_id
    elif case["scenario_type"] == "非法":
        path = f"/repositories/{repo_id}/entities/not-exist"
        target_entity_id = None
    else:
        path = f"/repositories/{repo_id}/entities/"
        target_entity_id = None

    try:
        record = await entity_api.delete(
            None,
            case_id=case["case_id"],
            module="entity",
            action="delete",
            name=case["name"],
            method=case["method"],
            path=path,
        )
        store.save(record)

        assert record.status_code == case["expected"]["status_code"]
        if target_entity_id is not None:
            await assert_entity_status(entity_api, repo_id, target_entity_id, expected_status=404)

        collector.record_success(case["case_id"])
    except AssertionError as exc:
        collector.record_failure(case["case_id"], str(exc))
        raise
    finally:
        collector.write_summary()
