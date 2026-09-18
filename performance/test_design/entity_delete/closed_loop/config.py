from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import json
import uuid
import sys
# Ensure API_TEST parent dir is on sys.path when running this file directly
_resolved = Path(__file__).resolve()
PROJECT_ROOT = None
for ancestor in _resolved.parents:
    if ancestor.name == 'API_TEST':
        PROJECT_ROOT = ancestor
        break
if PROJECT_ROOT is None:
    PROJECT_ROOT = _resolved.parents[3]
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

from API_TEST.performance.test_design.common.entity_access import default_run_dir as common_default_run_dir


DEFAULT_BASE_URL = "http://127.0.0.1:3154/x-api/v1"
# DEFAULT_BASE_URL = "http://175.168.12.43:3154/x-api/v1"
# DEFAULT_EXISTING_REPO_ID = ["3kwfacerepo_test", "1Efacerepo", "1Efacerepo_2"]
DEFAULT_MAX_INSERT_ATTEMPTS = 3
DEFAULT_ENTITY_PREFIX = "entity_7"
DEFAULT_INSERT_CONCURRENCY = 896
DEFAULT_STAGE_REQUEST_COUNT = 10000
DEFAULT_DELETE_CONCURRENCY_VALUES = [32, 64]
DEFAULT_EXISTING_REPO_ID = ["3kwfacerepo_test", "1Efacerepo", "5kwfacerepo"]
# DEFAULT_DELETE_CONCURRENCY_VALUES = [512]


DEFAULT_REPO_TEMPLATE = {
    "id": "3kwfacerepo_test",
    "type": "face",
    "capacity": 0,
    "level": "ram",
}


DEFAULT_ENTITY_TEMPLATE = {
    "id": "entity-001",
    "location_id": "camera-0001",
    "data": {
        "type": "feature",
        "value": "CJBOIoAQAOAsvQCAQzwAYIm7AEBhOwCgNb0AAIi7AIAPvQAA3jwAgIS9AEC8PQDg4TwA4OQ8AGBevQAAhbwA4Bs9AEAsvAAATL0AAEq9AECrPABAc70A4KM8ACCAOwCgsjwAAJG8AODNvADgLjwAYIA9AECAvQBgpz0AYPu8AOACOwBArrsAwCs8AKCyPQCgFr0AwHg9AOBWuwDgjzwA4LS9ACBBvQDABTwAoD29AADYvQBAZz0AQPg8AMCrvQDAqT0AIBk9AAAaPABgQ70AQMU9AEAevQCgyLgAIIc9AOAZvQBgMr0AQJC8AKCjuwDAtDwAoKS8AMAXOwCAjTwAQMY8AEA8PQCgNL0AAEc9AKByPAAgiD0AoHS8AECBPQDgebwAoP47AIC2PABATDwAoFu7AMBGvQCgiTsAQFA9AADdugBARrwAYHq9ACCwPABAWj0AgNE8AEBxPADgkrwAwGY8AICgvQAASD0A4Nq9AODDOwCgQb0AwF09ACArvADgPb0AwCW9AGCzvAAgrDwA4Ko9AAABPgCAET0AgIm8AOD1vACAFbwAwEG9AACtOwAgir0AgM06AOC/uwAAprwAILW7AEASPQAg5LwAQB88AAAoPADg4bsAoEq9AGAZPQCA+LwAwBU8AIBHPQAAnbsAwLY8AOBuPAAgDD0A4EU8AACJPQDgtDwAoPc8AOD2OQCAF70A4Ja8AGAtPQBg/7gAoHm8AEBGvABAnLwA4DI8AACQOwCgabwAwIo9AOAiPQDgqTwA4A09AKCKPQAgqLwAQJg9AOCpvABAFj0AIG29AOAUPQBgnTwA4Pe9AKD3uwCggj0AIII9AKDXvABAHLwAYIC8AECJOwDAYrwA4Kw9AGDqvACAYLwAgKg8AKAavABATL0AAKI7AAB2PQBA47wAwA29AACrPACAIrkA4Ng8AKBkPABAIjwAICm8ACAhvAAg+boA4GW9ACCIPQBgLz0AIM08AIAmPADgi7sAwI89AOBaPQDAJz0A4K27AKDKPAAAvzwAgDK8AAArPABANL0AICk9ACAxOwAgqL0A4Kg9AOCgvAAAFDsAAJi8AGAyvQDAHTwAAEM9AOCrvABgdL0AoJg9AAArvACgVj0AwJG9AOD8vACA/rwAoJC7ACCpuwBgGj0AoK89AKClPACAiL0AYFw9AMD3PQCARD0AAP88ACCFuwBAbr0AAEQ9AKCHPAAgXT0AALQ8AGAcPQAgUL0A4F69ACCHvQAAxDwA4KM9AADkvABgfD0AYCu9AMD2PADgnLwAADm9AKACvgCAQrsA4IO8AACbvAAAND0AYOw8AKCCvQCgQjwA4MI8AMBsvQBgwjwAQGE9AICrOwDANrwAYOu8AMCUvQCA4rwAQJK8AECJPABgOL0AoGy9AABEPAAATD0AYOk8ACCpPACAar0A4BU9AEBGPQBAnTwAAK27AMAMPQBgVD0AQFo9AGBWvQBgnTwAwNU8AGBDugCAQz0AgHo9AKAbPQBgqb0AACa7AOABPQAA5jwAwPK9AEC8vQCAvj0AADe8ACDMvQDAn7wAAKs8AOAsvQDgA7sAQNa8AGCEPQDgnL0AYNy5AACBOgCAj70A4Ky7AACgvQCgMrwA4LK8AOCAvQDAAr4AQNu9ACDQPABA2j0AIMC8AOB2vADgBjwAAL67AMCXvADgzb0A4Ic8AKA3vQCAr7wAYAg9AGCvvQBAp7wAADc8AAA+vACA5DwAwM48AGB9PQAgar0AoKE7AGAQOwCg9LsA4BE9AMD7PABAFD0AAMg8AMCOvQAgajsA4L+7AIAuvQAAvD0AoHc9AOCVPAAAprwAIK08AMA6ugBgIz0AIJk8AGCavQCAqLwA4Ji8AKCbPAAAN70AgOm8AKBkvQDAqDsAIKE9AKAHPQCgQb0AIJA8AIBPPAAg1rwAQIG9AMCBvQBgIT0AIFI9AED7vADg5DsAADQ9AMCBvADgkb0AoF69AMCRvABAtroAIM47AOA3PADgijwAoA69AABvPQBg/TwA4Io8AOBmvABA9jwAINg8AECrvADAHTwAALY8AMBiPQBgCT0AAKa8AECivADgILwAAMg7AMCPvAAAsz0A4Pu7AKDWPAAAhzwA4Hw7AOC5PACAdT0AoKg9AMCovQDAaL0AAK49ACDovADg9zoAwBs9AABduwAgGb0AoIa9AED8uwDgvDwAYEU8AOAMOwAgnDwA4FW8AOBavQCAlrwAYIe7AMAXvQDAJLwAIE68AIASPQAADzwA4AU8AGBkPAAA77sAgME8AGADvQCAKL0A4Dw9AKAsPABAeDwAYCe9AOCYvQAgfr0A4Bs9AMBqPQBART0AoBA9ACCuPQDgmb0AgMy8AEANPABA/bwA4Kq9AKAivQAg+DwAANs8AIB5vACAYjwAwL68ACAjPACAWroAwIG9AGAbvQAgqrwAYMO9ACDvvAAAVL0AoHi8ACDRvQAgmDsAoKI9ACCLvABg7LsAgB89AIAiPQCgPLwAoN67AKAtvQBA2L0AgCm8ACDMPABgyLsAwI+9AEDiPABgJj0AQCg9AACCPQDgG70AgDI9ACCpuwAgeb0AwFW9AGD2vQDgLz0AABg8AIDSvQBgP70AQOs7ACBivQBg97wAYAa8AMDGvABAV70AwPG7AABMPQDgsTwAIEU8AOCTPQAAir0AAAu8ACCnPAAgLT0A4JY8AADIvAAg0TsAgKO9AMDsPABAULwAQIS8AACAvADgKb09AACAPw==",
    },
}


@dataclass(frozen=True)
class BenchmarkConfig:
    base_url: str
    repo_prefix: str
    entity_prefix: str
    repo_type: str
    capacity: int
    level: str
    index_type: str
    insert_concurrency: int
    insert_timeout_seconds: int
    delete_timeout_seconds: int
    stage_request_count: int
    delete_concurrency_values: list[int]
    k6_executable: str
    report_output_dir: Path
    existing_repo_id: str | None = None
    max_insert_attempts: int = DEFAULT_MAX_INSERT_ATTEMPTS

    # 支持在配置中提供多个已存在的 repo id，按顺序执行压测。
    existing_repo_ids: list[str] | None = None


# 构造当前场景所需的数据。
def build_default_config() -> BenchmarkConfig:
    return BenchmarkConfig(
        base_url=DEFAULT_BASE_URL,
        repo_prefix="compare-",
        entity_prefix=DEFAULT_ENTITY_PREFIX,
        repo_type="face",
        capacity=0,
        level="ram",
        index_type="int8",
        insert_concurrency=DEFAULT_INSERT_CONCURRENCY,
        insert_timeout_seconds=30,
        delete_timeout_seconds=30,
        stage_request_count=DEFAULT_STAGE_REQUEST_COUNT,
        delete_concurrency_values=list(DEFAULT_DELETE_CONCURRENCY_VALUES),
        k6_executable="k6",
        report_output_dir=common_default_run_dir("entity_delete", category="entity"),
        existing_repo_id=None,
        existing_repo_ids=DEFAULT_EXISTING_REPO_ID,
        max_insert_attempts=DEFAULT_MAX_INSERT_ATTEMPTS,
    )


# 生成当前场景使用的标识或资源。
def make_repo_id(prefix: str, index: int) -> str:
    token = uuid.uuid4().hex[:10]
    return f"{prefix}-{index:04d}-{token}"


# 生成当前场景使用的标识或资源。
def make_entity_id(prefix: str, index: int) -> str:
    token = uuid.uuid4().hex
    return f"{prefix}-{index:08d}-{token}"


# 构造当前场景所需的数据。
def build_entity_payload(entity_id: str, template: dict[str, object] | None = None) -> dict[str, object]:
    payload = deepcopy(template or DEFAULT_ENTITY_TEMPLATE)
    payload["id"] = entity_id
    return payload


# 加载当前场景所需的数据或模板。
def load_repo_template(repo_data: str | None = None) -> dict[str, object]:
    if not repo_data:
        return deepcopy(DEFAULT_REPO_TEMPLATE)
    return json.loads(Path(repo_data).read_text(encoding="utf-8"))


# 加载当前场景所需的数据或模板。
def load_entity_template(entity_data: str | None = None) -> dict[str, object]:
    if not entity_data:
        return deepcopy(DEFAULT_ENTITY_TEMPLATE)
    return json.loads(Path(entity_data).read_text(encoding="utf-8"))
