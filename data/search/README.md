# Search 输入数据

## 职责
保存搜索接口功能测试和业务场景输入。

## 目录内容
- `function/query/`：搜索功能用例。
- `business/`：业务搜索场景的说明和扩展位置。

## 入口
由 `function_test/search/` 和 `business/search/` 读取。

## 输入与输出
- 输入：搜索 payload、include 特征和 body_checks。
- 输出：对应 `results/` 或 `responses/`。

## 依赖关系
依赖 `api/api.py` 的 SearchApi。
