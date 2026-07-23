# ALB 下一阶段接口易用性与运行时收敛计划

## 文档角色

- 角色：ALB_MAIN 下一阶段开发目标和验收边界。
- 目的：把 P2 架构验收后确认的用户接口、轴承生命周期、转子耦合、结果记录和 `Signal` 替换目标固定为可执行任务基线。
- 允许更新：目标特性、目标接口、实施阶段、兼容边界、验收条件和明确的非目标。
- 禁止更新：把规划项写成已经实现、记录单次测试日志、复制机器验收正文、写入外部项目实时状态或未经验证的数值结论。
- 更新时机：用户确认目标取舍、实施阶段完成、公共接口方案改变或验收边界改变时。
- 事实来源 / 相关文档：
  `docs/daily_maintenance/daily_doc_update_index.md`、
  `docs/current_state.md`、
  `docs/adr/README.md`、
  `docs/alb_package_overview.md`、
  `docs/interface_architecture.md`、
  `docs/alb_albnn_quickstart.md`、
  `ALB/contracts/`、
  `ALB/systems/alb/ports.py`、
  `ALB/dynamics/coupling.py`、
  `ALB/core/events.py`。

## 状态和定位

本文是下一阶段的**目标文档**，不是当前 API 手册。文中标记为“目标”的接口尚未承诺已经存在；
当前可运行方式仍以 `docs/alb_albnn_quickstart.md` 和源码签名为准。目标公共版本固定为 `0.3.0`；
版本、`step()`、失败封锁、recorder、observer、builder 类型和单位适配语义由 `docs/adr/` 约束。
第四轮审查已经批准全部五份 ADR；剩余四项 P2 精确化意见也已写入契约。Accepted 只表示方案
可以指导后续实现，不表示生产源码已经实现。

P2 已经完成命名空间、DTO、控制器/阀/转子生命周期和发布门禁收敛。下一阶段不再进行一次新的
全仓目录重构，而是解决以下剩余使用和集成问题：

1. 历史入口要求用户手动执行“创建 implementation、`init()`、再包一层 `BearingBlock`”，暴露了内部适配细节。
2. `BearingBlock` 当前把旧实现的计算型 `output()` 包装到 `evaluate()`，外部生命周期严格，但轴承实现内部尚未真正完成职责拆分。
3. `RsRotorBearingCouple` 仍依赖旧轴承对象的 `signal/init/input/output/save` 组合，没有直接消费正式 `BearingProtocol`。
4. `Signal` 同时承担组件树传播、完成通知和隐式历史写入，数值推进、记录和副作用边界没有完全分离。
5. 需要时间历史的调用者缺少明确的“按需注入 recorder”用法；不需要历史的调用者仍可能为隐藏记录付出内存和认知成本。

## 总体目标

最终希望普通用户只需要理解“配置、构建、输入、计算、输出”：

```python
built = build_alb_from_file("alb.json5")
result = built.runtime.step(bearing_input)
```

高级用户仍可以显式调用：

```python
bearing.input(bearing_input)
bearing.evaluate()
result = bearing.output()
```

配置文件入口返回带 `control_mode` 判别字段的 `BuiltBearing`；普通和 direct-spool 的类型化 Python
入口分别是 `build_alb()` 与 `build_direct_spool_alb()`。这样既保留文件配置的便利性，也能让
调用者在构造输入 DTO 前确认轴承端口类型。

转子耦合器只依赖正式协议，不要求调用者知道具体 ALB 类、适配 block、`Signal` 或保存树：

```text
config -> public builder -> BearingRuntimeProtocol -> rotor-bearing coupler
                                      |                 |
                                      |                 +-> optional recorder
                                      |                 +-> optional observer
                                      |                 +-> optional artifact writer
                                      +-> current immutable port/result snapshots
```

## 设计原则

1. Reynolds、热耦合、控制、转子、ALBNN 和 coupling 的数值方程、矩阵装配顺序及迭代准则保持不变。
2. 每次生产源码修改前建立对应的新版本行为参考；既有 v1-v9 参考不得覆盖。
3. 公开对象直接满足正式协议；adapter 可以作为内部兼容工具存在，但普通用户不需要手动添加。
4. `input()` 只校验和锁存，`evaluate()`/`advance()` 承担计算，`output()` 只读取快照。
5. 顶层 workflow/coupler 是唯一物理时步提交者；局部组件只返回结果和收敛状态。
6. “端口输出”“完整当前结果”“时间历史”“写入磁盘”是四种不同能力，必须分别建模。
7. 不通过数值大小或调用路径猜测单位；量纲转换只能经显式尺度对象或 adapter。
8. 数值正确性不依赖事件广播、字符串反射回调或隐式保存副作用。
9. mutable 数值组件只承诺失败封锁和正常结果发布原子性，不宣称具有未实现的状态回滚事务。
10. recorder 和 observer 在物理 ledger 提交后运行；它们的失败不能把已推进步骤改写为未执行。

## 审查前置决策

| 问题 | 当前决定 | ADR | 状态 |
| --- | --- | --- | --- |
| 公共版本和兼容周期 | 目标版本为 0.3.0；兼容 adapter 在 0.3.x 保留，满足清零条件后最早 0.4.0 删除。 | ADR-0001 | Accepted |
| `step()` 是否提交 | 只组合 input/evaluate/output；不提交 ledger，不调用 recorder/observer。 | ADR-0001 | Accepted |
| builder 静态类型 | 普通/direct-spool builder 分开；bearing build、coupling runtime 和 workflow output 依赖分层注入。 | ADR-0001 | Accepted |
| 初始化所有权 | bearing 构造完成后自动进入 `READY`；`init()` 只保留给拥有子组件的组合模块。 | ADR-0001 | Accepted |
| 混合轴承类型 | 不声明动压/静压模式；构造期节流器拓扑决定是否执行节流耦合。 | ADR-0001 | Accepted |
| mutable 组件事务 | 不承诺回滚；顺序为 ledger 预检、mutable execute、candidate、原子 ledger commit、不可失败 publish。 | ADR-0002 | Accepted |
| recorder 失败 | 使用 run_id/step_index、步骤/run 分型状态、RecordableValue 和规范摘要；pending 默认阻止下一次 advance，只重试记录。 | ADR-0003 | Accepted |
| observer 和 failure snapshot | recorder 失败仍发送一次 StepCompleted；数值失败和 post-commit 诊断分开。 | ADR-0004 | Accepted |
| 单位适配 | scale 定义为一个 nondimensional unit 对应的 dimensional 值，转换经 canonical dimensional domain，metadata 分开记录 scale definition 和 applied transform。 | ADR-0005 | Accepted |

## 特性清单与修改方案

### A. 用户级构建和单步接口

| ID | 新增特性目标 | 对应修改方案 |
| --- | --- | --- |
| F01 | 从当前配置文件直接构建可运行轴承 | 新增 `build_alb_from_file(path, ...)`，内部完成 UTF-8/JSON5 读取、当前 schema 校验、装配和公开端口创建。legacy 文件仍必须先走单向迁移。 |
| F02 | 从当前类型化配置直接构建 | `build_alb(config, ...)` 和 `build_direct_spool_alb(config, ...)` 接受 `ALBConfig`/`NodimALBConfig`，在内部创建并校验 envelope；无版本平铺字典不进入公共 builder。 |
| F03 | 自动选择量纲实现 | builder 根据配置中的 `UnitSystem` 选择 dimensional/nondimensional 装配；无法确定时立即报错，不猜测。 |
| F04 | 文件入口使用可判别返回类型 | `build_alb_from_file()` 返回 `BuiltBearing` 封闭联合并携带 `control_mode`；类型化代码分别调用普通/direct-spool builder，不让一个函数静默返回两种无法提前区分的输入协议。 |
| F05 | 普通用户不再手动创建 block | factory 返回已经满足公开协议的对象；`BearingBlock` 系列降为内部装配或高级兼容工具。 |
| F06 | 提供无提交单步便捷调用 | `step(dto)` 严格等于 `input + evaluate + output`；它不提交 ledger、不调用 recorder、不通知 observer。物理提交只属于 workflow/coupler。 |
| F07 | 提供只读诊断出口 | 普通对象只公开不可变 `diagnostic_snapshot()`；仅兼容 adapter 提供明确命名的 legacy 解包入口，业务代码不直接取得 mutable implementation。 |

### B. 轴承原生严格生命周期

| ID | 新增特性目标 | 对应修改方案 |
| --- | --- | --- |
| F08 | ALB 原生 `input()` 只锁存 | 把当前 `ALB`、`ALBSV`、`NodimALB`、`NodimALBSV` 输入校验和状态锁存集中到运行时，不在输入阶段求解。 |
| F09 | ALB 原生 `evaluate()` 完成一次计算 | 将当前计算型 `output()` 中的控制器、阀、瓦块、热耦合和力汇总按原顺序移入 `evaluate()`。 |
| F10 | ALB 原生 `output()` 只读 | `output()` 返回同一份不可变 `BearingOutput` 完成快照；不重复深复制大数组。输入变化后未计算、首次未计算或 runtime 失效时明确报错。 |
| F11 | direct-spool 使用相同语义 | `ALBSV`/`NodimALBSV` 以 `DirectSpoolBearingInput` 锁存阀芯和轴承状态，`evaluate()` 只执行一次物理计算。 |
| F12 | 收敛状态只读 | `convergence_status` 或 `latest_result` 只返回最近计算快照，查询不得继续 film/thermal 迭代。 |
| F13 | 构造自动开启 runtime session | `__init__()` 在完整装配后自动执行内部 `init()`，清除锁存输入、旧输出和失败状态，所有子组件成功后才返回 `READY`；用户不调用该钩子。 |
| F14 | 运行失败统一封锁并保留诊断 | 任一局部组件在计算期间失败，顶层轴承 runtime 进入 `FAILED`，正常输入/计算/输出/保存被封锁；独立 `failure_snapshot()` 仍可读取。普通用户重新 build，组合模块可在整体重置时调用内部 `init()`。 |

### C. 正式协议拆分

| ID | 新增特性目标 | 对应修改方案 |
| --- | --- | --- |
| F15 | `BearingProtocol` 继续作为最小计算端口 | 保持 `node_link`、`unit_system` 和 `input/evaluate/output/step` 结构契约，供算法组合和静态类型检查使用。 |
| F16 | 新增泛型 `BearingRuntimeProtocol[InputT]` | 在最小端口上增加内部 owner `init()` 钩子、`lifecycle_state`、`convergence_status`、`result_snapshot()` 和 `failure_snapshot()`；普通与 direct-spool runtime 通过输入类型参数分开。 |
| F17 | direct-spool 协议显式分型 | 以独立输入 DTO/Protocol 表达外部阀芯命令，不让普通 `BearingInput` 隐式携带 `sx/sy`。 |
| F18 | 谐波系数保持能力协议 | `BearingCoefficientProtocol` 继续独立提供 `K`、`C` 和复数 `G_xv`，不强迫所有非线性轴承实现。 |
| F19 | 端口输出与结果 bundle 分离 | `output() -> BearingOutput` 只返回端口力；`result_snapshot() -> ResultBundle` 返回面向诊断/后处理的完整当前结果，两者都不携带历史或磁盘写入方法。 |
| F20 | 记录和持久化能力独立 | `ResultRecorderProtocol` 与 `ArtifactWriterProtocol` 分离；轴承协议不再要求 `signal` 或 `save()`。 |

### D. Rotor-bearing coupling 统一

| ID | 新增特性目标 | 对应修改方案 |
| --- | --- | --- |
| F21 | coupler 直接接收 `BearingRuntimeProtocol` | 删除具体 ALB 类和旧属性清单依赖；runtime-checkable 只做结构预检，随后还要显式验证输入类型、单位、节点、时间行为和 capability，不能把属性存在当作完整契约证明。 |
| F22 | coupler 不再要求 `signal` 和组件 `save()` | 数值推进使用显式方法；结果历史交给 recorder，磁盘输出交给 artifact writer。 |
| F23 | 轴承交换统一使用 DTO | 转子位移和速度构造成 `BearingInput`，轴承力读取为 `BearingOutput`，不再传递匿名字典。 |
| F24 | direct-spool 使用严格命令 provider | `SpoolCommandProviderProtocol` 接收 `StepContext` 与当前 `BearingInput`，遵循 `input/evaluate/output` 生命周期并返回时间一致、`UnitSystem.NONDIMENSIONAL`、范围 `[-1,1]` 的 `ValveOutput`；禁止隐式零阀芯。 |
| F25 | 量纲适配器覆盖完整变量和数学方向 | 运行时共享 ScaleSet；metadata 保存 primitive descriptor，并以 `scale_definition="dimensional_per_nondimensional"` 和独立 `applied_transform` 区分公式定义与本次数据流。 |
| F26 | 复用现有 rotor 载荷 DTO | `force0/force1` 继续使用 `RotorLoadInput.previous_force/force` 表达，不新增重复端点 DTO；内部可使用不可变 step workspace 避免半写入共享列表。 |
| F27 | 推进采用失败封锁和发布原子性 | 顺序固定为 `ledger.validate_next` 在内的 validate -> mutable execute -> candidate result -> ledger commit -> 不可失败 publish。提交前失败不发布正常结果且不自动重算，不宣称回滚内部状态。 |
| F28 | 每个物理步只提交一次且不与 recorder 伪原子化 | candidate 完成后先提交 ledger，再用不可失败引用发布；recorder/observer 原始异常先捕获并完成单次事件派发，最后才按策略返回或抛出明确的 post-commit 错误。 |
| F29 | 用类型化 binding 构建 coupling | `CoupledBearingBinding` 是唯一内部拓扑源。高级构造入口只接收显式 binding；`add_bearing(bearing, node_link)` 只为有量纲普通 `BearingInput` runtime 创建 binding，无量纲/direct-spool 必须显式提供 adapter/provider。 |

### E. `Signal` 替换

| ID | 新增特性目标 | 对应修改方案 |
| --- | --- | --- |
| F30 | 数值正确性改用显式调用 | `init/evaluate/advance/commit` 不再依赖 `Signal.lead_loop("...")` 触发关键计算或状态更新。 |
| F31 | 完成事件携带共享不可变数据 | `StepCompleted` 在物理提交后只发送一次，状态只能为 `NOT_CONFIGURED/RECORDED/PENDING`；恢复改发 `RecordingRecovered`，incomplete close 由 run receipt 表达。observer 异常默认隔离且 bounded。 |
| F32 | 观察者采用类型化 Protocol | 引入 `StepObserverProtocol.on_step_completed(event)`；不使用字符串属性名和 `getattr()` 反射回调，也不允许 observer 参与推进或 ledger。 |
| F33 | 组件拓扑由拥有者显式维护 | ALB 保存明确的 pads/valves，coupler 只保存 bindings 并派生 bearing 序列，不维护平行列表；拓扑改变后由 owner 重新初始化，不用父子 signal 树表达所有权。 |
| F34 | legacy Signal 仅保留一个兼容周期 | 如果外部旧调用仍依赖 signal，0.3.x 使用单独 `LegacySignalAdapter`；声明消费者清零且完成一个 minor 弃用周期后，最早在 0.4.0 移除。新代码不得新增 signal 依赖。 |
| F35 | 最终移除数值核心中的 `Signal` | 当声明的内部/外部消费者全部迁移并有参考保护后，从 film、thermal、bearing、ALB、rotor 和 coupler 核心路径删除 signal。 |

### F. 当前结果、时间历史和持久化

| ID | 新增特性目标 | 对应修改方案 |
| --- | --- | --- |
| F36 | 默认只保存当前不可变结果 | 不注入 recorder 时，组件只保留完成当前生命周期所需的最近快照，不无限增长时间历史。 |
| F37 | 时间历史显式选择 | 需要轨迹、控制历史或后处理时，由调用者明确注入 recorder；“计算一次”本身不再暗含历史写入。 |
| F38 | 显式内存 recorder | 升级 begin/record/end run 协议；实现 `StepRecordingStatus`、`RunCloseStatus`、`RecordableValue`、`InMemoryResultRecorder`、规范 SHA-256、NumPy scalar 规范化和 object-dtype 拒绝。 |
| F39 | 受限内存策略使用组合 decorator | ring buffer、固定间隔 sampling 和字段 filtering 分别实现可组合 recorder decorator，避免形成包含所有策略的巨型 recorder。 |
| F40 | 记录具有跨 run 幂等和失败恢复 | 唯一键为 `run_id + step_index`，时间规则复用 ledger。pending 时数值输出仍有效但默认阻止下一次 advance；恢复只重试记录。bounded recorder 使用有限 idempotency window，淘汰键返回 `ExpiredRecordKey`。 |
| F41 | 磁盘写入保持注入式 | workflow 把 recorder 的快照或最终 `ResultBundle` 交给 `ArtifactWriterProtocol`，writer 返回可核验 manifest；数值组件不决定路径。 |

### G. 兼容和迁移边界

| ID | 新增特性目标 | 对应修改方案 |
| --- | --- | --- |
| F42 | 当前 block 保留为内部兼容层 | 第一阶段不立即删除 `BearingBlock`/`DirectSpoolBearingBlock`，factory 可在内部使用它们，保证外部迁移可分步进行。 |
| F43 | block 与原生 runtime 行为一致 | 原生生命周期完成后，block 只做 DTO/能力转发或逐步退役；禁止出现 block 与 implementation 两套推进语义。 |
| F44 | 旧轴承通过显式 adapter 接入 | 对仍只有计算型 `output()` 的第三方轴承提供 `LegacyBearingAdapter`，并在类名和文档中明确其兼容性质。 |
| F45 | 旧控制器适配器继续限期存在 | `LegacyControllerAdapter` 只服务旧自定义控制器；所有仓库内置控制器继续使用原生严格生命周期。 |
| F46 | 兼容面固定版本和删除条件 | 0.3.x 保留并声明 adapter；最早 0.4.0 删除。迁移审计记录消费者、替代 API、弃用提示和清零证据，不建立永久双生命周期。 |

### H. 配置和构建语义

| ID | 新增特性目标 | 对应修改方案 |
| --- | --- | --- |
| F47 | 用户入口只接受当前 schema | 在实现 builder 前先固定配置语义；`build_alb_from_file()` 使用 `load_current_config()`，legacy 配置报出迁移命令，不在运行入口中宽松猜测。 |
| F48 | 配置可精确往返 | dimensional/nondimensional、controller none/PID/FuzzyPID、ALB/ALBSV 和 thermal 设置必须带类型标签精确 round-trip。`transient_enabled` 是默认 `False` 的严格 bool，typed/schema 拒绝 `None`，legacy 缺失/`None` 迁移为 `False`；servo 类型不得覆盖该值。 |
| F49 | 控制模式成为显式配置 | 用枚举/带标签字段区分闭环控制、无控制器和 direct-spool，避免从 `controller=None` 或类名推测含义。 |
| F50 | 单位制成为构建必需信息 | envelope 明确 `unit_system`；旧配置迁移时根据明确旧类型转换并在报告中记录来源。 |
| F51 | 依赖按拥有者注入且不配置反序列化 | `BearingBuildDependencies` 只含 controller/component factories；spool provider 属于 binding，recorder/observer 属于 coupling runtime，artifact writer 属于 workflow output。 |
| F52 | 尺度配置产生显式 adapter | 实现前冻结 `x_dim=x_nd*Sx`、`t_dim=t_nd*St`、`v_dim=v_nd*Sv`、`F_dim=F_nd*Sf` 参考并默认验证 `Sv=Sx/St`；residual 使用 definition ID，不假定统一比例。 |
| F53 | 所有迁移默认不覆盖源文件 | 新 schema 迁移、adapter 迁移清单和可能的 recorder 导出都另存，并返回来源、目标和摘要信息。 |

### I. 测试、参考和发布验收

| ID | 新增特性目标 | 对应修改方案 |
| --- | --- | --- |
| F54 | 配置到可运行对象的端到端测试 | 覆盖“读取当前配置 -> build -> READY -> step”，验证用户无需手动创建 block、envelope 或调用 `init()`。 |
| F55 | 单步与三阶段调用等价 | 对相同输入精确比较 `step()` 和 `input/evaluate/output`，并验证重复 `output()` 不重复求解或记录。 |
| F56 | 数值与 post-commit 状态测试 | 覆盖内部 NEW 转换、公开构造后的 READY、RUNNING、FAILED、`COMMITTED_RECORDING_PENDING`、owner 重新初始化、pending 恢复以及输入改变使旧输出失效；`MultiPad` 同样覆盖三阶段生命周期和只读输出。 |
| F57 | native 与旧参考数值一致 | 对 film、thermal、控制、ALB/ALBSV、ALBNN shell、MultiPad 聚合和 Hydrostatic 配置派生建立修改前参考；固定 CPU、device、dtype、依赖和随机种子的路径使用精确相等，GPU/并行路径另建有理由的容差参考。 |
| F58 | direct-spool 全链路测试 | 覆盖合法 `sx/sy`、复杂数/NaN/Inf/越界、时间不一致、失败封锁和重新初始化。 |
| F59 | 真实 ROSS coupling 回归 | 正式门禁必须覆盖真实 ROSS 4/6-DOF rotor、非零状态相关 bearing force、`previous_force/force` 插值、最终状态和时间长度；等价 mock 只能补充失败注入，不能替代。 |
| F60 | coupling 失败封锁和提交后故障测试 | 分别在 bearing、rotor、spool provider、结果构造、recorder 和 observer 阶段注入异常，覆盖 step 0 与后续步，区分提交前封锁与提交后诊断。唯一有效性源是 `CouplingStepRuntime`；post-commit 异常不得使已提交状态失效或重复物理推进。 |
| F61 | recorder 选择性测试 | 验证无 recorder 不增长历史；内存、ring buffer、降采样和字段筛选的步序、拷贝隔离及内存上界。 |
| F62 | Signal 移除边界测试 | import/AST 门禁禁止新数值模块依赖 `ALB.core.events.Signal`，legacy adapter 是唯一暂时允许位置。 |
| F63 | 数值、时间和内存性能门禁 | 每阶段先过精确参考；使用下文固定的机器身份、批量时间下限、预热、样本数、中位数/MAD 和峰值内存规则比较 film、thermal、ALB、ALBNN、coupling。 |
| F64 | 文档、类型和制品验收 | 同步 package overview、interface architecture、quickstart、API docstring、import map、strict mypy、wheel/extras smoke 和 detached release 证据。 |

### J. 2026-07-24 新增构建特性

| ID | 新增特性目标 | 对应修改方案 |
| --- | --- | --- |
| F65 | bearing 实例构造后即可计算 | ALB、ALBNN、harmonic、混合轴承、`MultiPad` 及兼容 runtime 在构造结束时处于 `READY`；内部组合仍可调用可重复的 `init()` 完成整体 session 重置。 |
| F66 | 中性动静压混合轴承 | 新增 `build_hybrid_bearing()`、`HybridBearing`、`NodimHybridBearing` 和 `HybridOrificeConfig`。未给节流器时执行动压油膜计算，给出构造期节流器时自动装配节流-压力耦合；不提供动压/静压模式字段。 |

## 分阶段实施顺序

### 2026-07-23 实施状态

| 范围 | 状态 | 主要实现 |
| --- | --- | --- |
| F47-F53、F01-F07 | 已实现 | 0.3 envelope、显式 control mode、非覆盖迁移、类型化 builder、配置文件入口、完整尺度对象 |
| F08-F20 | 已实现 | ALB/ALBSV/Nodim/ALBNN/harmonic 原生 DTO 生命周期、只读 output、诊断与失败封锁 |
| F36-F41 | 已实现 | run-scoped recorder、v1 规范摘要、pending 恢复、内存/ring/sampling/filtering 组合策略、writer 分离 |
| F21-F29 | 已实现 | `CoupledBearingBinding`、direct-spool provider、单位 adapter、`RotorLoadInput`、提交后发布顺序 |
| F30-F34、F42-F46 | 已实现 | 新 coupling 正确性路径不依赖 Signal；原生 ALB/ALBNN/harmonic 默认不写 Signal 历史；observer 直接调用 Protocol 方法，不使用字符串反射 |
| F35 | 延期到 0.4.0 | legacy Signal 仅保留给尚未清零的 film/thermal/rotor 消费者；AST 门禁禁止增加新消费者 |
| F54-F63 | 已实现 | 64 项 manifest、故障注入、recorder 选择性/内存上界、Signal AST、精确参考和五领域时间/峰值内存报告均已落地 |
| F64 | 已实现 | 文档、测试映射、26 个 strict 目标、564 节点、detached pytest、wheel/extras smoke 和可复现制品证据均已通过 |
| F02/F13/F16/F29/F33/F48/F54/F56/F57/F60 修订、F65-F66 | 已实现并纳入 manifest，待正式发布验收 | 类型化配置 builder、内部 envelope、自动 `READY`、构造期节流器混合轴承、binding-only coupling、正式 MultiPad runtime、thermal resolver 和针对性回归已落地；F65-F66 已加入 0.3 feature manifest |

66 项中 65 项已经实现；唯一未完成项仍是 F35。当前 manifest 已覆盖 F01-F66，
F65-F66 仍需要在下一次正式发布验收中从 detached 候选执行。F35 尚未物理删除全部旧 Signal，不是方案未确定，
而是 ADR-0001 要求至少保留一个 0.3.x minor
兼容周期并先取得消费者清零证据。旧 film/thermal/rotor 消费者尚未清零，因此不能在 0.3.0
提前删除兼容面；新代码不得再增加 Signal 依赖。

### 阶段 0：冻结新边界参考

- 五份 ADR 已全部 Accepted，架构决策门禁完成。
- 已固定当前 raw implementation、block、coupler、signal 历史、保存行为和跨单位转换。
- 新参考覆盖普通 ALB、direct-spool、thermal、ALBNN shell、真实 coupling 和异常路径，并继续复用既有真实 ROSS 4/6-DOF、Signal 回调顺序及全领域 v1 参考。
- `refs/review_fix_unaffected_reference_v1.json` 在本轮实现前冻结 PID 非饱和区、MultiPad 数值汇总和 Hydrostatic 速度派生，并由精确回归持续保护。
- 单独记录有意改变的生命周期/历史行为，数值数组仍要求精确一致。
- 阶段 0 已完成；后续不得覆盖这些 v1 参考。

### 阶段 1：先固定配置，再改善用户入口

- 先实施 F47-F53，再实施 F01-F07。
- factory 可以暂时在内部创建现有 block，因此先解决用户必须理解 adapter 的问题。
- 更新 quickstart，但不得提前宣称轴承 implementation 已原生严格化。
- 阶段 1 已完成：当前 schema、控制模式、非破坏迁移、类型化 builder、文件入口和显式完整尺度
  adapter 已落地；builder 内部仍使用临时 `LegacyBearingRuntimeAdapter`，原生生命周期属于阶段 2。

### 阶段 2：迁移轴承原生生命周期和协议

- 实施 F08-F20。
- 按 ALB、ALBSV、NodimALB、NodimALBSV、harmonic、ALBNN shell 顺序迁移。
- 每个实现独立提交并运行对应精确参考。

### 阶段 3：建立结果与 recorder 基础设施

- 实施 F36-F41。
- 先升级 recorder protocol 和 run/receipt DTO，再实现内存 recorder 与组合 decorator。
- 用独立测试固定 post-commit recorder failure、`COMMITTED_RECORDING_PENDING` 推进门禁、
  pending record、bundle digest、end_run、有限 idempotency window 和幂等重试，不依赖
  coupling 才验证。

### 阶段 4：统一 rotor-bearing coupling

- 实施 F21-F29。
- 先接普通 dimensional bearing，再加入 direct-spool provider，最后加入显式单位 adapter。
- 不在该阶段更改转子积分算法、bearing force 符号或 `previous_force/force` 插值顺序。
- 只实现失败封锁和发布原子性，不引入没有完整 checkpoint 的伪回滚 API。

### 阶段 5：清除 Signal 并收口兼容面

- 按 film、thermal、bearing、rotor、coupler 分域实施 F30-F35 和 F42-F46。
- 先把关键调用改为显式方法，再接入 observer，最后删除无消费者的 signal 连接。
- 0.3.x 保留已声明兼容 adapter；达到 ADR-0001 的清零条件后最早在 0.4.0 移除。

### 阶段 6：持续门禁和最终验收

- F54-F64 从每个阶段开始持续执行，不留到最后集中补测试。
- 最终阶段只收口 canonical test/import map、全量性能与峰值内存、wheel 和 detached 证据。
- 每阶段形成独立提交；失败通过 `git revert` 回退，不覆盖参考或移动既有标签。

## 性能门禁固定参数

F63 使用以下统一规则，避免短计时和环境漂移产生没有意义的 15% 比较：

1. 基线与候选必须在同一台机器、同一 power plan、同一 CPU affinity、同一 Python 环境中连续运行；
   报告记录 CPU 型号、逻辑核数、OS、Python、NumPy、SciPy、PyTorch、ROSS 和关键 optional
   dependency 版本。
2. 每个 case 至少执行 3 个不计时 warm-up 和 9 个 measured samples。
3. 调整 `work_units_per_sample`，使基线每个 measured sample 的中位时间至少为 50 ms；不足 50 ms
   时先增加批量工作量，不直接对微秒/数毫秒噪声应用比例门禁。
4. 时间报告至少包含 median、MAD、P25 和 P75。候选 median 超过基线 1.15 倍即暂停对应阶段分析。
5. 峰值内存使用同一测量工具和进程边界。只有候选同时满足“超过基线 1.15 倍”和“绝对增加超过
   16 MiB”时判定失败；否则记录为可观察变化。
6. GPU 或并行路径单独记录 device、线程/进程数和确定性设置，不与 CPU 串行参考混用。

## 完成标准

除 ADR 明确延期到 0.4.0 的 F35 外，只有同时满足以下条件，才能把相应目标标记为完成：

1. 普通用户从当前配置文件到第一次轴承输出不需要显式创建任何 block，并能在构造输入前通过
   `control_mode` 确认普通或 direct-spool 端口。
2. `step()` 已由契约和测试固定为无全局提交、无 recorder、无 observer 的单次计算组合。
3. 所有正式轴承实现的 `output()` 都返回同一不可变完成快照；重复调用不推进控制器、阀、film、
   thermal 或 recorder。
4. `RsRotorBearingCouple` 只消费正式协议和 `CoupledBearingBinding`，不检查 `signal`、具体实现类
   或组件 `save()`。
5. 正常结果严格按 candidate -> ledger commit -> 不可失败 publish 顺序公开；数值失败只产生
   failure snapshot，不发布未提交 candidate且不自动重算，API 不宣称存在 mutable 状态回滚。
6. 数值核心不再依赖 signal tree 完成计算、提交或正常历史记录。
7. 无 recorder 时不累计无界时间历史；注入 recorder 后使用 `run_id + step_index` 幂等记录和
   版本化 bundle digest。默认 pending 阻止下一步推进，只重试写入；bounded recorder 明确
   idempotency window。
8. recorder 失败仍发送一次带 pending status 的 `StepCompleted`；恢复时只发送
   `RecordingRecovered`。observer 默认异常隔离且不形成无界隐藏历史。
9. 当前端口输出、完整当前结果、时间历史和磁盘 artifact 四个接口可以独立使用和测试。
10. dimensional/nondimensional 与 direct-spool 边界均由显式类型、配置或完整尺度对象表达，输出
    metadata 可追溯尺度来源。
11. 所有新参考、全量 pytest、分层 mypy、固定机器性能/峰值内存、wheel 和 detached 验收通过，
    测试前后 tracked 状态不变。
12. `SURROGATE_TRAIN` 和 `PAPER_WORK` 的调用修改在各自项目独立审计、独立提交，不通过复制 ALB
    源码完成。

## 明确非目标

- 不在接口迁移提交中修正新发现的物理方程或数值算法问题。
- 不恢复已经删除的 0.1 平铺 import facade。
- 不让 recorder 取代 artifact writer，也不让 artifact writer进入数值核心。
- 不默认记录全部大数组或全部局部迭代历史。
- 不使用 `Signal`、observer 或 recorder 作为物理时步提交者。
- 不为 mutable film、thermal 或 rotor 声称不存在的 checkpoint/rollback 能力。
- 不把本轮公共语义变化作为 0.2.0 的无提示补丁；目标版本和兼容周期按 ADR-0001 执行。

## 与现有文档的关系

- 当前模块和公共接口地图：`docs/alb_package_overview.md`。
- 当前稳定接口契约：`docs/interface_architecture.md`。
- 当前实际可运行示例：`docs/alb_albnn_quickstart.md`。
- 下一阶段架构决定及复审状态：`docs/adr/README.md`；五份 ADR 均为 Accepted。
- 0.1 到 0.2 迁移：`docs/migrations/0.2.0.md` 和机器 import map。
- 当前阶段、风险和近期工作：`docs/current_state.md`。
- 本文：只定义下一阶段要实现什么、如何分段和怎样验收。
