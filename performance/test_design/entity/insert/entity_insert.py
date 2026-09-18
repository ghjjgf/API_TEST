"""Entity Insert 接口性能测试入口（Python orchestration + k6 execution）。"""

from __future__ import annotations

import asyncio
import importlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
from API_TEST.performance.data.entity.entity import SAMPLE_ENTITY
from API_TEST.performance.data.repo.repo import SAMPLE_REPO
from API_TEST.performance.test_design.common.ascii_report import render_report
from API_TEST.performance.test_design.common.entity_access import default_run_dir as common_default_run_dir

if TYPE_CHECKING:
    import aiohttp

DEFAULT_REPO_PREFIX = "entity-create"
DEFAULT_ENTITY_PREFIX = "entity"
DEFAULT_CONCURRENCY_VALUES = [512, 896, 1024]
DEFAULT_CAPACITY = 0
DEFAULT_TIMEOUT = 30
DEFAULT_TOTAL_DURATION_SECONDS = 200
DEFAULT_MEASUREMENT_START_OFFSET_SECONDS = 20
DEFAULT_MEASUREMENT_WINDOW_SECONDS = 180
DEFAULT_REPO_READY_WAIT_SECONDS = 5.0
DEFAULT_PROGRESS_UPDATE_SECONDS = 5.0

# 在这里输入要执行插入压测的多个 Repo ID，主流程会逐个执行并分别输出报告
DEFAULT_TARGET_REPO_IDS = [
    "3kwfacerepo_test",
    "5kwfacerepo",
    "1Efacerepo"
]


@dataclass(frozen=True)
class BenchmarkConfig:
    base_url: str
    repo_prefix: str
    entity_prefix: str
    repo_type: str
    capacity: int
    concurrency_values: list[int]
    total_duration_seconds: int
    measurement_start_offset_seconds: int
    measurement_window_seconds: int
    repo_ready_wait_seconds: float
    cleanup: bool
    k6_executable: str
    report_output_dir: Path
    repo_data: str | None = None
    entity_data: str | None = None
    target_repo_id: str | None = None


# 实现当前模块的核心逻辑。
def require_aiohttp():
    try:
        return importlib.import_module("aiohttp")
    except ModuleNotFoundError as exc:
        raise RuntimeError("aiohttp is required for repo lifecycle management in the k6 entity benchmark") from exc


# 构造当前场景所需的数据。
def build_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


# 返回当前场景的默认配置。
# (使用公共的 default_run_dir，参见 common.entity_access.default_run_dir)


# 加载当前场景所需的数据或模板。
def load_repo_template(repo_data: str | None = None) -> dict[str, Any]:
    if not repo_data:
        return deepcopy(SAMPLE_REPO)

    path = Path(repo_data)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read repo payload from {path}: {exc}") from exc


# 加载当前场景所需的数据或模板。
def load_entity_template(entity_data: str | None = None) -> dict[str, Any]:
    if not entity_data:
        return deepcopy(SAMPLE_ENTITY)

    path = Path(entity_data)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read entity payload from {path}: {exc}") from exc


# 每次插入使用的 face 特征文件（两列 TSV：<id>\t<base64 fp32 特征>）。
# 默认取插库脚本使用的 50w 条真实特征，避免压测反复写同一条特征造成 IVF 单桶倾斜。
DEFAULT_FEATURE_FILE = os.environ.get("ENTITY_FEATURE_FILE", "/home/wx/testFlow/wx/插库/feature_cache_fp32.txt")
# 0 = 使用特征文件里的全部特征（默认）；>0 = 只用前 N 条
DEFAULT_FEATURE_POOL_SIZE = int(os.environ.get("ENTITY_FEATURE_POOL_SIZE", "0"))


# 顺序读取特征文件中的 base64 特征值（只取前 limit 条，缓存复用，避免每个并发档重复读 1.4GB 文件）。


# 创建当前场景所需的资源或请求负载。
def create_entity_payload(entity_id: str, template: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = deepcopy(template or SAMPLE_ENTITY)
    payload["id"] = entity_id
    return payload


# 生成当前场景使用的标识或资源。
def make_repo_id(prefix: str, index: int) -> str:
    token = uuid.uuid4().hex[:10]
    return f"{prefix}-{index:04d}-{token}"


# 生成当前场景使用的标识或资源。
def make_entity_id(prefix: str, index: int) -> str:
    token = uuid.uuid4().hex
    return f"{prefix}-{index:08d}0-{token}"


# 实现当前模块的核心逻辑。
def normalize_serializable(data: Any) -> Any:
    if isinstance(data, (str, int, float, bool)) or data is None:
        return data
    if isinstance(data, dict):
        return {str(key): normalize_serializable(value) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        return [normalize_serializable(item) for item in data]
    return str(data)


# 实现当前模块的核心逻辑。
def percentile(values: list[float], percent: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = (len(ordered) - 1) * (percent / 100.0)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return round(ordered[lower], 3)
    weight = position - lower
    value = ordered[lower] + (ordered[upper] - ordered[lower]) * weight
    return round(value, 3)


# 实现当前模块的核心逻辑。
def estimate_payload_size_bytes(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


# 格式化当前场景的数据输出。
def format_iso_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


# 构造当前场景所需的数据。
def build_default_config(
    *,
    target_repo_id: str | None = None,
    cleanup: bool = True,
    report_output_dir: Path | str | None = None,
) -> BenchmarkConfig:
    return BenchmarkConfig(
        base_url=DEFAULT_BASE_URL,
        repo_prefix=DEFAULT_REPO_PREFIX,
        entity_prefix=DEFAULT_ENTITY_PREFIX,
        repo_type=SAMPLE_REPO["type"],
        capacity=DEFAULT_CAPACITY,
        concurrency_values=list(DEFAULT_CONCURRENCY_VALUES),
        total_duration_seconds=DEFAULT_TOTAL_DURATION_SECONDS,
        measurement_start_offset_seconds=DEFAULT_MEASUREMENT_START_OFFSET_SECONDS,
        measurement_window_seconds=DEFAULT_MEASUREMENT_WINDOW_SECONDS,
        repo_ready_wait_seconds=DEFAULT_REPO_READY_WAIT_SECONDS,
        cleanup=cleanup,
        k6_executable="k6",
        report_output_dir=Path(report_output_dir) if report_output_dir else common_default_run_dir("entity_insert", category="entity"),
        target_repo_id=target_repo_id,
    )


# 校验当前场景的配置或输入。
def validate_config(config: BenchmarkConfig) -> None:
    if config.measurement_start_offset_seconds < 0:
        raise ValueError("measurement_start_offset_seconds must be >= 0")
    if config.measurement_window_seconds <= 0:
        raise ValueError("measurement_window_seconds must be > 0")
    if config.measurement_start_offset_seconds + config.measurement_window_seconds > config.total_duration_seconds:
        raise ValueError("measurement window must fit within total duration")
    if not config.concurrency_values:
        raise ValueError("concurrency_values cannot be empty")
    if config.target_repo_id is not None and not config.target_repo_id.strip():
        raise ValueError("target_repo_id must not be blank when provided")


# 打印当前场景的说明或统计结果。
def print_step(label: str, detail: str) -> None:
    print(f"[INFO] {label.upper().replace('-', '_'):<18} {detail}")


# 渲染当前场景的图表或报告。
def render_progress_bar(value: float, total: float, width: int = 24) -> str:
    ratio = 0.0 if total <= 0 else max(0.0, min(1.0, value / total))
    filled = max(0, min(width, int(ratio * width)))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {ratio * 100:5.1f}%"


# 输出当前场景的进度信息。
def emit_measured_progress_line(*, current_seconds: float, total_seconds: float, repo_id: str, concurrency: int, done: bool = False) -> None:
    elapsed = min(current_seconds, total_seconds)
    status = f"repo={repo_id} concurrency={concurrency} measured | {render_progress_bar(elapsed, total_seconds)} {elapsed:5.1f}s/{total_seconds:5.1f}s"
    if done:
        sys.stdout.write(f"\r[INFO] PHASE_PROGRESS     {status} ✅")
        sys.stdout.flush()
        return
    sys.stdout.write(f"\r[INFO] PHASE_PROGRESS     {status}")
    sys.stdout.flush()


# 打印当前场景的说明或统计结果。
def print_phase_metric_summary(metric: dict[str, Any]) -> None:
    summary_line = (
        "[INFO] CONCURRENCY_RESULT "
        f"concurrency={metric['concurrency']} | "
        f"total_requests={metric['total_requests']} | "
        f"success_count={metric['success_count']} | "
        f"failure_count={metric['failure_count']} | "
        f"success_rate={metric['success_rate']}% | "
        f"error_rate={metric['error_rate']}% | "
        f"qps={metric['throughput_rps']} | "
        f"p50={metric['latency_p50_ms']}ms | "
        f"p95={metric['latency_p95_ms']}ms | "
        f"p99={metric['latency_p99_ms']}ms | "
        f"avg={metric['latency_avg_ms']}ms | "
        f"max={metric['latency_max_ms']}ms | "
        f"timeout_count={metric['timeout_count']} | "
        f"connection_error_count={metric['connection_error_count']}"
    )
    sys.stdout.write("\n")
    print(summary_line)


# 实现当前模块的核心逻辑。
async def send_json_request_async(
    session: aiohttp.ClientSession,
    *,
    method: str,
    url: str,
    timeout: int,
    insecure: bool,
    payload: dict[str, Any] | None,
) -> tuple[int | None, Any]:
    aiohttp = require_aiohttp()
    try:
        async with session.request(
            method=method,
            url=url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout),
            ssl=False if insecure else None,
        ) as response:
            try:
                body = await response.json()
            except (aiohttp.ContentTypeError, json.JSONDecodeError, ValueError):
                body = await response.text()
            return response.status, body
    except aiohttp.ClientError as exc:
        return None, str(exc)
    except asyncio.TimeoutError:
        return None, "timeout"


# 创建当前场景所需的资源或请求负载。
async def create_repo_async(
    base_url: str,
    timeout: int,
    insecure: bool,
    repo_id: str,
    capacity: int,
    repo_type: str,
    template: dict[str, Any],
    session: aiohttp.ClientSession,
) -> tuple[int | None, Any]:
    payload = deepcopy(template)
    payload["id"] = repo_id
    payload["type"] = repo_type
    payload["capacity"] = capacity
    return await send_json_request_async(
        session,
        method="POST",
        url=build_url(base_url, "/repositories"),
        timeout=timeout,
        insecure=insecure,
        payload=payload,
    )


# 删除当前场景所需的资源或请求负载。
async def delete_repo_async(
    base_url: str,
    timeout: int,
    insecure: bool,
    repo_id: str,
    session: aiohttp.ClientSession,
) -> tuple[int | None, Any]:
    return await send_json_request_async(
        session,
        method="DELETE",
        url=build_url(base_url, f"/repositories/{repo_id}"),
        timeout=timeout,
        insecure=insecure,
        payload=None,
    )


# 等待当前场景所需的资源进入目标状态。
def wait_for_repo_ready(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


# 过滤当前场景需要保留的数据。
def filter_measured_window_events(
    events: list[dict[str, Any]],
    measurement_start_offset_seconds: float,
    measurement_window_seconds: float,
) -> list[dict[str, Any]]:
    measurement_end = measurement_start_offset_seconds + measurement_window_seconds
    return [
        event
        for event in events
        if measurement_start_offset_seconds <= float(event["relative_start_s"]) < measurement_end
    ]


# 汇总当前场景的统计结果。
def summarize_measured_events(
    events: list[dict[str, Any]],
    *,
    concurrency: int,
    measurement_window_seconds: float,
) -> dict[str, Any]:
    total_requests = len(events)
    success_events = [item for item in events if item.get("ok")]
    failure_events = [item for item in events if not item.get("ok")]
    latencies = [float(item.get("duration_ms") or 0.0) for item in events]
    error_kind_counts = Counter(str(item.get("error_kind")) for item in failure_events if item.get("error_kind"))
    return {
        "concurrency": concurrency,
        "total_requests": total_requests,
        "success_count": len(success_events),
        "failure_count": len(failure_events),
        "success_rate": round((len(success_events) / total_requests) * 100.0, 3) if total_requests else 0.0,
        "error_rate": round((len(failure_events) / total_requests) * 100.0, 3) if total_requests else 0.0,
        "throughput_rps": round(total_requests / measurement_window_seconds, 3) if measurement_window_seconds > 0 else 0.0,
        "latency_p50_ms": percentile(latencies, 50),
        "latency_p95_ms": percentile(latencies, 95),
        "latency_p99_ms": percentile(latencies, 99),
        "latency_avg_ms": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "latency_max_ms": round(max(latencies), 3) if latencies else None,
        "timeout_count": int(error_kind_counts.get("timeout", 0)),
        "connection_error_count": int(error_kind_counts.get("connection_error", 0)),
    }


# 分析当前场景的指标变化。
def analyze_performance_inflection(steady_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    qps_plateau_concurrency = None
    latency_growth_concurrency = None
    error_growth_concurrency = None
    stability_degradation_concurrency = None

    for current, nxt in zip(steady_metrics, steady_metrics[1:]):
        current_qps = float(current.get("throughput_rps") or 0.0)
        next_qps = float(nxt.get("throughput_rps") or 0.0)
        if current_qps > 0 and next_qps <= current_qps * 1.10:
            qps_plateau_concurrency = current.get("concurrency")
            break

    for previous, current in zip(steady_metrics, steady_metrics[1:]):
        previous_p95 = float(previous.get("latency_p95_ms") or 0.0)
        current_p95 = float(current.get("latency_p95_ms") or 0.0)
        if previous_p95 > 0 and current_p95 >= previous_p95 * 1.5:
            latency_growth_concurrency = current.get("concurrency")
            break

    for current in steady_metrics:
        if float(current.get("error_rate") or 0.0) >= 5.0:
            error_growth_concurrency = current.get("concurrency")
            break

    for current in steady_metrics:
        if float(current.get("success_rate") or 100.0) < 95.0:
            stability_degradation_concurrency = current.get("concurrency")
            break

    narrative_parts: list[str] = []
    if qps_plateau_concurrency is not None:
        narrative_parts.append(f"系统在并发 {qps_plateau_concurrency} 左右开始接近吞吐平台")
    if latency_growth_concurrency is not None:
        narrative_parts.append(f"P95 延迟在并发 {latency_growth_concurrency} 开始明显上升")
    if error_growth_concurrency is not None:
        narrative_parts.append(f"错误率在并发 {error_growth_concurrency} 开始显著上升")
    if stability_degradation_concurrency is not None:
        narrative_parts.append(f"稳定性在并发 {stability_degradation_concurrency} 开始明显下降")
    if not narrative_parts:
        narrative_parts.append("当前数据尚未呈现明确的吞吐拐点")

    return {
        "qps_plateau_concurrency": qps_plateau_concurrency,
        "latency_growth_concurrency": latency_growth_concurrency,
        "error_growth_concurrency": error_growth_concurrency,
        "stability_degradation_concurrency": stability_degradation_concurrency,
        "narrative": "；".join(narrative_parts),
    }


# 构造当前场景所需的数据。
def build_failures_payload(summary: dict[str, Any], measured_failure_events: list[dict[str, Any]]) -> dict[str, Any]:
    error_kind_counts = Counter(str(item.get("error_kind")) for item in measured_failure_events if item.get("error_kind"))
    status_counts = Counter(str(item.get("status")) for item in measured_failure_events if item.get("status") is not None)
    return {
        "meta": {
            "generated_at": summary["generated_at"],
            "base_url": summary["base_url"],
            "endpoint": summary["endpoint"],
            "total_duration_seconds": summary["total_duration_seconds"],
            "measurement_start_offset_seconds": summary["measurement_start_offset_seconds"],
            "measurement_window_seconds": summary["measurement_window_seconds"],
            "repo_mode": summary.get("repo_mode"),
            "target_repo_id": summary.get("target_repo_id"),
            "cleanup_enabled": summary.get("cleanup_enabled"),
        },
        "summary": {
            "total_failure_count": len(measured_failure_events),
            "concurrency_with_failures": sorted({int(item["concurrency"]) for item in measured_failure_events}) if measured_failure_events else [],
            "error_kind_counts": dict(error_kind_counts),
            "status_counts": dict(status_counts),
        },
        "failures": normalize_serializable(measured_failure_events),
    }


# 内部辅助函数，封装当前模块的局部逻辑。
def _format_report_int(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value)


# 内部辅助函数，封装当前模块的局部逻辑。
def _format_report_float(value: Any, *, decimals: int = 2, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


# 内部辅助函数，封装当前模块的局部逻辑。
def _render_ascii_table(headers: list[str], rows: list[list[str]]) -> str:
    normalized_rows: list[list[str]] = []
    source_rows = rows if rows else [["N/A"] * len(headers)]
    for row in source_rows:
        cells = [str(cell) for cell in row[: len(headers)]]
        if len(cells) < len(headers):
            cells.extend([""] * (len(headers) - len(cells)))
        normalized_rows.append(cells)

    widths = [len(header) for header in headers]
    for row in normalized_rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    # 格式化当前场景的数据输出。
    def format_row(row: list[str]) -> str:
        return " | ".join(cell.ljust(widths[index]) for index, cell in enumerate(row))

    separator = " | ".join("-" * width for width in widths)
    return "\n".join([format_row(headers), separator, *(format_row(row) for row in normalized_rows)])


# 内部辅助函数，封装当前模块的局部逻辑。
def _render_concurrency_summary_table(phase_metrics: list[dict[str, Any]]) -> str:
    headers = [
        "Concurrency",
        "Total Req",
        "Success",
        "Failure",
        "Success Rate",
        "Error Rate",
        "QPS",
        "P50",
        "Avg Latency",
        "P95",
        "P99",
        "Max",
        "Timeout",
        "Conn Err",
    ]
    rows: list[list[str]] = []
    for metric in phase_metrics:
        rows.append(
            [
                _format_report_int(metric.get("concurrency")),
                _format_report_int(metric.get("total_requests")),
                _format_report_int(metric.get("success_count")),
                _format_report_int(metric.get("failure_count")),
                _format_report_float(metric.get("success_rate"), decimals=2, suffix="%"),
                _format_report_float(metric.get("error_rate"), decimals=2, suffix="%"),
                _format_report_float(metric.get("throughput_rps"), decimals=2),
                _format_report_float(metric.get("latency_p50_ms"), decimals=2, suffix=" ms"),
                _format_report_float(metric.get("latency_avg_ms"), decimals=2, suffix=" ms"),
                _format_report_float(metric.get("latency_p95_ms"), decimals=2, suffix=" ms"),
                _format_report_float(metric.get("latency_p99_ms"), decimals=2, suffix=" ms"),
                _format_report_float(metric.get("latency_max_ms"), decimals=2, suffix=" ms"),
                _format_report_int(metric.get("timeout_count")),
                _format_report_int(metric.get("connection_error_count")),
            ]
        )
    return _render_ascii_table(headers, rows)


# 渲染当前场景的图表或报告。
def render_final_markdown_report(summary: dict[str, Any], failure_summary: dict[str, Any]) -> str:
    phase_metrics = summary.get("phase_metrics", [])
    repo_mode = summary.get("repo_mode", "managed")
    target_repo_id = summary.get("target_repo_id")
    if repo_mode == "existing" and target_repo_id:
        repo_mode_line = "复用既有 Repo"
        repo_target_line = f"`{target_repo_id}`"
    else:
        repo_mode_line = "自动创建临时 Repo"
        repo_target_line = "N/A"
    metrics_table = _render_concurrency_summary_table(phase_metrics)

    inflection = summary.get("inflection_analysis", {})
    return f"""# Entity Insert 接口性能测试报告

## 测试目标

- 验证 `POST /repositories/{{repo_id}}/entities` 在不同并发梯度下的正式窗口性能表现。

## 测试环境配置

- 生成时间：{summary['generated_at']}
- Base URL：`{summary['base_url']}`
- Endpoint：`POST {summary['endpoint']}`
- Repo Type：`{summary['repo_type']}`
- Capacity：`{summary['capacity']}`
- Concurrency Values：`{summary['concurrency_values']}`
- 测量窗口：前 `{summary['measurement_start_offset_seconds']}s` 预热 / 后 `{summary['measurement_window_seconds']}s` 统计
- 并发梯度数：{len(summary.get('concurrency_values', []))}
- 失败请求数：{failure_summary.get('total_failure_count', 0)}
- Repo 模式：{repo_mode_line}
- 目标 Repo：{repo_target_line}

## 并发结果

{metrics_table}

## 性能拐点分析

- 结论：{inflection.get('narrative')}

## 失败请求摘要

- 总失败数：{failure_summary.get('total_failure_count', 0)}
- 详细失败响应体见：`failures.json`

## 产物索引

    - `entity_insert_report.md`
- `failures.json`
"""


# 写入当前场景输出文件。
def write_final_outputs(summary: dict[str, Any], failures_payload: dict[str, Any]) -> Path:
    output_dir = Path(summary["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "failures.json").write_text(json.dumps(normalize_serializable(failures_payload), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = render_final_markdown_report(summary, failures_payload.get("summary", {}))
    report_path = output_dir / "entity_insert_report.md"
    report_path.write_text(markdown, encoding="utf-8")
    return report_path


# 解析当前场景生成的事件或日志。
def parse_k6_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        events.append(json.loads(raw))
    return events


# 内部辅助函数，封装当前模块的局部逻辑。
def _build_k6_script_content(
    config: BenchmarkConfig,
    *,
    repo_id: str,
    concurrency: int,
    payload_path: Path,
    events_path: Path,
    run_token: str,
    feature_file: Path | None = None,
    feature_limit: int = 0,
) -> str:
    endpoint = build_url(config.base_url, f"/repositories/{repo_id}/entities")
    total_duration = f"{config.total_duration_seconds}s"
    if feature_file:
        limit_js = int(feature_limit) if feature_limit and feature_limit > 0 else 0
        features_init = (
            "new SharedArray('entity_features', function () {"
            f"  const lines = open('{feature_file.as_posix()}').split('\\n');"
            "  const out = [];"
            f"  const limit = {limit_js};"
            "  for (let i = 0; i < lines.length; i++) {"
            "    if (limit > 0 && out.length >= limit) { break; }"
            "    const s = lines[i];"
            "    if (!s) { continue; }"
            "    const tab = s.indexOf('\\t');"
            "    const value = tab >= 0 ? s.slice(tab + 1).trim() : ((s.trim().split(/\\s+/)[1]) || '');"
            "    if (value) { out.push(value); }"
            "  }"
            "  return out;"
            "})"
        )
    else:
        features_init = "[]"
    return f"""
import http from 'k6/http';
import exec from 'k6/execution';
import {{ SharedArray }} from 'k6/data';

const payloadTemplate = JSON.parse(open('{payload_path.as_posix()}'));
const eventsPath = '{events_path.as_posix()}';
const runToken = '{run_token}';
// 特征池：用 SharedArray 只加载一次、所有 VU 共享（避免每个 VU 各读一份）
const features = {features_init};

export const options = {{
  scenarios: {{
    entity_insert: {{
      executor: 'constant-vus',
      vus: {concurrency},
      duration: '{total_duration}',
    }},
  }},
  summaryTrendStats: ['avg', 'min', 'med', 'p(95)', 'p(99)', 'max'],
}};

function makeEntityId(vu, iter) {{
  return `entity-k6-${{runToken}}-{concurrency}-${{vu}}-${{String(iter).padStart(8, '0')}}`;
}}

function appendEvent(event) {{
  console.log('__K6_EVENT__' + JSON.stringify(event));
}}

export default function () {{
  const entityId = makeEntityId(exec.vu.idInTest, exec.scenario.iterationInTest);
  const payload = JSON.parse(JSON.stringify(payloadTemplate));
  payload.id = entityId;
  // 顺序使用特征池中的下一条特征（按全局迭代序号取，池用尽后循环），不再复用同一条特征
  if (features.length > 0) {{
    const featureIndex = exec.scenario.iterationInTest % features.length;
    payload.data.value = features[featureIndex];
  }}
  const started = Date.now();
  const response = http.post('{endpoint}', JSON.stringify(payload), {{
    headers: {{ 'Content-Type': 'application/json' }},
    timeout: '{DEFAULT_TIMEOUT}s',
  }});
  const ended = Date.now();
  let body = '';
  try {{
    body = response.body || '';
  }} catch (error) {{
    body = '';
  }}
  appendEvent({{
    relative_start_s: started / 1000,
    relative_end_s: ended / 1000,
    concurrency: {concurrency},
    repo_id: '{repo_id}',
    entity_id: entityId,
    status: response.status,
    duration_ms: response.timings.duration,
    ok: response.status >= 200 && response.status < 300,
    error_kind: null,
    error_message: null,
    response_headers: response.status >= 400 ? response.headers : null,
    response_body: response.status >= 400 ? body : null,
    response_preview: body ? String(body).slice(0, 240) : '',
  }});
}}
""".strip()


# 构造当前场景所需的数据。
def build_k6_runtime_files(
    config: BenchmarkConfig,
    *,
    repo_id: str,
    concurrency: int,
    entity_template: dict[str, Any],
    run_token: str | None = None,
    feature_pool_size: int | None = None,
) -> dict[str, Path]:
    runtime_dir = Path(tempfile.mkdtemp(prefix=f"entity-insert-k6-{concurrency}-"))
    script_path = runtime_dir / "entity_insert_runtime.js"
    events_path = runtime_dir / "events.jsonl"
    payload_path = runtime_dir / "entity_payload.json"
    run_token = run_token or uuid.uuid4().hex[:12]
    events_path.touch()
    payload_path.write_text(json.dumps(create_entity_payload("sample", entity_template), ensure_ascii=False, indent=2), encoding="utf-8")
    # 直接把源特征文件交给 k6 的 SharedArray 读取（只读一次、全 VU 共享），
    # 避免每个并发档把上百万条特征复制一份到 runtime 目录。
    feature_file = Path(DEFAULT_FEATURE_FILE)
    pool_limit = int(feature_pool_size if feature_pool_size is not None else DEFAULT_FEATURE_POOL_SIZE)
    script_path.write_text(
        _build_k6_script_content(
            config,
            repo_id=repo_id,
            concurrency=concurrency,
            payload_path=payload_path,
            events_path=events_path,
            run_token=run_token,
            feature_file=feature_file if feature_file.is_file() else None,
            feature_limit=pool_limit,
        ),
        encoding="utf-8",
    )
    return {
        "runtime_dir": runtime_dir,
        "script_path": script_path,
        "events_path": events_path,
        "payload_path": payload_path,
        "feature_file": str(feature_file),
        "feature_limit": pool_limit,
    }


# 执行当前场景的核心流程。
def run_k6_for_concurrency(config: BenchmarkConfig, *, repo_id: str, concurrency: int, runtime_files: dict[str, Path]) -> subprocess.CompletedProcess[str]:
    env = dict(**__import__("os").environ)
    env["ENTITY_INSERT_EVENTS_PATH"] = str(runtime_files["events_path"])
    env["ENTITY_INSERT_REPO_ID"] = repo_id
    command = [config.k6_executable, "run", str(runtime_files["script_path"])]
    return subprocess.run(command, capture_output=True, text=True, check=False, env=env)


_ORIGINAL_RUN_K6_FOR_CONCURRENCY = run_k6_for_concurrency


# 内部辅助函数，封装当前模块的局部逻辑。
def _decode_embedded_k6_json(raw_payload: str) -> dict[str, Any] | None:
    candidates = [raw_payload.strip()]
    if '" source=' in raw_payload:
        candidates.append(raw_payload.split('" source=', 1)[0].strip())
    if '" level=' in raw_payload:
        candidates.append(raw_payload.split('" level=', 1)[0].strip())

    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(json.loads(f'"{candidate}"'))
        except json.JSONDecodeError:
            continue
    return None


# 内部辅助函数，封装当前模块的局部逻辑。
def _parse_k6_console_events(output: str) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    marker = "__K6_EVENT__"
    for line in output.splitlines():
        if marker not in line:
            continue
        payload = line.split(marker, 1)[1]
        event = _decode_embedded_k6_json(payload)
        if event is not None:
            parsed.append(event)
    return parsed


# 内部辅助函数，封装当前模块的局部逻辑。


# 内部辅助函数，封装当前模块的局部逻辑。
def _normalize_k6_relative_times(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not events:
        return []
    base_start = min(float(event["relative_start_s"]) for event in events)
    needs_rebase = base_start > 1000
    normalized: list[dict[str, Any]] = []
    for event in events:
        cloned = dict(event)
        start_s = float(event["relative_start_s"])
        end_s = float(event.get("relative_end_s", start_s))
        if needs_rebase:
            cloned["relative_start_s"] = round(start_s - base_start, 6)
            cloned["relative_end_s"] = round(end_s - base_start, 6)
        else:
            cloned["relative_start_s"] = round(start_s, 6)
            cloned["relative_end_s"] = round(end_s, 6)
        if cloned.get("response_body") is not None and isinstance(cloned["response_body"], str):
            body_text = cloned["response_body"].strip()
            if body_text:
                try:
                    cloned["response_body"] = json.loads(body_text)
                except json.JSONDecodeError:
                    pass
        normalized.append(cloned)
    return normalized


# 内部辅助函数，封装当前模块的局部逻辑。
def _cleanup_runtime_files(runtime_files: dict[str, Path]) -> None:
    runtime_dir = runtime_files.get("runtime_dir")
    if runtime_dir and runtime_dir.exists():
        shutil.rmtree(runtime_dir, ignore_errors=True)


# 内部辅助函数，封装当前模块的局部逻辑。
def _filter_events_for_current_run(
    events: list[dict[str, Any]],
    *,
    repo_id: str,
    concurrency: int,
) -> list[dict[str, Any]]:
    has_concurrency = any(event.get("concurrency") is not None for event in events)
    if has_concurrency:
        concurrency_filtered = [event for event in events if int(event["concurrency"]) == concurrency]
    else:
        concurrency_filtered = list(events)

    has_repo_id = any(event.get("repo_id") is not None for event in concurrency_filtered)
    repo_filtered = [event for event in concurrency_filtered if event.get("repo_id") == repo_id] if has_repo_id else []

    if repo_filtered:
        return repo_filtered
    if concurrency_filtered:
        return concurrency_filtered
    return []


# 内部辅助函数，封装当前模块的局部逻辑。
def _emit_measured_progress_until_complete(
    process: subprocess.Popen[str] | None,
    *,
    repo_id: str,
    concurrency: int,
    total_duration_seconds: float,
    measurement_start_offset_seconds: float,
    measurement_window_seconds: float,
) -> None:
    started = time.perf_counter()
    while True:
        elapsed = time.perf_counter() - started
        if elapsed >= measurement_start_offset_seconds:
            measured_elapsed = min(elapsed - measurement_start_offset_seconds, measurement_window_seconds)
            emit_measured_progress_line(
                current_seconds=measured_elapsed,
                total_seconds=measurement_window_seconds,
                repo_id=repo_id,
                concurrency=concurrency,
            )

        process_finished = process is None or process.poll() is not None
        if process_finished:
            break

        if elapsed >= total_duration_seconds:
            time.sleep(0.05)
        else:
            sleep_for = min(DEFAULT_PROGRESS_UPDATE_SECONDS, max(0.0, total_duration_seconds - elapsed))
            time.sleep(sleep_for)

    final_elapsed = max(time.perf_counter() - started - measurement_start_offset_seconds, 0.0)
    emit_measured_progress_line(
        current_seconds=min(final_elapsed, measurement_window_seconds),
        total_seconds=measurement_window_seconds,
        repo_id=repo_id,
        concurrency=concurrency,
        done=True,
    )


# 内部辅助函数，封装当前模块的局部逻辑。
def _run_k6_process_with_progress(
    config: BenchmarkConfig,
    *,
    repo_id: str,
    concurrency: int,
    runtime_files: dict[str, Path],
) -> subprocess.CompletedProcess[str]:
    env = dict(__import__("os").environ)
    env["ENTITY_INSERT_EVENTS_PATH"] = str(runtime_files["events_path"])
    env["ENTITY_INSERT_REPO_ID"] = repo_id
    command = [config.k6_executable, "run", str(runtime_files["script_path"])]

    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    progress_thread = threading.Thread(
        target=_emit_measured_progress_until_complete,
        kwargs={
            "process": process,
            "repo_id": repo_id,
            "concurrency": concurrency,
            "total_duration_seconds": float(config.total_duration_seconds),
            "measurement_start_offset_seconds": float(config.measurement_start_offset_seconds),
            "measurement_window_seconds": float(config.measurement_window_seconds),
        },
        daemon=True,
    )
    progress_thread.start()
    stdout, stderr = process.communicate()
    progress_thread.join()
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


# 执行当前场景的核心流程。
def run_k6_for_concurrency_with_progress(
    config: BenchmarkConfig,
    *,
    repo_id: str,
    concurrency: int,
    runtime_files: dict[str, Path],
) -> subprocess.CompletedProcess[str]:
    # Preserve the old entry point for tests and simple call sites, while
    # letting the benchmark path opt into real-time single-line progress.
    patched_target = run_k6_for_concurrency
    if patched_target is not _ORIGINAL_RUN_K6_FOR_CONCURRENCY:
        return patched_target(
            config,
            repo_id=repo_id,
            concurrency=concurrency,
            runtime_files=runtime_files,
        )
    return _run_k6_process_with_progress(
        config,
        repo_id=repo_id,
        concurrency=concurrency,
        runtime_files=runtime_files,
    )


# 执行当前场景的核心流程。
def run_entity_insert_benchmark(config: BenchmarkConfig) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_config(config)
    entity_template = load_entity_template(config.entity_data)

    # 内部辅助函数，封装当前模块的局部逻辑。
    async def _run() -> tuple[dict[str, Any], dict[str, Any]]:
        target_repo_id = config.target_repo_id.strip() if config.target_repo_id else None
        managed_repo_ids: list[str] = []
        phase_metrics: list[dict[str, Any]] = []
        all_measured_failures: list[dict[str, Any]] = []
        if target_repo_id:
            print_step("repo-bind", f"using existing repo={target_repo_id} for all concurrency gradients; create/delete are skipped")

            for index, concurrency in enumerate(config.concurrency_values, start=1):
                repo_id = target_repo_id
                print_step("k6-start", f"repo={repo_id} concurrency={concurrency} total={config.total_duration_seconds}s | first {config.measurement_start_offset_seconds}s warmup/settle not counted")

                runtime_files = build_k6_runtime_files(
                    config,
                    repo_id=repo_id,
                    concurrency=concurrency,
                    entity_template=entity_template,
                )
                try:
                    completed = run_k6_for_concurrency_with_progress(
                        config,
                        repo_id=repo_id,
                        concurrency=concurrency,
                        runtime_files=runtime_files,
                    )
                    if completed.returncode != 0:
                        raise RuntimeError(f"k6 failed for concurrency {concurrency}: {completed.stderr.strip()}")

                    parsed_events = _parse_k6_console_events(f"{completed.stdout}\n{completed.stderr}")
                    runtime_files["events_path"].write_text(
                        "\n".join(json.dumps(item, ensure_ascii=False) for item in parsed_events),
                        encoding="utf-8",
                    )
                    events = parse_k6_events(runtime_files["events_path"])
                    current_run_events = _filter_events_for_current_run(events, repo_id=repo_id, concurrency=concurrency)
                    normalized_events = _normalize_k6_relative_times(current_run_events)
                    measured_events = filter_measured_window_events(
                        normalized_events,
                        config.measurement_start_offset_seconds,
                        config.measurement_window_seconds,
                    )
                    metric = summarize_measured_events(
                        measured_events,
                        concurrency=concurrency,
                        measurement_window_seconds=config.measurement_window_seconds,
                    )
                    phase_metrics.append(metric)
                    print_phase_metric_summary(metric)

                    for item in measured_events:
                        if item.get("ok"):
                            continue
                        all_measured_failures.append(
                            {
                                "concurrency": concurrency,
                                "repo_id": item.get("repo_id", repo_id),
                                "entity_id": item.get("entity_id"),
                                "status": item.get("status"),
                                "error_kind": item.get("error_kind"),
                                "error": item.get("error_message"),
                                "elapsed_ms": item.get("duration_ms"),
                                "started_at": format_iso_timestamp(time.time()),
                                "finished_at": format_iso_timestamp(time.time()),
                                "response_headers": item.get("response_headers"),
                                "response_body": item.get("response_body"),
                            }
                        )
                finally:
                    _cleanup_runtime_files(runtime_files)
        else:
            aiohttp = require_aiohttp()
            repo_template = load_repo_template(config.repo_data)
            connector = aiohttp.TCPConnector(limit=max(config.concurrency_values) * 2, limit_per_host=max(config.concurrency_values) * 2)
            timeout_config = aiohttp.ClientTimeout(total=max(config.total_duration_seconds, DEFAULT_TIMEOUT))

            async with aiohttp.ClientSession(timeout=timeout_config, connector=connector) as session:
                try:
                    for index, concurrency in enumerate(config.concurrency_values, start=1):
                        repo_id = make_repo_id(config.repo_prefix, index)
                        managed_repo_ids.append(repo_id)

                        print_step("repo-create", f"step {index}/{len(config.concurrency_values)} | creating repo={repo_id} (concurrency={concurrency})")
                        create_status, create_body = await create_repo_async(
                            config.base_url,
                            DEFAULT_TIMEOUT,
                            False,
                            repo_id,
                            config.capacity,
                            config.repo_type,
                            repo_template,
                            session,
                        )
                        if create_status is None or not (200 <= create_status < 300):
                            raise RuntimeError(f"Failed to create repo {repo_id}: {create_status}, body={create_body}")

                        print_step("repo-ready", f"repo={repo_id} waiting {config.repo_ready_wait_seconds:.1f}s for initialization")
                        wait_for_repo_ready(config.repo_ready_wait_seconds)
                        print_step("repo-ready", f"repo={repo_id} ready")

                        print_step("k6-start", f"repo={repo_id} concurrency={concurrency} total={config.total_duration_seconds}s | first {config.measurement_start_offset_seconds}s warmup/settle not counted")

                        runtime_files = build_k6_runtime_files(
                            config,
                            repo_id=repo_id,
                            concurrency=concurrency,
                            entity_template=entity_template,
                        )
                        try:
                            completed = run_k6_for_concurrency_with_progress(
                                config,
                                repo_id=repo_id,
                                concurrency=concurrency,
                                runtime_files=runtime_files,
                            )
                            if completed.returncode != 0:
                                raise RuntimeError(f"k6 failed for concurrency {concurrency}: {completed.stderr.strip()}")

                            parsed_events = _parse_k6_console_events(f"{completed.stdout}\n{completed.stderr}")
                            runtime_files["events_path"].write_text(
                                "\n".join(json.dumps(item, ensure_ascii=False) for item in parsed_events),
                                encoding="utf-8",
                            )
                            events = parse_k6_events(runtime_files["events_path"])
                            current_run_events = _filter_events_for_current_run(events, repo_id=repo_id, concurrency=concurrency)
                            normalized_events = _normalize_k6_relative_times(current_run_events)
                            measured_events = filter_measured_window_events(
                                normalized_events,
                                config.measurement_start_offset_seconds,
                                config.measurement_window_seconds,
                            )
                            metric = summarize_measured_events(
                                measured_events,
                                concurrency=concurrency,
                                measurement_window_seconds=config.measurement_window_seconds,
                            )
                            phase_metrics.append(metric)
                            print_phase_metric_summary(metric)

                            for item in measured_events:
                                if item.get("ok"):
                                    continue
                                all_measured_failures.append(
                                    {
                                        "concurrency": concurrency,
                                        "repo_id": item.get("repo_id", repo_id),
                                        "entity_id": item.get("entity_id"),
                                        "status": item.get("status"),
                                        "error_kind": item.get("error_kind"),
                                        "error": item.get("error_message"),
                                        "elapsed_ms": item.get("duration_ms"),
                                        "started_at": format_iso_timestamp(time.time()),
                                        "finished_at": format_iso_timestamp(time.time()),
                                        "response_headers": item.get("response_headers"),
                                        "response_body": item.get("response_body"),
                                    }
                                )
                        finally:
                            _cleanup_runtime_files(runtime_files)

                finally:
                    if config.cleanup:
                        for repo_id in managed_repo_ids:
                            await delete_repo_async(config.base_url, DEFAULT_TIMEOUT, False, repo_id, session)

        inflection = analyze_performance_inflection(phase_metrics)
        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "base_url": config.base_url,
            "endpoint": "/repositories/{repo_id}/entities",
            "repo_type": config.repo_type,
            "capacity": config.capacity,
            "repo_mode": "existing" if target_repo_id else "managed",
            "target_repo_id": target_repo_id,
            "cleanup_enabled": config.cleanup,
            "concurrency_values": list(config.concurrency_values),
            "total_duration_seconds": config.total_duration_seconds,
            "measurement_start_offset_seconds": config.measurement_start_offset_seconds,
            "measurement_window_seconds": config.measurement_window_seconds,
            "phase_metrics": phase_metrics,
            "inflection_analysis": inflection,
            "output_dir": str(config.report_output_dir),
            "entity_payload_size_bytes": estimate_payload_size_bytes(create_entity_payload("sample", entity_template)),
        }
        failures_payload = build_failures_payload(summary, all_measured_failures)
        write_final_outputs(summary, failures_payload)
        return summary, failures_payload

    return asyncio.run(_run())


# 汇总多仓库失败明细（用于最终合并报告的同级 failures.json）。
def build_combined_failures(repo_results: list[dict[str, Any]], failures_by_repo: list[dict[str, Any]]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    error_kind_counts: Counter = Counter()
    status_counts: Counter = Counter()
    concurrency_with_failures: set[int] = set()
    failure_count_by_repo: dict[str, int] = {}
    for result, payload in zip(repo_results, failures_by_repo):
        repo_id = str(result.get("repo_id") or "multi")
        summary = (payload or {}).get("summary") or {}
        failure_count_by_repo[repo_id] = int(summary.get("total_failure_count") or 0)
        records.extend((payload or {}).get("failures") or [])
        error_kind_counts.update({str(k): int(v) for k, v in (summary.get("error_kind_counts") or {}).items()})
        status_counts.update({str(k): int(v) for k, v in (summary.get("status_counts") or {}).items()})
        for value in summary.get("concurrency_with_failures") or []:
            try:
                concurrency_with_failures.add(int(value))
            except (TypeError, ValueError):
                continue
    meta = (failures_by_repo[0].get("meta") if failures_by_repo and failures_by_repo[0] else {}) or {}
    return {
        "meta": {**meta, "repo_ids": [str(result.get("repo_id")) for result in repo_results]},
        "summary": {
            "total_failure_count": len(records),
            "concurrency_with_failures": sorted(concurrency_with_failures),
            "error_kind_counts": dict(error_kind_counts),
            "status_counts": dict(status_counts),
            "failure_count_by_repo": failure_count_by_repo,
        },
        "failures": normalize_serializable(records),
    }


# 渲染多仓库合并报告（ASCII 表格，格式与 entity_delete 一致）。
def write_combined_report(
    run_dir: Path | str,
    repo_results: list[dict[str, Any]],
    failures_payload: dict[str, Any],
    *,
    base_url: str,
    endpoint: str,
    generated_at: str,
) -> Path:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "entity_insert_report.md"
    repo_label = ", ".join(str(result.get("repo_id")) for result in repo_results) or "N/A"
    failure_count = (failures_payload.get("summary") or {}).get("total_failure_count", 0)
    report_text = render_report(
        title="Entity Insert Interface Performance Report",
        goal=f"- 验证仓库 `{repo_label}` 在不同并发梯度下的插入实例性能表现。",
        env_lines=[
            f"- 生成时间：{generated_at}",
            f"- Base URL：`{base_url}`",
            f"- Endpoint：`POST {endpoint}`",
            f"- Repo Type：`{SAMPLE_REPO['type']}`",
            f"- Capacity：`{DEFAULT_CAPACITY}`",
            f"- Concurrency Values：`{DEFAULT_CONCURRENCY_VALUES}`",
            "- 测量窗口：前 `5s` 预热 / 后 `30s` 统计",
            "- Repo 模式：复用既有 Repo",
            f"- Repo 数量：{len(repo_results)}",
            f"- 失败请求数：{failure_count}",
        ],
        repo_results=repo_results,
        failure_count=failure_count,
        artifact_lines=["- `entity_insert_report.md`", "- `failures.json`"],
    )
    report_path.write_text(report_text, encoding="utf-8")
    (run_dir / "failures.json").write_text(
        json.dumps(failures_payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return report_path


# 依次压测所有目标 Repo，并输出一份合并报告。
def run_multi_repo_benchmark(repo_ids: list[str] | None = None, *, cleanup: bool = False) -> Path:
    targets = list(repo_ids if repo_ids is not None else DEFAULT_TARGET_REPO_IDS)
    if not targets:
        raise ValueError("DEFAULT_TARGET_REPO_IDS cannot be empty")

    run_dir = common_default_run_dir("entity_insert", category="entity")
    repo_results: list[dict[str, Any]] = []
    failures_by_repo: list[dict[str, Any]] = []
    generated_at = ""
    base_url = DEFAULT_BASE_URL
    endpoint = ""

    for repo_id in targets:
        config = build_default_config(target_repo_id=repo_id, cleanup=cleanup, report_output_dir=run_dir)
        summary, failures_payload = run_entity_insert_benchmark(config)
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
    print(f"[entity_insert] Combined report written to: {report_path}")
    return report_path


# 程序入口，用于串起当前模块的执行流程。
def main() -> int:
    run_multi_repo_benchmark()
    return 0


__all__ = [
    "BenchmarkConfig",
    "build_default_config",
    "build_combined_failures",
    "build_failures_payload",
    "build_k6_runtime_files",
    "create_repo_async",
    "delete_repo_async",
    "emit_measured_progress_line",
    "filter_measured_window_events",
    "load_entity_template",
    "load_repo_template",
    "make_entity_id",
    "make_repo_id",
    "parse_k6_events",
    "print_phase_metric_summary",
    "render_final_markdown_report",
    "run_entity_insert_benchmark",
    "run_multi_repo_benchmark",
    "run_k6_for_concurrency",
    "run_k6_for_concurrency_with_progress",
    "summarize_measured_events",
    "validate_config",
    "write_combined_report",
    "write_final_outputs",
]


if __name__ == "__main__":
    raise SystemExit(main())
