# ALB 架构决策记录索引

相关文件：
  `docs/daily_maintenance/daily_doc_update_index.md`、
  `docs/current_state.md`、
  `docs/migrations/0.4.0.md`、
  `docs/interface_architecture.md`。

## 状态定义

- `Accepted`：已经作为后续实现约束采用，但不表示相关源码已经实现。
- `Proposed`：方向和候选契约已形成，尚未作为正式决策采用；是否实施由本次用户授权和实际任务范围确定。
- `Superseded`：已被后续 ADR 明确替代；旧文档保留用于追溯。
- `Deprecated`：决定仍能解释现有兼容行为，但不再用于新增实现。

## 当前 ADR

| ADR | 状态 | 主题 |
| --- | --- | --- |
| [ADR-0001](0001-public-api-version-step-and-builders.md) | Superseded | 0.3.0 公共版本、自动初始化、混合轴承、配置封装、builder 返回类型和兼容周期 |
| [ADR-0002](0002-failure-sealing-and-step-publication.md) | Accepted | mutable 数值组件的失败封锁、原子 ledger 提交与结果发布顺序 |
| [ADR-0003](0003-result-recorder-and-idempotency.md) | Accepted | recorder、run/session、分型状态、RecordableValue、规范摘要、pending 和失败恢复 |
| [ADR-0004](0004-observer-and-failure-snapshot.md) | Accepted | observer 异常隔离、post-commit 诊断和 failure snapshot |
| [ADR-0005](0005-bearing-unit-adapter.md) | Accepted | 轴承单位换算、local context、primitive descriptor 和转换方向元数据 |
| [ADR-0006](0006-alb-0-4-no-legacy-friendly-api.md) | Accepted | 0.4 无 legacy、友好 facade、严格配置、不可变 simulation 和发布门禁 |
| [ADR-0007](0007-preserve-validated-numerical-algorithms.md) | Accepted | 接口重构保留已验证数值算法、双侧参考条件和 0.4.1 数值门禁 |
| [ADR-0008](0008-servovalve-public-configuration.md) | Accepted | 0.4.5 二阶 Hz、静态与任意传递函数三类伺服阀公开配置 |
| [ADR-0009](0009-controller-sampling-period-and-ros2-integrator.md) | Accepted（ROS2 部分功能不完善） | 0.4.6 控制器采样周期为仿真步整数倍的例外、步长调整规则与可选 ROS2 耦合积分器 |

ADR-0006 替代 ADR-0001。ADR-0002 至 ADR-0005 的失败、提交、记录和单位原则
继续约束 0.4 内部 runtime；当前用户接口以 `docs/interface_architecture.md` 和
`docs/alb_albnn_quickstart.md` 为准。ADR-0007 补充 ADR-0006 的数值算法保留
边界；ADR-0008 固定 0.4.5 的三类伺服阀配置。ADR-0009 为 ADR-0007 第 8 条
增加控制器采样周期例外，物理组件仍共享同一步长；ROS2 只作为可选积分器加入，
默认 staggered 路径继续按 ADR-0007 冻结并精确回归。Accepted 表示决策已采用，
不等于发布验收已通过。
