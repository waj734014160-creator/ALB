# 公开接口边界

ALB 将接口分为三个层级。网站只把明确承诺的层级作为 API reference，不把“可以 import”误写成“稳定支持”。

## 普通用户：根 facade

```python
import ALB
```

`ALB.__all__` 中的 27 个符号是 0.4.4 普通用户入口，覆盖版本元数据、配置、构建、计算、分析、仿真、结果和稳定异常。`ALB.__version__` 表示安装包版本，`ALB.SCHEMA_VERSION` 表示严格 JSON5 配置契约版本。首先查阅[根公开 API](../../api/public_api_reference.md)。

## 高级用户：显式 namespace

`ALB.control`、`ALB.dynamics` 和 `ALB.surrogate` 为特定能力提供经过选择的高级接口。使用前：

1. 安装对应 optional extra；
2. 只从 namespace 明确导出的符号导入；
3. 阅读页面上的稳定级别和适用范围。

## 开发者：内部实现

以下路径服务于装配、数值实现或基础设施，不因为存在模块就成为普通用户 API：

- 私有模块或下划线符号；
- `ALB.core` 数值基础；
- `ALB.physics` 内部 solver/assembly；
- `ALB.infrastructure` 记录和远程实现；
- training、remote、compatibility 和 reference-generation internals。

!!! danger "不要绕过 facade"
    直接构造原生 config 或 solver 可能绕过 public validation、单位契约、异常包装和 lifecycle。只有在开发新模型或维护 ALB 本体时才进入内部层，并以 package overview 和 architecture tests 为边界。
