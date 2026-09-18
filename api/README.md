# API 适配层

## 职责
集中封装 Repo、Entity、Search、Detect 四类接口的 HTTP 调用，业务和测试模块不直接拼接请求细节。

## 目录内容
- `api.py`：四个异步 API 适配器。
- `__init__.py`：包标识。

## 入口
由 `function_test/`、`business/` 等上层模块导入，不单独执行。

## 输入与输出
- 输入：上游传入 payload、路径和请求元数据；HTTP 客户端由 `core/http_client.py` 提供。
- 输出：返回 `HttpResponseRecord` 或调用方期望的响应对象。

## 依赖关系
依赖 `core/http_client.py`；被功能测试和业务场景复用。
