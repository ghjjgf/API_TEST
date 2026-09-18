# Detect 业务场景

## 职责
验证检测接口高级字段和独立 payload 组合。

## 目录内容
- `advanced_fields.py`：高级字段场景。
- `responses/`：运行结果。

## 入口
运行 `python3 /home/wx/API_TEST/business/detect/advanced_fields.py`。

## 输入与输出
- 输入：`data/detect/business/advanced_fields.json` 和参考检测图片/URL。
- 输出：`business/detect/responses/advanced_fields/`。

## 依赖关系
依赖 Detect API 适配器和业务运行时。
