# ALB 包概览

## 文档角色

- 角色：稳定 package 导览。
- 目的：说明 `ALB/` 包的模块地图、主要公共接口分组和 package 边界。
- 允许更新：公共 API / 模块归属变化、package 边界说明、首次阅读导览。
- 禁止更新：实验运行状态、每日维护历史、训练进度、原始证据。
- 更新时机：公共 API、模块归属或 package 边界发生变化时。
- 事实来源 / 相关文档：
  `docs/daily_maintenance/daily_doc_update_index.md`。

本文档是 `ALB_MAIN` 中 `ALB/` Python package 的首次阅读导览。接口定义、依赖方向和迁移规则详见 `docs/interface_architecture.md`。

## 中英文术语对照

| English | 中文含义 |
| --- | --- |
| Package Boundary | package 边界 |
| Public Interface Groups | 公共接口分组 |
| Module Map | 模块地图 |
| Interface Notes | 接口注意事项 |
| Remote helpers | 远程操作 helper |
| Surrogate models | 代理模型 / 神经网络 surrogate |
| Config contracts | 配置契约 |
| Packaged inference | 打包模型推理 |

## Package 边界

`ALB/` 是稳定的数值计算和系统仿真 package。`SURROGATE_TRAIN` 等 sibling 项目应从 `../ALB_MAIN` 导入该 package，并把采样、训练和实验记录保留在 package 之外。

顶层 import 通过 `ALB/__init__.py` 做 lazy export。下面列出的一些接口属于模块级 API，应从其所属模块导入。如果某个公共 API 需要成为广泛使用的顶层接口，应同时更新 export map 和本文档。如果某个 API 仍是实验性或 workflow-specific，优先从模块路径直接导入。

## 公共接口分组

| 接口分组 | 主要入口 | 用途 |
| --- | --- | --- |
| 通用模板与领域协议 | `ComponentBase`, `BearingComponentBase`, `BearingProtocol`, `BearingCoefficientProtocol`, `ControllerProtocol`, `ServoValveProtocol`, `RotorProtocol`, `TimeGridProtocol`, `NotifierProtocol`, `ConvergenceStatus`, `BearingDecoratorBase`, `LegacyBearingAdapter` | 用小型模板复用生命周期/事件/结果，用窄 Protocol 定义各领域语义，并通过 adapter 兼容旧轴承。 |
| ALB 系统 | `ALB`, `NodimALB`, `alb2`, `alb2_static`, `alb2_fuzzy`, `nodim_alb`, `ALBHarmonicCoefficients`, `ALBHarmonicLinear`, `alb_harmonic_linear` | 从配置对象构建有量纲或无量纲 active lubricated bearing 系统；也可加载方程推导的单频 `K/C/G_xv`，构建具有标准轴承接口的窄带线性 ALB。 |
| 配置契约 | `ALBConfig`, `NodimALBConfig`, `ServoConfig`, `Moog2ndServoConfig`, `FPBConfig`, `NodimPadConfig`, `OrificeConfig`, `NodimOrificeConfig`, `PIDConfig`, `FuzzyPIDConfig`, `LQGConfig`, `ThermalConfig`, `TimeGridConfig`, `ResolvedTimeGrid`, `GasConfig`, `ALBNetConfig` | builder、task 和 surrogate wrapper 使用的 dataclass-style 配置对象；时间网格由独立配置解析为唯一的 `dt/steps`。 |
| 轴承与油膜模型 | `HydrostaticBearing`, `NodimHydrostaticBearing`, `MultiPad`, `four_pads_bearing`, `four_pads_bearings`, `NodimNewtonFilm`, `GasBearing` | 油膜、气膜、静压瓦块和多瓦块轴承模型。 |
| 热模型与无量纲 helper | `ThermalHydroBearing`, `NodimThermalHydroBearing`, `SkfemThermalModel`, `SkfemThermalModelNondim`, `ThermalNondimScales`, `FilmNondimScales` | 热-流体耦合，以及有量纲 / 无量纲尺度转换。 |
| 控制器与阀 | `PID`, `FuzzyPID`, `ALB.controller.ALBLQGController`, `ALB.orifice.CSOrifice`, `NodimCSOrifice`, `ALB.servovalve.moog_2nd_servovalve`, `ALB.servovalve.moog_servovalve`, `ALB.servovalve.static_sv` | ALB 装配中使用的控制器、伺服阀和节流孔组件；LQG 输出默认限制在 `[-1, 1]`，也可通过 `LQGConfig` 设置标量或逐通道上下限。 |
| 转子耦合 | `ALB.rotor.RossRotor`, `ALB.couple.RotorBearingCouple`, `ALB.couple.RsRotorBearingCouple`, `ALB.orbit.EllipseTrack`, `ALB.orbit.BearingForceTrack`, `ALB.orbit.test_bearing_orbit_parallel` | 转子-轴承耦合、轨道生成和时域响应 workflow；并行轨道识别函数用于正反涡动力轨迹同步计算。 |
| ALBNN surrogate 支持 | `ALBNN`, `ALBNNC4Canonical`, `ALB.nn.ALBNNForceExpert`, `ALB.nn.ALBNet`, `albnn`, `ALB.nn.thermal_albnet`, `ALB.alb.ALBNNAgent`, `ALB.alb.FakeOf` | 打包神经网络力模型，以及用于本地验证和下游仿真的 ALB shell 替换组件。 |
| 训练核心 | `ALB.train.TrainingConfig`, `ALB.train.ColumnTransformPipeline`, `ALB.train.AlbnnMlpTrainer` | 配置驱动的 surrogate 训练核心。项目 CLI 保留在 `SURROGATE_TRAIN/run/train`，稳定数据变换、scaler、loss、report 和 trainer 生命周期放在 package 中复用。 |
| 远程操作 helper | `ALB.remote.job`, `ALB.remote.albnn_start`, `ALB.remote.albnn_status`, `ALB.remote.albnn_queue`, `ALB.remote.monitor`, `ALB.remote.transport` | 稳定的 SSH、PowerShell 7、Task Scheduler、launch、queue 和 monitor helper，供 `SURROGATE_TRAIN/run/remote` wrapper 使用；`ALB.remote.transport` 集中提供 encoded command 和 runner-file 命令构造。 |
| 任务与结果 | `ALB.task.TaskConfigFactory`, `ALB.task.*`, `DataFrameResult`, `SaveTreeNode`, `read_json5`, `recognize_kc` | 统一时间配置工厂、可复用批处理入口、结果存储 helper、配置读取和信号分析工具。 |

## 模块地图

| 区域 | 文件 | 说明 |
| --- | --- | --- |
| Package export | `__init__.py` | lazy 顶层 export。把模块 API 提升为 package 公共 API 时需要同步更新。 |
| 接口与核心模板 | `contracts/`, `core/`, `adapters/` | 轴承/转子/控制器/伺服阀/时间/通知协议，生命周期与事件模板，单位制/输出验证，以及旧轴承 adapter。 |
| 分类 namespace | `physics/`, `control/`, `dynamics/`, `systems/`, `surrogate/` | 面向新代码的职责入口；当前通过 lazy export 指向旧实现文件，使实现可渐进迁移。 |
| 系统装配 | `alb.py` | ALB / NodimALB 类、builder、线性和神经网络核心替换 agent。 |
| 谐波线性轴承 | `harmonic_linear.py`, `data/alb_harmonic_linear_gamma1_50hz.json` | 方程推导系数的数据契约、PD/二阶 Moog 状态、复阀芯力时域重建和 `RsRotorBearingCouple` 标准轴承接口；内置 JSON 是 `γ=1`、50 Hz、热惯性严格基态结果。 |
| 配置 | `config.py` | film、gas、thermal、时间网格、ALB、servovalve、PID 和 ALBNN workflow 的 dataclass 配置契约。 |
| 数值基础 | `base.py`, `mesh.py`, `boundary.py`, `gauss.py`, `matrix/` | `base.py` 保留有限元基础类型和旧核心 import facade；其余模块负责节点 / 单元抽象、网格生成、边界装配和底层矩阵 / 迭代工具。 |
| 油膜与轴承求解 | `film.py`, `bearing.py`, `orifice.py`, `gas.py`, `damping.py` | Reynolds 油膜求解、静压 / 气体轴承、节流孔流量、多瓦块装配和自适应 damping。 |
| 热模型与无量纲代码 | `thermal.py`, `nondim.py` | 热网格、粘温耦合油膜、热求解器和尺度对象。 |
| 控制与动力学 | `controller.py`, `servovalve.py`, `lti.py`, `rotor.py`, `orbit.py`, `couple.py` | 控制器、伺服阀、状态空间工具、转子模型、轨道定义和耦合系统。 |
| Surrogate 模型 | `nn.py` | ALBNN 架构、特征增强、目标变换、训练 helper 和打包推理 loader。 |
| 训练核心 | `train/` | JSON 配置、声明式列变换/scaler、loss、报告和 trainer 类。它不拥有实验路径、远程 queue config 或具体 run 历史。 |
| 远程 helper | `remote/` | 共享远程操作实现。wrapper 兼容脚本保留在 `SURROGATE_TRAIN/run/remote`。 |
| 输出与工具 | `results.py`, `postprocess.py`, `plot.py`, `logger.py`, `tool.py`, `task.py` | 结果、绘图、日志、通用工具和历史可复用 task 入口。 |

## 接口注意事项

- 新代码优先从 `ALB.contracts` 获取结构协议，从 `ALB.core` 获取通用模板；不要新增具有统一 `input/output/solve` 含义的万能基类。
- 标准轴承必须声明 `unit_system`，实现 `node_link`、`signal`、`init()`、`input(uxy, uxyt, t)`、`output()["force"]`、`calc_is_finished()`、`results` 和 `save()`。`RsRotorBearingCouple` 是有量纲边界，会拒绝显式无量纲轴承；旧对象可用 `LegacyBearingAdapter` 补齐元数据。
- `ALB.physics`、`ALB.control`、`ALB.dynamics`、`ALB.systems` 和 `ALB.surrogate` 是推荐分类入口；旧模块路径继续用于兼容外部脚本和 pickle。
- 构建 ALB 系统时，优先使用配置对象，不要使用随意拼接的字典。
- `alb_harmonic_linear(node_link, dt=...)` 返回可直接传给 `RsRotorBearingCouple` 的 `ALBHarmonicLinear`。它提供 `node_link`、`signal`、`init()`、`input(uxy, uxyt, t)`、`output()["force"]` 和 `save()`；公开方程推导的 `K`、`C`、复 `G_xv`，并用 `fdxv` 兼容旧 `ALBLinearAgent` 命名。内部使用 `kp=0.3, kd=0.5` 的 PD 与默认 166 Hz、`zeta=0.7` 二阶 Moog 伺服阀，不直接输入阀芯谐波。复 `G_xv` 的虚部通过指定涡动频率下的精确采样相位恒等式重建，不通过轨迹差分生成系数。该对象是 50 Hz 附近的窄带局部模型，不应当作全频流体状态模型。
- 新代码和文档中，粘度使用 `miu`，无量纲轴承参数使用 `lambda_value`。
- `ALBConfig.servo` 和 `NodimALBConfig.servo` 默认使用 `moog_2nd`，对应 `ALB.servovalve.moog_2nd_servovalve` 的单二阶伺服阀；当前默认参数为 `tw=9.587647174210562e-4`、`zeta=0.7`，即固有频率约 `166 Hz`。`ServoConfig` 类本身保留 legacy `moog` 默认参数，`ALBConfig` / `NodimALBConfig` 通过继承自 `ServoConfig` 的 `Moog2ndServoConfig` 作为默认 `servo_config`；flat config 工厂不根据 `servo` 字符串路由切换嵌套配置，因此使用旧 `moog` 时应显式提供对应 `tw`、`zeta` 和 `tp3`，或直接传入 `ServoConfig`。旧 `moog` 仍保留为二阶 Moog 环节串联 `tp3` 一阶环节的 legacy 三阶模型，`static` 仍为静态阀。
- `ThermalConfig.iter_method` 控制热非线性迭代方式：默认 `direct` 保持旧直接迭代行为；`newton` 在每个压力步固定压力场后对 `miu(T)` 代入的热方程做分离式 Newton 子迭代；`direct_then_newton` 仅在旧直接迭代未收敛时用末态触发 Newton fallback。瞬态热模型当前只允许 `direct`，其他组合在配置阶段报错。`coupling` 自动转为小写且只接受 `full|half`；deprecated 的 `flow_rate_factor` 仅允许无作用值 `1.0`。`k_lub` 是 W/(m·K) 的三维导热率，装配时使用局部 `k_lub*h`；默认 `k_lub=0.0`，空间对流稳定由 SUPG 独立提供。`miu_update="log"` 与 `heat_partition_steps` 可显式启用粘度对数松弛和热分配 continuation。未收敛的稳态初场或瞬态步不会写入历史温度。热 wrapper 输出求解器诊断，以及 `q_orifice_total_nondim`、`q_orifice_total_vol`；兼容字段 `q_orifice_total` 固定为 m³/s。
- 热包装的数值核心以无量纲实现为准：`NodimThermalHydroBearing` 直接接受无量纲 pad/config；`ThermalHydroBearing` 只保留有量纲 public API 和默认有量纲输出，内部把有量纲 film 参数转换为 `NodimViscositySkfemNewtonFilm` 并使用 `SkfemThermalModelNondim`。`wrap_pad_collection_with_thermal` 会按 pad 的 `args_nodim` 单位制选择对应 wrapper，且要求 `ThermalConfig.args_nodim` 与 pad 单位制一致。
- `ThermalNondimScales.qf` 是面内通量尺度 $Q_f=p_sc^3/(12\mu_0l_r^2R)$，单位 m²/s；只读 `flow_scale` 保留为兼容别名。供油孔体积流量尺度为 $Q_w=Q_fl_rR$，单位 m³/s，且 `q_vol=q_nondim*Qw`。`flow_info()` 明确同时返回有量纲与无量纲位置/流量，热核只消费 `position_nondim` 和 `q_nondim`。
- `TimeGridConfig.resolve()` 支持两种互斥模式：`cycle_points` 由 `freq+cycles+points_per_cycle` 推导 `dt/steps`；`fixed_dt` 保留 `freq+dt+steps`，并严格要求每转采样数 $1/(freq\,dt)$ 为正整数。缺少 `mode` 且存在旧 `n/pt` 时按 `cycle_points` 兼容解析。`TaskConfigFactory` 从 `share.json5` 读取唯一共享转速 `freq`，从 `time_iter.json5` 解析时间网格，并只在内存中把 `dt/freq` 注入 task、GUI、ALB、控制器、热模型和转子配置；不会回写 `share.json5`。旧 `read_share(recover=True)` 仅返回内存结果并发出弃用警告。
- 当前 thermal surrogate workflow 中，`ALB.nn` 期望 12 个基础 ALBNN 输入：
  `ex, ey, vx, vy, sx, sy, lambda_value, beta_nondim, lr, cq0, cq1, cq2`，
  输出为 `fx, fy`。
- 第一象限 canonical ALBNN 模型应通过 `ALBNNC4Canonical` 或 `metadata.json` 中的 `inference_symmetry.name="c4_canonical_quadrant"` 进行全域推理。该兼容层把 `ex/ey`、`vx/vy` 和 `sx/sy` 同步旋转到 `ex>=0, ey>=0`，调用原模型后再把 `fx/fy` 反向旋转回调用方坐标；未显式启用该 metadata/config 标记的旧模型保持原推理行为。
- Polar ALBNN 实验可以使用派生输入列 `sin_theta, cos_theta, r` 替代 `ex, ey`，并训练目标契约 `sin_f_theta, cos_f_theta, force_norm`；打包推理会把该目标契约解码回 `fx, fy`。在这个 polar 契约中，角度 sine / cosine 列可以不经变换地通过 minmax scaler，半径、力范数和物理参数继续缩放。
- Full-polar ALBNN 实验还可以把速度向量和伺服阀向量表示为 `sin_v_theta, cos_v_theta, v_norm` 与 `sin_s_theta, cos_s_theta, s_norm`。对于不使用额外特征增强的 15 输入实验，这些角度列可以不经变换地通过 minmax。
- Force-polar ALBNN 目标可以只对 `force_norm` 使用可逆 signed `log1p` 变换后再 minmax 缩放，同时保持 `sin_f_theta, cos_f_theta` 作为角度直通目标列。
- Cartesian ALBNN force 目标在使用 `asinh` target transform 时，可以使用 `IdentityTargetScaler`，前提是变换后的力已经处于合适数值范围，不应再做 minmax 或 standard scaling。
- Force-expert ALBNN package 通过 `ALB.nn.albnn` metadata dispatch 使用 `ALB.nn.ALBNNForceExpert`。每个 expert 输出两个 force-code channel 和一个 raw router logit；部署推理使用 hard 或 confidence-gated adjacent expert blending，并返回普通 `fx, fy`。
- Hybrid ALBNN scaler 实验可以 standardize `ex, ey, vx, vy, sx, sy`，同时对其余输入列先 standardize 再 minmax；匹配的 force-target 实验可以对 `fx, fy` 先 standardize 再 minmax，同时保持 expert router logits 不缩放。
- Direct-parameter hybrid scaler 实验可以 standardize `ex, ey, vx, vy, sx, sy`，直接 minmax 标量参数和 ratio 列，例如 `lambda_over_lr`，并 standardize cartesian `fx, fy` target。
- Scaled-EVS MLP 实验可以先把 12 个基础输入 minmax 到 `[0, 1]`，再从该 scaled input space 计算并追加 `evs_geom`, `edotv`, `edots`, `sdotv`。这些追加 interaction features 不再进行第二次缩放。
- 新训练入口应优先使用 `ALB.train` 的 JSON 配置契约：CLI 负责读取配置和运行层 override，`ColumnTransformPipeline` 负责按列名或列序号执行 scaler/派生特征步骤，并把原始配置与 resolved 配置写入模型输出目录。新增输入/输出 scaler 组合时，优先扩展 transform registry，而不是继续新增命名策略函数。
- ALBNN MLP checkpoint 可以启用 hidden-layer LayerNorm。checkpoint 字段 `use_layer_norm` 控制 packaged inference 时 `ALB.nn.Net` 是否在每个 hidden `Linear` 层和 activation 之间插入 `LayerNorm`。
- Polar force-expert 实验可以把 `ex/ey`, `vx/vy`, `sx/sy` 替换为各向量的 sine、cosine 和 norm，再追加 `e_dot_v`, `e_dot_s`, `s_dot_v` interaction features。在这个契约中，角度列直通 scaling，norm 和 dot product 做 standardization，标量参数先 standardize 再 minmax，每个 expert 可在 packaged inference 解码最终 blended output 为 `fx, fy` 之前输出 `sin_f_theta, cos_f_theta, force_norm, router_logit`。
- `ALB.nn.albnn_augment_frame(..., feature_set="sqrt_abs")` 保持选定基础输入契约，只追加 `sqrt_abs_<column>` 特征，不追加 norm、ratio、dot、cross 或 log-combination 特征。
- `ALB.nn.albnn_augment_frame(..., feature_set="polar37")` 用于 full-polar 15 输入契约。它会为每个基础输入追加 `sqrt_abs_*`，并追加 7 个目标 interaction features：
  `lambda_over_lr`, `sqrt_lambda_over_lr`, `log_lr`, `v_radial`,
  `v_tangential`, `s_radial`, `s_tangential`。
- `ALB.nn.albnn_augment_frame(..., feature_set="sqrt28")` 保持 12 个基础输入，并为当前 28 输入 thermal ALBNN 实验追加 12 个 `sqrt_abs_*` 特征和 4 个 norm / ratio 特征。
- `ALB.nn.albnn_augment_frame(..., feature_set="sqrt34")` 保持 12 个基础输入，并追加 12 个 `sqrt_abs_*` 特征、`e_norm`, `v_norm`, `s_norm`、它们的 square-root companion，以及 4 个 `lambda_value / lr` 或 `lr` ratio / log companion。
- `ALBNNAgent` 和 `FakeOf` 位于 `ALB.alb`，因为它们只替换 ALB shell 内的 pad force core；加载打包模型时使用 `ALB.nn.albnn`。
- `ALB/remote` 是 library code。新的通用远程 launch、monitor 和 conditional queue workflow 使用 `ALB.remote.job`；PowerShell 调用默认使用 PowerShell 7，SSH encoded command 使用 `pwsh`，Task Scheduler runner 默认优先使用 `C:/Program Files/PowerShell/7/pwsh.exe` 绝对路径，并通过 `ALB_POWERSHELL_EXE`、`ALB_POWERSHELL_TASK_EXE` 保留覆盖入口。面向用户的 queue config 和兼容 wrapper 保留在 `../SURROGATE_TRAIN/run/remote`。
- 运行编号和路径放置规则属于 repository workflow 文档，不是 ALB 数值 package 代码。人类可读规则保留在 `docs/run_index.md`，活跃运行 locator state 保留在所属项目的 current-status 文档。
- 不要在没有兼容计划的情况下重命名 `ALB/matrix/dynmaic.py`；这个拼写错误已经是现有 import 的一部分。
