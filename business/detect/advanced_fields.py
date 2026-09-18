"""用于校验 detect 服务复杂字段调用链路的业务场景脚本。

    流程：
        1. 使用 image.url + user_object 的独立 payload 调用检测接口，断言 HTTP 200。
        2. 使用 image.url + rois_polygon 的独立 payload 调用检测接口，断言 HTTP 200。
        3. 两个 payload 相互独立，后一个请求不会继承前一个请求的字段。

"""

from __future__ import annotations

import asyncio
import json
import os
from copy import deepcopy
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    repo_root = str(Path(__file__).resolve().parents[3])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

from API_TEST.business.support import build_business_runtime, finalize_business_summary, load_business_config, open_business_apis


# 构造当前场景所需的数据。
def build_detect_payload(case: dict[str, object]) -> dict[str, object]:
    return deepcopy(case["payload"])


# 执行当前场景的核心流程。
async def run_scenario(*, detect_api, output_root: Path | None = None) -> dict[str, object]:
    config = load_business_config("detect", "advanced_fields")
    collector, store, summary_path, _ = build_business_runtime(Path(__file__), "detect", "advanced_fields", output_root)
    overall_status = "passed"

    try:
        for case in config["cases"]:
            payload = build_detect_payload(case)
            record = await detect_api.run(
                payload,
                case_id=case["case_id"],
                module="detect",
                action="run",
                name=case["name"],
                method=case["method"],
                path=case["path"],
            )
            store.save(record)
            assert record.status_code == 200, record.response_body
            collector.record_success(case["case_id"])
    except Exception as exc:
        overall_status = "failed"
        collector.record_failure("advanced_fields", str(exc))
    finally:
        summary = finalize_business_summary(collector, summary_path, overall_status=overall_status, extra={"case_total": len(config["cases"])})

    if overall_status != "passed":
        raise AssertionError(summary)
    return summary


# 程序入口，用于串起当前模块的执行流程。
async def main() -> None:
    async with open_business_apis(detect=True) as apis:
        summary = await run_scenario(detect_api=apis["detect_api"])
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if os.environ.get("API_TEST_IMPORT_ONLY") == "1":
        raise SystemExit(0)
    asyncio.run(main())
