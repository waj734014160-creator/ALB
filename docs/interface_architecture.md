# ALB 模块分类与接口架构

## 文档角色

- 角色：稳定模块边界与接口协议说明。
- 目的：定义 ALB package 的依赖方向、通用模板、领域协议、单位制边界、兼容策略和验证入口。
- 允许更新：模块分类、接口契约、兼容边界、依赖规则、单位制规则和稳定验证入口。
- 禁止更新：实时运行状态、单次实验指标、训练进度、临时日志和未验证的迁移结论。
- 更新时机：通用接口、模块边界、推荐导入路径或兼容策略变化时。
- 事实来源 / 相关文档：
  `ALB/contracts/`、
  `ALB/core/`、
  `ALB/systems/alb/ports.py`、
  `tests/unit/contracts/`、
  `tests/validation/test_import_boundaries.py`、
  `docs/alb_package_overview.md`。

本文定义 ALB 0.3.0 的稳定接口架构。0.2 已完成 namespace 重构；0.3 进一步固定用户 builder、原生 runtime、recorder、observer 和 coupling 边界。

## 架构原则

1. package 根只提供最基础契约，不聚合领域实现。
2. `contracts` 和 `core` 保持轻量，不依赖物理领域或外部副作用。
3. 每个领域只机械迁移实现、接入 DTO 和改写 import；方程、矩阵装配顺序和迭代准则不在重构提交中改变。
4. 文件系统、SMTP、配置文件和远程工作站调用只存在于 infrastructure 或 workflow 边界。
5. 顶层 coupler/workflow 是唯一物理时步提交者；子模块只返回局部结果和收敛状态。
6. 单位制必须显式声明，禁止用 `unspecified` 或隐式猜测完成跨单位制调用。

## 依赖层次

```text
ALB.contracts
    ↓
ALB.core
    ↓
ALB.config ── ALB.physics / ALB.control / ALB.dynamics / ALB.surrogate
                                      ↓
                              ALB.systems.alb
                                      ↓
                                ALB.workflows

ALB.infrastructure 通过 Protocol 注入需要副作用的边界
```

强制规则：

- `contracts` 不导入 `core`、领域实现、systems、workflows 或 infrastructure。
- `core` 不导入 physics、control、dynamics、surrogate、systems、workflows 或 infrastructure。
- physics、control、dynamics 和 surrogate 的数值代码不直接依赖 exporter、SMTP 或远程执行。
- systems 可以组合领域组件，但不反向成为领域底层依赖。
- workflows 可以协调完整任务并提交物理时步。
- namespace 图必须无循环；验证入口为 `tests/validation/test_import_boundaries.py`。

## 计算块契约

`ComputationalBlock[InputT, OutputT]` 保留 Simulink 风格的三个操作，但职责严格分离：

```python
block.input(dto)       # 校验并锁存输入，同时使旧输出失效
block.evaluate()       # 或 solve()/compute_command()/advance()
result = block.output()  # 只读取已经完成的结果
```

不同语义对应不同 Protocol：

| Protocol | 显式计算方法 | 典型组件 |
| --- | --- | --- |
| `SolvableBlock` | `solve()` | 迭代求解器 |
| `EvaluableBlock` | `evaluate()` | 轴承、阀、原生控制器和代数模型 |
| `CommandBlock` | `compute_command()` | 接收 `ControlInput` DTO 的 `ControllerBlock` 端口适配器 |
| `AdvancingBlock` | `advance()` | 带状态的转子或时间推进器 |

`step(dto)` 只组合 `input()`、显式计算方法和 `output()`，不提交物理时步。以下情况必须抛出 `RuntimeError`：

- 从未完成计算就调用 `output()`。
- 已有结果后重新调用 `input()`，但尚未重新计算就调用 `output()`。

`ALB.core.computation` 提供统一状态机基类；领域 adapter 不应复制状态管理逻辑。某些机械迁移后的实现内部仍保留旧求解调用形式以冻结数值行为，但推荐公共端口必须由严格 block adapter 暴露。

带内部状态的原生运行时还实现 `RuntimeLifecycleProtocol`，并复用
`ALB.core.lifecycle.RuntimeLifecycle`：

```text
NEW --init--> READY --input/evaluate--> RUNNING
  ^              |                         |
  |              +---- execution error ----+--> FAILED
  +---------------- successful init --------------+
```

`FAILED` 是终止性状态：不得继续锁存输入、推进、读取结果或保存；只有成功 `init()` 才能恢复。
`output()` 返回调用方拥有的快照，修改返回数组不得改变下一次读取。Harmonic、coupler、PID、
LQG、重复控制器和伺服阀使用同一状态语义，领域代码不再各自发明布尔标记组合。

## 标准 DTO

`ALB.contracts.ports` 定义：

- `BearingInput` / `BearingOutput`
- `ControlInput` / `ControlOutput`
- `ValveInput` / `ValveOutput`
- `RotorLoadInput` / `RotorState`

构造时统一执行：

- 二轴向量必须为 `(2,)`；多节点转子量允许 `(n, 2)`。
- 所有数值必须有限。
- 时间必须有限且非负。
- 转子节点数量必须与 `node_links` 匹配，节点索引必须为非负整数。
- 输入数组复制后设为只读，避免调用方在锁存后原地改变含义。
- `unit_system` 必须可转换为合法 `UnitSystem`。

DTO 与兼容型原生入口共用 `ALB.core.validation`：任何 complex 输入都在转为 float 前拒绝，NaN、
Inf、布尔时间、错误形状和错误长度使用一致的异常语义。验证函数总是生成自有 `float64` 数组，
避免调用方在锁存后修改原始内存。

## 单位制

`UnitSystem` 只有：

```text
dimensional
nondimensional
```

不存在 `unspecified`。每个集成边界必须显式比较单位制；跨单位制转换需要显式尺度对象或
adapter。不得根据数值大小、变量名或调用路径推测单位。

`BearingScaleSet` 把尺度统一定义为“一个 nondimensional unit 对应的 dimensional 值”，并要求
`Sv = Sx / St`。`BearingUnitAdapter` 经统一 dimensional domain 分别转换位移、时间、速度、力和
压力；归一化阀芯值不使用物理位移尺度。`descriptor()` 使用基础类型记录 scale ID、来源、全局和
局部 `StepContext`、`scale_definition` 及实际 `applied_transform`，可直接进入结果摘要。

## 时步和收敛

`StepContext` 使用 `step_index`、`time`、正 `dt` 和 `unit_system` 标识一个物理时步。`ALB.core.steps.StepCommitLedger` 拒绝重复或乱序提交。

只有顶层 coupler/workflow 可以调用 `commit_step(StepContext)`。轴承、阀、控制器、热模型和转子子组件只报告局部 `ConvergenceStatus`，不得分别写一条全局步记录。这样一个物理步无论包含多少局部迭代都只提交一次。

## 轴承与谐波能力

`BearingProtocol` 保持最小计算端口，`BearingRuntimeProtocol[InputT]` 增加初始化、生命周期、收敛和诊断出口。`ALB.systems.alb.build_alb()` 与 `build_direct_spool_alb()` 隐藏 0.3.x 兼容 block；`HarmonicBearingBlock` 额外正式公开：

- `K`：2 x 2 刚度矩阵。
- `C`：2 x 2 阻尼矩阵。
- `G_xv`：复数 2 x 2 阀芯到轴承力传递矩阵。

属性返回数组副本，调用者不能通过原地写入篡改组件内部系数。

## 控制、阀和转子

- 原生控制器实现 `ControllerProtocol`，运行时顺序是 `input(time, error)`、`evaluate()`、`output()`；`output()` 不计算。
- 需要 DTO 端口时使用 `ControllerBlock`，由它以 `compute_command()` 封装原生控制器的一次严格运行。
- 仅有计算型 `output()` 的旧自定义控制器不满足 `ControllerProtocol`，必须显式经 `LegacyControllerAdapter` 接入；该兼容层将在下一破坏式版本移除。
- 伺服阀实现 `ServoValveProtocol`，计算动作是 `evaluate()`。
- 转子实现同时继承 `RuntimeLifecycleProtocol` 的 `RotorProtocol`，状态推进是 `advance()`。
- `RossRotor` 的载荷输入只锁存，`advance()` 是唯一公开推进入口；`current_state()`、`output()`、
  结果提取和保存只读取已完成快照。推进失败后进入 `FAILED`，必须重新 `init()`。
- 转子结果/保存树组装位于 `ALB.dynamics.rotor_results`；谐波系数契约和资源加载位于
  `ALB.systems.alb.harmonic_coefficients`，避免运行时同时承担持久化和配置 IO。
- 顶层 rotor-bearing coupler 负责一次 `advance()` 后的一次全局 step commit。

## 结果和副作用边界

统一结果形式为 `ResultBundle`，通过 `result_snapshot()` 得到不可变快照。保存必须注入 `ArtifactWriterProtocol` 并返回 `ArtifactManifest`：

```python
from pathlib import Path

from ALB.infrastructure.persistence import DirectoryArtifactWriter

writer = DirectoryArtifactWriter()
manifest = writer.write(bundle, Path("outputs") / "case_001")
```

具体签名以 `ArtifactWriterProtocol` 和 writer 实现为准。manifest 可检查相对路径、字节数、媒体类型和 SHA-256。数值模块不得直接依赖 `DirectoryArtifactWriter`，也不得自行决定磁盘目录。

旧结果树仅作为 `ALB.contracts.result_tree` 中的纯内存数据契约保留；旧 pickle save/load 和内部 exporter 不属于 0.2 公共面。

## 配置和 model package 迁移

- 当前配置文件使用 `ALB.config.schema.ALBConfigEnvelope`，schema 版本固定为 `0.3.0`，并显式保存 `control_mode=controlled|none|direct_spool`。
- `ALB.config.legacy.migrate_legacy_alb_config()` 是旧平铺配置到当前 envelope 的单向转换；当前
  `load_current_config()` 不接受无版本 legacy payload。
- legacy JSON5 使用 `alb-migrate-config` 另存；禁止原地覆盖。`ALB.workflows.build_alb_from_file()` 只接受当前 envelope，不执行宽松 legacy 推断。
- legacy ALBNN checkpoint/scaler 使用 `alb-migrate-surrogate` 或 `tools/migrations/migrate_surrogate_0_2.py` 生成带 manifest 和 digest 的 package。
- pickle 加载需要调用者显式设置可信开关；不接受来源不明的 model package。
- 旧 pickle 中的 `ALB.nn.*` module-qualified 类型不保证直接反序列化。

## 兼容策略

0.3 不恢复旧 import facade。完整 0.2 历史映射以 `docs/migrations/0.2.0_import_map.json` 为准。以下兼容只存在于新 namespace 内部，不构成长期 API 承诺：

- 用于保持数值行为的旧参数名称解析。
- 旧 JSON5 到 0.3 schema 的只读转换。
- 旧模型 artifact 到 versioned package 的非破坏复制。
- 数值实现到强类型端口的 adapter。

任何数值或物理修正必须独立于机械重构提交，并生成新的 v2 行为参考。

## 稳定验证入口

```powershell
E:/Anaconda2023/envs/ALB/python.exe -m pytest tests/unit/contracts -q
E:/Anaconda2023/envs/ALB/python.exe -m pytest tests/unit/systems/test_bearing_ports.py -q
E:/Anaconda2023/envs/ALB/python.exe -m pytest tests/regression/test_full_repo_refactor_references.py -q
E:/Anaconda2023/envs/ALB/python.exe -m pytest tests/validation/test_import_boundaries.py -q
E:/Anaconda2023/envs/ALB/python.exe -m pytest tests/validation/test_optional_dependency_errors.py -q
E:/Anaconda2023/envs/ALB/python.exe tools/validation/run_layered_mypy.py
```

全量测试、类型、性能和 wheel 证据见 `docs/current_state.md` 及 `docs/migrations/` 下的正式报告。
