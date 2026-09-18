# Repo 输入数据

## 职责
保存仓库功能测试的用例定义和响应校验规则。

## 目录内容
- `function/create/`、`get/`、`list/`、`delete/`、`update/` 子目录。

## 入口
由 `function_test/repo/` 下的 pytest 用例读取。

## 输入与输出
- 输入：仓库 payload、用例字段和 body_checks。
- 输出：`function_test/repo/results/`。

## 依赖关系
依赖 `function_test/support.py` 和 `api/api.py`。
