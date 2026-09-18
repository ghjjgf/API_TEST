"""多仓库性能报告的统一 ASCII 渲染器。

`entity_get` / `entity_insert` / `entity_delete` 的报告格式保持完全一致：

    ### 仓库：<repo_id>

    [Case] ID         : case-001
    [Case] Parameters : 并发梯度对比

    ```text
    Concurrency | Total Req | Success | Failure | Success Rate | ...
    ----------- | --------- | ------- | ------- | ------------ | ...
    1           | 10000     | 10000   | 0       | 100.00%      | ...
    ```

三个接口都复用这里的函数，避免各写一套导致格式漂移。
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

METRIC_HEADERS: tuple[str, ...] = (
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
)

DEFAULT_CASE_ID = "case-001"
DEFAULT_CASE_LABEL = "并发梯度对比"


# 整数格式化：None -> N/A
def format_int(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value)


# 百分比格式化：None -> N/A
def format_percent(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{decimals}f}%"
    except (TypeError, ValueError):
        return str(value)


# 普通数值格式化：整数不带小数位，其余保留两位
def format_number(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "N/A"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.{decimals}f}"


# 延迟格式化：统一带 ms 单位
def format_latency(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{decimals}f} ms"
    except (TypeError, ValueError):
        return str(value)


# 渲染管道分隔的 ASCII 表格（列宽按内容自适应）
def render_ascii_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    header_cells = [str(header) for header in headers]
    normalized_rows: list[list[str]] = []
    source_rows = list(rows) or [["N/A"] * len(header_cells)]
    for row in source_rows:
        cells = [str(cell) for cell in list(row)[: len(header_cells)]]
        if len(cells) < len(header_cells):
            cells.extend([""] * (len(header_cells) - len(cells)))
        normalized_rows.append(cells)

    widths = [len(header) for header in header_cells]
    for row in normalized_rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def render_row(cells: list[str]) -> str:
        return " | ".join(cell.ljust(widths[index]) for index, cell in enumerate(cells))

    separator = " | ".join("-" * width for width in widths)
    return "\n".join([render_row(header_cells), separator, *(render_row(row) for row in normalized_rows)])


# 把一条并发指标转成表格行
def build_metric_row(metric: dict[str, Any]) -> list[str]:
    qps_value = metric.get("qps")
    if qps_value is None:
        qps_value = metric.get("throughput_rps")
    return [
        format_int(metric.get("concurrency")),
        format_int(metric.get("total_requests")),
        format_int(metric.get("success_count")),
        format_int(metric.get("failure_count")),
        format_percent(metric.get("success_rate")),
        format_percent(metric.get("error_rate")),
        format_number(qps_value),
        format_latency(metric.get("latency_p50_ms")),
        format_latency(metric.get("latency_avg_ms")),
        format_latency(metric.get("latency_p95_ms")),
        format_latency(metric.get("latency_p99_ms")),
        format_latency(metric.get("latency_max_ms")),
        format_int(metric.get("timeout_count", 0)),
        format_int(metric.get("connection_error_count", 0)),
    ]


# 渲染单组并发指标表
def render_metrics_table(metrics: Sequence[dict[str, Any]] | None) -> str:
    rows = [build_metric_row(metric) for metric in (metrics or [])]
    return render_ascii_table(list(METRIC_HEADERS), rows)


# 渲染一个 [Case] 块（含 ```text 表格围栏）
def render_case_block(
    metrics: Sequence[dict[str, Any]] | None,
    *,
    case_id: str = DEFAULT_CASE_ID,
    label: str = DEFAULT_CASE_LABEL,
) -> str:
    return "\n".join(
        [
            f"[Case] ID         : {case_id}",
            f"[Case] Parameters : {label}",
            "",
            "```text",
            render_metrics_table(metrics),
            "```",
        ]
    )


# 渲染一个仓库小节
def render_repo_block(
    repo_id: str,
    metrics: Sequence[dict[str, Any]] | None,
    *,
    case_id: str = DEFAULT_CASE_ID,
    label: str = DEFAULT_CASE_LABEL,
) -> str:
    return "\n".join(
        [
            f"### 仓库：{repo_id}",
            "",
            render_case_block(metrics, case_id=case_id, label=label),
        ]
    )


# 渲染多仓库指标区（每个仓库一段，互不新建报告）
def render_repo_sections(repo_results: Sequence[dict[str, Any]] | None) -> str:
    blocks: list[str] = []
    for result in repo_results or []:
        blocks.append(
            render_repo_block(
                str(result.get("repo_id") or "multi"),
                result.get("metrics") or [],
                case_id=str(result.get("case_id") or DEFAULT_CASE_ID),
                label=str(result.get("label") or DEFAULT_CASE_LABEL),
            )
        )
    if not blocks:
        blocks.append(render_repo_block("N/A", []))
    return "\n\n".join(blocks)


# 汇总每个仓库的拐点结论
def summarize_inflections(repo_results: Sequence[dict[str, Any]] | None) -> str:
    parts: list[str] = []
    for result in repo_results or []:
        narrative = (result.get("inflection") or {}).get("narrative") if isinstance(result.get("inflection"), dict) else result.get("inflection")
        if not narrative:
            continue
        repo_id = result.get("repo_id") or "multi"
        parts.append(f"{repo_id}：{narrative}")
    return "；".join(parts) if parts else "N/A"


# 渲染完整报告（get / insert / delete 共用骨架）
def render_report(
    *,
    title: str,
    goal: str,
    env_lines: Sequence[str],
    repo_results: Sequence[dict[str, Any]],
    extra_sections: Sequence[tuple[str, Sequence[str]]] = (),
    failure_count: Any = 0,
    artifact_lines: Sequence[str] = (),
) -> str:
    parts: list[str] = [f"# {title}", "", "## 测试目标", "", goal, "", "## 测试环境配置", ""]
    parts.extend(str(line) for line in env_lines)
    for heading, lines in extra_sections:
        parts.extend(["", f"## {heading}", ""])
        parts.extend(str(line) for line in lines)
    parts.extend(
        [
            "",
            "## 各并发梯度核心指标表",
            "",
            render_repo_sections(repo_results),
            "",
            "## 性能拐点分析",
            "",
            f"- 结论：{summarize_inflections(repo_results)}",
            "",
            "## 失败请求摘要",
            "",
            f"- 总失败数：{format_int(failure_count)}",
            "",
            "## 产物索引",
            "",
        ]
    )
    artifacts = list(artifact_lines) or ["`failures.json`"]
    parts.extend(str(line) for line in artifacts)
    return "\n".join(parts) + "\n"


__all__ = [
    "METRIC_HEADERS",
    "DEFAULT_CASE_ID",
    "DEFAULT_CASE_LABEL",
    "build_metric_row",
    "format_int",
    "format_latency",
    "format_number",
    "format_percent",
    "render_ascii_table",
    "render_case_block",
    "render_metrics_table",
    "render_report",
    "render_repo_block",
    "render_repo_sections",
    "summarize_inflections",
]
