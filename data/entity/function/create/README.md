# Entity Create 功能用例

## 职责
保存实体 `create` 动作的输入定义。

## 目录内容
- `source_legacy_cases.json`：用例列表。
- `body_checks.json`：成功/失败响应校验。

## 入口
由实体 `create` 功能测试或后续设计实现读取。

## 输入与输出
- 输入：实体 payload 和校验规则。
- 输出：执行后输出到 `function_test/entity/results/`。

## 依赖关系
依赖 `function_test/support.py` 和 `api/api.py`。
