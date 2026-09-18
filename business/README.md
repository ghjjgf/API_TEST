# 业务场景测试

## 职责
按真实业务流程串联多个接口，验证仓库、实体、搜索和检测的组合行为。

## 目录内容
- `repo/`：仓库配置和生命周期场景。
- `entity/`：实体版本和重读场景。
- `search/`：搜索组合场景。
- `detect/`：检测高级字段场景。
- `support.py`：运行时构建、配置加载和结果汇总公共层。

## 入口
每个场景脚本可作为独立入口执行；统一汇总仍由 `/home/wx/API_TEST/main.py` 完成。

## 输入与输出
- 输入：`data/**/business/*.json` 和 `business/support.py` 中的默认配置。
- 输出：各场景同级的 `responses/<scenario>/`，并可由最终 HTML 汇总。

## 依赖关系
依赖 `api/`、`core/` 和服务端；不依赖 pytest。

## 备注
当前不支持旧 CLI 参数。运行范围在 `main.py` 顶部选择。
