# Entity 业务用例

## 职责
保存实体相关业务场景的静态配置。

## 目录内容
- `compare_version_.json`：版本比较场景。
- `entity_repo_version_ctl.json`：仓库版本控制场景。
- `readd_entity.json`：实体重读场景。

## 入口
由 `business/entity/*.py` 读取。

## 输入与输出
- 输入：场景级 repo/entity 配置。
- 输出：对应 `business/entity/responses/<scenario>/`。

## 依赖关系
依赖 `business/support.py` 做 token 展开和运行时归档。
