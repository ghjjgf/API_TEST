"""Search 基线 + 热点库混合负载性能测试统一入口。

本文件合并了原 search.py 与 search_hotspot.py：
- 复用 k6 执行、事件解析、指标统计和安全阀；
- 每个并发档先执行同 case 纯 search baseline，再执行 hotspot；
- hotspot 阶段持续 insert/delete，case 完成后清理遗留实体。
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter, deque
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_resolved = Path(__file__).resolve()
PROJECT_ROOT = _resolved.parents[3]
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

from API_TEST.performance.config.config import DEFAULT_BASE_URL
from API_TEST.performance.data.entity.entity import SAMPLE_ENTITY
from API_TEST.performance.data.search.search import SAMPLE_SEARCH
from API_TEST.performance.test_design.common import ascii_report
from API_TEST.performance.test_design.common.entity_access import (
    build_url,
    create_entity_payload,
    default_run_dir as common_default_run_dir,
    resolve_k6_executable,
    send_json_request_async,
)

DEFAULT_CONCURRENCY_VALUES = [32, 64, 128]
# DEFAULT_CONCURRENCY_VALUES = [128, 256]
# 单请求超时（秒）：服务端未配置读写超时时，缩短客户端超时可以把"请求挂死"快速暴露成失败事件，
# 而不是等 60s 才返回、落到统计窗口之外显示成"0 请求"。可用 SEARCH_REQUEST_TIMEOUT_SECONDS 覆盖。
DEFAULT_TIMEOUT = int(os.environ.get("SEARCH_REQUEST_TIMEOUT_SECONDS", "15"))

# ---- 压测安全阀（默认开启）----
# 每个并发档开始前做一次健康探测，不健康立即中止并落盘已有结果
DEFAULT_HEALTH_GATE_ENABLED = os.environ.get("SEARCH_HEALTH_GATE", "1").lower() not in ("0", "false", "no")
HEALTH_PROBE_TIMEOUT_SECONDS = float(os.environ.get("SEARCH_HEALTH_PROBE_TIMEOUT_SECONDS", "3"))
HEALTH_PROBE_PATH = os.environ.get("SEARCH_HEALTH_PROBE_PATH", "/internal/repositories/audit?active_only=true")
# 某一档并发完全没有返回事件（请求全部挂死）时立即中止
DEFAULT_ABORT_ON_ZERO_EVENTS = os.environ.get("SEARCH_ABORT_ON_ZERO_EVENTS", "1").lower() not in ("0", "false", "no")
# 某一档并发有请求但"零成功"（全部超时/失败）时立即中止：服务不可用时不再空跑整轮
DEFAULT_ABORT_ON_ZERO_SUCCESS = os.environ.get("SEARCH_ABORT_ON_ZERO_SUCCESS", "1").lower() not in ("0", "false", "no")
# 重载荷保护：max_candidates >= 阈值时，最高并发限制到 cap（cap=0 关闭）
DEFAULT_HEAVY_MAX_CANDIDATES = int(os.environ.get("SEARCH_HEAVY_MAX_CANDIDATES", "500"))
DEFAULT_HEAVY_CONCURRENCY_CAP = int(os.environ.get("SEARCH_HEAVY_CONCURRENCY_CAP", "512"))
DEFAULT_TOTAL_DURATION_SECONDS = 200
DEFAULT_MEASUREMENT_START_OFFSET_SECONDS = 20
DEFAULT_MEASUREMENT_WINDOW_SECONDS = 180
DEFAULT_REPOSITORIES_VALUES = [
    ["3kwfacerepo_test"],
    ["1Efacerepo"],
    ["5kwfacerepo"],
    ["3kwfacerepo_test", "1kwfacerepo_test"],
    ["1Efacerepo", "5kwfacerepo"],
]
DEFAULT_MAX_CANDIDATES_VALUES = [1, 20, 100, 500]
DEFAULT_INCLUDE_THRESHOLD_VALUES = [0.7]
# DEFAULT_REPOSITORIES_VALUES = [["3kwfacerepo"]]
# DEFAULT_MAX_CANDIDATES_VALUES = [1]
# DEFAULT_INCLUDE_THRESHOLD_VALUES = [0.5]
DEFAULT_LOCATION_ID_VALUES = [1]
DEFAULT_PROGRESS_UPDATE_SECONDS = 1.0


# 实现当前模块的核心逻辑。


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
    repositories_enabled: bool
    repositories_values: list[list[str]]
    max_candidates_enabled: bool
    max_candidates_values: list[int]
    include_threshold_enabled: bool
    include_threshold_values: list[float]
    location_id_enabled: bool
    location_id_values: list[int]
    search_data: str | None = None


# 返回当前场景的默认配置。
def default_run_dir(prefix: str = "search") -> Path:
    # 优先使用环境变量 `API_TEST_PERF_OUTPUT` 以支持统一输出目录
    out_root = os.environ.get('API_TEST_PERF_OUTPUT')
    root = Path(out_root) if out_root else PROJECT_ROOT / 'performance' / 'outputs'
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    # 扁平化输出：<PROJECT_ROOT>/performance/outputs/<prefix>_<timestamp>
    return root / f"{prefix}_{timestamp}"


# 构造当前场景所需的数据。
def build_default_config() -> BenchmarkConfig:
    return BenchmarkConfig(
        base_url=DEFAULT_BASE_URL,
        concurrency_values=list(DEFAULT_CONCURRENCY_VALUES),
        total_duration_seconds=DEFAULT_TOTAL_DURATION_SECONDS,
        measurement_start_offset_seconds=DEFAULT_MEASUREMENT_START_OFFSET_SECONDS,
        measurement_window_seconds=DEFAULT_MEASUREMENT_WINDOW_SECONDS,
        timeout=DEFAULT_TIMEOUT,
        k6_executable=resolve_k6_executable(),
        report_output_dir=common_default_run_dir("search", category="search", flat_category=True),
        # 参数
        repositories_enabled=True,
        repositories_values=deepcopy(DEFAULT_REPOSITORIES_VALUES),
        max_candidates_enabled=True,
        max_candidates_values=list(DEFAULT_MAX_CANDIDATES_VALUES),
        include_threshold_enabled=True,
        include_threshold_values=list(DEFAULT_INCLUDE_THRESHOLD_VALUES),
        location_id_enabled=False,
        location_id_values=list(DEFAULT_LOCATION_ID_VALUES),
    )


# 校验当前场景的配置或输入。


# 加载当前场景所需的数据或模板。


# 实现当前模块的核心逻辑。


# 构造当前场景所需的数据。


# 构造当前场景所需的数据。
def build_search_payload(
    *,
    template: dict[str, Any],
    repositories: list[str] | None = None,
    max_candidates: int | None = None,
    include_threshold: float | None = None,
    location_id: int | None = None,
) -> dict[str, Any]:
    payload = deepcopy(template)
    if repositories is not None:
        payload["repositories"] = list(repositories)
    if max_candidates is not None:
        payload["max_candidates"] = int(max_candidates)
    if include_threshold is not None:
        payload["include_threshold"] = float(include_threshold)
    if location_id is not None:
        payload["locations"] = [f"location-{int(location_id):03d}"]
        payload.pop("location_id", None)
    return payload


# 构造当前场景所需的数据。


# 收集当前场景所需的数据。


# 内部辅助函数，封装当前模块的局部逻辑。


# 确保当前场景依赖或状态满足要求。


# 打印当前场景的说明或统计结果。


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
        sys.stdout.write(f"\r[INFO] PHASE_PROGRESS     {status} ✅\n")
        sys.stdout.flush()
        return
    sys.stdout.write(f"\r[INFO] PHASE_PROGRESS     {status}")
    sys.stdout.flush()


# 探测被测 search 服务是否还活着：任何 HTTP 响应都算存活；超时/连接错误算不健康。
def probe_service_health(base_url: str, timeout: float = HEALTH_PROBE_TIMEOUT_SECONDS) -> tuple[bool, str]:
    url = f"{base_url.rstrip('/')}{HEALTH_PROBE_PATH}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return True, f"http={response.status}"
    except urllib.error.HTTPError as exc:
        # 还能返回 HTTP 状态码（哪怕 4xx/5xx）说明 HTTP 线程没有被耗尽
        return True, f"http={exc.code}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


# 计算某个 case 实际执行的并发档；重载荷自动裁剪最高并发，避免打满服务端线程池。


# 打印当前场景的说明或统计结果。


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


# 分析当前场景的指标变化。


# 构造当前场景所需的数据。


# 内部辅助函数，封装当前模块的局部逻辑。


# 内部辅助函数，封装当前模块的局部逻辑。


# 内部辅助函数，封装当前模块的局部逻辑。


# 内部辅助函数，封装当前模块的局部逻辑。


# 内部辅助函数，封装当前模块的局部逻辑。


# 内部辅助函数，封装当前模块的局部逻辑。


# 渲染当前场景的图表或报告。


# 解析 k6 控制台事件：兼容旧 JSON 行与新的紧凑字段行（每行体积小 3~5 倍）。
def _parse_k6_console_events(output: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in output.splitlines():
        payload = _extract_event_payload(line)
        if not payload:
            continue
        decoded = _parse_legacy_event_json(payload) if payload.startswith("{") else _parse_compact_event(payload)
        if decoded is not None:
            events.append(decoded)
    return events


# 从一行 k6 输出里抠出事件内容。k6 默认把 console.log 包成 logfmt：
#   time="..." level=info msg="__SEARCH_K6_EVENT__|..." source=console
# 同时也兼容不经 logfmt 包装的裸行。
def _extract_event_payload(line: str) -> str | None:
    marker = "__SEARCH_K6_EVENT__"
    idx = line.find(marker)
    if idx < 0:
        return None
    payload = line[idx + len(marker):]
    # logfmt 结尾：最后一个 '" source=' 之前是 msg 内容（用 rsplit 避免正文里出现同样片段）
    head, sep, _tail = payload.rpartition('" source=')
    if sep:
        payload = head
    payload = payload.strip()
    if payload.endswith('"'):
        payload = payload[:-1]
    if payload.startswith(":") or payload.startswith("|"):
        payload = payload[1:]
    # logfmt 会转义 msg 内的引号/反斜杠
    if '\\' in payload:
        try:
            payload = json.loads(f'"{payload}"')
        except json.JSONDecodeError:
            payload = payload.replace('\\"', '"').replace('\\\\', '\\')
    return payload.strip()


# 旧格式：一行一个完整 JSON（保留兼容，历史日志仍可解析）
def _parse_legacy_event_json(payload: str) -> dict[str, Any] | None:
    candidates = [payload]
    if '" source=' in payload:
        candidates.append(payload.split('" source=', 1)[0].strip())
    if '" level=' in payload:
        candidates.append(payload.split('" level=', 1)[0].strip())
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


# 新格式（紧凑）：case_id|concurrency|rel_start_s|rel_end_s|status|duration_ms|ok|error_kind|detail(json)
def _parse_compact_event(payload: str) -> dict[str, Any] | None:
    # 共 9 个字段，只切前 8 个分隔符，detail 里即使含 '|' 也完整保留
    parts = payload.split("|", 8)
    if len(parts) < 9:
        return None
    head = [part.strip() for part in parts[:8]]
    case_id, concurrency, rel_start, rel_end, status, duration_ms, ok_flag, error_kind = head
    detail_raw = parts[8]
    detail: dict[str, Any] = {}
    if detail_raw:
        try:
            detail = json.loads(detail_raw)
        except json.JSONDecodeError:
            detail = {"b": detail_raw}
    try:
        status_value = int(status)
    except (TypeError, ValueError):
        status_value = 0
    try:
        concurrency_value = int(float(concurrency))
    except (TypeError, ValueError):
        concurrency_value = 0
    try:
        duration_value = float(duration_ms)
    except (TypeError, ValueError):
        duration_value = 0.0
    return {
        "case_id": case_id,
        "concurrency": concurrency_value,
        "relative_start_s": float(rel_start or 0.0),
        "relative_end_s": float(rel_end or 0.0),
        "status": status_value,
        "duration_ms": duration_value,
        "ok": ok_flag in ("1", "true", "True"),
        "error_kind": error_kind or None,
        "error_message": detail.get("m"),
        "response_headers": detail.get("h"),
        "response_body": detail.get("b"),
    }


# 内部辅助函数，封装当前模块的局部逻辑。
def _normalize_k6_relative_times(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not events:
        return []
    base_start = min(float(event["relative_start_s"]) for event in events if event.get("relative_start_s") is not None)
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


# 写入当前场景输出文件。


# 内部辅助函数，封装当前模块的局部逻辑。
def _build_k6_script_content(config: BenchmarkConfig, *, payload_path: Path, case_id: str, concurrency: int) -> str:
    endpoint = f"{config.base_url.rstrip('/')}/repositories/search"
    return f"""
import http from 'k6/http';

export const options = {{
  scenarios: {{
    search_benchmark: {{
      executor: 'constant-vus',
      vus: {concurrency},
      duration: '{config.total_duration_seconds}s',
    }},
  }},
}};

const payload = JSON.parse(open('{payload_path.as_posix()}'));

// 固定基准时间：优先用 scenario.startTime（所有 VU 共用同一基准，避免各 VU 漂移），
// 取不到才退化为本 VU 的初始化时刻。事件里的相对秒数 = (now - base) / 1000。
const vusInitMs = Date.now();
let baseMs = 0;
function resolveBaseMs() {{
  if (baseMs > 0) return baseMs;
  let parsed = NaN;
  try {{
    const iso = (typeof exec !== 'undefined' && exec && exec.scenario) ? exec.scenario.startTime : '';
    if (iso) parsed = Date.parse(iso);
  }} catch (error) {{
    parsed = NaN;
  }}
  baseMs = Number.isNaN(parsed) ? vusInitMs : parsed;
  return baseMs;
}}

export default function () {{
  const base = resolveBaseMs();
  const started = Date.now();
  const response = http.post('{endpoint}', JSON.stringify(payload), {{
    headers: {{ 'Content-Type': 'application/json' }},
    timeout: '{config.timeout}s',
  }});
  const ended = Date.now();

  const status = response.status;
  const failed = status === 0 || status >= 400;
  // status=0 表示没拿到响应：1050=请求超时，其余按连接错误归类
  const errorKind = status === 0 ? (response.error_code === 1050 ? 'timeout' : 'connection_error') : null;

  // 失败时才带上详情（错误信息/响应头/响应体），成功行保持最小
  let detail = '';
  if (failed) {{
    const payloadDetail = {{
      m: response.error ? String(response.error).slice(0, 500) : null,
    }};
    if (status >= 400) {{
      payloadDetail.h = response.headers;
      try {{
        payloadDetail.b = response.body ? String(response.body).slice(0, 4000) : null;
      }} catch (error) {{
        payloadDetail.b = null;
      }}
    }}
    detail = JSON.stringify(payloadDetail);
  }}

  // 紧凑行：marker|case_id|concurrency|rel_start_s|rel_end_s|status|duration_ms|ok|error_kind|detail
  console.log(
    '__SEARCH_K6_EVENT__|' + '{case_id}' + '|' + {concurrency} + '|'
    + ((started - base) / 1000).toFixed(3) + '|' + ((ended - base) / 1000).toFixed(3) + '|'
    + status + '|' + response.timings.duration.toFixed(3) + '|'
    + (failed ? '0' : '1') + '|' + (errorKind || '') + '|' + detail
  );
}}
""".strip()


# 内部辅助函数，封装当前模块的局部逻辑。
def _build_k6_environment(base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env or os.environ)
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        env.pop(key, None)
    return env


# 构造当前场景所需的数据。
def build_k6_runtime_files(config: BenchmarkConfig, *, payload: dict[str, Any], case_id: str, concurrency: int) -> dict[str, Path]:
    runtime_dir = Path(tempfile.mkdtemp(prefix=f"search-k6-{case_id}-{concurrency}-"))
    script_path = runtime_dir / "search_runtime.js"
    payload_path = runtime_dir / "search_payload.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    script_path.write_text(_build_k6_script_content(config, payload_path=payload_path, case_id=case_id, concurrency=concurrency), encoding="utf-8")
    return {
        "runtime_dir": runtime_dir,
        "script_path": script_path,
        "payload_path": payload_path,
    }


# 执行当前场景的核心流程。


# 内部辅助函数，封装当前模块的局部逻辑。
def _cleanup_runtime_files(runtime_files: dict[str, Path]) -> None:
    runtime_dir = runtime_files.get("runtime_dir")
    if runtime_dir and runtime_dir.exists():
        shutil.rmtree(runtime_dir, ignore_errors=True)


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


# 执行当前场景的核心流程。
def run_k6_for_case_with_progress(config: BenchmarkConfig, *, case_id: str, concurrency: int, runtime_files: dict[str, Path]) -> subprocess.CompletedProcess[str]:
    command = [config.k6_executable, "run", str(runtime_files["script_path"])]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=_build_k6_environment())
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
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


# 执行当前场景的核心流程。


# ==================== 热点库混合负载与在线基线 ====================

REPORT_FILENAME = "search_hotspot_report.md"
HOTSPOT_PAIR_HEADERS = [
    "并发",
    "基线总请求",
    "热点总请求",
    "基线成功",
    "基线成功率",
    "基线QPS",
    "热点QPS",
    "基线P50",
    "基线Avg",
    "基线P95",
    "热点P95",
    "基线P99",
    "基线Max",
    "基线超时",
    "基线连接错误",
]
BASELINE_ONLY_HEADERS = [
    "并发",
    "基线总请求",
    "基线成功",
    "基线成功率",
    "基线QPS",
    "基线P50",
    "基线Avg",
    "基线P95",
    "基线P99",
    "基线Max",
    "基线超时",
    "基线连接错误",
]
FAILURES_FILENAME = "failures.json"

# ---- 搜索范围（已锁定）----
WRITE_HOTSPOT_REPOS: list[str] = [
    "3kwfacerepo_test",
    "1Efacerepo",
    "5kwfacerepo",
    "1kwfacerepo_test",
]
# NPU 库只做 baseline，不执行 hotspot 混合负载。
NPU_REPOSITORIES: set[str] = {
    item.strip()
    for item in os.environ.get(
        "SEARCH_NPU_REPOSITORIES",
        "3kwfacerepo_test,1kwfacerepo_test",
    ).split(",")
    if item.strip()
}
# 多 NPU 库组合只保留到该并发上限；单 NPU 库继续使用完整并发梯度。
NPU_MULTI_REPO_CONCURRENCY_CAP = int(
    os.environ.get("SEARCH_NPU_MULTI_REPO_CONCURRENCY_CAP", "32")
)
# HotspotConfig 的主流程配置统一复用文件顶部的旧 DEFAULT_* 常量。
SEARCH_REPOSITORY_COMBOS: list[list[str]] = [
    list(item) for item in DEFAULT_REPOSITORIES_VALUES
]
CONCURRENCY_VALUES: list[int] = list(DEFAULT_CONCURRENCY_VALUES)
SEARCH_CONCURRENCY_OVERRIDES: dict[tuple[str, ...], list[int]] = {}
MAX_CANDIDATES_VALUES: list[int] = list(DEFAULT_MAX_CANDIDATES_VALUES)
INCLUDE_THRESHOLD_VALUES: list[float] = list(DEFAULT_INCLUDE_THRESHOLD_VALUES)

# ---- 测量窗口 ----
TOTAL_DURATION_SECONDS = 200
MEASUREMENT_START_OFFSET_SECONDS = 20
MEASUREMENT_WINDOW_SECONDS = 180
BASELINE_MEASUREMENT_START_OFFSET_SECONDS = 20

# ---- 持续写入策略 ----
DEFAULT_FEATURE_FILE = Path("/home/wx/testFlow/wx/插库/feature_cache_fp32.txt")
FEATURE_FILE = Path(os.environ.get("SEARCH_HOTSPOT_FEATURE_FILE", str(DEFAULT_FEATURE_FILE))).expanduser()
INSERT_WORKERS = int(os.environ.get("SEARCH_HOTSPOT_INSERT_WORKERS", "32"))
DELETE_WORKERS = int(os.environ.get("SEARCH_HOTSPOT_DELETE_WORKERS", "32"))
POOL_INITIAL_SIZE = int(os.environ.get("SEARCH_HOTSPOT_POOL_INITIAL", "0"))
CHURN_JOIN_TIMEOUT_SECONDS = int(os.environ.get("SEARCH_HOTSPOT_CHURN_JOIN_TIMEOUT", "15"))
CLEANUP_CONCURRENCY = int(os.environ.get("SEARCH_HOTSPOT_CLEANUP_CONCURRENCY", "32"))
VERIFY_PROBE_COUNT = int(os.environ.get("SEARCH_HOTSPOT_VERIFY_PROBES", "15"))
VERIFY_DELETED_SAMPLE = int(os.environ.get("SEARCH_HOTSPOT_VERIFY_DELETED_SAMPLE", "10"))
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("SEARCH_HOTSPOT_REQUEST_TIMEOUT", "15"))

# 第一条特征就是历史 SAMPLE_SEARCH 使用的查询特征。
_QUERY_FEATURE_VALUE: str | None = None


# ---------------------------------------------------------------- 特征读取
@dataclass(frozen=True)
class FeatureEntry:
    index: int
    key: str
    value: str


class FeatureCursor:
    """按文件顺序读取特征，不把约 50 万条特征全部加载进内存。"""

    def __init__(self, path: Path = FEATURE_FILE):
        self.path = Path(path)
        self._fh = self.path.open("r", encoding="utf-8", errors="replace")
        self._feature_index = 0
        self._line_number = 0
        self.wrap_count = 0

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass

    def read_next(self) -> FeatureEntry:
        while True:
            line = self._fh.readline()
            if not line:
                if self._feature_index <= 0:
                    raise RuntimeError(f"feature file contains no valid feature rows: {self.path}")
                self._fh.seek(0)
                self._line_number = 0
                self.wrap_count += 1
                continue
            self._line_number += 1
            parts = line.rstrip("\r\n").split("\t", 1)
            if len(parts) != 2:
                continue
            key, value = parts[0].strip(), parts[1].strip()
            if not value:
                continue
            entry = FeatureEntry(index=self._feature_index, key=key, value=value)
            self._feature_index += 1
            return entry


def read_first_feature(path: Path = FEATURE_FILE) -> str:
    with Path(path).open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.rstrip("\r\n").split("\t", 1)
            if len(parts) == 2 and parts[1].strip():
                return parts[1].strip()
    raise RuntimeError(f"feature file contains no valid feature rows: {path}")


def query_feature_value() -> str:
    global _QUERY_FEATURE_VALUE
    if _QUERY_FEATURE_VALUE is None:
        _QUERY_FEATURE_VALUE = read_first_feature(FEATURE_FILE)
    return _QUERY_FEATURE_VALUE


# ---------------------------------------------------------------- 模板构造
def build_entity_template(feature_value: str) -> dict[str, Any]:
    template = deepcopy(SAMPLE_ENTITY)
    template.setdefault("data", {})
    template["data"] = {**template.get("data", {}), "value": str(feature_value)}
    return template


def build_search_template(
    *,
    repositories: list[str],
    max_candidates: int,
    include_threshold: float,
    feature_value: str | None = None,
) -> dict[str, Any]:
    template = deepcopy(SAMPLE_SEARCH)
    include = template.get("include")
    if isinstance(include, list) and include and isinstance(include[0], dict):
        include[0].setdefault("data", {})
        if isinstance(include[0]["data"], dict):
            include[0]["data"]["value"] = str(feature_value or query_feature_value())
    return build_search_payload(
        template=template,
        repositories=list(repositories),
        max_candidates=max_candidates,
        include_threshold=include_threshold,
        location_id=None,
    )


# ---------------------------------------------------------------- 配置
@dataclass
class HotspotConfig:
    base_url: str = DEFAULT_BASE_URL
    search_repositories_values: list[list[str]] = field(
        default_factory=lambda: [list(item) for item in SEARCH_REPOSITORY_COMBOS]
    )
    concurrency_values: list[int] = field(default_factory=lambda: list(CONCURRENCY_VALUES))
    max_candidates_values: list[int] = field(default_factory=lambda: list(MAX_CANDIDATES_VALUES))
    include_threshold_values: list[float] = field(default_factory=lambda: list(INCLUDE_THRESHOLD_VALUES))
    total_duration_seconds: int = TOTAL_DURATION_SECONDS
    measurement_start_offset_seconds: int = MEASUREMENT_START_OFFSET_SECONDS
    measurement_window_seconds: int = MEASUREMENT_WINDOW_SECONDS
    baseline_measurement_start_offset_seconds: int = BASELINE_MEASUREMENT_START_OFFSET_SECONDS
    baseline_measurement_window_seconds: int = MEASUREMENT_WINDOW_SECONDS
    phase_order: tuple[str, ...] = ("baseline", "hotspot")
    phase_policy: str = "staged"
    phase_gap_seconds: int = 0
    timeout: int = REQUEST_TIMEOUT_SECONDS
    k6_executable: str = field(default_factory=resolve_k6_executable)
    report_output_dir: Path = field(
        default_factory=lambda: default_run_dir("search_hotspot")
    )
    feature_file: Path = FEATURE_FILE
    insert_workers: int = INSERT_WORKERS
    delete_workers: int = DELETE_WORKERS
    pool_initial_size: int = POOL_INITIAL_SIZE
    cleanup_concurrency: int = CLEANUP_CONCURRENCY
    query_feature: str = field(default_factory=query_feature_value)
    verify_probe_count: int = VERIFY_PROBE_COUNT
    verify_deleted_sample: int = VERIFY_DELETED_SAMPLE
    insecure: bool = False

    def concurrency_for(self, repositories: list[str], max_candidates: int | None = None) -> list[int]:
        key = tuple(sorted(str(item) for item in repositories))
        if key in SEARCH_CONCURRENCY_OVERRIDES:
            allowed = set(SEARCH_CONCURRENCY_OVERRIDES[key])
            return [value for value in self.concurrency_values if value in allowed]
        tiers = list(self.concurrency_values)
        npu_count = sum(1 for repo_id in repositories if repo_id in NPU_REPOSITORIES)
        if npu_count > 1 and NPU_MULTI_REPO_CONCURRENCY_CAP > 0:
            tiers = [tier for tier in tiers if tier <= NPU_MULTI_REPO_CONCURRENCY_CAP]
        if (
            max_candidates is not None
            and DEFAULT_HEAVY_CONCURRENCY_CAP > 0
            and int(max_candidates) >= DEFAULT_HEAVY_MAX_CANDIDATES
        ):
            tiers = [
                tier
                for tier in tiers
                if tier <= DEFAULT_HEAVY_CONCURRENCY_CAP
            ]
        return tiers


# ---------------------------------------------------------------- 库规模
async def fetch_repo_sizes_async(config: HotspotConfig) -> dict[str, int | None]:
    import aiohttp

    sizes: dict[str, int | None] = {}
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=4)) as session:
        for repo_id in WRITE_HOTSPOT_REPOS:
            url = build_url(config.base_url, f"/repositories/{repo_id}")
            try:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=config.timeout),
                    ssl=False if config.insecure else None,
                ) as response:
                    body = await response.json(content_type=None)
                    size = body.get("size") if isinstance(body, dict) else None
                    sizes[repo_id] = int(size) if size is not None else None
            except Exception:
                sizes[repo_id] = None
    return sizes


# ---------------------------------------------------------------- 写入池
@dataclass
class PoolItem:
    entity_id: str
    feature_index: int
    feature_value: str
    feature_kind: str = "scan"
    inserted_at: float = field(default_factory=time.monotonic)


@dataclass
class WritePool:
    repo_id: str
    items: deque[PoolItem] = field(default_factory=deque)


@dataclass
class WriteTierStats:
    started_at: float = field(default_factory=time.monotonic)
    measurement_start_offset_seconds: int = MEASUREMENT_START_OFFSET_SECONDS
    measurement_window_seconds: int = MEASUREMENT_WINDOW_SECONDS
    insert_workers: int = INSERT_WORKERS
    delete_workers: int = DELETE_WORKERS
    insert_ok: int = 0
    insert_fail: int = 0
    delete_ok: int = 0
    delete_fail: int = 0
    window_insert_ok: int = 0
    window_insert_fail: int = 0
    window_delete_ok: int = 0
    window_delete_fail: int = 0
    insert_latencies_ms: list[float] = field(default_factory=list)
    delete_latencies_ms: list[float] = field(default_factory=list)
    status_counts: Counter = field(default_factory=Counter)
    pool_min: int = 0
    pool_max: int = 0
    series: dict[int, dict[str, int]] = field(default_factory=dict)
    worker_errors: list[str] = field(default_factory=list)

    def _series_bucket(self) -> dict[str, int]:
        second = max(0, int(time.monotonic() - self.started_at))
        return self.series.setdefault(
            second,
            {
                "insert_ok": 0,
                "insert_fail": 0,
                "delete_ok": 0,
                "delete_fail": 0,
                "pool_size": 0,
                "samples": 0,
            },
        )

    def _in_window(self) -> bool:
        offset = time.monotonic() - self.started_at
        return (
            self.measurement_start_offset_seconds
            <= offset
            < self.measurement_start_offset_seconds + self.measurement_window_seconds
        )

    def record_insert(
        self,
        *,
        ok: bool,
        latency_ms: float,
        status: int | None,
        pool_size: int,
        feature_kind: str,
    ) -> None:
        bucket = self._series_bucket()
        bucket["insert_ok" if ok else "insert_fail"] += 1
        bucket["pool_size"] = pool_size
        bucket["samples"] += 1
        self.pool_min = pool_size if self.pool_min == 0 else min(self.pool_min, pool_size)
        self.pool_max = max(self.pool_max, pool_size)
        self.status_counts[f"insert:{status}"] += 1
        if ok:
            self.insert_ok += 1
        else:
            self.insert_fail += 1
        if self._in_window():
            if ok:
                self.window_insert_ok += 1
                self.insert_latencies_ms.append(latency_ms)
            else:
                self.window_insert_fail += 1

    def record_delete(
        self,
        *,
        ok: bool,
        latency_ms: float,
        status: int | None,
        pool_size: int,
        feature_kind: str,
    ) -> None:
        bucket = self._series_bucket()
        bucket["delete_ok" if ok else "delete_fail"] += 1
        bucket["pool_size"] = pool_size
        bucket["samples"] += 1
        self.pool_min = pool_size if self.pool_min == 0 else min(self.pool_min, pool_size)
        self.pool_max = max(self.pool_max, pool_size)
        self.status_counts[f"delete:{status}"] += 1
        if ok:
            self.delete_ok += 1
        else:
            self.delete_fail += 1
        if self._in_window():
            if ok:
                self.window_delete_ok += 1
                self.delete_latencies_ms.append(latency_ms)
            else:
                self.window_delete_fail += 1

    def as_dict(self) -> dict[str, Any]:
        insert_ops = self.window_insert_ok + self.window_insert_fail
        delete_ops = self.window_delete_ok + self.window_delete_fail
        total_ops = insert_ops + delete_ops
        success_ops = self.window_insert_ok + self.window_delete_ok
        return {
            "insert_ok": self.insert_ok,
            "insert_fail": self.insert_fail,
            "delete_ok": self.delete_ok,
            "delete_fail": self.delete_fail,
            "window_insert_ok": self.window_insert_ok,
            "window_insert_fail": self.window_insert_fail,
            "window_delete_ok": self.window_delete_ok,
            "window_delete_fail": self.window_delete_fail,
            "insert_ops": insert_ops,
            "delete_ops": delete_ops,
            "total_ops": total_ops,
            "insert_ops_per_second": round(insert_ops / self.measurement_window_seconds, 3)
            if insert_ops and self.measurement_window_seconds > 0
            else 0.0,
            "delete_ops_per_second": round(delete_ops / self.measurement_window_seconds, 3)
            if delete_ops and self.measurement_window_seconds > 0
            else 0.0,
            "ops_per_second": round(total_ops / self.measurement_window_seconds, 3)
            if total_ops and self.measurement_window_seconds > 0
            else 0.0,
            "success_rate": round(100.0 * success_ops / total_ops, 3) if total_ops else 0.0,
            "insert_p95_ms": percentile(self.insert_latencies_ms, 95),
            "delete_p95_ms": percentile(self.delete_latencies_ms, 95),
            "pool_min": self.pool_min,
            "pool_max": self.pool_max,
            "insert_workers": max(1, int(self.insert_workers)),
            "delete_workers": max(1, int(self.delete_workers)),
            "series": [
                {"second": second, **values}
                for second, values in sorted(self.series.items())
            ],
            "status_counts": {str(key): int(value) for key, value in self.status_counts.items()},
            "worker_errors": list(self.worker_errors),
        }




# ---------------------------------------------------------------- HTTP 操作
async def insert_entity_async(
    *, session: Any, config: HotspotConfig, repo_id: str, entity_id: str, feature_value: str
) -> tuple[bool, float, int | None]:
    url = build_url(config.base_url, f"/repositories/{repo_id}/entities")
    payload = create_entity_payload(entity_id, build_entity_template(feature_value))
    started = time.perf_counter()
    status, _body = await send_json_request_async(
        session, method="POST", url=url, timeout=config.timeout, insecure=config.insecure, payload=payload
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return (status is not None and 200 <= status < 300), elapsed_ms, status


async def delete_entity_async(
    *, session: Any, config: HotspotConfig, repo_id: str, entity_id: str
) -> tuple[bool, float, int | None]:
    import aiohttp

    url = build_url(config.base_url, f"/repositories/{repo_id}/entities/{entity_id}")
    started = time.perf_counter()
    try:
        async with session.delete(
            url,
            timeout=aiohttp.ClientTimeout(total=config.timeout),
            ssl=False if config.insecure else None,
        ) as response:
            await response.text()
            status = response.status
    except Exception:
        status = None
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return (status is not None and 200 <= status < 300), elapsed_ms, status


def make_hotspot_entity_id(index: int) -> str:
    return f"hotspot-{index:08d}-{uuid.uuid4().hex}"


# ---------------------------------------------------------------- 写入池初始化
async def prepare_write_pool_async(
    *, config: HotspotConfig, repo_id: str, cursor: FeatureCursor
) -> tuple[WritePool, list[dict[str, Any]]]:
    import aiohttp

    pool = WritePool(repo_id=repo_id)
    timings: list[dict[str, Any]] = []
    target = max(1, int(config.pool_initial_size))
    max_attempts = max(target, target * 2)
    attempts = 0
    lock = asyncio.Lock()
    preload_workers = max(1, min(64, int(config.insert_workers)))
    connector_limit = max(16, preload_workers * 2)

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=connector_limit)) as session:
        async def worker(worker_index: int) -> None:
            nonlocal attempts
            while True:
                async with lock:
                    if len(pool.items) >= target or attempts >= max_attempts:
                        return
                    feature = cursor.read_next()
                    attempt = attempts
                    attempts += 1
                entity_id = make_hotspot_entity_id(attempt)
                ok, elapsed_ms, status = await insert_entity_async(
                    session=session,
                    config=config,
                    repo_id=repo_id,
                    entity_id=entity_id,
                    feature_value=feature.value,
                )
                async with lock:
                    timings.append(
                        {
                            "op": "pool_preload_insert",
                            "repo_id": repo_id,
                            "entity_id": entity_id,
                            "feature_index": feature.index,
                            "ok": ok,
                            "status": status,
                            "elapsed_ms": round(elapsed_ms, 3),
                        }
                    )
                    if ok:
                        pool.items.append(
                            PoolItem(
                                entity_id=entity_id,
                                feature_index=feature.index,
                                feature_value=feature.value,
                                feature_kind="scan",
                            )
                        )

        await asyncio.gather(*(worker(index) for index in range(preload_workers)))
    if len(pool.items) < target:
        raise RuntimeError(
            f"failed to prepare write pool for {repo_id}: "
            f"got={len(pool.items)} target={target} attempts={attempts}"
        )
    return pool, timings


# ---------------------------------------------------------------- 持续写入 worker
async def _wait_condition(
    condition: asyncio.Condition, predicate: Any, stop_event: threading.Event
) -> None:
    while not stop_event.is_set() and not predicate():
        try:
            await asyncio.wait_for(condition.wait(), timeout=0.2)
        except asyncio.TimeoutError:
            continue


async def _write_workers_async(
    *,
    config: HotspotConfig,
    repo_id: str,
    pool: WritePool,
    cursor: FeatureCursor,
    stats: WriteTierStats,
    stop_event: threading.Event,
) -> None:
    import aiohttp

    total_workers = max(1, config.insert_workers) + max(1, config.delete_workers)
    connector_limit = max(8, total_workers * 2)
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=connector_limit)) as session:
        condition = asyncio.Condition()

        async def insert_worker(worker_index: int) -> None:
            while not stop_event.is_set():
                # 所有插入都按特征文件顺序取不同特征，不再复制查询热点特征。
                feature = cursor.read_next()
                feature_kind = "scan"
                entity_id = make_hotspot_entity_id(worker_index)
                ok, elapsed_ms, status = await insert_entity_async(
                    session=session,
                    config=config,
                    repo_id=repo_id,
                    entity_id=entity_id,
                    feature_value=feature.value,
                )
                async with condition:
                    if ok:
                        pool.items.append(
                            PoolItem(
                                entity_id=entity_id,
                                feature_index=feature.index,
                                feature_value=feature.value,
                                feature_kind=feature_kind,
                            )
                        )
                    stats.record_insert(
                        ok=ok,
                        latency_ms=elapsed_ms,
                        status=status,
                        pool_size=len(pool.items),
                        feature_kind=feature_kind,
                    )
                    condition.notify_all()
                if not ok:
                    await asyncio.sleep(0.05)

        async def delete_worker(worker_index: int) -> None:
            while not stop_event.is_set():
                async with condition:
                    await _wait_condition(
                        condition,
                        lambda: len(pool.items) > 0,
                        stop_event,
                    )
                    if stop_event.is_set():
                        return
                    victim = pool.items.popleft()
                ok, elapsed_ms, status = await delete_entity_async(
                    session=session,
                    config=config,
                    repo_id=repo_id,
                    entity_id=victim.entity_id,
                )
                async with condition:
                    if not ok:
                        pool.items.appendleft(victim)
                    stats.record_delete(
                        ok=ok,
                        latency_ms=elapsed_ms,
                        status=status,
                        pool_size=len(pool.items),
                        feature_kind=victim.feature_kind,
                    )
                    condition.notify_all()
                if not ok:
                    await asyncio.sleep(0.05)

        workers = [insert_worker(i) for i in range(max(1, config.insert_workers))]
        workers.extend(delete_worker(i) for i in range(max(1, config.delete_workers)))
        try:
            await asyncio.gather(*workers)
        except Exception as exc:
            stats.worker_errors.append(repr(exc))


def start_write_thread(
    *,
    config: HotspotConfig,
    repo_id: str,
    pool: WritePool,
    cursor: FeatureCursor,
    stats: WriteTierStats,
    stop_event: threading.Event,
) -> threading.Thread:
    def runner() -> None:
        try:
            asyncio.run(
                _write_workers_async(
                    config=config,
                    repo_id=repo_id,
                    pool=pool,
                    cursor=cursor,
                    stats=stats,
                    stop_event=stop_event,
                )
            )
        except Exception as exc:
            stats.worker_errors.append(repr(exc))

    thread = threading.Thread(
        target=runner,
        name=f"search-hotspot-write-{repo_id}",
        daemon=True,
    )
    thread.start()
    return thread


# ---------------------------------------------------------------- 校验
async def _probe_search_hits_async(
    *,
    config: HotspotConfig,
    payload: dict[str, Any],
    probe_count: int,
    needles: list[str],
) -> tuple[int, int, int, set[str]]:
    import aiohttp

    url = build_url(config.base_url, "/repositories/search")
    probes_with_hit = 0
    hit_total = 0
    failed_probes = 0
    matched: set[str] = set()
    async with aiohttp.ClientSession() as session:
        for _ in range(max(1, probe_count)):
            try:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=config.timeout),
                    ssl=False if config.insecure else None,
                ) as response:
                    text = await response.text()
                    if not 200 <= response.status < 300:
                        failed_probes += 1
                        continue
            except Exception:
                failed_probes += 1
                continue
            found = [item for item in needles if item in text]
            if found:
                probes_with_hit += 1
                hit_total += len(found)
                matched.update(found)
    return probes_with_hit, hit_total, failed_probes, matched


async def verify_visibility_async(
    *, config: HotspotConfig, repo_id: str, pool: WritePool
) -> dict[str, Any]:
    needles = [item.entity_id for item in list(pool.items)[:30]]
    payload = build_search_template(
        repositories=[repo_id],
        max_candidates=1000,
        include_threshold=0.5,
        feature_value=config.query_feature,
    )
    probes_with_hit, hit_total, failed_probes, matched = await _probe_search_hits_async(
        config=config,
        payload=payload,
        probe_count=config.verify_probe_count,
        needles=needles,
    )
    return {
        "repo_id": repo_id,
        "probe_count": max(1, config.verify_probe_count),
        "probes_with_hit": probes_with_hit,
        "hit_total": hit_total,
        "failed_probes": failed_probes,
        "distinct_seeded_ids_seen": len(matched),
        "pass": probes_with_hit > 0 and failed_probes == 0,
        "note": "写入池可见性，低并发探针，不计入压测指标",
    }


async def verify_stale_async(
    *, config: HotspotConfig, repo_id: str, deleted_items: list[PoolItem]
) -> dict[str, Any]:
    if not deleted_items:
        return {
            "repo_id": repo_id,
            "deleted_ids_checked": 0,
            "probe_count": max(1, config.verify_probe_count),
            "stale_hits": 0,
            "failed_probes": 0,
            "pass": False,
            "note": "无可校验的已删实体",
        }
    payload = build_search_template(
        repositories=[repo_id],
        max_candidates=1000,
        include_threshold=0.5,
        feature_value=config.query_feature,
    )
    # 查询使用被删实体的特征，避免用不对应特征时产生误判。
    include = payload.get("include")
    if isinstance(include, list) and include and isinstance(include[0], dict):
        include[0].setdefault("data", {})
        if isinstance(include[0]["data"], dict):
            include[0]["data"]["value"] = deleted_items[0].feature_value
    needles = [item.entity_id for item in deleted_items]
    _probes_with_hit, stale_hits, failed_probes, _matched = await _probe_search_hits_async(
        config=config,
        payload=payload,
        probe_count=config.verify_probe_count,
        needles=needles,
    )
    return {
        "repo_id": repo_id,
        "deleted_ids_checked": len(deleted_items),
        "probe_count": max(1, config.verify_probe_count),
        "stale_hits": stale_hits,
        "failed_probes": failed_probes,
        "pass": stale_hits == 0 and failed_probes == 0,
        "note": "已删实体不应再被检索返回",
    }


async def cleanup_pool_async(
    *, config: HotspotConfig, repo_id: str, items: list[PoolItem]
) -> list[dict[str, Any]]:
    import aiohttp

    concurrency = max(1, int(config.cleanup_concurrency))
    semaphore = asyncio.Semaphore(concurrency)
    timings: list[dict[str, Any] | None] = [None] * len(items)
    connector_limit = max(8, concurrency * 2)
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=connector_limit, limit_per_host=connector_limit)
    ) as session:
        async def worker(index: int, item: PoolItem) -> None:
            async with semaphore:
                ok, elapsed_ms, status = await delete_entity_async(
                    session=session,
                    config=config,
                    repo_id=repo_id,
                    entity_id=item.entity_id,
                )
                timings[index] = {
                    "op": "pool_cleanup_delete",
                    "repo_id": repo_id,
                    "entity_id": item.entity_id,
                    "feature_index": item.feature_index,
                    "ok": ok,
                    "status": status,
                }

        await asyncio.gather(*(worker(index, item) for index, item in enumerate(items)))
    return [item for item in timings if item is not None]


# ---------------------------------------------------------------- 单档压测
def run_search_tier(
    *,
    config: HotspotConfig,
    search_repositories: list[str],
    write_repositories: list[str],
    max_candidates: int,
    include_threshold: float,
    concurrency: int,
    repo_states: dict[str, dict[str, Any]],
    phase: str = "hotspot",
    measurement_start_offset_seconds: int | None = None,
    measurement_window_seconds: int | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], float]:
    payload = build_search_template(
        repositories=search_repositories,
        max_candidates=max_candidates,
        include_threshold=include_threshold,
        feature_value=config.query_feature,
    )
    repo_label = ",".join(search_repositories)
    case_id = (
        f"search_{phase}@{repo_label}"
        f"[M={max_candidates},T={include_threshold}]"
    )
    tier_dir = Path(config.report_output_dir) / "tiers"
    tier_dir.mkdir(parents=True, exist_ok=True)
    effective_offset = (
        config.measurement_start_offset_seconds
        if measurement_start_offset_seconds is None
        else int(measurement_start_offset_seconds)
    )
    effective_window = (
        config.measurement_window_seconds
        if measurement_window_seconds is None
        else int(measurement_window_seconds)
    )
    tier_total_seconds = effective_offset + effective_window
    search_config = replace(
        build_default_config(),
        base_url=config.base_url,
        concurrency_values=[int(concurrency)],
        total_duration_seconds=tier_total_seconds,
        measurement_start_offset_seconds=effective_offset,
        measurement_window_seconds=effective_window,
        timeout=config.timeout,
        k6_executable=config.k6_executable,
        report_output_dir=tier_dir,
    )
    runtime_files = build_k6_runtime_files(
        search_config,
        payload=payload,
        case_id=case_id,
        concurrency=int(concurrency),
    )

    if DEFAULT_HEALTH_GATE_ENABLED:
        healthy, detail = probe_service_health(config.base_url)
        if not healthy:
            _cleanup_runtime_files(runtime_files)
            raise RuntimeError(
                f"service unhealthy before {phase} case={case_id} "
                f"concurrency={concurrency}: {detail}"
            )

    tier_started = time.monotonic()
    stop_event = threading.Event()
    write_stats: dict[str, WriteTierStats] = {
        repo_id: WriteTierStats(
            started_at=tier_started,
            measurement_start_offset_seconds=effective_offset,
            measurement_window_seconds=effective_window,
            insert_workers=config.insert_workers,
            delete_workers=config.delete_workers,
        )
        for repo_id in write_repositories
    }
    write_threads: list[threading.Thread] = []
    for repo_id in write_repositories:
        state = repo_states[repo_id]
        write_threads.append(
            start_write_thread(
                config=config,
                repo_id=repo_id,
                pool=state["pool"],
                cursor=state["cursor"],
                stats=write_stats[repo_id],
                stop_event=stop_event,
            )
        )

    started = time.perf_counter()
    try:
        completed = run_k6_for_case_with_progress(
            search_config,
            case_id=case_id,
            concurrency=int(concurrency),
            runtime_files=runtime_files,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"k6 failed for {case_id} concurrency={concurrency}: {completed.stderr.strip()}"
            )
        events = _normalize_k6_relative_times(
            _parse_k6_console_events(f"{completed.stdout}\n{completed.stderr}")
        )
        measured_events = filter_measured_window_events(
            events,
            measurement_start_offset_seconds=effective_offset,
            measurement_window_seconds=effective_window,
        )
        metric = summarize_measured_events(
            measured_events,
            case_id=case_id,
            concurrency=int(concurrency),
            measurement_window_seconds=effective_window,
        )
        metric["case_id"] = case_id
        metric["repositories"] = list(search_repositories)
        metric["write_repositories"] = list(write_repositories)
        metric["max_candidates"] = int(max_candidates)
        metric["include_threshold"] = float(include_threshold)
        metric["phase"] = phase
        if not measured_events and DEFAULT_ABORT_ON_ZERO_EVENTS:
            raise RuntimeError(
                f"zero measured events for {phase} case={case_id} concurrency={concurrency}"
            )
        if int(metric.get("success_count") or 0) == 0 and DEFAULT_ABORT_ON_ZERO_SUCCESS:
            raise RuntimeError(
                f"zero successful requests for {phase} case={case_id} concurrency={concurrency}"
            )
        failures = [
            {
                "case_id": case_id,
                "repositories": list(search_repositories),
                "write_repositories": list(write_repositories),
                "max_candidates": int(max_candidates),
                "include_threshold": float(include_threshold),
                "concurrency": int(concurrency),
                "status": event.get("status"),
                "error_kind": event.get("error_kind"),
                "error": event.get("error_message"),
                "elapsed_ms": event.get("duration_ms"),
            }
            for event in measured_events
            if not event.get("ok")
        ]
    finally:
        elapsed = time.perf_counter() - started
        stop_event.set()
        for repo_id, thread in zip(write_repositories, write_threads):
            thread.join(timeout=CHURN_JOIN_TIMEOUT_SECONDS)
            if thread.is_alive():
                write_stats[repo_id].worker_errors.append("write worker did not stop before join timeout")
        _cleanup_runtime_files(runtime_files)

    write_rows: dict[str, dict[str, Any]] = {}
    for repo_id, stats in write_stats.items():
        write_rows[repo_id] = stats.as_dict()
    aggregate_insert_ops = sum(row["insert_ops"] for row in write_rows.values())
    aggregate_delete_ops = sum(row["delete_ops"] for row in write_rows.values())
    aggregate_insert_ops_per_second = sum(row["insert_ops_per_second"] for row in write_rows.values())
    aggregate_delete_ops_per_second = sum(row["delete_ops_per_second"] for row in write_rows.values())
    aggregate_ok = sum(row["window_insert_ok"] + row["window_delete_ok"] for row in write_rows.values())
    aggregate_total = aggregate_insert_ops + aggregate_delete_ops
    aggregate_write = {
        "insert_ops": aggregate_insert_ops,
        "delete_ops": aggregate_delete_ops,
        "insert_ops_per_second": round(aggregate_insert_ops_per_second, 3),
        "delete_ops_per_second": round(aggregate_delete_ops_per_second, 3),
        "total_ops": aggregate_total,
        "ops_per_second": round(aggregate_total / config.measurement_window_seconds, 3)
        if aggregate_total and config.measurement_window_seconds > 0
        else 0.0,
        "success_rate": round(100.0 * aggregate_ok / aggregate_total, 3) if aggregate_total else 0.0,
        "write_repositories": list(write_repositories),
        "repositories": write_rows,
    }
    return metric, failures, {"repositories": write_rows, "aggregate": aggregate_write}, elapsed


# ---------------------------------------------------------------- 基线读取与匹配
def find_baseline_reports(roots: list[Path] | None = None) -> list[Path]:
    search_roots: list[Path] = []
    env_root = os.environ.get("API_TEST_PERF_OUTPUT")
    if roots:
        search_roots.extend(Path(root) for root in roots)
    search_roots.append(PROJECT_ROOT / "performance" / "outputs")
    if env_root:
        search_roots.append(Path(env_root))
    reports: list[Path] = []
    seen: set[Path] = set()
    for root in search_roots:
        try:
            if not Path(root).exists():
                continue
            for path in Path(root).rglob("search_report.md"):
                key = path.resolve()
                if key not in seen:
                    seen.add(key)
                    reports.append(path)
        except Exception:
            continue
    return sorted(reports, key=lambda item: item.stat().st_mtime)


def parse_case_parameters(label: str) -> dict[str, Any]:
    text = str(label or "")
    result: dict[str, Any] = {
        "repositories": None,
        "max_candidates": None,
        "include_threshold": None,
    }
    for chunk in text.split("|"):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key == "repositories":
            result["repositories"] = [item.strip() for item in value.split(",") if item.strip()]
        elif key == "max_candidates":
            try:
                result["max_candidates"] = int(value)
            except ValueError:
                pass
        elif key == "include_threshold":
            try:
                result["include_threshold"] = float(value)
            except ValueError:
                pass
    return result


def _parse_report_text(text: str) -> dict[str, Any] | None:
    if str(PROJECT_ROOT.parent) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT.parent))
    try:
        import main as main_module

        return main_module.parse_perf_report_text(text)
    except Exception:
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("%", "").replace("ms", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def normalize_baseline_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row or {})
    for key in (
        "qps",
        "throughput_rps",
        "p50",
        "p95",
        "p99",
        "avg",
        "max",
        "latency_p50_ms",
        "latency_p95_ms",
        "latency_p99_ms",
        "latency_avg_ms",
        "latency_max_ms",
        "success_rate",
        "error_rate",
    ):
        if key in normalized:
            normalized[key] = _to_float(normalized[key])
    for key in ("concurrency", "total", "success", "failure", "timeout", "conn_err"):
        if key in normalized:
            value = _to_float(normalized[key])
            normalized[key] = int(value) if value is not None else None
    return normalized


def _combo_key(repositories: list[str]) -> tuple[str, ...]:
    return tuple(str(item) for item in repositories)


def load_baselines(
    search_repositories_values: list[list[str]],
) -> tuple[dict[tuple[tuple[str, ...], int, float, int], dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    wanted = {_combo_key(item) for item in search_repositories_values}
    reports = find_baseline_reports()
    index: dict[tuple[tuple[str, ...], int, float, int], dict[str, Any]] = {}
    sources_by_path: dict[str, dict[str, Any]] = {}
    skipped: Counter = Counter()
    for path in reports:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            skipped["unreadable"] += 1
            continue
        parsed = _parse_report_text(text)
        if not parsed:
            skipped["unparsed"] += 1
            continue
        stamp_match = re.search(r"生成时间[：:]\s*(\S+)", text) or re.search(r"\[Time\] End\s*:\s*(.+)", text)
        generated_at = stamp_match.group(1).strip() if stamp_match else ""
        used_keys: list[str] = []
        for case in parsed.get("cases") or []:
            params = parse_case_parameters(case.get("params") or case.get("label") or "")
            repositories = params.get("repositories") or []
            key_combo = _combo_key(repositories)
            if key_combo not in wanted:
                skipped["repo_not_in_scope"] += 1
                continue
            if params.get("max_candidates") is None or params.get("include_threshold") is None:
                skipped["unparsed_params"] += 1
                continue
            for row in case.get("metrics") or []:
                try:
                    concurrency = int(float(row.get("concurrency")))
                except (TypeError, ValueError):
                    continue
                key = (
                    key_combo,
                    int(params["max_candidates"]),
                    float(params["include_threshold"]),
                    concurrency,
                )
                normalized = normalize_baseline_row(row)
                index[key] = {
                    "metrics": normalized,
                    "source": str(path),
                    "generated_at": generated_at,
                }
                used_keys.append(f"{key_combo}|M={key[1]}|T={key[2]}|C={key[3]}")
        if used_keys:
            sources_by_path[str(path)] = {
                "source": str(path),
                "generated_at": generated_at,
                "keys": len(used_keys),
                "examples": used_keys[:5],
            }
    return index, list(sources_by_path.values()), {
        "scanned_reports": len(reports),
        "matched_rows": len(index),
        "skipped": dict(skipped),
    }


def match_baseline_row(
    index: dict[tuple[tuple[str, ...], int, float, int], dict[str, Any]],
    repositories: list[str],
    max_candidates: int,
    include_threshold: float,
    concurrency: int,
) -> dict[str, Any] | None:
    return index.get(
        (
            _combo_key(repositories),
            int(max_candidates),
            float(include_threshold),
            int(concurrency),
        )
    )


# ---------------------------------------------------------------- 报告


def _verify_label(value: Any) -> str:
    if value is None:
        return "N/A"
    return "PASS" if value else "FAIL"


def _pair_rows(
    *,
    case: dict[str, Any],
) -> list[list[str]]:
    rows: list[list[str]] = []
    baseline_by_concurrency = {
        int(item.get("concurrency")): item
        for item in (case.get("baseline_metrics") or [])
        if item.get("concurrency") is not None
    }
    for metric in case.get("metrics") or []:
        concurrency = int(metric.get("concurrency"))
        baseline = baseline_by_concurrency.get(concurrency) or {}
        rows.append(
            [
                str(concurrency),
                ascii_report.format_int(baseline.get("total_requests")),
                ascii_report.format_int(metric.get("total_requests")),
                ascii_report.format_int(baseline.get("success_count")),
                ascii_report.format_percent(baseline.get("success_rate")),
                ascii_report.format_number(baseline.get("throughput_rps")),
                ascii_report.format_number(metric.get("throughput_rps")),
                ascii_report.format_latency(baseline.get("latency_p50_ms")),
                ascii_report.format_latency(baseline.get("latency_avg_ms")),
                ascii_report.format_latency(baseline.get("latency_p95_ms")),
                ascii_report.format_latency(metric.get("latency_p95_ms")),
                ascii_report.format_latency(baseline.get("latency_p99_ms")),
                ascii_report.format_latency(baseline.get("latency_max_ms")),
                ascii_report.format_int(baseline.get("timeout_count")),
                ascii_report.format_int(baseline.get("connection_error_count")),
            ]
        )
    return rows


def _baseline_only_rows(case: dict[str, Any]) -> list[list[str]]:
    return [
        [
            str(metric.get("concurrency")),
            ascii_report.format_int(metric.get("total_requests")),
            ascii_report.format_int(metric.get("success_count")),
            ascii_report.format_percent(metric.get("success_rate")),
            ascii_report.format_number(metric.get("throughput_rps")),
            ascii_report.format_latency(metric.get("latency_p50_ms")),
            ascii_report.format_latency(metric.get("latency_avg_ms")),
            ascii_report.format_latency(metric.get("latency_p95_ms")),
            ascii_report.format_latency(metric.get("latency_p99_ms")),
            ascii_report.format_latency(metric.get("latency_max_ms")),
            ascii_report.format_int(metric.get("timeout_count")),
            ascii_report.format_int(metric.get("connection_error_count")),
        ]
        for metric in (case.get("baseline_metrics") or [])
    ]


def _write_series_payload(config: HotspotConfig, combination_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """生成 HTML 用的并行 insert/delete 按秒时序数据。"""
    charts: list[dict[str, Any]] = []
    for combo_result in combination_results:
        for case in combo_result.get("cases") or []:
            for metric in case.get("metrics") or []:
                concurrency = int(metric.get("concurrency"))
                write = (case.get("write_by_concurrency") or {}).get(concurrency) or {}
                repo_rows = write.get("repositories") or {}
                for repo_id, repo_row in repo_rows.items():
                    raw_points = {
                        int(point.get("second", 0)): point
                        for point in (repo_row.get("series") or [])
                    }
                    max_ops = max(
                        [
                            int(point.get("insert_ok") or 0)
                            for point in raw_points.values()
                        ] + [
                            int(point.get("delete_ok") or 0)
                            for point in raw_points.values()
                        ] + [1]
                    )
                    points: list[dict[str, Any]] = []
                    last_pool_size = 0
                    for second in range(0, max(1, int(config.total_duration_seconds))):
                        point = raw_points.get(second) or {}
                        insert_ok = int(point.get("insert_ok") or 0)
                        delete_ok = int(point.get("delete_ok") or 0)
                        pool_size = int(point.get("pool_size") or last_pool_size)
                        last_pool_size = pool_size
                        points.append(
                            {
                                "second": second,
                                "insert_ok": insert_ok,
                                "delete_ok": delete_ok,
                                "pool_size": pool_size,
                                "insert_height": max(2, round(64.0 * insert_ok / max_ops)),
                                "delete_height": max(2, round(64.0 * delete_ok / max_ops)),
                            }
                        )
                    charts.append(
                        {
                            "title": (
                                f"{repo_id} | {','.join(case.get('repositories') or [])} | "
                                f"M={case.get('max_candidates')} T={case.get('include_threshold')} "
                                f"C={concurrency}"
                            ),
                            "repo": repo_id,
                            "repositories": list(case.get("repositories") or []),
                            "write_repositories": list(case.get("write_repositories") or []),
                            "max_candidates": int(case.get("max_candidates") or 0),
                            "include_threshold": float(case.get("include_threshold") or 0.0),
                            "concurrency": concurrency,
                            "insert_workers": int(repo_row.get("insert_workers") or config.insert_workers),
                            "delete_workers": int(repo_row.get("delete_workers") or config.delete_workers),
                            "points": points,
                        }
                    )
    return charts


def render_hotspot_report(
    *,
    config: HotspotConfig,
    combination_results: list[dict[str, Any]],
    repo_sizes: dict[str, int | None],
    verify_results: dict[str, dict[str, Any]],
    write_ledger: dict[str, Any],
    failure_count: int,
    generated_at: str,
) -> str:
    parts: list[str] = []
    parts.append("# Search 热点库混合负载性能报告")
    parts.append("")
    parts.append("## 测试目标")
    parts.append("")
    parts.append("- 在写入热点库持续 insert/delete 的同时执行 search，观察锁竞争、资源竞争和延迟退化。")
    parts.append("- 同一 case 先执行纯 search 基线，再立即执行同条件热点库混合负载，二者从同一干净仓库状态开始。")
    parts.append("- 本报告只作为中间 ASCII 报告，由 main.py 汇总到既有 report.html，不单独生成 HTML。")
    parts.append("")
    parts.append("## 基础参数")
    parts.append("")
    case_count = sum(len(item.get("cases") or []) for item in combination_results)
    parts.append(f"[Base URL] : {config.base_url}")
    parts.append("[Endpoint] : /repositories/search")
    parts.append(
        f"[Duration] : hotspot_total={config.total_duration_seconds}s | "
        f"hotspot_warmup={config.measurement_start_offset_seconds}s | "
        f"hotspot_measured={config.measurement_window_seconds}s | "
        f"baseline_warmup={config.baseline_measurement_start_offset_seconds}s | "
        f"baseline_measured={config.baseline_measurement_window_seconds}s"
    )
    parts.append(f"[Case Count] : {case_count}")
    parts.append(f"[Failure Count] : {failure_count}")
    parts.append("")
    parts.append(f"- Base URL：`{config.base_url}`")
    parts.append(f"- 阶段策略：`{config.phase_policy}`")
    parts.append(f"- 阶段顺序：`{' -> '.join(config.phase_order)}`")
    parts.append(f"- 阶段间隔：`{config.phase_gap_seconds}s`")
    hotspot_write_repos = [repo_id for repo_id in WRITE_HOTSPOT_REPOS if repo_id not in NPU_REPOSITORIES]
    parts.append(f"- 写入热点库：`{', '.join(hotspot_write_repos)}`")
    parts.append(f"- NPU baseline-only 库：`{', '.join(sorted(NPU_REPOSITORIES))}`")
    parts.append(f"- 多 NPU 库组合并发上限：`{NPU_MULTI_REPO_CONCURRENCY_CAP}`")
    parts.append("- NPU 单库或包含 NPU 的组合库仅执行 baseline，不生成 hotspot 指标")
    parts.append(f"- 搜索组合：`{config.search_repositories_values}`")
    parts.append(f"- 插入特征文件：`{config.feature_file}`")
    parts.append(f"- 查询特征：特征文件第 1 条（索引 0），长度 {len(config.query_feature)}")
    parts.append(f"- 每库写入 worker：`{config.insert_workers}` insert + `{config.delete_workers}` delete")
    parts.append("- 写入限速：不使用独立限速器，32 insert + 32 delete worker 持续运行直到 case 结束")
    parts.append("- 写入模式：insert/delete 持续运行；delete 快于 insert 时只等待池中有新实体，不暂停 insert")
    parts.append(f"- 插入特征：全量按 `{config.feature_file}` 顺序循环使用，不复制查询热点特征")
    parts.append(
        f"- case 后清理：使用 cleanup 并发 `{max(1, int(config.cleanup_concurrency))}` 删除剩余实体；"
        "仅记录待清理数、成功删除数、剩余数和耗时"
    )
    parts.append("- 写入池：不预置；每个 case 从干净状态开始，结束后清理剩余实体")
    parts.append(
        f"- 热点测量窗口：前 `{config.measurement_start_offset_seconds}s` 预热，"
        f"后 `{config.measurement_window_seconds}s` 统计"
    )
    parts.append(
        f"- 基线测量窗口：前 `{config.baseline_measurement_start_offset_seconds}s` 预热，"
        f"后 `{config.baseline_measurement_window_seconds}s` 统计"
    )
    parts.append(f"- 生成时间：{generated_at}")
    for repo_id in WRITE_HOTSPOT_REPOS:
        parts.append(f"- 库规模（{repo_id}）：`{repo_sizes.get(repo_id, 'N/A')}`")
    parts.append("")
    parts.append("## 同 case 实时基线")
    parts.append("")
    baseline_rows = sum(
        len(case.get("baseline_metrics") or [])
        for combo_result in combination_results
        for case in (combo_result.get("cases") or [])
    )
    parts.append(f"- 当前进程实时采集基线档位：{baseline_rows} 行")
    parts.append("- 每个并发档的顺序固定为：先 baseline，后 hotspot；二者之间不执行其他写入。")
    parts.append("- hotspot 结束后立即清理本 case 剩余写入实体，再进入下一档。")
    parts.append("")
    parts.append("## 同 case 基线 vs 热点库（顺序对比）")
    parts.append("")
    npu_cases: list[dict[str, Any]] = []
    for combo_result in combination_results:
        for case in combo_result["cases"]:
            if _requires_baseline_only(case["repositories"]):
                npu_cases.append(case)
                continue
            pair_label = (
                f"repositories={','.join(case['repositories'])} | "
                f"max_candidates={case['max_candidates']} | "
                f"include_threshold={case['include_threshold']} | "
                f"write_repositories={','.join(case['write_repositories']) or 'N/A'}"
            )
            parts.append(f"### Hotspot Pair [{pair_label}]")
            parts.append(f"[Hotspot Pair] Parameters : {pair_label}")
            parts.append("")
            parts.append("```text")
            parts.append(
                ascii_report.render_ascii_table(
                    HOTSPOT_PAIR_HEADERS,
                    _pair_rows(case=case),
                )
            )
            parts.append("```")
            parts.append("")
    if npu_cases:
        parts.append("## NPU 基线-only 搜索结果（不执行 hotspot）")
        parts.append("")
        for case in npu_cases:
            label = (
                f"repositories={','.join(case['repositories'])} | "
                f"max_candidates={case['max_candidates']} | "
                f"include_threshold={case['include_threshold']}"
            )
            parts.append(f"### Baseline Only [{label}]")
            parts.append(f"[Baseline Only] Parameters : {label}")
            parts.append("")
            parts.append("```text")
            parts.append(
                ascii_report.render_ascii_table(
                    BASELINE_ONLY_HEADERS,
                    _baseline_only_rows(case),
                )
            )
            parts.append("```")
            parts.append("")
    parts.append("## 并行插库与删除时序")
    parts.append("")
    parts.append("[Hotspot Write Series]")
    parts.append("```json")
    parts.append(json.dumps(_write_series_payload(config, combination_results), ensure_ascii=False))
    parts.append("```")
    parts.append("")
    parts.append("## 各并发梯度核心指标表（mixed）")
    parts.append("")
    for combo_result in combination_results:
        for case in combo_result["cases"]:
            if _requires_baseline_only(case["repositories"]):
                continue
            params = (
                f"repositories={','.join(case['repositories'])} | "
                f"max_candidates={case['max_candidates']} | "
                f"include_threshold={case['include_threshold']} | "
                f"write_repositories={','.join(case['write_repositories']) or 'N/A'}"
            )
            parts.append(f"### Case search_mixed@{','.join(case['repositories'])} "
                         f"[max_candidates={case['max_candidates']} | include_threshold={case['include_threshold']}]")
            parts.append(f"[Case] Parameters : {params}")
            parts.append("")
            parts.append("```text")
            parts.append(ascii_report.render_metrics_table(case.get("metrics") or []))
            parts.append("```")
            parts.append("")
    parts.append("## 写入压力台账")
    parts.append("")
    parts.append("```text")
    parts.append(
        ascii_report.render_ascii_table(
            ["repo", "预置", "insert_ok", "insert_fail", "delete_ok", "delete_fail", "insert/s", "delete/s", "总 ops/s", "成功率", "insert P95", "delete P95"],
            [
                [
                    repo_id,
                    ascii_report.format_int(row.get("preloaded")),
                    ascii_report.format_int(row.get("insert_ok")),
                    ascii_report.format_int(row.get("insert_fail")),
                    ascii_report.format_int(row.get("delete_ok")),
                    ascii_report.format_int(row.get("delete_fail")),
                    ascii_report.format_number(row.get("insert_ops_per_second")),
                    ascii_report.format_number(row.get("delete_ops_per_second")),
                    ascii_report.format_number(row.get("ops_per_second")),
                    ascii_report.format_percent(row.get("success_rate")),
                    ascii_report.format_latency(row.get("insert_p95_ms")),
                    ascii_report.format_latency(row.get("delete_p95_ms")),
                ]
                for repo_id, row in (write_ledger.get("repositories") or {}).items()
                if repo_id not in NPU_REPOSITORIES
            ],
        )
    )
    parts.append("```")
    parts.append("")
    parts.append("## 校验 VERIFY")
    parts.append("")
    parts.append("```text")
    parts.append(
        ascii_report.render_ascii_table(
            ["repo", "可见性 hits/probes", "命中实体数", "可见性结果", "已删样本", "stale 命中", "stale 结果"],
            [
                [
                    repo_id,
                    f"{info.get('visibility', {}).get('probes_with_hit', 0)}/{info.get('visibility', {}).get('probe_count', 0)}",
                    ascii_report.format_int(info.get("visibility", {}).get("distinct_seeded_ids_seen")),
                    _verify_label(info.get("visibility", {}).get("pass")),
                    ascii_report.format_int(info.get("stale", {}).get("deleted_ids_checked")),
                    ascii_report.format_int(info.get("stale", {}).get("stale_hits")),
                    _verify_label(info.get("stale", {}).get("pass")),
                ]
                for repo_id, info in verify_results.items()
            ],
        )
    )
    parts.append("```")
    parts.append("- 校验为低并发探针，不计入 search 指标；stale 校验要求无失败探针且无 stale 命中。")
    parts.append("")
    parts.append("## 失败请求摘要")
    parts.append("")
    parts.append(f"- baseline + hotspot 失败请求数：{failure_count}")
    parts.append(f"- 明细见同目录 `{FAILURES_FILENAME}`")
    parts.append("")
    parts.append("## 产物索引")
    parts.append("")
    parts.append(f"- `{REPORT_FILENAME}`")
    parts.append(f"- `{FAILURES_FILENAME}`")
    parts.append("- `write_ledger.json`")
    parts.append("- `verify.json`")
    parts.append("- `insert_delete_timings.json`")
    parts.append("")
    return "\n".join(parts)


# ---------------------------------------------------------------- 编排
def _write_repositories_for_search(repositories: list[str]) -> list[str]:
    return [repo_id for repo_id in repositories if repo_id in WRITE_HOTSPOT_REPOS]


def _requires_baseline_only(repositories: list[str]) -> bool:
    return bool(set(str(item) for item in repositories) & NPU_REPOSITORIES)


def _skipped_hotspot_metric(
    *,
    repositories: list[str],
    max_candidates: int,
    include_threshold: float,
    concurrency: int,
) -> dict[str, Any]:
    return {
        "concurrency": int(concurrency),
        "total_requests": None,
        "success_count": None,
        "failure_count": None,
        "success_rate": None,
        "error_rate": None,
        "throughput_rps": None,
        "latency_p50_ms": None,
        "latency_avg_ms": None,
        "latency_p95_ms": None,
        "latency_p99_ms": None,
        "latency_max_ms": None,
        "timeout_count": None,
        "connection_error_count": None,
        "repositories": list(repositories),
        "write_repositories": [],
        "max_candidates": int(max_candidates),
        "include_threshold": float(include_threshold),
        "phase": "hotspot",
        "hotspot_skipped": True,
        "skip_reason": "NPU repository baseline-only",
    }


def _cleanup_repo_pools(
    *,
    config: HotspotConfig,
    repo_ids: list[str],
    repo_states: dict[str, dict[str, Any]],
    all_timings: list[dict[str, Any]],
    max_rounds: int = 5,
) -> dict[str, Any]:
    """在 case 结束后清理该 case 期间没有来得及被 delete worker 删除的实体。"""

    started = time.perf_counter()
    repo_stats: dict[str, dict[str, Any]] = {}
    for repo_id in repo_ids:
        state = repo_states.get(repo_id)
        if not state:
            continue
        pool: WritePool = state["pool"]
        initial_count = len(pool.items)
        deleted_count = 0
        repo_started = time.perf_counter()
        for attempt in range(max_rounds):
            items = list(pool.items)
            if not items:
                break
            timings = asyncio.run(
                cleanup_pool_async(config=config, repo_id=repo_id, items=items)
            )
            all_timings.extend(timings)
            succeeded = {
                str(item.get("entity_id"))
                for item in timings
                if item.get("entity_id") is not None
                and (
                    item.get("ok")
                    or int(item.get("status") or 0) in {200, 202, 204, 404}
                )
            }
            pool.items = deque(
                item for item in pool.items if item.entity_id not in succeeded
            )
            deleted_count += len(succeeded)
            if not pool.items:
                break
            if attempt == max_rounds - 1:
                raise RuntimeError(
                    f"failed to clean hotspot pool for {repo_id}: remaining={len(pool.items)}"
                )
        repo_elapsed = max(time.perf_counter() - repo_started, 0.0)
        repo_stats[repo_id] = {
            "leftover_before_cleanup": initial_count,
            "deleted": deleted_count,
            "remaining": len(pool.items),
            "elapsed_s": round(repo_elapsed, 3),
        }
    total_elapsed = max(time.perf_counter() - started, 0.0)
    total_deleted = sum(int(row.get("deleted") or 0) for row in repo_stats.values())
    return {
        "repositories": repo_stats,
        "leftover_before_cleanup": sum(
            int(row.get("leftover_before_cleanup") or 0) for row in repo_stats.values()
        ),
        "deleted": total_deleted,
        "remaining": sum(int(row.get("remaining") or 0) for row in repo_stats.values()),
        "elapsed_s": round(total_elapsed, 3),
    }


def run_hotspot_benchmark(config: HotspotConfig | None = None) -> tuple[Path, dict[str, Any]]:
    config = config or HotspotConfig()
    config.feature_file = Path(config.feature_file).expanduser()
    if not config.feature_file.exists():
        raise FileNotFoundError(f"feature file not found: {config.feature_file}")
    config.query_feature = read_first_feature(config.feature_file)

    out_dir = Path(config.report_output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    repo_sizes = asyncio.run(fetch_repo_sizes_async(config))

    repo_states: dict[str, dict[str, Any]] = {}
    all_timings: list[dict[str, Any]] = []
    verify_results: dict[str, dict[str, Any]] = {}
    for repo_id in WRITE_HOTSPOT_REPOS:
        # v8：不预置写入池。每个 case 都从干净状态开始，hotspot 阶段再持续 insert/delete。
        repo_states[repo_id] = {
            "cursor": FeatureCursor(config.feature_file),
            "pool": WritePool(repo_id=repo_id),
            "preloaded": 0,
        }
        verify_results[repo_id] = {
            "visibility": {
                "pass": None,
                "note": "v8 改为 case 后清理并连续写入，未使用预置池可见性探针",
            },
        }

    combination_results: list[dict[str, Any]] = []
    all_failures: list[dict[str, Any]] = []
    staged_baseline: dict[tuple[Any, ...], tuple[dict[str, Any], list[dict[str, Any]]]] = {}

    if config.phase_policy == "staged":
        print(
            "[hotspot] staged policy: running all baseline cases first, "
            "then running all hotspot cases after baseline completes",
            flush=True,
        )
        for repositories in config.search_repositories_values:
            repositories = [str(item) for item in repositories]
            write_repositories = _write_repositories_for_search(repositories)
            for max_candidates in config.max_candidates_values:
                for include_threshold in config.include_threshold_values:
                    for concurrency in config.concurrency_for(
                        repositories, max_candidates=int(max_candidates)
                    ):
                        _cleanup_repo_pools(
                            config=config,
                            repo_ids=write_repositories,
                            repo_states=repo_states,
                            all_timings=all_timings,
                        )
                        baseline_metric, baseline_failures, _baseline_write, _elapsed = run_search_tier(
                            config=config,
                            search_repositories=repositories,
                            write_repositories=[],
                            max_candidates=int(max_candidates),
                            include_threshold=float(include_threshold),
                            concurrency=int(concurrency),
                            repo_states=repo_states,
                            phase="baseline",
                            measurement_start_offset_seconds=config.baseline_measurement_start_offset_seconds,
                            measurement_window_seconds=config.baseline_measurement_window_seconds,
                        )
                        key = (
                            tuple(repositories),
                            int(max_candidates),
                            float(include_threshold),
                            int(concurrency),
                        )
                        staged_baseline[key] = (baseline_metric, baseline_failures)
                        print(
                            f"[hotspot] baseline repos={','.join(repositories)} M={max_candidates} "
                            f"T={include_threshold} c={concurrency} "
                            f"QPS={baseline_metric.get('throughput_rps')} "
                            f"P95={baseline_metric.get('latency_p95_ms')}",
                            flush=True,
                        )
        if config.phase_gap_seconds > 0:
            print(f"[hotspot] staged gap: sleeping {config.phase_gap_seconds}s", flush=True)
            time.sleep(int(config.phase_gap_seconds))

    for repositories in config.search_repositories_values:
        repositories = [str(item) for item in repositories]
        write_repositories = _write_repositories_for_search(repositories)
        cases: list[dict[str, Any]] = []
        for max_candidates in config.max_candidates_values:
            for include_threshold in config.include_threshold_values:
                baseline_metrics: list[dict[str, Any]] = []
                metrics: list[dict[str, Any]] = []
                write_by_concurrency: dict[int, dict[str, Any]] = {}
                for concurrency in config.concurrency_for(
                    repositories, max_candidates=int(max_candidates)
                ):
                    # 每个并发档开始前清理，保证第一个阶段从干净仓库状态开始。
                    _cleanup_repo_pools(
                        config=config,
                        repo_ids=write_repositories,
                        repo_states=repo_states,
                        all_timings=all_timings,
                    )

                    for phase in config.phase_order:
                        phase = str(phase).strip().lower()
                        if phase == "baseline":
                            key = (
                                tuple(repositories),
                                int(max_candidates),
                                float(include_threshold),
                                int(concurrency),
                            )
                            if config.phase_policy == "staged":
                                baseline_metric, baseline_failures = staged_baseline[key]
                                baseline_metrics.append(baseline_metric)
                                all_failures.extend(baseline_failures)
                                print(
                                    f"[hotspot] baseline-cached repos={','.join(repositories)} "
                                    f"M={max_candidates} T={include_threshold} c={concurrency} "
                                    f"QPS={baseline_metric.get('throughput_rps')} "
                                    f"P95={baseline_metric.get('latency_p95_ms')}"
                                )
                                continue
                            baseline_metric, baseline_failures, _baseline_write, _elapsed = run_search_tier(
                                config=config,
                                search_repositories=repositories,
                                write_repositories=[],
                                max_candidates=int(max_candidates),
                                include_threshold=float(include_threshold),
                                concurrency=int(concurrency),
                                repo_states=repo_states,
                                phase="baseline",
                                measurement_start_offset_seconds=config.baseline_measurement_start_offset_seconds,
                                measurement_window_seconds=config.baseline_measurement_window_seconds,
                            )
                            baseline_metrics.append(baseline_metric)
                            all_failures.extend(baseline_failures)
                            print(
                                f"[hotspot] baseline repos={','.join(repositories)} M={max_candidates} "
                                f"T={include_threshold} c={concurrency} "
                                f"QPS={baseline_metric.get('throughput_rps')} "
                                f"P95={baseline_metric.get('latency_p95_ms')}"
                            )
                            continue

                        if phase != "hotspot":
                            raise ValueError(f"unsupported search phase order entry: {phase}")
                        if _requires_baseline_only(repositories):
                            metrics.append(
                                _skipped_hotspot_metric(
                                    repositories=repositories,
                                    max_candidates=int(max_candidates),
                                    include_threshold=float(include_threshold),
                                    concurrency=int(concurrency),
                                )
                            )
                            print(
                                f"[hotspot] skipped-hotspot repos={','.join(repositories)} "
                                f"M={max_candidates} T={include_threshold} c={concurrency} "
                                "reason=NPU repository baseline-only"
                            )
                            continue
                        cleanup_stats: dict[str, Any] = {}
                        try:
                            metric, failures, write, _elapsed = run_search_tier(
                                config=config,
                                search_repositories=repositories,
                                write_repositories=write_repositories,
                                max_candidates=int(max_candidates),
                                include_threshold=float(include_threshold),
                                concurrency=int(concurrency),
                                repo_states=repo_states,
                                phase="hotspot",
                            )
                        finally:
                            # hotspot 结束后清理，baseline 不产生写入实体。
                            cleanup_stats = _cleanup_repo_pools(
                                config=config,
                                repo_ids=write_repositories,
                                repo_states=repo_states,
                                all_timings=all_timings,
                            )

                        metrics.append(metric)
                        aggregate_write = write.get("aggregate") or {}
                        aggregate_write["cleanup"] = cleanup_stats
                        write_by_concurrency[int(concurrency)] = aggregate_write
                        all_failures.extend(failures)
                        print(
                            f"[hotspot] repos={','.join(repositories)} M={max_candidates} "
                            f"T={include_threshold} c={concurrency} "
                            f"QPS={metric.get('throughput_rps')} P95={metric.get('latency_p95_ms')} "
                            f"write={write.get('aggregate', {}).get('ops_per_second', 0)} ops/s "
                            f"cleanup={cleanup_stats.get('leftover_before_cleanup', 0)} "
                            f"elapsed={cleanup_stats.get('elapsed_s', 0)}s"
                        )
                cases.append(
                    {
                        "repositories": list(repositories),
                        "write_repositories": list(write_repositories),
                        "max_candidates": int(max_candidates),
                        "include_threshold": float(include_threshold),
                        "baseline_metrics": baseline_metrics,
                        "metrics": metrics,
                        "write_by_concurrency": write_by_concurrency,
                    }
                )
        combination_results.append({"repositories": list(repositories), "cases": cases})

    # 关闭特征游标，并确认没有 case 遗留的写入实体。
    for repo_id in WRITE_HOTSPOT_REPOS:
        state = repo_states[repo_id]
        pool: WritePool = state["pool"]
        if pool.items:
            raise RuntimeError(f"hotspot pool not empty after cleanup: {repo_id} items={len(pool.items)}")
        state["cursor"].close()

    # 汇总写入台账。
    preloaded_by_repo = {repo_id: int(state.get("preloaded") or 0) for repo_id, state in repo_states.items()}
    write_totals: dict[str, dict[str, Any]] = {
        repo_id: {
            "preloaded": preloaded_by_repo.get(repo_id, 0),
            "insert_ok": 0,
            "insert_fail": 0,
            "delete_ok": 0,
            "delete_fail": 0,
            "window_insert_ok": 0,
            "window_insert_fail": 0,
            "window_delete_ok": 0,
            "window_delete_fail": 0,
            "insert_latencies_ms": [],
            "delete_latencies_ms": [],
            "ops_per_second": 0.0,
            "insert_ops_per_second": 0.0,
            "delete_ops_per_second": 0.0,
            "active_measurement_seconds": 0,
        }
        for repo_id in WRITE_HOTSPOT_REPOS
    }
    for combo_result in combination_results:
        for case in combo_result["cases"]:
            for row in case.get("write_by_concurrency", {}).values():
                for repo_id, repo_row in (row.get("repositories") or {}).items():
                    current = write_totals.setdefault(
                        repo_id,
                        {
                            "preloaded": preloaded_by_repo.get(repo_id, 0),
                            "insert_ok": 0,
                            "insert_fail": 0,
                            "delete_ok": 0,
                            "delete_fail": 0,
                            "window_insert_ok": 0,
                            "window_insert_fail": 0,
                            "window_delete_ok": 0,
                            "window_delete_fail": 0,
                            "insert_latencies_ms": [],
                            "delete_latencies_ms": [],
                            "ops_per_second": 0.0,
                            "insert_ops_per_second": 0.0,
                            "delete_ops_per_second": 0.0,
                            "active_measurement_seconds": 0,
                        },
                    )
                    for key in (
                        "insert_ok",
                        "insert_fail",
                        "delete_ok",
                        "delete_fail",
                        "window_insert_ok",
                        "window_insert_fail",
                        "window_delete_ok",
                        "window_delete_fail",
                    ):
                        current[key] += int(repo_row.get(key) or 0)
                    if repo_row.get("insert_p95_ms") is not None:
                        current["insert_latencies_ms"].append(float(repo_row["insert_p95_ms"]))
                    if repo_row.get("delete_p95_ms") is not None:
                        current["delete_latencies_ms"].append(float(repo_row["delete_p95_ms"]))
                    current["active_measurement_seconds"] += int(config.measurement_window_seconds)
    for repo_id, row in write_totals.items():
        success_ops = int(row["window_insert_ok"] + row["window_delete_ok"])
        failure_ops = int(row["window_insert_fail"] + row["window_delete_fail"])
        total_ops = success_ops + failure_ops
        active_seconds = max(1, int(row.pop("active_measurement_seconds") or 0))
        row["ops_per_second"] = round(total_ops / active_seconds, 3) if total_ops else 0.0
        row["insert_ops_per_second"] = round(
            (row["window_insert_ok"] + row["window_insert_fail"]) / active_seconds, 3
        )
        row["delete_ops_per_second"] = round(
            (row["window_delete_ok"] + row["window_delete_fail"]) / active_seconds, 3
        )
        row["success_rate"] = round(100.0 * success_ops / total_ops, 3) if total_ops else 0.0
        row["insert_p95_ms"] = percentile(row.pop("insert_latencies_ms"), 95)
        row["delete_p95_ms"] = percentile(row.pop("delete_latencies_ms"), 95)

    write_ledger = {"repositories": write_totals}
    report_text = render_hotspot_report(
        config=config,
        combination_results=combination_results,
        repo_sizes=repo_sizes,
        verify_results=verify_results,
        write_ledger=write_ledger,
        failure_count=len(all_failures),
        generated_at=generated_at,
    )
    report_path = out_dir / REPORT_FILENAME
    report_path.write_text(report_text, encoding="utf-8")
    (out_dir / FAILURES_FILENAME).write_text(json.dumps(all_failures, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "write_ledger.json").write_text(
        json.dumps({"repositories": write_totals}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "verify.json").write_text(json.dumps(verify_results, ensure_ascii=False, indent=2), encoding="utf-8")
    sample = all_timings[:200] + (all_timings[-200:] if len(all_timings) > 400 else all_timings[200:])
    (out_dir / "insert_delete_timings.json").write_text(
        json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary = {
        "generated_at": generated_at,
        "base_url": config.base_url,
        "feature_file": str(config.feature_file),
        "write_hotspot_repos": list(WRITE_HOTSPOT_REPOS),
        "npu_baseline_only_repos": sorted(NPU_REPOSITORIES),
        "npu_multi_repo_concurrency_cap": NPU_MULTI_REPO_CONCURRENCY_CAP,
        "search_repositories_values": config.search_repositories_values,
        "concurrency_values": config.concurrency_values,
        "max_candidates_values": config.max_candidates_values,
        "include_threshold_values": config.include_threshold_values,
        "repo_sizes": repo_sizes,
        "combination_results": combination_results,
        "baseline_mode": "inline_same_case",
        "baseline_case_count": sum(
            len(case.get("baseline_metrics") or [])
            for combo_result in combination_results
            for case in (combo_result.get("cases") or [])
        ),
        "verify": verify_results,
        "failure_count": len(all_failures),
        "output_dir": str(out_dir),
    }
    print(f"[hotspot] Report written to: {report_path}")
    return report_path, summary


def build_runtime_hotspot_config() -> HotspotConfig:
    config = HotspotConfig()
    config.baseline_measurement_start_offset_seconds = int(
        os.environ.get(
            "SEARCH_HOTSPOT_BASELINE_WARMUP",
            str(config.baseline_measurement_start_offset_seconds),
        )
    )
    config.baseline_measurement_window_seconds = int(
        os.environ.get(
            "SEARCH_HOTSPOT_BASELINE_MEASUREMENT_WINDOW",
            str(config.baseline_measurement_window_seconds),
        )
    )
    phase_order_raw = os.environ.get("SEARCH_HOTSPOT_PHASE_ORDER", "baseline,hotspot")
    phase_order = tuple(
        item.strip().lower()
        for item in phase_order_raw.split(",")
        if item.strip()
    )
    if len(phase_order) != 2 or set(phase_order) != {"baseline", "hotspot"}:
        raise ValueError(
            "SEARCH_HOTSPOT_PHASE_ORDER must contain baseline and hotspot exactly once"
        )
    config.phase_order = phase_order
    config.phase_policy = os.environ.get("SEARCH_HOTSPOT_PHASE_POLICY", "staged").strip().lower()
    config.phase_gap_seconds = int(os.environ.get("SEARCH_HOTSPOT_PHASE_GAP_SECONDS", "0"))
    if config.phase_policy not in {"inline", "staged"}:
        raise ValueError("SEARCH_HOTSPOT_PHASE_POLICY must be inline or staged")
    if config.phase_policy == "staged":
        config.phase_order = ("baseline", "hotspot")
    if os.environ.get("SEARCH_HOTSPOT_SINGLE_CASE", "0").lower() not in ("1", "true", "yes"):
        return config

    repositories = [
        item.strip()
        for item in os.environ.get("SEARCH_HOTSPOT_CASE_REPOSITORIES", "3kwfacerepo_test").split(",")
        if item.strip()
    ]
    config.search_repositories_values = [repositories]
    config.max_candidates_values = [int(os.environ.get("SEARCH_HOTSPOT_CASE_MAX_CANDIDATES", "1"))]
    config.include_threshold_values = [float(os.environ.get("SEARCH_HOTSPOT_CASE_THRESHOLD", "0.5"))]
    config.concurrency_values = [int(os.environ.get("SEARCH_HOTSPOT_CASE_CONCURRENCY", "32"))]
    config.total_duration_seconds = int(
        os.environ.get("SEARCH_HOTSPOT_TOTAL_DURATION", str(config.total_duration_seconds))
    )
    config.measurement_start_offset_seconds = int(
        os.environ.get("SEARCH_HOTSPOT_MEASUREMENT_OFFSET", str(config.measurement_start_offset_seconds))
    )
    config.measurement_window_seconds = int(
        os.environ.get("SEARCH_HOTSPOT_MEASUREMENT_WINDOW", str(config.measurement_window_seconds))
    )
    return config


def main() -> int:
    run_hotspot_benchmark(build_runtime_hotspot_config())
    return 0


__all__ = [
    "FeatureCursor",
    "HotspotConfig",
    "WritePool",
    "WriteTierStats",
    "build_entity_template",
    "build_search_template",
    "cleanup_pool_async",
    "find_baseline_reports",
    "load_baselines",
    "match_baseline_row",
    "normalize_baseline_row",
    "parse_case_parameters",
    "prepare_write_pool_async",
    "render_hotspot_report",
    "run_hotspot_benchmark",
    "run_search_tier",
    "verify_stale_async",
    "verify_visibility_async",
]


if __name__ == "__main__":
    raise SystemExit(main())
