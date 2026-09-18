# 性能测试实现

## 职责
组织各接口的 k6 压测入口、公共统计和安全阀逻辑。

## 目录内容
- `common/`：ASCII 报告和实体访问公共层。
- `search/`：Search 基线与热点库混合负载。
- `entity/insert/`：Entity 插入。
- `entity/get/`：Entity 读取。
- `entity_delete/`：Entity Delete 闭环。
- `detect/`：Detect 压测。

## 入口
通过 `main.py` 选择接口，或直接运行对应入口脚本。

## 输入与输出
- 输入：`performance/data/`、`performance/config/config.py` 和运行环境变量。
- 输出：`performance/outputs/**`，由 `main.py` 汇总到 `outputs/report.html`。

## 依赖关系
所有入口遵循 Python 编排 + k6 执行 + Python 解析的链路。

## 备注
新接口优先复用 `common/entity_access.py` 和 `common/ascii_report.py`，避免复制报告格式。
