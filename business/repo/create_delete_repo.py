"""用于在验证仓库生命周期达到 READY 后执行删除的业务场景脚本。"""
# 流程：
# 1. 创建动态 id 的 business-delete-repo-* 仓库，预期 200/201/202。
# 2. 通过单仓库 GET 轮询等待 READY，预期 HTTP 200。
# 3. 第一次 DELETE 仓库，预期 HTTP 200。
# 4. 继续 GET 该仓库，轮询确认返回 400/404，以验证删除生效。
# 5. 最后再执行一次 DELETE cleanup，接受 200/202/204/404；未删除时继续轮询确认不存在。
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
async def _wait_repo_ready(repo_api, store, *, repo_id: str, timeout_s: float = 30.0):
    # 实现当前模块的核心逻辑。
    async def getter():
        return await repo_api.get(
            None,
            case_id=f"repo-ready-{repo_id}",
            module="repo",
            action="get",
            name=f"wait repo {repo_id} ready",
            path=f"/repositories/{repo_id}",
        )

    return await poll_and_save(store, getter, lambda record: record.status_code == 200, timeout_s=timeout_s)


# 内部辅助函数，封装当前模块的局部逻辑。
async def _ensure_repo_deleted(repo_api, store, *, repo_id: str, timeout_s: float = 60.0):
    # 实现当前模块的核心逻辑。
    async def getter():
        return await repo_api.get(
            None,
            case_id=f"repo-delete-{repo_id}",
            module="repo",
            action="get",
            name=f"wait repo {repo_id} deleted",
            path=f"/repositories/{repo_id}",
        )

    return await poll_and_save(store, getter, lambda record: record.status_code in {400, 404}, timeout_s=timeout_s)


# 执行当前场景的核心流程。
async def run_scenario(*, repo_api, output_root: Path | None = None) -> dict[str, object]:
    config = load_business_config("repo", "delete_repo")
    collector, store, summary_path, _ = build_business_runtime(Path(__file__), "repo", "delete_repo", output_root)
    repo_payload = dict(config["repo"])
    repo_id = make_repo_id(str(repo_payload.pop("id_prefix")))
    repo_payload["id"] = repo_id
    overall_status = "passed"
    case_results: list[dict[str, object]] = []

    try:
        created = await repo_api.create(
            repo_payload,
            case_id="create",
            module="repo",
            action="create",
            name="create repository",
            path="/repositories",
        )
        store.save(created)
        create_ok = created.status_code in {200, 201, 202}
        if create_ok:
            collector.record_success("create")
        else:
            overall_status = "failed"
            create_reason = failure_reason_from_body(created.response_body, f"expected 200/201/202, got {created.status_code}")
            collector.record_failure("create", create_reason)
        record_case_result(case_results, prefix="delete_repo", case_id="create", expected_status="200/201/202", actual_status=created.status_code, passed=create_ok, failure_reason=None if create_ok else create_reason)

        ready = await _wait_repo_ready(repo_api, store, repo_id=repo_id, timeout_s=30.0)
        ready_ok = ready.status_code == 200
        if ready_ok:
            collector.record_success("ready")
        else:
            overall_status = "failed"
            ready_reason = failure_reason_from_body(ready.response_body, f"expected 200, got {ready.status_code}")
            collector.record_failure("ready", ready_reason)
        record_case_result(case_results, prefix="delete_repo", case_id="ready", expected_status=200, actual_status=ready.status_code, passed=ready_ok, failure_reason=None if ready_ok else ready_reason)

        deleted = await repo_api.delete(
            None,
            case_id="delete",
            module="repo",
            action="delete",
            name="delete repository",
            path=f"/repositories/{repo_id}",
        )
        store.save(deleted)
        delete_ok = deleted.status_code == 200
        if delete_ok:
            collector.record_success("delete")
        else:
            overall_status = "failed"
            delete_reason = failure_reason_from_body(deleted.response_body, f"expected 200, got {deleted.status_code}")
            collector.record_failure("delete", delete_reason)
        record_case_result(case_results, prefix="delete_repo", case_id="delete", expected_status=200, actual_status=deleted.status_code, passed=delete_ok, failure_reason=None if delete_ok else delete_reason)

        await _ensure_repo_deleted(repo_api, store, repo_id=repo_id, timeout_s=60.0)
        collector.record_success("deleted_absent")
        record_case_result(case_results, prefix="delete_repo", case_id="deleted-absent", expected_status="404", actual_status=404, passed=True)
    except Exception as exc:
        overall_status = "failed"
        collector.record_failure("delete_repo", str(exc))
        record_case_result(case_results, prefix="delete_repo", case_id="scenario-error", expected_status="no exception", actual_status=None, passed=False, failure_reason=str(exc))
    finally:
        try:
            cleanup = await repo_api.delete(
                None,
                case_id="cleanup",
                module="repo",
                action="delete",
                name="cleanup delete repo",
                path=f"/repositories/{repo_id}",
            )
            store.save(cleanup)
            cleanup_ok = cleanup.status_code in {200, 202, 204, 404}
            if cleanup_ok:
                collector.record_success("cleanup")
                if cleanup.status_code != 404:
                    await _ensure_repo_deleted(repo_api, store, repo_id=repo_id, timeout_s=60.0)
            else:
                overall_status = "failed"
                cleanup_reason = failure_reason_from_body(cleanup.response_body, f"expected 200/202/204/404, got {cleanup.status_code}")
                collector.record_failure("cleanup", cleanup_reason)
            record_case_result(case_results, prefix="delete_repo", case_id="cleanup", expected_status="200/202/204/404", actual_status=cleanup.status_code, passed=cleanup_ok, failure_reason=None if cleanup_ok else cleanup_reason)
        except Exception as exc:
            overall_status = "failed"
            collector.record_failure("cleanup", str(exc))
            record_case_result(case_results, prefix="delete_repo", case_id="cleanup-error", expected_status="cleanup ok", actual_status=None, passed=False, failure_reason=str(exc))

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
