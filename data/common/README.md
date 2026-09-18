# 公共参考数据

## 职责
保存跨模块复用的参考特征。

## 目录内容
- `reference_feature.b64`：业务和功能用例替换 `__REFERENCE_FEATURE__` 的参考特征。

## 入口
由 `function_test/support.py`、`business/support.py` 读取。

## 输入与输出
- 输入：base64 特征文件。
- 输出：不生成独立结果，替换后的 payload 进入对应测试响应归档。

## 依赖关系
被功能测试和业务测试共同依赖。
