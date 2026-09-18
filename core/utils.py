"""提供 JSON 读取、时间戳与轮询能力的通用工具模块。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, TypeVar


T = TypeVar("T")


# 实现当前模块的核心逻辑。
def find_project_root(path: Path) -> Path | None:
    for candidate in [path, *path.parents]:
        if candidate.is_dir() and (candidate / "test_project_conventions.py").is_file():
            return candidate
    return None


# 实现当前模块的核心逻辑。
def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


# 加载当前场景所需的数据或模板。
def load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# 加载当前场景所需的数据或模板。
def load_case_entries(path: Path) -> list[dict[str, Any]]:
    payload = load_json_file(path)
    return [item for item in payload if isinstance(item, dict) and "__summary__" not in item]


# 确保运行时输出目录带有简要中文说明 README 文件。
def ensure_runtime_readme(directory: Path, description: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    project_root = find_project_root(directory)

    current = directory
    while True:
        readme_path = current / "README.md"
        if not readme_path.exists():
            readme_path.write_text(f"# 运行输出\n\n{description}\n", encoding="utf-8")
        if project_root is None or current == project_root:
            break
        current = current.parent

    return directory / "README.md"


# 持续轮询异步获取函数，直到断言成立或超时。
async def poll_until_ready(
    getter: Callable[[], Awaitable[T]],
    predicate: Callable[[T], bool],
    *,
    timeout_s: float = 30.0,
    interval_s: float = 0.5,
) -> T:
    deadline = asyncio.get_running_loop().time() + timeout_s
    last_value: T | None = None

    while True:
        last_value = await getter()
        if predicate(last_value):
            return last_value
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f"Condition not met within {timeout_s} seconds: {last_value!r}")
        await asyncio.sleep(interval_s)
