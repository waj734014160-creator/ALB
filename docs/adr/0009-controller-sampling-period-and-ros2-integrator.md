# ADR-0009：控制器采样周期例外与可选 ROS2 耦合积分器

- 状态：Accepted。ROS2 耦合积分器部分标记为“功能不完善”（实验性），见“功能状态”一节；
  控制器采样周期与步长调整部分不受此标记影响。
相关文件：`docs/adr/0007-preserve-validated-numerical-algorithms.md`、
  `docs/migrations/0.4.6.md`、
  `refs/coupling_default_path_0_4_6_reference_v1.json`、
  `refs/coupling_default_path_0_4_6_reference_v1.npz`、
  `tools/reference/generate_coupling_default_path_0_4_6_reference.py`。

## 背景

ADR-0007 第 8 条要求 simulation 的转子、mount、嵌套 `MultiPad` 及物化控制/阀/热
组件使用同一归一化 `time_step`。0.4.5 因此让 PID 和模糊 PID 在每个仿真步都运行
一次，离散 PID 律也按仿真步长离散。真实数字控制器以固定采样周期 `Ts` 工作，而
`Ts` 通常远大于为液膜和转子刚性选取的积分步长 `h`。把控制器绑定到 `h`，会使
控制律离散化和采样保持效应随数值步长改变，不能表达真实控制器。

默认 staggered 耦合按上一提交状态计算轴承力，再推进转子线性系统，轴承力滞后
一步，耦合误差为 `O(h)`。刚性油膜下需要很小的步长。用户需要同步计算轴承力的
二阶耦合积分器，但 ADR-0007 第 1、5、6 条不允许以接口或性能理由替换已验证的
默认算法。

## 决策

1. 控制器采样周期是 ADR-0007 第 8 条的受限例外。只有 `active_lubricated` 的
   `pid` 与 `fuzzy_pid` 接受 `spec.control.control_period`，单位为轴承局部时间
   单位（量纲轴承为 s）；其他控制模式在配置边界拒绝该字段。控制器每
   `m = Ts / h` 次求值运行一次，其余求值零阶保持上一指令；PID/模糊 PID 内部
   离散化改用 `Ts`。
2. 例外不扩展到物理组件。转子、mount、嵌套 `MultiPad`、阀和热模型继续共享同一
   步长 `h'`，ADR-0007 第 8 条对它们保持有效。staggered 路径中阀每步推进，阀
   模型在相邻求值之间对输入做一阶保持插值，新的保持指令因此在一步内线性进入；
   ROS2 把阀状态并入连续耦合状态，指令为真正的零阶保持。测量时刻也不同：
   staggered 第 `k` 步的轴承及其控制器看到第 `k-1` 步提交的状态，`t_k` 的控制
   采样使用 `x(t_k - h)`；ROS2 在 `t_k` 用该时刻提交的状态采样，指令右连续，
   作用于 `[t_k, t_k + Ts)`。因此同一 `Ts` 下两种积分器的受控响应只在 `O(h)`
   意义下一致，差异不只来自轴承力滞后。
3. 未设置 `control_period` 时 `Ts = time_step`，行为与 0.4.5 逐位一致。
4. 独立轴承（`build_bearing`）要求 `r = Ts / time_step` 为正整数，判据为
   `|r - round(r)| <= 1e-9 * r` 且 `round(r) >= 1`，否则以 `ConfigurationError`
   拒绝，不自动改写。轴承内部按求值次数计数采样，并假定每次求值相隔一个
   `time_step`。耦合仿真中第 `k` 次求值就是第 `k` 步；独立调用
   `Bearing.calculate()`、`BearingAnalysis.trace_orbit()` 或动态系数网格时，只有
   按 `time_step` 间隔求值，`Ts` 才有物理意义。静平衡和谐波分析的静态求值会重置
   控制器，并重新开始采样相位。
5. `SimulationConfig` 先按请求值检查 ADR-0007 第 8 条：`rotor.dt` 和每个
   bearing-local `time_step` 都必须等于请求步长 `h`。随后处理控制周期：若 `h`
   整除全部 `Ts`，配置不变；否则保持 `Ts`，因为它是真实控制器的属性，并调整为

   ```text
   h' = Ts / ceil(Ts / h)          （h > Ts 时 h' = Ts）
   steps' = m * ceil(T / Ts)        T = steps * h，m = Ts / h'
   ```

   取整时先从 `T / Ts` 中减去 `1e-9 * max(1, T / Ts)`，避免浮点尾差多出一个
   周期；调整后的结束时间满足 `T <= T' < T + Ts`。配置了多个不同 `Ts` 时，只接受同时
   整除全部周期的 `h`，不做自动调整。全部轴承配置按 `h'` 重建并重新校验；文件
   引用的 `MultiPad` 子瓦无法自动改写，以 `ConfigurationError` 拒绝。全部校验通过
   后先发出第 6 条的警告，再对同一个转子对象原位重新离散并重置状态；警告被提升为
   异常时配置被拒绝且转子不变，警告前的任何拒绝也不修改转子。转子缺少 owner hook
   `_retime_for_owner` 时在警告前拒绝；重新离散本身失败时，在警告之后报
   `ConfigurationError`。转子被一个配置重新离散后，仍按原步长校验的另一个配置在
   构建 `RotorBearingSimulation` 时以 `ConfigurationError` 拒绝，每个配置应使用
   独立的转子对象。
6. 步长调整必须可见。`SimulationConfig` 在重新离散转子之前发出
   `ALB.TimeStepAdjustedWarning`。它是 `UserWarning` 子类，不是 `ALBError`，其
   `adjustment` 属性记录请求值与实际值。
   `SimulationConfig.time_step_adjustment` 和 `SimulationConfig.control_periods`
   保存同样的信息，结果 metadata 也记录这些值。`HistoryPolicy` 的 `downsample`
   和 `capacity` 继续按提交索引计数，不随步长调整换算。
7. ROS2 是可选积分器，不替代默认算法。`SimulationConfig(integrator="ros2")` 或
   `spec.time_grid.integrator: "ros2"` 启用两级 Rosenbrock-W 方法（Verwer, Spee,
   Blom, Hundsdorfer 1999, SIAM J. Sci. Comput. 20(4):1456-1480）。方法取
   `gamma = 1 + 1/sqrt(2)`、`W = I - gamma*h*J`。它对任意 `J` 保持二阶精度，
   对精确 `J` 为 L-稳定。`J` 缺省冻结，`W` 只做一次 LU 分解。
   `jacobian_refresh` 可取整数 `N` 或 `"control_period"`：前者每 `N` 步刷新，后者
   在任一阀驱动主动轴承（`pid`、`fuzzy_pid` 或 `uncontrolled`）的控制采样时刻
   刷新，没有这类轴承时（`Ts` 等于步长）每步刷新。刷新只改变稳定裕度和成本，不改变
   精度阶。`Ros2Options.jacobian_state` 和 `SimulationConfig.initial_rotor_state`
   保存为浮点数元组，使冻结的选项和配置可以比较，`Ros2Options` 也可以哈希。
8. ROS2 通过无副作用的 `probe_force` 在 stage 状态同步计算轴承力。主动轴承的
   阀状态并入耦合状态，控制器在 `J` 之外每 `m` 步于已提交状态采样；主动轴承的
   probe 把限幅后的阀芯开度直接写入节流器输入，不触动阀的生命周期和状态。外部
   spool provider 是耦合状态之外的有状态黑盒，每步在已提交状态采样一次，并在该步
   内零阶保持，因此该通道一般为一阶，只有 provider 指令在步长网格上分段常数时才
   保持二阶。`J` 在 runtime 提供 `torch_force` 时使用自动微分，否则使用中心差分；
   当前随包 runtime 都不提供 `torch_force`。支持范围是无热模型的液膜、气膜、
   surrogate、子瓦只含这些无热族（surrogate 限固定阀芯）的 `MultiPad`，以及无热
   模型的主动轴承。热模型保存温度或黏度状态，不是转子状态的无副作用函数，因此以
   `ConfigurationError` 拒绝；热包装器也显式不提供 `probe_force`，不会转发内部等温
   液膜的 probe。`MultiPad` 内的主动子瓦或外部阀芯子瓦没有可积分的阀状态或 spool
   provider，同样在配置阶段拒绝。
9. 默认路径继续由 ADR-0007 第 5 条约束。修改前已在未改动的 `df7336f` 上冻结
   staggered、每步控制和单一步长的输入、完整数组和环境元数据，回归测试要求精确
   相等。新增 metadata 键只在 ROS2、配置控制周期或显式初始转子状态时出现，默认
   路径的结果元数据保持不变。控制周期和 ROS2 作为新行为单独验证，不通过重新
   生成默认路径参考来证明。

## 功能状态

0.4.6 的 ROS2 耦合积分器标记为**功能不完善**（实验性）。已知缺口：

1. 代理模型（ALBNN）族的 ROS2 路径只做了接口层验证，没有用训练好的模型做数值收敛验证；
   内置轴承族都没有 `torch_force`，雅可比全部由中心差分得到。
2. 不支持带热模型（含稳态热）的轴承，也不支持含主动或外部阀芯子瓦的 `multi_pad`；
   带内部时变状态的族如何并入耦合状态尚未设计。
3. 外部阀芯 provider 每步零阶保持，阀芯随状态连续变化时该通道只有一阶精度。
4. 冻结 `J` 没有自适应刷新，轴颈接近壁面时稳定裕度下降；主动轴承的 `J` 默认取阀芯
   状态为零。
5. ROS2 运行期间主动轴承 runtime 自身不发布 output 和 result snapshot。
6. 尚未用论文降阶模型与 RK4 交叉核对，两份 0.4.6 参考也未在 Windows 环境复核。

正式计算继续使用默认 `staggered`；ROS2 结果应先与 staggered 细步长解或独立参考交叉核对。

## 影响

- 新增根符号 `TimeStepAdjustedWarning`，根 API 由 27 个符号增至 28 个；新增高级
  导出 `ALB.dynamics.Ros2Options` 和内部契约 `ForceProbeProtocol`、
  `SampledActuatorBearingProtocol`。
- 新增可选配置字段 `control.control_period`、`time_grid.integrator` 和
  `time_grid.jacobian_refresh`。JSON5 `schema_version` 和 `ALB.SCHEMA_VERSION`
  继续为 `0.4.0`，合法的 0.4.5 配置无需迁移。
- `SimulationConfig` 构造后保存实际生效的 `time_step`、`steps`、`rotor` 和
  `mounts`。调用者应读取这些值或 `time_step_adjustment`，不应假定请求值不变。
- ROS2 运行中，主动轴承由积分器持有阀状态，并通过 probe 求值。主动轴承 runtime
  自身在 ROS2 运行期间不发布 output 或 result snapshot；纯力轴承和直接阀芯轴承
  仍在每个提交步走正常生命周期。stage 求力失败抛出
  `ALB.dynamics.ros2.Ros2StageError`，并由 `run()` 包装为 `SimulationError`。
- Python 包版本升级为 `0.4.6`。迁移和能力边界见 `docs/migrations/0.4.6.md`。

## 修订关系

本文为 ADR-0007 第 8 条增加受限例外：只放宽控制器采样，不放宽物理组件共享
步长。ADR-0007 第 1、5、6 条继续有效：默认 staggered 路径冻结并精确回归；ROS2
作为可选新算法引入，并给出数值理由，不替换已验证的耦合算法。ADR-0008 的伺服阀
配置不变。
