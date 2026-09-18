# Entity Get 性能测试

## 职责
对多个仓库顺序执行实体 GET 压测，并把结果汇总成一个 ASCII 表格报告。

## 目录内容
- `entity_get.py`：入口和组合报告逻辑。

## 入口
运行 `python3 /home/wx/API_TEST/performance/test_design/entity/get/entity_get.py`。

## 输入与输出
- 输入：`DEFAULT_TARGET_REPO_IDS` 和 `performance/data/entity/entity.py`。
- 输出：`performance/outputs/entity/entity_get/entity_get_<timestamp>/`。

## 依赖关系
复用 `common/entity_access.py` 和 `common/ascii_report.py`。

## 备注
三个 repo 不再分别出报告，最终 HTML 会读取合并后的 Markdown。
