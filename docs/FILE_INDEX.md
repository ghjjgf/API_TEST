# 文件索引

## 入口与核心

```text
main.py                         统一执行与 HTML 汇总入口
config/settings.py              全局服务地址与超时
api/api.py                      Repo/Entity/Search/Detect 适配层
core/http_client.py             异步 HTTP 客户端
core/models.py                  响应与汇总模型
core/response_store.py          响应归档
core/result_collector.py        通过/失败汇总
core/utils.py                   JSON、时间戳、轮询工具
```

## 功能测试

```text
function_test/conftest.py                   pytest 夹具和资源生命周期
function_test/support.py                    用例加载与公共断言
function_test/repo/                         仓库功能测试
function_test/entity/                       实体功能测试
function_test/search/                       搜索功能测试
function_test/detect/                       检测功能测试，含内部结果解析
```

## 业务测试

```text
business/support.py                         业务运行时与配置加载
business/repo/                              仓库生命周期和配置场景
business/entity/                            实体版本和重读场景
business/search/                            多库、阈值、多数据、版本场景
business/detect/                            检测高级字段场景
```

## 性能测试

```text
performance/config/config.py                        性能环境配置
performance/data/**                                 样例 payload
performance/test_design/common/entity_access.py     实体访问公共层
performance/test_design/common/ascii_report.py      统一 ASCII 报告
performance/test_design/search/search.py            Search 合并入口
performance/test_design/entity/insert/entity_insert.py
performance/test_design/entity/get/entity_get.py
performance/test_design/entity_delete/entity_delete.py
performance/test_design/detect/detect.py
```

## 输入与输出

```text
data/**                                     功能/业务输入用例
function_test/**/results/                   功能运行结果
business/**/responses/                      业务运行结果
performance/outputs/**                      性能运行结果
outputs/report.html                         唯一最终 HTML 报告
```

## 文档与归档

```text
docs/ARCHITECTURE.md                        架构说明
docs/TEST_ENTRYPOINTS.md                    入口与选择项
docs/FILE_INDEX.md                          当前文件索引
docs/reports/                               方案 PDF
archive/legacy/                             旧入口、旧说明和历史日志
archive/report_snapshots/                   历史 HTML 快照
archive/query_samples/                      历史查询样本
```
