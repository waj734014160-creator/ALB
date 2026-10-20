# ALB_MAIN 当前状态

参考来源：当前 Git 工作树、`pyproject.toml`、源码、版本验收报告和本次文档检查。

## 当前快照

最近本地核对: 2026-10-09，本轮范围为热耦合谐波线性化工具、相关数值回归和安装包调用。本文区分当前工作树、历史发布和局部验证。

| 项目 | 当前事实 |
| --- | --- |
| 开发分支 | `codex/alb-0.4.5` |
| 当前 HEAD | `aafb9fc8e099aa8191a7a12293787ec5ed6ac6b9` |
| 包版本 | `re-alb 0.4.5`，导入名 `ALB`，最低 Python 3.10 |
| 配置与模型包格式 | JSON5 schema 和 surrogate package 仍为 `0.4.0` |
| 发布边界 | 最新已有固定候选正式验收的版本为 `v0.4.2`；0.4.3 至 0.4.5 仍属开发边界 |
| 工作树 | 存在先于本次文档维护的热求解、配置说明、测试和 Claude 配置修改；未提交内容不计入固定发布候选 |

当前工作重点包含 0.4.5 接口和压力-热耦合契约维护，以及独立热记忆代理接口。
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

## 已实现的主要边界

- 根 namespace 提供严格配置、构建、`Bearing.calculate()`、独立分析、
  仿真、不可变结果和稳定异常；高级扩展按显式 namespace 使用。
- active、liquid-film、Gas、MultiPad、harmonic 和 surrogate 使用正式 runtime。
  旧 Signal、兼容 adapter、宽松配置入口和旧 console entry point 已移除。
- 静平衡统一为 `EquilibriumSolver(bearing)`；动态系数使用正反涡动复数识别。
  mixed-film 直接复用原生 FilmSystem 数值方法，薄 mixin 负责生命周期与结果。
- simulation 在运行前检查转子、mount、嵌套 MultiPad 和物化组件的 local
  `time_step`，区分物理提交、历史记录与 post-commit 完整性。
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

1. 0.4.5 尚未形成固定 SHA 正式发布候选。若发布，先处理工作树归属、完成对应
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

## 外部工作与阅读入口

- 训练、采样、队列与模型状态: `../SURROGATE_TRAIN/docs/current_runtime_status.md`。
- 论文计算、网格图表和 GCI 的实际进度: `F:/BaiduSyncdisk/博士论文/PAPER_WORK/docs/current_task_status.md`。
  网格任务入口和实际进度以该工作区记录为准。
- [用户手册](alb_albnn_quickstart.md)、[远程操作](remote_workstation_connection.md)、
  [文件归属](file_classification.md)、[文档路径索引](daily_maintenance/daily_doc_update_index.md)。
- 当前开发接口迁移: [0.4.3](migrations/0.4.3.md)、[0.4.4](migrations/0.4.4.md)、[0.4.5](migrations/0.4.5.md)。
- 公共用户站点: <https://waj734014160-creator.github.io/ALB/>。
  最近保存的发布记录对应源提交 `30b42fcc6bb667d0b0cdb1b2b5ebb62cdb1b28c7`；
  本次未核验线上最新部署。
