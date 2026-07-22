# ALB 包概览

## 文档角色

- 角色：稳定 package 导览。
- 目的：说明 `ALB/` 包的模块地图、主要公共接口分组和 package 边界。
- 允许更新：公共 API / 模块归属变化、package 边界说明、首次阅读导览。
- 禁止更新：实验运行状态、每日维护历史、训练进度、原始证据。
- 更新时机：公共 API、模块归属或 package 边界发生变化时。
- 事实来源 / 相关文档：
  `docs/daily_maintenance/daily_doc_update_index.md`、
  `docs/interface_architecture.md`、
  `docs/migrations/0.2.0.md`。

本文是 ALB 0.2.0 package 的首次阅读导览。接口生命周期、依赖方向和单位制规则以 `docs/interface_architecture.md` 为准；从 0.1 迁移时使用 `docs/migrations/0.2.0_import_map.json`。

## 顶层边界

`ALB.__init__` 刻意保持很窄，只导出：

- `__version__`
- `UnitSystem`
- `StepContext`
- `ConvergenceStatus`
- `ComputationalBlock`、`SolvableBlock`、`EvaluableBlock`、`CommandBlock`、`AdvancingBlock`

领域实现不从 package 根导出。调用者必须选择明确 namespace，例如：

```python
from ALB.physics.bearing import HydrostaticBearing
from ALB.control.pid import PID
from ALB.dynamics.rotor import RossRotor, RotorDofLayout
from ALB.surrogate.inference import albnn
from ALB.systems.alb import BearingBlock, DirectSpoolBearingBlock, nodim_alb
```

## 模块地图

| Namespace | 职责 | 代表模块或能力 |
| --- | --- | --- |
| `ALB.contracts` | 纯接口、DTO、值对象和结果契约 | block Protocol、轴承/控制/阀/转子端口、`UnitSystem`、`StepContext`、`ConvergenceStatus`、`ResultBundle`、artifact 协议 |
| `ALB.core` | 与领域和文件系统无关的运行时基础 | 显式计算块状态机、时步 ledger、时间迭代、验证和事件 |
| `ALB.core.fem` | 有限元基础 | 节点、单元、网格、边界 |
| `ALB.core.numerics` | 通用数值工具 | 数组、静态/动态矩阵、阻尼、迭代工具 |
| `ALB.config` | 按领域分类的配置契约 | `film`、`hydraulics`、`gas`、`thermal`、`control`、`system`、`surrogate`、配置迁移 |
| `ALB.physics.film` | Reynolds 油膜求解 | mesh、film solver、压力场和容量辅助 |
| `ALB.physics.hydraulics` | 液压与节流 | orifice 模型和流量关系 |
| `ALB.physics.bearing` | 轴承组合 | 静压轴承、四瓦轴承和显式适配器 |
| `ALB.physics.gas` | 气体轴承 | gas-film solver |
| `ALB.physics.thermal` | 热耦合 | 热模型、黏温/尺度转换和热惯性状态 |
| `ALB.control` | 控制和阀 | PID、Fuzzy、LQG、状态空间、降阶、伺服阀和严格端口 blocks |
| `ALB.dynamics` | 转子与耦合 | `RotorDofLayout`、rotor、coupling、orbit、FFT/KC 识别 |
| `ALB.surrogate` | 部署侧代理模型 | features、networks、scalers、inference、versioned model package、非破坏迁移 |
| `ALB.surrogate.training` | 训练侧公共能力 | config、data、loss、transform、report、run 和 ALBNN 专用远程队列 |
| `ALB.systems.alb` | 顶层 ALB 系统装配 | builder、非线性 ALB、严格 `BearingBlock`、direct-spool 适配器、谐波线性轴承及 `K/C/G_xv` |
| `ALB.infrastructure` | 外部副作用 | UTF-8 配置 IO、日志、`SmtpNotifier`、artifact writer、generic remote engine |
| `ALB.workflows` | 可执行流程和后处理 | ALB workflow、DoE、配置装配、命名、绘图、后处理和顶层执行 |

## 依赖方向

稳定依赖方向为：

```text
contracts
   ↓
core
   ↓
config / physics / control / dynamics / surrogate
   ↓
systems
   ↓
workflows

infrastructure 仅在需要 IO、通知、持久化或远程执行的边界被注入
```

`contracts` 不依赖领域实现，`core` 不依赖 infrastructure；数值 namespace 不得直接导入文件系统 exporter。循环依赖和禁止 import 由 `tests/validation/test_import_boundaries.py` 检查。

## 公共接口组

### 计算块与端口

`ALB.contracts` 提供 `BearingInput/BearingOutput`、`ControlInput/ControlOutput`、`ValveInput/ValveOutput`、`RotorLoadInput/RotorState`。DTO 在构造时验证形状、有限性、非负时间和单位制，并冻结数组副本。

严格 block 遵循 `input()`、显式计算、`output()` 的生命周期。非线性 ALB 和谐波线性轴承都可通过 `ALB.systems.alb.BearingBlock` 系列暴露同一个轴承端口协议。已经是归一化阀芯状态的 `sx/sy` 应通过 `DirectSpoolBearingInput(BearingInput, ValveOutput)` 交给 `DirectSpoolBearingBlock`；它不会再次引入阀动态。

`ValveOutput.spool` 和 direct-spool 节流器输入必须是 `[-1, 1]` 内的有限标量，非法值会立即失败，
不会静默沿用旧阀芯状态。`BaseLti`/`BaseDlti.output()` 每次只返回当前输出向量；完整状态和输出
历史分别从 `xout`、`yout` 读取。`PID.init()` 与 `FuzzyPID.init()` 会恢复到新实例等价状态。
ALB 装配和谐波控制路径通过同一个控制器生命周期适配器接入：提供 `evaluate()` 的严格控制器按
`input()`、`evaluate()`、`output()` 执行；仅提供旧式 `input()`、`output()` 的 LQG、重复控制器
或自定义控制器只调用一次 `output()`，不会因缺少 `evaluate()` 而失败。`ALBHarmonicLinear`
可以通过 `controller=` 注入带 `init()` 的控制器实例，也可以通过 `controller_factory=` 在每次
初始化时创建新的旧式控制器；二者都经过完整的构造、基态预热、多步运行和重新初始化门禁。
harmonic 重新初始化从入口即使旧运行时失效，只有控制器创建/复位和阀预热全部成功后才恢复
有效状态；任一步失败后，`input()`、`output()`、`results`、`save()`、`xv` 和 `t` 都拒绝暴露
可能混合的新旧状态，必须再次成功调用 `init()`。正常运行中的控制器计算、命令形状转换、任一
阀推进或结果记录只要抛出异常，也通过独立的 runtime failure guard 立即执行相同失效语义；
系统不会在控制器与双阀可能不同步的状态上重试。

`ALBConfig.switch` 是永久控制许可：配置为 `False` 后，非负时间输入不会自动把控制重新打开。
`turn_on_at()` 只在永久许可为 `True` 时安排延迟启动，并在每次输入时重新计算当前启用状态。
普通 `ALB` 没有控制器时输出零阀命令；需要直接指定阀芯位置时使用 `ALBSV` 或对应的
direct-spool 端口。

`RsRotorBearingCouple.init()` 把时间网格首点登记为只读初始快照，`solve()` 只对后续目标时刻
推进。时步 ledger 要求序号恰好加 1、时间增量与固定 `dt` 一致，因此 `t=0` 不再对应
已经推进到 `dt` 的转子状态。
中途异常会使 coupler 整体失效；此后 `advance()`、`output()`、`results` 和 `save()` 都拒绝
暴露可能只推进了一部分的状态，必须显式 `init()` 后才能继续。
初始化后调用 `add_bearing()`、`add_static_force()`、`add_unbalance()` 或 `add_gravity()` 修改
耦合拓扑也会立即使 coupler 失效；重新 `init()` 会重建节点映射后才允许读取或推进。

### 配置

配置从 `ALB.config.<domain>` 显式导入。`alb-migrate-config` 和 `tools/migrations/migrate_config_0_2.py` 只读旧 JSON5，并把 0.2 schema 另存为 UTF-8 文件；不会覆盖源配置。旧文件若无法按 UTF-8 解码，迁移器会显式警告并临时尝试 GBK/CP936，输出仍统一写为 UTF-8。

`ALBConfig.to_dict()` 与 `NodimALBConfig.to_dict()` 固定写出
`"controller": "PID" | "FuzzyPID" | "none"` 类型标签；`from_dict()` 据此恢复具体配置类型和
非默认参数。`controller_config=None` 能稳定往返为无控制器配置，缺少显式标签的旧配置仍保留
历史默认 PID。带标签的嵌套 `controller_config` 使用严格字段白名单：标签、对象类型或字段集合
冲突时立即报错；只有没有嵌套 payload 的旧式顶层平铺配置保留宽松迁移解析。

`ALBSV`、`NodimALB` 和 `NodimALBSV` 省略 `alb_config` 时会为每个实例新建配置，配置中的
`gxy`、`gxyt` 和嵌套对象不会通过函数默认参数在实例之间共享。

`ALB.physics.hydraulics.CSOrifice` 与 `NodimCSOrifice` 的 0.2 契约固定为零泄漏，
`q_leak` 只能取 `0.0`；配置或直接求解传入非零值会立即抛出 `ValueError`。公共腔压力通过同一
单调质量守恒标量方程求解，供油、回油、反向流和零供油压力不再切换求解器；油膜装配使用该
标量方程的隐式解析导数。

### ALBNN

部署入口位于 `ALB.surrogate`。0.2 model package 使用 manifest、固定 artifact 名和 SHA-256 校验；加载 pickle scaler 时必须显式声明信任。旧 `ALB.nn` pickle 不作为运行时兼容面，先使用带 `--trust-legacy-pickle` 的 `alb-migrate-surrogate` 或 `tools/migrations/migrate_surrogate_0_2.py` 迁移可信本地文件。迁移器把已知旧 scaler 类重写到当前 namespace，默认不覆盖源文件。

thermal ALBNN 的实际输入列、feature set、target transform 和模型选择以 model package metadata 及 `../SURROGATE_TRAIN/docs/albnn_training_brief.md` 为准，不在 package 根硬编码。
距离搜索、局部回归等分析若需要网络的真实缩放输入，应调用已加载模型的 `transform_inputs(frame)`；不得依赖私有 `_model_frame` 或自行重复 scaler/feature 逻辑。C4 wrapper 会先完成规范象限变换。

### 结果与持久化

数值模块通过 `result_snapshot()` 生成 `ResultBundle`。写文件由 workflow 注入 `ArtifactWriterProtocol`；`ALB.infrastructure.persistence.DirectoryArtifactWriter` 返回含相对路径、媒体类型、字节数和 SHA-256 的 `ArtifactManifest`。纯数值结果对象不直接选择目录或 exporter。

### 远程执行

通用 SSH、PowerShell、Task Scheduler、launch 和 monitor helper 位于 `ALB.infrastructure.remote`。ALBNN queue/start/status 位于 `ALB.surrogate.training.remote`。外部 wrapper 可以调用这些实现，但远程队列的实时状态仍由所属项目的 current-status 文档维护。

## Optional extras

| Extra | 领域依赖 |
| --- | --- |
| `film` | Matplotlib、scikit-fem |
| `control` | python-control、Matplotlib、scikit-fuzzy |
| `dynamics` | Matplotlib、ROSS |
| `surrogate` | Matplotlib、scikit-learn、PyTorch |
| `io` | JSON5 |
| `all` | 全部运行时领域依赖 |
| `test` | build、import-linter、mypy、pytest |

缺少 optional dependency 时，namespace 会给出对应 extra 的安装提示。wheel 和隔离安装证据位于 `docs/migrations/0.2.0_build_acceptance.json`。

## 不兼容边界

- 旧平铺模块已经物理删除；不存在一个版本周期的 facade。
- `StaicLoad` 更名为 `StaticLoad`，`dynmaic` 更名为 `dynamic`，`rotor_respone` 更名为 `rotor_response`。
- `RossRotor.output()` 不再隐式推进；使用 `advance()` 和 `current_state()`。
- `RossRotor.current_state(node=...)` 与节点载荷入口共用严格节点规范化；布尔值和浮点数不会再被静默转换为整数节点。
- `RsRotorBearingCouple` 的首点是初始快照，包含 `num + 1` 个采样点的网格只推进 `num` 次。
- `BaseLti`、`BaseDlti`、`PID` 和 `FuzzyPID` 使用 `input()` → `evaluate()` → `output()`；`output()` 只读取已完成快照，重复读取不再推进状态、积分或写历史。
- `ServoValve2` 仍保留旧式 `input()` 内计算语义以兼容既有调用者；其 `solve()` 只读取该次已完成结果，不会再次调用底层 LTI 的 `evaluate()`。严格阀端口继续使用 `ValveBlock`。
- 4/6-DOF ROSS 节点映射统一通过 `RotorDofLayout`；`result_uxy()` 与 LQG 执行器、传感器和扰动映射不再假定固定 4-DOF 步长。
- 旧结果树保存方法和数值模块内部 exporter 已删除；保存必须经过 artifact writer。
- 数值实现内部仍可能保留用于冻结行为的旧参数解析或适配代码，但这些不是 0.2 推荐公共 import 面。

完整的 65 模块、479 公共定义迁移表见 `docs/migrations/0.2.0_import_map.json`。
