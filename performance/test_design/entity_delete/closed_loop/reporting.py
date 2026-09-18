from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ...common.ascii_report import render_metrics_table


# 内部辅助函数，封装当前模块的局部逻辑。
def _build_report_stamp(bundle: dict[str, Any]) -> str:
    raw = bundle.get("generated_at")
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return parsed.strftime("%Y%m%d_%H%M%S_%f")
        except ValueError:
            pass
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


# 渲染当前场景的图表或报告。
def render_delete_report(bundle: dict[str, Any]) -> str:
    insert_summary = bundle.get("insert_summary", {})
    benchmark_status = bundle.get("benchmark_status", "completed")
    repo_ids = bundle.get("repo_ids") or ([bundle.get("repo_id")] if bundle.get("repo_id") else [])
    repo_label = ", ".join(str(item) for item in repo_ids if item) or "multi"

    # 单组并发指标表：统一复用 common.ascii_report，保证与 entity_get / entity_insert 格式一致。
    def _render_case_report_table(case: dict[str, Any]) -> str:
        return render_metrics_table(case.get("metrics", []))

    def _build_metrics_section(case_bundle: dict[str, Any]) -> str:
        stage_metrics_local = sorted(case_bundle.get("stage_metrics", []), key=lambda item: float(item.get("concurrency", 0)))
        if stage_metrics_local:
            parameter_combo_local = case_bundle.get("parameter_combo") or case_bundle.get("scenario_label") or "并发梯度对比"
            case_section_local = {
                "case_id": case_bundle.get("case_id", "case-001"),
                "label": parameter_combo_local,
                "metrics": stage_metrics_local,
            }
            return "\n".join(
                [
                    f"[Case] ID         : {case_section_local['case_id']}",
                    f"[Case] Parameters : {case_section_local['label']}",
                    "",
                    "```text",
                    _render_case_report_table(case_section_local),
                    "```",
                ]
            )
        return "暂无并发指标数据。"

    # 如果是多仓库报告，则为每个仓库单独渲染指标表。
    multi_summary = bundle.get("multi_repo_summary") or {}
    if multi_summary and multi_summary.get("results"):
        per_repo_sections: list[str] = []
        for repo_result in multi_summary.get("results", []):
            repo_id = repo_result.get("repo_id") or (repo_result.get("bundle") or {}).get("repo_id") or "multi"
            repo_bundle = repo_result.get("bundle") or {}
            header = f"### 仓库：{repo_id}\n"
            metrics_section = _build_metrics_section(repo_bundle)
            per_repo_sections.append(header + "\n" + metrics_section)
        metrics_markdown = "\n\n".join(per_repo_sections)
    else:
        metrics_markdown = _build_metrics_section(bundle)
    inflection = bundle.get("inflection_analysis", {})
    failure_summary = bundle.get("failure_summary", {})
    return f"""# Delete Instance Interface Performance Report

## 测试目标

- 验证仓库 `{repo_label}` 在不同并发梯度下的删实例性能表现。

## 测试环境配置

- 生成时间：{bundle['generated_at']}
- Base URL：`{bundle['base_url']}`
- Endpoint：`DELETE {bundle['endpoint']}`

## 插入阶段摘要

- 状态：{benchmark_status}
- 尝试次数：{insert_summary.get('attempts_used', 0)} / {insert_summary.get('max_attempts', 'N/A')}
- 目标实例数：{insert_summary.get('target_entity_count', 0)}
- 已成功插入：{insert_summary.get('inserted_entity_count', 0)}
- 剩余失败数：{insert_summary.get('remaining_failure_count', 0)}
- 中止原因：{insert_summary.get('abort_reason') or 'N/A'}

## 各并发梯度核心指标表

{metrics_markdown}

## 性能拐点分析

- 结论：{inflection.get('narrative')}

## 失败请求摘要

- 总失败数：{failure_summary.get('total_failure_count', 0)}

## 产物索引

- `insert_failures_<stamp>.json`
- `delete_failures_<stamp>.json`
"""


# 写入当前场景输出文件。
def write_report_bundle(output_dir: Path, bundle: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_stamp = _build_report_stamp(bundle)
    # 直接在 output_dir 下写入带 stamp 的文件，避免额外嵌套目录
    report_path = output_dir / f"entity_delete_report_{report_stamp}.md"
    report_path.write_text(render_delete_report(bundle), encoding="utf-8")
    (output_dir / f"insert_failures_{report_stamp}.json").write_text(
        json.dumps(bundle.get("insert_failure_records", []), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (output_dir / f"delete_failures_{report_stamp}.json").write_text(json.dumps(bundle.get("failure_samples", []), ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path
