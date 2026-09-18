# Search Query 功能用例

## 职责
保存搜索查询的 pytest 输入和校验规则。

## 目录内容
- `source_legacy_cases.json`：查询用例。
- `body_checks.json`：响应体判定规则。

## 入口
由 `function_test/search/test_search_query.py` 读取。

## 输入与输出
- 输入：搜索 payload。
- 输出：`function_test/search/results/`。

## 依赖关系
完整执行由 `main.py` 的 `search_query` 选择项控制。
