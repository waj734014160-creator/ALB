# ADR-0008：伺服阀公开配置收敛为二阶参数与传递函数

## 文档角色

- 角色：0.4.5 伺服阀公共配置、内部构建和数值保留边界的架构决策。
- 状态：Accepted。
- 允许更新：模型判别字段、输入参数、迁移规则和验收边界。
- 禁止更新：单次测试日志、外部实时状态和未经验证的数值结论。
- 相关文档：`docs/adr/0006-alb-0-4-no-legacy-friendly-api.md`、
  `docs/adr/0007-preserve-validated-numerical-algorithms.md`、
  `docs/migrations/0.4.5.md`。

## 背景

0.4.4 的 `response_time` 实际映射到二阶传递函数的
`tw = 1 / (2*pi*f_n)`，不是通常意义的响应时间；`third_order` 又把固定二阶
环节和一个一阶极点绑在一起，不能表达用户已辨识的任意高阶阀。`static` 同时
承担公开动态模型和内部静平衡工具两个角色，导致配置模型与运行时用途混杂。

## 决策

1. 0.4.5 的主动轴承 JSON5 `valve.model` 只接受 `second_order` 和
   `transfer_function`。
2. `second_order` 必须输入 `natural_frequency_hz > 0` 与
   `damping_ratio > 0`，可选 `delay >= 0`，单位分别为 Hz、1 和 s。
3. 二阶运行时继续使用已验证的
   `1 / (tw^2*s^2 + 2*zeta*tw*s + 1)`，其中
   `tw = 1 / (2*pi*natural_frequency_hz)`，因此接口变化不替换数值算法。
4. `transfer_function` 必须输入连续时间 SISO 的 `numerator` 和
   `denominator`，系数按 `s` 降幂排列。分子包含完整增益和任何有理延迟近似；
   不接受独立的频率、阻尼或延迟字段。
5. 多项式必须非空、有限、实数、首项非零，分子不能全零，且传递函数必须
   proper。`[1] / [1]` 是静态单位传递函数的规范表示。
6. 内部 `static_sv()` 继续用于静平衡和直接阀芯路径，但不作为第三种公共
   JSON5 模型。
7. 解析谐波 runtime 本轮保持二阶阀边界；任意传递函数先用于完整时域运行，
   不在接口重构中扩大未经参考验证的解析算法。
8. 修改前先冻结二阶、带延迟二阶、旧三阶和静态阀的连续/离散矩阵及时间响应；
   等价新接口必须精确匹配该参考。

## 版本与迁移

Python 包版本升级为 `0.4.5`。按本轮小版本决定，根
`ALB.SCHEMA_VERSION` 继续为 `0.4.0`；但旧阀字段不再被该运行时接受，调用者
必须显式迁移，运行时不提供模糊别名。

- 旧二阶：`natural_frequency_hz = 1 / (2*pi*response_time)`。
- 旧三阶：把二阶分母、`[tp3, 1]` 和需要的 Padé 延迟多项式卷积后直接传入。
- 旧静态：使用 `numerator: [1.0]`、`denominator: [1.0]`。

## 修订关系

本文补充 ADR-0006 的严格配置边界，并服从 ADR-0007 的数值算法保留与修改前
冻结参考要求。历史 0.4.0 至 0.4.4 的发布证据和配置说明保持不修改。
