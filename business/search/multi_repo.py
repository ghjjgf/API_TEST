"""用于校验 legacy multi_repo_ 业务场景脚本的模块。"""
# multi_repo.py 测试流程
# 流程：
# 1. 分别创建动态 id 的 repo-mul-1-* 和 repo-mul-2-* 仓库，均为 person/int8/ram、PreFilter=false，预期创建 200/201/202 并等待 READY。
# 2. repo-mul-1 写入 a-entity1-1~3（location_id=1）与 a-entity2-1~3（location_id=0），均预期 HTTP 201。
# 3. repo-mul-2 写入 b-entity1-1~3（location_id=1）与 b-entity2-1~3（location_id=0），均预期 HTTP 201。
# 4. POST /repositories/search：query 使用 ENTITY1_FEATURE，repositories 同时包含两个动态仓库 id，max_candidates=12，topk=12。
# 5. 断言 HTTP 200、结果非空、结果所属仓库集合精确等于两个仓库 id 的集合、similarity 非递增。
# 6. 最后分别删除两个仓库并确认不存在。

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

from API_TEST.business.search._scenario_runtime import cleanup_repo, create_entity, create_repo, failure_reason_or_body, record_step, search_query, wait_repo_ready
from API_TEST.business.search._scenario_support import describe_search_failure, finalize_search_summary
from API_TEST.business.support import build_business_runtime, extract_result_repo_ids, extract_result_similarities, extract_search_results, is_nonincreasing, make_repo_id, open_business_apis


# 1
# 0.9
ENTITY2_FEATURE = "CKKcASKAEABgNDsA4JS8AMALPQDAO7wAAOm8AMAiPABg0rwAAGM9AADLPAAA4zwAwPw8AKAGPAAAoD0AwMQ7AECpPABg2LkAYHm7ACAYvADgZzoA4Pa7AAC7vACAdb0AgMo6AADdPAAAVr0AYKS9AGC0vQCAj7oAAJI6AOB6vQCAZbwAYFi7AOAwPACgkr0AAIm9AKCPvQDg6T0AYJa7AOD7PAAArb0AQNM8AABJvABgtL0AYLy9AABFvQBAMjoAwIQ9AAD4vADgjzwA4Ge8AGCyPQBgL70AYDm7AACJPQBgPT0AAM68AMAEvACgYL0AgMq9AEClvAAAXb0AQIs9AOBVPQCAwrwAAGk9ACDhPACgDD0AIJ87AIDovABgST0AII+8ACCNPQAghL0AQIu8AOCgvADgEL0AgKA9AICmPQCgorwAIHS7AGCmvQDgPr0AwMa8AMCZPABgqLsA4Je8AECOvQDAAT0AgGc9AEA0PQAAF70AQOS7ACA3vQCAmb0AAJc8AAAxPQCAtrsAADE9AMBkPABgQzwAoFG8AMDvPADAd7wAwFI7AIA2uwCAQj0AgG+9AEBxvABg8TwAwDQ8AAA4PACgz7oAwDM9AKC5vAAAsDwAwAg9AIAbPQAAmz0AIH48AKCSPABgaDwAIAY9AAB8vQDgSz0AoOA7AEAQvQBgAj0AgCG8ACBlvQCAt7wAYKW9AGCAPAAAMD0AwEu9AMDRPQDADr0A4CE9AADIvADgLT0AwPS6AKCYvQAA4bwAAD09AICcPAAAhLwAoPA7ACCPvACAAb0AQD49AACJPQBgRb0AIB+9ACAvPQCgoLwAoME8AKAvugBgKr0AAEe9AMDRvQCgtrwAYBO8AAC3PQDAbrwAQBC9ACD+OwCAqLwAQKi8ACBHPADAtbwAQJk8AOA9PQDghD0AQAK9AAAMuwBAa70AIH+8AEAevQAgGzwAYGi8AAApvQBgar0AoLY8ACBDugDAID0AQFi8AAC7vABg7rsA4C09ACABPQCgcj0A4Pk8AECCPABAnjwAgP68AEDEvADgpLwAoLC8AGCaPADAfb0A4CG9AICBvQCgFT0AwBk8AKBmvQCgWrwAwG49AKAbOwAArDwAoAg9AOD0vQDALrsAQCU9AGBqvQCAMT0AoDk9AIDfvQAAhDsAgJ28AOAnPQDgM7wA4Jo8AECIvAAABTwAYIm9AICEvQAgFj0AgKm9AOAXvQDgWz0AgIm5AKDhvADgBL0A4Fs8AICHPQCgBb0AYBO9AEAEvQAgpzwAQJw9AADdvABAZTwAgC49AABBPACgUrwAIPO8AIBEvQCgW70AoOC8AIDmuwDgS70AYAm9AOCwvAAAn70AAG49AGAtuwCgNDwAQOk8AOBJPADA2L0AYNe8AKAFOwCAPbwA4OK6AEBQPQDA/DwAAA29AAA/vQCgpLwAgFO8AODzvQCADb0AoCm5AEBYPQCgADwAQKm8AGDVvABgWz0AwP28AIC2OwDAhDoAwO48AECfvAAAB7wAIB69AEAHPQBgvDwAYJI9AGBXPADgnrwAQI08AMC/PQDAeDwAQNe7AKCnPAAAILwAQBO9AECzPQCggjwAoA87AGB/vAAgM70AwAA6AKDaPQBgS7wAIOw8AAAOPgAAV70AIIy8AICPPADgwjwAgAs7AICfuwBgirwAAIM3AGCEPQBgNz0AwA49AGBYvAAAB7wAQJW9AIDzOwCApT0A4Fs9AIC9vQDglT0AoNo9AODovAAgTb0AoBe9AGBFPQAgYjwAgBS9AGAzvQBA8LoAgFA9ACCDugBABz0AAFy9AOCqPQBAyLwA4Jc8AMAiPQAgFDwAABs9AECgPQBgDL4AoE08AOBnPQDAHr0A4O47AEDSPADgo7wAYK+8AOC9PABAVz0AgCw9ACAZvQAgX70AgK85AECaPQBAy7sAgOm7AMCAuwCAYzgAQAa8AKDRvACgDjwAoFI9AIA+OgAA/D0AILq6ACCquwBgsrwAAKU9AOA4vQDABL0AgBM9AGCEvQDgajwA4AE9AGAeuwBgAL0AgH69AMAtPQDgsbwA4J69AMBBvAAAJjkAoGw9AGBuvQDAlrsAQBq8AECGPQBAO70AgCI9AKCGuwDAIr0AQEi8AEAjvQBAQbwAIEA8AGCHPABAlL0AQC+8AKAAPQCgvb0AQPC8AGAZvQDA/LwAoAi9AOCRPABgBrsAAES9AIB7PQDgIj0AwI27AKDZvQDAszsA4BE9AMDwvACACj0AYLc6AMADPgCAGj0AIBU8AEBwuwCAfLgA4O48AIC4PQBA2TwAIPg9ACBkuwDAjLsAoMY9AMBqOgBgdj0AYJM8AGAXvQCgxzwAwLG9AED2PAAgSbwAgFA9AKD9PAAAI70AIIY9AIBQPQCgML0AAHQ9AAC3vQDgijoAwLu8AGDoPADAAD0AIOQ7AOABvAAA+rwAAFS9AKBRvADAhLsAQCe7AGCuvQCgzzwA4Lm6AIAZPQAAr70AQES9AOApPQCA47wA4JG7AAAMPQDA+LsAgEG9AMACOwBAfjwAoBI7AOAVvQAAMb0AQAQ7AAAnPADAMjwAgG09AGAjvQCAdD0AQCC+AKAuPQCgkb0AwBo9AEC5PACgIbwAYC69ACAbPQBgpbsA4AO8ACBCOwCAnDsAoJ48AOA+vQBA5rsAgOO8AMDGPACgND0AYI28ACAmPQDAND0AwDk9AMD7vACA3DwAACc8AGBiPACgKT0AQP68PQAAgD8="
# 0.5
ENTITY1_FEATURE = "CKKcASKAEAAg0LwAYPa8AIAEPQAAgb0AII49AEBrvABgej0AAHo9AABtvADgZ70AQDE9AOBzvABANz0AoEG7AKDxPABAUroAwE69AICxvQDAcr0AIHQ9AGDYvAAgjzwAYIK9AMDqvQCgX70AgOY9AMAKugAgC7oAYC48AGDovQAgh7sA4Da5AMChPQBADT0A4Bu9AIBDvABgaDwAgBW9ACAGPADAQzgAQIs9AKBYPQBgMj0AwHK8AOACvQBAQDsAwLo9ACADvQDgSb0A4FO8AEBpPQDgwjoAYO28AKAIPABgpbkAYFi8AADIOwCgJLsAQPS8AGBZvACAhr0AYK08AKD4uwAgO7wAAAo8AKAVPQBg/7wAAMK7ACBdPQAgVD0AIFM9AAAEvADAFTwAYJ68ACC7vAAAKr0AwCI9AKBOvQCgYr0AgLu8AGBmugBgUTwAYG89AGAIPQBgBbsA4Ds9AMCWOwBAa7wAoBe9AEC6vABAHb0AYAM7AIB4vABggzkAICM6AIDavADgkD0AQPg8AOCjPQDgkbwAYJ06AIANvACAkT0AwNm8AGAkOwDAoL0AYOw8AGAgvABALD0AIIQ8ACBCvQBA0L0AgLc8ACDZuwDgoL0AQCO6AMAYPQAAELwAQIM7AEA7PQBgcjsAgOC6AOCdvQAA0z0AgA29AAAkvQCAHL0AgJ69AKDuvABgVT0AANG9AGBEvACghr0AoG49AEANvQCA1L0AIC+9AABcvQAgxb0AgCa9AEBnvQCAkb0AoHu9AMCEvADgXDwA4Jg7AGCXOwCgQT0AoHi8AICDvQBgLTwAwKm9AGBVPQAAgbwAYKk8AID7NwCgIr0AIBQ7AICTvACAn7wAoJG8AACJPQDgET0AYLe7AGB2PABgib0AwK89AGDVPAAAd7wAwEk8ACD6PABATjwAQHg9AED4uQAgLjsAYIy8ACA1uwDAzj0A4Pe7AOBRPABgNz0AoDE8AGAQPQDg9DsAYEs8AICjvQCAWr0A4FO8AOBRPQCAIb0AIP06AABCOgBACz0AIJC9AGAXvQBgIDwA4CM9AGDWPACgVz0AQCu9AODQvAAgsDwAwLW9ACCHuwAAJ7sAIDk8AMCTvACgGzwAIKm9AGCBvQBAsL0AIA07AECQvQCg7zoAALE8AKAaPQDgDjsAQO88AKBAvQBANzwAQPi8AKBRPADAKr0AoGS9AOAGvQAgK70AwHY9AABGPQBAXj0AQLE5AAAMvQAgF70AwNI8ACCjvQCAR70AQIs9AOCpvADA8L0AwFk9AGCRvQAAEzwAAI27AEBOPQCgeT0AIDi8AEApPADAib0AwGO9AMBbPQBAQD0AgE88AGBVPQCAgD0A4CE9AGAqOgCgPD0AIDM8AIBwvQBgDLkAALc8AICNvQCgPDwAgKw7AGAiuwBAjb0AgDo9AED/PQBAUL0AwCI9AGAHvQBA1LoAQIq9AMAYvQCArrwAoBK8AGDTvQCgOLwAgPE8AMBBOgDgmr0AAC89AAADuwDAqrsAoNe8AMDYPABA3z0AoDY9AADPvQAAgDwAAKA8AEAsPAAguLwAwFa9AGCBvQAgR70A4Cq9AIAFvQCAmbwAIHE8AKDDOwDgz7wAQPa5AKDUPACANbsA4Ku8ACBmPQBgNT0AwOA8AKBNvQDgmDwA4G69AEAQuwDgv70AwAU4ACAPvQBgEbwAAD09AOABOgDgqDwAYMK8AGDWPAAAfTwAQKA8AOD9vACgBL0AgKc8AMCdPAAglToAYAa8AGD9vAAAQD0AYJu8AOBGPQDgF70AYE89ACCwuwDgGbwAgBS+AEDhvQDAST0AIMK6AKAxuwDARb0AgL07AIBgvADALjwAoEo9ACA4vQDAE70AwKK9AKDxOwAAkTwAQDE9AACfPAAAIz0AwGA8AGAvvADAbzoAYOU8AMCbvADAZr0AgAO8AGCbuwDgiLwAQIa8AKBBPQDAwLwAAJa8AABPugDg3bsAoIo8AMC5vACAnL0AgIq8AEDBPACAbTgA4PW8AADGOgBA4b0AIMO8AABIvQAA3zwAQBA6ACCbvQDAET0AoOm8AEAqvQBAeb0AgCM9AGA5OwAgiD0AoLy8ACDDvAAgLT0AgJi9AAA3vQBgLDwA4LE8AGCOPQBgDj0AACO8AKAOvADAqjwAIBC9AIDNvACgazwAQFu7AIBdPQBA7DsAwIm8AAB5vQCg9TwAYCS9ACCMvQBAtL0AAOg7AECEvABglb0AAIe9AGAJvQBgdr0AAIe8AKB4vQDg/b0AQHE8ACB7vQAA7zoAwJW8AIChvQAgHr0AwCu9AOBJPADAN7wAAJ89AIBQPABATbwAYK09AECfPABgBjwAQNC8AMCUvQCg4TwAoJQ9AADsPACAq7wAYA49AIAlvADgML0AIGs9AIAEvQBgGLwAYPO8AOBPvACAgrwAgGe9AICuPAAgLr0AoJe8ACCYvACAxjsAYMU9AIDZvADAdD0AAFa7ACCnPADgDDsA4Gg8ACB+vADgMbwAYNw7ACDKPABgh70AwIY9AICPPQBgd70A4GA9ACC8PQDga70AwFa7AGBIvACgsTwAYIA9AODnPAAAir0AYJQ8AMBbPABgE7wAQA89AIC7PADAabwAwKm8AEB2vQDgSrsAIF66AECSugAgCD0AgFe9AAA7PADACD0AgGA9AED4OwDA/zoAYKq8AOCoPQDgZzwAYKU9AMC/PQCAYDwAgKE8AIDCvADAJz0AgJk9PQAAgD8="


# 内部辅助函数，封装当前模块的局部逻辑。
def _assert_results(payload: dict[str, object], expected_repo_ids: set[str]) -> None:
    results = extract_search_results(payload)
    if not results:
        raise AssertionError("expected multi-repo search results")
    if set(extract_result_repo_ids(results)) != expected_repo_ids:
        raise AssertionError(f"expected results from {sorted(expected_repo_ids)}")
    if not is_nonincreasing(extract_result_similarities(results)):
        raise AssertionError("expected nonincreasing similarities")


# 执行当前场景的核心流程。
async def run_scenario(*, repo_api, entity_api, search_api, output_root: Path | None = None) -> dict[str, object]:
    collector, store, summary_path, _ = build_business_runtime(Path(__file__), "search", "multi_repo_", output_root)
    repo_a_id = make_repo_id("repo-mul-1")
    repo_b_id = make_repo_id("repo-mul-2")
    overall_status = "passed"
    case_results: list[dict[str, object]] = []

    try:
        repo_payload = {"type": "person", "index_type": "int8", "level": "ram", "options": {"PreFilter": "false"}}
        for case_id, repo_id in [("repo-a", repo_a_id), ("repo-b", repo_b_id)]:
            created = await create_repo(repo_api, store, repo_id=repo_id, payload={**repo_payload, "id": repo_id}, case_id=f"{case_id}-create", name=f"create {case_id}")
            create_ok = created.status_code in {200, 201, 202}
            if not create_ok:
                overall_status = "failed"
            create_reason = None if create_ok else failure_reason_or_body(created.response_body, f"expected 200/201/202, got {created.status_code}")
            record_step(collector, case_results, prefix="multi_repo_", case_id=f"{case_id}-create", expected_status="200/201/202", actual_status=created.status_code, passed=create_ok, failure_reason=create_reason)

            if create_ok:
                ready = await wait_repo_ready(repo_api, store, repo_id=repo_id, timeout_s=30.0)
                ready_ok = ready.status_code == 200
                if not ready_ok:
                    overall_status = "failed"
                ready_reason = None if ready_ok else failure_reason_or_body(ready.response_body, f"expected 200, got {ready.status_code}")
                record_step(collector, case_results, prefix="multi_repo_", case_id=f"{case_id}-ready", expected_status=200, actual_status=ready.status_code, passed=ready_ok, failure_reason=ready_reason)

        for idx in range(1, 4):
            entity_record = await create_entity(entity_api, store, repo_id=repo_a_id, entity_id=f"a-entity1-{idx}", payload={"id": f"a-entity1-{idx}", "data": {"type": "feature", "value": ENTITY1_FEATURE}, "location_id": "1"}, case_id=f"repo-a-entity1-{idx}", name=f"create repo a entity1 {idx}")
            entity_ok = entity_record.status_code == 201
            if not entity_ok:
                overall_status = "failed"
            entity_reason = None if entity_ok else failure_reason_or_body(entity_record.response_body, f"expected 201, got {entity_record.status_code}")
            record_step(collector, case_results, prefix="multi_repo_", case_id=f"repo-a-entity1-{idx}", expected_status=201, actual_status=entity_record.status_code, passed=entity_ok, failure_reason=entity_reason)

            entity_record = await create_entity(entity_api, store, repo_id=repo_a_id, entity_id=f"a-entity2-{idx}", payload={"id": f"a-entity2-{idx}", "data": {"type": "feature", "value": ENTITY2_FEATURE}, "location_id": "0"}, case_id=f"repo-a-entity2-{idx}", name=f"create repo a entity2 {idx}")
            entity_ok = entity_record.status_code == 201
            if not entity_ok:
                overall_status = "failed"
            entity_reason = None if entity_ok else failure_reason_or_body(entity_record.response_body, f"expected 201, got {entity_record.status_code}")
            record_step(collector, case_results, prefix="multi_repo_", case_id=f"repo-a-entity2-{idx}", expected_status=201, actual_status=entity_record.status_code, passed=entity_ok, failure_reason=entity_reason)

        for idx in range(1, 4):
            entity_record = await create_entity(entity_api, store, repo_id=repo_b_id, entity_id=f"b-entity1-{idx}", payload={"id": f"b-entity1-{idx}", "data": {"type": "feature", "value": ENTITY1_FEATURE}, "location_id": "1"}, case_id=f"repo-b-entity1-{idx}", name=f"create repo b entity1 {idx}")
            entity_ok = entity_record.status_code == 201
            if not entity_ok:
                overall_status = "failed"
            entity_reason = None if entity_ok else failure_reason_or_body(entity_record.response_body, f"expected 201, got {entity_record.status_code}")
            record_step(collector, case_results, prefix="multi_repo_", case_id=f"repo-b-entity1-{idx}", expected_status=201, actual_status=entity_record.status_code, passed=entity_ok, failure_reason=entity_reason)

            entity_record = await create_entity(entity_api, store, repo_id=repo_b_id, entity_id=f"b-entity2-{idx}", payload={"id": f"b-entity2-{idx}", "data": {"type": "feature", "value": ENTITY2_FEATURE}, "location_id": "0"}, case_id=f"repo-b-entity2-{idx}", name=f"create repo b entity2 {idx}")
            entity_ok = entity_record.status_code == 201
            if not entity_ok:
                overall_status = "failed"
            entity_reason = None if entity_ok else failure_reason_or_body(entity_record.response_body, f"expected 201, got {entity_record.status_code}")
            record_step(collector, case_results, prefix="multi_repo_", case_id=f"repo-b-entity2-{idx}", expected_status=201, actual_status=entity_record.status_code, passed=entity_ok, failure_reason=entity_reason)

        search_record = await search_query(search_api, store, payload={"type": "person", "include": [{"data": {"value": ENTITY1_FEATURE, "type": "feature"}}], "repositories": [repo_a_id, repo_b_id], "max_candidates": 12, "topk": 12}, case_id="search", name="multi repo search")
        search_ok = search_record.status_code == 200
        search_reason = None
        if search_ok:
            try:
                _assert_results(search_record.response_body, {repo_a_id, repo_b_id})
            except Exception as exc:
                search_ok = False
                search_reason = describe_search_failure(search_record.response_body, str(exc))
        else:
            search_reason = describe_search_failure(search_record.response_body, f"expected 200, got {search_record.status_code}")
        if not search_ok:
            overall_status = "failed"
            search_reason = search_reason or describe_search_failure(search_record.response_body, "search validation failed")
        record_step(collector, case_results, prefix="multi_repo_", case_id="search", expected_status="200 + results from both repos + nonincreasing similarity", actual_status=search_record.status_code, passed=search_ok, failure_reason=search_reason)
    except Exception as exc:
        overall_status = "failed"
        record_step(collector, case_results, prefix="multi_repo_", case_id="scenario-error", expected_status="no exception", actual_status=None, passed=False, failure_reason=str(exc))
    finally:
        for repo_id, cleanup_case in [(repo_a_id, "cleanup-repo-a"), (repo_b_id, "cleanup-repo-b")]:
            try:
                cleanup = await cleanup_repo(repo_api, store, repo_id=repo_id, name=f"cleanup {repo_id}")
                record_step(collector, case_results, prefix="multi_repo_", case_id=cleanup_case, expected_status="200/202/204/404", actual_status=cleanup.status_code, passed=True)
            except Exception as exc:
                overall_status = "failed"
                record_step(collector, case_results, prefix="multi_repo_", case_id=f"{cleanup_case}-error", expected_status="cleanup ok", actual_status=None, passed=False, failure_reason=str(exc))

        summary = finalize_search_summary(collector, summary_path, overall_status=overall_status, extra={"repo_ids": [repo_a_id, repo_b_id], "case_total": len(case_results), "case_results": case_results})
    return summary


# 程序入口，用于串起当前模块的执行流程。
async def main() -> None:
    async with open_business_apis(repo=True, entity=True, search=True) as apis:
        summary = await run_scenario(repo_api=apis["repo_api"], entity_api=apis["entity_api"], search_api=apis["search_api"])
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if os.environ.get("API_TEST_IMPORT_ONLY") == "1":
        raise SystemExit(0)
    asyncio.run(main())
