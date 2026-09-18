# Detect 功能输入

## 职责
保存检测接口 pytest 功能用例及其校验规则。

## 目录内容
- `run/source_legacy_cases.json`：检测功能用例。
- `run/body_checks.json`：响应体判定规则。

## 入口
由 `function_test/detect/test_detect_run.py` 和 `main.py` 读取。

## 输入与输出
- 输入：检测请求 payload。
- 输出：`function_test/detect/results/`。

## 依赖关系
依赖 `function_test/detect/detect_checks.py` 解析内部检测结果。
