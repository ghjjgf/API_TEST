"""search 业务场景共用的结果记录辅助模块。"""

from __future__ import annotations

from typing import Any

from API_TEST.business.repo._scenario_support import failure_reason_from_body
from API_TEST.business.support import finalize_business_summary


# 完成当前场景的结果汇总。
def finalize_search_summary(collector, summary_path, *, overall_status: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return finalize_business_summary(collector, summary_path, overall_status=overall_status, extra=extra)


# 提取当前场景需要的字段或结果。
def extract_result_ids(results: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("id")) for item in results if item.get("id") is not None]


# 实现当前模块的核心逻辑。
def describe_search_failure(response_body: Any, fallback: str) -> str:
    return failure_reason_from_body(response_body, fallback)


# 轮询当前场景的执行结果。

