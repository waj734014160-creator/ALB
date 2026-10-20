# ALB 仿真配置字段参考

参考来源：`ALB/api/simulation.py`、`ALB/api/_config_fields.py` 和 `ALB.dynamics` 显式导出的高级类型。

## 两种构造方式

文件入口 `ALB.load_simulation_config(path)` 读取严格 UTF-8 JSON5，构建并返回
`SimulationConfig`；`ALB.simulation_from_file(path)` 再把它包装成可运行的
`RotorBearingSimulation`。文件配置当前只接受 `rotor.model: "ross_excel"`，因此
需要用户提供一个实际存在的 ROSS Excel 资源和至少一个轴承 JSON5 文件。

程序化入口 `ALB.SimulationConfig(...)` 接受已经满足 `RotorProtocol` 的量纲转子、
`BearingMount` 对象、载荷和 `HistoryPolicy`。记录器、observer 及后提交失败策略只能通过
高级 `ALB.dynamics.CouplingRuntimeDependencies` 对象提供；它们不能序列化进普通 JSON5。
程序化转子的 `rotor.dt` 必须与 `time_step` 完全相等，`rotor.unit_system` 必须为
`dimensional`。

## 文档、include 与资源边界

顶层文档固定使用 `schema_version: "0.4.0"` 和 `kind: "simulation"`。
`includes` 只能引用同一外层文档目录下的相对 `simulation_profile` 文件；绝对路径、
越过根目录的路径、重复 include 和循环 include 会在构建前拒绝。profile 按列表顺序
深度合并，当前文档的 `spec` 最后覆盖。

`rotor.path` 和 `history.directory` 会解析后检查仍位于外层 simulation 文档目录内。
`mounts[].bearing` 也是相对 simulation 文档的轴承配置路径；轴承文档内部的 profile、
模糊规则、子瓦和模型包继续按该轴承文档自己的资源根处理。示例中的占位路径不是随包
提供的数据资产，必须替换为用户自己的文件。

## 时间与提交语义

`time_grid.steps` 表示初始状态之后的推进次数，因此未下采样的内存历史通常有
`steps + 1` 个提交样本。仿真对象是一次性的：第一次 `run()` 后不能再次运行，重复计算
需要重新构建。物理步提交后若 recorder、observer 或磁盘历史失败，运行不会重复该物理
步；`SimulationError.partial_result` 和 `failure_snapshot` 保存已经提交的可审计边界。

## 控制周期与步长调整

主动轴承可在 `control.control_period` 声明控制器采样周期 `Ts`（轴承局部时间单位，
经 mount 的 unit adapter 换算为全局秒）。转子、mount、`MultiPad`、阀和热模型仍共享
同一个全局步长 `h`，只有控制器每 `m = Ts / h` 步采样一次并保持指令。程序化
`rotor.dt` 与各轴承 `time_step` 首先必须与请求的 `time_step` 一致；之后若 `h` 不能
整除 `Ts`（相对容差 `1e-9`），`SimulationConfig` 保持 `Ts` 不变并按下式调整：

```text
h' = Ts / ceil(Ts / h)        （h > Ts 时 h' = Ts）
steps' = m * ceil(T / Ts)      T = steps * h，m = Ts / h'
```

调整后的结束时间满足 `T <= T' < T + Ts`，`T` 恰为 `Ts` 整数倍时不变。全部轴承配置
按 `h'` 重新校验（引用外部文件的 `MultiPad` 子瓦无法自动改写，直接报
`ConfigurationError`）。全部校验通过后先发出 `ALB.TimeStepAdjustedWarning`，再对
同一个转子对象原位重新离散并重置状态；把该警告提升为异常时配置被拒绝，转子保持
不变。转子须提供 owner hook `_retime_for_owner`（`RossRotor` 提供），重新离散失败时
在警告之后报 `ConfigurationError`。转子被一个配置重新离散后，仍持有它、按原步长
校验的另一个配置在构建仿真时以 `ConfigurationError` 拒绝，因此每个配置应使用独立的
转子对象。构造后的 `time_step`、`steps`、`rotor` 和 `mounts`
保存实际值；`time_step_adjustment` 记录请求值、`Ts`、`h'`、`m`、步数、结束时间和
规则，`control_periods` 按声明列出 `mount`、配置路径、局部/全局周期和 `m`。配置了
多个不同 `Ts` 时只允许 `h` 同时整除全部周期，不做自动调整。`HistoryPolicy` 的
`downsample` 与 `capacity` 继续按提交索引计数，步长改变后对应的物理时间间隔随之
改变。

## 耦合积分器

`time_grid.integrator` 缺省为 `"staggered"`：轴承力滞后一步、转子精确推进，结果与
0.4.5 默认路径逐位一致。`"ros2"` 选择可选的两级 Rosenbrock-W 积分器，在两个 stage
状态同步计算轴承力，转子状态和主动轴承阀状态组成一个耦合状态；它不替代默认算法。
0.4.6 中 ROS2 标记为**功能不完善**（实验性），正式计算继续使用 `staggered`，已知缺口见
0.4.6 迁移说明。
`time_grid.jacobian_refresh` 只在 `"ros2"` 下接受：`null` 冻结整个运行的 Jacobian，
正整数 `N` 每 `N` 步刷新一次，`"control_period"` 在任一阀驱动主动轴承（`pid`、
`fuzzy_pid` 或 `uncontrolled`）的每个控制器采样时刻刷新，没有这类轴承时每步刷新。
程序化入口用 `SimulationConfig(integrator="ros2", ros2=ALB.dynamics.Ros2Options(...))`
设置同样的选项及 `jacobian_state`、中心差分步长，并可用 `initial_rotor_state` 给出
完整初始转子状态；这两个状态向量都保存为浮点数元组。`jacobian_state` 短于转子状态，或在
没有阀驱动主动轴承时不等于转子状态长度，构造时报 `ConfigurationError`；有阀驱动
主动轴承时完整耦合长度在 `run()` 的 reset 阶段检查。

ROS2 需要连续时间 `RossRotor`，支持无热模型的液膜、气膜、surrogate（固定或外部
阀芯）、`MultiPad`，以及无热模型的主动轴承（`pid`、`fuzzy_pid`、`uncontrolled` 和
`external_spool`）。`MultiPad` 子瓦只能是无热液膜、气膜或固定阀芯 surrogate；含主动
子瓦、外部阀芯子瓦或任何层级带热模型的轴承在构造时以 `ConfigurationError` 拒绝。
外部 spool provider 每步在已提交状态采样一次并在该步内零阶保持，因此该通道一般为
一阶，只有 provider 指令在步长网格上分段常数时才保持二阶。staggered
路径的控制器在 `t_k` 采样上一步提交的状态，阀输入在相邻求值间一阶保持插值；ROS2
在 `t_k` 采样该时刻提交的状态，阀指令为零阶保持。因此同一 `Ts` 下两种积分器的受控
响应只在 `O(h)` 意义下一致。

只有 `integrator` 为 `"ros2"` 或 `"predictor_corrector"`、声明了控制周期或给出 `initial_rotor_state` 时，
`SimulationResult.metadata` 才额外包含 `integrator`、`time_step`、`control_periods`、
`time_step_adjustment`、`ros2_options` 和 `initial_rotor_state`；用户状态向量只记录为
`"user-supplied"`，默认路径的元数据保持不变。`SimulationResult.write()` 可写出这些
嵌套只读映射。完整适用边界见 [0.4.6 迁移说明](../migrations/0.4.6.md)。

`"predictor_corrector"`（0.4.7）是保持轴承黑箱的预测-校正分区耦合：每步预测界面力，
用“从已提交状态出发、不提交”的轴承试算校正并迭代到界面一致，最后每个轴承只提交
一次，不需要导数，也不拆分模型。无副作用的轴承用 `probe_force` 试算；热模型、主动
轴承及含它们的 `MultiPad` 通过存档/回退协议走正常生命周期试算并立即回退，控制器仍
按提交次数每 `m` 次运行一次。选项写在 `time_grid.predictor_corrector`（只能与该积分器
同时出现，省略时用全部默认值），程序化入口为
`SimulationConfig(integrator="predictor_corrector",
predictor_corrector=ALB.dynamics.PredictorCorrectorOptions(...))`。`mode: "pece"` 时其余
迭代选项只校验不起作用。唯一拒绝的拓扑是 `MultiPad` 内需要外部阀芯的子瓦；转子需要
提供 `_propagate_trial` 等 owner hook（连续或离散 `RossRotor`）。迭代未收敛时，
`on_nonconvergence: "warn"` 提交最后一次迭代并在每次运行发出一次
`ALB.CouplingIterationWarning`，`"raise"` 以 `SimulationError` 结束运行；试算失败时轴承
先回到提交状态，再按失败封存契约报告。只有该积分器在结果元数据中额外写入
`predictor_corrector_options` 和 `predictor_corrector_diagnostics`。完整说明见
[0.4.7 迁移说明](../migrations/0.4.7.md)。

## 载荷

- `static` 在一个节点施加固定 `[Fx, Fy]`，单位 N。
- `gravity` 在 y 方向施加重力；显式负加速度可反转方向。
- `unbalance` 使用节点、质量、偏心、频率、相位和可选斜坡生成转子激励。

载荷在 `SimulationConfig` 构造时完成字段和值域校验并冻结；`run()` 不重新解释未知键。

## 历史与输出

`memory` 保存全部策略选中的提交；`ring_buffer` 只保留最近 `capacity` 个；
`disk_stream` 把每个保留步原子写入 `directory`，内存结果的对应数组为空尾维，
`SimulationResult.metadata["history_path"]` 指向历史目录。`downsample` 总是保留索引 0
和整除该值的提交，完成或失败时还会强制保留最后一个已提交状态。

`SimulationResult.time` 第一维与全部保留数组一致；转子位移/速度通常为
`(samples, rotor_dofs)`，轴承力通常为 `(samples, mount_count, 2)`，单位分别为 m、m/s
和 N。`SimulationResult.as_bundle()` 返回只读持久化快照，`write(path)` 只写入一个新的
目标目录。

## 完整 JSON5 模板

```json5
{
  schema_version: "0.4.0",
  kind: "simulation",
  includes: [],
  spec: {
    rotor: {
      model: "ross_excel",
      path: "resources/rotor.xlsx",
      frequency_hz: 50.0,
      alpha: 0.0,
      beta: 0.0,
    },
    time_grid: {time_step: 1e-4, steps: 1000},
    mounts: [
      {bearing: "bearings/left.json5", node: 0},
      {bearing: "bearings/right.json5", node: 4},
    ],
    loads: [
      {type: "gravity", acceleration: 9.80665},
      {type: "static", node: 2, force: [0.0, -100.0]},
    ],
    history: {
      mode: "memory",
      fields: ["rotor_displacement", "rotor_velocity", "bearing_force"],
      downsample: 1,
    },
  },
}
```

模板中的 Excel 和 bearing 路径是资源占位符，不是 ALB 随包数据。可解析模板位于 `docs/api/examples/templates/simulation_ross_excel.json5`。

## 源码同步字段合同

<!-- Generated by tools/docs/generate_simulation_config_reference.py. -->

- 配置字段组：`10`
- 源码合同摘要：`sha256:ed2c265087ef451f`
- 对应规则：loader 的允许键集合与本页都从 `ALB.api._config_fields` 派生；新增、删除或修改字段会使生成检查失败。
- 英文列保留源码合同，中文标题和摘要来自经过键集合校验的站点语义元数据。

<a id="config-group-document"></a>
### JSON5 文档外壳

simulation 与 simulation_profile 的版本、include 和 spec 合同。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `schema_version` | `string` | `version` | "0.4.0" | ["0.4.0"] | - | 全部 | 与公开字段同名 | Exact document schema version. |
| `kind` | `string` | `name` | 必填 | ["simulation", "simulation_profile"] | - | 全部 | 与公开字段同名 | Simulation document role. |
| `includes` | `array[string]` | `path list` | [] | - | relative, unique, acyclic, and contained below document root | 全部 | 与公开字段同名 | Ordered relative simulation profiles. |
| `spec` | `object` | `mapping` | 必填 | - | - | 全部 | 与公开字段同名 | Simulation specification overlaid after profiles. |

<a id="config-group-spec"></a>
### simulation spec 顶层

转子、时间网格、轴承挂载、载荷和历史策略。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `rotor` | `object` | `mapping` | 必填 | - | - | 全部 | 与公开字段同名 | ROSS rotor resource and operating point. |
| `time_grid` | `object` | `mapping` | 必填 | - | - | 全部 | 与公开字段同名 | Global fixed step and advance count. |
| `mounts` | `array[object]` | `list` | 必填 | - | nonempty; nodes unique after construction | 全部 | 与公开字段同名 | Bearing file paths mounted at unique rotor nodes. |
| `loads` | `array[object]` | `list` | [] | - | - | 全部 | 与公开字段同名 | Static, gravity, or unbalance rotor loads. |
| `history` | `object` | `mapping` | {} | - | - | 全部 | 与公开字段同名 | Committed-history retention policy. |

<a id="config-group-rotor"></a>
### rotor

ROSS Excel 资源、转频和比例阻尼参数。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `model` | `string` | `name` | 必填 | ["ross_excel"] | - | 全部 | 与公开字段同名 | Rotor resource loader. |
| `path` | `string` | `relative file` | 必填 | - | nonempty, relative, contained below document root | 全部 | 与公开字段同名 | ROSS Excel rotor file below the outer document. |
| `frequency_hz` | `number` | `Hz` | 必填 | - | finite | 全部 | 与公开字段同名 | Rotor rotation frequency passed to the ROSS adapter. |
| `alpha` | `number` | `1` | 0.0 | - | finite | 全部 | 与公开字段同名 | ROSS proportional mass damping coefficient. |
| `beta` | `number` | `1` | 0.0 | - | finite | 全部 | 与公开字段同名 | ROSS proportional stiffness damping coefficient. |

<a id="config-group-time_grid"></a>
### time_grid

全局量纲时间步、初始状态后的推进次数、耦合积分器选择、ROS2 Jacobian 刷新策略和预测-校正选项。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `time_step` | `number` | `s` | 必填 | - | finite and > 0 | 全部 | 与公开字段同名 | Global dimensional integration time step. |
| `steps` | `integer` | `count` | 必填 | - | >= 0 | 全部 | 与公开字段同名 | Advances after the initial committed state. |
| `integrator` | `string` | `name` | "staggered" | ["staggered", "ros2", "predictor_corrector"] | - | 全部 | 与公开字段同名 | Coupled rotor-bearing integration scheme; ros2 evaluates bearing forces synchronously and is functionally incomplete (experimental) in 0.4.6; predictor_corrector (0.4.7) removes the force lag with derivative-free trials of black-box bearings. |
| `jacobian_refresh` | `integer, 'control_period', or null` | `steps or name` | null | - | only with integrator='ros2'; integer >= 1 | 全部 | 与公开字段同名 | ROS2 Jacobian refresh: null keeps J frozen, N refreshes every N steps, control_period refreshes at each controller sample. |
| `predictor_corrector` | `object or null` | `mapping` | null | - | only with integrator='predictor_corrector' | 全部 | 与公开字段同名 | Predictor-corrector interface iteration options; omitted or null uses the defaults. |

<a id="config-group-time_grid_predictor_corrector"></a>
### time_grid.predictor_corrector

预测-校正积分器（0.4.7）的迭代模式、力预测、界面松弛、收敛容差和不收敛策略；只能与 integrator: "predictor_corrector" 同时出现，省略时使用全部默认值。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `mode` | `string` | `name` | "iterate" | ["iterate", "pece"] | - | 全部 | 与公开字段同名 | iterate converges the interface force; pece runs one trial and one commit per step. |
| `predictor` | `string` | `name` | "linear" | ["linear", "constant"] | - | 全部 | 与公开字段同名 | First interface-force guess: linear extrapolation 2 F_n - F_(n-1) or constant F_n. |
| `relaxation` | `string` | `name` | "aitken" | ["aitken", "iqn_ils", "constant", "none"] | unused when mode='pece' | 全部 | 与公开字段同名 | Interface-force update between trials. |
| `omega` | `number` | `1` | 0.5 | - | finite and > 0; unused when mode='pece' | 全部 | 与公开字段同名 | Constant relaxation factor and first Aitken/IQN-ILS factor. |
| `omega_bounds` | `array[number, 2]` | `1` | [0.01, 1.5] | - | 0 < lower <= upper; unused when mode='pece' | 全部 | 与公开字段同名 | Aitken factor clipping range [lower, upper]. |
| `iqn_reuse_steps` | `integer` | `count` | 0 | - | >= 0; unused when mode='pece' | 全部 | 与公开字段同名 | Previous steps whose IQN-ILS secant columns are reused. |
| `rtol` | `number` | `1` | 1e-06 | - | >= 0, not below the bearing solver tolerance; unused when mode='pece' | 全部 | 与公开字段同名 | Relative interface tolerance against max(\|\|F~\|\|_inf, max(\|\|F_n\|\|_inf, 1 N)). |
| `atol` | `number` | `N` | 1e-06 | - | >= 0; rtol and atol not both zero; unused when mode='pece' | 全部 | 与公开字段同名 | Absolute interface tolerance in the rotor domain. |
| `max_iterations` | `integer` | `count` | 20 | - | >= 1; unused when mode='pece' | 全部 | 与公开字段同名 | Maximum trials per step. |
| `on_nonconvergence` | `string` | `name` | "warn" | ["warn", "raise"] | unused when mode='pece' | 全部 | 与公开字段同名 | warn commits the last iterate and warns once per run; raise seals the step as a coupling failure. |

<a id="config-group-mount"></a>
### mounts[]

轴承文档与唯一转子节点之间的绑定。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `bearing` | `string` | `relative file` | 必填 | - | nonempty relative path | 全部 | 与公开字段同名 | Bearing JSON5 document resolved from the simulation directory. |
| `node` | `integer` | `index` | 必填 | - | >= 0 | 全部 | 与公开字段同名 | Rotor node receiving displacement and bearing force. |

<a id="config-group-load_static"></a>
### 静载荷

指定节点上的固定二维力。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `type` | `string` | `name` | "static" | ["static"] | - | 全部 | 与公开字段同名 | Static load discriminator. |
| `node` | `integer` | `index` | 必填 | - | >= 0 | 全部 | 与公开字段同名 | Rotor node receiving the force. |
| `force` | `array[number, 2]` | `N` | 必填 | - | finite | 全部 | 与公开字段同名 | Fixed [Fx, Fy] vector. |

<a id="config-group-load_gravity"></a>
### 重力载荷

统一 y 方向重力加速度。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `type` | `string` | `name` | "gravity" | ["gravity"] | - | 全部 | 与公开字段同名 | Gravity load discriminator. |
| `acceleration` | `number` | `m/s^2` | 9.80665 | - | finite | 全部 | 与公开字段同名 | Y-axis gravity acceleration; sign controls direction. |

<a id="config-group-load_unbalance"></a>
### 不平衡载荷

节点、相位、质量、偏心、频率与斜坡参数。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `type` | `string` | `name` | "unbalance" | ["unbalance"] | - | 全部 | 与公开字段同名 | Unbalance load discriminator. |
| `node` | `integer or array[integer]` | `index or list` | 必填 | - | all >= 0 | 全部 | 与公开字段同名 | One rotor node or a nonempty sequence of nodes. |
| `phase` | `number` | `rad` | 0.0 | - | finite | 全部 | 与公开字段同名 | Initial excitation phase. |
| `t_max` | `number` | `s` | 1.0 | - | > 0 | 全部 | 与公开字段同名 | Positive ramp or gate time scale. |
| `m` | `number` | `kg` | 0.0 | - | finite | 全部 | 与公开字段同名 | Equivalent unbalance mass. |
| `freq` | `number` | `Hz` | 0.0 | - | finite | 全部 | 与公开字段同名 | Unbalance excitation frequency. |
| `e` | `number` | `m` | 0.0 | - | finite | 全部 | 与公开字段同名 | Unbalance mass eccentricity radius. |
| `no_step` | `boolean` | `bool` | false | - | - | 全部 | 与公开字段同名 | Use a linear [0, t_max] ramp instead of a step. |

<a id="config-group-history"></a>
### history

内存、环形缓冲或磁盘流式历史的字段和保留策略。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `mode` | `string` | `name` | "memory" | ["memory", "ring_buffer", "disk_stream"] | - | 全部 | 与公开字段同名 | History storage strategy. |
| `fields` | `array[string]` | `field list` | ["rotor_displacement", "rotor_velocity", "bearing_force"] | ["rotor_displacement", "rotor_velocity", "bearing_force"] | nonempty and unique membership not required | 全部 | 与公开字段同名 | Committed arrays retained or streamed. |
| `downsample` | `integer` | `count` | 1 | - | >= 1 | 全部 | 与公开字段同名 | Retain committed indices divisible by this value plus the final state. |
| `capacity` | `integer or null` | `count` | null | - | required and >= 1 only for ring_buffer | 全部 | 与公开字段同名 | Ring-buffer sample capacity. |
| `directory` | `string or null` | `relative directory` | null | - | required only for disk_stream; contained below document root | 全部 | 与公开字段同名 | Disk-stream output directory below the outer document. |
