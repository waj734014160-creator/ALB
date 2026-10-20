# ALB_MAIN 当前状态

参考来源：当前 Git 工作树、`pyproject.toml`、源码、版本验收报告和本次文档检查。

## 当前快照

最近本地核对: 2026-10-20，本轮范围为 0.4.7 可选预测-校正耦合积分器、轴承存档/回退协议及其文档（云端会话）。本文区分当前工作树、历史发布和局部验证。

| 项目 | 当前事实 |
| --- | --- |
| 开发分支 | `claude/alb-0.4.7`（自 `claude/alb-0.4.6` 末端 `51cce0b` 分出） |
| 当前 HEAD | 以 `git rev-parse HEAD` 为准；0.4.7 修改前参考在 `9432c06` 生成（与 `51cce0b` 的 Python 运行代码相同，后者只改 docstring 和文档） |
| 包版本 | `re-alb 0.4.7`，导入名 `ALB`，最低 Python 3.10 |
| 配置与模型包格式 | JSON5 schema 和 surrogate package 仍为 `0.4.0` |
| 发布边界 | 最新已有固定候选正式验收的版本为 `v0.4.2`；0.4.3 至 0.4.7 仍属开发边界 |
| 工作树 | 0.4.7 实现、文档和测试在 `claude/alb-0.4.7` 上提交；未提交内容不计入固定发布候选 |

当前工作重点包含 0.4.7 预测-校正耦合积分器的真实模型本地核对、0.4.6 控制周期与 ROS2 耦合积分器、压力-热耦合契约维护，以及独立热记忆代理接口。
2026-09-06 完成文档与代理规则维护；该次文档检查不代表当前未提交数值实现已完成验收。

2026-09-23 新增冻结 M35 基线的热记忆 MLP、显式状态预测、安全模型包及
采样/训练/衔接组件，尚未接入完整转子 runtime。已核对原 11303 点预测保持
最大差约 `3.286e-6` 无量纲；局部物理连续步探针和 GPU 训练短跑只能验证
流程，不能替代独立瞬态验收。原 M35 在坐标轴/原点的 C4 边界误差保持原样，
该次严格总力验收没有豁免。接口契约见[热记忆说明](thermal_memory_surrogate.md)，
实验配置、数据与实时状态见 `../SURROGATE_TRAIN/docs/current_runtime_status.md`。

2026-09-27 为轨迹力拟合新增可选当前工况修正分支；默认关闭，原平衡零修正
行为保持，开启后可修正冻结基线的稳态拟合偏差。模型包保存该开关，初始化、
重置和逐步状态接口保持显式。相关模型与训练单元测试35项通过；已训练包的
CPU逐步/整段/分块、重置、恒定输入回归和基线权重保持检查通过，证据位于
`../SURROGATE_TRAIN/outputs/thermal_memory/S0017_trajectory_memory_training_20260927/verification/delivery_api.json`。
这是代理模型功能及拟合交付验证，不代表完整物理求解器、C4总力或转子运行时验收。

2026-09-28 新增独立 `thermal_residual_lstm` 模块：冻结 M35，由单层 LSTM 与当前
工况共同驱动一个总残差读出层，支持时间间隔输入和 Time-aware cell 折扣。
独立安全包类型与显式 h/c 状态接口已核验；共享训练器增加可选模型身份契约，
旧模型恢复身份保留原结构。本轮相关模型/训练测试 55 项通过，真实轨迹的逐步/
整段/分块和冻结权重检查通过。此模块保持实验接口，未接入 Bearing/runtime；
时间细分一致性和稳定记忆泛化仍不足，详见
`../SURROGATE_TRAIN/outputs/thermal_memory/S0020_m35_unified_lstm_time_20260928/verification.json`。

2026-09-26 完成已授权的本地缓存清理、五子棋删除、手动脚本分类与历史资产归档。
ALB 数值源码和冻结参考保持清理前字节；处置清单、恢复入口与保留项见
[清理记录](daily_maintenance/project_cleanup_20260926.md)。

2026-10-06 按用户授权删除 15 份旧文档和 14 个维护日志、结果、状态及空日志文件，
修正文档引用，并将两份旧审计脚本的 Markdown 导出改为显式指定。
工作树原文恢复副本与逐项清单保存于
`outputs/maintenance/document_cleanup_20261006_8f066d8f/`。

2026-10-09 将压力-温度-节流器解析谐波线性化接入
`bearing.analysis.harmonic_linearize()`，新增配置驱动的命令行工具和可运行算例。
工具独立求严格互补基态，再按频率计算 K、C 和复数阀芯传递 G；支持传统张量
网格上的完整黏温四瓦主动轴承及两种供油投影。原临时脚本的热源孔位坐标已修正，
修正前后参考分别冻结保存。用法和边界见[分析工作流](site/guides/analysis.md)，
本轮机器证据位于 `outputs/thermal_harmonic_integration_20261008/verification.json`。

2026-10-09 修复 surrogate 构建器漏用 C4 映射的问题。论文 T03 诊断
(`F:/BaiduSyncdisk/博士论文/NEW_SMALL_PAPER/task/day2_linearization/out/t03_report.md`)
显示：M35/M42 只在 `ex, ey >= 0` 训练，构建器却直接加载原网络；3000 rpm 下
8 个 `ey < 0` 静态点相对物理热轴承的矢量 RMS 误差为 27.75%，套用
`ALBNNC4Canonical` 后为 1.90%。0.2 加载器原本读取 metadata
`inference_symmetry`，0.4 迁移时丢失了这一处理。现在的规则：
`model_package.symmetry` 可取 `"c4"`、`"none"` 或 `null`；`null` 按 package 声明解析，
未声明且输入 scaler 记录的 `ex`、`ey` 最小值都不小于 0 时以 `BuildError` 拒绝构建。
`"none"` 以及全平面 package 与原构建器逐位一致。这里不猜测对称性，不改 package
摘要，也不改物理求解器。
现有 M35/M42 配置需补写 `symmetry: "c4"`。修改前冻结的参考见
`refs/surrogate_c4_builder_reference_v1.json`/`.npz`。

2026-10-20 形成 0.4.6 开发版本，依据见
[ADR-0009](adr/0009-controller-sampling-period-and-ros2-integrator.md) 和
[0.4.6 迁移说明](migrations/0.4.6.md)。主动轴承 `pid`/`fuzzy_pid` 可用
`control.control_period` 声明控制器采样周期 `Ts`：控制器每 `m = Ts/h` 步采样并
保持指令，物理组件仍共享同一步长。仿真步长不能整除 `Ts` 时改用
`h' = Ts/ceil(Ts/h)` 并重算步数，先发出 `ALB.TimeStepAdjustedWarning`，再原位重新
离散转子；共享转子被另一配置重新离散后，原配置构建仿真时报 `ConfigurationError`。
`SimulationConfig(integrator="ros2")` 新增可选的两级 Rosenbrock-W 同步耦合积分器，
带热模型的轴承及含主动或外部阀芯子瓦的 `MultiPad` 不支持。修改前在 `df7336f`
冻结了默认 staggered 路径参考
`refs/coupling_default_path_0_4_6_reference_v1.json`/`.npz`，并以精确相等回归；
默认路径的数值与结果元数据保持 0.4.5 不变。

2026-10-20 形成 0.4.7 开发版本，依据见
[ADR-0010](adr/0010-predictor-corrector-coupling-and-bearing-checkpoints.md) 和
[0.4.7 迁移说明](migrations/0.4.7.md)。`SimulationConfig(integrator="predictor_corrector")`
新增可选的预测-校正分区耦合：转子用纯函数 hook 试算，轴承从已提交状态试算（无副作用族
用 `probe_force`，热模型、主动轴承及其 `MultiPad` 用新契约
`CheckpointableRuntimeProtocol` 存档 → 生命周期试算 → 回退），按 Aitken/IQN-ILS 等无导数
规则迭代界面力，最后每个轴承只提交一次。解析算例上迭代版与 PECE 为二阶（误差比约 4），
staggered 为一阶；全部随包族满足存档/回退逐位契约。修改前在 `9432c06` 冻结了热液膜、
带热主动轴承、多瓦和外部阀芯轴承的 staggered 参考
`refs/coupling_staggered_pre_0_4_7_reference_v1.json`/`.npz`；新格式行为参考为
`refs/predictor_corrector_0_4_7_reference_v1.json`/`.npz`。staggered 与 ROS2 路径、0.4.6
两份参考保持精确相等。

## 已实现的主要边界

- 根 namespace 提供严格配置、构建、`Bearing.calculate()`、独立分析、
  仿真、不可变结果和稳定异常；高级扩展按显式 namespace 使用。
- active、liquid-film、Gas、MultiPad、harmonic 和 surrogate 使用正式 runtime。
  旧 Signal、兼容 adapter、宽松配置入口和旧 console entry point 已移除。
- 静平衡统一为 `EquilibriumSolver(bearing)`；动态系数使用正反涡动复数识别。
  mixed-film 直接复用原生 FilmSystem 数值方法，薄 mixin 负责生命周期与结果。
- simulation 在运行前检查转子、mount、嵌套 MultiPad 和物化组件的 local
  `time_step`，区分物理提交、历史记录与 post-commit 完整性。
- 0.4.6 控制器采样周期：只有 PID/模糊 PID 可按 `control.control_period` 以
  仿真步整数倍采样（ADR-0007 第 8 条的受限例外）。仿真在必要时把步长调整为
  `Ts/ceil(Ts/h)`，结束时间向上取整到整数个控制周期，并通过警告、
  `SimulationConfig.time_step_adjustment` 和结果 metadata 报告；独立轴承要求精确
  整数倍。
- 0.4.6 可选 ROS2 积分器（**功能不完善**，实验性；正式计算仍用默认 staggered）：`time_grid.integrator: "ros2"` 或
  `SimulationConfig(integrator="ros2")`。缺省冻结 Jacobian，可按步数或控制周期
  刷新；轴承力经无副作用 probe 同步计算。支持无热液膜、气膜、surrogate、子瓦
  只含这些无热族（surrogate 限固定阀芯）的 `MultiPad` 和无热主动轴承；默认
  staggered 路径不变。
- 0.4.7 可选预测-校正积分器：`time_grid.integrator: "predictor_corrector"` 与
  `time_grid.predictor_corrector`，或 `SimulationConfig(integrator="predictor_corrector",
  predictor_corrector=PredictorCorrectorOptions(...))`。支持全部随包轴承族（含热模型和
  主动轴承），只拒绝 `MultiPad` 内需要外部阀芯的子瓦；不收敛时警告一次
  （`ALB.CouplingIterationWarning`，根 API 29 个符号）或封存失败；只有该积分器写入
  `predictor_corrector_options/diagnostics` 元数据。
- 0.4.5 主动轴承阀配置支持 `second_order`、`static`、`transfer_function`。
  二阶模型使用 `natural_frequency_hz`、`damping_ratio` 和可选 `delay`。
- 显式压力/温度网格支持 P1/P2/Q1/Q2，并共享网格、阶次和自由度。
  `restrictors.flow_projection` 缺省为 `nearest_node`，`element_shape`
  使用真实孔位的原生形函数。压力、流量 Jacobian、热混合源和阀芯线性化使用
  一致投影；两种模式均为集中点源。
- 均匀显式结构网格的 SUPG 尺度按实际坐标跨度、宏观单元数与阶次计算，
  避免高阶重合坐标的浮点尾差产生伪极小尺度。旧配置路径维持原算法。

详细接口见 [包概览](alb_package_overview.md)、[架构](interface_architecture.md)
和 [API 入口](api/README.md)，不在本页重复稳定手册。

## 验证范围与证据

| 证据层级 | 结论及适用范围 |
| --- | --- |
| 历史正式发布 | 0.4.0、0.4.1、0.4.2 的机器验收状态均为 `passed`；只适用于各报告绑定的候选 |
| 既有开发验证 | 文档压缩前记录的最后一次全套数值测试为 `492 passed, 13 skipped, 10 subtests passed`；该记录早于当前未提交修改，不是本次重跑结果 |
| 类型基线文件 | `tools/validation/mypy_layer_baseline_0_4.json` 当前记录 23 个 strict target、352 条实现层诊断和 82 个文件/错误码组；本轮未重跑全项目类型基线门禁 |
| 2026-10-20 0.4.7 预测-校正 | 云端 Linux 环境（与 0.4.6 参考环境相同）。基线 `51cce0b` 全量 pytest 为 49 failed、717 passed、4 skipped、13 errors，失败集合均与环境或外部依赖有关；0.4.7 的全量结果与新增测试数见交付报告 `docs/alb_0_4_7_predictor_corrector_report.md` 第 5 节。0.4.6 两份参考、修改前参考与新行为参考均精确相等。只覆盖解析算例和小网格 FEM 算例；M42 代理、hb34 FEM 液膜、热模型和本地热记忆/LSTM 代理的核对待用户本地完成 |
| 2026-10-20 0.4.6 文档 | 四类生成参考 `--check` 均通过（28 个根符号、189 个轴承字段行、38 个仿真字段行、3 个 namespace 页面）；`tests/unit/docs`、`tests/integration/docs`、三项配置/根 API 参考测试和文档示例 smoke 共 34 项通过；`mkdocs build --strict` 通过。文档与代码一致性核对（HEAD `7d66218`）后重跑：四类 `--check` 通过，前述五组测试（不含示例 smoke）28 项通过，`mkdocs build --strict` 通过。只覆盖文档与生成参考，控制周期和 ROS2 的数值验证以对应 0.4.6 测试和报告为准 |
| 2026-10-09 surrogate C4 | 新增参考回归 14 项与单元测试 28 项，全部通过。参考回归包括真实 M42/M35：`"c4"` 与 `ALBNNC4Canonical` 逐位相等，`"none"` 与修改前构建器逐位相等。邻近 surrogate/API/config/docs 套件 402 项通过；唯一失败 `test_public_site_contains_no_local_absolute_paths` 源自既有未提交的 `site/guides/analysis.md` 本机路径。生成参考检查与 `mkdocs build --strict` 均通过。ALB 环境未安装 mypy，本轮未做类型检查 |
| 2026-10-09 谐波工具 | 59 项相关测试通过；25/50/100 Hz 冻结参考、两种供油投影、解析导数、复数结果保存和失败隔离均覆盖。API 严格类型及新实现层定向检查通过；最终 wheel 隔离计算通过，50 Hz 相对线性残差约 `9.97e-13`。这是当前工作树的功能验收，尚未形成固定 SHA 发布候选 |
| 2026-10-06 文档清理 | 12 项文档与站点测试通过（含严格构建）；四类生成参考检查、4 项审计 CLI 导出检查及文档链接检查通过。未执行完整数值或固定 SHA 发布验收 |
| 2026-09-26 文件整理 | 清理前后均为 631 个 pytest 节点；相关测试 14 passed、1 failed，失败为已有热记忆训练依赖层问题；严格文档构建通过。未执行完整数值回归 |

历史正式证据保留原样:

- [0.4.0 验收](migrations/0.4.0_release_acceptance.json)，候选 `b0761f991452a3c3060e9e51d0cbad6f98a7b296`。
- [0.4.1 验收](migrations/0.4.1_release_acceptance.json)，候选 `a26435e2eb7652d6d64af2194865dd3cf05db61d`。
- [0.4.2 验收](migrations/0.4.2_release_acceptance.json)，候选 `ff491e4dc9668f49e41870c37898f3c4d3a4ddc3`。

供油投影的两侧历史参考分别为
`refs/mesh_independence_legacy_reference_v1.json`、`refs/mesh_independence_legacy_reference_v1.npz`
和 `refs/supply_flow_element_shape_reference_v1.json`、`refs/supply_flow_element_shape_reference_v1.npz`。
当前测试入口见 [一致性说明](formula/pressure_temperature_consistency_review.md)。

旧版构建摘要、多轮开发测试与发布过程可追溯到相应 `docs/migrations/` 文件，
以及提交 `aafb9fc8e099aa8191a7a12293787ec5ed6ac6b9` 中本文件的历史版本。

## 当前风险与下一步

1. 0.4.6、0.4.7 尚未形成固定 SHA 正式发布候选。若发布，先处理工作树归属、完成对应
   manifest/test map 和验收工具，再执行固定候选验收；不移动历史标签。
2. 谐波分析和倾瓦等能力的既有适用边界，以 API 文档及
   [ADR-0007](adr/0007-preserve-validated-numerical-algorithms.md) 为准。
   observer、资源路径 containment 和未明确契约的 TODO 仍按独立问题评估；
   [0.4.2 债务记录](migrations/0.4.2_deferred_debt.md) 中的诊断数量是历史数值。
3. 温度场 `direct` 是继续维护的稳定路径。`newton` 与可能进入同一准 Newton fallback
   的 `direct_then_newton` 当前仍为有效配置值且不发运行时弃用警告，但因实际稳定性
   不及 `direct`，已标记为计划在后续版本通过明确迁移后移除。
   移除前需要版本化配置迁移和对应验证，当前文档维护不改变配置行为。
4. SUPG 解析尺度修补的适用范围是均匀结构网格。局部加密、畸变网格和非零
   润滑油扩散仍需独立验证；不同算法或投影版本的结果不能直接拼成最终 GCI 结论。
5. 原始数据、冻结参考和历史机器报告不因文档压缩改写。当前热求解与配置的
   未提交修改仍需在相应实现任务中明确验证范围。
6. 文件整理检查发现 `ALB.surrogate.training.thermal_memory_training` 导入
   `ALB.dynamics.identification`，违反当前 `test_production_imports_obey_namespace_layers`
   的依赖白名单。源码和测试与清理前哈希一致，属于已有热记忆工作的问题；后续应在该实现任务中明确代码归属或依赖契约，不通过文件清理放宽门禁。
7. 现有 surrogate 配置若引用 M35/M42 而未写 `model_package.symmetry`，现在会构建失败，需补写
   `"c4"`；要复现旧的原网络结果时写 `"none"`。SURROGATE_TRAIN 后续打包第一象限模型时，
   应在 metadata 写入 `inference_symmetry`。C4 只适用于四瓦、阀芯指令轴随瓦旋转的对称轴承；
   坐标轴和原点处的 C4 边界误差保持原样。
8. ROS2 积分器在 0.4.6 标记为功能不完善（实验性）。代理模型族未做数值收敛验证，
   尚未与论文降阶模型 RK4 解交叉核对。ROS2 首版拒绝热模型轴承，以及含主动或外部阀芯子瓦的 `MultiPad`。冻结 Jacobian
   只影响稳定裕度：轴颈接近壁面时裕度下降，打包 surrogate 在居中处存在平方根型
   刚度奇异，应设置 `jacobian_refresh` 或偏心 `jacobian_state`。外部 spool provider
   采用每步零阶保持，只有分段常数输出才保持二阶。默认路径参考仅保证当前记录环境下
   的精确相等，其他平台可能出现舍入级差异，需按迁移说明用环境变量指向本地生成的
   参考对复核。0.4.6 新行为参考 `refs/ros2_control_period_0_4_6_reference_v1.*`
   由完成后的实现（`7b97f41`）生成，回归测试为
   `tests/regression/dynamics/test_ros2_control_period_0_4_6_reference.py`。
9. 0.4.7 预测-校正积分器只在解析算例和小网格 FEM 算例上验证。需在本地用 M42 代理、
   hb34 FEM 液膜（网格尺度力跳变可能使迭代来回振荡，默认 `on_nonconvergence="warn"`
   会计数并警告）、热模型以及热记忆/LSTM 代理核对。主动轴承的阀对输入做一阶保持插值，
   `m > 1` 时阀芯通道降为一阶（解析算例误差比约 2），改为采样时刻起作用的零阶保持可恢复
   二阶，但会改变默认路径数值，需单独立项。不实现存档协议的 spool provider 每步保持，
   该通道为一阶。

## 外部工作与阅读入口

- 训练、采样、队列与模型状态: `../SURROGATE_TRAIN/docs/current_runtime_status.md`。
- 论文计算、网格图表和 GCI 的实际进度: `F:/BaiduSyncdisk/博士论文/PAPER_WORK/docs/current_task_status.md`。
  网格任务入口和实际进度以该工作区记录为准。
- [用户手册](alb_albnn_quickstart.md)、[远程操作](remote_workstation_connection.md)、
  [文件归属](file_classification.md)、[文档路径索引](daily_maintenance/daily_doc_update_index.md)。
- 当前开发接口迁移: [0.4.3](migrations/0.4.3.md)、[0.4.4](migrations/0.4.4.md)、[0.4.5](migrations/0.4.5.md)、[0.4.6](migrations/0.4.6.md)、[0.4.7](migrations/0.4.7.md)。
- 公共用户站点: <https://waj734014160-creator.github.io/ALB/>。
  最近保存的发布记录对应源提交 `30b42fcc6bb667d0b0cdb1b2b5ebb62cdb1b28c7`；
  本次未核验线上最新部署。
