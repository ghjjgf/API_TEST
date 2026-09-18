# Entity 性能样例

## 职责
提供实体创建、读取、更新和删除的基础 payload。

## 目录内容
- `entity.py`：`SAMPLE_ENTITY`、`SAMPLE_GET_ENTITY`、`SAMPLE_UPDATE_ENTITY`、`SAMPLE_DELETE_ENTITY`。

## 入口
由实体性能入口和公共实体访问模块导入。

## 输入与输出
- 输入：实体 payload 字典。
- 输出：不直接生成报告。

## 依赖关系
默认特征仅为样例，entity_insert 实时使用特征文件。
