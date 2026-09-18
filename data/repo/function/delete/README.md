# Repo Delete 功能用例

## 职责
保存仓库 `delete` 动作的输入定义。

## 目录内容
- `source_legacy_cases.json`：用例列表。
- `body_checks.json`：响应体校验。

## 入口
由 `function_test/repo/test_repo_delete.py` 读取。

## 输入与输出
- 输入：仓库 payload 和校验规则。
- 输出：`function_test/repo/results/`。

## 依赖关系
依赖功能测试夹具和 Repo API 适配器。
