# API_TEST 架构

## 1. 总览

```text
main.py
  ├─ 功能测试 -> function_test/ -> api/ -> core/ -> 服务端
  ├─ 业务测试 -> business/ -> api/ -> core/ -> 服务端
  └─ 性能测试 -> performance/test_design/ -> performance/data/ -> k6 -> 服务端
                                      └─ performance/outputs/
main.py -> outputs/report.html
```

`main.py` 是唯一推荐入口。接口范围在文件顶部配置，不再使用 `--functional`、`--performance` 或 `--collect-only` 参数。

## 2. 分层

| 层级 | 目录/文件 | 职责 |
|---|---|---|
| 入口层 | `main.py` | 选择接口、执行测试、汇总结果、生成 HTML |
| 适配层 | `api/` | Repo、Entity、Search、Detect 请求封装 |
| 核心层 | `core/` | HTTP、模型、响应归档、结果收集、轮询 |
| 配置层 | `config/` | 服务地址、端口、超时 |
| 功能测试层 | `function_test/` | pytest 用例和夹具 |
| 业务测试层 | `business/` | 跨接口业务场景 |
| 性能实现层 | `performance/test_design/` | Python + k6 压测编排 |
| 性能数据层 | `performance/data/` | payload 样例和生成数据 |
| 输入数据层 | `data/` | 功能/业务用例与校验规则 |
| 产物层 | `outputs/`、`performance/outputs/` | 最终 HTML 和原始运行结果 |
| 文档层 | `docs/`、各目录 `README.md` | 架构、入口和维护说明 |
| 归档层 | `archive/` | 旧入口、旧报告、旧日志，不参与执行 |

## 3. 功能与业务测试

功能测试：

```text
data/<module>/function/.../source_legacy_cases.json
  -> function_test/<module>/test_*.py
  -> api/api.py
  -> core/http_client.py
  -> function_test/<module>/results/
```

业务测试：

```text
data/<module>/business/*.json 或 business/support.py 默认配置
  -> business/<module>/*.py
  -> api/api.py
  -> business/<module>/responses/<scenario>/
```

功能选项目标是最小接口动作；业务场景目标是跨接口业务约束。两者都只通过 `api/` 访问服务端。

## 4. 性能测试

性能测试统一采用：

```text
Python 构造配置和 case
  -> 生成 k6 运行时脚本
  -> k6 发压
  -> Python 解析事件并按测量窗口统计
  -> Markdown/JSON 结果
  -> main.py 汇总到 outputs/report.html
```

入口：

| 接口 | 文件 |
|---|---|
| Search | `performance/test_design/search/search.py` |
| Entity Insert | `performance/test_design/entity/insert/entity_insert.py` |
| Entity Get | `performance/test_design/entity/get/entity_get.py` |
| Entity Delete | `performance/test_design/entity_delete/entity_delete.py` |
| Detect | `performance/test_design/detect/detect.py` |

实体类报告统一复用 `performance/test_design/common/ascii_report.py`，避免不同入口的表格格式漂移。

## 5. Search 热点库逻辑

Search 默认配置复用 `search.py` 顶部旧 `DEFAULT_*` 常量：并发 `32/64/128`、`max_candidates=1/20/100/500`、`include_threshold=0.7`，所有 case 均使用同一并发梯度；baseline 和 hotspot 均使用 `20s` 预热 + `180s` 统计。

Search 默认采用 staged 策略：

```text
全部 baseline case
  -> 全部 baseline 完成后
  -> 全部 hotspot case
  -> 合并为一份标准对比报告
```

可通过 `SEARCH_HOTSPOT_PHASE_POLICY=inline` 恢复旧的同 case 连续执行模式。

默认写入策略：

- 每库 `32` 个 insert worker、`32` 个 delete worker。
- 插入特征按 `feature_cache_fp32.txt` 顺序切换。
- 清理并发由 `SEARCH_HOTSPOT_CLEANUP_CONCURRENCY` 控制，默认 `32`。
- 默认不额外等待；只有显式设置 `SEARCH_HOTSPOT_PHASE_GAP_SECONDS` 时才增加阶段间隔。
- NPU 库默认通过 `SEARCH_NPU_REPOSITORIES` 配置，当前默认 `3kwfacerepo_test,1kwfacerepo_test`；NPU 单库及包含 NPU 的组合只执行 baseline，hotspot 指标为 `N/A`。
- 多 NPU 库组合默认将并发限制为 `32`，可通过 `SEARCH_NPU_MULTI_REPO_CONCURRENCY_CAP` 调整。
- 多 NPU 组合仅执行并发 `32`。

## 6. 输出约定

```text
function_test/<module>/results/                         功能结果
business/<module>/responses/<scenario>/                 业务结果
performance/outputs/<run>/                              性能原始结果
performance/outputs/**/*_report.md                      性能 Markdown
/home/wx/API_TEST/outputs/report.html                   最终 HTML
```

## 7. 维护原则

1. 新增功能接口：先扩展 `data/` 和 `function_test/`，再在 `main.py` 注册选择项。
2. 新增业务链路：复用 `business/support.py`，不要复制客户端和归档逻辑。
3. 新增性能接口：优先复用 `performance/test_design/common/`，报告使用 ASCII 渲染器。
4. 删除代码前先做全局引用检查；历史实现放入 `archive/legacy/`。
5. 不把测试运行产物写回仓库根目录。
