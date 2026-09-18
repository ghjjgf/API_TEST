"""为真实接口测试及其结构化运行输出提供共享夹具的模块。"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path

import pytest
import pytest_asyncio

from API_TEST.api.api import DetectApi, EntityApi, RepoApi, SearchApi
from API_TEST.config.settings import DEFAULT_BASE_URL, DEFAULT_DETECT_URL, DEFAULT_REQUEST_TIMEOUT_S
from API_TEST.core.http_client import AioHttpClient
from API_TEST.core.response_store import ResponseStore
from API_TEST.core.result_collector import ResultCollector
from API_TEST.function_test.support import build_response_store, cleanup_entity_resource, cleanup_repo_resource, create_tracked_entity_resource, create_tracked_repo_resource, resolve_summary_path


SUMMARY_CACHE: dict[tuple[str, str, str], ResultCollector] = {}
RESPONSE_STORE_CACHE: dict[tuple[str, str], ResponseStore] = {}


# 构建接口测试输出使用的运行根目录。
def runtime_root() -> Path:
    return Path(__file__).resolve().parent


# 生成当前场景使用的标识或资源。
def make_repo_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# 生成当前场景使用的标识或资源。
def make_entity_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# 处理当前功能测试的核心逻辑。
@pytest_asyncio.fixture
async def repo_api() -> Iterator[RepoApi]:
    client = AioHttpClient(DEFAULT_BASE_URL, timeout_s=DEFAULT_REQUEST_TIMEOUT_S)
    try:
        yield RepoApi(client)
    finally:
        await client.close()


# 处理当前功能测试的核心逻辑。
@pytest_asyncio.fixture
async def entity_api() -> Iterator[EntityApi]:
    client = AioHttpClient(DEFAULT_BASE_URL, timeout_s=DEFAULT_REQUEST_TIMEOUT_S)
    try:
        yield EntityApi(client)
    finally:
        await client.close()


# 处理当前功能测试的核心逻辑。
@pytest_asyncio.fixture
async def search_api() -> Iterator[SearchApi]:
    client = AioHttpClient(DEFAULT_BASE_URL, timeout_s=DEFAULT_REQUEST_TIMEOUT_S)
    try:
        yield SearchApi(client)
    finally:
        await client.close()


# 处理当前功能测试的核心逻辑。
@pytest_asyncio.fixture
async def detect_api() -> Iterator[DetectApi]:
    client = AioHttpClient(DEFAULT_DETECT_URL, timeout_s=DEFAULT_REQUEST_TIMEOUT_S)
    try:
        yield DetectApi(client)
    finally:
        await client.close()


# 处理当前功能测试的核心逻辑。
@pytest.fixture
def response_store_factory(request) -> Callable[[str | None], ResponseStore]:
    base_dir = Path(request.fspath).resolve().parent / "results" / "responses"

    # 在测试模块的响应归档目录下创建响应存储器。
    def factory(subdir: str | None = None) -> ResponseStore:
        target = base_dir if subdir is None else base_dir / subdir
        cache_key = (str(base_dir), subdir or "")
        if cache_key not in RESPONSE_STORE_CACHE:
            RESPONSE_STORE_CACHE[cache_key] = build_response_store(target)
        return RESPONSE_STORE_CACHE[cache_key]

    return factory


# 处理当前功能测试的核心逻辑。
@pytest.fixture
def summary_factory(request) -> Callable[[str, str, str], ResultCollector]:
    test_file = Path(request.fspath).resolve()

    # 实现当前模块的核心逻辑。
    def factory(name: str, module: str, action_or_scenario: str) -> ResultCollector:
        cache_key = (str(test_file), module, action_or_scenario)
        if cache_key not in SUMMARY_CACHE:
            SUMMARY_CACHE[cache_key] = ResultCollector(
                name=name,
                module=module,
                action_or_scenario=action_or_scenario,
                output_path=resolve_summary_path(test_file),
            )
        return SUMMARY_CACHE[cache_key]

    return factory


# 处理当前功能测试的核心逻辑。
@pytest_asyncio.fixture
async def repo_resource_factory(repo_api) -> Iterator[Callable[[str], Awaitable[str]]]:
    created_repo_ids: list[str] = []

    # 创建唯一仓库，并等待其可供后续测试使用。
    async def factory(prefix: str) -> str:
        return await create_tracked_repo_resource(repo_api, prefix, created_repo_ids, timeout_s=30.0)

    try:
        yield factory
    finally:
        for repo_id in reversed(created_repo_ids):
            await cleanup_repo_resource(repo_api, repo_id, timeout_s=60.0)


# 处理当前功能测试的核心逻辑。
@pytest_asyncio.fixture
async def entity_resource_factory(repo_resource_factory, entity_api) -> Iterator[Callable[[str, str], Awaitable[tuple[str, str]]]]:
    created_entities: list[tuple[str, str]] = []

    # 实现当前模块的核心逻辑。
    async def factory(repo_prefix: str, entity_prefix: str) -> tuple[str, str]:
        repo_id = await repo_resource_factory(repo_prefix)
        return await create_tracked_entity_resource(entity_api, repo_id, entity_prefix, created_entities, timeout_s=60.0)

    try:
        yield factory
    finally:
        for repo_id, entity_id in reversed(created_entities):
            await cleanup_entity_resource(entity_api, repo_id, entity_id, timeout_s=60.0)
