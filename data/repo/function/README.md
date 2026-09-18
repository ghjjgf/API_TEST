# Repo 功能用例

## 职责
按仓库动作拆分输入定义。

## 目录内容
- `create/`、`get/`、`list/`、`delete/` 为可执行用例。
- `update/` 为设计输入。

## 入口
由仓库功能测试读取。

## 输入与输出
- 输入：各动作的 `source_legacy_cases.json` 和适用的 `body_checks.json`。
- 输出：`function_test/repo/results/`。

## 依赖关系
用例 token 由 `function_test/support.py` 展开。
