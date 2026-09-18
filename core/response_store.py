"""负责持久化写出 API_TEST 运行期响应归档的模块。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from API_TEST.core.models import HttpResponseRecord

class ResponseStore:
    """按场景维度写出扁平响应归档。"""

    # 初始化当前对象的状态。
    def __init__(self, root_dir: Path):
        self.root_dir = Path(root_dir)
        self._file: Path | None = None
        self._records: list[dict[str, Any]] = []
        self._generated_at: str | None = None

    # 内部辅助函数，封装当前模块的局部逻辑。
    def _build_output_file(self) -> Path:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        if self._file is None:
            self._generated_at = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            self._file = self.root_dir / f"response_{self._generated_at}.json"
        return self._file

    # 实现当前模块的核心逻辑。
    def save(self, record: HttpResponseRecord) -> Path:
        output_path = self._build_output_file()
        self._records.append(record.to_dict())
        payload = {
            "generated_at": self._generated_at,
            "count": len(self._records),
            "responses": self._records,
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return output_path
