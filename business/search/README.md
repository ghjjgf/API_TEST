# Search 业务场景

## 职责
验证多库、包含阈值、多数据组合和版本类型约束下的搜索行为。

## 目录内容
- `include_threshold.py`：include 阈值。
- `muldata.py`：多数据组合。
- `multi_repo.py`：多仓库组合。
- `version_type_check.py`：版本类型校验。
- `_scenario_runtime.py`：搜索场景运行时。
- `_scenario_support.py`：搜索结果提取和汇总。

## 入口
按需执行单个脚本，例如 `python3 /home/wx/API_TEST/business/search/multi_repo.py`。

## 输入与输出
- 输入：业务默认配置、`data/common/reference_feature.b64` 和场景内特征。
- 输出：`business/search/responses/<scenario>/`。

## 依赖关系
依赖 Search/Repo/Entity API 适配器和服务端索引可见性。
