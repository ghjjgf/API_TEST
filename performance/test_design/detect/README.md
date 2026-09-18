# Detect 性能测试

## 职责
对检测接口执行 Python + k6 压测。

## 目录内容
- `detect.py`：入口。

## 入口
运行 `python3 /home/wx/API_TEST/performance/test_design/detect/detect.py`。

## 输入与输出
- 输入：`performance/data/detect/detect.py` 的 payload 样例。
- 输出：`performance/outputs/detect/detect_<timestamp>/`。

## 依赖关系
默认场景为 all/face，默认并发梯度为 1/8/16/32/64/128。
