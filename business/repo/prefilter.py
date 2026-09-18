"""用于校验仓库预过滤配置、实体写入与搜索链路的业务场景脚本。"""
# 流程：
# 1. 先清理固定名称仓库，再创建 repo-prefilter-true 和 repo-prefilter-true-with-entity3，均为 person/int8/ram、PreFilter=true。
#    创建正常时预期 202；如果客户端超时，则轮询确认仓库是否最终进入 READY，避免把“请求超时但资源创建成功”误判成失败。
# 2. 在 repo-prefilter-true 创建 entity-1-1 ~ entity-1-10；1~5 的 location_id=1，6~10 的 location_id=0。
# 3. 在同一仓库创建 entity-2-11 ~ entity-2-20；11~15 的 location_id=1，16~20 的 location_id=0。
# 4. 在 repo-prefilter-true-with-entity3 重复上述 20 条实体，再创建 entity-3-1 ~ entity-3-3，location_id=0（最相似但位置不符，作为前过滤的干扰项）。
# 5. 每个仓库各自记录自己的时间窗（t1=第一批、t2=第二批），search 的 include 统一使用 ENTITY3_FEATURE；
#    开跑前先做一次"可见性预热"（轮询到无过滤搜索有结果），避免索引未可见被误判成前过滤把结果全过滤。
# 6. 场景一 search-location-time：repo1，locations=[1] + 第一批时间窗 t1_start~t1_end，期望精确返回 entity-1-1 ~ entity-1-5。
# 7. 场景二 search-location-only：repo2，locations=[1]，期望精确返回 entity-2-11 ~ entity-2-15（最相似的 entity-3-* 位置=0，必须被过滤掉）。
# 8. 场景三 search-time-only：repo1，第二批时间窗 t2_start~t2_end、max_candidates=10，期望精确返回 entity-2-11 ~ entity-2-20。
# 9. 三个 search 场景均要求 HTTP 200、结果非空、ID 集合精确匹配、similarity 非递增；
#    每个用例把"预期返回/实际返回"写进 summary（expected_result / actual_outcome），供 HTML 报告展示。
# 10. 最后删除两个仓库并确认不存在。
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    repo_root = str(Path(__file__).resolve().parents[3])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

from API_TEST.business.repo._scenario_support import failure_reason_from_body, finalize_repo_summary, poll_and_save, record_case_result
from API_TEST.business.support import build_business_runtime, extract_result_similarities, extract_search_results, is_nonincreasing, load_business_config, open_business_apis


REPO_IDS = ["repo-prefilter-true", "repo-prefilter-true-with-entity3"]
REPO_CREATE_TIMEOUT_S = float(os.environ.get("REPO_CREATE_TIMEOUT_S", "180"))
REPO_EVENTUAL_READY_TIMEOUT_S = float(os.environ.get("REPO_EVENTUAL_READY_TIMEOUT_S", "180"))
REPO_READY_TIMEOUT_S = float(os.environ.get("REPO_READY_TIMEOUT_S", "30"))
REPO_BATCH_GAP_SECONDS = float(os.environ.get("REPO_BATCH_GAP_SECONDS", "1.2"))
REPO_WINDOW_MARGIN_MS = int(os.environ.get("REPO_WINDOW_MARGIN_MS", "500"))


def _now_ms() -> int:
    return int(time.time() * 1000)


def _is_repo_ready(record) -> bool:
    body = record.response_body
    return (
        record.status_code == 200
        and isinstance(body, dict)
        and str(body.get("status", "")).upper() == "READY"
    )


# 1
ENTITY3_FEATURE = "CKKcASKAEADgxrwAAF69AKAnPADgjrwAYOU8AIAavQBACbwAgJM9AID4PACAiTwAwP48AEA0vABATj0AII08AMCdPACgdroAYJW8AACLvQCgDDwAoGm8AKBPPADgmbwAoJc8AIAHPQDgU70AwI29ACCdvQCARroA4FC8AOAdvQDgbTwAoB+8AKDVOgDAqr0A4HK8AOC2vQCg/T0AYMM8AMBmPQAgmr0A4KE9AEA3vQAghL0AYLe9ACCqvACASjoA4F09AEAHvQCgo7wAQMe8AACKPQAAer0AIMA8AECJPQBgkTwAYK28AKChvABAi7wAAGm9AEBpuwCAeL0AwF89AOCVPQDgbbsAoFk9AOCqPACA/DwAgIM7AEBNvQDAMjwAgG08ACDtPACAyrsAYKo8AOBQvABgOb0AoA89AMABugCA4jsAIGM8AMClvQAAw7wA4Pg8AAALugCAJj0AYGy9AICLvQCAnTwAQOw7AIDtPAAg67wAQLc8AEDhvADgO70AIEM8AMBePQDAL70AgDQ9AMCVPQBgEj0AoEQ8AODEPABAT7wAwBU9AOByvABAhD0AgBS9AKDaPABAkDwAAKM7AGAyvADgG70AIAI9ACAbvQBgiTwAIDo9AOAYPACAIz0AQC88AKDKPACgkzwAoFc8AIAfvQDgajwAoAo7AMCtvACAMTwAoBI9AGAyvACAcL0A4MO9ACCPPACgvT0AIBS9AEBZPQAgbLwAYLQ8AEB7vQDgyDwAYAy9AOAcvQDAY70A4IE9AECOPQDgUzwAIEs9AKBFPADgjjsAIAE9AMBXPQAAMzwAYGk8AAAcPQCgOjwAoNi7AABzuQAgGb0AoD29AKACvgBgHL0AYC68AABBPQBgPz0AIPg7AIADvABAj70AABa9AOBOPQBAmbwAwIA7AMDrPADAZj0AYCq9AMCEugAgBb0AQP87AOBlvQAgGD0AIIG8ACCSvACAiL0AYOQ8AADVvQAgFD0AoDU8AAAGvQAAk7wAwJ08AKAbPQDghz0AIJ68AGBEvADgMT0A4HO8AKArvQDA77wAwES8AOBRPQBAHb0AwGm9ACB4vQCA0zwAoGW8AOBEvADAjTwAQB89AKCWPABgubsAACM9AGDsvQBAH70AoI89AMB+vADAXz0A4Ck9AMBfvQBgnzwAQFk9AEB5PQBAOL0AgMK8ACAGvQCg/DsAYDa9AOBiPABAzbwAINu9AIA5vQAAJz0AQK26ACAbvQDAW70AAHG8AMCHPQAAHr0AQI69AMAevQCAsToAoFA9AGACvABgUD0A4MQ8AEA8PQDAVjwAQFW7AIDlvAAgPbwAIOC8AEALvADgiL0AIG+9AGAvOwCgM70AYAc+AOBTOgAAMzwAIIQ9AODlvADgCL4AICW9AOA0vQCASL0A4Bg8AEDePABAPzwAQPu8AAAvvQDAgb0AQPw8ACANvgAg0rwAwJ68AMDjPAAgAbsAwMK8AEDRvACgtD0AgIU8AMCmOwDA+zwAwDc5ACBPvABgErwAQD29AIBCPQCgZbwAwNQ9AAAOuwCgfDsAACg9AOBePQDgFD0AQBw7AKCOvABgcL0AYM47AMBTPABAuDwAwAi9AMCCvAAgjjsAQK45AIClPQDAJL0AwFk8ACD/PQAA/bwAYCO8AKDpvADgqbwAIKG8AKD1vACAJ70AAOA0AMCRPQCg7zsAAGM8AODWPABAUr0AoO68AABzPABguzwAgNU9AEDKvQAAST0AoL89AGCuvABgrr0AIBW9ACAHPQDAtjwAINA7AEBsugCgpDwAoPU8AICTOgBgiTwAII29ACD/PAAA4TwAYEY9AECKPQCgLToAoHI9AADjPQDAAL4AYLO6AECgOwDgC70AoNW7AMBOuwDAurwAgOc8AEAFvADAozwAoAe7AABZvABAzbwAYBO9AGAUPQDA9DsAoEK8AICjvADgG70AwEu9AECsuwCgNT0AAFg9AKC7OgAACz4AQLw8AKC/vADAC70AQHM9AMBrvQDg97wAwKm7AED+vABg+LsAIFA9ACA7PQBgXLwAwKu8AMCqOwDAY7wAQLS8ACB3PAAgDLsAQHw9AIByvQAAmLwAQAW9AGADPgCArr0AgM48AGAjPAAghL0AgGK7AEALvQBAVTwAgBE9AGDjOgBAuL0AwC08AACmPAAgu70AgF+8ACBrvACgFT0AIMe8AGC7OwCgBr0AADm8AGBjPADgFz0AwA29AOCCvQBAKDwA4Kw8AKD8vADAhjwAQN08AGAVPgDgSD0AABM8AKAcvQBgFroAAEk8AECXPADAUz0AgOA9AIAevQAAcbwAQHM9AOAaPQCAmT0AAJc9AOBdvQCgx70AoOq8ACDLPACg0bwAAAI9AKA1PACAurwAAOE5AOCFPQBgz7wAQMQ8AAC+vQAgRrwAgIy9AOAgPQAAVD0AAC09ACAhOgCAS70AIEa9AGD+uwDAX70A4LU8AICDvQCg/bsAQJw7AIAhPQAgd70AgKu9AGAwPAAgIDwAQJg7AED8PAAAobwAYN68AIB/PADgtjwA4Jq8AKD3vABgKr0AwL86AACHOwDgQbwAQDw9AOBtvABgOz0AYP69AECxPQDgsr0AoFI9AABBPQCgMrsAAOG8ACDCOwBAuTsAABO8AOAqOwBAN70A4OY8AKCXvQDgUzsAgJM7AEC5PAAgSj0A4Ce9ACBVOwDgBz0AYGQ7AOB1vACAYDwAANg8AIASPQCgAD0AwGy9PQAAgD8="
# 0.9
ENTITY2_FEATURE = "CKKcASKAEABgNDsA4JS8AMALPQDAO7wAAOm8AMAiPABg0rwAAGM9AADLPAAA4zwAwPw8AKAGPAAAoD0AwMQ7AECpPABg2LkAYHm7ACAYvADgZzoA4Pa7AAC7vACAdb0AgMo6AADdPAAAVr0AYKS9AGC0vQCAj7oAAJI6AOB6vQCAZbwAYFi7AOAwPACgkr0AAIm9AKCPvQDg6T0AYJa7AOD7PAAArb0AQNM8AABJvABgtL0AYLy9AABFvQBAMjoAwIQ9AAD4vADgjzwA4Ge8AGCyPQBgL70AYDm7AACJPQBgPT0AAM68AMAEvACgYL0AgMq9AEClvAAAXb0AQIs9AOBVPQCAwrwAAGk9ACDhPACgDD0AIJ87AIDovABgST0AII+8ACCNPQAghL0AQIu8AOCgvADgEL0AgKA9AICmPQCgorwAIHS7AGCmvQDgPr0AwMa8AMCZPABgqLsA4Je8AECOvQDAAT0AgGc9AEA0PQAAF70AQOS7ACA3vQCAmb0AAJc8AAAxPQCAtrsAADE9AMBkPABgQzwAoFG8AMDvPADAd7wAwFI7AIA2uwCAQj0AgG+9AEBxvABg8TwAwDQ8AAA4PACgz7oAwDM9AKC5vAAAsDwAwAg9AIAbPQAAmz0AIH48AKCSPABgaDwAIAY9AAB8vQDgSz0AoOA7AEAQvQBgAj0AgCG8ACBlvQCAt7wAYKW9AGCAPAAAMD0AwEu9AMDRPQDADr0A4CE9AADIvADgLT0AwPS6AKCYvQAA4bwAAD09AICcPAAAhLwAoPA7ACCPvACAAb0AQD49AACJPQBgRb0AIB+9ACAvPQCgoLwAoME8AKAvugBgKr0AAEe9AMDRvQCgtrwAYBO8AAC3PQDAbrwAQBC9ACD+OwCAqLwAQKi8ACBHPADAtbwAQJk8AOA9PQDghD0AQAK9AAAMuwBAa70AIH+8AEAevQAgGzwAYGi8AAApvQBgar0AoLY8ACBDugDAID0AQFi8AAC7vABg7rsA4C09ACABPQCgcj0A4Pk8AECCPABAnjwAgP68AEDEvADgpLwAoLC8AGCaPADAfb0A4CG9AICBvQCgFT0AwBk8AKBmvQCgWrwAwG49AKAbOwAArDwAoAg9AOD0vQDALrsAQCU9AGBqvQCAMT0AoDk9AIDfvQAAhDsAgJ28AOAnPQDgM7wA4Jo8AECIvAAABTwAYIm9AICEvQAgFj0AgKm9AOAXvQDgWz0AgIm5AKDhvADgBL0A4Fs8AICHPQCgBb0AYBO9AEAEvQAgpzwAQJw9AADdvABAZTwAgC49AABBPACgUrwAIPO8AIBEvQCgW70AoOC8AIDmuwDgS70AYAm9AOCwvAAAn70AAG49AGAtuwCgNDwAQOk8AOBJPADA2L0AYNe8AKAFOwCAPbwA4OK6AEBQPQDA/DwAAA29AAA/vQCgpLwAgFO8AODzvQCADb0AoCm5AEBYPQCgADwAQKm8AGDVvABgWz0AwP28AIC2OwDAhDoAwO48AECfvAAAB7wAIB69AEAHPQBgvDwAYJI9AGBXPADgnrwAQI08AMC/PQDAeDwAQNe7AKCnPAAAILwAQBO9AECzPQCggjwAoA87AGB/vAAgM70AwAA6AKDaPQBgS7wAIOw8AAAOPgAAV70AIIy8AICPPADgwjwAgAs7AICfuwBgirwAAIM3AGCEPQBgNz0AwA49AGBYvAAAB7wAQJW9AIDzOwCApT0A4Fs9AIC9vQDglT0AoNo9AODovAAgTb0AoBe9AGBFPQAgYjwAgBS9AGAzvQBA8LoAgFA9ACCDugBABz0AAFy9AOCqPQBAyLwA4Jc8AMAiPQAgFDwAABs9AECgPQBgDL4AoE08AOBnPQDAHr0A4O47AEDSPADgo7wAYK+8AOC9PABAVz0AgCw9ACAZvQAgX70AgK85AECaPQBAy7sAgOm7AMCAuwCAYzgAQAa8AKDRvACgDjwAoFI9AIA+OgAA/D0AILq6ACCquwBgsrwAAKU9AOA4vQDABL0AgBM9AGCEvQDgajwA4AE9AGAeuwBgAL0AgH69AMAtPQDgsbwA4J69AMBBvAAAJjkAoGw9AGBuvQDAlrsAQBq8AECGPQBAO70AgCI9AKCGuwDAIr0AQEi8AEAjvQBAQbwAIEA8AGCHPABAlL0AQC+8AKAAPQCgvb0AQPC8AGAZvQDA/LwAoAi9AOCRPABgBrsAAES9AIB7PQDgIj0AwI27AKDZvQDAszsA4BE9AMDwvACACj0AYLc6AMADPgCAGj0AIBU8AEBwuwCAfLgA4O48AIC4PQBA2TwAIPg9ACBkuwDAjLsAoMY9AMBqOgBgdj0AYJM8AGAXvQCgxzwAwLG9AED2PAAgSbwAgFA9AKD9PAAAI70AIIY9AIBQPQCgML0AAHQ9AAC3vQDgijoAwLu8AGDoPADAAD0AIOQ7AOABvAAA+rwAAFS9AKBRvADAhLsAQCe7AGCuvQCgzzwA4Lm6AIAZPQAAr70AQES9AOApPQCA47wA4JG7AAAMPQDA+LsAgEG9AMACOwBAfjwAoBI7AOAVvQAAMb0AQAQ7AAAnPADAMjwAgG09AGAjvQCAdD0AQCC+AKAuPQCgkb0AwBo9AEC5PACgIbwAYC69ACAbPQBgpbsA4AO8ACBCOwCAnDsAoJ48AOA+vQBA5rsAgOO8AMDGPACgND0AYI28ACAmPQDAND0AwDk9AMD7vACA3DwAACc8AGBiPACgKT0AQP68PQAAgD8="
# 0.5
ENTITY1_FEATURE = "CKKcASKAEAAg0LwAYPa8AIAEPQAAgb0AII49AEBrvABgej0AAHo9AABtvADgZ70AQDE9AOBzvABANz0AoEG7AKDxPABAUroAwE69AICxvQDAcr0AIHQ9AGDYvAAgjzwAYIK9AMDqvQCgX70AgOY9AMAKugAgC7oAYC48AGDovQAgh7sA4Da5AMChPQBADT0A4Bu9AIBDvABgaDwAgBW9ACAGPADAQzgAQIs9AKBYPQBgMj0AwHK8AOACvQBAQDsAwLo9ACADvQDgSb0A4FO8AEBpPQDgwjoAYO28AKAIPABgpbkAYFi8AADIOwCgJLsAQPS8AGBZvACAhr0AYK08AKD4uwAgO7wAAAo8AKAVPQBg/7wAAMK7ACBdPQAgVD0AIFM9AAAEvADAFTwAYJ68ACC7vAAAKr0AwCI9AKBOvQCgYr0AgLu8AGBmugBgUTwAYG89AGAIPQBgBbsA4Ds9AMCWOwBAa7wAoBe9AEC6vABAHb0AYAM7AIB4vABggzkAICM6AIDavADgkD0AQPg8AOCjPQDgkbwAYJ06AIANvACAkT0AwNm8AGAkOwDAoL0AYOw8AGAgvABALD0AIIQ8ACBCvQBA0L0AgLc8ACDZuwDgoL0AQCO6AMAYPQAAELwAQIM7AEA7PQBgcjsAgOC6AOCdvQAA0z0AgA29AAAkvQCAHL0AgJ69AKDuvABgVT0AANG9AGBEvACghr0AoG49AEANvQCA1L0AIC+9AABcvQAgxb0AgCa9AEBnvQCAkb0AoHu9AMCEvADgXDwA4Jg7AGCXOwCgQT0AoHi8AICDvQBgLTwAwKm9AGBVPQAAgbwAYKk8AID7NwCgIr0AIBQ7AICTvACAn7wAoJG8AACJPQDgET0AYLe7AGB2PABgib0AwK89AGDVPAAAd7wAwEk8ACD6PABATjwAQHg9AED4uQAgLjsAYIy8ACA1uwDAzj0A4Pe7AOBRPABgNz0AoDE8AGAQPQDg9DsAYEs8AICjvQCAWr0A4FO8AOBRPQCAIb0AIP06AABCOgBACz0AIJC9AGAXvQBgIDwA4CM9AGDWPACgVz0AQCu9AODQvAAgsDwAwLW9ACCHuwAAJ7sAIDk8AMCTvACgGzwAIKm9AGCBvQBAsL0AIA07AECQvQCg7zoAALE8AKAaPQDgDjsAQO88AKBAvQBANzwAQPi8AKBRPADAKr0AoGS9AOAGvQAgK70AwHY9AABGPQBAXj0AQLE5AAAMvQAgF70AwNI8ACCjvQCAR70AQIs9AOCpvADA8L0AwFk9AGCRvQAAEzwAAI27AEBOPQCgeT0AIDi8AEApPADAib0AwGO9AMBbPQBAQD0AgE88AGBVPQCAgD0A4CE9AGAqOgCgPD0AIDM8AIBwvQBgDLkAALc8AICNvQCgPDwAgKw7AGAiuwBAjb0AgDo9AED/PQBAUL0AwCI9AGAHvQBA1LoAQIq9AMAYvQCArrwAoBK8AGDTvQCgOLwAgPE8AMBBOgDgmr0AAC89AAADuwDAqrsAoNe8AMDYPABA3z0AoDY9AADPvQAAgDwAAKA8AEAsPAAguLwAwFa9AGCBvQAgR70A4Cq9AIAFvQCAmbwAIHE8AKDDOwDgz7wAQPa5AKDUPACANbsA4Ku8ACBmPQBgNT0AwOA8AKBNvQDgmDwA4G69AEAQuwDgv70AwAU4ACAPvQBgEbwAAD09AOABOgDgqDwAYMK8AGDWPAAAfTwAQKA8AOD9vACgBL0AgKc8AMCdPAAglToAYAa8AGD9vAAAQD0AYJu8AOBGPQDgF70AYE89ACCwuwDgGbwAgBS+AEDhvQDAST0AIMK6AKAxuwDARb0AgL07AIBgvADALjwAoEo9ACA4vQDAE70AwKK9AKDxOwAAkTwAQDE9AACfPAAAIz0AwGA8AGAvvADAbzoAYOU8AMCbvADAZr0AgAO8AGCbuwDgiLwAQIa8AKBBPQDAwLwAAJa8AABPugDg3bsAoIo8AMC5vACAnL0AgIq8AEDBPACAbTgA4PW8AADGOgBA4b0AIMO8AABIvQAA3zwAQBA6ACCbvQDAET0AoOm8AEAqvQBAeb0AgCM9AGA5OwAgiD0AoLy8ACDDvAAgLT0AgJi9AAA3vQBgLDwA4LE8AGCOPQBgDj0AACO8AKAOvADAqjwAIBC9AIDNvACgazwAQFu7AIBdPQBA7DsAwIm8AAB5vQCg9TwAYCS9ACCMvQBAtL0AAOg7AECEvABglb0AAIe9AGAJvQBgdr0AAIe8AKB4vQDg/b0AQHE8ACB7vQAA7zoAwJW8AIChvQAgHr0AwCu9AOBJPADAN7wAAJ89AIBQPABATbwAYK09AECfPABgBjwAQNC8AMCUvQCg4TwAoJQ9AADsPACAq7wAYA49AIAlvADgML0AIGs9AIAEvQBgGLwAYPO8AOBPvACAgrwAgGe9AICuPAAgLr0AoJe8ACCYvACAxjsAYMU9AIDZvADAdD0AAFa7ACCnPADgDDsA4Gg8ACB+vADgMbwAYNw7ACDKPABgh70AwIY9AICPPQBgd70A4GA9ACC8PQDga70AwFa7AGBIvACgsTwAYIA9AODnPAAAir0AYJQ8AMBbPABgE7wAQA89AIC7PADAabwAwKm8AEB2vQDgSrsAIF66AECSugAgCD0AgFe9AAA7PADACD0AgGA9AED4OwDA/zoAYKq8AOCoPQDgZzwAYKU9AMC/PQCAYDwAgKE8AIDCvADAJz0AgJk9PQAAgD8="


# 内部辅助函数，封装当前模块的局部逻辑。
async def _wait_repo_ready(repo_api, store, *, repo_id: str, timeout_s: float = 30.0):
    # 实现当前模块的核心逻辑。
    async def getter():
        return await repo_api.get(None, case_id=f"repo-ready-{repo_id}", module="repo", action="get", name=f"wait repo {repo_id} ready", path=f"/repositories/{repo_id}")

    return await poll_and_save(store, getter, _is_repo_ready, timeout_s=timeout_s)


# 内部辅助函数，封装当前模块的局部逻辑。
async def _ensure_repo_deleted(repo_api, store, *, repo_id: str, timeout_s: float = 60.0):
    # 实现当前模块的核心逻辑。
    async def getter():
        return await repo_api.get(None, case_id=f"repo-delete-{repo_id}", module="repo", action="get", name=f"wait repo {repo_id} deleted", path=f"/repositories/{repo_id}")

    return await poll_and_save(store, getter, lambda record: record.status_code in {400, 404}, timeout_s=timeout_s)


async def _prepare_repo(repo_api, store, *, repo_id: str, timeout_s: float = 60.0) -> None:
    """清理上次异常退出可能残留的固定仓库，确保创建步骤从干净状态开始。"""

    deleted = await repo_api.delete(
        None,
        case_id=f"preclean-{repo_id}",
        module="repo",
        action="delete",
        name=f"preclean {repo_id}",
        path=f"/repositories/{repo_id}",
    )
    store.save(deleted)
    if deleted.status_code in {200, 202, 204}:
        await _ensure_repo_deleted(repo_api, store, repo_id=repo_id, timeout_s=timeout_s)
    elif deleted.status_code != 404:
        reason = failure_reason_from_body(deleted.response_body, f"preclean failed with status {deleted.status_code}")
        raise RuntimeError(f"failed to preclean repository {repo_id}: {reason}")


# 内部辅助函数，封装当前模块的局部逻辑。
async def _create_repo(
    repo_api,
    store,
    *,
    repo_id: str,
    collector,
    overall_status_ref: dict[str, str],
) -> tuple[bool, object, str | None]:
    payload = {
        "id": repo_id,
        "type": "person",
        "index_type": "int8",
        "level": "ram",
        "options": {"PreFilter": "true"},
    }
    created = await repo_api.create(
        payload,
        case_id=f"create-{repo_id}",
        module="repo",
        action="create",
        name=f"create {repo_id}",
        path="/repositories",
        timeout_s=REPO_CREATE_TIMEOUT_S,
    )
    store.save(created)
    if created.status_code in {200, 201, 202}:
        collector.record_success(f"create_{repo_id}")
        return True, created, None

    if created.error_type == "TimeoutError" or created.status_code is None:
        ready = await _wait_repo_ready(
            repo_api,
            store,
            repo_id=repo_id,
            timeout_s=REPO_EVENTUAL_READY_TIMEOUT_S,
        )
        if _is_repo_ready(ready):
            collector.record_success(f"create_{repo_id}")
            warning = (
                f"create request timed out after {created.elapsed_ms:.0f}ms, "
                f"but repository {repo_id} became READY eventually"
            )
            return True, created, warning

    overall_status_ref["value"] = "failed"
    reason = (
        f"create request failed: status={created.status_code}, "
        f"error_type={created.error_type}, elapsed_ms={created.elapsed_ms:.0f}, "
        f"body={created.response_body}"
    )
    collector.record_failure(f"create_{repo_id}", reason)
    return False, created, reason


# 内部辅助函数，封装当前模块的局部逻辑。
async def _create_entity(entity_api, store, *, repo_id: str, entity_id: str, feature_value: str, location_id: str, case_id: str, collector, overall_status_ref: dict[str, str]):
    payload = {"id": entity_id, "data": {"type": "feature", "value": feature_value}, "location_id": location_id}
    record = await entity_api.create(payload, case_id=case_id, module="entity", action="create", name=f"create entity {entity_id}", path=f"/repositories/{repo_id}/entities")
    store.save(record)
    ok = record.status_code == 201
    if ok:
        collector.record_success(case_id)
    else:
        overall_status_ref["value"] = "failed"
        reason = failure_reason_from_body(record.response_body, f"expected 201, got {record.status_code}")
        collector.record_failure(case_id, reason)
    return record, ok


# 内部辅助函数，封装当前模块的局部逻辑。
def _build_search_payload(*, repo_id: str, locations: list[str] | None = None, start_time: int | None = None, end_time: int | None = None, max_candidates: int = 5) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": "person",
        "include": [{"data": {"value": ENTITY3_FEATURE, "type": "feature"}}],
        "repositories": [repo_id],
        "max_candidates": max_candidates,
    }
    if locations is not None:
        payload["locations"] = locations
    if start_time is not None:
        payload["start_time"] = start_time
    if end_time is not None:
        payload["end_time"] = end_time
    return payload


# 内部辅助函数，封装当前模块的局部逻辑。
def _assert_expected_ids(results: list[dict[str, object]], expected_ids: set[str]) -> bool:
    return {str(item.get("id")) for item in results if item.get("id") is not None} == expected_ids


# 内部辅助函数：轮询"无过滤搜索有结果"，用于区分"索引还没可见"和"前过滤把候选全过滤了"。
async def _wait_search_visible(search_api, store, *, repo_id: str, timeout_s: float = 60.0, interval_s: float = 2.0) -> tuple[bool, str]:
    deadline = time.monotonic() + timeout_s
    attempts = 0
    status_code: int | None = None
    result_count = 0
    while True:
        attempts += 1
        payload = _build_search_payload(repo_id=repo_id, max_candidates=5)
        record = await search_api.query(payload, case_id="search-visibility", module="search", action="query", name="search visibility warmup", path="/repositories/search")
        store.save(record)
        results = extract_search_results(record.response_body)
        status_code = record.status_code
        result_count = len(results)
        if status_code == 200 and result_count > 0:
            return True, f"attempts={attempts} status={status_code} results={result_count}"
        if time.monotonic() >= deadline:
            return False, f"attempts={attempts} status={status_code} results={result_count}（等待 {timeout_s:.0f}s 超时）"
        await asyncio.sleep(interval_s)


# 执行当前场景的核心流程。
async def run_scenario(*, repo_api, entity_api, search_api, output_root: Path | None = None) -> dict[str, object]:
    load_business_config("repo", "prefilter")
    collector, store, summary_path, _ = build_business_runtime(Path(__file__), "repo", "prefilter", output_root)
    overall_status_ref = {"value": "passed"}
    case_results: list[dict[str, object]] = []
    repo_ids = list(REPO_IDS)
    entity1_ids: list[str] = []
    entity2_ids: list[str] = []
    entity3_ids: list[str] = []
    windows: dict[str, dict[str, int]] = {repo_id: {} for repo_id in repo_ids}
    visibility_warmup_detail = ""

    try:
        for repo_id in repo_ids:
            await _prepare_repo(repo_api, store, repo_id=repo_id, timeout_s=60.0)
            created_ok, created, create_warning = await _create_repo(
                repo_api,
                store,
                repo_id=repo_id,
                collector=collector,
                overall_status_ref=overall_status_ref,
            )
            record_case_result(
                case_results,
                prefix="prefilter",
                case_id=f"create-{repo_id}",
                expected_status="202 或创建超时后最终 READY",
                actual_status=created.status_code if created.status_code is not None else created.error_type,
                passed=created_ok,
                failure_reason=None if created_ok else create_warning,
                extra={"warning": create_warning} if create_warning else None,
            )
            if not created_ok:
                raise RuntimeError(f"repository create failed, aborting scenario: {repo_id}")

            ready = await _wait_repo_ready(repo_api, store, repo_id=repo_id, timeout_s=REPO_READY_TIMEOUT_S)
            ready_ok = _is_repo_ready(ready)
            if ready_ok:
                collector.record_success(f"ready_{repo_id}")
            else:
                overall_status_ref["value"] = "failed"
                ready_reason = failure_reason_from_body(ready.response_body, f"expected 200, got {ready.status_code}")
                collector.record_failure(f"ready_{repo_id}", ready_reason)
            record_case_result(case_results, prefix="prefilter", case_id=f"ready-{repo_id}", expected_status=200, actual_status=ready.status_code, passed=ready_ok, failure_reason=None if ready_ok else ready_reason)
        # repo1：用批次前后的真实时间窗口，避免使用 HTTP 响应时间导致首条实体被边界过滤。
        windows[repo_ids[0]]["t1_start"] = _now_ms() - REPO_WINDOW_MARGIN_MS
        for idx in range(1, 11):
            entity_id = f"entity-1-{idx}"
            location_id = "1" if idx <= 5 else "0"
            record, ok = await _create_entity(entity_api, store, repo_id=repo_ids[0], entity_id=entity_id, feature_value=ENTITY1_FEATURE, location_id=location_id, case_id=f"entity1-{idx}", collector=collector, overall_status_ref=overall_status_ref)

            entity1_ids.append(entity_id)
            record_case_result(case_results, prefix="prefilter", case_id=f"entity1-{idx}", expected_status=201, actual_status=record.status_code, passed=ok, failure_reason=None if ok else failure_reason_from_body(record.response_body, f"expected 201, got {record.status_code}"))

        await asyncio.sleep(REPO_BATCH_GAP_SECONDS)
        windows[repo_ids[0]]["t1_end"] = _now_ms()
        await asyncio.sleep(REPO_BATCH_GAP_SECONDS)
        windows[repo_ids[0]]["t2_start"] = _now_ms()
        for idx in range(11, 21):
            entity_id = f"entity-2-{idx}"
            location_id = "1" if idx <= 15 else "0"
            record, ok = await _create_entity(entity_api, store, repo_id=repo_ids[0], entity_id=entity_id, feature_value=ENTITY2_FEATURE, location_id=location_id, case_id=f"entity2-{idx}", collector=collector, overall_status_ref=overall_status_ref)
            entity2_ids.append(entity_id)
            record_case_result(case_results, prefix="prefilter", case_id=f"entity2-{idx}", expected_status=201, actual_status=record.status_code, passed=ok, failure_reason=None if ok else failure_reason_from_body(record.response_body, f"expected 201, got {record.status_code}"))

        await asyncio.sleep(REPO_BATCH_GAP_SECONDS)
        windows[repo_ids[0]]["t2_end"] = _now_ms() + REPO_WINDOW_MARGIN_MS

        # repo2
        for idx in range(1, 11):
            entity_id = f"entity-1-{idx}"
            location_id = "1" if idx <= 5 else "0"
            record, ok = await _create_entity(entity_api, store, repo_id=repo_ids[1], entity_id=entity_id, feature_value=ENTITY1_FEATURE, location_id=location_id, case_id=f"entity1-{idx}", collector=collector, overall_status_ref=overall_status_ref)

            entity1_ids.append(entity_id)
            record_case_result(case_results, prefix="prefilter", case_id=f"entity1-{idx}", expected_status=201, actual_status=record.status_code, passed=ok, failure_reason=None if ok else failure_reason_from_body(record.response_body, f"expected 201, got {record.status_code}"))

        for idx in range(11, 21):
            entity_id = f"entity-2-{idx}"
            location_id = "1" if idx <= 15 else "0"
            record, ok = await _create_entity(entity_api, store, repo_id=repo_ids[1], entity_id=entity_id, feature_value=ENTITY2_FEATURE, location_id=location_id, case_id=f"entity2-{idx}", collector=collector, overall_status_ref=overall_status_ref)
            entity2_ids.append(entity_id)
            record_case_result(case_results, prefix="prefilter", case_id=f"entity2-{idx}", expected_status=201, actual_status=record.status_code, passed=ok, failure_reason=None if ok else failure_reason_from_body(record.response_body, f"expected 201, got {record.status_code}"))

        for idx in range(1, 4):
            record, ok = await _create_entity(entity_api, store, repo_id=repo_ids[1], entity_id=f"entity-3-{idx}", feature_value=ENTITY3_FEATURE, location_id="0", case_id=f"entity3-{idx}", collector=collector, overall_status_ref=overall_status_ref)
            entity3_ids.append(f"entity-3-{idx}")
            record_case_result(case_results, prefix="prefilter", case_id=f"entity3-{idx}", expected_status=201, actual_status=record.status_code, passed=ok, failure_reason=None if ok else failure_reason_from_body(record.response_body, f"expected 201, got {record.status_code}"))
   
        # 可见性预热：两个仓库都先轮询到"无过滤搜索有结果"，避免把索引延迟误判成前过滤生效。
        visibility_warmup_detail: dict[str, str] = {}
        for repo_id in repo_ids:
            visibility_warmup_ok, detail = await _wait_search_visible(
                search_api, store, repo_id=repo_id, timeout_s=60.0
            )
            visibility_warmup_detail[repo_id] = detail
            print(f"[prefilter] visibility-warmup repo={repo_id} ok={visibility_warmup_ok} {detail}")

        windows_repo1 = windows[repo_ids[0]]
        search_cases = [
            (
                "search-location-time",
                "前过滤=位置+时间：repo1 限定 locations=[1] 且只取第一批时间窗（t1_start~t1_end），应精确返回 entity-1-1~5；"
                "多出 entity-2-* 说明时间过滤未生效，多出 location_id=0 的实体说明位置过滤未生效",
                _build_search_payload(
                    repo_id=repo_ids[0],
                    locations=["1"],
                    start_time=windows_repo1["t1_start"],
                    end_time=windows_repo1["t1_end"],
                ),
                {f"entity-1-{idx}" for idx in range(1, 6)},
            ),
            (
                "search-location-only",
                "前过滤=仅位置：repo2 限定 locations=[1]，最相似（1.0）但 location_id=0 的 entity-3-* 必须被位置过滤掉，"
                "应精确返回 entity-2-11~15（0.92）",
                _build_search_payload(repo_id=repo_ids[1], locations=["1"]),
                {f"entity-2-{idx}" for idx in range(11, 16)},
            ),
            (
                "search-time-only",
                "前过滤=仅时间：repo1 只取第二批时间窗（t2_start~t2_end），第一批 entity-1-* 必须被时间过滤掉，"
                "应精确返回 entity-2-11~20 共 10 条（max_candidates 提到 10）",
                _build_search_payload(
                    repo_id=repo_ids[0],
                    start_time=windows_repo1["t2_start"],
                    end_time=windows_repo1["t2_end"],
                    max_candidates=10,
                ),
                {f"entity-2-{idx}" for idx in range(11, 21)},
            ),
        ]
        for case_id, expectation_note, payload, expected_ids in search_cases:
            searched = await search_api.query(payload, case_id=case_id, module="search", action="query", name=case_id, path="/repositories/search")
            store.save(searched)
            results = extract_search_results(searched.response_body)
            actual_ids = sorted({str(item.get("id")) for item in results if item.get("id") is not None})
            similarities = extract_result_similarities(results)
            expected_id_list = sorted(expected_ids)
            missing_ids = sorted(expected_ids - set(actual_ids))
            unexpected_ids = sorted(set(actual_ids) - expected_ids)
            case_extra = {
                "expected_result": f"200 | 期望条数={len(expected_ids)} | ids={expected_id_list} | similarity 非递增",
                "expected_detail": expectation_note,
                "actual_outcome": f"{searched.status_code} | 实际条数={len(actual_ids)} | ids={actual_ids} | similarity={similarities}",
                "expected_ids": expected_id_list,
                "actual_ids": actual_ids,
                "actual_similarities": similarities,
            }
            search_reason: str | None = None
            passed = searched.status_code == 200 and bool(results) and _assert_expected_ids(results, expected_ids)
            if passed and not is_nonincreasing(similarities):
                passed = False
                search_reason = f"similarity 非递增断言失败：{similarities}"
            if passed:
                collector.record_success(case_id)
            else:
                overall_status_ref["value"] = "failed"
                if searched.status_code != 200:
                    search_reason = failure_reason_from_body(searched.response_body, f"expected 200 with results, got {searched.status_code}")
                elif not results:
                    search_reason = "expected 200 with results, got 200 with empty results（前过滤或索引可见性异常）"
                elif search_reason is None:
                    search_reason = f"前过滤结果不符合预期：缺失={missing_ids}，多出={unexpected_ids}（多出的 id 说明位置或时间过滤未生效）"
                collector.record_failure(case_id, search_reason)
            record_case_result(
                case_results,
                prefix="prefilter",
                case_id=case_id,
                expected_status=200,
                actual_status=searched.status_code,
                passed=passed,
                failure_reason=search_reason,
                extra=case_extra,
            )

    except Exception as exc:
        overall_status_ref["value"] = "failed"
        collector.record_failure("prefilter", str(exc))
        record_case_result(case_results, prefix="prefilter", case_id="scenario-error", expected_status="no exception", actual_status=None, passed=False, failure_reason=str(exc))
    finally:
        for repo_id in reversed(repo_ids):
            try:
                cleanup = await repo_api.delete(None, case_id=f"cleanup-{repo_id}", module="repo", action="delete", name=f"cleanup {repo_id}", path=f"/repositories/{repo_id}")
                store.save(cleanup)
                cleanup_ok = cleanup.status_code in {200, 202, 204, 404}
                if cleanup_ok:
                    collector.record_success(f"cleanup_{repo_id}")
                    if cleanup.status_code != 404:
                        await _ensure_repo_deleted(repo_api, store, repo_id=repo_id, timeout_s=60.0)
                else:
                    overall_status_ref["value"] = "failed"
                    cleanup_reason = failure_reason_from_body(cleanup.response_body, f"expected 200/202/204/404, got {cleanup.status_code}")
                    collector.record_failure(f"cleanup_{repo_id}", cleanup_reason)
                record_case_result(case_results, prefix="prefilter", case_id=f"cleanup-{repo_id}", expected_status="200/202/204/404", actual_status=cleanup.status_code, passed=cleanup_ok, failure_reason=None if cleanup_ok else cleanup_reason)
            except Exception as exc:
                overall_status_ref["value"] = "failed"
                collector.record_failure(f"cleanup_{repo_id}", str(exc))
                record_case_result(case_results, prefix="prefilter", case_id=f"cleanup-error-{repo_id}", expected_status="cleanup ok", actual_status=None, passed=False, failure_reason=str(exc))

        summary = finalize_repo_summary(
            collector,
            summary_path,
            overall_status=overall_status_ref["value"],
            extra={
                "repo_ids": repo_ids,
                "entity1_ids": entity1_ids,
                "entity2_ids": entity2_ids,
                "entity3_ids": entity3_ids,
                "time_windows": windows,
                "visibility_warmup": visibility_warmup_detail,
                "case_total": len(case_results),
                "case_results": case_results,
            },
        )

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
