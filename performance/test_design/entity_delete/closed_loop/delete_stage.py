from __future__ import annotations

from dataclasses import dataclass
import asyncio
import time

import aiohttp


@dataclass(frozen=True)
class DeleteStageResult:
    concurrency: int
    total_requests: int
    success_count: int
    failure_count: int
    elapsed_seconds: float
    success_rate: float
    error_rate: float
    timeout_count: int
    connection_error_count: int
    qps: float
    latency_avg_ms: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    latency_p99_ms: float | None
    latency_max_ms: float | None


# 内部辅助函数，封装当前模块的局部逻辑。
def _delete_url(base_url: str, repo_id: str, entity_id: str) -> str:
    return f"{base_url.rstrip('/')}/repositories/{repo_id}/entities/{entity_id}"


# 删除当前场景所需的资源或请求负载。
async def delete_one_entity(
    session: aiohttp.ClientSession,
    *,
    base_url: str,
    repo_id: str,
    entity_id: str,
    timeout_seconds: int,
) -> tuple[int | None, float | None, str | None]:
    started = time.perf_counter()
    try:
        async with session.delete(
            _delete_url(base_url, repo_id, entity_id),
            timeout=aiohttp.ClientTimeout(total=timeout_seconds),
        ) as response:
            await response.text()
            return response.status, (time.perf_counter() - started) * 1000.0, None
    except asyncio.TimeoutError:
        return None, None, "timeout"
    except aiohttp.ClientError:
        return None, None, "connection_error"


# 执行当前场景的核心流程。
async def run_delete_stage(
    *,
    session: aiohttp.ClientSession,
    base_url: str,
    repo_id: str,
    entity_ids: list[str],
    concurrency: int,
    delete_timeout_seconds: int,
) -> DeleteStageResult:
    semaphore = asyncio.Semaphore(max(1, concurrency))
    latencies: list[float] = []
    success_count = 0
    failure_count = 0
    timeout_count = 0
    connection_error_count = 0
    started = time.perf_counter()

    # 实现当前模块的核心逻辑。
    async def worker(entity_id: str) -> None:
        nonlocal success_count, failure_count, timeout_count, connection_error_count
        async with semaphore:
            status, elapsed_ms, error_kind = await delete_one_entity(
                session,
                base_url=base_url,
                repo_id=repo_id,
                entity_id=entity_id,
                timeout_seconds=delete_timeout_seconds,
            )
            if elapsed_ms is not None:
                latencies.append(elapsed_ms)
            if status is not None and 200 <= status < 300:
                success_count += 1
            else:
                failure_count += 1
                if error_kind == "timeout":
                    timeout_count += 1
                elif error_kind == "connection_error":
                    connection_error_count += 1

    await asyncio.gather(*(worker(entity_id) for entity_id in entity_ids))
    elapsed_seconds = max(time.perf_counter() - started, 0.0)
    total_requests = len(entity_ids)
    qps = round(total_requests / elapsed_seconds, 3) if elapsed_seconds > 0 else 0.0
    success_rate = round((success_count / total_requests) * 100.0, 3) if total_requests else 0.0
    error_rate = round((failure_count / total_requests) * 100.0, 3) if total_requests else 0.0
    return DeleteStageResult(
        concurrency=concurrency,
        total_requests=total_requests,
        success_count=success_count,
        failure_count=failure_count,
        elapsed_seconds=elapsed_seconds,
        success_rate=success_rate,
        error_rate=error_rate,
        timeout_count=timeout_count,
        connection_error_count=connection_error_count,
        qps=qps,
        latency_avg_ms=round(sum(latencies) / len(latencies), 3) if latencies else None,
        latency_p50_ms=_percentile(latencies, 50),
        latency_p95_ms=_percentile(latencies, 95),
        latency_p99_ms=_percentile(latencies, 99),
        latency_max_ms=round(max(latencies), 3) if latencies else None,
    )


# 内部辅助函数，封装当前模块的局部逻辑。
def _percentile(values: list[float], percent: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = (len(ordered) - 1) * (percent / 100.0)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return round(ordered[lower], 3)
    weight = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * weight, 3)
