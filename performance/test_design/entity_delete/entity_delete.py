"""Closed-loop delete-instance benchmark entry point."""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiohttp
import sys
_resolved = Path(__file__).resolve()
PROJECT_ROOT = _resolved.parents[3]
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

from API_TEST.performance.test_design.entity_delete.closed_loop.config import build_default_config
from API_TEST.performance.test_design.entity_delete.closed_loop.delete_stage import run_delete_stage
from API_TEST.performance.test_design.entity_delete.closed_loop.insert_stage import insert_entities_async
from API_TEST.performance.test_design.entity_delete.closed_loop.orchestrator import run_closed_loop_benchmark
from API_TEST.performance.test_design.entity_delete.closed_loop.repo_api import create_repo_async, delete_repo_async
from API_TEST.performance.test_design.entity_delete.closed_loop.reporting import write_report_bundle


# 内部辅助函数，封装当前模块的局部逻辑。
async def _create_repo_wrapper(*, config, repo_template):
    async with aiohttp.ClientSession() as session:
        status, body = await create_repo_async(
            session,
            base_url=config.base_url,
            repo_id="compare-entry",
            capacity=config.capacity,
            level=config.level,
            index_type=config.index_type,
            repo_type=config.repo_type,
            template=repo_template,
            timeout_seconds=config.insert_timeout_seconds,
        )
    if status is None or status >= 400:
        raise RuntimeError(f"failed to create repo: {status}, body={body}")
    return "compare-entry"


# 删除压测过程中创建的临时仓库，回收测试环境。
async def _delete_repo_wrapper(*, config, repo_id):
    async with aiohttp.ClientSession() as session:
        await delete_repo_async(
            session,
            base_url=config.base_url,
            repo_id=repo_id,
            timeout_seconds=config.delete_timeout_seconds,
        )


# 内部辅助函数，封装当前模块的局部逻辑。
async def _insert_stage_wrapper(*, config, repo_id, entity_template, entity_ids):
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=max(1, config.insert_concurrency * 2), limit_per_host=max(1, config.insert_concurrency * 2))
    ) as session:

        # 发送单次请求并返回标准化结果。
        async def sender(*, base_url, repo_id, entity_id, payload, timeout_seconds):
            try:
                async with session.post(
                    f"{base_url.rstrip('/')}/repositories/{repo_id}/entities",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout_seconds),
                ) as response:
                    try:
                        body = await response.json()
                    except Exception:
                        body = await response.text()
                    return response.status, body, None
            except aiohttp.ClientError as exc:
                return None, {"message": str(exc)}, "connection_error"
            except asyncio.TimeoutError:
                return None, None, "timeout"

        return await insert_entities_async(
            base_url=config.base_url,
            repo_id=repo_id,
            entity_ids=entity_ids,
            entity_template=entity_template,
            concurrency=config.insert_concurrency,
            timeout_seconds=config.insert_timeout_seconds,
            request_sender=sender,
            progress_writer=print,
        )


# 内部辅助函数，封装当前模块的局部逻辑。
async def _delete_stage_wrapper(*, config, repo_id, entity_ids, concurrency):
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=max(1, concurrency * 2), limit_per_host=max(1, concurrency * 2))
    ) as session:
        return await run_delete_stage(
            session=session,
            base_url=config.base_url,
            repo_id=repo_id,
            entity_ids=entity_ids,
            concurrency=concurrency,
            delete_timeout_seconds=config.delete_timeout_seconds,
        )


# 内部辅助函数，封装当前模块的局部逻辑。
def _write_report_wrapper(output_dir: Path, bundle):
    return write_report_bundle(output_dir, bundle)


# 程序入口，用于串起当前模块的执行流程。
def main() -> int:
    config = build_default_config()
    repo_display = config.existing_repo_ids if getattr(config, "existing_repo_ids", None) is not None else config.existing_repo_id
    print(
        f"[RUN] base_url={config.base_url} insert_concurrency={config.insert_concurrency} "
        f"delete_concurrency={config.delete_concurrency_values} stage_entity_budget={config.stage_request_count} "
        f"repo_ids={repo_display} "
        f"max_insert_attempts={config.max_insert_attempts}",
        flush=True,
    )
    result = asyncio.run(
        run_closed_loop_benchmark(
            config=config,
            create_repo=_create_repo_wrapper,
            insert_stage=_insert_stage_wrapper,
            delete_stage=_delete_stage_wrapper,
            write_report=_write_report_wrapper,
            delete_repo=_delete_repo_wrapper,
        )
    )
    # 兼容单仓库和多仓库返回结果；多仓库时返回 {'results': [..]}。
    if isinstance(result, dict) and "results" in result:
        for r in result["results"]:
            if r.get("aborted"):
                print(
                    f"[RUN] benchmark aborted before delete stage for repo {r.get('repo_id')}: {r.get('abort_reason')} report_path={r.get('report_path')}",
                    flush=True,
                )
                return 1
    else:
        if result.get("aborted"):
            print(
                f"[RUN] benchmark aborted before delete stage: {result.get('abort_reason')} "
                f"report_path={result.get('report_path')}",
                flush=True,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
