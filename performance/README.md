# 性能测试

## 职责
使用 Python 编排、k6 发压和 Python 汇总的方式验证接口性能，并保存 Markdown/JSON 产物。

## 目录内容
- `config/`：性能环境配置。
- `data/`：各接口样例 payload。
- `test_design/`：压测入口和公共实现。
- `outputs/`：历史运行产物。

## 入口
推荐通过 `python3 /home/wx/API_TEST/main.py`，在顶部 `PERFORMANCE_TEST_SELECTION` 中选择接口；也可直接运行单个入口。

## 输入与输出
- 输入：`performance/data/**`、`performance/config/config.py` 和环境变量。
- 输出：`performance/outputs/**`，最终 HTML 汇总到 `outputs/report.html`。

## 依赖关系
依赖 k6、aiohttp 以及 `performance/test_design/common/` 共享实现。

## 备注
当前可选项：`search`、`entity_insert`、`entity_get`、`entity_delete`、`detect`。
