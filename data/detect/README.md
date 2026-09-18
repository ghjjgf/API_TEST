# Detect 输入数据

## 职责
保存检测业务场景和功能测试的 payload、断言规则。

## 目录内容
- `business/advanced_fields.json`：高级字段业务用例。
- `function/run/source_legacy_cases.json`：检测功能用例。
- `function/run/body_checks.json`：检测响应体校验规则。

## 入口
由 `business/detect/advanced_fields.py`、`function_test/detect/test_detect_run.py` 读取。

## 输入与输出
- 输入：检测请求 payload 和参考图片/URL 配置。
- 输出：测试结果写入对应 `responses/` 或 `results/` 目录。

## 依赖关系
依赖 `business/support.py` 和 `function_test/support.py` 完成 token 展开。
