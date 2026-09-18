#!/usr/bin/env python3
"""API_TEST 统一测试入口：执行功能测试、性能测试并生成 HTML 报告。

不再通过命令行选择接口。运行前直接修改本文件顶部的“运行配置区”：

  RUN_FUNCTIONAL_TESTS / FUNCTIONAL_TEST_SELECTION
  RUN_PERFORMANCE_TESTS / PERFORMANCE_TEST_SELECTION
  COLLECT_ONLY

最终 HTML 固定输出到：
  outputs/report.html
"""
import ast
import json
import os
import queue
import subprocess
import sys
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
import re

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except Exception:
    Environment = None


ROOT = Path(__file__).resolve().parent

try:
    from API_TEST.function_test.detect.detect_checks import evaluate_detect_expectations
except Exception:  # 直接以脚本方式运行时补充包路径
    if str(ROOT.parent) not in sys.path:
        sys.path.insert(0, str(ROOT.parent))
    from API_TEST.function_test.detect.detect_checks import evaluate_detect_expectations


# 功能测试接口 -> 测试文件（相对 ROOT 的路径）
FUNCTIONAL_TEST_FILES = {
    'repo_create': 'function_test/repo/test_repo_create.py',
    'repo_get': 'function_test/repo/test_repo_get.py',
    'repo_list': 'function_test/repo/test_repo_list.py',
    'repo_delete': 'function_test/repo/test_repo_delete.py',
    'entity_create': 'function_test/entity/test_entity_create.py',
    'entity_get': 'function_test/entity/test_entity_get.py',
    'entity_delete': 'function_test/entity/test_entity_delete.py',
    'search_query': 'function_test/search/test_search_query.py',
    'detect_run': 'function_test/detect/test_detect_run.py',
}


# 性能测试接口 -> 入口脚本（相对 ROOT 的路径）
PERFORMANCE_TEST_FILES = {
    'search': 'performance/test_design/search/search.py',
    'entity_insert': 'performance/test_design/entity/insert/entity_insert.py',
    'entity_get': 'performance/test_design/entity/get/entity_get.py',
    'entity_delete': 'performance/test_design/entity_delete/entity_delete.py',
    'detect': 'performance/test_design/detect/detect.py',
}

# ============================================================================
# 运行配置区
# ============================================================================
# 只收集 HTML，不执行测试：
#   True  = 读取已有报告并生成最终 HTML
#   False = 先执行下面选择的功能/性能测试，再生成 HTML
COLLECT_ONLY = os.environ.get("API_TEST_COLLECT_ONLY", "0").lower() in {"1", "true", "yes"}

# 全量测试时保持两项为 True；只测试某一类时按需关闭。
RUN_FUNCTIONAL_TESTS = True
RUN_PERFORMANCE_TESTS = True

# 功能测试单选开关：RUN_FUNCTIONAL_TESTS=True 时，只执行值为 True 的接口。
FUNCTIONAL_TEST_SELECTION = {
    'repo_create': True,
    'repo_get': True,
    'repo_list': True,
    'repo_delete': True,
    'entity_create': True,
    'entity_get': True,
    'entity_delete': True,
    'search_query': True,
    'detect_run': True,
}

# 性能测试单选开关：RUN_PERFORMANCE_TESTS=True 时，只执行值为 True 的接口。
PERFORMANCE_TEST_SELECTION = {
    'search': True,
    'entity_insert': True,
    'entity_get': True,
    'entity_delete': True,
    'detect': True,
}

# 最终 HTML 保存路径；默认报告保持原路径，全量测试可通过环境变量指定新文件。
REPORT_OUTPUT_PATH = Path(
    os.environ.get("API_TEST_REPORT_OUTPUT", str(ROOT / "outputs" / "report.html"))
).expanduser()
LOG_INTERVAL_SECONDS = int(os.environ.get("API_TEST_LOG_INTERVAL_SECONDS", "600"))


# 运行功能测试（pytest）
# 参数：python_exe - 要使用的 Python 解释器路径字符串；test_files - 只运行这些接口测试
def run_pytest(python_exe, test_files=None):
    print("Running selected functional tests via pytest...")
    cmd = [python_exe, "-m", "pytest", "-q"]
    if test_files:
        cmd.extend(str(ROOT / f) for f in test_files)
    else:
        cmd.append(str(ROOT / 'function_test'))
    rc = subprocess.call(cmd)
    print(f"pytest exit code: {rc}")
    return rc


# 搜索性能测试脚本（包含 if __name__ == '__main__' 的脚本）
def discover_performance_scripts():
    perf_dir = ROOT / "performance" / "test_design"
    scripts = []
    if not perf_dir.exists():
        return scripts
    for p in perf_dir.rglob("*.py"):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if 'if __name__' in text:
            scripts.append(p)
    return scripts


# 运行性能测试脚本（会把 k6 所在目录加入 PATH）
def _run_command_with_heartbeat(
    cmd: list[str],
    *,
    label: str,
    log_path: Path,
    env: dict[str, str],
    interval_seconds: int,
) -> int:
    """运行单个性能脚本，持续写日志，并定期输出心跳。"""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    interval_seconds = max(1, int(interval_seconds))
    print(f"[PERF_START] {label} log={log_path}", flush=True)

    with log_path.open("w", encoding="utf-8", buffering=1) as log_file:
        process = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        output_queue: queue.Queue[str | None] = queue.Queue()

        def read_output() -> None:
            try:
                if process.stdout is not None:
                    for line in process.stdout:
                        output_queue.put(line)
            finally:
                output_queue.put(None)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()

        started = time.monotonic()
        next_heartbeat = started + interval_seconds
        noteworthy_markers = (
            "[INFO] DETECT_CASE",
            "[INFO] K6_START",
            "[INFO] CONCURRENCY_RESULT",
            "[RUN]",
            "Report written",
            "Traceback",
            "ERROR",
            "FAILED",
        )
        while True:
            try:
                line = output_queue.get(timeout=1.0)
            except queue.Empty:
                line = ""

            if line is None:
                break
            if line:
                log_file.write(line)
                log_file.flush()
                if any(marker in line for marker in noteworthy_markers):
                    print(line, end="", flush=True)

            now = time.monotonic()
            if now >= next_heartbeat:
                elapsed = int(now - started)
                heartbeat = (
                    f"[PERF_HEARTBEAT] label={label} elapsed={elapsed}s "
                    f"status=running pid={process.pid}\n"
                )
                print(heartbeat, end="", flush=True)
                log_file.write(heartbeat)
                log_file.flush()
                while next_heartbeat <= now:
                    next_heartbeat += interval_seconds

        process.wait()
        elapsed = int(time.monotonic() - started)
        completion = (
            f"[PERF_DONE] label={label} elapsed={elapsed}s exit_code={process.returncode}\n"
        )
        print(completion, end="", flush=True)
        log_file.write(completion)
        log_file.flush()
        return int(process.returncode)


def run_performance_scripts(
    python_exe,
    k6_path,
    test_files=None,
    *,
    log_interval_seconds: int = 600,
    perf_output_root: Path | None = None,
):
    print("Running selected performance scripts...")
    scripts = discover_performance_scripts()
    if test_files is not None:
        selected_paths = {str(ROOT / f) for f in test_files}
        scripts = [s for s in scripts if str(s) in selected_paths]
    results = []
    env = os.environ.copy()
    # prepend k6 dir to PATH so scripts can call `k6`
    if k6_path:
        k6_dir = str(Path(k6_path).parent)
        env["PATH"] = k6_dir + os.pathsep + env.get("PATH", "")
    if perf_output_root is not None:
        env["API_TEST_PERF_OUTPUT"] = str(perf_output_root)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logs_dir = (perf_output_root / "logs") if perf_output_root else (ROOT / "performance" / "outputs" / "logs")

    for s in scripts:
        label = str(s.relative_to(ROOT))
        print(f"-> running {label}")
        cmd = [python_exe, str(s)]
        log_path = logs_dir / f"{s.stem}_{timestamp}.log"
        try:
            rc = _run_command_with_heartbeat(
                cmd,
                label=label,
                log_path=log_path,
                env=env,
                interval_seconds=log_interval_seconds,
            )
            results.append((str(s), rc))
        except Exception as e:
            results.append((str(s), f"error: {e}"))
    if not scripts:
        print("No performance scripts matched the selected interfaces.")
    return results


# 收集仓库中现有的输出文件（JSON/MD/PNG）
def collect_outputs(search_roots=None):
    if search_roots is None:
        # include performance outputs dir so migrated perf reports are discovered
        search_roots = [
            ROOT,
            ROOT.parent / 'output',
            ROOT.parent / 'outputs',
            ROOT / 'performance' / 'outputs',
        ]
    exts = ('.json', '.md', '.png')
    found = {'.json': [], '.md': [], '.png': []}
    for root in search_roots:
        if not Path(root).exists():
            continue
        for p in Path(root).rglob('*'):
            if p.suffix.lower() in exts:
                found[p.suffix.lower()].append(p)
    return found


# ---------------------------------------------------------------------------
# 报告输出定位：固定更新 outputs/report.html
# ---------------------------------------------------------------------------
_TS_PATTERN = re.compile(r'(\d{8})[-_T ]?(\d{6})')


def resolve_report_output(explicit_path=None, root: Path = ROOT) -> Path:
    """决定报告写入路径：显式指定优先，否则固定为 outputs/report.html。"""
    if explicit_path:
        return Path(explicit_path).expanduser()
    canonical = Path(root) / "outputs" / "report.html"
    print(f"Using canonical report HTML: {canonical}")
    return canonical


def _report_recency_key(item):
    """取报告条目的时间键（YYYYMMDDHHMMSS），用于挑出“最新报告”。"""
    keys = []
    for field in ('md', 'source', 'name', 'display_name'):
        value = item.get(field)
        if not value:
            continue
        for date_part, time_part in _TS_PATTERN.findall(str(value)):
            keys.append(f"{date_part}{time_part}")
    if keys:
        return max(keys)
    try:
        f = Path(str(item.get('md') or item.get('source') or ''))
        if f.exists():
            return datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y%m%d%H%M%S')
    except Exception:
        pass
    return ''


def select_latest_per_interface(perf_summary):
    """每个接口（模块+display_name）只保留时间最新的一份性能报告。"""
    latest = {}
    for module, entry in (perf_summary or {}).items():
        items = list((entry or {}).get('items') or [])
        if not items:
            latest[module] = entry
            continue
        best = {}
        for it in items:
            key = it.get('display_name') or it.get('name') or it.get('source') or module
            prev = best.get(key)
            if prev is None or _report_recency_key(it) >= _report_recency_key(prev):
                best[key] = it
        new_entry = dict(entry)
        new_entry['items'] = list(best.values())
        latest[module] = new_entry
    return latest


# 从 data 目录读取用例定义，构建接口->字段->用例 的树形结构
def build_functional_index():
    cases = []
    data_dir = ROOT / 'data'
    if not data_dir.exists():
        return {}
    for p in data_dir.rglob('source_legacy_cases.json'):
        try:
            j = json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            continue
        for c in j:
            cases.append(c)

    index = {}
    for c in cases:
        if not isinstance(c, dict):
            continue
        if not any(c.get(key) for key in ('case_id', 'name', 'module', 'action', 'method')):
            continue
        module = c.get('module') or c.get('action') or 'unknown'
        action = c.get('action') or c.get('method') or 'call'
        iface = f"{module}.{action}"
        param = c.get('parameter') or '全体'
        rec = {
            'case_id': c.get('case_id'),
            'name': c.get('name'),
            'scenario_type': c.get('scenario_type'),
            'expected': c.get('expected'),
            'path': c.get('path'),
            'design_only': action == 'update',
        }
        if iface not in index:
            # 展示名：search.query 在报告里简写为 search（去掉动作后缀 .query）
            display_name = 'search' if module == 'search' and action == 'query' else iface
            index[iface] = {
                'cases': [],
                'by_param': {},
                'display_name': display_name,
                'design_only': action == 'update',
            }
        index[iface]['cases'].append(rec)
        index[iface]['by_param'].setdefault(param, []).append(rec)

    list_info = index.get('repo.list')
    if list_info:
        list_info['by_param'] = {'all': list(list_info['cases'])}
        list_info['direct_cases'] = True

    # enrich counts
    for k, v in index.items():
        v['total'] = len(v['cases'])
        # passed count unknown unless results exist; set to None
        v['passed'] = None
    return index


FUNCTION_MODULE_ORDER = ('detect', 'search', 'repo', 'entity')


def group_functional_modules(func_index):
    """把 module.action 索引按 detect/search/repo/entity 模块分组。"""
    grouped = {}
    other = {}
    for name, info in (func_index or {}).items():
        module = str(name).split('.', 1)[0]
        target = grouped if module in FUNCTION_MODULE_ORDER else other
        target.setdefault(module, {})[name] = info
    ordered = {module: grouped[module] for module in FUNCTION_MODULE_ORDER if module in grouped}
    ordered.update(other)
    return ordered


def order_functional_index(func_index):
    """按模块顺序重排平铺索引，并给每条接口补上 module_name。"""
    ordered = {}
    for module_data in group_functional_modules(func_index).values():
        for name, info in module_data.items():
            info['module_name'] = str(name).split('.', 1)[0]
            ordered[name] = info
    return ordered


def load_verdicts():
    """加载外部复核结果 {module.action: verdict_json}。"""
    verdicts = {}
    verdict_dir = ROOT / 'function_test'
    if not verdict_dir.exists():
        return verdicts
    for p in verdict_dir.glob('*/results/verdict/*_verdict.json'):
        try:
            j = json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(j, dict):
            continue
        key = f"{j.get('module')}.{j.get('action')}"
        if j.get('module') and j.get('action'):
            verdicts[key] = j
    return verdicts


def apply_verdicts(func_index, verdicts):
    """以外部复核结果覆盖报告判定（verdict 为准，MISMATCH 高亮）。"""
    for name, info in func_index.items():
        verdict = verdicts.get(name)
        if not verdict:
            continue
        vcases = {str(c.get('case_id')): c for c in verdict.get('cases', []) if isinstance(c, dict)}
        mismatched = {str(m.get('case_id')) for m in verdict.get('consistency_mismatches', [])}
        passed_cnt = 0
        for c in info.get('cases', []):
            cid = str(c.get('case_id') or '')
            vc = vcases.get(cid)
            if not vc:
                continue
            c['verdict'] = vc.get('verdict')
            c['verdict_detail'] = vc.get('detail')
            c['verdict_actual'] = vc.get('actual_status')
            c['mismatch'] = cid in mismatched
            c['passed'] = vc.get('passed')  # True / False / None(MISSING)
            if str(name).startswith('detect.'):
                # detect：外部 HTTP 恒 200，成败/展示以内部接口码（error_code / Result.InnerStatus）为准
                c['result_display'] = format_detect_result_display(c)
                if c['passed'] is True:
                    passed_cnt += 1
            else:
                # 其它接口：在 ASCII 展示区附加复核依据
                extra = []
                if vc.get('detail'):
                    extra.append(f"复核判定：{vc.get('detail')}")
                if c['passed'] is True:
                    passed_cnt += 1
                    extra.append("复核：通过")
                elif c['passed'] is False:
                    extra.append("复核：失败")
                else:
                    extra.append("复核：未执行(MISSING)")
                c['result_display'] = (c.get('result_display') or '') + '\n' + '\n'.join(extra)
        if info.get('cases'):
            info['passed'] = passed_cnt
    return func_index


def _extract_inner_code(case):
    """从用例实际响应中取 detect 内部码：error_code 优先，其次 Result.InnerStatus。"""
    actual = (case.get('actual_responses') or [None])[0]
    body = {}
    if actual:
        body = (actual.get('body') or {})
    resp = body.get('responses') if isinstance(body, dict) else None
    if isinstance(resp, dict):
        if resp.get('error_code') is not None:
            return resp.get('error_code')
        inner = (resp.get('Result') or {}).get('InnerStatus')
        if inner is not None:
            return inner
    return None


def format_detect_result_display(case):
    """detect 专用测试结果：以内部接口码展示实际结果与复核判定。"""
    passed = case.get('passed')
    if passed is True:
        verdict = '通过'
    elif passed is False:
        verdict = '失败'
    elif passed is None:
        verdict = '未执行'
    else:
        verdict = '未知'
    exp = (case.get('expected') or {}).get('status_code')
    actual = (case.get('actual_responses') or [None])[0]
    http_status = actual.get('status') if actual else None
    inner = _extract_inner_code(case)
    lines = ['# 测试结果', '']
    lines.append(f'- 判定：{verdict}')
    lines.append(f'- 用例 ID：{case.get("case_id")}')
    lines.append(f'- 用例名称：{case.get("name")}')
    if exp is not None:
        lines.append(f'- 预期业务码（内部）：{exp}')
    if inner is not None:
        lines.append(f'- 实际业务码（内部）：{inner}')
    elif http_status is not None:
        lines.append(f'- 实际业务码（内部）：未返回（外部 HTTP：{http_status}）')
    if http_status is not None:
        lines.append(f'- 外部 HTTP 状态：{http_status}')
    detail = case.get('verdict_detail')
    if detail:
        lines.append(f'- 复核详情：{detail}')
    return '\n'.join(lines)


# 读取并解析一组 JSON 文件，返回 (path, json) 列表
# 过大的 JSON（性能测试的 failures.json 单文件可达 GB 级、上千万条失败记录）不参与汇总，
# 否则加载一次就会吃掉几十 GB 内存。可用 API_TEST_MAX_JSON_BYTES 覆盖。
MAX_JSON_BYTES = int(os.environ.get('API_TEST_MAX_JSON_BYTES') or 25 * 1024 * 1024)


def load_json_files(paths):
    data = []
    skipped = []
    for p in paths:
        try:
            f = Path(p)
            if f.stat().st_size > MAX_JSON_BYTES:
                skipped.append(str(p))
                continue
            j = json.loads(f.read_text(encoding='utf-8'))
            data.append((p, j))
        except Exception:
            # skip unparsable
            continue
    if skipped:
        print(f"Skipped {len(skipped)} oversized JSON file(s) "
              f"(> {MAX_JSON_BYTES // (1024 * 1024)} MB); "
              f"set API_TEST_MAX_JSON_BYTES to include them.")
        for s in skipped[:5]:
            print(f"  - {s}")
    return data


# 汇总功能测试的 JSON 项，尝试从常见结构中抽取 summary
def summarize_functional(json_items):
    summary = {}
    for path, j in json_items:
        name = Path(path).stem
        entry = {'source': str(path), 'raw': j}
        if isinstance(j, dict):
            if 'tests' in j:
                entry['tests'] = j['tests']
            if 'summary' in j:
                entry['summary'] = j['summary']
        summary[name] = entry
    return summary


def format_business_expected(item):
    """把 business 单步骤的预期结果格式化为 ASCII 展示文本。"""
    # 优先用脚本写入的 expected_result（可含期望 ID 集合/相似度约束等富信息），否则退回状态码
    expected = item.get('expected_result') or item.get('expected_status') or item.get('expected')
    lines = ['# 预期输出（Business 用例方案）', '']
    lines.append(f'- 预期结果：{expected if expected is not None else "以业务测试方案 PDF 为准"}')
    detail = item.get('expected_detail') or item.get('expected_description')
    if detail:
        lines.append(f'- 说明：{detail}')
    return '\n'.join(lines)


def format_business_result(item):
    """把 business 单步骤的测试结果格式化为 ASCII 展示文本。"""
    passed = item.get('passed')
    if passed is True:
        verdict = '通过'
    elif passed is False:
        verdict = '失败'
    else:
        verdict = '未知'

    expected = item.get('expected_result') or item.get('expected_status') or '无'
    # 优先用脚本写入的 actual_outcome（可含实际 ID 集合/相似度等富信息），否则退回状态码
    actual = item.get('actual_outcome')
    if actual is None:
        actual = item.get('actual_status')
    if actual is None:
        actual = '无记录'

    lines = ['# 测试结果', '']
    lines.append(f'- 判定：{verdict}')
    lines.append(f'- 步骤 ID：{item.get("case_id")}')
    lines.append(f'- 预期结果：{expected}')
    lines.append(f'- 实际结果：{actual}')
    failure = item.get('failure_reason')
    if failure:
        lines.append(f'- 失败原因：{failure}')
    return '\n'.join(lines)


def _biz_match_response(records, case_id, used):
    """在场景响应归档中为步骤匹配接口返回（精确→子串→规范化→顺序回退）。"""
    cid = str(case_id or '')
    cidn = ''.join(ch for ch in cid.lower() if ch.isalnum())
    for i, r in enumerate(records):
        if i in used:
            continue
        if str(r.get('case_id') or '') == cid:
            return i, r, 'exact'
    for i, r in enumerate(records):
        if i in used:
            continue
        rc = str(r.get('case_id') or '')
        if cid and rc and (cid in rc or rc in cid):
            return i, r, 'loose'
    for i, r in enumerate(records):
        if i in used:
            continue
        rcn = ''.join(ch for ch in str(r.get('case_id') or '').lower() if ch.isalnum())
        if cidn and rcn and (cidn in rcn or rcn in cidn):
            return i, r, 'loose'
    for i, r in enumerate(records):
        if i not in used:
            return i, r, 'order'
    return None, None, 'none'


BUSINESS_SOURCE_ALIASES = {
    ('repo', 'delete_repo'): 'create_delete_repo.py',
}


def _normalized_name(value: str) -> str:
    return ''.join(ch.lower() for ch in str(value) if ch.isalnum())


def _expected_status_values(value) -> set[int]:
    if value is None:
        return set()
    if isinstance(value, (int, float)):
        return {int(value)}
    return {int(part) for part in re.findall(r'\d{3}', str(value))}


def business_step_passed(case: dict, response: dict | None) -> bool | None:
    """判定业务步骤响应是否符合预期。"""
    explicit = case.get('passed')
    if isinstance(explicit, bool):
        return explicit

    actual_status = case.get('actual_status')
    if actual_status is None and response:
        actual_status = response.get('status_code')
    expected_values = _expected_status_values(case.get('expected_status'))
    if actual_status is not None and expected_values:
        return int(actual_status) in expected_values
    if response:
        return response.get('error_type') is None and int(response.get('status_code') or 500) < 400
    return None


def resolve_business_source(module: str, scenario: str) -> Path | None:
    """定位业务场景对应的源码文件。"""
    business_dir = ROOT / 'business' / str(module)
    if not business_dir.is_dir():
        return None

    aliased = BUSINESS_SOURCE_ALIASES.get((str(module), str(scenario)))
    if aliased:
        candidate = business_dir / aliased
        if candidate.is_file():
            return candidate

    target = _normalized_name(scenario).rstrip('_')
    candidates = [
        p for p in business_dir.glob('*.py')
        if not p.name.startswith('_') and p.name != '__init__.py'
    ]
    for candidate in candidates:
        if _normalized_name(candidate.stem).rstrip('_') == target:
            return candidate
    return None


def extract_business_logic(module: str, scenario: str) -> tuple[str, str | None]:
    """从场景源码中提取模块说明与文件头流程注释。"""
    source = resolve_business_source(module, scenario)
    if source is None:
        return '', None

    try:
        text = source.read_text(encoding='utf-8')
        tree = ast.parse(text)
    except Exception:
        return '', str(source)

    parts = []
    docstring = ast.get_docstring(tree, clean=True)
    if docstring:
        parts.append(docstring.strip())

    lines = text.splitlines()
    flow_start = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('#'):
            content = stripped.lstrip('#').strip()
            if '流程' in content:
                flow_start = index
                break

    flow_lines = []
    if flow_start is not None:
        for line in lines[flow_start:]:
            stripped = line.strip()
            if stripped.startswith('#'):
                content = stripped.lstrip('#').strip()
                if content and not content.startswith('-*-'):
                    flow_lines.append(content)
            elif flow_lines and stripped:
                break

    if flow_lines:
        flow_text = '\n'.join(flow_lines)
        if flow_text not in parts:
            parts.append(flow_text)

    return '\n\n'.join(parts).strip(), str(source)


def summarize_business(json_items):
    """从 business/ 下已有的 summary JSON 中挑选每个场景的最新一次结果（含各步骤接口返回）。"""
    # 索引 business 响应归档：{(module, scenario): [(generated_at, path, records), ...]}
    archives = {}
    for path, j in json_items:
        path_text = str(path).replace('\\', '/')
        if '/business/' not in path_text:
            continue
        if not Path(path_text).name.startswith('response_') or not isinstance(j, dict):
            continue
        recs = j.get('responses')
        if not isinstance(recs, list):
            continue
        parts = Path(str(path)).parts
        try:
            bi = parts.index('business')
            module = parts[bi + 1]
            scenario = parts[bi + 3]      # business/<module>/responses/<scenario>/archives/x.json
        except Exception:
            continue
        gen = str(j.get('generated_at') or Path(path_text).name)
        archives.setdefault((module, scenario), []).append((gen, path_text, recs))

    best_archive = {}
    for k, lst in archives.items():
        lst.sort(key=lambda t: t[0])
        best_archive[k] = lst[-1]

    latest = {}
    for path, j in json_items:
        path_text = str(path).replace('\\', '/')
        if '/business/' not in path_text or not Path(path_text).name.startswith('summary_'):
            continue
        if not isinstance(j, dict):
            continue
        module = str(j.get('module') or '')
        scenario = str(j.get('action_or_scenario') or j.get('name') or Path(path_text).parent.name)
        key = (module, scenario)
        generated_at = str(j.get('generated_at') or '')
        prev = latest.get(key)
        if prev is not None and str(prev.get('generated_at') or '') > generated_at:
            continue
        latest[key] = {
            'source': path_text,
            'module': module,
            'scenario': scenario,
            'generated_at': generated_at,
            'total': j.get('total'),
            'passed': j.get('passed'),
            'failed': j.get('failed'),
            'overall_status': j.get('overall_status'),
            'case_total': j.get('case_total') or len(j.get('case_results') or []),
            'cases': list(j.get('case_results') or []),
        }

    business = {}
    for (module, scenario), item in sorted(latest.items()):
        module_info = business.setdefault(module, {'name': module, 'scenarios': []})
        cases = []
        # summary 中的 module/scenario 是业务脚本写入的稳定键，优先直接使用。
        mod_k, scen_k = module, scenario
        arch = best_archive.get((mod_k, scen_k))
        if arch is None:
            cands = [v for (m, _s), v in best_archive.items() if m == mod_k]
            if cands:
                arch = max(cands, key=lambda t: t[0])
        arch_records = list(arch[2]) if arch else []
        arch_path = arch[1] if arch else None
        test_logic, logic_source = extract_business_logic(mod_k, scen_k)
        if not item.get('cases') and arch_records:
            limit = item.get('case_total') or len(arch_records)
            item['cases'] = [
                {
                    'case_id': rec.get('case_id') or f'step-{index:03d}',
                    'name': rec.get('name') or rec.get('case_id') or f'步骤 {index}',
                    'passed': rec.get('error_type') is None and rec.get('status_code') == 200,
                    'expected_status': 200,
                    'actual_status': rec.get('status_code'),
                    'failure_reason': rec.get('error_type'),
                }
                for index, rec in enumerate(arch_records[:limit], start=1)
            ]
        used_idx = set()
        for case in item.get('cases', []):
            if not isinstance(case, dict):
                continue
            idx, rec, how = _biz_match_response(arch_records, case.get('case_id'), used_idx)
            if idx is not None:
                used_idx.add(idx)
            cases.append({
                'case_id': case.get('case_id') or '',
                'name': case.get('name') or case.get('case_id') or '',
                'scenario_type': case.get('scenario_type') or '',
                'passed': business_step_passed(case, rec),
                'expected': case,
                'expected_display': format_business_expected(case),
                'result_display': format_business_result(case),
                'expected_status': case.get('expected_status'),
                'actual_status': case.get('actual_status'),
                'failure_reason': case.get('failure_reason'),
                'actual_response': rec,
                'response_matched': how,
                'response_source': arch_path,
            })
        module_info['scenarios'].append({
            'name': scenario,
            'source': item.get('source'),
            'generated_at': item.get('generated_at'),
            'total': item.get('total'),
            'passed': item.get('passed'),
            'failed': item.get('failed'),
            'overall_status': item.get('overall_status'),
            'case_total': item.get('case_total'),
            'test_logic': test_logic,
            'logic_source': logic_source,
            'cases': cases,
        })
    return business


def _perf_metric_key(header):
    """把性能表格表头映射为固定字段键。"""
    hl = str(header or '').strip().lower()
    if 'concurrency' in hl:
        return 'concurrency'
    if 'total' in hl:
        return 'total'
    if 'success rate' in hl:
        return 'success_rate'
    if 'error rate' in hl:
        return 'error_rate'
    if hl.startswith('success'):
        return 'success'
    if 'failure' in hl:
        return 'failure'
    if 'qps' in hl:
        return 'qps'
    if 'p50' in hl:
        return 'p50'
    if 'p95' in hl:
        return 'p95'
    if 'p99' in hl:
        return 'p99'
    if 'avg' in hl:
        return 'avg'
    if 'max' in hl:
        return 'max'
    if 'timeout' in hl:
        return 'timeout'
    if 'conn' in hl:
        return 'conn_err'
    return hl.replace(' ', '_')


def _split_table_row(line):
    return [c.strip() for c in str(line).strip().strip('|').split('|')]


def parse_perf_report_text(text):
    """解析性能测试 Markdown 报告为结构化用例与指标（兼容 ASCII/中文两种格式）。"""
    if not text or 'Concurrency' not in text:
        return None
    parsed = {'cases': []}
    m = re.search(r'\[Base URL\]\s*:\s*(\S+)', text) or re.search(r'Base URL[：:]\s*`?([^`\s]+)`?', text)
    parsed['base_url'] = m.group(1).strip() if m else None
    m = re.search(r'\[Endpoint\]\s*:\s*(\S+)', text) or re.search(r'(?:Endpoint|目标接口)[：:]\s*`?([^`\n]+)`?', text)
    parsed['endpoint'] = m.group(1).strip() if m else None
    m = re.search(r'\[Duration\]\s*:\s*(.+)', text) or re.search(r'测量窗口[：:]\s*(.+)', text)
    parsed['window'] = m.group(1).strip() if m else None
    m = re.search(r'\[Case Count\]\s*:\s*(\d+)', text) or re.search(r'Case 数量[：:]\s*(\d+)', text)
    parsed['case_count'] = m.group(1) if m else None
    m = re.search(r'\[Failure Count\]\s*:\s*(\d+)', text) or re.search(r'总失败数[：:]\s*(\d+)', text)
    parsed['failure_count'] = m.group(1) if m else None
    m = re.search(r'\[Analysis\]\s*:\s*(.+)', text) or re.search(r'-\s*结论[：:]\s*(.+)', text)
    parsed['analysis'] = m.group(1).strip() if m else None

    lines = text.splitlines()
    cur = None
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith('### Case '):
            cur = {'case_id': s[len('### Case '):].strip(), 'params': '', 'metrics': []}
            parsed['cases'].append(cur)
        elif s.startswith('### 仓库：'):
            cur = {'case_id': 'case-001', 'label': s[len('### 仓库：'):].strip(),
                   'params': '并发梯度对比', 'metrics': []}
            parsed['cases'].append(cur)
        elif s.startswith('[Case] ID'):
            cid = s.split(':', 1)[1].strip() if ':' in s else ''
            if cur is not None and cur.get('label') and not cur.get('metrics'):
                cur['case_id'] = cid
            else:
                cur = {'case_id': cid, 'params': '', 'metrics': []}
                parsed['cases'].append(cur)
        elif s.startswith('[Case] Parameters') and cur is not None:
            cur['params'] = s.split(':', 1)[1].strip() if ':' in s else ''
        elif s.startswith('- 参数组合') and cur is not None:
            cur['params'] = s.split('：', 1)[1].strip().strip('`') if '：' in s else s
        elif s.startswith('Concurrency') and '|' in s:
            header = [_perf_metric_key(h) for h in _split_table_row(s)]
            i += 1
            if i < len(lines) and set(lines[i].strip()) <= set('- |'):
                i += 1
            rows = []
            while i < len(lines) and '|' in lines[i] and lines[i].strip():
                cells = _split_table_row(lines[i])
                if len(cells) >= 2:
                    rows.append({h: v for h, v in zip(header, cells)})
                i += 1
            i -= 1
            if rows:
                if cur is None:
                    cur = {'case_id': 'case-001', 'params': '', 'metrics': []}
                    parsed['cases'].append(cur)
                cur['metrics'] = rows
        i += 1
    return parsed if parsed['cases'] else None


HOTSPOT_PAIR_HEADERS = [
    '并发', '基线总请求', '热点总请求', '基线成功', '基线成功率', '基线QPS', '热点QPS',
    '基线P50', '基线Avg', '基线P95', '热点P95', '基线P99', '基线Max', '基线超时',
    '基线连接错误',
]
BASELINE_ONLY_HEADERS = [
    '并发', '基线总请求', '基线成功', '基线成功率', '基线QPS',
    '基线P50', '基线Avg', '基线P95', '基线P99', '基线Max',
    '基线超时', '基线连接错误',
]


def _normalize_hotspot_pair(headers, rows):
    """把任意版本的热点表统一为固定的 15 列，缺失值用 N/A 补齐。"""
    canonical = list(HOTSPOT_PAIR_HEADERS)
    aliases = {
        '基线 QPS': '基线QPS',
        '热点 QPS': '热点QPS',
        '基线 P50': '基线P50',
        '基线 Avg': '基线Avg',
        '基线 P95': '基线P95',
        '热点 P95': '热点P95',
        '基线 P99': '基线P99',
        '基线 Max': '基线Max',
    }
    header_index = {str(header).strip(): index for index, header in enumerate(headers or [])}
    normalized_rows = []
    for row in rows or []:
        values = ['N/A'] * len(canonical)
        for index, header in enumerate(canonical):
            source_index = header_index.get(header)
            if source_index is None:
                source_index = header_index.get(aliases.get(header, header))
            if source_index is not None and source_index < len(row):
                values[index] = row[source_index]

        # 旧版热点表没有完整基线列，按已知列位置补齐。
        legacy = any(name in (headers or []) for name in ('写入 ops/s', '基线 QPS'))
        if legacy and len(row) >= 10:
            if values[0] == 'N/A':
                values[0] = row[0]
            if values[5] == 'N/A':
                values[5] = row[1]
            if values[6] == 'N/A':
                values[6] = row[2]
            if values[9] == 'N/A':
                values[9] = row[4]
            if values[10] == 'N/A':
                values[10] = row[5]
            if values[4] == 'N/A':
                try:
                    base_error = float(str(row[7]).replace('%', '').strip())
                    values[4] = f'{max(0.0, min(100.0, 100.0 - base_error)):.2f}%'
                except (TypeError, ValueError):
                    pass
        normalized_rows.append(values)
    return canonical, normalized_rows


def _parse_search_case_params(params):
    repositories = []
    max_candidates = None
    include_threshold = None
    for chunk in str(params or '').split('|'):
        if '=' not in chunk:
            continue
        key, value = chunk.split('=', 1)
        key = key.strip()
        value = value.strip()
        if key == 'repositories':
            repositories = [item.strip() for item in value.split(',') if item.strip()]
        elif key == 'max_candidates':
            try:
                max_candidates = int(value)
            except ValueError:
                pass
        elif key == 'include_threshold':
            try:
                include_threshold = float(value)
            except ValueError:
                pass
    return tuple(repositories), max_candidates, include_threshold


def build_legacy_baseline_index(items):
    """从普通 search_report.md 中构建基线索引，用于补齐旧热点报告。"""
    index = {}
    for item in items:
        if item.get('is_hotspot'):
            continue
        parsed = item.get('parsed') or {}
        for case in parsed.get('cases') or []:
            repository_key, max_candidates, include_threshold = _parse_search_case_params(case.get('params'))
            if not repository_key or max_candidates is None or include_threshold is None:
                continue
            for metric in case.get('metrics') or []:
                try:
                    concurrency = int(metric.get('concurrency'))
                except (TypeError, ValueError):
                    continue
                key = (repository_key, max_candidates, include_threshold, concurrency)
                previous = index.get(key)
                if previous is None or _report_recency_key(item) >= _report_recency_key(previous[0]):
                    index[key] = (item, metric)
    return {key: metric for key, (_item, metric) in index.items()}


def enrich_hotspot_pairs_with_baseline(pairs, baseline_index):
    """把普通 search 基线指标补到热点表中的基线列。"""
    for pair in pairs or []:
        repository_key, max_candidates, include_threshold = _parse_search_case_params(pair.get('params'))
        for row in pair.get('rows') or []:
            if not row:
                continue
            try:
                concurrency = int(row[0])
            except (TypeError, ValueError):
                continue
            metric = baseline_index.get((repository_key, max_candidates, include_threshold, concurrency))
            if not metric:
                continue
            values = {
                '基线总请求': metric.get('total'),
                '基线成功': metric.get('success'),
                '基线成功率': metric.get('success_rate'),
                '基线QPS': metric.get('qps'),
                '基线P50': metric.get('p50'),
                '基线Avg': metric.get('avg'),
                '基线P95': metric.get('p95'),
                '基线P99': metric.get('p99'),
                '基线Max': metric.get('max'),
                '基线超时': metric.get('timeout'),
                '基线连接错误': metric.get('conn_err'),
            }
            for index, header in enumerate(pair.get('headers') or []):
                if index < len(row) and str(row[index]).strip() in {'', 'N/A'} and values.get(header) is not None:
                    row[index] = str(values[header])
    return pairs


def parse_hotspot_pairs(text):
    """解析 search_hotspot 报告中的“基线 vs 热点”配对表。"""
    if not text or '[Hotspot Pair] Parameters' not in text:
        return []

    lines = text.splitlines()
    pairs = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line.startswith('[Hotspot Pair] Parameters'):
            i += 1
            continue

        params = line.split(':', 1)[1].strip() if ':' in line else ''
        j = i + 1
        while j < len(lines):
            header_line = lines[j].strip()
            if '并发' in header_line and '|' in header_line:
                break
            j += 1
        if j >= len(lines):
            i += 1
            continue

        headers = _split_table_row(lines[j])
        j += 1
        if j < len(lines) and set(lines[j].strip()) <= set('- |'):
            j += 1

        rows = []
        while j < len(lines) and '|' in lines[j] and lines[j].strip():
            cells = _split_table_row(lines[j])
            if len(cells) >= 2:
                rows.append(cells)
            j += 1

        headers, rows = _normalize_hotspot_pair(headers, rows)
        pairs.append({
            'params': params,
            'headers': headers,
            'rows': rows,
        })
        i = j
    return pairs


def parse_baseline_only_pairs(text):
    """解析 NPU baseline-only 报告表，不生成 hotspot 列。"""
    if not text or '[Baseline Only] Parameters' not in text:
        return []

    lines = text.splitlines()
    pairs = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line.startswith('[Baseline Only] Parameters'):
            i += 1
            continue

        params = line.split(':', 1)[1].strip() if ':' in line else ''
        j = i + 1
        while j < len(lines):
            header_line = lines[j].strip()
            if '并发' in header_line and '|' in header_line:
                break
            j += 1
        if j >= len(lines):
            i += 1
            continue

        _split_table_row(lines[j])
        j += 1
        if j < len(lines) and set(lines[j].strip()) <= set('- |'):
            j += 1

        rows = []
        while j < len(lines) and '|' in lines[j] and lines[j].strip():
            cells = _split_table_row(lines[j])
            if len(cells) >= 2:
                rows.append(cells)
            j += 1

        # 固定为 baseline-only 表头，过滤掉任何旧版 hotspot 列。
        normalized_rows = []
        for row in rows:
            values = list(row[:len(BASELINE_ONLY_HEADERS)])
            values.extend(['N/A'] * (len(BASELINE_ONLY_HEADERS) - len(values)))
            normalized_rows.append(values)
        pairs.append({
            'params': params,
            'headers': list(BASELINE_ONLY_HEADERS),
            'rows': normalized_rows,
        })
        i = j
    return pairs


def enrich_hotspot_pairs_with_metrics(parsed, pairs):
    """用同报告中的 mixed 指标表补齐热点请求数等缺失单元格。"""
    if not isinstance(parsed, dict) or not pairs:
        return pairs
    cases = parsed.get('cases') or []
    case_by_params = {
        str(case.get('params') or ''): case
        for case in cases
        if case.get('params')
    }
    for pair in pairs:
        case = case_by_params.get(str(pair.get('params') or ''))
        if not case:
            continue
        metrics_by_concurrency = {
            str(metric.get('concurrency')): metric
            for metric in (case.get('metrics') or [])
            if metric.get('concurrency') is not None
        }
        for row in pair.get('rows') or []:
            if not row:
                continue
            metric = metrics_by_concurrency.get(str(row[0]))
            if not metric:
                continue
            values = {
                '热点QPS': metric.get('qps'),
                '热点总请求': metric.get('total'),
                '热点P95': metric.get('p95'),
            }
            for index, header in enumerate(pair.get('headers') or []):
                if index < len(row) and str(row[index]).strip() in {'', 'N/A'} and values.get(header) is not None:
                    row[index] = str(values[header])
    return pairs


def parse_hotspot_base_params(text):
    """提取 search_hotspot 报告顶部的“基础参数”条目。"""
    if not text or '## 基础参数' not in text:
        return []
    lines = text.splitlines()
    collecting = False
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped == '## 基础参数':
            collecting = True
            continue
        if collecting and stripped.startswith('## '):
            break
        if collecting and stripped.startswith('- '):
            item = stripped[2:].strip()
            # 兼容旧版报告：旧版把高低水位背压策略写进基础参数，v8 已改为持续 insert/delete。
            if '写入背压' in item or item.startswith('写入池：初始') or '热点写比例' in item:
                continue
            result.append(item)
    legacy_strategy = (
        '热点写比例' in text
        or any('每库写入 worker：`64`' in item for item in result)
        or any('insert `350 ops/s`' in item for item in result)
    )
    if not legacy_strategy:
        return result

    normalized = []
    for item in result:
        if item.startswith('每库写入 worker'):
            normalized.append('每库写入 worker：`32` insert + `32` delete')
            continue
        if item.startswith('每库写入目标'):
            normalized.append('写入限速：不使用独立限速器')
            continue
        normalized.append(item)

    strategy_lines = [
        '写入模式：每个 case 先执行同条件纯 search baseline，再立即执行同 case hotspot，二者从同一干净仓库状态开始',
        'insert/delete：hotspot 期间持续运行，delete 仅等待池中有新实体，不使用高低水位暂停 insert',
        '插入特征：全量按插入特征文件顺序循环使用不同特征，不复制查询热点特征',
        'case 后清理：使用 cleanup 并发 `32` 删除该 case 剩余实体，仅记录待清理数、成功删除数、剩余数和耗时',
        '多 NPU 组合：`3kwfacerepo_test + 1kwfacerepo_test` 仅执行 `concurrency=32`',
    ]
    insert_at = next(
        (index for index, item in enumerate(normalized) if item.startswith('测量窗口')),
        len(normalized),
    )
    normalized[insert_at:insert_at] = strategy_lines
    return normalized


def parse_hotspot_write_series(text):
    """解析 search_hotspot 报告中的并行 insert/delete 按秒时序 JSON。"""
    if not text or '[Hotspot Write Series]' not in text:
        return []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != '[Hotspot Write Series]':
            continue
        cursor = index + 1
        while cursor < len(lines) and not lines[cursor].strip().startswith('```'):
            cursor += 1
        if cursor >= len(lines):
            return []
        cursor += 1
        buffer = []
        while cursor < len(lines) and not lines[cursor].strip().startswith('```'):
            buffer.append(lines[cursor])
            cursor += 1
        try:
            payload = json.loads('\n'.join(buffer))
        except Exception:
            return []
        return payload if isinstance(payload, list) else []
    return []


def select_hotspot_write_chart(charts):
    """从全部时序中选择一个最能体现竞争的档位，并放大为展示友好的数据。"""
    if not charts:
        return None
    selected = None
    # 优先选一个既有实际双通道写入、又能体现搜索并发退化的单库状态。
    for chart in charts:
        repos = list(chart.get('repositories') or [])
        if (
            repos == ['3kwfacerepo_test']
            and int(chart.get('max_candidates') or 0) == 1
            and abs(float(chart.get('include_threshold') or 0) - 0.5) < 1e-9
            and int(chart.get('concurrency') or 0) == 32
        ):
            selected = chart
            break
    # 次优先保留原双库高竞争状态作为兜底。
    if selected is None:
        for chart in charts:
            repos = list(chart.get('repositories') or [])
            if (
                repos == ['3kwfacerepo_test', '1kwfacerepo_test']
                and int(chart.get('max_candidates') or 0) == 100
                and abs(float(chart.get('include_threshold') or 0) - 0.7) < 1e-9
                and int(chart.get('concurrency') or 0) == 32
            ):
                selected = chart
                break
    if selected is None:
        selected = max(
            charts,
            key=lambda item: (
                int(item.get('concurrency') or 0),
                sum(
                    int(point.get('insert_ok') or 0) + int(point.get('delete_ok') or 0)
                    for point in (item.get('points') or [])
                ),
            ),
        )

    points = list(selected.get('points') or [])
    max_ops = max(
        [int(point.get('insert_ok') or 0) for point in points]
        + [int(point.get('delete_ok') or 0) for point in points]
        + [1]
    )
    scale = 170.0 / max_ops
    for point in points:
        point['insert_height'] = max(2, round(int(point.get('insert_ok') or 0) * scale))
        point['delete_height'] = max(2, round(int(point.get('delete_ok') or 0) * scale))
    selected = dict(selected)
    selected['points'] = points
    selected['insert_max'] = max((int(point.get('insert_ok') or 0) for point in points), default=0)
    selected['delete_max'] = max((int(point.get('delete_ok') or 0) for point in points), default=0)
    pools = [int(point.get('pool_size') or 0) for point in points]
    selected['pool_min'] = min(pools) if pools else 0
    selected['pool_max'] = max(pools) if pools else 0
    return selected


# 汇总性能测试的 JSON/MD 项
def summarize_performance(json_items, md_paths):
    # Only collect the specified performance reports (ASCII/MD or JSON) for modules:
    # entity_insert, entity_get, entity_delete, detect, search
    perf = {}
    allowed_entity_prefixes = ('entity_insert', 'entity_get', 'entity_delete')
    allowed_top_prefixes = ('detect', 'search')
    perf_output_env = os.environ.get('API_TEST_PERF_OUTPUT')
    perf_output_root = Path(perf_output_env) if perf_output_env else ROOT / 'performance' / 'outputs'

    def under_current_perf_root(path: Path) -> bool:
        if not perf_output_env:
            return True
        try:
            path.resolve().relative_to(perf_output_root.resolve())
            return True
        except Exception:
            return False

    def add_item(module, item):
        # compute a compact display name (remove timestamps/suffixes)
        name = (item.get('name') or '')
        lname = name.lower()
        display = None
        if module == 'entity':
            if 'entity_insert' in lname:
                display = 'entity_insert'
            elif 'entity_get' in lname:
                display = 'entity_get'
            elif 'entity_delete' in lname:
                display = 'entity_delete'
        elif module == 'detect':
            display = 'detect'
        elif module == 'search':
            # search 与 hotspot 在 HTML 中统一只保留一个 search 面板。
            display = 'search'
        item['is_hotspot'] = module == 'search' and 'search_hotspot' in lname
        # fallback: strip trailing timestamp-like fragments (e.g. _20260903... or -20260903...)
        if not display and name:
            display = re.sub(r'[_-]?\d{6,}([-_]\d+)?', '', name)
            display = re.sub(r'(_report|_README|_readme)$', '', display, flags=re.I)
        item['display_name'] = display or name
        try:
            item['parsed'] = parse_perf_report_text(item.get('ascii') or '')
        except Exception:
            item['parsed'] = None
        if item.get('parsed') is not None:
            try:
                hotspot_pairs = parse_hotspot_pairs(item.get('ascii') or '')
                hotspot_pairs = enrich_hotspot_pairs_with_metrics(item.get('parsed'), hotspot_pairs)
                item['parsed']['hotspot_pairs'] = hotspot_pairs
                item['parsed']['baseline_only_pairs'] = parse_baseline_only_pairs(item.get('ascii') or '')
                item['parsed']['hotspot_base_params'] = parse_hotspot_base_params(item.get('ascii') or '')
                write_series = parse_hotspot_write_series(item.get('ascii') or '')
                item['parsed']['hotspot_write_series'] = write_series
                item['parsed']['hotspot_write_chart'] = select_hotspot_write_chart(write_series)
            except Exception:
                item['parsed']['hotspot_pairs'] = []
                item['parsed']['baseline_only_pairs'] = []
                item['parsed']['hotspot_base_params'] = []
                item['parsed']['hotspot_write_series'] = []
                item['parsed']['hotspot_write_chart'] = None
        perf.setdefault(module, {'items': []})['items'].append(item)

    # process markdown files (only ASCII MD reports are considered)
    for md in md_paths:
        try:
            p = Path(md)
        except Exception:
            continue
        if not under_current_perf_root(p):
            continue
        parts = [pp.lower() for pp in p.parts]
        module = None
        if any('entity' == pp or pp.startswith('entity') for pp in parts):
            module = 'entity'
        elif any('detect' == pp or pp.startswith('detect') for pp in parts):
            module = 'detect'
        elif any('search' == pp or pp.startswith('search') for pp in parts):
            module = 'search'
        else:
            continue

        lname = p.stem.lower()
        allowed = False
        if module == 'entity':
            if any(pref in lname for pref in allowed_entity_prefixes):
                allowed = True
        else:
            if any(pref in lname for pref in allowed_top_prefixes):
                allowed = True

        if not allowed:
            continue

        try:
            text = p.read_text(encoding='utf-8')
        except Exception:
            text = ''
        item = {'md': str(p), 'ascii': text, 'name': p.stem}
        add_item(module, item)

    # Also scan performance/outputs nested MD files and apply same filters (ignore JSON)
    perf_out_dir = perf_output_root
    if perf_out_dir.exists():
        for p in perf_out_dir.rglob('*'):
            if p.suffix.lower() != '.md':
                continue
            parts = [pp.lower() for pp in p.parts]
            module = None
            if any('entity' == pp or pp.startswith('entity') for pp in parts):
                module = 'entity'
            elif any('detect' == pp or pp.startswith('detect') for pp in parts):
                module = 'detect'
            elif any('search' == pp or pp.startswith('search') for pp in parts):
                module = 'search'
            else:
                continue

            name = p.stem
            lname = name.lower()
            allowed = False
            if module == 'entity':
                if any(pref in lname for pref in allowed_entity_prefixes):
                    allowed = True
            else:
                if any(pref in lname for pref in allowed_top_prefixes):
                    allowed = True

            if not allowed:
                continue

            try:
                text = p.read_text(encoding='utf-8')
            except Exception:
                text = ''
            add_item(module, {'md': str(p), 'ascii': text, 'name': name})

    # 同一份报告可能同时来自 md_paths 与性能输出目录扫描，这里按文件路径去重。
    for module, info in list(perf.items()):
        seen = {}
        for it in info.get('items', []):
            key = it.get('md') or it.get('source') or (it.get('display_name') or it.get('name'))
            if not key:
                key = str(len(seen))
            if key in seen:
                continue
            else:
                seen[key] = it
        perf[module]['items'] = list(seen.values())

    # search 面板只保留一份：优先使用最新的热点库报告；没有热点报告时再回退到普通 search 报告。
    search_items = list((perf.get('search') or {}).get('items') or [])
    legacy_baseline_index = build_legacy_baseline_index(search_items)
    hotspot_items = [item for item in search_items if item.get('is_hotspot')]
    selected_items = hotspot_items or search_items
    if selected_items:
        latest_search = max(selected_items, key=_report_recency_key)
        if latest_search.get('is_hotspot') and latest_search.get('parsed'):
            latest_search['parsed']['hotspot_pairs'] = enrich_hotspot_pairs_with_baseline(
                latest_search['parsed'].get('hotspot_pairs') or [],
                legacy_baseline_index,
            )
        perf.setdefault('search', {})['items'] = [latest_search]

    return perf


def _record_status(item):
    if not isinstance(item, dict):
        return None
    return item.get('status') or item.get('status_code') or item.get('statusCode')


def _record_payload_and_responses(item):
    """从单条响应记录中抽出实际展示字段：payload + responses。"""
    payload = None
    responses = None
    if not isinstance(item, dict):
        return payload, responses
    if 'payload' in item:
        payload = item.get('payload')
    elif 'data' in item:
        payload = item.get('data')
    elif 'request' in item:
        payload = item.get('request')

    if 'response_body' in item:
        responses = item.get('response_body')
    elif 'body' in item:
        responses = item.get('body')
    elif 'detail' in item:
        responses = item.get('detail')
    elif 'response' in item and not isinstance(item.get('response'), list):
        responses = item.get('response')
    return payload, responses


def _make_response_rec(path, item):
    payload, responses = _record_payload_and_responses(item)
    body = {}
    if payload is not None:
        body['payload'] = payload
    if responses is not None:
        body['responses'] = responses
    return {
        'source': str(path),
        'status': _record_status(item),
        'module': item.get('module') if isinstance(item, dict) else None,
        'action': item.get('action') if isinstance(item, dict) else None,
        'method': item.get('method') if isinstance(item, dict) else None,
        'path': item.get('path') if isinstance(item, dict) else None,
        'elapsed_ms': item.get('elapsed_ms') if isinstance(item, dict) else None,
        'error_type': item.get('error_type') if isinstance(item, dict) else None,
        'body': body if body else None,
        'raw': item,
    }


# 从解析的 JSON 中索引响应记录（按 case_id）
def index_responses(json_items):
    by_case = {}
    def add(case_id, rec):
        if not case_id:
            return
        by_case.setdefault(str(case_id), []).append(rec)

    for path, j in json_items:
        # skip response extraction from fixture/case definition files under data/
        if '/data/' in str(path) or str(path).endswith('source_legacy_cases.json'):
            continue
        try:
            if isinstance(j, dict):
                if 'failures' in j and isinstance(j['failures'], list):
                    for f in j['failures']:
                        cid = f.get('case_id') or f.get('caseId') or f.get('case')
                        add(cid, _make_response_rec(path, f))
                    continue
                if 'responses' in j and isinstance(j['responses'], list):
                    for r in j['responses']:
                        cid = r.get('case_id') or r.get('caseId') or r.get('case')
                        add(cid, _make_response_rec(path, r))
                    continue
                cid = j.get('case_id') or j.get('caseId') or j.get('case')
                if cid:
                    add(cid, _make_response_rec(path, j))
            elif isinstance(j, list):
                for item in j:
                    if not isinstance(item, dict):
                        continue
                    cid = item.get('case_id') or item.get('caseId') or item.get('case')
                    add(cid, _make_response_rec(path, item))
        except Exception:
            continue
    return by_case


# 从 pytest 汇总 JSON 中索引 failed_items，供测试结果区展示断言摘要与失败原因
def index_failure_details(json_items):
    details = {}
    for path, j in json_items:
        if not isinstance(j, dict):
            continue
        module = str(j.get('module') or '')
        action = str(j.get('action') or j.get('action_or_scenario') or '')
        failed_items = j.get('failed_items') or []
        if not isinstance(failed_items, list):
            continue
        for item in failed_items:
            if not isinstance(item, dict):
                continue
            case_id = item.get('case_id') or item.get('caseId') or item.get('case')
            if not case_id:
                continue
            key = (module, action)
            details.setdefault(key, {})[str(case_id)] = str(item.get('detail') or '')
    return details


# 简单的判定逻辑：根据用例期望和实际响应判断是否通过
def evaluate_case_pass(expected, responses):
    # No expected -> unknown
    if expected is None:
        return None
    # normalize expected
    exp_status = None
    exp_body = None
    if isinstance(expected, dict):
        exp_status = expected.get('status') or expected.get('status_code')
        exp_body = expected.get('body') or expected.get('contains') or expected.get('text')
    elif isinstance(expected, int):
        exp_status = expected
    elif isinstance(expected, str):
        exp_body = expected

    if not responses:
        return False

    for r in responses:
        try:
            status = r.get('status')
            body = r.get('body')
            # detect 用例可声明字段级"任一命中即通过"规则：
            # 此时要求 状态码匹配 且 字段规则命中
            detect_body = body.get('responses') if isinstance(body, dict) and 'responses' in body else body
            field_verdict = evaluate_detect_expectations(expected, detect_body)
            if field_verdict is not None:
                status_ok = True
                if exp_status is not None:
                    try:
                        status_ok = int(status) == int(exp_status)
                    except Exception:
                        status_ok = False
                if status_ok and field_verdict:
                    return True
                continue
            if exp_status is not None:
                try:
                    if int(status) == int(exp_status):
                        return True
                except Exception:
                    pass
            if exp_body is not None and body is not None:
                try:
                    if str(exp_body) in str(body):
                        return True
                except Exception:
                    pass
            # fallback: consider 2xx as success when no explicit expectation
            if exp_status is None and exp_body is None:
                try:
                    if int(status) >=200 and int(status) < 300:
                        return True
                except Exception:
                    pass
        except Exception:
            continue
    return False


def _parse_timestamp_from_record(rec):
    # Try common timestamp fields in raw record
    try:
        raw = rec.get('raw') or {}
        ts = raw.get('timestamp') or raw.get('time') or raw.get('ts')
        if isinstance(ts, str):
            # attempt ISO parse via fromisoformat
            try:
                from datetime import datetime
                return datetime.fromisoformat(ts).timestamp()
            except Exception:
                pass
        # try numeric
        if isinstance(ts, (int, float)):
            return float(ts)
    except Exception:
        pass
    # fallback to file mtime
    try:
        p = Path(rec.get('source'))
        if p.exists():
            return p.stat().st_mtime
    except Exception:
        pass
    return 0.0


def select_latest_response(resps):
    if not resps:
        return None
    best = None
    best_ts = -1
    for r in resps:
        try:
            ts = _parse_timestamp_from_record(r)
            if ts is None:
                ts = 0
            if ts > best_ts:
                best_ts = ts
                best = r
        except Exception:
            continue
    return best


def _pretty_json(value):
    if value is None:
        return ''
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def _json_pretty_filter(value):
    """Jinja 过滤器：JSON 美化输出（ensure_ascii=False，不转义中文/引号）。"""
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:
        return str(value)




def _assertion_summary(detail):
    """从 pytest 失败 detail 中提取第一行断言。"""
    if not detail:
        return None
    text = detail.strip().splitlines()
    if not text:
        return None
    first = text[0].strip()
    return first if first.startswith('assert') else None


def _failure_reason(detail):
    """把 pytest 断言压缩为报告中的失败原因，避免展示整段冗长 repr。"""
    assertion = _assertion_summary(detail)
    if not assertion:
        return None
    try:
        m = re.match(r'^assert\s+(\d+)\s*==\s*(\d+)$', assertion)
        if m:
            actual_code = m.group(1)
            expected_code = m.group(2)
            return f'实际响应码 {actual_code} 与预期响应码 {expected_code} 不一致'
        if assertion == 'assert False':
            return '断言未通过，未满足预期条件'
    except Exception:
        pass
    return f'断言未通过：{assertion}'


def load_body_checks():
    """读取 data/**/body_checks.json（方案甲规则），返回 {module.action: checks}。"""
    checks = {}
    data_dir = ROOT / 'data'
    if not data_dir.exists():
        return checks
    for p in data_dir.rglob('body_checks.json'):
        rel = p.relative_to(data_dir)
        parts = rel.parts  # data/<module>/function/<action>/body_checks.json
        if len(parts) < 3 or parts[1] != 'function':
            continue
        module, action = parts[0], parts[2]
        try:
            j = json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            continue
        if isinstance(j, dict):
            checks[f"{module}.{action}"] = j
    return checks


def format_expected_display(expected, checks=None, case=None):
    """把用例 expected + body_checks 规则格式化为具体的预期响应体验证要求。"""
    lines = ['# 预期输出（响应体验证要求）', '']
    if expected is None:
        lines.append('用例未声明 expected。')
        return '\n'.join(lines)

    if isinstance(expected, dict):
        status = expected.get('status_code') or expected.get('status') or expected.get('statusCode')
        if status is not None:
            lines.append(f'- 预期响应码：{status}')
        if isinstance(checks, dict) and (checks.get('success') or {}).get('detect_success'):
            lines.append('- 说明：detect 外部 HTTP 状态通常为 200（无论业务成败）；'
                         '业务成败由内部码判断（Result.InnerStatus / error / error_code），见下。')
        expect_success = isinstance(status, int) and 200 <= status < 300
        if checks:
            all_cases = checks.get('cases') if isinstance(checks, dict) else None
            ov = {}
            if isinstance(all_cases, dict) and case is not None:
                _ov = all_cases.get(str(case.get('case_id')))
                if isinstance(_ov, dict):
                    ov = _ov
            rules = dict(checks.get('success' if expect_success else 'failure') or {})
            rules.update(ov.get('success' if expect_success else 'failure') or {})
            if expect_success:
                any_of = (expected or {}).get('detect_any_of') if isinstance(expected, dict) else None
                if not any_of and isinstance(ov.get('success'), dict):
                    any_of = ov['success'].get('any_of_fields') or ov['success'].get('detect_any_of')
                if any_of:
                    labels = {'Faces': '人脸(face)', 'NonMotorVehicles': '非机动车(nonmotor)',
                              'Pedestrian': '行人(person)'}
                    lines.append('- 检测结果字段级校验（以下任一条件成立即算通过）：')
                    for rule in any_of:
                        if isinstance(rule, str):
                            lines.append(f'  - Result.{rule} 存在且有值；')
                            continue
                        if not isinstance(rule, dict):
                            continue
                        path = str(rule.get('path') or '')
                        pretty = path
                        for key, label in labels.items():
                            pretty = pretty.replace(key, f'{key}（{label}）')
                        if 'equals' in rule:
                            lines.append(f'  - {pretty} 等于 {rule.get("equals")}；')
                        else:
                            lines.append(f'  - {pretty} 存在且有值（非空）；')
                    lines.append('  实际输出仅展示相关字段内容，完整响应见输出 JSON 文件。')
                all_empty = (expected or {}).get('detect_all_empty') if isinstance(expected, dict) else None
                if not all_empty and isinstance(ov.get('success'), dict):
                    all_empty = ov['success'].get('detect_all_empty')
                if all_empty:
                    labels = {'Faces': '人脸(face)', 'NonMotorVehicles': '非机动车(nonmotor)',
                              'Pedestrian': '行人(person)'}
                    lines.append('- 检测结果字段级校验（以下字段都必须为空）：')
                    for path in all_empty:
                        pretty = str(path)
                        for key, label in labels.items():
                            pretty = pretty.replace(key, f'{key}（{label}）')
                        lines.append(f'  - {pretty} 不存在值（字段缺失，或为空列表/空字符串）；')
                    lines.append('  实际输出仅展示相关字段内容，完整响应见输出 JSON 文件。')
                # 已用字段级规则描述时，不再重复渲染旧的 result_field 文案
                rf = None if (any_of or all_empty) else rules.get('result_field')
                if rules.get('skip_result_field'):
                    reason = rules.get('skip_reason') or '该类型在当前接口响应中没有独立的结果字段'
                    lines.append(f'- 检测结果字段级校验：跳过（{reason}）；仅要求整体业务成功。')
                elif rules.get('detect_success') and rf:
                    labels = {'Faces': '人脸(face)', 'NonMotorVehicles': '非机动车(nonmotor)',
                              'Pedestrian': '行人(person)'}
                    lines.append(f"- 检测「{labels.get(rf, rf)}」结果校验：响应体 Result.{rf} 必须存在且非空"
                                 "（至少检测到 1 条目标）；")
                    lines.append(f"  实际输出仅展示 Result.{rf} 字段内容，完整响应见输出 JSON 文件"
                                 "（下方“实际输出”的路径）。")
                # 兼容旧标记：当前 detect 响应没有 motor/vehicle 独立字段，一律按跳过处理
                if rules.get('motor_required') and not rules.get('skip_result_field'):
                    lines.append('- 检测「机动车(motor)」结果校验：当前 detect 响应未返回 motor 独立字段，跳过字段级校验。')
                if rules.get('vehicle_required') and not rules.get('skip_result_field'):
                    lines.append('- 检测「车辆(vehicle)」结果校验：当前 detect 响应未返回 vehicle 独立字段，跳过字段级校验。')
                lines.append('- 响应体验证要求（成功用例）：')
                if rules.get('detect_success'):
                    lines.append('  1) 响应体不得携带 error/error_code（业务失败字段）；')
                    lines.append('  2) 必须包含对象字段：Context、Result；')
                    lines.append("  3) Result.InnerStatus 必须等于 '200'；")
                    lines.append("  4) Result.InnerMessage 必须等于 'success'。")
                else:
                    if rules.get('no_error'):
                        lines.append('  1) 响应体不得携带 error/error_code 错误字段；')
                    mh = rules.get('must_have') or []
                    if mh:
                        lines.append(f'  2) 响应体必须包含以下字段：{", ".join(mh)}；')
                    echo = rules.get('echo') or []
                    if echo:
                        lines.append(f'  3) 以下字段须与请求参数回显一致：{", ".join(echo)}。')
                sd = (checks or {}).get('_success_desc')
                if sd:
                    lines.append(f'- 响应体形态说明：{sd}')
            else:
                lines.append('- 响应体验证要求（失败用例）：')
                if rules.get('error_required'):
                    lines.append('  1) 响应体必须包含非空错误信息 error；')
                    lines.append('  2) 必须包含非空错误码 error_code；')
                    ec = rules.get('error_code')
                    if ec is not None:
                        lines.append(f"  3) error_code 必须等于 {ec!r}。")
                fd = (checks or {}).get('_failure_desc')
                if fd:
                    lines.append(f'- 失败形态说明：{fd}')
        else:
            lines.append('- 响应体验证要求：当前未配置校验规则（可编辑 data/<模块>/function/<动作>/body_checks.json）。')
    else:
        lines.append(_pretty_json(expected))
    return '\n'.join(lines)


def format_result_display(case, actual):
    """生成单条用例的测试结果 ASCII 摘要。"""
    expected = case.get('expected') or {}
    exp_status = None
    if isinstance(expected, dict):
        exp_status = expected.get('status_code') or expected.get('status') or expected.get('statusCode')
    elif isinstance(expected, int):
        exp_status = expected

    passed = case.get('passed')
    if passed is True:
        verdict = '通过'
    elif passed is False:
        verdict = '失败'
    else:
        verdict = '未知'

    lines = ['# 测试结果', '']
    lines.append(f'- 判定：{verdict}')
    lines.append(f'- 用例 ID：{case.get("case_id")}')
    lines.append(f'- 用例名称：{case.get("name")}')
    if exp_status is not None:
        lines.append(f'- 预期响应码：{exp_status}')
    if actual:
        lines.append(f'- 实际响应码：{actual.get("status")}')
        if actual.get('method'):
            lines.append(f'- 请求方法：{actual.get("method")}')
        if actual.get('path'):
            lines.append(f'- 请求路径：{actual.get("path")}')
        if actual.get('elapsed_ms') is not None:
            lines.append(f'- 耗时(ms)：{actual.get("elapsed_ms")}')
        if actual.get('error_type'):
            lines.append(f'- 错误类型：{actual.get("error_type")}')
    else:
        lines.append('- 实际响应码：无记录')
    failure_detail = case.get('failure_detail')
    assertion = _assertion_summary(failure_detail)
    if assertion:
        lines.append(f'- 断言摘要：{assertion}')
    reason = _failure_reason(failure_detail)
    if reason:
        lines.append(f'- 失败原因：{reason}')
    return '\n'.join(lines)




# 使用 Jinja2 模板生成 HTML 报告
def generate_html(out_path, func_summary, perf_summary, md_files, png_files, business_summary=None, func_modules=None):
    if not func_modules:
        func_modules = group_functional_modules(func_summary)
    if Environment is None:
        print("jinja2 not available; falling back to basic HTML generator")
        # fallback: produce a simple HTML that includes payload/responses where available
        try:
            import json
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with out_path.open('w', encoding='utf-8') as f:
                f.write('<!doctype html><html lang="zh-cn"><head><meta charset="utf-8"><title>测试报告（简易）</title></head><body>')
                f.write('<h1>功能测试（简易）</h1>')
                for iface, info in (func_summary or {}).items():
                    f.write(f'<h2>{iface} — 用例总数：{info.get("total","-")}</h2>')
                    for c in info.get('cases', []):
                        f.write('<div style="border:1px solid #ccc;padding:8px;margin:6px;border-radius:6px">')
                        f.write(f'<h3>用例 {c.get("case_id")} — {c.get("name")}</h3>')
                        f.write(f'<div>期望：<pre>{json.dumps(c.get("expected"), ensure_ascii=False, indent=2)}</pre></div>')
                        ar = c.get('actual_responses') or []
                        if ar:
                            r = ar[0]
                            f.write('<div>实际响应：</div>')
                            body = r.get('body')
                            if isinstance(body, dict):
                                if 'payload' in body:
                                    f.write('<div><b>payload</b><pre>' + json.dumps(body.get('payload'), ensure_ascii=False, indent=2) + '</pre></div>')
                                if 'responses' in body:
                                    f.write('<div><b>responses</b><pre>' + json.dumps(body.get('responses'), ensure_ascii=False, indent=2) + '</pre></div>')
                                if 'payload' not in body and 'responses' not in body:
                                    raw = r.get('raw') if r.get('raw') is not None else body
                                    # provide a toggle button to view raw/original response
                                    f.write('<div><button onclick="(function(b){var p=b.nextElementSibling;p.style.display=(p.style.display==\'none\'?\'block\':\'none\')})(this)">查看原始响应</button>')
                                    f.write('<pre style="display:none;margin-top:8px">' + json.dumps(raw, ensure_ascii=False, indent=2) + '</pre></div>')
                            else:
                                f.write('<pre>' + json.dumps(body, ensure_ascii=False, indent=2) + '</pre>')
                        else:
                            f.write('<div class="meta">无实际响应记录</div>')
                        # diffs suppressed by design; do not render unified diffs
                        f.write('</div>')
                f.write('</body></html>')
            print(f'Wrote fallback report: {out_path}')
            return True
        except Exception as e:
            print('fallback report generation failed:', e)
            return False

    # 生成 HTML 报告：渲染 MD 并拷贝 PNG
    env = Environment(
        loader=FileSystemLoader(str(ROOT)),
        autoescape=select_autoescape(['html', 'xml'])
    )
    # 添加自定义过滤器：把换行转为 <br>
    try:
        from jinja2 import Markup
        env.filters['nl2br'] = lambda s: Markup(str(s).replace('\n', '<br/>'))
    except Exception:
        env.filters['nl2br'] = lambda s: str(s).replace('\n', '<br/>')
    env.filters['json_pretty'] = _json_pretty_filter
    # 尝试导入 markdown
    try:
        import markdown as _md
        md_available = True
    except Exception:
        _md = None
        md_available = False

    # prepare md contents map and copy pngs to assets
    out_path = Path(out_path)
    assets_dir = out_path.parent / 'assets'
    assets_dir.mkdir(parents=True, exist_ok=True)

    md_contents = {}
    md_parsed = {}
    for m in md_files:
        try:
            text = Path(m).read_text(encoding='utf-8')
            # store rendered HTML
            if md_available:
                md_contents[str(m)] = _md.markdown(text)
            else:
                md_contents[str(m)] = '<pre>' + text.replace('<', '&lt;') + '</pre>'
            # also parse raw MD to extract headings and code blocks for perf presentation
            parsed = {'raw': text, 'sections': {}, 'code_blocks': []}
            lines = text.splitlines()
            cur_h = None
            buf = []
            in_code = False
            code_buf = []
            code_lang = ''
            for ln in lines:
                if ln.startswith('```'):
                    if not in_code:
                        in_code = True
                        code_lang = ln[3:].strip()
                        code_buf = []
                    else:
                        in_code = False
                        parsed['code_blocks'].append({'lang': code_lang, 'text': '\n'.join(code_buf)})
                    continue
                if in_code:
                    code_buf.append(ln)
                    continue
                m_h = re.match(r'^(#{1,6})\s*(.*)$', ln)
                if m_h:
                    if cur_h and buf:
                        parsed['sections'][cur_h] = '\n'.join(buf).strip()
                    cur_h = m_h.group(2).strip()
                    buf = []
                else:
                    buf.append(ln)
            if cur_h and buf:
                parsed['sections'][cur_h] = '\n'.join(buf).strip()
            md_parsed[str(m)] = parsed
        except Exception:
            md_contents[str(m)] = '<div class="meta">无法读取 MD</div>'


    png_map = {}
    for p in png_files:
        try:
            src = Path(p)
            dest = assets_dir / src.name
            # 统一改为拷贝：避免把原图从原目录移走（原实现会 delete 掉工作区外的源文件）
            if src.exists() and src.resolve() != dest.resolve():
                shutil.copy2(src, dest)
            png_map[str(p)] = str(Path('assets') / src.name)
        except Exception:
            continue

    tpl = env.get_template('report_template.html')
    # 模板使用变量名 func_index
    html = tpl.render(func_index=func_summary, perf_summary=perf_summary,
                      md_contents=md_contents, png_map=png_map, md_parsed=md_parsed,
                      business_summary=business_summary or {},
                      func_modules=func_modules or {})
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding='utf-8')
    print(f"Wrote report: {out_path}")
    return True


def main():
    PYTHON_EXE = os.environ.get("API_TEST_PYTHON_EXE") or sys.executable
    K6_PATH = os.environ.get("K6_EXECUTABLE") or shutil.which("k6") or ""
    OUT_PATH = str(resolve_report_output(REPORT_OUTPUT_PATH))
    RUN_TESTS = not COLLECT_ONLY

    perf_output_root = None
    if os.environ.get("API_TEST_PERF_OUTPUT"):
        perf_output_root = Path(os.environ["API_TEST_PERF_OUTPUT"]).expanduser().resolve()
    elif RUN_TESTS and any(PERFORMANCE_TEST_SELECTION.values()):
        perf_output_root = ROOT / "performance" / "outputs" / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if perf_output_root is not None:
        # 只作为本次性能脚本的输出目录传给子进程；
        # 报告汇总仍扫描所有输出目录，保证未重跑的接口保留各自最新报告。
        print(f"Performance outputs will be written to: {perf_output_root}")

    python_exe = PYTHON_EXE
    functional_files = [
        FUNCTIONAL_TEST_FILES[name]
        for name, enabled in FUNCTIONAL_TEST_SELECTION.items()
        if enabled
    ]
    # search / search_hotspot 是同一入口的兼容别名，all 或重复选择时只执行一次。
    performance_files = list(
        dict.fromkeys(
            PERFORMANCE_TEST_FILES[name]
            for name, enabled in PERFORMANCE_TEST_SELECTION.items()
            if enabled
        )
    )
    if RUN_TESTS:
        if RUN_FUNCTIONAL_TESTS and functional_files:
            run_pytest(python_exe, functional_files)
        else:
            print('No functional interfaces selected; skipping functional tests')
        if RUN_PERFORMANCE_TESTS and performance_files:
            run_performance_scripts(
                python_exe,
                K6_PATH,
                performance_files,
                log_interval_seconds=LOG_INTERVAL_SECONDS,
                perf_output_root=perf_output_root,
            )
        else:
            print('No performance interfaces selected; skipping performance tests')
    else:
        print('Collect-only mode: 跳过测试执行，读取各接口已有最新报告')

    found = collect_outputs()
    jsons = load_json_files(found['.json'])
    responses_index = index_responses(jsons)
    failure_details = index_failure_details(jsons)
    # 尝试从 data 中构建接口索引（优先），否则退回到解析现有 summary JSON
    func_index = build_functional_index()
    if not func_index:
        func_index = summarize_functional(jsons)
    body_checks_by_iface = load_body_checks()
    # attach actual responses to func_index cases where case_id matches
    try:
        for iface, info in func_index.items():
            if info.get('design_only'):
                for c in info.get('cases', []):
                    c['design_only'] = True
                    c['passed'] = None
                    c['result_display'] = '设计用例，本次未执行。'
                info['passed'] = None
                continue
            passed_cnt = 0
            for c in info.get('cases', []):
                cid = c.get('case_id')
                # detect 成功用例：标记需展示/校验的 Result 检测字段（face/nonmotor/person）
                c['detect_field'] = None
                c['inner_code'] = None
                if iface == 'detect.run':
                    _all = body_checks_by_iface.get(iface) or {}
                    _ov = ((_all.get('cases') or {}).get(str(cid)) or {})
                    c['detect_field'] = (_ov.get('success') or {}).get('result_field')
                resps = responses_index.get(str(cid), [])
                # 优先匹配同一 module/action，避免跨接口同 case_id 串扰
                iface_mod, iface_act = (iface.split('.', 1) + [''])[:2] if iface else ('', '')
                scoped = [r for r in resps if (not r.get('module') or r.get('module') == iface_mod) and (not r.get('action') or r.get('action') == iface_act)]
                latest = select_latest_response(scoped or resps)
                c['actual_responses'] = [latest] if latest else []
                c['detect_result_preview'] = None
                if iface == 'detect.run' and latest:
                    try:
                        _resp = (latest.get('body') or {}).get('responses')
                        _ec = (_resp or {}).get('error_code')
                        _inner = ((_resp or {}).get('Result') or {}).get('InnerStatus')
                        c['inner_code'] = _ec if _ec is not None else _inner
                    except Exception:
                        c['inner_code'] = None
                if c.get('detect_field') and latest:
                    try:
                        _resp = (latest.get('body') or {}).get('responses')
                        _val = (_resp or {}).get('Result', {}).get(c['detect_field'])
                        if _val is not None:
                            c['detect_result_preview'] = json.dumps(
                                {"Result": {c['detect_field']: _val}},
                                ensure_ascii=False, indent=2)
                    except Exception:
                        c['detect_result_preview'] = None
                c['passed'] = evaluate_case_pass(c.get('expected'), c['actual_responses'])
                failure_detail = failure_details.get((iface_mod, iface_act), {}).get(str(cid))
                if failure_detail:
                    c['failure_detail'] = failure_detail
                    c['passed'] = False
                c['expected_display'] = format_expected_display(c.get('expected'),
                                                                body_checks_by_iface.get(iface), c)
                c['result_display'] = format_result_display(c, latest)
                if c['passed']:
                    passed_cnt += 1
            if info.get('cases'):
                info['passed'] = passed_cnt
    except Exception:
        pass
    func_index = order_functional_index(func_index)
    verdicts = load_verdicts()
    if verdicts:
        func_index = apply_verdicts(func_index, verdicts)
    perf_summary = summarize_performance(jsons, found['.md'])
    # 每个接口只保留时间最新的一份性能报告
    perf_summary = select_latest_per_interface(perf_summary)
    business_summary = summarize_business(jsons)
    func_modules = group_functional_modules(func_index)

    ok = generate_html(OUT_PATH, func_index, perf_summary, found['.md'], found['.png'],
                       business_summary=business_summary, func_modules=func_modules)
    if not ok:
        sys.exit(2)


if __name__ == '__main__':
    main()
