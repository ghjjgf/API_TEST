# 测试入口

## 统一入口

```bash
python3 /home/wx/API_TEST/main.py
```

不再使用命令行参数。运行范围和是否只收集报告，统一在 `main.py` 顶部配置区修改。

## 全量执行

```python
COLLECT_ONLY = False
RUN_FUNCTIONAL_TESTS = True
RUN_PERFORMANCE_TESTS = True
```

并把 `FUNCTIONAL_TEST_SELECTION`、`PERFORMANCE_TEST_SELECTION` 中要执行的接口设为 `True`。

## 只更新 HTML

```python
COLLECT_ONLY = True
```

此时不执行功能/性能测试，只读取已有结果并更新：

```text
/home/wx/API_TEST/outputs/report.html
```

## 只执行功能接口

```python
COLLECT_ONLY = False
RUN_FUNCTIONAL_TESTS = True
RUN_PERFORMANCE_TESTS = False
FUNCTIONAL_TEST_SELECTION = {
    'repo_create': True,
    'repo_get': False,
    'repo_list': False,
    'repo_delete': False,
    'entity_create': False,
    'entity_get': False,
    'entity_delete': False,
    'search_query': False,
    'detect_run': False,
}
```

## 只执行性能接口

```python
COLLECT_ONLY = False
RUN_FUNCTIONAL_TESTS = False
RUN_PERFORMANCE_TESTS = True
PERFORMANCE_TEST_SELECTION = {
    'search': True,
    'entity_insert': False,
    'entity_get': False,
    'entity_delete': False,
    'detect': False,
}
```

## 接口选择项

功能：`repo_create`、`repo_get`、`repo_list`、`repo_delete`、`entity_create`、`entity_get`、`entity_delete`、`search_query`、`detect_run`。

性能：`search`、`entity_insert`、`entity_get`、`entity_delete`、`detect`。

Search 已合并基线与热点库逻辑，因此只需要一个 `search` 选择项。
