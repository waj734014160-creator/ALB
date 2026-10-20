# ALB 0.4.6 ROS2 积分与控制周期交付报告

- 分支：`claude/alb-0.4.6`，起点 `df7336f`（与 `codex/alb-0.4.5` 末端相同）。
- 第一个提交 `60e2642 test: freeze pre-0.4.6 default coupling path` 只做默认路径参考冻结，之后才开始功能修改。
- 本报告由云端会话生成；数值环境、命令和结果均为实际执行记录，未执行项单独说明。

## 1. 改动清单

### 1.1 代码

| 文件 | 改动 |
| --- | --- |
| `ALB/core/time.py` | 新增 `control_steps_per_period()`（`|r - round(r)| <= 1e-9 r` 判定整数倍）和 `fit_time_step_to_control_period()`（`h' = Ts/ceil(Ts/h)`，`h > Ts` 时 `h' = Ts`）。 |
| `ALB/config/control_models.py` | `PIDConfig`、`FuzzyPIDConfig` 新增可选 `control_period` 与只读 `sample_period`；未设置时 `Ts = dt`。 |
| `ALB/control/pid.py`、`ALB/control/fuzzy.py` | PID 离散公式与模糊 PID 误差变化率归一化使用 `Ts`；新增 `PID.sample_period`。 |
| `ALB/api/_config_fields.py`、`ALB/api/config.py` | 公开字段 `spec.control.control_period`（仅 `pid`/`fuzzy_pid`）；`spec.time_grid.integrator`、`spec.time_grid.jacobian_refresh`。 |
| `ALB/api/building.py` | 物化控制周期；独立轴承要求严格整数倍；多瓦树遍历、重定步长、ROS2 轴承族检查；`check_control_period` 用于先校验原始步长一致性。 |
| `ALB/systems/alb/runtime.py` | 主动轴承按 `m` 次求值执行一次控制器并零阶保持指令（`m = 1` 时代码路径与 0.4.5 相同）；静态求值后重置采样相位；ROS2 钩子 `actuator_state_space()`、`sample_actuator_command()`、`probe_force_with_spool()`；`ALBSV`/`NodimALBSV.probe_force()`。 |
| `ALB/api/simulation.py` | `SimulationConfig` 新增 `integrator`、`ros2`、`initial_rotor_state`，派生字段 `control_periods`、`time_step_adjustment`；整数倍强制与自动调整、`TimeStepAdjustedWarning`、结果/失败元数据；`load_simulation_config` 解析新字段。 |
| `ALB/api/errors.py`、`ALB/api/__init__.py`、`ALB/__init__.py` | 新增并导出 `TimeStepAdjustedWarning(UserWarning)`（根命名空间 28 个符号）。 |
| `ALB/dynamics/ros2.py`（新） | ROS2 积分核心 `Ros2Stepper`、`Ros2Options`、耦合积分器 `Ros2CouplingIntegrator`、`Ros2StageError`。 |
| `ALB/dynamics/coupling.py` | `_RotorBearingStepRuntime` 支持 `integrator="ros2"`、`ros2_options`、`initial_rotor_state`；交错格式代码仅提取为 `_advance_staggered()`，语句不变。 |
| `ALB/dynamics/rotor.py` | `RossRotor._retime_for_owner()`（原对象就地重离散）、`_continuous_system()`、`_node_state_indices()`、`_node_force_vector()`、`_commit_integrated_state()`；`UnbalancedExcitation.force_at()`（不写日志的力计算）。 |
| `ALB/contracts/bearing.py` | 新契约 `ForceProbeProtocol`、`SampledActuatorBearingProtocol`。 |
| `ALB/physics/bearing/solver.py`、`ALB/physics/gas/runtime.py`、`ALB/surrogate/runtime.py` | 液膜、多瓦、气膜、代理模型的无副作用 `probe_force()`。 |
| `pyproject.toml`、`ALB/__init__.py` | 版本 0.4.6。 |

### 1.2 测试与参考

（见第 5 节）

### 1.3 ADR、迁移说明与文档

（见第 5 节）

## 2. 轴承族调查结论（第五节第 3 条）

“无副作用”指：给定轴颈位移、速度、阀芯开度（和时间），返回力，不发布 lifecycle 输出、不改变已提交结果、不推进任何时间积分状态；求解器内部临时缓冲允许被覆盖。

| 轴承族 / 运行时 | 力是否为输入的纯函数 | 内部时变状态 | ROS2 首版 |
| --- | --- | --- | --- |
| `liquid_film`（量纲/无量纲，无热） | 是。`FilmSystem.output()` 每次求解前重置主模型，以当前膜厚的线性 Reynolds 解作初值，不复用上一时刻压力；挤压项来自速度输入，时间参数被忽略。带节流器时，节流器 30 行滚动缓冲把上一次求解的节点压力带入下一次求解首轮收敛判据，只影响停止迭代次数（差异在求解容差内）。 | 无 | 支持（`probe_force`） |
| `liquid_film` + 热（`ThermalHydroBearing`） | `transient_enabled=False` 时稳态求解是输入的纯函数，但求值会更新后处理、粘度网格等缓存；`transient_enabled=True` 时每次求值以固定 `dt` 做一步后向欧拉并覆盖 `_temperature_prev`，重复求值（如 Runge-Kutta 级）会再推进热状态。 | 有（热惯性、瞬态能量方程） | 不支持，配置阶段 `ConfigurationError` |
| `gas_film` | 是。求解前重置为均匀压力并清除箔片变形；挤压项来自速度输入。 | 无 | 支持 |
| `multi_pad` | 子瓦力之和；子瓦都是纯函数时成立。 | 取决于子瓦 | 子瓦全部受支持时支持；含热或主动子瓦时拒绝 |
| `surrogate`（固定阀芯） | 是。输入 `ex, ey, vx, vy, sx, sy` 与静态参数，时间不是特征；只保存最后一行输入。推理经 pandas/numpy/sklearn 预处理且在 `torch.no_grad()` 下执行，**现有路径不能做自动微分**。 | 无 | 支持（中心差分） |
| `surrogate`（外部阀芯 `DirectSpoolBearingInput`） | 给定阀芯时是纯函数；阀芯来自外部 provider（黑盒，可能有内部状态）。 | provider 自身 | 支持：provider 每步在提交状态采样一次并零阶保持 |
| `active_lubricated` `pid`/`fuzzy_pid`/`uncontrolled`（`ALB`/`NodimALB`） | 求值内部串联控制器（积分、差分记忆）、阀 LTI（严格时间步检查，按一阶保持推进）和节流器，**整体不是纯函数**；但给定阀芯开度时，瓦块力是纯函数。 | 控制器、阀 | 支持：拆分为“采样控制器（不进 J）+ 阀芯连续状态并入 z + 瓦块无副作用求力” |
| `active_lubricated` `external_spool`（`ALBSV`/`NodimALBSV`） | 给定阀芯时是纯函数（`set_spool` 不推进阀动态）。 | 无（阀芯来自 provider） | 支持（同外部阀芯代理） |
| 任一族带热模型 | 见上 | 有 | 不支持 |

带内部状态的族（热惯性、瞬态热模型）如何并入整体状态 `z`，列为后续议题，本次未实现。

## 3. 需要用户确认的事项（均已按默认方案实施）

1. **控制周期字段的命名和位置。** 采用任务默认方案：公开字段 `spec.control.control_period`（仅 `pid`/`fuzzy_pid`，单位与该轴承 `time_step` 相同，量纲制为 s），原生配置为 `PIDConfig.control_period`、`FuzzyPIDConfig.control_period`（`None` 表示 `Ts = dt`）。`PIDConfig.dt` 仍表示仿真步长，因此 ADR-0007 第 8 条“物化控制器 dt 等于 time_step”的检查保持不变。
2. **步长调整的结束时间。** 调整后步数取 `m * ceil(T/Ts)`（带 `1e-9` 相对容差），结束时间 `T' >= T` 且 `T' < T + Ts`；`T` 为 `Ts` 整数倍时总时长不变。若希望改为四舍五入或截断，请确认。
3. **转子对象就地重离散。** 调整步长时保持用户转子对象不变（`config.rotor is rotor`），原位重建离散矩阵并重置状态；警告在重离散之前发出。副作用是同一个转子对象不能被另一个仍按原步长校验的 `SimulationConfig` 继续使用，构建时以 `ConfigurationError` 明确拒绝。另一种方案是为调整后的配置创建新转子对象。
4. **多个控制周期。** 允许多个不同 `Ts`，但只有当 `h` 同时整除全部 `Ts` 时才通过；需要调整时只支持单一 `Ts`，否则 `ConfigurationError`。
5. **文件引用的 `multi_pad` 子瓦。** 需要调整步长时无法改写外部文件中的 `time_step`，以 `ConfigurationError` 拒绝（提示改用 `time_step = Ts/m`）；内联子瓦会被重建。
6. **ROS2 首版覆盖的轴承族。** 见第 2 节：无热液膜、气膜、代理模型（固定/外部阀芯）、由它们组成的多瓦、无热主动轴承（`pid`/`fuzzy_pid`/`uncontrolled` 拆分阀芯状态；`external_spool` 走 provider）。热模型、多瓦内的主动或外部阀芯子瓦拒绝。外部阀芯 provider 每步在提交状态采样一次并在步内保持，因此当 provider 指令随状态连续变化时阀芯通道为一阶（已用测试固定为约 2 的误差比）。
7. **J 的默认求取位置。** 默认在仿真初始状态（缺省为零状态、指令为初始采样值、阀芯状态为零）。`Ros2Options.jacobian_state` 可给转子状态或完整耦合状态（含阀芯状态）。代理模型在轴颈居中处有平方根型刚度奇异点，建议给出偏心（如静平衡）状态。所有内置族目前都用中心差分；自动微分仅在 runtime 提供 `torch_force` 时启用（现有 ALBNN 推理路径经 pandas/sklearn 预处理且在 `no_grad` 下，无法直接求导）。
8. **默认积分格式。** 保持 `"staggered"`，ROS2 需显式选择（`SimulationConfig(integrator="ros2")` 或 `spec.time_grid.integrator`）。是否把默认切换为 ROS2 由用户决定；切换会改变默认路径数值，需要按 ADR-0007 第 6 条单独立项。
9. **“一拍计算延迟”等控制器实现选项。** 本次未实现。当前语义：ROS2 在 `t_k` 用该时刻提交状态采样，指令右连续；staggered 在第 `k` 步使用第 `k-1` 步状态（与轴承力滞后一致），阀模型对输入做一阶保持插值。
10. **新增可选初始状态。** 为便于第 4 节的交叉核对，新增了任务未要求的 `SimulationConfig.initial_rotor_state`（默认 `None`，默认路径不变）。如不需要可移除。
11. **新增元数据的出现条件。** 为保持默认路径结果契约（含 `result.write()` 的文件集合）不变，`integrator`、`control_periods`、`time_step_adjustment`、`ros2_options`、`initial_rotor_state` 只在 ROS2、配置控制周期或显式初始状态时写入结果元数据。
12. **分层 mypy 基线。** `tools/validation/mypy_layer_baseline_0_4.json` 在 `df7336f` 已经过期（缺 3 个已存在文件），本次未改动该发布门禁文件。本次改动的精确增量：新增 `ALB/dynamics/ros2.py`（0 条诊断），`ALB/dynamics/rotor.py|assignment` 8 → 9；strict 层没有新增诊断。
13. **发布动作。** 未打 tag，未写发布验收记录，未修改 `.github/workflows/`。`docs-pages.yml` 只在推送 `main` 和 `codex/alb-0.4.5` 时触发，是否把 0.4.6 分支纳入自动发布由用户决定。0.4.6 的正式发布验收是否进行，也请用户确认。

## 4. 本地交叉核对建议

用户计划在本地用论文第 4 章降阶模型核对（3000 r/min、kp = kd = 0.3、计入不平衡、从静平衡积分 3 转、每转 400 步，与 2 μs RK4 比较）。对应的 ALB 配置要点：

- `SimulationConfig(integrator="ros2", ros2=ALB.dynamics.Ros2Options(jacobian_state=x_eq), initial_rotor_state=x_eq, time_step=(60/3000)/400, steps=1200, ...)`，其中 `x_eq` 为完整 ROSS 状态向量 `[q, dq/dt]` 形式的静平衡状态（用仓库现有静平衡算法求得，速度分量为零）。
- 若控制器通过主动轴承配置实现，`control.control_period` 设为实际采样周期；若 PD 控制写在外部 spool provider 中，注意 provider 在每步提交状态采样、步内保持。
- 跨平台比对 0.4.6 默认路径参考时，可在 `df7336f` 上用 `tools/reference/generate_coupling_default_path_0_4_6_reference.py --json <file> --npz <file>` 生成本地参考，并设置 `ALB_COUPLING_DEFAULT_PATH_0_4_6_NPZ`/`_JSON` 运行回归测试；仓库中提交的参考不重新生成。

## 5. 测试实际执行结果

（待补充）
