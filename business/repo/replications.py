"""用于校验仓库 replications 配置更新的业务场景脚本。"""
# 流程：
# 1. 创建动态 id 的 business-replications-repo-* 仓库，初始 replications=1，预期创建 200/201/202 并等待 READY。
# 2. PUT 将 replications 上调为 7，预期 200/201/202。
# 3. PUT 将 replications 下调为 3，预期 HTTP 400。
# 4. GET，确认 replications 保持上调后的值 7。
# 5. 最后删除测试仓库并轮询确认不存在。
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    repo_root = str(Path(__file__).resolve().parents[3])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

from API_TEST.business.repo._scenario_support import failure_reason_from_body, finalize_repo_summary, poll_and_save, record_case_result
from API_TEST.business.support import build_business_runtime, load_business_config, make_repo_id, open_business_apis


# 内部辅助函数，封装当前模块的局部逻辑。
def _body_dict(record) -> dict[str, object]:
    return record.response_body if isinstance(record.response_body, dict) else {}


# 内部辅助函数，封装当前模块的局部逻辑。
def _replications(record) -> int | None:
    value = _body_dict(record).get("replications")
    return value if isinstance(value, int) else None


# 内部辅助函数，封装当前模块的局部逻辑。
async def _wait_repo_ready(repo_api, store, *, repo_id: str, timeout_s: float = 30.0):
    # 实现当前模块的核心逻辑。
    async def getter():
        return await repo_api.get(None, case_id=f"repo-ready-{repo_id}", module="repo", action="get", name=f"wait repo {repo_id} ready", path=f"/repositories/{repo_id}")

    return await poll_and_save(store, getter, lambda record: record.status_code == 200, timeout_s=timeout_s)


# 内部辅助函数，封装当前模块的局部逻辑。
async def _ensure_repo_deleted(repo_api, store, *, repo_id: str, timeout_s: float = 60.0):
    # 实现当前模块的核心逻辑。
    async def getter():
        return await repo_api.get(None, case_id=f"repo-delete-{repo_id}", module="repo", action="get", name=f"wait repo {repo_id} deleted", path=f"/repositories/{repo_id}")

    return await poll_and_save(store, getter, lambda record: record.status_code in {400, 404}, timeout_s=timeout_s)


# 内部辅助函数，封装当前模块的局部逻辑。
async def _cleanup_repo(repo_api, store, *, repo_id: str) -> None:
    cleanup = await repo_api.delete(None, case_id="cleanup", module="repo", action="delete", name="cleanup replications repo", path=f"/repositories/{repo_id}")
    store.save(cleanup)
    if cleanup.status_code not in {200, 202, 204, 404}:
        raise RuntimeError(f"expected 200/202/204/404, got {cleanup.status_code}")
    if cleanup.status_code != 404:
        await _ensure_repo_deleted(repo_api, store, repo_id=repo_id, timeout_s=60.0)
    return cleanup


# 执行当前场景的核心流程。
async def run_scenario(*, repo_api, output_root: Path | None = None) -> dict[str, object]:
    config = load_business_config("repo", "replications")
    collector, store, summary_path, _ = build_business_runtime(Path(__file__), "repo", "replications", output_root)
    repo_payload = dict(config["repo"])
    repo_id = make_repo_id(str(repo_payload.pop("id_prefix")))
    repo_payload["id"] = repo_id
    overall_status = "passed"
    case_results: list[dict[str, object]] = []

    try:
        created = await repo_api.create(repo_payload, case_id="create", module="repo", action="create", name="create replications repo", path="/repositories")
        store.save(created)
        create_ok = created.status_code in {200, 201, 202}
        if create_ok:
            collector.record_success("create")
        else:
            overall_status = "failed"
            create_reason = failure_reason_from_body(created.response_body, f"expected 200/201/202, got {created.status_code}")
            collector.record_failure("create", create_reason)
        record_case_result(case_results, prefix="replications", case_id="create", expected_status="200/201/202", actual_status=created.status_code, passed=create_ok, failure_reason=None if create_ok else create_reason)

        ready = await _wait_repo_ready(repo_api, store, repo_id=repo_id, timeout_s=30.0)
        ready_ok = ready.status_code == 200
        if ready_ok:
            collector.record_success("ready")
        else:
            overall_status = "failed"
            ready_reason = failure_reason_from_body(ready.response_body, f"expected 200, got {ready.status_code}")
            collector.record_failure("ready", ready_reason)
        record_case_result(case_results, prefix="replications", case_id=f"repo-ready-{repo_id}", expected_status=200, actual_status=ready.status_code, passed=ready_ok, failure_reason=None if ready_ok else ready_reason)

        up_result = await repo_api.update({"id": repo_id, "replications": 7}, case_id="update-up", module="repo", action="update", name="increase replications", path="/repositories")
        store.save(up_result)
        up_ok = up_result.status_code in {200, 201, 202}
        if up_ok:
            collector.record_success("update_up")
        else:
            overall_status = "failed"
            up_reason = failure_reason_from_body(up_result.response_body, f"expected 200/201/202, got {up_result.status_code}")
            collector.record_failure("update_up", up_reason)
        record_case_result(case_results, prefix="replications", case_id="update-up", expected_status="200/201/202", actual_status=up_result.status_code, passed=up_ok, failure_reason=None if up_ok else up_reason)

        down_result = await repo_api.update({"id": repo_id, "replications": 3}, case_id="update-down", module="repo", action="update", name="decrease replications", path="/repositories")
        store.save(down_result)
        down_ok = down_result.status_code == 400
        if down_ok:
            collector.record_success("update_down")
        else:
            overall_status = "failed"
            down_reason = failure_reason_from_body(down_result.response_body, f"expected 400, got {down_result.status_code}")
            collector.record_failure("update_down", down_reason)
        record_case_result(case_results, prefix="replications", case_id="update-down", expected_status=400, actual_status=down_result.status_code, passed=down_ok, failure_reason=None if down_ok else down_reason)

        repo_after_down = await repo_api.get(None, case_id="repo-after-down", module="repo", action="get", name="get replications after down", path=f"/repositories/{repo_id}")
        store.save(repo_after_down)
        current_replications = _replications(repo_after_down)
        down_state_ok = current_replications == 7
        if down_state_ok:
            collector.record_success("replications_after_down")
        else:
            overall_status = "failed"
            down_state_reason = failure_reason_from_body(repo_after_down.response_body, f"expected replications 7, got {current_replications}")
            collector.record_failure("replications_after_down", down_state_reason)
        record_case_result(case_results, prefix="replications", case_id="repo-after-down", expected_status=7, actual_status=current_replications, passed=down_state_ok, failure_reason=None if down_state_ok else down_state_reason)
    except Exception as exc:
        overall_status = "failed"
        collector.record_failure("replications", str(exc))
        record_case_result(case_results, prefix="replications", case_id="scenario-error", expected_status="no exception", actual_status=None, passed=False, failure_reason=str(exc))
    finally:
        try:
            cleanup_record = await _cleanup_repo(repo_api, store, repo_id=repo_id)
            collector.record_success("cleanup")
            record_case_result(case_results, prefix="replications", case_id="cleanup", expected_status="200/202/204/404", actual_status=cleanup_record.status_code, passed=True, failure_reason=None)
        except Exception as exc:
            overall_status = "failed"
            collector.record_failure("cleanup", str(exc))
            record_case_result(case_results, prefix="replications", case_id="cleanup-error", expected_status="cleanup ok", actual_status=None, passed=False, failure_reason=str(exc))
        summary = finalize_repo_summary(collector, summary_path, overall_status=overall_status, extra={"repo_id": repo_id, "case_total": len(case_results), "case_results": case_results})

    return summary


# 程序入口，用于串起当前模块的执行流程。
async def main() -> None:
    async with open_business_apis(repo=True) as apis:
        summary = await run_scenario(repo_api=apis["repo_api"])
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if os.environ.get("API_TEST_IMPORT_ONLY") == "1":
        raise SystemExit(0)
    asyncio.run(main())
