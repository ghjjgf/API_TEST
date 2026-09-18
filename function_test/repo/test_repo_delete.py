"""用于校验 API_TEST MVP 矩阵下仓库删除场景的真实接口测试模块。"""

from __future__ import annotations

from pathlib import Path

import pytest

from API_TEST.function_test.repo.post_checks import assert_repo_absent, assert_repo_present_in_list
from API_TEST.function_test.support import load_function_cases


CASE_FILE = Path(__file__).resolve().parents[2] / "data" / "repo" / "function" / "delete" / "cases.json"
CASES = load_function_cases(CASE_FILE)
VALID_DELETE_CASE_ID = "DR-VALID-001"
VALID_DELETE_REPO_ID = "testrepo"


# 解析当前场景所需的路径或目标。
async def prepare_delete_target(case: dict[str, object], repo_api, store) -> tuple[str, str | None, bool]:
    if case["case_id"] == VALID_DELETE_CASE_ID:
        setup = await repo_api.create(
            {
                "id": VALID_DELETE_REPO_ID,
                "type": "face",
                "index_type": "int8",
                "level": "ram",
            },
            case_id=f"{VALID_DELETE_CASE_ID}-setup",
            module="repo",
            action="create",
            name=f"setup {VALID_DELETE_REPO_ID}",
            path="/repositories",
        )
        store.save(setup)
        if setup.status_code not in {201, 202}:
            raise AssertionError(
                f"删除前置创建失败：期望 201/202 / 实际 {setup.status_code}; {setup.response_body}"
            )

        await assert_repo_present_in_list(repo_api, VALID_DELETE_REPO_ID)
        return f"/repositories/{VALID_DELETE_REPO_ID}", VALID_DELETE_REPO_ID, True

    return case["path"], None, False


# 测试当前用例的预期行为。
@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
async def test_repo_delete(case, repo_api, response_store_factory, summary_factory) -> None:
    collector = summary_factory("repo delete", "repo", "delete")
    store = response_store_factory()
    repo_created = False

    try:
        path, repo_id, repo_created = await prepare_delete_target(case, repo_api, store)
        record = await repo_api.delete(
            None,
            case_id=case["case_id"],
            module="repo",
            action="delete",
            name=case["name"],
            method=case["method"],
            path=path,
        )
        store.save(record)

        assert record.status_code == case["expected"]["status_code"]
        if repo_id is not None:
            await assert_repo_absent(repo_api, repo_id)

        collector.record_success(case["case_id"])
    except AssertionError as exc:
        collector.record_failure(case["case_id"], str(exc))
        raise
    finally:
        collector.write_summary()
        if repo_created and repo_id is not None:
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
