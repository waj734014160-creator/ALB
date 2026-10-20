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

（待补充）

## 4. 本地交叉核对建议

（待补充）

## 5. 测试实际执行结果

（待补充）
