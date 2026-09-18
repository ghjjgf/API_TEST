# Search 性能测试

## 职责
将 Search 的 baseline case 与 hotspot case 分阶段执行，并合并为一份标准对比报告。

## 目录内容
- `search.py`：唯一 Search 性能入口。

## 入口
运行 `python3 /home/wx/API_TEST/performance/test_design/search/search.py`，或通过 `main.py` 选择 `search`。

默认 Search 配置以 `search.py` 顶部旧 `DEFAULT_*` 常量为准：

```text
仓库组合：DEFAULT_REPOSITORIES_VALUES
并发：DEFAULT_CONCURRENCY_VALUES = [32, 64, 128]
max_candidates：DEFAULT_MAX_CANDIDATES_VALUES = [1, 20, 100, 500]
include_threshold：DEFAULT_INCLUDE_THRESHOLD_VALUES = [0.7]
测量窗口：20s 预热 + 180s 统计
```

NPU 多库组合不再做并发覆盖，所有 Search case 统一使用 32/64/128。

默认阶段策略：

```text
全部 baseline case
  -> 全部 baseline 完成后
  -> 全部 hotspot case
  -> 合并为 15 列 Search 对比表
```

## 输入与输出
- 输入：仓库组合、`max_candidates`、`include_threshold`、特征文件和服务地址。
- 阶段策略：`SEARCH_HOTSPOT_PHASE_POLICY` 默认 `staged`，表示全部 baseline 完成后再执行全部 hotspot；`SEARCH_HOTSPOT_PHASE_GAP_SECONDS` 默认 `0`，仅在显式设置时才增加额外等待。
- NPU 库：默认 `3kwfacerepo_test,1kwfacerepo_test` 只执行 baseline；包含 NPU 库的组合也不会执行 hotspot。
- 多 NPU 库组合并发上限：默认 `32`，可通过 `SEARCH_NPU_MULTI_REPO_CONCURRENCY_CAP` 调整。
- 输出：`performance/outputs/search_hotspot_<timestamp>/`，最终 HTML 读取报告和时序数据。

## 依赖关系
依赖 k6、aiohttp、`common/ascii_report.py` 和共享实体访问工具。

## 备注
默认为每库 32 insert + 32 delete worker；多 NPU 组合只保留并发 32；清理并发由 `SEARCH_HOTSPOT_CLEANUP_CONCURRENCY` 控制。

将 `SEARCH_HOTSPOT_PHASE_POLICY` 设置为 `inline` 可恢复旧的同 case 连续 baseline/hotspot 模式。

NPU 库可通过环境变量 `SEARCH_NPU_REPOSITORIES` 覆盖，默认值为：

```text
3kwfacerepo_test,1kwfacerepo_test
```
