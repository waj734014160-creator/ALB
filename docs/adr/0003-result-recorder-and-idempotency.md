# ADR-0003：结果 recorder、幂等性与失败恢复

## 文档角色

- 角色：显式结果历史记录协议的架构决策。
- 状态：Accepted，第四轮审查批准并补充 P2 精确化约束。
- 允许更新：run/session、记录键、receipt、顺序、重复调用、pending record 和恢复语义。
- 禁止更新：把 recorder 当作物理时步提交者、磁盘 writer 或隐式组件历史。
- 相关文档：`docs/next_interface_development_plan.md`、`docs/adr/0002-failure-sealing-and-step-publication.md`。

## 背景

当前 `ResultRecorderProtocol.record(bundle)` 没有时步上下文、run 身份或回执，无法区分不同仿真、
检测重复步骤或安全重试。数值组件中的隐藏 DataFrame 历史又会让不需要时间历史的用户承担持续
内存增长。

## 决策

目标 recorder 最小语义为：

```python
begin_run(run_id: str) -> RunReceipt
record(context: StepContext, bundle: ResultBundle) -> RecordReceipt
end_run(run_id: str, *, allow_incomplete: bool = False) -> RunReceipt
```

具体 DTO 名称可在实现时调整，但必须满足：

`run_id` 是非空 opaque string，不得包含 Unicode control character。它默认由顶层 workflow
生成；recorder 不解析其目录含义，也不得直接把它拼接为文件路径。同一 recorder 实例中已经关闭
的 `run_id` 不得重新开启。

1. `begin_run()` 建立 recorder 的唯一活动 run。已有活动 run 时再次调用必须失败；不能静默关闭
   或覆盖前一个 run。
2. `end_run(run_id)` 显式关闭活动 run，并返回包含已记录范围、数量、pending 数和最终摘要的
   `RunReceipt`。只有活动 run 已结束后才能开始另一个 run。存在 pending record 时，严格模式
   拒绝正常结束；调用者必须先恢复记录或显式使用 `allow_incomplete=True` 结束。incomplete receipt
   使用 `RunCloseStatus.INCOMPLETE` 并永久列出未恢复键，关闭后不再允许重试或追加；无缺口关闭
   使用 `RunCloseStatus.COMPLETE`。
3. `init()` 开启新的 runtime session 时不得清空调用者注入的外部 recorder；由顶层
   workflow/coupler 显式协调 `end_run()` 和新的 `begin_run()`。
4. 唯一记录键是 `(run_id, step_index)`。
5. 每个 run 的时间连续性直接复用 `StepCommitLedger` 的验证规则或其抽取出的同一公共 validator：
   第一个 context 定义起点；后续 step index 恰好加一；`unit_system` 和 `dt` 不变；
   `time[n] - time[n-1]` 使用 ledger 的同一容差匹配 `dt`。recorder 不复制另一套近似规则。
6. `RecordReceipt` 至少包含记录键、版本化 bundle 摘要和处置结果。
7. 相同键和相同摘要的重复调用返回原 receipt，或者以明确的 idempotent duplicate 结果成功；
   相同键但不同摘要必须抛出冲突错误。
8. 默认 recorder 按 step index 严格连续记录；跳号、倒序或跨 run 复用活动状态都失败。
9. 物理 ledger 提交后才调用 recorder。record 失败不会回滚物理状态，也不会使已经提交的步骤
   变成未提交。
10. 顶层运行时保存不可变 `PendingRecord(run_id, context, bundle, error_summary)`。恢复只重新调用
   recorder，不重新执行 bearing、thermal 或 rotor。
11. recorder 失败后，顶层进入独立的 `COMMITTED_RECORDING_PENDING` post-commit 状态：

   - 数值 runtime 仍然有效；
   - 当前已经提交的输出可以读取；
   - 默认禁止下一次 `advance()`，避免严格连续历史产生更多缺口；
   - 允许 `retry_pending_record()`；
   - 重试只调用 recorder，不执行任何物理计算；
   - receipt 成功后清除 pending 状态，允许推进下一步；
   - 不要求重新 `init()`。

12. 允许带历史缺口继续推进只能是显式 non-strict workflow 策略。该策略必须允许多个
    `PendingRecord`、在每个 `StepCompleted` 中报告准确 recording status，并定义结束 run 时如何
    处理未恢复缺口；它不是默认实现。
13. 默认 API 必须让调用者明确看到 post-commit 记录失败。实现可以返回带 recording status 的
   committed-step result；严格 workflow 可以抛出带 `physical_step_committed=True` 的专用异常，
   但异常必须携带 pending record。recorder 原始异常必须先被捕获，形成 pending/status 并完成
   ADR-0004 规定的单次 `StepCompleted` 派发后，才能向调用者返回或抛出。
14. `InMemoryResultRecorder` 保存完整已提交历史。ring buffer、sampling 和 field filtering 使用
    可组合 decorator。
15. 无界 recorder 可以保留全部 receipt 索引。bounded recorder 必须声明有限
    `idempotency_window`：

    - window 内保留 key、digest 和 receipt；
    - 淘汰后的旧键再次提交必须返回/抛出 `ExpiredRecordKey`；
    - 不重新插入已淘汰历史，也不声称能永久比较所有旧摘要；
    - receipt 索引和结果数据都必须符合声明的内存上界。

16. `clear()`、删除历史或写磁盘不属于最小 recorder 协议。磁盘持久化继续由
    `ArtifactWriterProtocol` 承担。

## 步骤记录与 run 关闭状态

单个物理步骤和整个 run 使用两个封闭枚举，不使用自由字符串：

`StepRecordingStatus`：

| 状态 | 含义 |
| --- | --- |
| `NOT_CONFIGURED` | 顶层没有注入 recorder。 |
| `RECORDED` | 当前步骤已经获得有效 `RecordReceipt`。 |
| `PENDING` | recorder 调用失败并生成 `PendingRecord`；默认阻止下一次 `advance()`。 |

`RunCloseStatus`：

| 状态 | 含义 |
| --- | --- |
| `COMPLETE` | run 已关闭且没有未恢复记录。 |
| `INCOMPLETE` | `end_run(allow_incomplete=True)` 关闭了仍含 pending 的 run。 |

普通 record 异常统一进入 `StepRecordingStatus.PENDING`，不存在含义重叠的通用 `"failed"` 状态。
pending 恢复成功后变为 `RECORDED`；incomplete run 关闭后不得再次恢复或追加。

## RecordableValue

recorder 接受的 bundle 值域显式限定为：

```text
None
bool, int, finite float, finite complex, str, bytes
numpy.ndarray satisfying the v1 dtype rules
tuple/list of RecordableValue
mapping[str, RecordableValue]
```

1. `np.generic` 标量在快照/摘要入口先执行 `.item()`，再应用对应 Python scalar 规则。因此
   `np.float64(1.0)` 与 `1.0` 使用同一种规范表示。
2. Python complex 按 real、imag 两个 finite IEEE-754 binary64 little-endian 数编码，并保留每个
   分量的 `-0.0` 位级差异。
3. Pandas `DataFrame/Series`、dataclass、Path、任意领域对象和其它 allowlist 外对象不属于
   `RecordableValue`。组件必须在生成 recordable bundle 前把它们转换为 ndarray 或 primitive
   mapping。
4. 顶层在 candidate result 阶段执行 `validate_recordable_bundle()`。如果配置了 recorder，
   不支持的结果应在 ledger commit 前失败，而不是等到 recorder post-commit 阶段才发现。

## Bundle 摘要

摘要算法固定为版本化的 `alb.result-bundle.sha256.v1`：

1. SHA-256 输入以算法 ID 的 UTF-8 字节开始。
2. `StepContext` 按固定字段顺序编码：`step_index`、`time`、`dt`、`unit_system`。
3. `ResultBundle.values` 和 `metadata` 的 mapping key 必须为字符串，并按 UTF-8 字节序排序。
4. 每个值带类型标签；tuple/list 保留类型和元素顺序，mapping 递归排序。
5. ndarray 必须满足：

   - `dtype.hasobject` 为 `False`；object array 和任何嵌套 object field 都拒绝；
   - v1 只接受 bool、signed/unsigned integer、float、complex，以及完全由这些类型组成的
     structured/subarray dtype；
   - float/complex 数组逐元素检查 finite；
   - dtype、shape、structured field name/order/offset/subarray shape 和规范字节都进入摘要；
   - 摘要前转换到规范 little-endian C-contiguous layout，但不改变 recorder 保存的原快照；
   - structured dtype 按声明字段顺序递归编码各字段值，不哈希 alignment/padding 原始字节；
   - `-0.0` 与 `+0.0` 保留 IEEE-754 位级差异，不做数值归一化。

6. NumPy scalar 按 `RecordableValue` 规则先规范化为 Python scalar。Python float 固定编码为
   IEEE-754 binary64 little-endian，并拒绝 NaN/Inf；`-0.0` 位级保留。Python complex 按两个
   binary64 分量编码。Python 整数、布尔、字符串、`None` 和 bytes 使用明确类型标签与固定长度/
   长度前缀编码。
7. object dtype、不在 v1 allowlist 中的 ndarray dtype、不支持的 Python 对象或非字符串 mapping
   key 必须抛出专用 `UnsupportedResultValueError`，不能退回 `repr()`、pickle 或对象地址。
8. `RecordReceipt` 记录算法 ID 和十六进制 SHA-256。更换编码规则必须创建新的算法 ID，不能在
   `v1` 名称下改变字节表示。

## `step()` 与 recorder

`bearing.step(dto)` 永远不自动调用 recorder。需要时间历史时，调用者把 recorder 注入顶层
workflow/coupler，由其在唯一物理步骤提交后记录。存在默认严格 pending 时，`step()` 仍不负责
恢复或绕过顶层推进门禁。

## 影响

- 无 recorder 的单次计算只保留当前快照。
- recorder 失败可以安全重试记录本身，不会重复推进物理模型。
- 长仿真的内存策略可以组合，而不需要一个包含所有策略的巨型 recorder。
