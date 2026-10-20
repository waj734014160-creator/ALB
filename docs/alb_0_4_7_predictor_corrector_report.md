# ALB 0.4.7 预测-校正分区耦合交付报告

- 分支：`claude/alb-0.4.7`，自 `origin/claude/alb-0.4.6` 末端 `51cce0b` 分出（见第 3 节第 1 条）。
- 第一个提交 `ad212c8 test: freeze pre-0.4.7 staggered paths of stateful bearings` 只做修改前参考冻结（参考在未修改的 `9432c06` 上生成），之后才开始功能修改。
- 本报告由云端会话生成；数值环境、命令和结果均为实际执行记录，未执行项单独说明。
- **结论概要：** 新增可选积分器 `integrator="predictor_corrector"`，保持轴承黑箱（不求导、不拆模型），支持热模型和主动轴承；在线性、硬化、记忆解析算例及 `m = 1` 的采样主动解析算例上为二阶（staggered 一阶），`m > 1` 时受阀的一阶保持插值限制降为一阶（第 2.2 节）；刚性算例中 Aitken 与 IQN-ILS 在 4 次试算内收敛。staggered、ROS2 和全部既有参考逐位不变。真实模型（M42 代理、hb34 FEM 液膜、热模型、本地热记忆与 LSTM 代理）的核对待用户本地完成。

## 1. 改动清单

### 1.1 代码

| 文件 | 改动 |
| --- | --- |
| `ALB/dynamics/predictor_corrector.py`（新） | `PredictorCorrectorOptions`（第 2.5 节默认值，冻结 dataclass，`to_dict()` 含 `unused_in_pece`）；迭代更新 `FixedPointUpdate`（`none`/`constant`）、`AitkenRelaxation`、`IQNILSAccelerator`（QR 最小二乘，`|R_ii| < 1e-10 ‖r‖` 列丢弃，可选跨步复用）；试算适配器 `_BearingTrial`（`probe` 或 `checkpoint`，外部阀芯 `provider_checkpoint` 或 `held_per_step`）；耦合积分器 `PredictorCorrectorCouplingIntegrator`（第 2.2 节流程、Jacobi 更新、诊断计数）；`CouplingIterationWarning`、`CouplingIterationError`、`CouplingTrialError`。 |
| `ALB/dynamics/coupling.py` | `_RotorBearingStepRuntime` 接受 `integrator="predictor_corrector"` 与 `predictor_corrector_options`；新增 `_reset_predictor_corrector()`、`_advance_predictor_corrector()`，以及 `diagnostic_snapshot()` 中的 `predictor_corrector` 诊断。`_advance_staggered()` 与 ROS2 路径语句不变。 |
| `ALB/dynamics/rotor.py` | `RossRotor._propagate_trial(x0, force0, force1)`：与 `_propagate` 同一套公式（连续模型一阶保持精确离散，离散模型照搬 `_run_discrete`），不改动对象状态；`_propagate` 语句不变。 |
| `ALB/dynamics/ros2.py` | `INTEGRATORS` 增加 `"predictor_corrector"`，ROS2 代码不变。 |
| `ALB/core/checkpoint.py`（新） | 组件快照工具：`ComponentSnapshot`、`capture_components()`、`RuntimeCheckpoint(owner, components, children)`、`require_checkpoint_token()`。快照保存时变对象的属性字典，字典（递归到字典值）、列表、集合、数组原地恢复以保持共享引用一致；网格、FEM 组装对象、torch 模型只保留引用。 |
| `ALB/contracts/bearing.py`、`ALB/contracts/__init__.py` | 新契约 `CheckpointableRuntimeProtocol`（`checkpoint() -> object`、`restore(token) -> None`）。 |
| `ALB/physics/film/solver.py` | `FilmSystem._checkpoint_components()`：模型参数、压力迭代、节点场、膜厚模型、后处理、节流器缓冲与可选保存历史。 |
| `ALB/physics/bearing/solver.py` | 液膜混合 runtime 的 `checkpoint()`/`restore()`；`MultiPad.probe_force_supported`、`checkpoint()`/`restore()`（委托子瓦）。 |
| `ALB/physics/thermal/solver.py` | 热包装（量纲/无量纲、稳态/瞬态）的 `checkpoint()`/`restore()`：`_temperature_prev`、`_last_thermal`、热网格与后处理记录，以及内部液膜令牌。 |
| `ALB/physics/gas/runtime.py`、`ALB/surrogate/runtime.py` | 气膜与代理 runtime 的 `checkpoint()`/`restore()`（供多瓦委托）。 |
| `ALB/systems/alb/runtime.py` | 主动轴承 `ALB`/`NodimALB`/`ALBSV`/`NodimALBSV`：`probe_force_supported`、`checkpoint()`/`restore()`（控制器记忆、`_control_counter`、`_held_command`、阀状态与一阶保持输入记忆、节流器、各瓦令牌、生命周期；控制器自身实现协议时委托给控制器）。 |
| `ALB/api/simulation.py` | `SimulationConfig.integrator` 增加 `"predictor_corrector"`、新字段 `predictor_corrector`；转子 owner hook 与拓扑校验；文件配置 `time_grid.predictor_corrector`；只在新格式下向结果元数据和失败快照元数据（`build_failure_snapshot`）写入 `predictor_corrector_options`、`predictor_corrector_diagnostics`。 |
| `ALB/api/building.py` | `_predictor_corrector_support_issue()`：唯一拒绝 `multi_pad` 内的外部阀芯子瓦，写明配置路径。 |
| `ALB/api/_config_fields.py` | `SIMULATION_PREDICTOR_CORRECTOR_FIELDS`（10 个字段，配置参考分组 `time_grid_predictor_corrector`）。 |
| `ALB/api/errors.py`、`ALB/api/__init__.py`、`ALB/__init__.py`、`ALB/dynamics/__init__.py` | 根符号 `CouplingIterationWarning`（共 29 个），高级导出 `ALB.dynamics.PredictorCorrectorOptions`；`__version__ = "0.4.7"`。 |
| `pyproject.toml` | `version = "0.4.7"`。 |

### 1.2 测试与参考

| 文件 | 内容 |
| --- | --- |
| `tools/reference/generate_coupling_staggered_pre_0_4_7_reference.py`、`refs/coupling_staggered_pre_0_4_7_reference_v1.json/.npz` | 第一个提交在未修改的 `9432c06` 上冻结的 staggered 参考：小网格液膜 + 瞬态热、液膜 + 稳态热、带瞬态热瓦的主动 PID、含液膜/主动 PID/瞬态热子瓦的多瓦、确定性 provider 驱动的外部阀芯主动轴承；完整数组、最终结果快照数值字段和环境元数据。 |
| `tests/regression/api/test_coupling_staggered_pre_0_4_7_reference.py` | 上述 5 例精确相等。 |
| `tools/reference/generate_predictor_corrector_0_4_7_reference.py`、`refs/predictor_corrector_0_4_7_reference_v1.json/.npz` | 由完成后的实现（`a1eb59b`）生成的新行为参考：液膜 iterate、液膜 PECE、瞬态热液膜、采样主动 PID（`Ts = 3.5h`，IQN-ILS）、外部阀芯（held）、记忆解析轴承、硬化解析轴承（IQN-ILS）。 |
| `tests/regression/dynamics/test_predictor_corrector_0_4_7_reference.py` | 新行为参考 7 例精确相等（数组与诊断元数据）。 |
| `tests/unit/physics/test_bearing_checkpoint_0_4_7.py` | 存档/回退契约（80 项）：18 个族/替身（含开启压力/膜厚保存历史的液膜、`control_period` 为 3 步的主动 PID）× {协议实现、3 次试算后回退与孪生对象逐位相同、A4 式 20 步序列每步插 2 次试算（输入幅值见第 3 节第 14 条）、失败试算后回退的生命周期}，以及令牌绑定、热包装不转发、`LinearSpoolProvider` 回退与 20 步孪生比较、多瓦子瓦缺协议拒绝、液膜失败试算回退、嵌套字典（历史列表字典、`defaultdict`、自引用字典）原地恢复、控制器自带协议时的委托。 |
| `tests/unit/dynamics/test_predictor_corrector_0_4_7.py` | 积分器核心（48 项）：选项校验、Aitken 两步得不动点、IQN-ILS 迭代次数 ≤ 维数 + 2、线性轴承对矩阵指数精确解（误差比约 4，staggered 约 2）、硬化轴承自收敛并与 ROS2/staggered 收敛到同一解、记忆轴承（ROS2 拒绝）、采样主动轴承控制器计数、刚性算例、求值计数、两个轴承的 Jacobi 试算与计数、不收敛 warn（与 PECE 逐位相同，即提交最后一次迭代）/raise（封存、运行时失效、诊断计入失败步）、试算失败回退与计数、非有限值、多瓦子瓦缺协议在 reset 时拒绝、离散转子、`_propagate_trial` 与 `_propagate` 逐位一致。 |
| `tests/unit/api/test_predictor_corrector_simulation_0_4_7.py` | 公开 API 层（30 项）：真实小网格瞬态热液膜运行与诊断字段、选项与拓扑校验（含路径）、文件配置解析、控制周期组合、默认/ROS2 元数据键集合不变、`write()`、失败封存与 `partial_result`、主动/外部阀芯/多瓦、带热主动 PID 与带热外部阀芯（可存档 provider）。 |
| `tests/_support/dynamics/memory_bearings.py`（新） | `MemoryAnalyticBearing`（刚度向偏心相关平衡值一阶松弛，指数衰减 + 输入梯形二阶推进，只在提交时更新，`probe_force=None`）和 `SampledActiveAnalyticBearing`（采样控制器 + 一阶阀，阀输入可选一阶保持或零阶保持）。 |
| `tests/_support/dynamics/analytic_bearings.py` | `LinearSpoolProvider` 实现存档协议并计数；新增 `OpaqueLinearSpoolProvider`（无协议，覆盖 held 情形）。 |
| `tests/_support/state_fingerprint.py`（新） | 递归状态指纹，用于核对存档覆盖是否完整。 |
| 版本相关测试 | `tests/unit/api/test_public_api_0_4.py`、`tests/unit/test_public_api.py`（另加 `CouplingIterationWarning`）、`tests/unit/api/test_simulation_time_step_0_4_1.py`、`tests/validation/test_optional_dependency_errors.py`、`tests/validation/test_release_0_4_1_gates.py`、`tests/validation/test_release_0_4_2_gates.py` 改为 0.4.7。 |
| 文档生成器计数 | `test_simulation_config_reference.py` 38 → 49 行（10 组），`test_namespace_reference.py` 11 → 12 导出。 |
| `tools/analysis/run_predictor_corrector_0_4_7_study.py`（新） | 复现第 2 节全部调查数字（`--sections linear hardening memory active stiff film thermal`）。 |

### 1.3 ADR、迁移说明与文档

- 新增 `docs/adr/0010-predictor-corrector-coupling-and-bearing-checkpoints.md`（算法、存档契约、与 ADR-0007 第 1/5/6 条和 ADR-0009 的关系、显式状态模型接入方式），同步 `docs/adr/README.md`。
- 新增 `docs/migrations/0.4.7.md`（版本边界、预测-校正格式、存档/回退协议、控制周期、结果元数据、数值参考、能力边界），`mkdocs.yml` 导航与 `README.md` 迁移列表加入 0.4.7。
- 当前版本标识：`docs/index.md`、`docs/site/concepts/public-api-policy.md`（29 个根符号）、`docs/current_state.md`、`docs/alb_package_overview.md`、`docs/interface_architecture.md`、`docs/project_overview.md`。
- 指南：`docs/site/guides/simulation.md`（“预测-校正积分器（0.4.7）”）、`docs/site/guides/configuration.md`（JSON5 示例）；索引：`docs/daily_maintenance/daily_doc_update_index.md`；`tools/README.md` 登记分析脚本。
- `docs/api/`：更新人工维护输入 `public_api_docs.json`（新示例 `simulation_predictor_corrector`）、`namespace_reference_docs.json`、`config_reference_docs.json`、`simulation_config_reference_source.md`，用 `tools/docs/` 四个生成器重新生成。
- 本报告加入 `mkdocs.yml` 的 `exclude_docs`。历史版本号（`docs/migrations/0.4.6.md`、ADR-0009、发布记录）与 `.github/workflows/` 未改动。

## 2. 调查结论（任务第五节）

全部数字由 `python tools/analysis/run_predictor_corrector_0_4_7_study.py` 在第 5.1 节环境中得到（总耗时约 2.6 分钟）。解析算例使用 `tests/_support` 的单节点解析转子（质量 2 kg）和解析轴承；误差为终态相对误差。

### 2.1 各轴承族（第 1 条）

“逐位契约”指“存档 → 任意次试算 → 回退 → 正常求值”与“直接正常求值”逐位相同；验证方式见第 5.3 节。

| 轴承族 / runtime | 试算方式 | 存档覆盖的状态 | 逐位契约 |
| --- | --- | --- | --- |
| `liquid_film` 无热（量纲/无量纲） | `probe_force` | 也实现协议（供多瓦委托）：模型参数、压力迭代、节点压力/膜厚/粘度比、膜厚模型、后处理、节流器缓冲、可选保存历史、生命周期与最新输出/结果/收敛状态 | 协议逐位满足。**探测路径**下，带液膜节流器时探测会覆盖节流器 30 行滚动缓冲，只影响下一次提交求解的停止迭代次数，差异在求解容差内（与 0.4.6 ROS2 相同，见第 3 节第 6 条） |
| `liquid_film` + 热（稳态、瞬态，量纲/无量纲） | 存档/回退 | `_temperature_prev`、`_last_thermal`、热网格与后处理记录、热配置；内部液膜令牌；生命周期 | 满足 |
| `gas_film` | `probe_force` | 也实现协议：膜模型、节点场、膜厚、箔片耦合、后处理缓存、可选保存历史、生命周期与最新输出/结果/收敛状态 | 满足 |
| `surrogate` 固定阀芯 | `probe_force` | 也实现协议：生命周期、最新输出/结果/收敛状态与待处理输入（模型本身无状态，torch 模型只保留引用） | 满足 |
| `surrogate` 外部阀芯、`ALBSV`/`NodimALBSV`（无热） | `probe_force`（带阀芯），阀芯见下 | — | — |
| `active_lubricated` `pid`/`fuzzy_pid`/`uncontrolled`（`ALB`/`NodimALB`，含带热瓦） | 存档/回退 | 控制器积分/差分记忆与结果记录、`_control_counter`、`_held_command`、控制开关、动态与静态伺服阀状态及一阶保持输入记忆与历史、阀连接的节流器、各瓦令牌、生命周期 | 满足 |
| `ALBSV`/`NodimALBSV` 带热瓦 | 存档/回退 | 同上，另含直接阀芯 | 满足 |
| `multi_pad` | 子瓦全部可探测时 `probe_force`，否则存档/回退 | 复合体生命周期与各子瓦令牌 | 满足；子瓦缺协议时以 `TypeError` 拒绝存档 |
| `multi_pad` 内外部阀芯子瓦 | — | — | **拒绝**（`ConfigurationError`，写明 `mounts[i].config.pads[j]` 路径）：复合体没有 spool provider |
| 外部阀芯 provider | 实现协议：每次试算用试算输入调用，与轴承一起回退（`provider_checkpoint`）；未实现：提交时采样一次，下一步试算保持（`held_per_step`，一阶） | `LinearSpoolProvider`：内部状态与计数 | 满足（测试替身） |

带热模型的主动轴承由“主动轴承存档 + 热子瓦存档”组合直接支持，已测试：`active_pid_thermal`、`external_spool_thermal`、`nondimensional_external_spool_thermal` 三族的契约测试，以及 API 层 `test_active_bearings_with_thermal_pads_run_through_checkpoints`（带热主动 PID 与带热外部阀芯 + 可存档 provider 经预测-校正运行，`trial_modes == ("checkpoint",)`）。元素矩阵和全局装配矩阵每次求解都从当前膜厚重建，属于求解器临时量，不存档；状态指纹核对显示除这类临时量外没有残余差异。

### 2.2 主动轴承黑箱内的阀（第 2 条）

采样主动解析轴承（刚度 3e4 N/m、阻尼 40 N·s/m、阀芯增益 200、控制增益 500、阀时间常数 5 ms），`Ts = 1 ms`，步长 2.5e-4 / 1.25e-4 / 6.25e-5 / 3.125e-5 s（`m > 1` 时 `m` = 4/8/16/32），`T = 0.1 s`，表中为相邻步长解之差的比值（≈4 为二阶，≈2 为一阶）：

| 阀输入保持方式 | `m` | 预测-校正（iterate） | staggered |
| --- | --- | --- | --- |
| 一阶保持插值（ALB 现有阀的做法） | 1 | 3.96、3.89 | 3.45、3.30 |
| 一阶保持插值 | > 1 | **1.81、1.94** | 2.27、2.30 |
| 零阶保持（指令在采样时刻跳变，步内保持） | 1 | 2.49、2.32 | 3.43、3.04 |
| 零阶保持 | > 1 | **4.00、4.00** | 2.25、2.23 |

- 不论迭代多少次，控制器都恰好每 `m` 次提交执行一次（单元测试按提交与试算分别计数验证）。
- `m = 1` 时控制器每步运行，相当于连续控制器的近似，一阶保持插值正确，预测-校正为二阶。
- `m > 1` 时，指令在采样时刻 `t_k` 跳变；一阶保持插值把跳变摊到 `[t_{k-1}, t_k]` 内（约提前半步），每个控制周期引入 `O(h)` 误差，阀芯通道降为一阶（比值约 1.8～1.9）。同一解析轴承改为零阶保持后恢复二阶（比值 4.00）；反过来，`m = 1` 时零阶保持本身是一阶近似，比值降为 2.3～2.5。staggered 在 `m = 1` 一阶保持时比值 3.3～3.5 偏离 2，属前渐近区（相邻差本身是预测-校正的 60～80 倍）。
- **建议（未实施）：** 对声明了 `control_period` 且 `m > 1` 的主动轴承，阀输入改为“采样时刻跳变、步内零阶保持”的离散方式（与真实 DAC 一致），`m = 1` 保持一阶保持插值。这会改变 0.4.6 staggered 与 ROS2 的控制周期数值，需要按 ADR-0007 第 6 条单独立项并冻结修改前参考。本次未修改阀离散方式。

### 2.3 热模型（第 3 条）

小网格瞬态热液膜（与 `tests/_support` 中的热液膜规格相同），`h = 2e-5 s`、10 步，单节点物理转子：

| 方案 | 每步试算次数（均值） | 最大迭代 | 相邻残差比（均值） | 每步耗时 | 相对 staggered |
| --- | --- | --- | --- | --- | --- |
| staggered | — | — | — | 0.178 s | 1.00 |
| iterate + Aitken（默认） | 3.1 | 4 | 0.024 | 0.692 s | 3.89 |
| iterate + `none` | 5.6 | 7 | 0.079 | 1.072 s | 6.03 |
| PECE | 1 | 1 | — | 0.341 s | 1.92 |

- 每次试算都从已提交状态把热场推进一次（后向欧拉，模型自身的时间离散），然后回退；提交时再推进一次。这是热模型自身的时间离散，与耦合精度无关；收敛后，提交时的轴颈输入与最后一次试算的输入只差界面容差量级。
- 全部步收敛，无不收敛步；iterate 的事后一致性残差最大 5.6e-7 N，PECE 为 1.26 N（合力约 79 N）。
- 10 步后轴承力：staggered `[0.300, 81.70]` N，iterate `[0.249, 79.31]` N，PECE `[0.249, 79.33]` N；起始瞬态中 staggered 的一步滞后误差约 3%。
- 存档与回退的代价：小网格主动 PID 在第 0 步存档约 3.4 ms、每次回退约 1.4 ms，第 3000 步约 6.2 ms 与 2.2 ms；瞬态热液膜约 0.9 ms 与 0.3 ms（并行负载下测得，单步求值约 80～230 ms）。令牌复制控制器、阀、液膜结果等追加式历史，因此代价随已提交步数线性增长，整次运行的累计代价随步数二次增长；按上述斜率外推到 2.4 万步，每步约增加 50 ms，在 FEM 求解为主的算例中仍是次要项，代价主要来自试算次数（见第 3 节第 17 条）。

无热小网格液膜（`h = 2e-5 s`、40 步，探测试算）：Aitken 每步 2.3 次试算、最大 4 次，耗时为 staggered 的 1.84 倍；`none` 4.8 次、最大 8 次，3.35 倍；PECE 1.67 倍。

### 2.4 收敛因子与稳定性（第 4 条）

收敛因子用 `relaxation="none"` 的相邻残差之比估计（`predictor_corrector_diagnostics["residual_ratio"]`）：

| 算例 | 估计的 ρ | 说明 |
| --- | --- | --- |
| 线性解析轴承（3e4 N/m，40 N·s/m，`h = 1.25e-4` s） | 理论 1.3e-3 | 多数步 1～2 次试算即收敛（均值 1.95 次） |
| 小网格液膜（无热） | 0.091（最大 0.102） | |
| 小网格瞬态热液膜 | 0.079 | |
| 刚性阻尼算例 `c = 2000` N·s/m | 0.500（理论 `c h/(2m) + k h²/(6m)` = 0.5025） | |
| `c = 8000` | 理论 2.0025 | `none` 发散 |
| `c = 20000` | 理论 5.0025 | `none` 发散 |

刚性阻尼算例（`k = 3e4` N/m，`m = 2` kg，`h = 1e-3` s，`T = 0.05 s`，误差相对 `h = 1e-5` s 的 staggered 细步长解）：

| 方案 | `c = 2000`（ρ≈0.5） | `c = 8000`（ρ≈2） | `c = 20000`（ρ≈5） |
| --- | --- | --- | --- |
| `none` | 均值 10.8、最大 20 次（2 步达到上限，`warn` 提交） | 发散（`FloatingPointError`） | 发散（`FloatingPointError`） |
| `constant`（ω = 0.5） | 均值 6.3、最大 12 次 | 均值 10.1、最大 20 次（3 步不收敛） | 发散：前 40 步均不收敛并按 `warn` 提交（只警告一次），力逐步增大，第 41 步提交时力非有限（输出 DTO 校验 `ValueError`） |
| `aitken` | 均值 2.1、最大 4 次，ω ∈ [0.50, 0.67] | 均值 2.1、最大 4 次，ω ∈ [0.33, 0.50] | 均值 2.4、最大 4 次，ω ∈ [0.17, 0.50] |
| `iqn_ils` | 均值 3.1、最大 4 次 | 均值 3.1、最大 4 次 | 均值 3.4、最大 4 次 |
| PECE | 稳定，误差 2.6e-3（iterate 2.2e-3） | **失稳**（误差 2e46） | **失稳**（误差 3e90） |

Aitken 收敛到的 ω 与最优值 `1/(1+ρ)`（0.67、0.33、0.17）一致；收敛的方案误差相同（2.2e-3～2.4e-3，为 `h = 1e-3` 自身的时间离散误差）。结论：ρ < 1 时 PECE 稳定、`none` 可用但慢；ρ > 1 时 `none` 与 PECE 不可用，Aitken（默认）与 IQN-ILS 在 4 次试算内收敛。

### 2.5 与 ROS2、staggered 对比（第 5 条）

线性解析轴承（常刚度、常阻尼）+ 静载 + 不平衡，对比增广矩阵指数精确解，`T = 0.1 s`：

| 方案 | 1.25e-4 s | 6.25e-5 s | 3.125e-5 s | 误差比 | 每步求值次数 |
| --- | --- | --- | --- | --- | --- |
| staggered | 1.16e-1 | 5.67e-2 | 2.80e-2 | 2.05、2.02 | 1 |
| ROS2 | 3.61e-3 | 1.00e-3 | 2.63e-4 | 3.60、3.82 | 2 |
| 预测-校正 PECE | 5.89e-5 | 1.47e-5 | 3.66e-6 | 4.02、4.01 | 2 |
| 预测-校正 iterate（Aitken） | 5.84e-5 | 1.46e-5 | 3.65e-6 | 4.00、4.00 | 2.95（均值 1.95 次试算 + 1 次提交） |

硬化轴承（刚度随偏心增大），对 ROS2 细步长解（1.5625e-5 s）：

| 方案 | 2.5e-4 s | 1.25e-4 s | 6.25e-5 s | 自收敛比 |
| --- | --- | --- | --- | --- |
| staggered | 1.70 | 6.34e-1 | 2.72e-1 | 2.94（对参考的误差比 2.68、2.33，趋向一阶） |
| ROS2 | 2.31e-2 | 5.27e-3 | 1.20e-3 | 4.38 |
| 预测-校正 PECE | 4.81e-3 | 1.25e-3 | 3.68e-4 | 4.04 |
| 预测-校正 iterate | 4.72e-3 | 1.24e-3 | 3.67e-4 | 3.99 |

（最细一档的误差比低于 4，是因为 ROS2 参考自身的误差已不可忽略。）

带记忆的解析轴承（`tau = 5 ms`，ROS2 以 `ConfigurationError` 拒绝），对预测-校正细步长解（7.8125e-6 s）：iterate 5.34e-5 / 1.32e-5 / 3.14e-6（比 4.05、4.20），PECE 5.37e-5 / 1.32e-5 / 3.14e-6（比 4.07、4.21），staggered 1.58e-1 / 7.58e-2 / 3.72e-2（比 2.08、2.04），收敛到同一解。

同一步长下，预测-校正的误差比 staggered 小 2.5～4 个数量级；比 ROS2 在线性算例中小约 60～70 倍，在硬化算例中小 3～5 倍（受 ROS2 参考自身误差限制）。原因是转子线性部分为精确离散，误差只来自界面耦合。PECE 与 ROS2 每步求值次数相同且不需要 `J`；迭代版在这些算例中每步约 1 次额外求值，换来界面残差到容差内。

## 3. 需要用户确认的事项（均已按默认方案实施）

1. **起点提交。** 任务指定起点 `9432c06`，但 `origin/claude/alb-0.4.6` 末端是 `51cce0b`（在 `9432c06` 之后只改 docstring 和文档，把 ROS2 标为功能不完善）。分支从 `51cce0b` 分出以保留该标记；修改前参考在未改动的 `9432c06` 上生成（两者 Python 运行代码相同）。
2. **格式名和选项。** 格式名 `"predictor_corrector"`；选项默认值与任务第 2.5 节完全相同；文件配置位置为 `spec.time_grid.predictor_corrector`，只能与该积分器同时出现，省略或 `null` 用全部默认值。
3. **PECE 下的迭代选项。** 选择“校验但忽略”：`mode="pece"` 时 `relaxation`、`omega`、`omega_bounds`、`iqn_reuse_steps`、`rtol`、`atol`、`max_iterations`、`on_nonconvergence` 仍校验，不起作用，`to_dict()["unused_in_pece"]` 列出这些字段，docstring 和迁移说明写明。另一方案是对非默认值报错。
4. **存档协议命名。** `ALB.contracts.CheckpointableRuntimeProtocol`（`checkpoint()`/`restore(token)`），令牌为不透明对象，只能回退到创建它的 runtime，可重复回退。另新增只读属性 `probe_force_supported`（`MultiPad` 与主动轴承），用于报告子瓦是否都可探测。主动轴承的控制器若自身实现 `checkpoint()`/`restore()`，存档委托给控制器，否则按组件快照保存控制器属性（含历史列表字典）。
5. **既不能探测也不能存档的 runtime。** 自定义 runtime 若既无可用 `probe_force` 也无协议，在 reset 时以 `TypeError` 拒绝（不是 `ConfigurationError`，因为在配置阶段无法看到自定义 runtime 的能力）；子瓦不支持存档的程序化复合体（多瓦、主动轴承）同样在 reset 时拒绝，而不是拖到第一步；随包族在配置阶段全部通过。ROS2 对此类 runtime 的行为不变。
6. **做不到逐位契约的情形。** 协议本身对全部随包族逐位满足。唯一例外在探测路径：带液膜节流器的无热液膜按任务要求用 `probe_force` 试算，探测会覆盖节流器滚动缓冲，只影响下一次提交求解的停止迭代次数，差异在求解容差内（与 0.4.6 ROS2 相同）。若需要逐位，可把这类液膜改走存档路径（代价约为一次令牌复制），请确认。
7. **未实现存档的 provider。** 与 ROS2 相同，提交时采样一次，下一步试算保持，阀芯通道一阶；诊断中记为 `spool_trials: "held_per_step"`，docstring 与迁移说明已写明。
8. **阀指令插值。** 见第 2.2 节建议：`m > 1` 时改为采样时刻跳变的零阶保持可恢复二阶，但会改变既有控制周期数值，需单独立项。本次未改。
9. **离散转子输出。** 预测-校正支持离散 `RossRotor`；其 `results()`/`result_uxy()` 输出与提交状态对齐，而 staggered 离散路径输出上一步状态。已写入迁移说明。
10. **外部载荷日志。** 与 ROS2 相同，步进中的外部载荷用不写日志的 `force_at`，`UnbalancedExcitation.results` 只记录 reset 时 `t0` 的初始载荷（staggered 每步记录）。
11. **IQN-ILS 细节。** `iqn_reuse_steps > 0` 时，前几步的列只在本步 `k >= 1` 时并入最小二乘（`k = 0` 仍用 `omega` 松弛），与任务公式的 `k = 0` 行一致；最小二乘最多保留界面维数个最新列；所有列都被丢弃时退回 `omega` 松弛。列丢弃阈值按任务公式取 `1e-10 ‖r^k‖`；代码评审指出该阈值随残差趋零，收敛末段可能保留近似相关的列，可改为相对 `max|R_ii|` 的阈值。本次按任务公式实现，未改。
12. **警告与异常的位置。** `CouplingIterationWarning` 定义在 `ALB/dynamics/predictor_corrector.py`，由 `ALB.api.errors` 再导出为根符号（与 `TimeStepAdjustedWarning` 不同，后者定义在 `ALB.api.errors`），以免 `ALB.dynamics` 依赖 `ALB.api`。`CouplingIterationError`、`CouplingTrialError` 不进入公开 API，`run()` 把它们包装为 `SimulationError`。
13. **参考生成脚本依赖测试替身。** `tools/reference/generate_predictor_corrector_0_4_7_reference.py` 从 `tests/_support` 导入解析转子与记忆轴承，并复用 0.4.6 ROS2 生成脚本中的解析对象，以保证参考与单元测试使用同一模型。
14. **A4 测试输入幅值。** 契约测试中 A4 式序列对全部 18 个族/替身均为 20 步；`nondimensional_external_spool_thermal` 使用 0.4 倍输入幅值，因为原幅值下该小网格无量纲瞬态热模型在不插入任何试算时也在第 6 个输入（步序号 5）热迭代不收敛，属模型自身问题，与存档无关。
15. **分层 mypy。** 未改动发布门禁基线 `tools/validation/mypy_layer_baseline_0_4.json`（在 0.4.6 起点已过期）；本次的精确增量见第 5.4 节。
16. **发布动作。** 未打 tag，未写发布验收记录，未修改 `.github/workflows/`。是否把 0.4.7 分支纳入文档自动发布、是否做正式发布验收，由用户决定。
17. **存档代价随运行长度增长。** 通用组件快照复制追加式历史（阀的 `ts`/`u`/`yout`/`xout`、控制器结果表、液膜结果表、节流器记录、可选保存历史），单次存档/回退为 O(已提交步数)。本次保持“完整复制”以确保逐位契约，未做按长度截断的优化（需要逐类确认哪些历史只追加）。若长时程运行中成为瓶颈，可作为后续优化立项。

## 4. 本地核对建议

- M42 准稳态代理：`SimulationConfig(integrator="predictor_corrector", initial_rotor_state=x_eq, ...)`，先用默认 Aitken；每转 400 步与 staggered 细步长解或 ROS2（每 20 步重算 `J`）比较幅值误差，同时查看 `predictor_corrector_diagnostics` 的 `iterations_per_step` 与 `nonconverged_steps`。
- hb34 FEM 液膜：关注 `nonconverged_steps`、`max_final_residual` 与 `residual_ratio.max`。若力在网格尺度上的跳变导致迭代来回振荡，可先确认 `rtol` 不小于求解器容差，再比较 `"iqn_ils"`；不收敛步在 `warn` 下提交最后一次迭代并只警告一次。
- 热模型与本地热记忆/LSTM 代理：按 ADR-0010“显式状态模型的接入方式”实现 `checkpoint()`/`restore()` 后可直接使用；建议先用 `tests/unit/physics/test_bearing_checkpoint_0_4_7.py` 的三类契约测试（3 次试算后回退与孪生对象逐位相同、A4 式序列、失败试算后回退）核对实现。
- 跨平台复核参考：把本分支的 `tools/reference/generate_coupling_staggered_pre_0_4_7_reference.py` 复制到 `9432c06` 的检出中，用 `--json <file> --npz <file>` 生成本地修改前参考，在本分支用 `generate_predictor_corrector_0_4_7_reference.py` 生成新行为参考，分别设置 `ALB_COUPLING_STAGGERED_PRE_0_4_7_NPZ`/`_JSON` 与 `ALB_PREDICTOR_CORRECTOR_0_4_7_NPZ`/`_JSON` 运行回归测试；仓库中提交的参考不重新生成。

## 5. 测试实际执行结果

（全量测试进行中，结果在后续提交中补充。）
