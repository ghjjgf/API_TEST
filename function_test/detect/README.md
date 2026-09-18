# Detect 功能测试

## 职责
执行 detect 接口的真实 pytest 用例。

## 目录内容
- `test_detect_run.py`
- `detect_checks.py`

## 入口
由 `main.py` 选择 `detect` 相关功能接口时执行；也可直接指定本目录测试文件。

## 输入与输出
- 输入：`data/detect/function/run/` 的用例和校验规则。
- 输出：`function_test/detect/results/`。

## 依赖关系
依赖功能测试夹具、API 适配器和共享响应模型。
