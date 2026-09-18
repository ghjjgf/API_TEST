# 功能测试

## 职责
使用 pytest 对 Repo、Entity、Search、Detect 接口执行黑盒功能验证。

## 目录内容
- `repo/`：仓库测试。
- `entity/`：实体测试。
- `search/`：搜索测试。
- `detect/`：检测测试。
- `conftest.py`：API 夹具和资源清理。
- `support.py`：用例加载、响应归档和轮询。

## 入口
推荐通过 `python3 /home/wx/API_TEST/main.py` 运行；运行前在顶部选择功能接口。

## 输入与输出
- 输入：`data/**/function/**/source_legacy_cases.json` 和 `body_checks.json`。
- 输出：`function_test/<module>/results/` 的 summary、verdict 和响应归档。

## 依赖关系
依赖 `api/`、`core/`、`config/`；不直接依赖业务场景模块。

## 备注
单接口选择项：`repo_create`、`repo_get`、`repo_list`、`repo_delete`、`entity_create`、`entity_get`、`entity_delete`、`search_query`、`detect_run`。
