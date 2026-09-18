"""提供校验真实仓库状态流转的仓库后置检查辅助模块。"""

from __future__ import annotations

from API_TEST.core.models import HttpResponseRecord
from API_TEST.core.utils import poll_until_ready
from API_TEST.function_test.support import ensure_repo_deleted


# 实现当前模块的核心逻辑。
async def assert_repo_present_in_list(repo_api, repo_id: str, *, timeout_s: float = 30.0) -> HttpResponseRecord:
    # 实现当前模块的核心逻辑。
    async def fetch_record() -> HttpResponseRecord:
        return await repo_api.list(
            None,
            case_id=f"repo-list-{repo_id}",
            module="repo",
            action="list",
            name=f"wait repo {repo_id} in list",
            path="/repositories",
        )

    # 判断当前对象是否满足目标条件。
    def is_present(record: HttpResponseRecord) -> bool:
        if record.status_code != 200 or not isinstance(record.response_body, dict):
            return False

        repos = record.response_body.get("repos", [])
        for repo in repos:
            if isinstance(repo, dict) and repo.get("id") == repo_id:
                status = str(repo.get("status", "")).upper()
                return status in {"READY", "ACTIVE", "SUCCESS"}
        return False

    return await poll_until_ready(fetch_record, is_present, timeout_s=timeout_s, interval_s=1.0)


# 实现当前模块的核心逻辑。
async def assert_repo_absent(repo_api, repo_id: str, *, timeout_s: float = 30.0) -> None:
    await ensure_repo_deleted(repo_api, repo_id, timeout_s=timeout_s)

    # 实现当前模块的核心逻辑。
    async def fetch_record() -> HttpResponseRecord:
        return await repo_api.list(
            None,
            case_id=f"repo-list-absent-{repo_id}",
            module="repo",
            action="list",
            name=f"wait repo {repo_id} absent from list",
            path="/repositories",
        )

    # 判断当前对象是否满足目标条件。
    def is_absent(record: HttpResponseRecord) -> bool:
        if record.status_code != 200 or not isinstance(record.response_body, dict):
            return False

        repos = record.response_body.get("repos", [])
        return not any(isinstance(repo, dict) and repo.get("id") == repo_id for repo in repos)

    await poll_until_ready(fetch_record, is_absent, timeout_s=timeout_s, interval_s=1.0)
