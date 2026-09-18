# Detect 性能样例

## 职责
提供检测性能测试的多种 payload 模板。

## 目录内容
- `detect.py`：单目标、多目标、face、file 等样例。

## 入口
由 `performance/test_design/detect/detect.py` 导入。

## 输入与输出
- 输入：检测请求字段和参考图片/文件配置。
- 输出：不直接生成报告。

## 依赖关系
依赖检测服务可接受的 payload 格式。
