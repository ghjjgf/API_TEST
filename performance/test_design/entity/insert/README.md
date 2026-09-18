# Entity Insert 性能测试

## 职责
对多个仓库顺序执行实体插入压测，使用真实特征文件并按顺序切换特征。

## 目录内容
- `entity_insert.py`：入口、特征文件和组合报告逻辑。

## 入口
运行 `python3 /home/wx/API_TEST/performance/test_design/entity/insert/entity_insert.py`。

## 输入与输出
- 输入：`ENTITY_FEATURE_FILE`、`ENTITY_FEATURE_POOL_SIZE`、仓库配置和实体模板。
- 输出：`performance/outputs/entity/entity_insert/entity_insert_<timestamp>/`。

## 依赖关系
复用 `common/entity_access.py` 和 `common/ascii_report.py`。

## 备注
默认特征文件为 `/home/wx/testFlow/wx/插库/feature_cache_fp32.txt`；三个 repo 合并为一份报告。
