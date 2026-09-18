#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""功能测试结束后基于输出 JSON 的独立复核判定命令（阶段 1）。

用法：
    python verify_functional.py            # 判定全部 8 个功能接口
    python verify_functional.py --iface repo.create --iface detect.run
    python verify_functional.py --write-rules   # 生成默认 body_checks.json（方案甲）

设计依据：docs/功能测试JSON成功判定设计.md（v0.5 冻结规则）。

判定管线（逐用例）：
    L1 状态码  ：actual.status_code == expected.status_code（detect 除外，detect 以响应体为准）
    L2 响应体  ：成功用例 no_error + must_have + (echo / detect 内部成功标志)
                 失败用例 error_required（detect 失败用例要求 error_code == '400'，严格）
    verdict    ：PASS / FAIL / MISSING，并与 pytest summary 对账标记 MISMATCH

本脚本自包含（仅标准库），不依赖 API_TEST 包内导入。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent

# 8 个功能测试接口（update 本期排除）
INTERFACES = {
    "repo": ["create", "get", "list", "delete"],
    "entity": ["create", "get", "delete"],
    "search": ["query"],
    "detect": ["run"],
}

SUMMARY_NAME = "source_legacy_cases.json"

# 成功(合法)响应的关键业务键（v0.5 冻结）
SUCCESS_KEYS = {
    ("repo", "create"): ["id", "status", "type", "index_type", "level",
                         "capacity", "size", "replications", "options"],
    ("repo", "get"):    ["id", "status", "type", "index_type", "level",
                         "capacity", "size", "replications", "options"],
    ("repo", "list"):   ["repos", "total_count"],
    ("repo", "delete"): ["id", "status", "type", "index_type", "level",
                         "capacity", "size", "replications", "options"],
    ("entity", "create"): ["id"],
    ("entity", "get"):    ["id", "data", "location_id", "time"],
    ("entity", "delete"): ["id", "data", "location_id", "time"],
    ("search", "query"):  ["message", "results"],
    ("detect", "run"):    ["Context", "Result"],
}

# payload 回显字段（成功时 body[field] 应等于 payload[field]）
ECHO_FIELDS = {
    ("repo", "create"): ["id", "type", "index_type", "level"],
    ("repo", "get"):    ["id"],
    ("repo", "delete"): ["id"],
    ("entity", "create"): ["id"],
    ("entity", "get"):    ["id"],
    ("entity", "delete"): ["id"],
    ("search", "query"):  [],
    ("detect", "run"):    [],
}

DEFAULT_BODY_CHECKS = {
    "success": {
        "no_error": True,
        "must_have": [],
        "echo": [],
        "detect_success": False,
    },
    "failure": {
        "error_required": True,
        "error_code": None,   # None=不限；detect 填 "400"
    },
}


def parse_iso(ts):
    """解析 ISO 时间戳为 epoch 秒；失败返回 None。"""
    if not ts:
        return None
    s = str(ts).strip()
    try:
        s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        try:
            return datetime.strptime(s, "%Y%m%d_%H%M%S_%f").timestamp()
        except Exception:
            return None


def norm_case_id(s):
    return str(s or "").strip()


def is_aux_record(case_id: str) -> bool:
    """判断是否辅助（轮询/清理/seed）记录，不参与用例主判定。"""
    cid = norm_case_id(case_id)
    if cid.endswith("-cleanup"):
        return True
    if re.match(r"^(repo-list-|entity-status-|repo-create-|repo-delete-)", cid):
        return True
    return False


def _is_motor_key(k) -> bool:
    """判断键是否属于“机动车(motor)”输出字段（排除 nonmotor/non_motor）。"""
    kl = str(k or "").lower()
    if "motor" not in kl:
        return False
    if "nonmotor" in kl or "non_motor" in kl or kl.startswith("non-"):
        return False
    return True


def _is_vehicle_key(k) -> bool:
    """判断键是否属于“车辆(vehicle)”输出字段（排除 nonvehicle/nonmotor）。"""
    kl = str(k or "").lower()
    if "vehicle" not in kl:
        return False
    if "nonvehicle" in kl or "nonmotor" in kl or kl.startswith("non-"):
        return False
    return True


def load_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def load_case_defs(module, action):
    p = ROOT / "data" / module / "function" / action / SUMMARY_NAME
    j = load_json(p)
    if not isinstance(j, list):
        return []
    return [c for c in j if isinstance(c, dict) and "__summary__" not in c]


def find_summary(module, action):
    """定位 pytest 汇总 JSON（function_test/<module>/results/test_<action>_summary.json）。"""
    p = ROOT / "function_test" / module / "results" / f"test_{module}_{action}_summary.json"
    j = load_json(p)
    if not isinstance(j, dict):
        return None, None
    return j, p


def collect_response_records(module, action):
    """收集归档中所有响应记录（扁平 + <module>/<action>/ 子目录 + archives）。"""
    root = ROOT / "function_test" / module / "results" / "responses"
    if not root.exists():
        return []
    recs = []
    for fp in root.rglob("response_*.json"):
        j = load_json(fp)
        items = j.get("responses") if isinstance(j, dict) else None
        if not isinstance(items, list):
            continue
        for r in items:
            if not isinstance(r, dict):
                continue
            if r.get("module") != module or r.get("action") != action:
                continue
            recs.append((fp, r))
    return recs


def response_batch_ts(fp: Path):
    """由响应归档文件名解析批次时间（response_YYYYmmdd_HHMMSS_*.json）。"""
    m = re.search(r"response_(\d{8}_\d{6})_\d+\.json$", fp.name)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d_%H%M%S").timestamp()
        except Exception:
            pass
    try:
        return fp.stat().st_mtime
    except Exception:
        return 0.0


def pick_run_batch(records, summary_ts):
    """按“summary.generated_at 就近”选择本次运行的归档批次。

    归档按文件分批（一次 pytest 运行、每个 module/action 一个 response_*.json），
    选取批次时间与 summary_ts 最接近的文件（时间差 < 3600s）作为本次运行窗口；
    无 summary 时退化为所有文件。
    """
    if summary_ts is None:
        return records
    by_file = {}
    for fp, r in records:
        by_file.setdefault(str(fp), (fp, []))[1].append(r)
    best_files = []
    best_diff = None
    for fp, recs in by_file.values():
        diff = abs(response_batch_ts(Path(fp)) - summary_ts)
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_files = [(fp, recs)]
        elif abs(diff - best_diff) < 3600.0:
            best_files.append((fp, recs))
    out = []
    for fp, recs in best_files:
        for r in recs:
            out.append((Path(fp), r))
    return out


def pick_latest_before(records, summary_ts):
    """在选定的本次运行批次内，为每个 case_id 选最近主记录。

    records: list[(path, record)]（已按批次过滤）
    """
    best = {}
    for fp, r in records:
        cid = norm_case_id(r.get("case_id"))
        if not cid or is_aux_record(cid):
            continue
        ts = parse_iso(r.get("timestamp"))
        if ts is None:
            # 无时间戳则用文件 mtime 近似
            try:
                ts = Path(fp).stat().st_mtime
            except Exception:
                ts = 0.0
        prev = best.get(cid)
        if prev is None or ts > prev[0]:
            best[cid] = (ts, fp, r)
    return {cid: (fp, rec) for cid, (_, fp, rec) in best.items()}


def _detect_path_values(body, path):
    """按 Result.NonMotorVehicles[].HasFace 这类路径取值（[] 表示逐元素展开）。"""
    current = [body]
    for raw_part in str(path).split("."):
        part = raw_part.strip()
        if not part:
            continue
        wildcard = part.endswith("[]")
        key = part[:-2] if wildcard else part
        nxt = []
        for node in current:
            if isinstance(node, dict):
                if key not in node:
                    continue
                value = node.get(key)
            elif isinstance(node, list):
                for item in node:
                    if isinstance(item, dict) and key in item:
                        value = item.get(key)
                        if wildcard and isinstance(value, list):
                            nxt.extend(value)
                        else:
                            nxt.append(value)
                continue
            else:
                continue
            if wildcard and isinstance(value, list):
                nxt.extend(value)
            else:
                nxt.append(value)
        current = nxt
        if not current:
            return []
    return current


def _detect_value_present(value):
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _eval_detect_rules(rule_source, res):
    """求值 detect_any_of / detect_all_empty；返回 (是否声明规则, 是否通过, 明细)。"""
    any_rules = rule_source.get("detect_any_of") or []
    empty_paths = rule_source.get("detect_all_empty") or []
    if not any_rules and not empty_paths:
        return False, True, ""
    details = []
    for path in empty_paths:
        values = _detect_path_values(res, path)
        hit = [v for v in values if _detect_value_present(v)]
        if hit:
            details.append(f"{path} 应为空，实际有 {len(hit)} 个值（示例 {str(hit[0])[:40]}）")
    if any_rules:
        matched = False
        traces = []
        for rule in any_rules:
            if not isinstance(rule, dict):
                continue
            path = str(rule.get("path") or "")
            values = _detect_path_values(res, path)
            if "equals" in rule:
                ok = any(v == rule.get("equals") for v in values)
            else:
                ok = any(_detect_value_present(v) for v in values)
            traces.append(f"{path}={'命中' if ok else '未命中'}")
            matched = matched or ok
        if not matched:
            details.append("以下任一条件应成立但全部未命中：" + "，".join(traces))
    return True, (not details), "；".join(details)


def body_matches(body_checks, record, case):
    """执行 L2 响应体校验，返回 (passed, detail)。"""
    body = record.get("response_body")
    payload = record.get("payload")
    exp = case.get("expected") or {}
    exp_status = exp.get("status_code")
    expect_success = isinstance(exp_status, int) and 200 <= exp_status < 300

    # 解析用例级覆盖（body_checks.json 的 cases.<case_id>）
    case_ov = {}
    all_cases = body_checks.get("cases") if isinstance(body_checks, dict) else None
    if isinstance(all_cases, dict):
        ov = all_cases.get(str(case.get("case_id")))
        if isinstance(ov, dict):
            case_ov = ov
    base = body_checks.get("success" if expect_success else "failure") or {}
    checks = dict(base)
    checks.update(case_ov.get("success" if expect_success else "failure") or {})
    details = []

    if not isinstance(body, dict):
        if isinstance(body, str) and body:
            return False, "响应体不是 JSON 对象: " + body[:120]
        return False, "响应体为空或非 JSON 对象"

    if expect_success:
        # detect 特殊：HTTP 恒 200，以响应体为准
        if checks.get("detect_success"):
            err = body.get("error")
            if err:
                return False, f"业务失败：error={str(err)[:200]}"
            res = body.get("Result")
            if not isinstance(res, dict):
                return False, "缺少 Result 对象"
            if str(res.get("InnerStatus")) != "200":
                details.append(f"Result.InnerStatus={res.get('InnerStatus')} != 200")
            if str(res.get("InnerMessage")) != "success":
                details.append(f"Result.InnerMessage={res.get('InnerMessage')!r} != success")
            # 声明式字段规则（来自用例 expected，其次 body_checks 覆盖）优先于旧的 result_field
            rule_source = {}
            if isinstance(exp, dict):
                for key in ("detect_any_of", "detect_all_empty"):
                    if exp.get(key):
                        rule_source[key] = exp[key]
            for key in ("detect_any_of", "detect_all_empty"):
                if key not in rule_source and checks.get(key):
                    rule_source[key] = checks[key]
            # 规则路径是 Result.xxx 的绝对路径，必须对完整响应体求值
            has_declared, declared_ok, declared_detail = _eval_detect_rules(rule_source, body)
            if has_declared and not declared_ok:
                details.append("字段级校验未通过：" + declared_detail)
            rf = None if has_declared else checks.get("result_field")
            if rf:
                arr = res.get(rf)
                if not isinstance(arr, list) or len(arr) == 0:
                    details.append(f"Result.{rf} 应为非空数组（未检测到目标），实际为空或缺失")
            if checks.get('motor_required'):
                found = [k for k in res if _is_motor_key(k)
                         and isinstance(res[k], list) and len(res[k]) > 0]
                if not found:
                    details.append("Result 中未检出非空 motor 字段（motor 场景应检出机动车）")
            if checks.get('vehicle_required'):
                found = [k for k in res if _is_vehicle_key(k)
                         and isinstance(res[k], list) and len(res[k]) > 0]
                if not found:
                    details.append("Result 中未检出非空 vehicle 字段（vehicle 场景应检出车辆）")
            if details:
                return False, "；".join(details)
            return True, None
        # no_error
        if checks.get("no_error") and body.get("error") is not None:
            return False, f"成功响应不应携带 error={str(body.get('error'))[:200]}"
        # must_have
        for k in checks.get("must_have", []):
            if k not in body:
                details.append(f"缺少字段 {k}")
        # echo
        if isinstance(payload, dict):
            for f in checks.get("echo", []):
                if f in payload and f in body and payload[f] != body[f]:
                    details.append(f"回显不一致 body.{f}={body[f]!r} != payload.{f}={payload[f]!r}")
        if details:
            return False, "；".join(details[:8])
        return True, None
    else:
        # 失败用例
        if checks.get("error_required"):
            err = body.get("error")
            ec = body.get("error_code")
            if err is None or str(err) == "":
                details.append("缺少 error 信息")
            if ec is None or str(ec) == "":
                details.append("缺少 error_code")
            want_ec = checks.get("error_code")
            if want_ec is not None and str(ec) != str(want_ec):
                details.append(f"error_code={ec!r} != 期望 {want_ec!r}")
        if details:
            return False, "；".join(details[:6])
        return True, None


def build_rule(module, action):
    """构造某接口的内置默认规则（后续可被 body_checks.json 覆盖）。"""
    key = (module, action)
    return {
        "success": {
            "no_error": True,
            "must_have": list(SUCCESS_KEYS.get(key, [])),
            "echo": list(ECHO_FIELDS.get(key, [])),
            "detect_success": key == ("detect", "run"),
        },
        "failure": {
            "error_required": True,
            "error_code": "400" if key == ("detect", "run") else None,
        },
    }


def load_override_rules(module, action):
    """方案甲：可选读 data/<module>/function/<action>/body_checks.json 覆盖。"""
    p = ROOT / "data" / module / "function" / action / "body_checks.json"
    j = load_json(p)
    return j if isinstance(j, dict) else None


def verify_interface(module, action, body_checks):
    cases = load_case_defs(module, action)
    summary, summary_path = find_summary(module, action)
    summary_ts = parse_iso(summary.get("generated_at")) if summary else None

    records = collect_response_records(module, action)
    run_batch = pick_run_batch(records, summary_ts)
    picked = pick_latest_before(run_batch, summary_ts)

    # pytest 侧失败索引（用于对账）
    summary_failed = {}
    summary_passed = set()
    if summary:
        for it in summary.get("failed_items") or []:
            if isinstance(it, dict) and it.get("case_id"):
                summary_failed[norm_case_id(it.get("case_id"))] = it.get("detail") or ""
        # passed 集合由总数推导不可靠，改为：非 failed 且出现在本次判定 pass 才算一致

    results = []
    n_pass = n_fail = n_missing = 0
    mismatches = []
    for case in sorted(cases, key=lambda c: norm_case_id(c.get("case_id"))):
        cid = norm_case_id(case.get("case_id"))
        rec = picked.get(cid)
        exp = case.get("expected") or {}
        exp_status = exp.get("status_code")
        item = {
            "case_id": cid,
            "name": case.get("name") or "",
            "parameter": case.get("parameter"),
            "scenario_type": case.get("scenario_type"),
            "expected_status": exp_status,
            "expected": exp,
        }
        if rec is None:
            item.update({"verdict": "MISSING", "passed": None,
                         "actual_status": None, "status_check": None,
                         "body_check": None, "evidence_file": None,
                         "detail": "归档中未找到该用例的响应记录"})
            n_missing += 1
            results.append(item)
            continue
        fp, r = rec
        actual_status = r.get("status_code")
        item["actual_status"] = actual_status
        item["evidence_file"] = str(fp)
        item["elapsed_ms"] = r.get("elapsed_ms")
        item["error_type"] = r.get("error_type")
        item["method"] = r.get("method")
        item["path"] = r.get("path")

        # L1 状态码（detect 除外）
        l1_ok = True
        l1_detail = None
        is_detect = (module == "detect" and action == "run")
        if not is_detect:
            if exp_status is None:
                l1_ok = None
                l1_detail = "用例未定义 expected.status_code"
            elif int(actual_status) != int(exp_status):
                l1_ok = False
                l1_detail = f"状态码 期望 {exp_status} / 实际 {actual_status}"
        item["status_check"] = {"expected": exp_status, "actual": actual_status,
                                "passed": l1_ok, "detail": l1_detail}

        # L2 响应体
        l2_ok, l2_detail = body_matches(body_checks, r, case)
        item["body_check"] = {"passed": l2_ok, "detail": l2_detail}

        # 汇总 verdict
        if exp_status is None:
            verdict = "UNKNOWN"
            passed = None
            detail = "无 expected.status_code，无法判定"
        elif (l1_ok is False) or (l2_ok is False):
            verdict = "FAIL"
            passed = False
            detail = "；".join(x for x in [l1_detail if l1_ok is False else None,
                                          l2_detail if l2_ok is False else None] if x)
        else:
            verdict = "PASS"
            passed = True
            detail = None
        item.update({"verdict": verdict, "passed": passed, "detail": detail})
        if passed is True:
            n_pass += 1
        elif passed is False:
            n_fail += 1

        # 对账：pytest 失败但复核通过 / 复核失败但 pytest 未记录失败
        in_summary_fail = cid in summary_failed
        if passed is False and not in_summary_fail:
            mismatches.append({"case_id": cid, "kind": "复核FAIL但pytest未记失败",
                               "detail": detail})
        elif passed is True and in_summary_fail:
            mismatches.append({"case_id": cid, "kind": "pytest记失败但复核PASS",
                               "detail": str(summary_failed[cid])[:200]})
        results.append(item)

    verdict_payload = {
        "module": module,
        "action": action,
        "generated_at": datetime.now().astimezone().isoformat(),
        "summary_source": str(summary_path) if summary_path else None,
        "summary_generated_at": summary.get("generated_at") if summary else None,
        "summary": {"total": summary.get("total") if summary else None,
                    "passed": summary.get("passed") if summary else None,
                    "failed": summary.get("failed") if summary else None},
        "total": len(results),
        "passed": n_pass,
        "failed": n_fail,
        "missing": n_missing,
        "consistency_mismatches": mismatches,
        "cases": results,
    }
    return verdict_payload


def write_verdict(module, action, payload):
    out = ROOT / "function_test" / module / "results" / "verdict"
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"{action}_verdict.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def write_default_rules():
    for module, actions in INTERFACES.items():
        for action in actions:
            p = ROOT / "data" / module / "function" / action / "body_checks.json"
            p.write_text(json.dumps(build_rule(module, action), ensure_ascii=False, indent=2),
                         encoding="utf-8")
            print("写入规则:", p)


def main():
    ap = argparse.ArgumentParser(description="功能测试 JSON 复核判定")
    ap.add_argument("--iface", action="append", help="指定接口，如 repo.create；可多次；默认全部")
    ap.add_argument("--write-rules", action="store_true", help="生成默认 body_checks.json（方案甲）")
    args = ap.parse_args()

    if args.write_rules:
        write_default_rules()
        return 0

    targets = []
    if args.iface:
        for s in args.iface:
            if "." not in s:
                print(f"接口格式应为 module.action: {s}")
                return 2
            m, a = s.split(".", 1)
            targets.append((m, a))
    else:
        for m, acts in INTERFACES.items():
            for a in acts:
                targets.append((m, a))

    total_pass = total_fail = total_missing = 0
    total_mismatch = 0
    for module, action in targets:
        rules = load_override_rules(module, action) or build_rule(module, action)
        payload = verify_interface(module, action, rules)
        p = write_verdict(module, action, payload)
        total_pass += payload["passed"]
        total_fail += payload["failed"]
        total_missing += payload["missing"]
        total_mismatch += len(payload["consistency_mismatches"])
        print(f"[{module}/{action}] 总{payload['total']} 通过{payload['passed']} "
              f"失败{payload['failed']} 缺失{payload['missing']} "
              f"不一致{len(payload['consistency_mismatches'])} -> {p}")
    print(f"\n汇总: 通过{total_pass} 失败{total_fail} 缺失{total_missing} "
          f"对账不一致{total_mismatch}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
