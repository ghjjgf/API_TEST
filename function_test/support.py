"""提供 API_TEST 接口测试路径处理、用例加载与轮询能力的通用辅助模块。"""

from __future__ import annotations

from copy import deepcopy
import uuid
from pathlib import Path
from typing import Any

from API_TEST.core.models import HttpResponseRecord
from API_TEST.core.response_store import ResponseStore
from API_TEST.core.utils import load_case_entries, poll_until_ready
from API_TEST.function_test.entity.post_checks import assert_entity_status


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_FEATURE_TOKEN = "__REFERENCE_FEATURE__"
REFERENCE_FEATURE_PATH = PROJECT_ROOT / "data" / "common" / "reference_feature.b64"
SOURCE_LEGACY_CASES_NAME = "source_legacy_cases.json"


# 加载实体与搜索真实测试共用的参考特征文本。
def load_reference_feature() -> str:
    return REFERENCE_FEATURE_PATH.read_text(encoding="utf-8").strip()


# 递归替换用例载荷中的占位符，使其变为可直接运行的测试资源。
def expand_case_tokens(value: Any) -> Any:
    if isinstance(value, str):
        if value == REFERENCE_FEATURE_TOKEN:
            return load_reference_feature()
        return value
    if isinstance(value, list):
        return [expand_case_tokens(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_case_tokens(item) for key, item in value.items()}
    return value


# 解析接口测试用例文件的真实读取路径，优先使用正式 cases.json，缺失时回退到 legacy 源文件。
def resolve_function_case_file(case_file: Path) -> Path:
    candidate = Path(case_file)
    if candidate.is_file():
        return candidate

    legacy_file = candidate.with_name(SOURCE_LEGACY_CASES_NAME)
    if legacy_file.is_file():
        return legacy_file

    raise FileNotFoundError(f"未找到正式用例文件或 legacy 源文件: {candidate}")


# 从 JSON 文件中加载接口测试用例，并去除汇总行。
def load_function_cases(case_file: Path) -> list[dict[str, Any]]:
    resolved_file = resolve_function_case_file(case_file)
    return [expand_case_tokens(deepcopy(case)) for case in load_case_entries(resolved_file)]


# 解析测试模块对应的结构化汇总文件路径。
def resolve_summary_path(test_file: Path) -> Path:
    test_path = Path(test_file)
    return test_path.parent / "results" / f"{test_path.stem}_summary.json"


# 构造当前场景所需的数据。
def build_response_store(root: Path) -> ResponseStore:
    return ResponseStore(root)


# 创建当前场景所需的资源或请求负载。
async def create_tracked_repo_resource(repo_api, prefix: str, created_repo_ids: list[str], *, timeout_s: float = 30.0) -> str:
    repo_id = f"{prefix}-{uuid.uuid4().hex[:8]}"
    record = await repo_api.create(
        {
            "id": repo_id,
            "type": "face",
            "index_type": "int8",
            "level": "ram",
        },
        case_id=f"seed-create-{repo_id}",
        module="repo",
        action="create",
        name=f"seed create {repo_id}",
    )
    if record.status_code != 202:
        raise RuntimeError(f"failed to create seed repo {repo_id}: {record.status_code} {record.response_body}")

    created_repo_ids.append(repo_id)
    await wait_repo_ready(repo_api, repo_id, timeout_s=timeout_s)
    return repo_id


# 创建当前场景所需的资源或请求负载。
async def create_tracked_entity_resource(entity_api, repo_id: str, entity_prefix: str, created_entities: list[tuple[str, str]], *, timeout_s: float = 30.0) -> tuple[str, str]:
    entity_id = f"{entity_prefix}-{uuid.uuid4().hex[:8]}"
    record = await entity_api.create(
        {
            "id": entity_id,
            "data": {
                "value": load_reference_feature(),
                "type": "feature",
            },
            "location_id": "loc-001",
        },
        case_id=f"seed-entity-create-{entity_id}",
        module="entity",
        action="create",
        name=f"seed entity create {entity_id}",
        path=f"/repositories/{repo_id}/entities",
    )
    if record.status_code != 201:
        raise RuntimeError(f"failed to create seed entity {entity_id}: {record.status_code} {record.response_body}")

    created_entities.append((repo_id, entity_id))
    await assert_entity_status(entity_api, repo_id, entity_id, expected_status=200, timeout_s=timeout_s)
    return repo_id, entity_id


# 确保当前场景依赖或状态满足要求。
async def ensure_repo_gone_from_list(repo_api, repo_id: str, *, timeout_s: float = 30.0) -> None:
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


# 清理当前场景产生的临时资源。
async def cleanup_repo_resource(repo_api, repo_id: str, *, timeout_s: float = 30.0) -> HttpResponseRecord:
    cleanup = await repo_api.delete(
        None,
        case_id=f"seed-delete-{repo_id}",
        module="repo",
        action="delete",
        name=f"seed delete {repo_id}",
        path=f"/repositories/{repo_id}",
    )
    if cleanup.status_code not in {200, 202, 204, 404}:
        raise RuntimeError(f"failed to cleanup repo {repo_id}: {cleanup.status_code} {cleanup.response_body}")

    await ensure_repo_deleted(repo_api, repo_id, timeout_s=timeout_s)
    await ensure_repo_gone_from_list(repo_api, repo_id, timeout_s=timeout_s)
    return cleanup


# 清理当前场景产生的临时资源。
async def cleanup_entity_resource(entity_api, repo_id: str, entity_id: str, *, timeout_s: float = 30.0) -> HttpResponseRecord:
    cleanup = await entity_api.delete(
        None,
        case_id=f"seed-entity-delete-{entity_id}",
        module="entity",
        action="delete",
        name=f"seed entity delete {entity_id}",
        path=f"/repositories/{repo_id}/entities/{entity_id}",
    )
    if cleanup.status_code not in {200, 202, 204, 404}:
        raise RuntimeError(f"failed to cleanup entity {entity_id}: {cleanup.status_code} {cleanup.response_body}")

    await assert_entity_status(entity_api, repo_id, entity_id, expected_status=404, timeout_s=timeout_s)
    return cleanup


# 等待当前场景所需的资源进入目标状态。
async def wait_repo_ready(repo_api, repo_id: str, *, timeout_s: float = 30.0) -> HttpResponseRecord:
    # 实现当前模块的核心逻辑。
    async def fetch_record() -> HttpResponseRecord:
        return await repo_api.get(
            None,
            case_id=f"repo-ready-{repo_id}",
            module="repo",
            action="get",
            name=f"wait repo {repo_id} ready",
            path=f"/repositories/{repo_id}",
        )

    # 判断当前对象是否满足目标条件。
    def is_ready(record: HttpResponseRecord) -> bool:
        if record.status_code != 200:
            return False
        if not isinstance(record.response_body, dict):
            return True
        status = str(record.response_body.get("status", "")).upper()
        state = str(record.response_body.get("state", "")).upper()
        return status in {"READY", "ACTIVE", "SUCCESS"} or state in {"READY", "ACTIVE", "SUCCESS"} or not (status or state)

    return await poll_until_ready(fetch_record, is_ready, timeout_s=timeout_s)


# 确保当前场景依赖或状态满足要求。
async def ensure_repo_deleted(repo_api, repo_id: str, *, timeout_s: float = 30.0) -> None:
    # 实现当前模块的核心逻辑。
    async def fetch_record() -> HttpResponseRecord:
        return await repo_api.get(
            None,
            case_id=f"repo-delete-{repo_id}",
            module="repo",
            action="get",
            name=f"wait repo {repo_id} deleted",
            path=f"/repositories/{repo_id}",
        )

    # 判断当前对象是否满足目标条件。
    def is_deleted(record: HttpResponseRecord) -> bool:
        return record.status_code in {400, 404}

    await poll_until_ready(fetch_record, is_deleted, timeout_s=timeout_s)
