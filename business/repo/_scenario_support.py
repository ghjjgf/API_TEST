"""repo 业务场景共用的结果记录辅助模块。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from API_TEST.business.support import finalize_business_summary
from API_TEST.core.models import HttpResponseRecord
from API_TEST.core.utils import poll_until_ready



# 记录当前场景的案例结果。
def record_case_result(
    case_results: list[dict[str, object]],
    *,
    prefix: str,
    case_id: str,
    expected_status: int | str,
    actual_status: int | None,
    passed: bool,
    failure_reason: str | None = None,
    extra: dict[str, object] | None = None,
) -> bool:
    """记录单条业务结果，并同步打印到终端日志。"""

    if failure_reason is None and not passed:
        failure_reason = f"expected {expected_status}, got {actual_status}"

    print(
        f"[{prefix}] {case_id}: expected={expected_status}, actual={actual_status}"
        f"{f', reason={failure_reason}' if failure_reason else ''}"
    )
    case_result = {
        "case_id": case_id,
        "expected_status": expected_status,
        "actual_status": actual_status,
        "failure_reason": failure_reason,
        "passed": passed,
    }
    if extra:
        case_result.update(extra)
    case_results.append(case_result)
    return passed


# 实现当前模块的核心逻辑。
def failure_reason_from_body(response_body: Any, fallback: str) -> str:
    """从响应体中提取更可读的失败原因。"""

    if isinstance(response_body, dict):
        error = response_body.get("error") or response_body.get("message")
        if isinstance(error, str) and error:
            return error
    if response_body is None:
        return fallback
    return str(response_body)


# 完成当前场景的结果汇总。
def finalize_repo_summary(collector, summary_path, *, overall_status: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """repo 场景的汇总封装，统一补上总览字段。"""

    return finalize_business_summary(collector, summary_path, overall_status=overall_status, extra=extra)


# 轮询当前场景的执行结果。
async def poll_and_save(
    store,
    getter: Callable[[], Awaitable[HttpResponseRecord]],
    predicate: Callable[[HttpResponseRecord], bool],
    *,
    timeout_s: float = 30.0,
    interval_s: float = 0.5,
) -> HttpResponseRecord:
    """轮询时将每次响应都写入归档文件。"""

    # 实现当前模块的核心逻辑。
    async def tracked_getter() -> HttpResponseRecord:
        record = await getter()
        store.save(record)
        return record

    return await poll_until_ready(tracked_getter, predicate, timeout_s=timeout_s, interval_s=interval_s)
