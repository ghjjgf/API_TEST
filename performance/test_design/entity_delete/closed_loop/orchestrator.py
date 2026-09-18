from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable
import sys
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

from API_TEST.performance.test_design.entity_delete.closed_loop.config import BenchmarkConfig, build_default_config, load_entity_template, load_repo_template, make_entity_id


# 打印当前场景的说明或统计结果。
def print_step(label: str, detail: str) -> None:
    print(f"[STEP] {label:<18} {detail}", flush=True)


# 内部辅助函数，封装当前模块的局部逻辑。
def _slice_entity_ids(entity_ids: list[str], stage_request_count: int, concurrency_count: int) -> list[list[str]]:
    batches: list[list[str]] = []
    for index in range(concurrency_count):
        start = index * stage_request_count
        end = start + stage_request_count
        batches.append(entity_ids[start:end])
    return batches


# 内部辅助函数，封装当前模块的局部逻辑。
def _analyze_performance_inflection(stage_results: list[Any]) -> dict[str, Any]:
    if not stage_results:
        return {"narrative": "no delete-stage data"}

    qps_values = [float(getattr(item, "qps", 0.0) or 0.0) for item in stage_results]
    p95_values = [float(getattr(item, "latency_p95_ms", 0.0) or 0.0) for item in stage_results]
    narrative_parts: list[str] = []

    if len(qps_values) >= 2 and qps_values[-1] <= max(qps_values[:-1]):
        narrative_parts.append("QPS 已出现平台或回落")
    if len(p95_values) >= 2 and p95_values[-1] >= max(p95_values[:-1]):
        narrative_parts.append("P95 延迟在高并发段抬升")
    if not narrative_parts:
        narrative_parts.append("当前结果未出现明显拐点")

    return {"narrative": "；".join(narrative_parts)}


# 内部辅助函数，封装当前模块的局部逻辑。
def _build_bundle(
    *,
    config: BenchmarkConfig,
    stage_results: list[Any],
    insert_failure_records: list[dict[str, Any]],
    target_entity_count: int,
    inserted_entity_count: int,
    remaining_failure_count: int,
    insert_attempts_used: int,
    benchmark_status: str,
    insert_abort_reason: str | None,
    repo_id: str | None = None,
) -> dict[str, Any]:
    bundle: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": config.base_url,
        "endpoint": "/repositories/{repo_id}/entities/{entity_id}",
        "stage_metrics": [asdict(item) if hasattr(item, "__dataclass_fields__") else item for item in stage_results],
        "failure_summary": {"total_failure_count": sum(int(getattr(item, "failure_count", 0) or 0) for item in stage_results)},
        "inflection_analysis": _analyze_performance_inflection(stage_results),
        "failure_samples": [],
        "insert_failure_records": insert_failure_records,
        "benchmark_status": benchmark_status,
        "insert_summary": {
            "target_entity_count": target_entity_count,
            "inserted_entity_count": inserted_entity_count,
            "remaining_failure_count": remaining_failure_count,
            "attempts_used": insert_attempts_used,
            "max_attempts": config.max_insert_attempts,
            "abort_reason": insert_abort_reason,
        },
    }
    if repo_id is not None:
        bundle["repo_id"] = repo_id
    return bundle


def _build_combined_bundle(config: BenchmarkConfig, repo_results: list[dict[str, Any]]) -> dict[str, Any]:
    repo_ids = [item.get("repo_id") for item in repo_results if item.get("repo_id")]
    stage_metrics: list[dict[str, Any]] = []
    insert_failure_records: list[dict[str, Any]] = []
    total_target = 0
    total_inserted = 0
    total_remaining_failure = 0
    attempts_used = 0
    abort_reasons: list[str] = []
    aborted = False

    for item in repo_results:
        bundle = item.get("bundle", {}) if isinstance(item.get("bundle"), dict) else {}
        stage_metrics.extend(bundle.get("stage_metrics", []))
        insert_failure_records.extend(bundle.get("insert_failure_records", []))
        insert_summary = bundle.get("insert_summary", {})
        total_target += int(insert_summary.get("target_entity_count", 0) or 0)
        total_inserted += int(insert_summary.get("inserted_entity_count", 0) or 0)
        total_remaining_failure += int(insert_summary.get("remaining_failure_count", 0) or 0)
        attempts_used += int(insert_summary.get("attempts_used", 0) or 0)
        if item.get("aborted"):
            aborted = True
            if item.get("abort_reason"):
                abort_reasons.append(item["abort_reason"])

    for metric in stage_metrics:
        if isinstance(metric, dict):
            metric.setdefault("repo_id", "multi")
            metric.setdefault("repo_ids", repo_ids)

    combined_bundle = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": config.base_url,
        "endpoint": "/repositories/{repo_id}/entities/{entity_id}",
        "repo_id": ",".join(repo_ids) if repo_ids else "multi",
        "repo_ids": repo_ids,
        "stage_metrics": stage_metrics,
        "failure_summary": {"total_failure_count": sum(int(item.get("failure_count", 0) or 0) for item in stage_metrics)},
        "inflection_analysis": _analyze_performance_inflection([item for item in stage_metrics if isinstance(item, dict)]),
        "failure_samples": [],
        "insert_failure_records": insert_failure_records,
        "benchmark_status": "aborted_before_delete" if aborted else "completed",
        "insert_summary": {
            "target_entity_count": total_target,
            "inserted_entity_count": total_inserted,
            "remaining_failure_count": total_remaining_failure,
            "attempts_used": attempts_used,
            "max_attempts": config.max_insert_attempts,
            "abort_reason": "; ".join(abort_reasons) if abort_reasons else None,
        },
        "multi_repo_summary": {
            "repo_count": len(repo_ids),
            "repo_ids": repo_ids,
            "results": repo_results,
        },
    }
    return combined_bundle


# 执行当前场景的核心流程。
async def run_closed_loop_benchmark(
    config: BenchmarkConfig | None = None,
    *,
    create_repo: Callable[..., Awaitable[str]],
    insert_stage: Callable[..., Awaitable[Any]],
    delete_stage: Callable[..., Awaitable[list[Any]]],
    write_report: Callable[..., Path],
    delete_repo: Callable[..., Awaitable[None]],
) -> dict[str, Any]:
    config = config or build_default_config()
    repo_template = load_repo_template(None)
    entity_template = load_entity_template(None)

    async def _run_for_repo(repo_id: str, *, write_report_file: bool = True) -> dict[str, Any]:
        """Run the benchmark flow for a single, existing repo_id (no create/delete here)."""
        print_step("use-repo", f"using repo_id={repo_id}")
        target_entity_count = config.stage_request_count * len(config.delete_concurrency_values)
        remaining_entity_ids = [make_entity_id(config.entity_prefix, i) for i in range(target_entity_count)]
        successful_entity_ids: list[str] = []
        insert_failure_records: list[dict[str, Any]] = []
        attempt = 0
        insert_abort_reason: str | None = None
        stage_results: list[Any] = []

        while len(successful_entity_ids) < target_entity_count:
            attempt += 1
            print_step(
                "insert-stage",
                f"attempt={attempt} target={target_entity_count} have={len(successful_entity_ids)} remaining={len(remaining_entity_ids)} concurrency={config.insert_concurrency}",
            )
            insert_result = await insert_stage(
                config=config,
                repo_id=repo_id,
                entity_template=entity_template,
                entity_ids=remaining_entity_ids,
            )
            insert_success = int(getattr(insert_result, "success_count", 0) or 0)
            insert_failure = int(getattr(insert_result, "failure_count", 0) or 0)
            insert_elapsed = float(getattr(insert_result, "elapsed_seconds", 0.0) or 0.0)
            successful_entity_ids.extend(list(getattr(insert_result, "entity_ids", [])))
            failed_entity_ids = list(getattr(insert_result, "failed_entity_ids", []))
            raw_failure_records = list(getattr(insert_result, "failure_records", []))
            if raw_failure_records:
                insert_failure_records.extend(
                    [{**record, "attempt": attempt, "repo_id": repo_id} for record in raw_failure_records]
                )
            elif failed_entity_ids:
                insert_failure_records.extend(
                    [
                        {
                            "attempt": attempt,
                            "repo_id": repo_id,
                            "entity_id": entity_id,
                            "status": None,
                            "error_kind": "unknown",
                            "response_body": None,
                        }
                        for entity_id in failed_entity_ids
                    ]
                )
            print_step(
                "insert-stage",
                f"attempt={attempt} success={insert_success} failure={insert_failure} elapsed={insert_elapsed:.2f}s total_success={len(successful_entity_ids)}",
            )
            if len(successful_entity_ids) >= target_entity_count:
                successful_entity_ids = successful_entity_ids[:target_entity_count]
                break
            if not failed_entity_ids:
                insert_abort_reason = (
                    "insert stage did not return failed entity ids for retry; "
                    f"have={len(successful_entity_ids)} target={target_entity_count}"
                )
                print_step("insert-stage", f"abort reason={insert_abort_reason}")
                break
            if attempt >= config.max_insert_attempts:
                insert_abort_reason = (
                    f"insert stage exhausted max attempts={config.max_insert_attempts}; "
                    f"have={len(successful_entity_ids)} target={target_entity_count} remaining={len(failed_entity_ids)}"
                )
                print_step("insert-stage", f"abort reason={insert_abort_reason}")
                remaining_entity_ids = failed_entity_ids
                break
            remaining_entity_ids = failed_entity_ids

        if insert_abort_reason is None:
            delete_batches = _slice_entity_ids(successful_entity_ids, config.stage_request_count, len(config.delete_concurrency_values))
            for concurrency, entity_batch in zip(sorted(config.delete_concurrency_values, reverse=True), delete_batches):
                print_step("delete-stage", f"starting concurrency={concurrency} batch_size={len(entity_batch)}")
                stage_results.append(
                    await delete_stage(
                        config=config,
                        repo_id=repo_id,
                        entity_ids=entity_batch,
                        concurrency=concurrency,
                    )
                )
                last = stage_results[-1]
                print_step("delete-stage", f"finished concurrency={concurrency} total={last.total_requests} success={last.success_count} failure={last.failure_count} elapsed={last.elapsed_seconds:.2f}s")

        bundle = _build_bundle(
            config=config,
            stage_results=stage_results,
            insert_failure_records=insert_failure_records,
            target_entity_count=target_entity_count,
            inserted_entity_count=len(successful_entity_ids),
            remaining_failure_count=max(target_entity_count - len(successful_entity_ids), 0),
            insert_attempts_used=attempt,
            benchmark_status="aborted_before_delete" if insert_abort_reason else "completed",
            insert_abort_reason=insert_abort_reason,
            repo_id=repo_id,
        )
        report_path = None
        if write_report_file:
            print_step("write-report", f"writing report to {config.report_output_dir}")
            report_path = write_report(config.report_output_dir, bundle)
            print_step("write-report", f"report written {report_path}")
        return {
            "repo_id": repo_id,
            "report_path": report_path,
            "bundle": bundle,
            "aborted": insert_abort_reason is not None,
            "abort_reason": insert_abort_reason,
        }

    # 如果在配置中提供了多个 repo id，则按顺序对每个 repo 执行（不创建/删除）。
    if config.existing_repo_ids is not None:
        results: list[dict[str, Any]] = []
        for repo_id in config.existing_repo_ids:
            results.append(await _run_for_repo(repo_id, write_report_file=False))
        combined_bundle = _build_combined_bundle(config, results)
        print_step("write-report", f"writing combined report to {config.report_output_dir}")
        report_path = write_report(config.report_output_dir, combined_bundle)
        print_step("write-report", f"combined report written {report_path}")
        combined_result = {
            "repo_id": ",".join(item.get("repo_id") for item in results if item.get("repo_id")),
            "repo_ids": [item.get("repo_id") for item in results if item.get("repo_id")],
            "report_path": report_path,
            "bundle": combined_bundle,
            "results": results,
            "aborted": any(item.get("aborted") for item in results),
            "abort_reason": "; ".join(item.get("abort_reason") for item in results if item.get("abort_reason")) or None,
        }
        return combined_result

    # 否则维持原有单仓库行为：若未指定 existing_repo_id 则创建一个临时仓库并在最后删除。
    if config.existing_repo_id is None:
        print_step("create-repo", "starting comparison repo creation")
        repo_id = await create_repo(config=config, repo_template=repo_template)
        print_step("create-repo", f"created repo_id={repo_id}")
        try:
            return await _run_for_repo(repo_id)
        finally:
            print_step("cleanup", f"deleting repo_id={repo_id}")
            await delete_repo(config=config, repo_id=repo_id)
            print_step("cleanup", f"deleted repo_id={repo_id}")
    else:
        return await _run_for_repo(config.existing_repo_id)
