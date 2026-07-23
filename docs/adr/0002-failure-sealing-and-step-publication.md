# ADR-0002：失败封锁与物理步骤发布

## 文档角色

- 角色：mutable 数值组件失败语义和物理步骤发布顺序的架构决策。
- 状态：Accepted，第三轮审查批准。
- 允许更新：执行阶段、失败状态、正常结果发布、ledger 提交和重试规则。
- 禁止更新：宣称 mutable film、thermal 或 rotor 已具有未实现的状态回滚能力。
- 相关文档：`docs/next_interface_development_plan.md`、`docs/adr/0003-result-recorder-and-idempotency.md`。

## 背景

film、thermal、控制器、阀和 rotor 都包含原地更新的数值状态。把 coupler 描述为
“prepare/commit 事务”会暗示系统能够在任意中途异常后恢复到步骤开始前，但当前算法并没有完整
checkpoint/rollback 能力。

## 决策

顶层一步采用以下唯一顺序：

```text
validate, including ledger.validate_next(context)
         -> execute mutable calculation
         -> build candidate immutable result
         -> ledger.commit_step(context)
         -> publish current result
         -> recorder attempt, captured as status/pending
         -> observer dispatch, captured as diagnostics
         -> return result or raise an explicit post-commit error
```

这里保证的是“失败封锁和正常结果发布原子性”，不是 mutable 状态回滚：

1. `validate` 在任何状态修改前检查 context、时间、单位、形状、有限性、拓扑和全部可预检输入，
   并必须调用 `ledger.validate_next(context)`。重复步、乱序、单位变化、`dt` 变化和时间增量错误
   应在 mutable execute 之前失败。
2. `execute` 可以修改内部数值状态。当前阶段不承诺把这些修改回滚。
3. `execute` 或候选结果构造失败时：

   - 整体 runtime 进入 `FAILED`；
   - 不发布本步正常输出；
   - 不提交 ledger；
   - 不调用正常 recorder 或 `StepCompleted` observer；
   - 不自动重算相同物理步骤；
   - 只允许读取独立 `failure_snapshot()` 和此前已经提交的历史。

4. 目标 `StepCommitLedger.commit_step(context)` 必须满足：

   - 不执行 recorder、observer 或任何用户代码；
   - 只复用 `validate_next()` 的规则并执行一次 `_last_context = context` 内部引用赋值；
   - 验证失败发生在赋值前，因此抛出即表示 context 未登记；
   - 赋值后不再执行可能抛出的代码；
   - 提供 `last_context` 和 `is_last_committed(context)`，只判断给定 context 是否为最近一次提交。

   ledger 由单一 workflow/coupler 拥有，提交调用必须串行化；不支持多个线程同时推进同一个物理
   runtime。`commit_step()` 仍会在赋值前重新验证，避免早期 `validate_next()` 与提交之间的状态漂移。
   ledger 不保存完整 context 历史；完整时间历史属于 recorder。

5. `publish current result` 只能是不可失败的内部不可变快照引用替换。它不得执行用户 callback、
   recorder、observer、持久化、数组转换、摘要计算或任何可能抛出异常的工作。
6. `physical_step_committed` 由 `ledger.is_last_committed(context)` 确定。只有 commit 成功后才能为
   `True`；此前构造的对象始终只是 candidate，不属于公开正常结果。
7. 只有成功重新 `init()` 才能从数值失败恢复。初始化会创建新的 runtime session，而不是声称
   继续失败前的物理轨迹。
8. ledger 提交后，物理步骤已经完成，不能因为 recorder 或 observer 失败而回滚或改写为未执行。
   recorder/observer 的原始异常不得在 post-commit 流程中提前逃逸；必须先转换为 recording status、
   pending record 或 observer diagnostic，完成规定的单次 observer 派发后，再由 workflow policy
   决定返回 committed result 或抛出带 `physical_step_committed=True` 的专用错误。
9. `StepCommitLedger` 的目标接口不再接受 recorder callback。它只验证并登记物理步骤；记录和
   观察属于提交后的独立阶段。

## 影响

- 同一 context 不会在半推进 mutable 状态上被静默重试。
- 正常结果只会在 ledger 成功后通过不可失败的引用替换公开，不会暴露未提交 candidate。
- recorder/observer 的失败必须明确标注“发生在物理提交后”，其恢复规则由各自 ADR 定义。
