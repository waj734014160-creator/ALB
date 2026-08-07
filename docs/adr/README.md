# ALB 架构决策记录索引

## 文档角色

- 角色：ALB_MAIN 架构决策及候选决策索引。
- 目的：记录会约束多个实现阶段、公共接口或验收语义的 Accepted/Proposed 决策，避免在生产代码迁移期间重复解释或产生相互冲突的局部方案。
- 允许更新：ADR 状态、决策、理由、影响范围、替代方案和后续修订关系。
- 禁止更新：把未实施设计写成当前 API、单次测试日志、外部项目实时状态、机器验收正文和源码实现细节流水。
- 更新时机：新增跨模块架构决定、原决定被替代或实现事实要求修订决定时。
- 事实来源 / 相关文档：
  `docs/daily_maintenance/daily_doc_update_index.md`、
  `docs/current_state.md`、
  `docs/next_interface_development_plan.md`、
  `docs/interface_architecture.md`。

## 状态定义

- `Accepted`：已经作为后续实现约束采用，但不表示相关源码已经实现。
- `Proposed`：方向和候选契约已经形成，但仍有待独立复审；不得据此开始相关生产实现。
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

ADR-0006 替代 ADR-0001。ADR-0002 至 ADR-0005 的失败、提交、记录和单位原则
继续约束 0.4 内部 runtime；当前用户接口以 `docs/interface_architecture.md` 和
`docs/alb_albnn_quickstart.md` 为准。ADR-0007 补充 ADR-0006 的数值算法保留
边界；ADR-0008 固定 0.4.5 的三类伺服阀配置。Accepted 表示决策已采用，
不等于发布验收已通过。
