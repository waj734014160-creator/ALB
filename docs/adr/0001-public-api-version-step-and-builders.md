# ADR-0001：0.3.0 公共版本、自动初始化与 builder

## 文档角色

- 角色：下一阶段公共接口版本、初始化和构建语义的架构决策。
- 状态：Accepted；2026-07-24 修订用户初始化、混合轴承构建和配置封装边界。
- 允许更新：目标版本、`step()` 语义、初始化所有权、builder 类型、配置封装、诊断出口和兼容周期。
- 禁止更新：把目标接口写成当前 0.2.0 已实现能力、单次测试结果或外部项目状态。
- 相关文档：`docs/next_interface_development_plan.md`、`docs/interface_architecture.md`。

## 背景

下一阶段会把 ALB 的计算型 `output()` 改为只读、把公开输入收敛为 DTO、默认停止隐式历史积累，
并把保存从数值组件移出。这些是公共语义变化，不应作为无版本影响的内部重构发布。

同时，用户不应在构造轴承后继续承担手动 `init()`、创建配置 envelope 或追加节流孔等装配步骤。
这些步骤会使“对象已经创建”和“对象已经可计算”成为两个状态，并让静压/动压分类暴露为不必要
的用户选择。是否需要节流耦合应由构造时给出的节流器拓扑决定。

“自动构建普通轴承或 direct-spool 轴承”虽然方便，但会让返回类型成为无法在调用点清楚收窄的
联合类型，因此不同输入端口仍使用分开的类型化 builder。

## 决策

1. 下一阶段公共语义目标版本为 `0.3.0`，不作为 `0.2.0` 的无提示补丁发布。
2. `bearing.step(dto)` 的唯一语义是：

   ```text
   input(dto) -> evaluate() -> output()
   ```

   它不提交全局物理时步，不更新 `StepCommitLedger`，不调用 recorder，也不通知 observer。
3. 物理时步提交只由 workflow/coupler 的 `advance(context)` 或等价顶层方法执行。
4. `output()` 返回同一份不可变完成快照；调用者不能修改其数组。无需为每次读取复制整个结果。
5. Python 类型化构建入口分开：

   ```python
   build_alb(config, ...) -> BearingRuntimeProtocol[BearingInput]
   build_direct_spool_alb(config, ...) -> DirectSpoolBearingRuntimeProtocol
   build_hybrid_bearing(config, ...) -> BearingRuntimeProtocol[BearingInput]
   build_alb_from_file(path) -> BuiltBearing
   ```

6. `ALBConfigEnvelope` 保留为 schema 校验、文件持久化和迁移使用的内部边界，但不再要求用户显式
   创建、调用或传入。`build_alb()`、`build_direct_spool_alb()` 和
   `build_hybrid_bearing()` 接收当前类型化配置或等价的显式构造参数，并在 builder 内部完成
   envelope 创建与校验；`build_alb_from_file()` 在内部加载和校验文件中的 envelope。无版本平铺
   字典仍不进入公共 builder，legacy 配置仍必须先经过单向迁移。envelope 的构造与
   materialize helper 不从用户 namespace 导出，公共 Python builder 也不接受 envelope 实例。
7. 用户直接创建 runtime 时，`__init__()` 必须在所有字段和直属子组件完成装配后自动执行一次
   `init()`；所有公共 builder 返回的对象也必须已经处于可接收输入的 `READY` 状态。用户示例、
   quickstart 和正常业务代码不得再要求 `bearing.init()`。
8. `init()` 方法保留，但它是组合模块拥有的内部生命周期钩子，不是普通用户操作。一个对象作为
   其他模块的子模块时，父模块可以在自身初始化或重置过程中显式调用子模块的 `init()`，以开启
   一致的新 session。重复的内部初始化必须安全地清除旧锁存输入、旧输出和失败状态，不得累计
   重复连接、节流器或历史。普通用户若需要从终止性失败重新开始，应重新构建对象，而不是直接
   调用 `init()`。
9. 新增中性的混合轴承构建入口 `build_hybrid_bearing()`。该轴承不要求用户声明
   `hydrodynamic` 或 `hydrostatic` 类型，也不接受等价的模式开关：

   - 构造时未提供节流器时，按动压油膜工况计算；
   - 构造时提供一个或多个节流器时，自动装配并调用节流流量与油膜压力的耦合计算；
   - 节流孔位置、供油压力及尺寸或无量纲流量系数必须作为 `__init__()` 的类型化输入，在对象
     进入 `READY` 前完成校验和装配；
   - 旧 `add_orifice()`、`add_orifices()` 和 `add_orifices_by_cq()` 仅作为限期兼容或内部装配
     能力保留，不属于新的用户构建流程，也不得要求用户在构造后修改轴承拓扑。

10. `BuiltBearing` 是带 `control_mode` 判别字段的封闭联合：

   ```text
   BuiltControlledBearing(control_mode="controlled" | "none", bearing=...)
   BuiltDirectSpoolBearing(control_mode="direct_spool", bearing=...)
   ```

   调用者在执行 `step()` 前即可根据判别字段收窄输入类型。
11. bearing 构造依赖通过独立类型化对象注入：

   ```python
   build_alb(
       config,
       *,
       dependencies: BearingBuildDependencies | None = None,
   )
   ```

   `BearingBuildDependencies` 只携带构造 bearing 数值组件所需的 `controller_factory` 和
   `component_factories`。这些对象不得从 JSON/JSON5 配置反序列化。
12. post-commit 和输出副作用依赖按拥有者分开：

   ```text
   CoupledBearingBinding
       -> spool_provider for that direct-spool bearing

   CouplingRuntimeDependencies
       -> recorder
       -> observers

   WorkflowOutputDependencies
       -> artifact_writer
   ```

   bearing builder 不接收或持有 recorder、observer、spool provider、artifact writer。
   `bearing.step()` 因此不会出现“持有但不应调用”的副作用依赖。
13. builder、coupler 和 workflow 必须拒绝放错层或与 `control_mode` 不兼容的依赖。例如普通
    closed-loop bearing 不能携带 direct-spool provider，数值 bearing 不能取得 artifact writer。
    `RsRotorBearingCouple` 以 `CoupledBearingBinding` 作为唯一内部拓扑源：高级构造入口只接收
    显式 binding；简易 `add_bearing(bearing, node_link)` 只为有量纲、普通
    `BearingInput` runtime 创建 binding。无量纲和 direct-spool 轴承必须显式提供 adapter/provider。
14. 普通对象不直接暴露 mutable implementation。诊断使用不可变
   `diagnostic_snapshot()`；确需迁移旧插件时，只能通过明确命名的兼容 adapter 解包。
15. `BearingBlock`、`DirectSpoolBearingBlock`、`LegacyBearingAdapter`、
   `LegacyControllerAdapter` 和必要的 `LegacySignalAdapter` 可以在 0.3.x 作为迁移兼容面存在。
   它们不得早于 `0.4.0` 删除，并且删除前必须满足：

   - 在至少一个已发布 minor 周期中给出弃用说明；
   - declared 内部和外部消费者为零；
   - quickstart、迁移表和替代 API 已完成；
   - 对应兼容参考可以被明确归档而不是静默删除。
16. `MultiPad` 是正式的组合 bearing runtime。它在构造结束时进入 `READY`，接收
    `BearingInput`，在一次 `evaluate()` 中各推进一个子瓦一次，并只发布当前不可变
    `BearingOutput`、收敛状态及结果/失败快照；默认不保存无限步骤历史。单瓦 film solver 仍是
    其内部数值实现。
17. `ThermalConfig.transient_enabled` 是默认 `False` 的严格布尔值。当前 typed/schema 配置拒绝
    `None`，legacy 缺失或 `None` 迁移为 `False`；builder 不再根据 servo 类型覆盖该选择。
    动态阀配稳态热、静态阀配瞬态热均允许构建，但每次 build 只发出一次提示性警告。

## 影响

- 简单用户可以从配置文件构建，但 public typing 不依赖运行时猜测。
- 用户拿到实例时即已完成初始化，不再手动协调构造、`init()` 和后装配步骤。
- 同一个混合轴承入口根据构造时的节流器拓扑决定是否执行节流耦合，不再要求用户先判断静压或
  动压类型。
- envelope 继续保护版本化配置和迁移边界，但不再成为 Python 用户必须理解和显式调用的中间对象。
- `step()` 适合单工况计算，却不会产生“似乎推进并提交了时间”的歧义。
- 0.2 调用者获得明确迁移周期；新实现无需永久维护两套计算生命周期。
