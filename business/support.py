"""提供业务场景数据加载、运行输出管理与真实 API 客户端构建能力的共享模块。"""

from __future__ import annotations

import json
from copy import deepcopy
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator

from API_TEST.api.api import DetectApi, EntityApi, RepoApi, SearchApi
from API_TEST.config.settings import DEFAULT_BASE_URL, DEFAULT_DETECT_URL, DEFAULT_REQUEST_TIMEOUT_S
from API_TEST.core.http_client import AioHttpClient
from API_TEST.core.response_store import ResponseStore
from API_TEST.core.result_collector import ResultCollector
from API_TEST.core.utils import ensure_runtime_readme, load_json_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_FEATURE_PATH = PROJECT_ROOT / "data" / "common" / "reference_feature.b64"
REFERENCE_FEATURE_TOKEN = "__REFERENCE_FEATURE__"
REFERENCE_DETECT_IMAGE_TOKEN = "__REFERENCE_DETECT_IMAGE__"
REFERENCE_DETECT_IMAGE_PATH = PROJECT_ROOT / "data" / "detect" / "function" / "run" / "source_legacy_cases.json"
DEFAULT_BUSINESS_CONFIGS: dict[tuple[str, str], dict[str, Any]] = {
    ("repo", "create_repo"): {
        "repo": {
            "id_prefix": "business-create-repo",
            "type": "face",
            "index_type": "int8",
            "level": "ram",
        }
    },
    ("repo", "delete_repo"): {
        "repo": {
            "id_prefix": "business-delete-repo",
            "type": "face",
            "index_type": "int8",
            "level": "ram",
        }
    },
    ("repo", "capacity"): {
        "repo": {
            "id_prefix": "business-capacity-repo",
            "type": "face",
            "index_type": "int8",
            "level": "ram",
            "capacity": 7,
        }
    },
    ("repo", "replications"): {
        "repo": {
            "id_prefix": "business-replications-repo",
            "type": "face",
            "index_type": "int8",
            "level": "ram",
            "replications": 1,
        }
    },
    ("repo", "prefilter"): {
        "repo": {
            "id_prefix": "business-prefilter-repo",
            "type": "person",
            "index_type": "int8",
            "level": "ram",
            "options": {
                "PreFilter": "true",
            },
        },
        "entity": {
            "id_prefix": "prefilter-entity",
            "data": {
                "value": REFERENCE_FEATURE_TOKEN,
                "type": "feature",
            },
            "location_id": "1",
        },
        "search": {
            "type": "face",
            "include": [
                {
                    "data": {
                        "value": REFERENCE_FEATURE_TOKEN,
                        "type": "feature",
                    }
                }
            ],
            "max_candidates": 5,
        },
    },
    ("entity", "compare_version"): {
        "repo": {
            "id_prefix": "business-version-repo",
            "type": "face",
            "index_type": "int8",
            "level": "ram",
        },
        "entity_a": {
            "id_prefix": "version-entity-a",
            "data": {
                "value": REFERENCE_FEATURE_TOKEN,
                "type": "feature",
                "version": "v1",
            },
            "location_id": "loc-001",
        },
        "entity_b": {
            "id_prefix": "version-entity-b",
            "data": {
                "value": REFERENCE_FEATURE_TOKEN,
                "type": "feature",
                "version": "v1",
            },
            "location_id": "loc-002",
        },
        "expected_same_version": True,
    },
    ("repo", "rotate"): {
        "repo": {
            "id_prefix": "business-rotate-repo",
            "type": "face",
            "index_type": "int8",
            "level": "ram",
            "capacity": 5,
            "options": {
                "Rotate": "true",
            },
        }
    },
    ("repo", "timerDeleteDays"): {
        "repo": {
            "id_prefix": "business-timer-delete-days-repo",
            "type": "face",
            "index_type": "int8",
            "level": "ram",
            "options": {
                "TimerDeleteDays": "1",
            },
        }
    },
    ("repo", "useFeatureIDMap"): {
        "repo": {
            "id_prefix": "business-use-feature-id-map-repo",
            "type": "face",
            "index_type": "int8",
            "level": "ram",
            "options": {
                "UseFeatureIDMap": "true",
            },
        }
    },
    ("search", "multi_repo"): {
        "repo_a": {
            "id_prefix": "business-multi-repo-a",
            "type": "face",
            "index_type": "int8",
            "level": "ram",
        },
        "repo_b": {
            "id_prefix": "business-multi-repo-b",
            "type": "face",
            "index_type": "int8",
            "level": "ram",
        },
        "entity": {
            "id_prefix": "multi-entity",
            "data": {
                "value": REFERENCE_FEATURE_TOKEN,
                "type": "feature",
            },
            "location_id": "loc-001",
        },
        "search": {
            "type": "face",
            "include": [
                {
                    "data": {
                        "value": REFERENCE_FEATURE_TOKEN,
                        "type": "feature",
                    }
                }
            ],
            "max_candidates": 12,
        },
    },
    ("detect", "detect_type"): {
        "cases": [
            {
                "detect_type": "all",
                "image": {
                    "url": "http://175.168.10.27:30073/s3development/4677b660-6250-46ac-b0ed-cac037a0ed5a.jpg",
                },
            },
            {
                "detect_type": "face",
                "image": {
                    "url": "http://175.168.10.27:30073/s3development/e0e98696-c6fc-49c9-8ab1-0be862f0610f.jpg",
                },
            },
        ]
    },
    ("detect", "advanced_fields"): {
        "cases": [
            {
                "case_id": "AF-FILE-VALID-001",
                "name": "image.file为合法base64字符串时检测",
                "method": "POST",
                "path": "/ai/detect/all",
                "payload": {
                    "image": {
                        "file": REFERENCE_DETECT_IMAGE_TOKEN,
                    }
                },
            },
            {
                "case_id": "AF-UO-VALID-001",
                "name": "user_object为合法结构时检测",
                "method": "POST",
                "path": "/ai/detect/all",
                "payload": {
                    "image": {
                        "url": "http://175.168.10.27:30073/s3development/14bcf6a9-3fba-4985-b7ee-876a03e428b7.jpg",
                    },
                    "user_object": {
                        "type": "face",
                        "rect": {
                            "x": 10,
                            "y": 10,
                            "w": 100,
                            "h": 100,
                        },
                    },
                },
            },
            {
                "case_id": "AF-ROI-VALID-001",
                "name": "rois_polygon为合法结构时检测",
                "method": "POST",
                "path": "/ai/detect/all",
                "payload": {
                    "image": {
                        "url": "http://175.168.10.27:30073/s3development/14bcf6a9-3fba-4985-b7ee-876a03e428b7.jpg",
                    },
                    "rois_polygon": [
                        {
                            "polygon_area": [
                                {"x": 0.1, "y": 0.1},
                                {"x": 0.5, "y": 0.1},
                                {"x": 0.5, "y": 0.5},
                            ],
                            "filter_threshold": 0.9,
                        }
                    ],
                },
            },
        ]
    },
}


# 加载当前场景所需的数据或模板。
def load_reference_feature() -> str:
    return REFERENCE_FEATURE_PATH.read_text(encoding="utf-8").strip()


# 加载当前场景所需的数据或模板。
def load_reference_detect_image() -> str:
    for case in load_json_file(REFERENCE_DETECT_IMAGE_PATH):
        if not isinstance(case, dict):
            continue
        payload = case.get("payload")
        if not isinstance(payload, dict):
            continue
        image = payload.get("image")
        if isinstance(image, dict) and isinstance(image.get("file"), str):
            return image["file"]

    raise FileNotFoundError(f"未找到 detect 参考图片 base64: {REFERENCE_DETECT_IMAGE_PATH}")


# 实现当前模块的核心逻辑。
def expand_business_tokens(value: Any) -> Any:
    if isinstance(value, str):
        if value == REFERENCE_FEATURE_TOKEN:
            return load_reference_feature()
        if value == REFERENCE_DETECT_IMAGE_TOKEN:
            return load_reference_detect_image()
        return value
    if isinstance(value, list):
        return [expand_business_tokens(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_business_tokens(item) for key, item in value.items()}
    return value


# 加载当前场景所需的数据或模板。
def load_business_config(module: str, scenario_name: str) -> dict[str, Any]:
    config_file = PROJECT_ROOT / "data" / module / "business" / f"{scenario_name}.json"
    if config_file.is_file():
        payload = load_json_file(config_file)
    else:
        payload = deepcopy(DEFAULT_BUSINESS_CONFIGS[(module, scenario_name)])
    return expand_business_tokens(payload)


# 生成当前场景使用的标识或资源。
def make_repo_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# 生成当前场景使用的标识或资源。
def make_entity_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# 构造当前场景所需的数据。
def build_business_runtime(script_file: Path, module: str, scenario_name: str, output_root: Path | None) -> tuple[ResultCollector, ResponseStore, Path, Path]:
    runtime_root = Path(output_root) if output_root is not None else script_file.parent
    response_root = runtime_root / "responses" / scenario_name
    archive_root = response_root / "archives"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    summary_path = response_root / f"summary_{stamp}.json"

    collector = ResultCollector(
        name=scenario_name,
        module=module,
        action_or_scenario=scenario_name,
        output_path=summary_path,
        response_archive_dir=str(archive_root),
    )
    store = ResponseStore(archive_root)
    return collector, store, summary_path, archive_root


# 完成当前场景的结果汇总。
def finalize_business_summary(
    collector: ResultCollector,
    summary_path: Path,
    *,
    overall_status: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_runtime_readme(summary_path.parent, "该目录用于存放业务场景汇总结果与响应归档。")
    summary = collector.build_summary().to_dict()
    summary["overall_status"] = overall_status
    summary["summary_path"] = str(summary_path)
    if extra:
        summary.update(extra)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


# 提取当前场景需要的字段或结果。
def extract_search_results(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return [item for item in payload["results"] if isinstance(item, dict)]
    return []


# 提取当前场景需要的字段或结果。
def extract_result_repo_ids(results: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("repo_id")) for item in results if item.get("repo_id") is not None]


# 提取当前场景需要的字段或结果。
def extract_result_similarities(results: list[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for item in results:
        similarity = item.get("similarity")
        if isinstance(similarity, (int, float)):
            values.append(float(similarity))
    return values


# 判断当前对象是否满足目标条件。
def is_nonincreasing(values: list[float]) -> bool:
    return all(left >= right for left, right in zip(values, values[1:]))


# 解析当前场景所需的路径或目标。


# 打开所需的真实 API 适配器，并在退出时关闭其底层 aiohttp 客户端。
@asynccontextmanager
async def open_business_apis(
    *,
    repo: bool = False,
    entity: bool = False,
    search: bool = False,
    detect: bool = False,
) -> AsyncIterator[dict[str, object]]:
    comp_client: AioHttpClient | None = None
    detect_client: AioHttpClient | None = None
    apis: dict[str, object] = {}

    if repo or entity or search:
        comp_client = AioHttpClient(DEFAULT_BASE_URL, timeout_s=DEFAULT_REQUEST_TIMEOUT_S)
    if detect:
        detect_client = AioHttpClient(DEFAULT_DETECT_URL, timeout_s=DEFAULT_REQUEST_TIMEOUT_S)

    if repo and comp_client is not None:
        apis["repo_api"] = RepoApi(comp_client)
    if entity and comp_client is not None:
        apis["entity_api"] = EntityApi(comp_client)
    if search and comp_client is not None:
        apis["search_api"] = SearchApi(comp_client)
    if detect and detect_client is not None:
        apis["detect_api"] = DetectApi(detect_client)

    try:
        yield apis
    finally:
        if detect_client is not None:
            await detect_client.close()
        if comp_client is not None:
            await comp_client.close()
