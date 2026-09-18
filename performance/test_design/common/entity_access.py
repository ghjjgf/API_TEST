"""Shared helpers for entity access benchmarks."""

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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_resolved = Path(__file__).resolve()
# Locate the API_TEST package directory by walking ancestors (robust across depths)
PROJECT_ROOT = None
for ancestor in _resolved.parents:
    if ancestor.name == 'API_TEST':
        PROJECT_ROOT = ancestor
        break
if PROJECT_ROOT is None:
    PROJECT_ROOT = _resolved.parents[3]
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

from API_TEST.performance.data.entity.entity import SAMPLE_ENTITY
DEFAULT_TOTAL_DURATION_SECONDS = 200
DEFAULT_MEASUREMENT_START_OFFSET_SECONDS = 20
DEFAULT_MEASUREMENT_WINDOW_SECONDS = 180
DEFAULT_TIMEOUT = 30
DEFAULT_PROGRESS_UPDATE_SECONDS = 5.0


# 定位 k6 可执行文件：依次尝试环境变量 K6_EXECUTABLE、PATH 查找、常见安装路径。
def resolve_k6_executable() -> str:
    explicit = os.environ.get("K6_EXECUTABLE")
    if explicit:
        return explicit
    found = shutil.which("k6")
    if found:
        return found
    for candidate in (Path(r"H:\软件安装\k6\k6.exe"),):
        if candidate.exists():
            return str(candidate)
    return "k6"


# 实现当前模块的核心逻辑。
def require_aiohttp():
    try:
        return importlib.import_module("aiohttp")
    except ModuleNotFoundError as exc:
        raise RuntimeError("aiohttp is required for entity access benchmark helpers") from exc


@dataclass(frozen=True)
class BenchmarkConfig:
    base_url: str
    repo_id: str
    entity_prefix: str
    concurrency_values: list[int]
    total_duration_seconds: int
    measurement_start_offset_seconds: int
    measurement_window_seconds: int
    repo_ready_wait_seconds: float
    entity_pool_size: int
    cleanup: bool
    k6_executable: str
    report_output_dir: Path
    entity_data: str | None = None


# 构造当前场景所需的数据。
def build_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


# 返回当前场景的默认配置。
def default_run_dir(prefix: str, category: str | None = None, flat_category: bool = False) -> Path:
    # 优先使用环境变量 `API_TEST_PERF_OUTPUT` 以支持统一输出目录
    out_root = os.environ.get('API_TEST_PERF_OUTPUT')
    root = Path(out_root) if out_root else PROJECT_ROOT / 'performance' / 'outputs'
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    # 如果指定 category（例如 'entity'），将输出放到对应目录下：
    # <PROJECT_ROOT>/performance/outputs/<category>/<prefix>_<timestamp>
    if category:
        if flat_category:
            # 使用单层 category 目录：/outputs/<category>/<prefix>_<timestamp>
            return root / category / f"{prefix}_{timestamp}"
        # 默认：二层目录 /outputs/<category>/<prefix>/<prefix>_<timestamp>
        return root / category / prefix / f"{prefix}_{timestamp}"
    # 默认扁平化输出：<PROJECT_ROOT>/performance/outputs/<prefix>_<timestamp>
    return root / f"{prefix}_{timestamp}"


# 加载当前场景所需的数据或模板。
def load_entity_template(entity_data: str | None = None) -> dict[str, Any]:
    if not entity_data:
        return json.loads(json.dumps(SAMPLE_ENTITY, ensure_ascii=False))

    path = Path(entity_data)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read entity payload from {path}: {exc}") from exc


# 创建当前场景所需的资源或请求负载。
def create_entity_payload(entity_id: str, template: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = json.loads(json.dumps(template or SAMPLE_ENTITY, ensure_ascii=False))
    payload["id"] = entity_id
    return payload


# 生成当前场景使用的标识或资源。
def make_entity_id(prefix: str, index: int) -> str:
    if index < 0:
        raise ValueError("index must be >= 0")
    token = uuid.uuid4().hex
    return f"{prefix}-{index:08d}-{token}"


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


# 校验当前场景的配置或输入。
def validate_config(config: BenchmarkConfig) -> None:
    if not config.concurrency_values:
        raise ValueError("concurrency_values cannot be empty")
    if config.total_duration_seconds <= 0:
        raise ValueError("total_duration_seconds must be > 0")
    if config.measurement_start_offset_seconds < 0:
        raise ValueError("measurement_start_offset_seconds must be >= 0")
    if config.measurement_window_seconds <= 0:
        raise ValueError("measurement_window_seconds must be > 0")
    if config.measurement_start_offset_seconds + config.measurement_window_seconds > config.total_duration_seconds:
        raise ValueError("measurement window must fit within total duration")
    if config.entity_pool_size <= 0:
        raise ValueError("entity_pool_size must be > 0")


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
        },
        "summary": {
            "total_failure_count": len(measured_failure_events),
            "concurrency_with_failures": sorted({int(item["concurrency"]) for item in measured_failure_events}) if measured_failure_events else [],
            "error_kind_counts": dict(error_kind_counts),
            "status_counts": dict(status_counts),
        },
        "failures": normalize_serializable(measured_failure_events),
    }


# 渲染当前场景的图表或报告。
def render_final_markdown_report(
    summary: dict[str, Any],
    failure_summary: dict[str, Any],
    *,
    report_title: str,
    report_filename: str,
    endpoint_method: str,
) -> str:
    phase_metrics = summary.get("phase_metrics", [])
    metric_sections: list[str] = []
    for metric in phase_metrics:
        metric_sections.append(
            "\n".join(
                [
                    f"### 并发 {metric['concurrency']}",
                    "",
                    "| 指标 | 值 |",
                    "| --- | --- |",
                    f"| 总请求数 | {metric['total_requests']} |",
                    f"| 成功数 | {metric['success_count']} |",
                    f"| 失败数 | {metric['failure_count']} |",
                    f"| 成功率 | {metric['success_rate']}% |",
                    f"| 错误率 | {metric['error_rate']}% |",
                    f"| QPS | {metric['throughput_rps']} |",
                    f"| P50 | {metric['latency_p50_ms']} |",
                    f"| P95 | {metric['latency_p95_ms']} |",
                    f"| P99 | {metric['latency_p99_ms']} |",
                    f"| Avg | {metric['latency_avg_ms']} |",
                    f"| Max | {metric['latency_max_ms']} |",
                    f"| Timeout | {metric['timeout_count']} |",
                    f"| Conn Error | {metric['connection_error_count']} |",
                ]
            )
        )
    metrics_markdown = "\n\n".join(metric_sections) if metric_sections else "暂无并发指标数据。"

    inflection = summary.get("inflection_analysis", {})
    return f"""# {report_title}

## 测试目标

- 验证 `{endpoint_method}` 在不同并发梯度下的正式窗口性能表现。

## 测试环境配置

- 生成时间：{summary['generated_at']}
- Base URL：`{summary['base_url']}`
- Endpoint：`{endpoint_method} {summary['endpoint']}`
- Fixed Repo：`{summary['endpoint'].split('/')[2] if '/' in summary['endpoint'] else '3kwfacerepo'}`
- Entity Pool Size：`{summary.get('entity_pool_size')}`
- Concurrency Values：`{summary['concurrency_values']}`

## 测试方法说明

- 架构：`Python orchestration + k6 execution + Python reporting`
- 使用 `3kwfacerepo`/`1Efacerepo`
- 正式指标按请求开始时间落窗统计

## 35 秒连续测试窗口说明

- 总时长：`{summary['total_duration_seconds']}s`
- 连续预热/稳定段：前 `{summary['measurement_start_offset_seconds']}s`
- 正式统计窗口：后 `{summary['measurement_window_seconds']}s`
- 正式指标仅来自正式统计窗口，不采用整轮 35 秒平均值

## 各并发梯度核心指标表

{metrics_markdown}

## 性能拐点分析

- QPS 平台点：{inflection.get('qps_plateau_concurrency')}
- P95 上升点：{inflection.get('latency_growth_concurrency')}
- 错误率上升点：{inflection.get('error_growth_concurrency')}
- 稳定性劣化点：{inflection.get('stability_degradation_concurrency')}
- 结论：{inflection.get('narrative')}

## 失败请求摘要

- 总失败数：{failure_summary.get('total_failure_count', 0)}
- 详细失败响应体见：`failures.json`

## 产物索引

- `{report_filename}`
- `failures.json`
"""


# 写入当前场景输出文件。
def write_report_bundle(
    summary: dict[str, Any],
    failures_payload: dict[str, Any],
    report_path: Path,
    *,
    report_title: str,
    endpoint_method: str,
) -> Path:
    output_dir = report_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "failures.json").write_text(json.dumps(normalize_serializable(failures_payload), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = render_final_markdown_report(
        summary,
        failures_payload.get("summary", {}),
        report_title=report_title,
        report_filename=report_path.name,
        endpoint_method=endpoint_method,
    )
    report_path.write_text(markdown, encoding="utf-8")
    return report_path


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


# 解析当前场景生成的事件或日志。
def parse_k6_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        events.append(json.loads(raw))
    return events


# 解析当前场景生成的事件或日志。
def parse_k6_console_events(output: str, marker: str) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for line in output.splitlines():
        if marker not in line:
            continue
        payload = line.split(marker, 1)[1]
        event = _decode_embedded_k6_json(payload)
        if event is not None:
            parsed.append(event)
    return parsed


# 内部辅助函数，封装当前模块的局部逻辑。
def _build_k6_environment(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    for key in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
        env.pop(key, None)
    if extra_env:
        env.update(extra_env)
    return env


# 实现当前模块的核心逻辑。
async def send_json_request_async(
    session: Any,
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


# 内部辅助函数，封装当前模块的局部逻辑。
def _unique_entity_ids(prefix: str, count: int) -> list[str]:
    return [make_entity_id(prefix, index) for index in range(count)]


# 构造当前场景所需的数据。
def build_entity_pool_file(entity_ids: list[str], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    pool_path = output_dir / "entity_pool.json"
    pool_path.write_text(json.dumps(entity_ids, ensure_ascii=False, indent=2), encoding="utf-8")
    return pool_path


# 内部辅助函数，封装当前模块的局部逻辑。
def _build_k6_script_content(
    *,
    endpoint_builder: str,
    concurrency: int,
    total_duration_seconds: int,
    timeout: int,
    marker: str,
    operation: str,
    pool_path: Path,
) -> str:
    return f"""
import http from 'k6/http';
import exec from 'k6/execution';

const entityIds = JSON.parse(open('{pool_path.as_posix()}'));
const endpointBuilder = {endpoint_builder};

export const options = {{
  scenarios: {{
    entity_access: {{
      executor: 'constant-vus',
      vus: {concurrency},
      duration: '{total_duration_seconds}s',
    }},
  }},
  summaryTrendStats: ['avg', 'min', 'med', 'p(95)', 'p(99)', 'max'],
}};

function appendEvent(event) {{
  console.log('{marker}' + JSON.stringify(event));
}}

export default function () {{
  const index = exec.scenario.iterationInTest % entityIds.length;
  const entityId = entityIds[index];
  const endpoint = endpointBuilder(entityId);
  const started = Date.now();
  const response = http.request('{operation.upper()}', endpoint, null, {{
    headers: {{ 'Content-Type': 'application/json' }},
    timeout: '{timeout}s',
  }});
  const ended = Date.now();
  const body = response.body || '';
  appendEvent({{
    relative_start_s: started / 1000,
    relative_end_s: ended / 1000,
    concurrency: {concurrency},
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
    concurrency: int,
    operation: str,
    marker: str,
    entity_pool: list[str],
) -> dict[str, Path]:
    runtime_dir = Path(tempfile.mkdtemp(prefix=f"entity-access-k6-{operation}-{concurrency}-"))
    script_path = runtime_dir / f"entity_{operation}_runtime.js"
    pool_path = build_entity_pool_file(entity_pool, runtime_dir)
    events_path = runtime_dir / "events.jsonl"
    events_path.touch()
    endpoint_builder = f"(entityId) => `{build_url(config.base_url, f'/repositories/{config.repo_id}/entities/')}${{entityId}}`"
    script_path.write_text(
        _build_k6_script_content(
            endpoint_builder=endpoint_builder,
            concurrency=concurrency,
            total_duration_seconds=config.total_duration_seconds,
            timeout=config.total_duration_seconds,
            marker=marker,
            operation=operation,
            pool_path=pool_path,
        ),
        encoding="utf-8",
    )
    return {
        "runtime_dir": runtime_dir,
        "script_path": script_path,
        "events_path": events_path,
        "pool_path": pool_path,
    }


# 执行当前场景的核心流程。
def run_k6_for_concurrency(
    config: BenchmarkConfig,
    *,
    concurrency: int,
    runtime_files: dict[str, Path],
) -> subprocess.CompletedProcess[str]:
    env = _build_k6_environment({
        "ENTITY_ACCESS_EVENTS_PATH": str(runtime_files["events_path"]),
        "ENTITY_ACCESS_REPO_ID": config.repo_id,
    })
    command = [config.k6_executable, "run", str(runtime_files["script_path"])]
    return subprocess.run(command, capture_output=True, text=True, check=False, env=env)


_ORIGINAL_RUN_K6_FOR_CONCURRENCY = run_k6_for_concurrency


# 内部辅助函数，封装当前模块的局部逻辑。
def _cleanup_runtime_files(runtime_files: dict[str, Path]) -> None:
    runtime_dir = runtime_files.get("runtime_dir")
    if runtime_dir and runtime_dir.exists():
        shutil.rmtree(runtime_dir, ignore_errors=True)


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
def _filter_events_for_current_run(events: list[dict[str, Any]], *, repo_id: str, concurrency: int) -> list[dict[str, Any]]:
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


# 执行当前场景的核心流程。
def run_k6_for_concurrency_with_progress(
    config: BenchmarkConfig,
    *,
    concurrency: int,
    runtime_files: dict[str, Path],
) -> subprocess.CompletedProcess[str]:
    patched_target = run_k6_for_concurrency
    if patched_target is not _ORIGINAL_RUN_K6_FOR_CONCURRENCY:
        return patched_target(config, concurrency=concurrency, runtime_files=runtime_files)

    process = subprocess.Popen(
        [config.k6_executable, "run", str(runtime_files["script_path"])],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_build_k6_environment({
            "ENTITY_ACCESS_EVENTS_PATH": str(runtime_files["events_path"]),
            "ENTITY_ACCESS_REPO_ID": config.repo_id,
        }),
    )
    progress_thread = threading.Thread(
        target=_emit_measured_progress_until_complete,
        kwargs={
            "process": process,
            "repo_id": config.repo_id,
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
    return subprocess.CompletedProcess([config.k6_executable, "run", str(runtime_files["script_path"])], process.returncode, stdout, stderr)


# 预置当前场景所需的数据。
async def seed_entities_async(
    base_url: str,
    timeout: int,
    insecure: bool,
    repo_id: str,
    entity_ids: list[str],
    template: dict[str, Any],
    session: Any,
) -> None:
    endpoint = build_url(base_url, f"/repositories/{repo_id}/entities")
    print(f"URL:{endpoint}")
    for entity_id in entity_ids:
        payload = create_entity_payload(entity_id, template)
        status, body = await send_json_request_async(
            session,
            method="POST",
            url=endpoint,
            timeout=timeout,
            insecure=insecure,
            payload=payload,
        )
        if status is None or not (200 <= status < 300):
            raise RuntimeError(f"Failed to seed entity {entity_id}: {status}, body={body}")


# 内部辅助函数，封装当前模块的局部逻辑。
def _make_entity_access_summary(
    *,
    config: BenchmarkConfig,
    endpoint: str,
    phase_metrics: list[dict[str, Any]],
    inflection: dict[str, Any],
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": config.base_url,
        "endpoint": endpoint,
        "concurrency_values": list(config.concurrency_values),
        "total_duration_seconds": config.total_duration_seconds,
        "measurement_start_offset_seconds": config.measurement_start_offset_seconds,
        "measurement_window_seconds": config.measurement_window_seconds,
        "entity_pool_size": config.entity_pool_size,
        "phase_metrics": phase_metrics,
        "inflection_analysis": inflection,
        "output_dir": str(config.report_output_dir),
    }


# 内部辅助函数，封装当前模块的局部逻辑。
async def _run_entity_access_benchmark_async(
    config: BenchmarkConfig,
    *,
    operation: str,
    endpoint: str,
    report_title: str,
    report_filename: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    aiohttp = require_aiohttp()
    entity_template = load_entity_template(config.entity_data)

    phase_metrics: list[dict[str, Any]] = []
    all_measured_failures: list[dict[str, Any]] = []
    connector = aiohttp.TCPConnector(limit=max(config.concurrency_values) * 2, limit_per_host=max(config.concurrency_values) * 2)
    timeout_config = aiohttp.ClientTimeout(total=max(config.total_duration_seconds, DEFAULT_TIMEOUT))

    async with aiohttp.ClientSession(timeout=timeout_config, connector=connector) as session:
        try:
            for index, concurrency in enumerate(config.concurrency_values, start=1):
                entity_ids = _unique_entity_ids(f"{config.entity_prefix}-{index}", config.entity_pool_size)
                print_step("entity-seed", f"repo={config.repo_id} seeding {len(entity_ids)} entities for {operation}")
                await seed_entities_async(
                    config.base_url,
                    config.total_duration_seconds,
                    False,
                    config.repo_id,
                    entity_ids,
                    entity_template,
                    session,
                )

                print_step("repo-ready", f"repo={config.repo_id} waiting {config.repo_ready_wait_seconds:.1f}s for initialization")
                print_step("repo-ready", f"repo={config.repo_id} ready")
                print_step("k6-start", f"repo={config.repo_id} concurrency={concurrency} total={config.total_duration_seconds}s | first {config.measurement_start_offset_seconds}s warmup/settle not counted")

                runtime_files = build_k6_runtime_files(
                    config,
                    concurrency=concurrency,
                    operation=operation,
                    marker="__ENTITY_ACCESS_K6_EVENT__",
                    entity_pool=entity_ids,
                )
                try:
                    completed = run_k6_for_concurrency_with_progress(
                        config,
                        concurrency=concurrency,
                        runtime_files=runtime_files,
                    )
                    if completed.returncode != 0:
                        raise RuntimeError(f"k6 failed for concurrency {concurrency}: {completed.stderr.strip()}")

                    parsed_events = parse_k6_console_events(f"{completed.stdout}\n{completed.stderr}", "__ENTITY_ACCESS_K6_EVENT__")
                    runtime_files["events_path"].write_text(
                        "\n".join(json.dumps(item, ensure_ascii=False) for item in parsed_events),
                        encoding="utf-8",
                    )
                    events = parse_k6_events(runtime_files["events_path"])
                    current_run_events = _filter_events_for_current_run(events, repo_id=config.repo_id, concurrency=concurrency)
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
                                "repo_id": item.get("repo_id", config.repo_id),
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

            inflection = analyze_performance_inflection(phase_metrics)
            summary = _make_entity_access_summary(
                config=config,
                endpoint=endpoint,
                phase_metrics=phase_metrics,
                inflection=inflection,
            )
            summary["entity_payload_size_bytes"] = estimate_payload_size_bytes(create_entity_payload("sample", entity_template))
            failures_payload = build_failures_payload(summary, all_measured_failures)
            write_report_bundle(
                summary,
                failures_payload,
                config.report_output_dir / report_filename,
                report_title=report_title,
                endpoint_method=operation.upper(),
            )
            return summary, failures_payload
        finally:
            if config.cleanup:
                await asyncio.sleep(0)


# 执行当前场景的核心流程。
def run_entity_access_benchmark(
    config: BenchmarkConfig,
    *,
    operation: str,
    endpoint: str,
    report_title: str,
    report_filename: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_config(config)
    return asyncio.run(
        _run_entity_access_benchmark_async(
            config,
            operation=operation,
            endpoint=endpoint,
            report_title=report_title,
            report_filename=report_filename,
        )
    )
