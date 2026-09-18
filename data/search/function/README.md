# Search 功能用例

## 职责
汇总搜索查询功能测试输入。

## 目录内容
- `query/source_legacy_cases.json`：查询用例。
- `query/body_checks.json`：响应校验。

## 入口
由 `function_test/search/test_search_query.py` 读取和汇总。

## 输入与输出
- 输入：搜索 payload。
- 输出：`function_test/search/results/`。

## 依赖关系
依赖 SearchApi 和功能测试轮询工具。
