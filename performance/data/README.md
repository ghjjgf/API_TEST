# 性能样例数据

## 职责
保存各接口性能测试使用的静态 payload 和生成数据。

## 目录内容
- `detect/`：检测请求样例。
- `entity/`：实体样例。
- `repo/`：仓库及批量实体数据。
- `search/`：搜索查询模板。

## 入口
被 `performance/test_design/` 入口导入。

## 输入与输出
- 输入：Python 字典或生成函数。
- 输出：不直接写报告。

## 依赖关系
与 `performance/config/` 共同构成性能测试输入层。
