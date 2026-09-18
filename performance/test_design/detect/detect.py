"""Detect 接口性能测试入口（Python orchestration + k6 execution）。"""

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
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_resolved = Path(__file__).resolve()
PROJECT_ROOT = _resolved.parents[3]
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))
    
from API_TEST.performance.config.config import DEFAULT_DETECT_URL
from API_TEST.performance.data.detect.detect import (
    SAMPLE_DETECT,
    SAMPLE_DETECT_FACE,
    SAMPLE_DETECT_FILE,
    SAMPLE_DETECT_FILE_FACE,
    SAMPLE_DETECT_FILE_MULTI,
    SAMPLE_DETECT_MULTI,
)
from API_TEST.performance.test_design.common.entity_access import default_run_dir as common_default_run_dir

DEFAULT_CONCURRENCY_VALUES = [8, 16, 32]
# DEFAULT_CONCURRENCY_VALUES = [1]
DEFAULT_TIMEOUT = 60
DEFAULT_TOTAL_DURATION_SECONDS = 200
DEFAULT_MEASUREMENT_START_OFFSET_SECONDS = 20
DEFAULT_MEASUREMENT_WINDOW_SECONDS = 180
# DEFAULT_TYPES = ["face"]
DEFAULT_PAYLOAD_KINDS = ["image", "file"]
# 场景：type=all（少目标 / 多目标各一组）与 type=face（单个face）；不再跑 vehicle
DEFAULT_TYPES = ["all", "face"]
# 样本组标识 → 报告展示名（与 performance/data/detect/detect.py 中的三组样本一一对应）
SAMPLE_GROUP_LABELS = {
    "single": "单张人脸+1非机动车+2人体（单目标）",
    "multi": "多个目标",
    "face": "单个face",
}
# 三组样本 × 目标 type：前两组用于 type=all（少目标 / 多目标），第三组用于 type=face
# 元组含义：(type, 样本组, case_id 前缀)
DEFAULT_SCENARIOS = [
    ("all", "single", "all-single"),
    ("all", "multi", "all-multi"),
    ("face", "face", "face"),
]
DEFAULT_PROGRESS_UPDATE_SECONDS = 1.0


@dataclass(frozen=True)
class BenchmarkConfig:
    base_url: str
    concurrency_values: list[int]
    total_duration_seconds: int
    measurement_start_offset_seconds: int
    measurement_window_seconds: int
    timeout: int
    k6_executable: str
    report_output_dir: Path
    types: list[str]
    payload_kinds: list[str]
    detect_data: str | None = None


# 实现当前模块的核心逻辑。
def require_aiohttp():
    try:
        return importlib.import_module("aiohttp")
    except ModuleNotFoundError as exc:
        raise RuntimeError("aiohttp is required for detect benchmark helpers") from exc


# 返回当前场景的默认配置。
def default_run_dir(prefix: str = "detect") -> Path:
    # 优先使用环境变量 `API_TEST_PERF_OUTPUT` 以支持统一输出目录
    out_root = os.environ.get('API_TEST_PERF_OUTPUT')
    root = Path(out_root) if out_root else Path('/home/wx/API_TEST/performance/outputs')
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    # 扁平化输出：/home/wx/API_TEST/performance/outputs/<prefix>_<timestamp>
    return root / f"{prefix}_{timestamp}"


# 加载当前场景所需的数据或模板。
def load_detect_template(detect_data: str | None = None) -> dict[str, Any]:
    if not detect_data:
        return deepcopy(SAMPLE_DETECT)

    path = Path(detect_data)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read detect payload from {path}: {exc}") from exc


# 构造当前场景所需的数据。
def build_default_config() -> BenchmarkConfig:
    return BenchmarkConfig(
        base_url=DEFAULT_DETECT_URL,
        concurrency_values=list(DEFAULT_CONCURRENCY_VALUES),
        total_duration_seconds=DEFAULT_TOTAL_DURATION_SECONDS,
        measurement_start_offset_seconds=DEFAULT_MEASUREMENT_START_OFFSET_SECONDS,
        measurement_window_seconds=DEFAULT_MEASUREMENT_WINDOW_SECONDS,
        timeout=DEFAULT_TIMEOUT,
        k6_executable="k6",
        report_output_dir=common_default_run_dir("detect", category="detect", flat_category=True),
        types=list(DEFAULT_TYPES),
        payload_kinds=list(DEFAULT_PAYLOAD_KINDS),
        detect_data=None,
    )


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
    if not config.types:
        raise ValueError("types cannot be empty")
    allowed_types = {"all", "face", "vehicle"}
    invalid_types = [type_name for type_name in config.types if type_name not in allowed_types]
    if invalid_types:
        raise ValueError(f"types contains unsupported values: {invalid_types}")
    if not config.payload_kinds:
        raise ValueError("payload_kinds cannot be empty")
    allowed_payload_kinds = {"image", "file"}
    invalid_payload_kinds = [kind for kind in config.payload_kinds if kind not in allowed_payload_kinds]
    if invalid_payload_kinds:
        raise ValueError(f"payload_kinds contains unsupported values: {invalid_payload_kinds}")


# 构造当前场景所需的数据。
def build_benchmark_cases(config: BenchmarkConfig) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for type_name, sample_group, case_prefix in DEFAULT_SCENARIOS:
        if type_name not in config.types:
            continue
        for payload_kind in config.payload_kinds:
            cases.append(
                {
                    "case_id": f"{case_prefix}-{payload_kind}",
                    "type": type_name,
                    "payload_kind": payload_kind,
                    "sample_group": sample_group,
                    "label": (
                        f"type={type_name} | payload={payload_kind} | "
                        f"sample={SAMPLE_GROUP_LABELS.get(sample_group, sample_group)}"
                    ),
                    "concurrency_values": list(config.concurrency_values),
                }
            )
    return cases


# 构造当前场景所需的数据。
def build_detect_payload(
    type_name: str,
    template: dict[str, Any] | None = None,
    *,
    payload_kind: str = "image",
    sample_group: str = "single",
) -> dict[str, Any]:
    # 三组样本：(样本组, 载荷类型) → 模板；各组都提供 url(image)/file 两种载荷
    sample_templates = {
        ("single", "image"): SAMPLE_DETECT,
        ("single", "file"): SAMPLE_DETECT_FILE,
        ("multi", "image"): SAMPLE_DETECT_MULTI,
        ("multi", "file"): SAMPLE_DETECT_FILE_MULTI,
        ("face", "image"): SAMPLE_DETECT_FACE,
        ("face", "file"): SAMPLE_DETECT_FILE_FACE,
    }
    base = sample_templates.get((sample_group, payload_kind))
    if base is None:
        # 未知样本组时回退到旧行为（保持向后兼容）
        base = (template or SAMPLE_DETECT) if payload_kind != "file" else SAMPLE_DETECT_FILE
    payload = deepcopy(base)
    payload["type"] = type_name
    return payload


# 内部辅助函数，封装当前模块的局部逻辑。
def _build_detect_url(base_url: str, type_name: str) -> str:
    return f"{base_url.rstrip('/')}/ai/detect/{type_name}"


# 渲染当前场景的图表或报告。
def render_progress_bar(value: float, total: float, width: int = 24) -> str:
    ratio = 0.0 if total <= 0 else max(0.0, min(1.0, value / total))
    filled = max(0, min(width, int(ratio * width)))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {ratio * 100:5.1f}%"


# 输出当前场景的进度信息。
def emit_measured_progress_line(*, current_seconds: float, total_seconds: float, case_id: str, concurrency: int, done: bool = False) -> None:
    elapsed = min(current_seconds, total_seconds)
    status = f"case={case_id} concurrency={concurrency} measured | {render_progress_bar(elapsed, total_seconds)} {elapsed:5.1f}s/{total_seconds:5.1f}s"
    if done:
        sys.stdout.write(f"\r[INFO] PHASE_PROGRESS     {status} ✅")
        sys.stdout.flush()
        return
    sys.stdout.write(f"\r[INFO] PHASE_PROGRESS     {status}")
    sys.stdout.flush()


# 打印当前场景的说明或统计结果。
def print_case_metric_summary(*, case_label: str, metric: dict[str, Any]) -> None:
    summary_line = (
        "\n[INFO] CONCURRENCY_RESULT "
        f"case={case_label} | "
        f"concurrency={metric['concurrency']} | "
        f"total_requests={metric['total_requests']} | "
        f"success_count={metric['success_count']} | "
        f"failure_count={metric['failure_count']} | "
        f"success_rate={metric['success_rate']}% | "
        f"error_rate={metric['error_rate']}% | "
        f"qps={metric['throughput_rps']} | "
        f"p50={metric.get('latency_p50_ms')}ms | "
        f"p95={metric.get('latency_p95_ms')}ms | "
        f"p99={metric.get('latency_p99_ms')}ms | "
        f"avg={metric.get('latency_avg_ms')}ms | "
        f"max={metric.get('latency_max_ms')}ms | "
        f"timeout_count={metric.get('timeout_count', 0)} | "
        f"connection_error_count={metric.get('connection_error_count', 0)}"
    )
    print(summary_line)


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


# 过滤当前场景需要保留的数据。
def filter_measured_window_events(
    events: list[dict[str, Any]],
    *,
    measurement_start_offset_seconds: int,
    measurement_window_seconds: int,
) -> list[dict[str, Any]]:
    measured_end = measurement_start_offset_seconds + measurement_window_seconds
    return [
        item
        for item in events
        if measurement_start_offset_seconds <= float(item.get("relative_start_s", -1)) < measured_end
    ]


# 汇总当前场景的统计结果。
def summarize_measured_events(
    events: list[dict[str, Any]],
    *,
    case_id: str,
    concurrency: int,
    measurement_window_seconds: int,
) -> dict[str, Any]:
    total_requests = len(events)
    success_count = sum(1 for item in events if item.get("ok"))
    failure_count = total_requests - success_count
    durations = [float(item.get("duration_ms", 0.0)) for item in events if item.get("duration_ms") is not None]
    timeout_count = sum(1 for item in events if item.get("error_kind") == "timeout")
    connection_error_count = sum(1 for item in events if item.get("error_kind") == "connection_error")
    return {
        "case_id": case_id,
        "concurrency": concurrency,
        "total_requests": total_requests,
        "success_count": success_count,
        "failure_count": failure_count,
        "success_rate": round((success_count / total_requests) * 100, 2) if total_requests else 0.0,
        "error_rate": round((failure_count / total_requests) * 100, 2) if total_requests else 0.0,
        "throughput_rps": round(total_requests / measurement_window_seconds, 3) if measurement_window_seconds > 0 else 0.0,
        "latency_p50_ms": percentile(durations, 50),
        "latency_p95_ms": percentile(durations, 95),
        "latency_p99_ms": percentile(durations, 99),
        "latency_avg_ms": round(sum(durations) / len(durations), 3) if durations else None,
        "latency_max_ms": round(max(durations), 3) if durations else None,
        "timeout_count": timeout_count,
        "connection_error_count": connection_error_count,
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


# 实现当前模块的核心逻辑。
def normalize_serializable(data: Any) -> Any:
    if isinstance(data, (str, int, float, bool)) or data is None:
        return data
    if isinstance(data, dict):
        return {str(key): normalize_serializable(value) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        return [normalize_serializable(item) for item in data]
    return str(data)


# 分析当前场景的指标变化。
def analyze_performance_inflection(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    all_metrics = [metric for case in case_results for metric in case.get("metrics", [])]
    qps_plateau_at = None
    latency_growth_at = None
    error_growth_at = None
    stability_degradation_at = None

    for previous, current in zip(all_metrics, all_metrics[1:]):
        previous_qps = float(previous.get("throughput_rps") or 0.0)
        current_qps = float(current.get("throughput_rps") or 0.0)
        if previous_qps > 0 and current_qps <= previous_qps * 1.10:
            qps_plateau_at = {"case_id": current.get("case_id"), "concurrency": current.get("concurrency")}
            break

    for previous, current in zip(all_metrics, all_metrics[1:]):
        previous_p95 = float(previous.get("latency_p95_ms") or 0.0)
        current_p95 = float(current.get("latency_p95_ms") or 0.0)
        if previous_p95 > 0 and current_p95 >= previous_p95 * 1.5:
            latency_growth_at = {"case_id": current.get("case_id"), "concurrency": current.get("concurrency")}
            break

    for metric in all_metrics:
        if float(metric.get("error_rate") or 0.0) >= 5.0:
            error_growth_at = {"case_id": metric.get("case_id"), "concurrency": metric.get("concurrency")}
            break

    for metric in all_metrics:
        if float(metric.get("success_rate") or 100.0) < 95.0:
            stability_degradation_at = {"case_id": metric.get("case_id"), "concurrency": metric.get("concurrency")}
            break

    narrative_parts: list[str] = []
    if qps_plateau_at is not None:
        narrative_parts.append(f"吞吐在 {qps_plateau_at['case_id']} / 并发 {qps_plateau_at['concurrency']} 左右开始接近平台")
    if latency_growth_at is not None:
        narrative_parts.append(f"P95 延迟在 {latency_growth_at['case_id']} / 并发 {latency_growth_at['concurrency']} 开始明显上升")
    if error_growth_at is not None:
        narrative_parts.append(f"错误率在 {error_growth_at['case_id']} / 并发 {error_growth_at['concurrency']} 开始显著上升")
    if stability_degradation_at is not None:
        narrative_parts.append(f"稳定性在 {stability_degradation_at['case_id']} / 并发 {stability_degradation_at['concurrency']} 开始下降")
    if not narrative_parts:
        narrative_parts.append("当前数据尚未呈现明确的吞吐拐点")

    return {
        "qps_plateau_at": qps_plateau_at,
        "latency_growth_at": latency_growth_at,
        "error_growth_at": error_growth_at,
        "stability_degradation_at": stability_degradation_at,
        "narrative": "；".join(narrative_parts),
    }


# 内部辅助函数，封装当前模块的局部逻辑。
def _format_report_number(value: Any, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


# 内部辅助函数，封装当前模块的局部逻辑。
def _format_report_int(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value)


# 内部辅助函数，封装当前模块的局部逻辑。
def _format_report_latency(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{_format_report_number(value)} ms"


# 内部辅助函数，封装当前模块的局部逻辑。
def _format_report_percent(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{_format_report_number(value)}%"


# 内部辅助函数，封装当前模块的局部逻辑。
def _render_ascii_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(str(cell)))

    # 渲染当前场景的图表或报告。
    def render_row(cells: list[str]) -> str:
        return " | ".join(str(cell).ljust(widths[index]) for index, cell in enumerate(cells))

    separator = " | ".join("-" * width for width in widths)
    return "\n".join([render_row(headers), separator, *(render_row(row) for row in rows)])


# 内部辅助函数，封装当前模块的局部逻辑。
def _render_case_report_table(case: dict[str, Any]) -> str:
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
    for metric in case.get("metrics", []):
        rows.append(
            [
                _format_report_int(metric.get("concurrency")),
                _format_report_int(metric.get("total_requests")),
                _format_report_int(metric.get("success_count")),
                _format_report_int(metric.get("failure_count")),
                _format_report_percent(metric.get("success_rate")),
                _format_report_percent(metric.get("error_rate")),
                _format_report_number(metric.get("throughput_rps")),
                _format_report_latency(metric.get("latency_p50_ms")),
                _format_report_latency(metric.get("latency_avg_ms")),
                _format_report_latency(metric.get("latency_p95_ms")),
                _format_report_latency(metric.get("latency_p99_ms")),
                _format_report_latency(metric.get("latency_max_ms")),
                _format_report_int(metric.get("timeout_count", 0)),
                _format_report_int(metric.get("connection_error_count", 0)),
            ]
        )

    if not rows:
        rows.append(["N/A"] * len(headers))
    return _render_ascii_table(headers, rows)


# 渲染当前场景的图表或报告。
def render_final_markdown_report(summary: dict[str, Any], failure_summary: dict[str, Any]) -> str:
    inflection = summary.get("inflection_analysis", {})
    case_sections = []
    for case in summary.get("case_results", []):
        case_sections.append(
            "\n".join(
                [
                    f"### Case {case.get('case_id')}",
                    "",
                    f"- 参数组合：`{case.get('label', 'template-defaults')}`",
                    "",
                    _render_case_report_table(case),
                ]
            )
        )

    return "\n".join(
        [
            "# Detect 接口性能测试报告",
            "",
            "## 测试目标",
            "",
            "- 验证 `POST /ai/detect/{type}` 在 `type × payload_kind × 样本组（单张人脸/多个目标）`"
            " 组合下的正式窗口性能表现。",
            "",
            "## 测试环境配置",
            "",
            f"- 生成时间：{summary.get('generated_at', 'N/A')}",
            f"- Base URL：`{summary.get('base_url', 'N/A')}`",
            f"- 目标接口：`{summary.get('endpoint', '/ai/detect/{type}')}`",
            f"- 测量窗口：前 {summary.get('measurement_start_offset_seconds', 'N/A')}s 预热 / 后 {summary.get('measurement_window_seconds', 'N/A')}s 统计",
            f"- Case 数量：{len(summary.get('case_results', []))}",
            f"- 失败请求数：{failure_summary.get('total_failure_count', 0)}",
            "",
            "## Case 结果",
            "",
            *(case_sections or ["暂无 case 结果。"]),
            "",
            "## 性能拐点分析",
            "",
            f"- 结论：{inflection.get('narrative', '当前数据尚未呈现明确的吞吐拐点')}",
            "",
            "## 失败请求摘要",
            "",
            f"- 总失败数：{failure_summary.get('total_failure_count', 0)}",
            "- 详细失败响应体见：`failures.json`",
            "",
            "## 产物索引",
            "",
            "- `detect_report.md`",
            "- `failures.json`",
        ]
    )


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
def _normalize_k6_relative_times(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not events:
        return []
    starts = [float(event["relative_start_s"]) for event in events if event.get("relative_start_s") is not None]
    if not starts:
        return [dict(event) for event in events]

    base_start = min(starts)
    needs_rebase = base_start > 1000
    normalized: list[dict[str, Any]] = []
    for event in events:
        cloned = dict(event)
        start_s = float(event.get("relative_start_s", 0.0))
        end_s = float(event.get("relative_end_s", start_s))
        if needs_rebase:
            cloned["relative_start_s"] = round(start_s - base_start, 6)
            cloned["relative_end_s"] = round(end_s - base_start, 6)
        else:
            cloned["relative_start_s"] = round(start_s, 6)
            cloned["relative_end_s"] = round(end_s, 6)

        response_body = cloned.get("response_body")
        if isinstance(response_body, str) and response_body.strip():
            try:
                cloned["response_body"] = json.loads(response_body)
            except json.JSONDecodeError:
                pass
        normalized.append(cloned)

    return normalized


# 内部辅助函数，封装当前模块的局部逻辑。
def _build_k6_environment(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    for key in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
        env.pop(key, None)
    if extra_env:
        env.update(extra_env)
    return env


# 内部辅助函数，封装当前模块的局部逻辑。
def _build_k6_script_content(*, base_url: str, case_type: str, concurrency: int, total_duration_seconds: int, timeout: int, marker: str, payload_path: Path) -> str:
    return f"""
import http from 'k6/http';
import exec from 'k6/execution';

const payload = JSON.parse(open('{payload_path.as_posix()}'));
const endpoint = '{base_url.rstrip('/')}/ai/detect/{case_type}';

export const options = {{
  scenarios: {{
    detect_case: {{
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
  const started = Date.now();
  const response = http.request('POST', endpoint, JSON.stringify(payload), {{
    headers: {{ 'Content-Type': 'application/json' }},
    timeout: '{timeout}s',
  }});
  const ended = Date.now();
  const body = response.body || '';
  appendEvent({{
    case_type: '{case_type}',
    relative_start_s: started / 1000,
    relative_end_s: ended / 1000,
    concurrency: {concurrency},
    status: response.status,
    duration_ms: response.timings.duration,
    ok: response.status >= 200 && response.status < 300,
    error_kind: null,
    error_message: null,
    response_headers: response.status >= 400 ? response.headers : null,
    response_body: response.status >= 400 ? body : null,
  }});
}}
""".strip()


# 构造当前场景所需的数据。
def build_k6_runtime_files(
    config: BenchmarkConfig,
    *,
    case_type: str,
    payload_kind: str,
    concurrency: int,
    sample_group: str = "single",
) -> dict[str, Path]:
    runtime_dir = Path(tempfile.mkdtemp(prefix=f"detect-k6-{case_type}-{sample_group}-{payload_kind}-{concurrency}-"))
    script_path = runtime_dir / f"detect_{case_type}_{sample_group}_{payload_kind}_runtime.js"
    payload_path = runtime_dir / "detect_payload.json"
    payload_path.write_text(
        json.dumps(
            build_detect_payload(
                case_type,
                load_detect_template(config.detect_data),
                payload_kind=payload_kind,
                sample_group=sample_group,
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    events_path = runtime_dir / "events.jsonl"
    events_path.touch()
    script_path.write_text(
        _build_k6_script_content(
            base_url=config.base_url,
            case_type=case_type,
            concurrency=concurrency,
            total_duration_seconds=config.total_duration_seconds,
            timeout=config.timeout,
            marker="__DETECT_K6_EVENT__",
            payload_path=payload_path,
        ),
        encoding="utf-8",
    )
    return {
        "runtime_dir": runtime_dir,
        "script_path": script_path,
        "events_path": events_path,
        "payload_path": payload_path,
    }


# 执行当前场景的核心流程。
def run_k6_for_concurrency_with_progress(config: BenchmarkConfig, *, case_id: str, concurrency: int, runtime_files: dict[str, Path]) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        [config.k6_executable, "run", str(runtime_files["script_path"])],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_build_k6_environment({"DETECT_CASE_ID": case_id}),
    )
    progress_thread = threading.Thread(
        target=_emit_measured_progress_until_complete,
        kwargs={
            "process": process,
            "case_id": case_id,
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


# 内部辅助函数，封装当前模块的局部逻辑。
def _emit_measured_progress_until_complete(
    process: subprocess.Popen[str] | None,
    *,
    case_id: str,
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
                case_id=case_id,
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
        case_id=case_id,
        concurrency=concurrency,
        done=True,
    )


# 实现当前模块的核心逻辑。
async def preflight_detect_case_async(
    base_url: str,
    timeout: int,
    case_type: str,
    session: Any,
    *,
    payload_kind: str,
    sample_group: str = "single",
) -> None:
    aiohttp = require_aiohttp()
    url = _build_detect_url(base_url, case_type)
    payload = build_detect_payload(
        case_type,
        load_detect_template(None),
        payload_kind=payload_kind,
        sample_group=sample_group,
    )
    try:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            if response.status >= 400:
                text = await response.text()
                raise RuntimeError(f"detect preflight failed for {case_type}: {response.status} - {text}")
    except aiohttp.ClientError as exc:
        raise RuntimeError(f"detect preflight failed for {case_type}: {exc}") from exc


# 内部辅助函数，封装当前模块的局部逻辑。
def _make_detect_summary(*, config: BenchmarkConfig, case_results: list[dict[str, Any]], inflection: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": config.base_url,
        "endpoint": "/ai/detect/{type}",
        "concurrency_values": list(config.concurrency_values),
        "total_duration_seconds": config.total_duration_seconds,
        "measurement_start_offset_seconds": config.measurement_start_offset_seconds,
        "measurement_window_seconds": config.measurement_window_seconds,
        "case_results": case_results,
        "inflection_analysis": inflection,
        "output_dir": str(config.report_output_dir),
    }


# 内部辅助函数，封装当前模块的局部逻辑。
def _cleanup_runtime_files(runtime_files: dict[str, Path]) -> None:
    runtime_dir = runtime_files.get("runtime_dir")
    if runtime_dir and runtime_dir.exists():
        shutil.rmtree(runtime_dir, ignore_errors=True)


# 内部辅助函数，封装当前模块的局部逻辑。
def _filter_events_for_current_case(events: list[dict[str, Any]], *, case_id: str, concurrency: int) -> list[dict[str, Any]]:
    filtered = [event for event in events if event.get("case_type") == case_id and int(event.get("concurrency", -1)) == concurrency]
    return filtered


# 内部辅助函数，封装当前模块的局部逻辑。
async def _run_detect_benchmark_async(config: BenchmarkConfig) -> tuple[dict[str, Any], dict[str, Any]]:
    aiohttp = require_aiohttp()
    case_results: list[dict[str, Any]] = []
    all_measured_failures: list[dict[str, Any]] = []
    connector = aiohttp.TCPConnector(limit=max(config.concurrency_values) * 2, limit_per_host=max(config.concurrency_values) * 2)
    timeout_config = aiohttp.ClientTimeout(total=max(config.total_duration_seconds, config.timeout))

    async with aiohttp.ClientSession(timeout=timeout_config, connector=connector) as session:
        for case in build_benchmark_cases(config):
            case_id = str(case["case_id"])
            case_type = str(case["type"])
            case_payload_kind = str(case["payload_kind"])
            case_sample_group = str(case.get("sample_group") or "single")
            print_step(
                "detect-case",
                f"type={case_type} payload={case_payload_kind} sample={case_sample_group} start",
            )
            await preflight_detect_case_async(
                config.base_url,
                config.timeout,
                case_type,
                session,
                payload_kind=case_payload_kind,
                sample_group=case_sample_group,
            )

            metrics: list[dict[str, Any]] = []
            for concurrency in config.concurrency_values:
                runtime_files = build_k6_runtime_files(
                    config,
                    case_type=case_type,
                    payload_kind=case_payload_kind,
                    sample_group=case_sample_group,
                    concurrency=concurrency,
                )
                try:
                    completed = run_k6_for_concurrency_with_progress(
                        config,
                        case_id=case_id,
                        concurrency=concurrency,
                        runtime_files=runtime_files,
                    )
                    if completed.returncode != 0:
                        raise RuntimeError(f"k6 failed for detect {case_type} concurrency {concurrency}: {completed.stderr.strip()}")

                    parsed_events = parse_k6_console_events(f"{completed.stdout}\n{completed.stderr}", "__DETECT_K6_EVENT__")
                    runtime_files["events_path"].write_text(
                        "\n".join(json.dumps(item, ensure_ascii=False) for item in parsed_events),
                        encoding="utf-8",
                    )
                    events = _normalize_k6_relative_times(parse_k6_events(runtime_files["events_path"]))
                    current_case_events = _filter_events_for_current_case(events, case_id=case_type, concurrency=concurrency)
                    measured_events = filter_measured_window_events(
                        current_case_events,
                        measurement_start_offset_seconds=config.measurement_start_offset_seconds,
                        measurement_window_seconds=config.measurement_window_seconds,
                    )
                    metric = summarize_measured_events(
                        measured_events,
                        case_id=case_id,
                        concurrency=concurrency,
                        measurement_window_seconds=config.measurement_window_seconds,
                    )
                    metrics.append(metric)
                    print_case_metric_summary(case_label=case_id, metric=metric)

                    for item in measured_events:
                        if item.get("ok"):
                            continue
                        all_measured_failures.append(
                            {
                                "case_id": case_id,
                                "type": case_type,
                                "payload_kind": case_payload_kind,
                                "sample_group": case_sample_group,
                                "concurrency": concurrency,
                                "status": item.get("status"),
                                "error_kind": item.get("error_kind"),
                                "error": item.get("error_message"),
                                "elapsed_ms": item.get("duration_ms"),
                                "response_headers": item.get("response_headers"),
                                "response_body": item.get("response_body"),
                            }
                        )
                finally:
                    _cleanup_runtime_files(runtime_files)

            case_results.append({"case_id": case_id, "type": case_type, "payload_kind": case_payload_kind, "label": case["label"], "metrics": metrics})

    inflection = analyze_performance_inflection(case_results)
    summary = _make_detect_summary(config=config, case_results=case_results, inflection=inflection)
    failures_payload = build_failures_payload(summary, all_measured_failures)
    write_report_bundle(summary, failures_payload, config.report_output_dir / "detect_report.md")
    return summary, failures_payload


# 写入当前场景输出文件。
def write_report_bundle(summary: dict[str, Any], failures_payload: dict[str, Any], report_path: Path) -> Path:
    output_dir = report_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "failures.json").write_text(json.dumps(normalize_serializable(failures_payload), ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(render_final_markdown_report(summary, failures_payload.get("summary", {})), encoding="utf-8")
    return report_path


# 执行当前场景的核心流程。
def run_detect_benchmark(config: BenchmarkConfig):
    validate_config(config)
    return asyncio.run(_run_detect_benchmark_async(config))


# 打印当前场景的说明或统计结果。
def print_step(label: str, detail: str) -> None:
    print(f"[INFO] {label.upper().replace('-', '_'):<18} {detail}")


# 程序入口，用于串起当前模块的执行流程。
def main() -> int:
    config = build_default_config()
    summary, _ = run_detect_benchmark(config)
    report_path = Path(summary["output_dir"]) / "detect_report.md"
    print(f"Report written to: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
