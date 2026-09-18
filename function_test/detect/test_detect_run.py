"""用于校验 API_TEST MVP 矩阵下检测执行场景的真实接口测试模块。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from API_TEST.function_test.detect.detect_checks import describe_detect_any_of, evaluate_detect_expectations
from API_TEST.function_test.support import load_function_cases


CASE_FILE = Path(__file__).resolve().parents[2] / "data" / "detect" / "function" / "run" / "cases.json"
CASES = load_function_cases(CASE_FILE)


# 为每个检测用例构造独立载荷副本，避免参数化执行之间相互污染。
def build_detect_payload(case: dict[str, object]) -> dict[str, object]:
    return deepcopy(case["payload"])


# 测试当前用例的预期行为。
@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
async def test_detect_run(case, detect_api, response_store_factory, summary_factory) -> None:
    collector = summary_factory("detect run", "detect", "run")
    store = response_store_factory()
    payload = build_detect_payload(case)

    try:
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

        assert record.status_code == case["expected"]["status_code"]

        # 用例声明的字段级规则（expected.detect_any_of / detect_all_empty）在此求值：
        # - DT-TYPE-VALID-001：Faces 非空 / NonMotorVehicles[].HasFace=true /
        #   NonMotorVehicles[].Passengers 非空 / Pedestrian[].Face 有值，任一命中即通过
        # - DT-UO/ROI/IO-VALID-001：Faces、NonMotorVehicles、Pedestrian 都必须为空
        field_verdict = evaluate_detect_expectations(case.get("expected"), record.response_body)
        if field_verdict is False:
            detail = describe_detect_any_of(case.get("expected"), record.response_body)
            raise AssertionError(
                "detect 结果字段校验未通过：以下任一条件成立即算通过\n" + detail
            )

        collector.record_success(case["case_id"])
    except AssertionError as exc:
        collector.record_failure(case["case_id"], str(exc))
        raise
    finally:
        collector.write_summary()
