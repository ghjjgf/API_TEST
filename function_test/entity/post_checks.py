"""提供校验真实实体状态流转的实体后置检查辅助模块。"""

from __future__ import annotations

from API_TEST.core.models import HttpResponseRecord
from API_TEST.core.utils import poll_until_ready


# 实现当前模块的核心逻辑。
async def assert_entity_status(entity_api, repo_id: str, entity_id: str, *, expected_status: int, timeout_s: float = 30.0) -> HttpResponseRecord:
    # 实现当前模块的核心逻辑。
    async def fetch_record() -> HttpResponseRecord:
        return await entity_api.get(
            None,
            case_id=f"entity-status-{repo_id}-{entity_id}",
            module="entity",
            action="get",
            name=f"wait entity {entity_id} status {expected_status}",
            path=f"/repositories/{repo_id}/entities/{entity_id}",
        )

    # 判断当前对象是否包含目标特征。
    def has_expected_status(record: HttpResponseRecord) -> bool:
        return record.status_code == expected_status

    return await poll_until_ready(fetch_record, has_expected_status, timeout_s=timeout_s, interval_s=1.0)
