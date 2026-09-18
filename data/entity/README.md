# Entity 输入数据

## 职责
保存实体业务场景和功能测试的输入。

## 目录内容
- `business/`：实体版本、轮询和重读场景配置。
- `function/create/`、`function/get/`、`function/delete/`、`function/update/`：实体接口用例。

## 入口
由实体功能测试和 `business/entity/` 场景读取。

## 输入与输出
- 输入：实体 payload、repo 配置和 body_checks。
- 输出：`function_test/entity/results/` 或 `business/entity/responses/`。

## 依赖关系
实体 API 适配由 `api/api.py` 提供。
