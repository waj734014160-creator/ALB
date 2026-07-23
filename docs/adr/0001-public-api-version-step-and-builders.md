# ADR-0001：0.3.0 公共版本、step 与 builder

## 文档角色

- 角色：下一阶段公共接口版本和调用语义的架构决策。
- 状态：Accepted，第三轮审查后修正依赖注入边界。
- 允许更新：目标版本、`step()` 语义、builder 类型、诊断出口和兼容周期。
- 禁止更新：把目标接口写成当前 0.2.0 已实现能力、单次测试结果或外部项目状态。
- 相关文档：`docs/next_interface_development_plan.md`、`docs/interface_architecture.md`。

## 背景

下一阶段会把 ALB 的计算型 `output()` 改为只读、把公开输入收敛为 DTO、默认停止隐式历史积累，
并把保存从数值组件移出。这些是公共语义变化，不应作为无版本影响的内部重构发布。

同时，“自动构建普通轴承或 direct-spool 轴承”虽然方便，但会让返回类型成为无法在调用点清楚
收窄的联合类型。

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
   build_alb(envelope) -> BearingRuntimeProtocol[BearingInput]
   build_direct_spool_alb(envelope) -> DirectSpoolBearingRuntimeProtocol
   build_alb_from_file(path) -> BuiltBearing
   ```

6. `build_alb()` 和 `build_direct_spool_alb()` 只接受 `ALBConfigEnvelope`。裸领域配置和无版本字典
   不进入新的公共 builder。
7. `BuiltBearing` 是带 `control_mode` 判别字段的封闭联合：

   ```text
   BuiltControlledBearing(control_mode="controlled" | "none", bearing=...)
   BuiltDirectSpoolBearing(control_mode="direct_spool", bearing=...)
   ```

   调用者在执行 `step()` 前即可根据判别字段收窄输入类型。
8. bearing 构造依赖通过独立类型化对象注入：

   ```python
   build_alb(
       envelope,
       *,
       dependencies: BearingBuildDependencies | None = None,
   )
   ```

   `BearingBuildDependencies` 只携带构造 bearing 数值组件所需的 `controller_factory` 和
   `component_factories`。这些对象不得从 JSON/JSON5 配置反序列化。
9. post-commit 和输出副作用依赖按拥有者分开：

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
10. builder、coupler 和 workflow 必须拒绝放错层或与 `control_mode` 不兼容的依赖。例如普通
    closed-loop bearing 不能携带 direct-spool provider，数值 bearing 不能取得 artifact writer。
11. 普通对象不直接暴露 mutable implementation。诊断使用不可变
   `diagnostic_snapshot()`；确需迁移旧插件时，只能通过明确命名的兼容 adapter 解包。
12. `BearingBlock`、`DirectSpoolBearingBlock`、`LegacyBearingAdapter`、
   `LegacyControllerAdapter` 和必要的 `LegacySignalAdapter` 可以在 0.3.x 作为迁移兼容面存在。
   它们不得早于 `0.4.0` 删除，并且删除前必须满足：

   - 在至少一个已发布 minor 周期中给出弃用说明；
   - declared 内部和外部消费者为零；
   - quickstart、迁移表和替代 API 已完成；
   - 对应兼容参考可以被明确归档而不是静默删除。

## 影响

- 简单用户可以从配置文件构建，但 public typing 不依赖运行时猜测。
- `step()` 适合单工况计算，却不会产生“似乎推进并提交了时间”的歧义。
- 0.2 调用者获得明确迁移周期；新实现无需永久维护两套计算生命周期。
