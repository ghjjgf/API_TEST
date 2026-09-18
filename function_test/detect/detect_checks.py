"""detect 接口响应体的判定规则（功能测试与 HTML 报告共用）。

用例可以在 `expected.detect_any_of` 中声明"任一命中即通过"的字段级校验，
例如：

    "expected": {
      "status_code": 200,
      "detect_any_of": [
        {"path": "Result.Faces", "non_empty": true},
        {"path": "Result.NonMotorVehicles[].HasFace", "equals": true},
        {"path": "Result.NonMotorVehicles[].Passengers", "non_empty": true},
        {"path": "Result.Pedestrian[].Face", "non_empty": true}
      ]
    }

路径语法：
- ``A.B``      普通字段
- ``A.B[]``    对列表逐元素展开（若该字段是 dict 则退化为单元素）
- ``A.B[].C``  列表逐元素后继续取子字段

判定语义：
- ``detect_any_of``：满足任意一条即通过
  - ``non_empty``（默认）：字段存在且有值（字符串非空、列表/字典非空、数字/布尔非 None）
  - ``equals``：字段等于给定值（如 HasFace 是否为 true）
- ``detect_all_empty``：列表中每个路径都"没有值"（字段缺失或空列表/空串）才通过，例如：

    "expected": {
      "status_code": 200,
      "detect_all_empty": ["Result.Faces", "Result.NonMotorVehicles", "Result.Pedestrian"]
    }
"""

from __future__ import annotations

from typing import Any


# 按路径取出所有候选值（支持 [] 列表展开），找不到时返回空列表。
def values_at(body: Any, path: str) -> list[Any]:
    if body is None or not path:
        return []
    current: list[Any] = [body]
    for raw_part in str(path).split("."):
        part = raw_part.strip()
        if not part:
            continue
        wildcard = part.endswith("[]")
        key = part[:-2] if wildcard else part
        next_values: list[Any] = []
        for node in current:
            if isinstance(node, dict):
                if key not in node:
                    continue
                value = node.get(key)
            elif isinstance(node, list):
                # 允许路径中间直接跨列表（等价于隐式 []）
                for item in node:
                    if isinstance(item, dict) and key in item:
                        value = item.get(key)
                        if wildcard and isinstance(value, list):
                            next_values.extend(value)
                        else:
                            next_values.append(value)
                continue
            else:
                continue
            if wildcard:
                if isinstance(value, list):
                    next_values.extend(value)
                else:
                    next_values.append(value)
            else:
                next_values.append(value)
        current = next_values
        if not current:
            return []
    return current


# 判断字段值是否"有值"。
def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


# 对单条规则求值；返回 True/False，路径不存在时返回 False。
def evaluate_rule(body: Any, rule: dict[str, Any]) -> bool:
    if not isinstance(rule, dict):
        return False
    path = str(rule.get("path") or "")
    if not path:
        return False
    candidates = values_at(body, path)
    if not candidates:
        return False
    if "equals" in rule:
        expected = rule.get("equals")
        return any(value == expected for value in candidates)
    if "exists" in rule and not rule.get("exists"):
        return all(value is None for value in candidates)
    # non_empty 为默认语义
    return any(is_present(value) for value in candidates)


# 求值用例里的"任一命中即通过"规则；未声明规则时返回 None（表示不做字段级判定）。
def evaluate_detect_any_of(expected: Any, body: Any) -> bool | None:
    if not isinstance(expected, dict):
        return None
    rules = expected.get("detect_any_of")
    if not rules:
        return None
    if not isinstance(rules, list):
        return None
    if body is None:
        return False
    return any(evaluate_rule(body, rule) for rule in rules)


# 求值"全部字段都为空"规则；未声明规则时返回 None。
def evaluate_detect_all_empty(expected: Any, body: Any) -> bool | None:
    if not isinstance(expected, dict):
        return None
    paths = expected.get("detect_all_empty")
    if not paths:
        return None
    if isinstance(paths, str):
        paths = [paths]
    if not isinstance(paths, list):
        return None
    if body is None:
        return False
    for path in paths:
        candidates = values_at(body, str(path))
        if any(is_present(value) for value in candidates):
            return False
    return True


# 综合求值用例声明的字段级规则（any_of 与 all_empty 同时存在时都要满足）。
def evaluate_detect_expectations(expected: Any, body: Any) -> bool | None:
    verdicts = [
        verdict
        for verdict in (
            evaluate_detect_any_of(expected, body),
            evaluate_detect_all_empty(expected, body),
        )
        if verdict is not None
    ]
    if not verdicts:
        return None
    return all(verdicts)


# 生成失败时的可读诊断（列出每条规则的路径与实测值）。
def describe_detect_any_of(expected: Any, body: Any, *, limit: int = 3) -> str:
    if not isinstance(expected, dict):
        return ""
    rules = expected.get("detect_any_of")
    if not isinstance(rules, list) or not rules:
        return ""
    lines: list[str] = []
    empty_paths = expected.get("detect_all_empty")
    if isinstance(empty_paths, str):
        empty_paths = [empty_paths]
    if isinstance(empty_paths, list):
        for path in empty_paths:
            candidates = values_at(body, str(path))
            shown = candidates[:limit]
            rendered = ", ".join(_brief(value) for value in shown) if shown else "未找到该字段"
            lines.append(f"  - {path}（应为空）实测: {rendered}")
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        path = str(rule.get("path") or "")
        candidates = values_at(body, path)
        shown = candidates[:limit]
        rendered = ", ".join(_brief(value) for value in shown) if shown else "未找到该字段"
        expectation = (
            f"equals {rule['equals']!r}" if "equals" in rule else "非空"
        )
        lines.append(f"  - {path}（{expectation}）实测: {rendered}")
    return "\n".join(lines)


# 把值压缩成便于展示的短字符串。
def _brief(value: Any) -> str:
    text = value if isinstance(value, str) else repr(value)
    text = str(text).replace("\n", " ")
    return text if len(text) <= 48 else text[:45] + "..."


__all__ = [
    "describe_detect_any_of",
    "evaluate_detect_all_empty",
    "evaluate_detect_any_of",
    "evaluate_detect_expectations",
    "evaluate_rule",
    "is_present",
    "values_at",
]
