# Entity Delete 闭环实现

## 职责
实现实体删除压测的配置、插入、删除、编排和报告写出。

## 目录内容
- `config.py`：默认配置和 payload 加载。
- `insert_stage.py`：插入阶段。
- `delete_stage.py`：删除阶段。
- `repo_api.py`：仓库生命周期接口。
- `orchestrator.py`：闭环编排。
- `reporting.py`：报告包写出。

## 入口
由 `entity_delete.py` 导入，不单独执行。

## 输入与输出
- 输入：仓库 ID、实体模板、并发梯度和超时。
- 输出：删除闭环结果和报告文件。

## 依赖关系
是 `entity_delete.py` 的内部实现层。
