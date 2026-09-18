# Detect Run 功能用例

## 职责
保存 `detect.run` 接口的用例和 body_checks。

## 目录内容
- `source_legacy_cases.json`：用例列表。
- `body_checks.json`：成功/失败响应的通用断言。

## 入口
由 `function_test/detect/test_detect_run.py` 读取。

## 输入与输出
- 输入：检测 payload。
- 输出：`function_test/detect/results/`。

## 依赖关系
由 `main.py` 汇总报告时一并读取。
