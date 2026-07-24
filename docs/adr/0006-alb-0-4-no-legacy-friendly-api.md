# ADR-0006：ALB 0.4 无 Legacy 与友好 API

## 文档角色

- 角色：0.4 公共 API、配置、运行时和兼容边界的架构决策。
- 状态：Accepted。
- 允许更新：0.4 公共契约、删除边界、结果语义和发布条件。
- 禁止更新：单次测试日志、外部实时状态和机器验收正文。
- 相关文档：`docs/interface_architecture.md`、
  `docs/next_interface_development_plan.md`、`docs/migrations/0.4.0.md`。

## 背景

0.3 同时存在用户 builder、内部 envelope、bearing block、legacy adapter、
`Signal` 和多个历史分析/耦合入口。即使新生命周期更严格，用户仍需理解内部
装配与兼容层，且声明消费者可以继续依赖旧路径。继续同步两套接口会扩大数值
路径和失败恢复的审查面。

## 决策

1. 目标版本固定为 0.4.0，并明确允许不兼容变更。
2. `ALB` 根只公开配置、构建、用户对象、不可变结果和稳定异常。
3. 普通轴承入口固定为 `build_bearing()`、`bearing_from_file()` 和 keyword-only
   `Bearing.calculate()`；构造完成即可计算，不公开 `init()`，新会话使用 `reset()`。
4. active、liquid-film、Gas、MultiPad、harmonic 和 surrogate 使用正式 bearing
   runtime；高级领域入口使用严格 DTO 的 `input/evaluate/output/step`。
5. liquid-film 不接受动压/静压模式开关；构造期 `restrictors` 拓扑决定是否执行
   节流耦合。
6. 分析统一为 `bearing.analysis`，每次创建独立 runtime，返回完整不可变结果，
   不污染用户当前 bearing 状态。
7. 转子轴承系统统一为不可变 `SimulationConfig`/`BearingMount` 和
   `RotorBearingSimulation`；不提供运行期 `add_bearing()`，默认保存全部提交步。
8. JSON5 固定为 schema 0.4.0、严格 kind/include/spec 结构；include、资源根、
   override/sweep 和跨字段规则不允许宽松推断。
9. `Signal`、`lead_loop`、legacy adapter、旧 factories、旧 alias、宽松配置、
   兼容 save 和兼容 CLI 从 package 物理删除，不给弃用转发。
10. ALBNN 运行时只接受 v0.4 package、`weights_only=True` 权重和 NPZ scaler；
    旧模型转换器只位于不安装的 `tools/migrations`。
11. 历史 refs、文档和机器证据可以保留旧名称，但不得成为 wheel 或活跃源码的
    可执行依赖。
12. 发布必须从固定 SHA 的 detached worktree 双构建相同 wheel，完成内容审计、
    隔离安装、required nodeid、mypy 和外部消费者 smoke。验收报告不得写回候选。

## 影响

- 普通用户只需理解配置、构建、计算、分析/仿真和结果写出。
- 高级扩展依赖 typed factory/provider/observer，而不是对象内部字段或 Signal。
- 升级者必须在安装 0.4 前转换旧配置和模型；运行时不会替他们猜测。
- 数值公式保持不变，由迁移前冻结参考与 V4 manifest 约束。
- 0.3 的兼容周期结束，ADR-0001 中有关 0.3 builder、公开内部 init 钩子、
  BuiltBearing 联合和 legacy adapter 保留期的决定被本文替代。

## 替代关系

本文替代 ADR-0001。ADR-0002 至 ADR-0005 的提交后失败、recorder/observer、
failure snapshot 和单位适配原则继续作为内部 simulation/coupling 约束，但不再
要求用户接触其 0.3 兼容类型。
