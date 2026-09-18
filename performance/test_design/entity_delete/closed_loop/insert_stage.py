from __future__ import annotations

from dataclasses import dataclass, field
import asyncio
import time
from typing import Any, Awaitable, Callable
import sys
from pathlib import Path
# Bootstrap sys.path so running this submodule directly can import API_TEST
_resolved = Path(__file__).resolve()
PROJECT_ROOT = None
for ancestor in _resolved.parents:
    if ancestor.name == 'API_TEST':
        PROJECT_ROOT = ancestor
        break
if PROJECT_ROOT is None:
    PROJECT_ROOT = _resolved.parents[3]
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

from API_TEST.performance.test_design.entity_delete.closed_loop.config import build_entity_payload


@dataclass(frozen=True)
class InsertStageResult:
    success_count: int
    failure_count: int
    entity_ids: list[str]
    failed_entity_ids: list[str]
    elapsed_seconds: float
    failure_records: list[dict[str, Any]] = field(default_factory=list)


# 格式化当前场景的数据输出。
def format_insert_checkpoint(*, completed: int, success_count: int, failure_count: int, elapsed_seconds: float) -> str:
    return (
        f"completed={completed} "
        f"success={success_count} "
        f"failure={failure_count} "
        f"elapsed={elapsed_seconds:.2f}s"
    )


# 内部辅助函数，封装当前模块的局部逻辑。
async def _default_sender(
    *,
    base_url: str,
    repo_id: str,
    entity_id: str,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> tuple[int | None, Any, str | None]:
    raise RuntimeError("request_sender is required")


# 内部辅助函数，封装当前模块的局部逻辑。
def _normalize_for_json(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _normalize_for_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_for_json(item) for item in value]
    return str(value)


# 内部辅助函数，封装当前模块的局部逻辑。
def _coerce_sender_result(result: Any) -> tuple[int | None, Any, str | None]:
    if not isinstance(result, tuple):
        raise TypeError("request_sender must return a tuple")
    if len(result) == 2:
        status, body = result
        return status, body, None
    if len(result) == 3:
        status, body, error_kind = result
        return status, body, error_kind
    raise TypeError("request_sender must return (status, body) or (status, body, error_kind)")


# 实现当前模块的核心逻辑。
async def insert_entities_async(
    *,
    base_url: str,
    repo_id: str,
    entity_ids: list[str],
    entity_template: dict[str, Any],
    concurrency: int,
    timeout_seconds: int,
    request_sender: Callable[..., Awaitable[Any]] | None = None,
    progress_writer: Callable[[str], None] = print,
) -> InsertStageResult:
    sender = request_sender or _default_sender
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    for entity_id in entity_ids:
        queue.put_nowait(entity_id)
    for _ in range(max(concurrency, 1)):
        queue.put_nowait(None)

    success_ids: list[str] = []
    failed_ids: list[str] = []
    failure_records: list[dict[str, Any]] = []
    success_count = 0
    failure_count = 0
    completed = 0
    started = time.perf_counter()
    lock = asyncio.Lock()

    # 实现当前模块的核心逻辑。
    async def worker() -> None:
        nonlocal success_count, failure_count, completed
        while True:
            entity_id = await queue.get()
            if entity_id is None:
                return
            payload = build_entity_payload(entity_id, entity_template)
            status, response_body, error_kind = _coerce_sender_result(
                await sender(
                    base_url=base_url,
                    repo_id=repo_id,
                    entity_id=entity_id,
                    payload=payload,
                    timeout_seconds=timeout_seconds,
                )
            )
            async with lock:
                completed += 1
                if status is not None and 200 <= status < 300:
                    success_count += 1
                    success_ids.append(entity_id)
                else:
                    failure_count += 1
                    failed_ids.append(entity_id)
                    failure_records.append(
                        {
                            "entity_id": entity_id,
                            "status": status,
                            "error_kind": error_kind,
                            "response_body": _normalize_for_json(response_body),
                        }
                    )
                if completed % 10000 == 0:
                    checkpoint = format_insert_checkpoint(
                        completed=completed,
                        success_count=success_count,
                        failure_count=failure_count,
                        elapsed_seconds=time.perf_counter() - started,
                    )
                    progress_writer(checkpoint)

    await asyncio.gather(*(worker() for _ in range(max(concurrency, 1))))
    if completed % 10000 != 0:
        progress_writer(
            format_insert_checkpoint(
                completed=completed,
                success_count=success_count,
                failure_count=failure_count,
                elapsed_seconds=time.perf_counter() - started,
            )
        )
    return InsertStageResult(
        success_count=success_count,
        failure_count=failure_count,
        entity_ids=success_ids,
        failed_entity_ids=failed_ids,
        elapsed_seconds=time.perf_counter() - started,
        failure_records=failure_records,
    )
