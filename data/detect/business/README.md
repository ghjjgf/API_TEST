# Detect 业务用例

## 职责
保存检测业务场景输入。

## 目录内容
- `advanced_fields.json`：`image.url + user_object`、`image.url + rois_polygon` 两组独立 payload。

## 入口
由 `business/detect/advanced_fields.py` 读取。

## 输入与输出
- 输入：检测 payload 用例。
- 输出：`business/detect/responses/advanced_fields/`。

## 依赖关系
仅用于业务场景，不参与功能 pytest 用例集合。
