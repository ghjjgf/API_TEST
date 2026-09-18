# 核心能力层

## 职责
提供所有测试模块共享的异步 HTTP、响应归档、结果汇总和通用工具。

## 目录内容
- `http_client.py`：aiohttp 异步客户端。
- `models.py`：响应与汇总数据模型。
- `response_store.py`：响应 JSON 归档。
- `result_collector.py`：通过/失败汇总。
- `utils.py`：JSON、时间戳和轮询工具。

## 入口
由功能测试、业务测试和性能编排模块导入，不单独执行。

## 输入与输出
- 输入：接口请求参数、响应记录和输出目录。
- 输出：响应归档 JSON、summary JSON 和中间记录。

## 依赖关系
位于 `api/` 和业务/测试模块之间的共享底层。
