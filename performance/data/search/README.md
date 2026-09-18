# Search 性能样例

## 职责
提供搜索请求的基础模板。

## 目录内容
- `search.py`：`SAMPLE_SEARCH` 查询模板和特色样例。

## 入口
由 Search 性能入口和业务搜索运行时导入。

## 输入与输出
- 输入：search payload 字典。
- 输出：不直接生成报告。

## 依赖关系
搜索压测会运行时替换 include 特征、repo 组合和参数。
