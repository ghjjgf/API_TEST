# Entity 性能测试

## 职责
统一管理实体插入和读取两类性能入口。

## 目录内容
- `insert/`：Entity Insert。
- `get/`：Entity Get。

## 入口
从 `insert/entity_insert.py` 或 `get/entity_get.py` 执行。

## 输入与输出
- 输入：实体样例和运行时特征文件/仓库配置。
- 输出：`performance/outputs/entity/**`。

## 依赖关系
两个入口共享 `performance/test_design/common/entity_access.py`。
