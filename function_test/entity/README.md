# Entity 功能测试

## 职责
执行 entity 接口的真实 pytest 用例。

## 目录内容
- `test_entity_create.py`
- `test_entity_get.py`
- `test_entity_delete.py`
- `post_checks.py`

## 入口
由 `main.py` 选择 `entity` 相关功能接口时执行；也可直接指定本目录测试文件。

## 输入与输出
- 输入：`data/entity/function/` 的用例和校验规则。
- 输出：`function_test/entity/results/`。

## 依赖关系
依赖功能测试夹具、API 适配器和共享响应模型。
