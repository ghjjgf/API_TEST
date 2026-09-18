# Entity 功能用例

## 职责
汇总实体 create/get/delete/update 的输入和校验规则。

## 目录内容
- `create/`：创建实体。
- `get/`：读取实体。
- `delete/`：删除实体。
- `update/`：设计输入，当前不执行。

## 入口
由 `function_test/entity/` 下的 pytest 用例读取。

## 输入与输出
- 输入：实体 payload 和 body_checks。
- 输出：`function_test/entity/results/`。

## 依赖关系
update 目录当前仅保留设计输入，测试入口按需启用。
