# Search 业务输入

## 职责
说明搜索业务场景的数据位置。

## 目录内容
- 当前场景数据主要由 `business/support.py` 中的 `DEFAULT_BUSINESS_CONFIGS` 提供。
- 需要独立用例文件时放在本目录。

## 入口
由 `business/search/` 场景读取或在运行时生成。

## 输入与输出
- 输入：仓库、实体、特征和搜索参数组合。
- 输出：`business/search/responses/<scenario>/`。

## 依赖关系
依赖 `business/search/_scenario_runtime.py` 和 `_scenario_support.py`。
