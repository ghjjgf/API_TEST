"""定义接口响应与结构化测试汇总数据模型的模块。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class HttpResponseRecord:
    """用于描述每次 Python 侧接口调用的规范化响应记录。"""

    case_id: str
    module: str
    action: str
    name: str
    method: str
    path: str
    payload: dict[str, Any] | None
    status_code: int | None
    response_body: Any
    elapsed_ms: float
    error_type: str | None
    timestamp: str

    # 实现当前模块的核心逻辑。
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SummaryItem:
    """结构化汇总中存储的单条通过或失败结果。"""

    case_id: str
    status: str
    detail: str | None = None

    # 实现当前模块的核心逻辑。
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SummaryPayload:
    """供测试与场景脚本共用的结构化汇总载荷。"""

    name: str
    module: str
    action_or_scenario: str
    total: int
    passed: int
    failed: int
    duration_ms: float
    failed_items: list[SummaryItem] = field(default_factory=list)
    response_archive_dir: str | None = None
    generated_at: str = ""

    # 实现当前模块的核心逻辑。
    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["failed_items"] = [item.to_dict() for item in self.failed_items]
        return payload
