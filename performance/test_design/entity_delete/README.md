# Entity Delete 闭环压测

## 职责
先插入待删实体，再按并发梯度执行删除，验证完整闭环并输出统一 ASCII 报告。

## 目录内容
- `entity_delete.py`：入口。
- `closed_loop/`：配置、插入、删除、编排和报告实现。

## 入口
运行 `python3 /home/wx/API_TEST/performance/test_design/entity_delete/entity_delete.py`。

## 输入与输出
- 输入：`closed_loop/config.py` 的默认仓库和实体模板。
- 输出：`performance/outputs/entity/entity_delete/entity_delete_<timestamp>/`。

## 依赖关系
依赖 `aiohttp`、仓库 API 和 `common/ascii_report.py`。

## 备注
支持单个或多个现有 repo；报告格式与 entity_get、entity_insert 保持一致。
