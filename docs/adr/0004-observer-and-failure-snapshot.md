# ADR-0004：Observer 与 failure snapshot

## 文档角色

- 角色：步骤观察、异常隔离和失败诊断数据的架构决策。
- 状态：Accepted，第三轮审查批准。
- 允许更新：事件 DTO、调用顺序、observer 异常策略、共享快照和 failure snapshot 字段。
- 禁止更新：让 observer 参与数值正确性、ledger 提交或物理回滚。
- 相关文档：`docs/next_interface_development_plan.md`、`docs/adr/0002-failure-sealing-and-step-publication.md`。

## 背景

GUI、日志和监控需要收到步骤事件，但当前布尔 `Signal` 没有 payload，并通过字符串回调混合了
数值计算、历史写入和外围通知。如果 observer 的异常改变已经推进完成的物理步骤状态，会产生
无法解释的重复执行风险。

## 决策

1. 数值正确性、状态推进和 ledger 提交全部使用显式方法，不通过 observer。
2. `StepCompleted` 是物理 ledger 成功提交后的不可变事件，至少包含：

   ```text
   run_id, StepContext, ResultBundle, recording status/receipt
   ```

   recorder 成功或失败都发送且只发送一次 `StepCompleted`。状态使用 ADR-0003 的封闭
   `StepRecordingStatus`：未配置为 `NOT_CONFIGURED`，成功为 `RECORDED`，record 异常并生成
   pending 时统一为 `PENDING`，不使用自由字符串 `"failed"`。
3. pending record 恢复成功时发送独立 `RecordingRecovered` 事件；不得再次发送该物理步骤的
   `StepCompleted`。`RecordingRecovered` observer 自身异常使用与其他 observer 相同的隔离规则。
4. 多个 observer 共享同一不可变 `ResultBundle` 对象，不为每个 observer 深复制大数组。observer
   不得获得 mutable runtime 引用。
5. 默认 observer 策略是隔离异常：

   - 继续承认物理步骤已经提交；
   - 把 observer 名称、异常类型和消息记录为 `ObserverFailure`；
   - 不使数值 runtime 进入 `FAILED`；
   - 不自动重复物理步骤或重复通知已经成功的其他 observer。

6. 需要强制监控成功的 workflow 可以选择 strict observer policy。它可以在提交后抛出
   `PostCommitObserverError`，但必须明确携带 `physical_step_committed=True`，不能暗示可回滚。
7. 数值阶段失败时不发送 `StepCompleted`。可选诊断 observer 可以接收独立 `StepFailed`，但它
   仍不参与恢复或提交；任何 `StepFailed` observer 自身异常也必须隔离到外部诊断，不能覆盖原始
   数值失败或产生第二条未定义恢复路径。
8. `failure_snapshot()` 专门描述使数值 runtime 进入 `FAILED` 的提交前失败，并在该状态下仍可
   读取。目标字段至少包括：

   ```text
   run_id
   attempted StepContext
   phase and component
   error type and sanitized message
   physical_step_committed=False
   last committed result
   ```

9. post-commit recorder/observer 问题不使数值 runtime 进入 `FAILED`，也不写入
   `failure_snapshot()`。始终可读的 `post_commit_status()`/`diagnostic_snapshot()` 至少包含：

   ```text
   run_id and committed StepContext
   physical_step_committed=True
   recording status and pending record key
   bounded recent ObserverFailure records
   whether the next advance is blocked
   ```

   `end_run()` 后，run receipt 使用 `RunCloseStatus.COMPLETE` 或 `RunCloseStatus.INCOMPLETE`；
   关闭状态通过 run receipt 和 post-commit diagnostic 表达，不重发过去步骤的 `StepCompleted`。

10. `ObserverFailure` 不形成新的无界隐藏历史。默认只保留当前步骤；可配置 bounded ring 最多
    保留最近 N 条。完整长期日志交给外部日志/ArtifactWriter 边界。
11. failure snapshot 和 post-commit diagnostic 不保存 traceback 中的凭据、文件内容或 mutable
    组件引用；完整 traceback 只进入受控日志边界。

## 影响

- GUI/日志失败不会污染物理轨迹。
- 调用者能区分“数值执行失败”和“物理提交后记录/通知失败”。
- `Signal` 可以从核心路径移除，而不丢失必要的监控能力。
