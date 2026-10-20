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

只有 `integrator="ros2"`、声明了控制周期或给出 `initial_rotor_state` 时，
`SimulationResult.metadata` 才额外包含 `integrator`、`time_step`、`control_periods`、
`time_step_adjustment`、`ros2_options` 和 `initial_rotor_state`；用户状态向量只记录为
`"user-supplied"`，默认路径的元数据保持不变。`SimulationResult.write()` 可写出这些
嵌套只读映射。完整适用边界见 [0.4.6 迁移说明](../migrations/0.4.6.md)。

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
