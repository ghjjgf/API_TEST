# 性能公共层

## 职责
提供实体访问压测的配置、k6 运行时、事件解析和统一 ASCII 报告。

## 目录内容
- `entity_access.py`：实体访问 config、k6 脚本、seed、统计、报告。
- `ascii_report.py`：多仓库报告的统一 ASCII 渲染器。

## 入口
被 entity get/insert/delete 等性能入口导入，不单独执行。

## 输入与输出
- 输入：各入口的 `BenchmarkConfig` 和事件结果。
- 输出：`entity_*_report.md` 与 `failures.json`。

## 依赖关系
是实体类性能入口的共享依赖。
