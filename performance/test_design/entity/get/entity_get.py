"""Entity Get 接口性能测试入口（Python orchestration + k6 execution）。

三个目标 Repo 顺序压测，结果汇总到同一份 ASCII 表格报告，不再每个 Repo 单独出报告。
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

_resolved = Path(__file__).resolve()
# Locate the API_TEST package directory by walking ancestors (handles nested dirs)
PROJECT_ROOT = None
for ancestor in _resolved.parents:
    if ancestor.name == 'API_TEST':
        PROJECT_ROOT = ancestor
        break
if PROJECT_ROOT is None:
    PROJECT_ROOT = _resolved.parents[4]
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

from API_TEST.performance.config.config import DEFAULT_BASE_URL
from API_TEST.performance.test_design.common.ascii_report import render_report
from API_TEST.performance.test_design.common.entity_access import BenchmarkConfig, build_k6_runtime_files as _build_k6_runtime_files, default_run_dir, run_entity_access_benchmark

REPORT_FILENAME = "entity_get_report.md"
DEFAULT_CONCURRENCY_VALUES = [128, 512, 896]
# DEFAULT_CONCURRENCY_VALUES = [1]

# 在这里输入要执行 GET 压测的多个 Repo ID；
# 三个 Repo 的压测结果会一起写入同一份报告，不再分别新建报告。
DEFAULT_TARGET_REPO_IDS = [
    "3kwfacerepo_test",
    "5kwfacerepo",
    "1Efacerepo",
]
DEFAULT_ENTITY_POOL_SIZE = 20
DEFAULT_TIMEOUT = 30
DEFAULT_TOTAL_DURATION_SECONDS = 200
DEFAULT_MEASUREMENT_START_OFFSET_SECONDS = 20
DEFAULT_MEASUREMENT_WINDOW_SECONDS = 180
DEFAULT_REPO_READY_WAIT_SECONDS = 1.0


# 构造当前场景所需的数据。
def build_default_config(*, repo_id: str | None = None, report_output_dir: Path | str | None = None) -> BenchmarkConfig:
    return BenchmarkConfig(
        base_url=DEFAULT_BASE_URL,
        repo_id=repo_id or DEFAULT_TARGET_REPO_IDS[0],
        entity_prefix="entity-0",
        concurrency_values=list(DEFAULT_CONCURRENCY_VALUES),
        total_duration_seconds=DEFAULT_TOTAL_DURATION_SECONDS,
        measurement_start_offset_seconds=DEFAULT_MEASUREMENT_START_OFFSET_SECONDS,
        measurement_window_seconds=DEFAULT_MEASUREMENT_WINDOW_SECONDS,
        repo_ready_wait_seconds=DEFAULT_REPO_READY_WAIT_SECONDS,
        entity_pool_size=DEFAULT_ENTITY_POOL_SIZE,
        cleanup=True,
        k6_executable="k6",
        report_output_dir=Path(report_output_dir) if report_output_dir else default_run_dir("entity_get", category="entity"),
        entity_data=None,
    )


# 构造当前场景所需的数据。
def build_k6_runtime_files(config: BenchmarkConfig, **kwargs):
    kwargs.pop("operation", None)
    return _build_k6_runtime_files(config, operation="get", **kwargs)


# 执行当前场景的核心流程（单个 Repo）。
def run_entity_get_benchmark(config: BenchmarkConfig):
    return run_entity_access_benchmark(
        config,
        operation="get",
        endpoint=f"/repositories/{config.repo_id}/entities/{{entity_id}}",
        report_title="Entity Get Interface Performance Report",
        report_filename=REPORT_FILENAME,
    )


# 汇总多仓库失败明细（用于最终合并报告的同级 failures.json）。
def build_combined_failures(repo_results: list[dict], failures_by_repo: list[dict]) -> dict:
    records: list[dict] = []
    error_kind_counts: Counter = Counter()
    status_counts: Counter = Counter()
    concurrency_with_failures: set[int] = set()
    per_repo_count: dict[str, int] = {}
    for result, payload in zip(repo_results, failures_by_repo):
        repo_id = str(result.get("repo_id") or "multi")
        summary = (payload or {}).get("summary") or {}
        count = int(summary.get("total_failure_count") or 0)
        per_repo_count[repo_id] = count
        for item in (payload or {}).get("failures") or []:
            records.append(item)
        error_kind_counts.update({str(k): v for k, v in (summary.get("error_kind_counts") or {}).items()})
        status_counts.update({str(k): v for k, v in (summary.get("status_counts") or {}).items()})
        for value in summary.get("concurrency_with_failures") or []:
            try:
                concurrency_with_failures.add(int(value))
            except (TypeError, ValueError):
                continue
    meta = (failures_by_repo[0].get("meta") if failures_by_repo and failures_by_repo[0] else {}) or {}
    return {
        "meta": {
            **meta,
            "repo_ids": [str(result.get("repo_id")) for result in repo_results],
        },
        "summary": {
            "total_failure_count": len(records),
            "concurrency_with_failures": sorted(concurrency_with_failures),
            "error_kind_counts": dict(error_kind_counts),
            "status_counts": dict(status_counts),
            "failure_count_by_repo": per_repo_count,
        },
        "failures": records,
    }


# 渲染多仓库合并报告（ASCII 表格，格式与 entity_delete 一致）。
def write_combined_report(
    run_dir: Path,
    repo_results: list[dict],
    failures_payload: dict,
    *,
    base_url: str,
    endpoint: str,
    generated_at: str,
) -> Path:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / REPORT_FILENAME
    repo_label = ", ".join(str(result.get("repo_id")) for result in repo_results) or "N/A"
    report_text = render_report(
        title="Entity Get Interface Performance Report",
        goal=f"- 验证仓库 `{repo_label}` 在不同并发梯度下的查询实例性能表现。",
        env_lines=[
            f"- 生成时间：{generated_at}",
            f"- Base URL：`{base_url}`",
            f"- Endpoint：`GET {endpoint}`",
            f"- Entity Pool Size：`{DEFAULT_ENTITY_POOL_SIZE}`",
            f"- Concurrency Values：`{DEFAULT_CONCURRENCY_VALUES}`",
            f"- 测量窗口：前 `{DEFAULT_MEASUREMENT_START_OFFSET_SECONDS}s` 预热 / 后 `{DEFAULT_MEASUREMENT_WINDOW_SECONDS}s` 统计",
            f"- Repo 数量：{len(repo_results)}",
            f"- 失败请求数：{failures_payload.get('summary', {}).get('total_failure_count', 0)}",
        ],
        repo_results=repo_results,
        failure_count=failures_payload.get('summary', {}).get('total_failure_count', 0),
        artifact_lines=[f"- `{REPORT_FILENAME}`", "- `failures.json`"],
    )
    report_path.write_text(report_text, encoding="utf-8")
    (run_dir / "failures.json").write_text(
        json.dumps(failures_payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return report_path


# 依次压测所有目标 Repo，并输出一份合并报告。
def run_multi_repo_benchmark(repo_ids: list[str] | None = None) -> Path:
    targets = list(repo_ids if repo_ids is not None else DEFAULT_TARGET_REPO_IDS)
    if not targets:
        raise ValueError("DEFAULT_TARGET_REPO_IDS cannot be empty")

    run_dir = default_run_dir("entity_get", category="entity")
    repo_results: list[dict] = []
    failures_by_repo: list[dict] = []
    generated_at = ""
    base_url = DEFAULT_BASE_URL
    endpoint = ""

    for repo_id in targets:
        config = build_default_config(repo_id=repo_id, report_output_dir=run_dir)
        summary, failures_payload = run_entity_get_benchmark(config)
        base_url = summary.get("base_url", base_url)
        endpoint = summary.get("endpoint", endpoint)
        generated_at = generated_at or str(summary.get("generated_at") or "")
        repo_results.append(
            {
                "repo_id": repo_id,
                "metrics": summary.get("phase_metrics", []),
                "inflection": summary.get("inflection_analysis", {}),
            }
        )
        failures_by_repo.append(failures_payload or {})
        print(f"[{repo_id}] benchmark finished (results merged into the combined report)")

    combined_failures = build_combined_failures(repo_results, failures_by_repo)
    report_path = write_combined_report(
        run_dir,
        repo_results,
        combined_failures,
        base_url=base_url,
        endpoint=endpoint,
        generated_at=generated_at,
    )
    print(f"[entity_get] Combined report written to: {report_path}")
    return report_path


# 程序入口，用于串起当前模块的执行流程。
def main() -> int:
    run_multi_repo_benchmark()
    return 0


__all__ = [
    "BenchmarkConfig",
    "build_combined_failures",
    "build_default_config",
    "build_k6_runtime_files",
    "run_entity_get_benchmark",
    "run_multi_repo_benchmark",
    "write_combined_report",
]


if __name__ == "__main__":
    raise SystemExit(main())
