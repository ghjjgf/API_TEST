"""用于校验 API_TEST MVP 矩阵下实体创建场景的真实接口测试模块。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import uuid

import pytest

from API_TEST.function_test.entity.post_checks import assert_entity_status
from API_TEST.function_test.support import load_function_cases


CASE_FILE = Path(__file__).resolve().parents[2] / "data" / "entity" / "function" / "create" / "cases.json"
CASES = load_function_cases(CASE_FILE)


# 生成当前场景使用的标识或资源。
def make_unique_entity_id(base_id: str) -> str:
    return f"{base_id}-{uuid.uuid4().hex[:8]}"


# 实现当前模块的核心逻辑。
def prepare_create_payload(case: dict[str, object]) -> tuple[dict[str, object], str | None]:
    payload = deepcopy(case["payload"])
    entity_id: str | None = None

    if isinstance(payload, dict) and isinstance(payload.get("id"), str) and payload.get("id"):
        entity_id = make_unique_entity_id(str(payload["id"]))
        payload["id"] = entity_id

    return payload, entity_id


# 测试当前用例的预期行为。
@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
async def test_entity_create(case, repo_resource_factory, entity_api, response_store_factory, summary_factory) -> None:
    collector = summary_factory("entity create", "entity", "create")
    store = response_store_factory()
    payload, entity_id = prepare_create_payload(case)
    repo_id = await repo_resource_factory("apitest-entity-create")
    if case["parameter"] == "repo_id" and case["scenario_type"] != "合法":
        path = case["path"]
    else:
        path = f"/repositories/{repo_id}/entities"
        if isinstance(payload, dict) and isinstance(payload.get("repo_id"), str):
            payload["repo_id"] = repo_id

    try:
        record = await entity_api.create(
            payload,
            case_id=case["case_id"],
            module="entity",
            action="create",
            name=case["name"],
            method=case["method"],
            path=path,
        )
        store.save(record)

        assert record.status_code == case["expected"]["status_code"]
        if entity_id is not None and record.status_code == 201:
            await assert_entity_status(entity_api, repo_id, entity_id, expected_status=200)

        collector.record_success(case["case_id"])
    except AssertionError as exc:
        collector.record_failure(case["case_id"], str(exc))
        raise
    finally:
        collector.write_summary()
