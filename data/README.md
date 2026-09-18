# 测试输入数据

## 职责
保存功能测试和业务测试使用的用例定义、校验规则和共享参考数据。

## 目录内容
- `common/`：跨模块参考特征。
- `detect/`：检测服务输入。
- `entity/`：实体接口输入。
- `repo/`：仓库接口输入。
- `search/`：搜索接口输入。

## 入口
由 pytest 用例、业务脚本和 `main.py` 报告汇总读取。

## 输入与输出
- 输入：`source_legacy_cases.json`、`body_checks.json`、业务 payload JSON 和参考特征文件。
- 输出：不生成测试结果；结果分别写入 `function_test/**/results/` 和 `business/**/responses/`。

## 依赖关系
依赖 `core/utils.py` 的 JSON 加载能力。

## 备注
文件名为历史兼容名称，不代表当前用例已废弃。
