"""用于校验 API_TEST MVP 矩阵下仓库创建场景的真实接口测试模块。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import uuid

import pytest

from API_TEST.function_test.repo.post_checks import assert_repo_absent, assert_repo_present_in_list
from API_TEST.function_test.support import load_function_cases


CASE_FILE = Path(__file__).resolve().parents[2] / "data" / "repo" / "function" / "create" / "cases.json"
CASES = load_function_cases(CASE_FILE)


# 生成当前场景使用的标识或资源。
def make_unique_repo_id(base_id: str) -> str:
    return f"{base_id}-{uuid.uuid4().hex[:8]}"


# 实现当前模块的核心逻辑。
def prepare_create_payload(case: dict[str, object]) -> tuple[dict[str, object], str | None]:
    payload = deepcopy(case["payload"])
    repo_id: str | None = None

    if isinstance(payload, dict) and isinstance(payload.get("id"), str) and payload.get("id"):
        repo_id = make_unique_repo_id(str(payload["id"]))
        payload["id"] = repo_id

    return payload, repo_id


# 测试当前用例的预期行为。
@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
async def test_repo_create(case, repo_api, response_store_factory, summary_factory) -> None:
    collector = summary_factory("repo create", "repo", "create")
    store = response_store_factory()
    payload, repo_id = prepare_create_payload(case)

    try:
        record = await repo_api.create(
            payload,
            case_id=case["case_id"],
            module="repo",
            action="create",
            name=case["name"],
            method=case["method"],
            path=case["path"],
        )
        store.save(record)

        expected_status = int(case["expected"]["status_code"])
        creation_verified = False
        if repo_id is not None and record.status_code in {201, 202}:
            await assert_repo_present_in_list(repo_api, repo_id)
            creation_verified = True

        if record.status_code != expected_status:
            raise AssertionError(
                f"状态码 期望 {expected_status} / 实际 {record.status_code}; "
                f"仓库创建成功性校验={'通过' if creation_verified else '未执行'}"
            )

        collector.record_success(case["case_id"])
    except AssertionError as exc:
        collector.record_failure(case["case_id"], str(exc))
        raise
    finally:
        collector.write_summary()
        if repo_id is not None:
            cleanup = await repo_api.delete(
                None,
                case_id=f"{case['case_id']}-cleanup",
                module="repo",
                action="delete",
                name=f"cleanup {repo_id}",
                path=f"/repositories/{repo_id}",
            )
            store.save(cleanup)
            assert cleanup.status_code in {200, 202, 204, 404}, cleanup.response_body
            await assert_repo_absent(repo_api, repo_id, timeout_s=60.0)
