# Entity 业务场景

## 职责
验证实体版本、仓库版本控制和重读流程。

## 目录内容
- `compare_version.py`：比较实体版本。
- `entity_repo_version_ctl.py`：仓库版本控制配置。
- `readd_entity.py`：实体重读/恢复流程。

## 入口
按需执行单个脚本，例如 `python3 /home/wx/API_TEST/business/entity/compare_version.py`。

## 输入与输出
- 输入：`data/entity/business/*.json` 和公共参考特征。
- 输出：`business/entity/responses/<scenario>/`。

## 依赖关系
依赖 `business/support.py`、Entity/Repo API 适配器。
