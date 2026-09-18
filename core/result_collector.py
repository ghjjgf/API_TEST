"""负责测试、场景与压测结果聚合的结构化汇总模块。"""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

from API_TEST.core.models import SummaryItem, SummaryPayload
from API_TEST.core.utils import utc_timestamp


class ResultCollector:
    """汇总通过/失败结果并写出汇总文件。"""

    # 初始化当前对象的状态。
    def __init__(self, *, name: str, module: str, action_or_scenario: str, output_path: Path, response_archive_dir: str | None = None):
        self.name = name
        self.module = module
        self.action_or_scenario = action_or_scenario
        self.output_path = Path(output_path)
        self.response_archive_dir = response_archive_dir
        self._started_at = perf_counter()
        self._passed = 0
        self._failed_items: list[SummaryItem] = []
        self._total = 0

    # 记录一条通过的测试或场景步骤。
    def record_success(self, case_id: str) -> None:
        self._total += 1
        self._passed += 1

    # 记录一条失败的测试或场景步骤。
    def record_failure(self, case_id: str, detail: str) -> None:
        self._total += 1
        self._failed_items.append(SummaryItem(case_id=case_id, status="failed", detail=detail))

    # 构造当前场景所需的数据。
    def build_summary(self) -> SummaryPayload:
        duration_ms = (perf_counter() - self._started_at) * 1000
        return SummaryPayload(
            name=self.name,
            module=self.module,
            action_or_scenario=self.action_or_scenario,
            total=self._total,
            passed=self._passed,
            failed=len(self._failed_items),
            duration_ms=duration_ms,
            failed_items=self._failed_items,
            response_archive_dir=self.response_archive_dir,
            generated_at=utc_timestamp(),
        )

    # 写入当前场景输出文件。
    def write_summary(self) -> Path:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        summary = self.build_summary()
        self.output_path.write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return self.output_path
