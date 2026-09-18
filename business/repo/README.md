# Repo 业务场景

## 职责
验证仓库创建、删除、容量、复制、轮转、预过滤和配置回显等业务规则。

## 目录内容
- `create_delete_repo.py`：创建并确认 READY 后删除。
- `capacity.py`：容量上限和溢出。
- `replications.py`：复制数上调/下调。
- `rotate.py`：Rotate 轮转行为。
- `timerDeleteDays.py`：删除策略配置回显。
- `useFeatureIDMap.py`：特征 ID Map 配置。
- `prefilter.py`：预过滤与搜索结果约束。
- `_scenario_support.py`：仓库场景公共轮询和结果记录。

## 入口
按需执行单个脚本，例如 `python3 /home/wx/API_TEST/business/repo/capacity.py`。

## 输入与输出
- 输入：来自 `data/repo/business/` 或 `business/support.py` 默认配置。
- 输出：`business/repo/responses/<scenario>/`。

## 依赖关系
依赖 Repo/Entity/Search API 适配器和公共业务运行时。
