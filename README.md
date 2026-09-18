# API_TEST

## 职责
`API_TEST` 是接口功能、业务链路和性能压测的统一工作区。所有可执行测试由顶层 `main.py` 编排，最终 HTML 统一写入 `outputs/report.html`。

## 目录内容
- `api/`：Repo、Entity、Search、Detect 接口适配层。
- `core/`：异步 HTTP 客户端、响应模型、结果收集和通用工具。
- `config/`：服务地址、端口和请求超时等全局常量。
- `function_test/`：基于 pytest 的接口功能测试。
- `business/`：跨接口业务场景测试。
- `performance/`：k6 性能测试编排、样例数据、运行结果和 ASCII 报告。
- `data/`：功能测试与业务测试的输入用例、body_checks 和参考特征。
- `docs/`：架构、入口和文件索引。
- `outputs/`：当前最终 HTML 报告。
- `assets/`：报告静态资源。
- `archive/`：历史备份，不参与当前测试执行。

## 入口
在 `/home/wx/API_TEST/main.py` 顶部配置：

```python
COLLECT_ONLY = False
RUN_FUNCTIONAL_TESTS = True
RUN_PERFORMANCE_TESTS = True
FUNCTIONAL_TEST_SELECTION = {...}
PERFORMANCE_TEST_SELECTION = {...}
```

运行：

```bash
python3 /home/wx/API_TEST/main.py
```

`COLLECT_ONLY=True` 时不执行测试，只汇总已有结果并更新最终 HTML。

## 输入与输出
- 输入：`data/**`、`performance/data/**`、各模块配置与已有运行结果。
- 输出：功能结果、业务结果、性能原始结果以及 `/home/wx/API_TEST/outputs/report.html`。

## 依赖关系
- 功能测试：`function_test -> api -> core -> 服务端`。
- 业务测试：`business -> api -> core -> 服务端`。
- 性能测试：`main.py -> performance/test_design -> performance/data -> k6 -> 服务端`。
- 报告汇总：`main.py -> outputs/report.html`。

## 备注
历史入口、旧报告和旧日志已归档到 `archive/`；当前目录只保留可执行入口和有效输入。
