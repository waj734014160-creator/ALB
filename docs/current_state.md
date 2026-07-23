# ALB_MAIN 当前状态

## 文档角色

- 角色：ALB_MAIN 项目当前状况记录。
- 目的：集中记录 ALB_MAIN 当前开发阶段、最近确认的基线、当前验证状态、已知问题和下一步，使接手者能够快速恢复上下文。
- 允许更新：当前分支和基线、正在进行的项目级工作、已经实际执行的验证及结果、当前风险或阻塞、近期下一步、相关证据指针。
- 禁止更新：SURROGATE_TRAIN 的训练/采样实时进度、论文任务实时状态、完整历史流水、原始日志正文、稳定 API 手册和未经验证的结论。
- 更新节奏：ALB_MAIN 的开发阶段、工作重点、验证结论、风险或下一步发生实质变化时更新；旧状态应压缩为结论，不在本文持续堆叠时间线。
- 事实来源 / 相关文档：
  `AGENTS.md`、
  `docs/daily_maintenance/daily_doc_update_index.md`、
  `docs/project_overview.md`、
  `docs/interface_architecture.md`、
  `docs/next_interface_development_plan.md`、
  `docs/adr/README.md`、
  `docs/alb_package_overview.md`、
  `docs/run_index.md`、
  Git 提交和本文列出的验收报告。

本文只记录 `ALB_MAIN`。ALBNN 活跃训练状态属于 `../SURROGATE_TRAIN/docs/current_runtime_status.md`；论文计算状态属于 `F:/BaiduSyncdisk/博士论文/PAPER_WORK/docs/current_task_status.md`。

## 当前快照

- 分支：`codex/full-repo-refactor`。
- 开发包版本：`0.3.0`；最低 Python：`3.10`；0.3 wheel 已重建并通过正式验收，尚未创建 0.3 发布标签。
- 最近正式发布标签：`v0.2.0`。
- 重构前源码基线：commit `a4b2be1`，annotated tag `pre-full-repo-refactor-20260720`。
- 完整行为参考基线：commit `d6d7432`，annotated tag `pre-full-repo-refactor-refs-20260720`。
- 冻结参考：`refs/full_repo_refactor_v1/`，11 个领域、121 个冻结数组；现有 v1 参考不得覆盖。
- 热收敛补充参考：`refs/full_repo_refactor_addendum_v1/`，3 个自包含 case、40 个冻结数组；由重构前 commit `a4b2be1` 的隔离源码生成，并由 annotated tag `full-repo-refactor-thermal-addendum-v1-20260721` 固定。
- 热 Newton 修正参考：`refs/thermal_segregated_newton_reference_v2.{json,npz}`，33 个数组；commit `d9d37de` 先于测试修正建立，v1 保持不变。S0011 部分冻结的是当前代码和当前 shared config 回放，不是缺失的历史 `share.json5` 精确重建。
- 转子时步修正参考：`refs/ross_rotor_time_validation_reference_v2.{json,npz}`，14 个数组；commit `4713eec` 先建立修正前合法轨迹，commit `e375d2d` 再修复校验，既有 v1 未改动。
- ALBSV 状态修正参考：`refs/albsv_convergence_state_reference_v2.{json,npz}`；重复收敛查询已改为纯读取，完成时压力和力保持精确一致。
- CSOrifice 单调求解参考：commit `765b9b6` 先创建 `refs/csorifice_monotonic_reference_v2.{json,npz}`，冻结局部供油、零供油回流、反向流、端点及完整热耦合共 38 个数组；`refs/csorifice_monotonic_consumers_reference_v2.{json,npz}` 另冻结 ALBSV direct-spool 与 S0011 的 57 个下游数组。既有 v1/v2 参考均未覆盖。
- 重构后审查参考：`refs/control_state_contract_reference_v1.{json,npz}` 含 22 个控制状态数组；`refs/rotor_bearing_coupling_time_reference_v3.{json,npz}` 含 10 个旧/新耦合时序数组；有意改变的 orifice AST 由 `encoding_repair_reference_v2.json` 接管，既有编码 v1 未覆盖。
- 二轮审查参考：commit `1ef2ee8` 先创建 `refs/rotor_dof_coupling_reference_v4.{json,npz}`，以真实 ROSS 4/6-DOF 转子、非零状态相关轴承力和 `force0/force1` 插值冻结 40 个数组，并创建 `refs/control_lifecycle_reference_v2.{json,npz}` 冻结旧重复 `output()` 缺陷和 21 个修正目标；commit `1eb9538` 再实施生产修正。既有参考未覆盖。
- 三轮审查参考：`refs/third_review_compatibility_reference_v3.{json,npz}` 在生产修正前冻结 LQG、重复控制器、旧式控制器、ServoValve2、合法 6-DOF 状态读取和默认配置共 17 个数组；修正后逐元素精确相等。
- 四轮审查参考：`refs/fourth_review_release_reference_v4.{json,npz}` 在生产修正前冻结默认 harmonic-PID 的构造、运行和重新初始化轨迹、普通 ALB 启用控制时的阀命令，以及非默认 PID 配置回读，共 13 个数组；当前工作树逐元素精确相等。
- 五轮审查参考：`refs/fifth_review_release_reference_v5.{json,npz}` 在第五轮生产修正前冻结 harmonic 成功运行/重新初始化、PID/FuzzyPID 合法带标签回读和三个公开 ALB 子类的默认初始矩阵，共 27 个数组；当前工作树逐元素精确相等。
- 六轮审查参考：`refs/sixth_review_runtime_reference_v6.{json,npz}` 在第六轮生产修正前继续冻结第五轮 27 个合法行为数组；当前工作树逐元素精确相等。
- 七轮审查参考：`refs/seventh_review_release_reference_v7.{json,npz}` 在 commit `908abd7` 的生产修正前冻结 harmonic 合法控制器、阀、位移/速度、力和重新初始化路径共 27 个数组；修正后逐元素精确相等，既有 v1-v6 参考均未覆盖。
- 八轮制品身份参考：commit `a29290e` 在工具修正前创建 `refs/eighth_review_wheel_identity_reference_v8.json`，冻结 candidate `4d6e609` 的 119 个 release Git blob、规范源码摘要 `39bece7c…`、v7 行为参考哈希，以及两份旧 wheel 证据的差异；生产 `ALB/**` 与运行时 `pyproject.toml` 内容保持精确一致。
- 原生控制生命周期参考：commit `00a842b` 创建 `refs/native_control_lifecycle_reference_v9.{json,npz}`，在生产修改前冻结 LQG、重复控制器和二阶伺服阀的 18 个多步数组；迁移后逐元素精确相等，既有 v1-v8 参考均未覆盖。
- ADR 审查闭环参考：commit `4982b68` 创建 `refs/adr_review_closure_reference_v1.{json,npz}`，在本轮生产修正前冻结 coupling 时间/单位、recorder、legacy adapter、配置和保存边界；commit `30dc5cc` 创建同机性能与峰值内存基线，既有参考均未覆盖。
- 当前阶段：0.3.0 五份 Accepted ADR 的已承诺边界完成实现和 detached 正式验收。F01-F64 中 63 项已实现；F35 按 ADR 保留到最早 0.4.0，不宣称 64/64。候选 `056e319` 已通过 551 passed、13 skipped、0 warnings、27 subtests；564 节点全部收集，134 个版本化 required nodeid 通过，26 个 strict mypy 目标通过，领域历史诊断从 221 降至 151。

## 已完成的 0.2.0 边界

1. `ALB.__init__` 只公开版本、`UnitSystem`、`StepContext`、`ConvergenceStatus` 和基础计算块协议。
2. 旧 `ALB.base/film/bearing/thermal/controller/nn/alb/tool/task/remote` 等平铺模块已删除，不提供 facade。
3. 实现按 `contracts`、`core`、`config`、`physics`、`control`、`dynamics`、`surrogate`、`systems`、`infrastructure` 和 `workflows` 分类。
4. 标准 DTO、显式计算生命周期、唯一物理时步提交、统一收敛状态、`ResultBundle` 和 `ArtifactWriterProtocol` 已落地。
5. Reynolds、热耦合、控制、转子、ALBNN、coupling 和谐波线性轴承的冻结行为保持精确一致；`K`、`C` 和复数 `G_xv` 作为正式能力保留。
6. `RossRotor` 已拆分 `current_state()` 与 `advance()`；`output()` 不再承担隐藏推进。
7. 配置迁移和 surrogate model-package/scaler 迁移均提供默认不覆盖原文件的 CLI 与工具脚本。
8. generic remote engine 位于 `ALB.infrastructure.remote`；ALBNN 专用队列位于 `ALB.surrogate.training.remote`。
9. 邮件能力改为 `SmtpNotifier`，只读取注入配置或环境变量；tracked example 不含私人默认信息。
10. 正式 pytest 只从 `tests/` 收集；诊断和手动工具分别位于 `tools/diagnostics` 与 `tools/manual`。
11. CSOrifice 的 `q_leak` 固定为 `0.0`；所有压力方向共用一个带压力物理边界的单调标量根，不再通过 `fsolve` 初值或工况分支选择解法，装配导数改为隐式解析式。
12. 重构后审查确认的 13 个具体问题已修复：Python 3.11+ 配置导入、耦合时间轴、LTI MIMO/时间/输出、控制器复位、ROSS 节点载荷、阀芯边界、`no_step`、空控制器、固定 Ki、builder 参数、ledger、LQG 空历史和 legacy 编码回退。
13. 二轮审查确认的 5 个问题已修复：ROSS 4/6-DOF 统一布局、真实 coupling 精确门禁、无控制器保存及无量纲装配、中途异常后的 coupling 强制失效，以及 LTI/PID/FuzzyPID 的只读 `output()` 生命周期。
14. 三轮审查确认的 5 个问题已修复：ALB/harmonic 对严格及旧式控制器的共享适配、coupler 失效后的 `results/save` 封锁、`current_state()` 严格节点校验、无控制器配置的显式表达与回读，以及 ServoValve2 单次 evaluate。
15. 第四轮审查修正已提交：harmonic 真实公共生命周期支持控制器实例/工厂注入；永久控制许可与定时启动分离；无控制器普通 ALB 输出零命令；PID/FuzzyPID/none 带类型标签精确回读；coupler 改拓扑后立即失效；正式发布证据改为测试前必须是干净 tracked 工作树。
16. 第五轮审查修正已提交并验收：harmonic 重初始化失败后整体失效并封锁状态出口；正式验收拒绝敏感 untracked/ignored 输入并验证 HEAD 前后一致；带标签的嵌套控制器配置严格校验类型和字段；`ALBSV`、`NodimALB`、`NodimALBSV` 不再共享可变默认配置。
17. 第六轮审查修正已提交并验收：`input()`/`output()` 的控制器、命令整形、双阀和记录阶段由严格 runtime guard 封锁半推进异常；正式验收从 detached candidate 执行，不再依赖本地 `outputs/.devtools`。旧热参考生成器固定为 LF checkout，历史构建证据路径采用可移植的后缀校验。
18. 第七轮审查修正已提交并验收：harmonic 在任何 float 转换前拒绝 complex，并对控制器命令、阀芯、轴承输入、quadrature 和最终力执行形状与有限性校验；pytest 使用固定 9.0.3、禁用插件自动加载并精确校验 skip/warning/xfail/插件；wheel 从运行专属 tracked 源码副本构建并核对候选源码和 METADATA，不再污染 detached 候选树。
19. 八轮制品身份修正已提交并验收：wheel 输入改由 `git cat-file` 读取 candidate blob，不再复制受换行、smudge 或文件时间影响的工作树字节；`SOURCE_DATE_EPOCH` 固定为最近一次 release 输入提交时间；同一候选必须连续两次生成相同 build tag `1` wheel；外层只发布 detached 实际安装验证的那一份精确字节。
20. P2 控制生命周期第一批已完成：LQG、重复控制器和 `ServoValve2` 的状态推进全部移入 `evaluate()`，重复 `output()` 只读；direct-spool 使用显式 `set_spool()`，旧控制器只经限期 `LegacyControllerAdapter` 接入；共享状态名采用 `NEW/READY/RUNNING/FAILED`，复杂数和非有限输入共用 core 校验。
21. 生命周期、数值和接口契约已收口：Harmonic、coupler、RossRotor、PID、LQG、重复控制器和阀复用 `RuntimeLifecycle`；控制器、阀、转子、结果记录器和 runtime lifecycle 均有正式 Protocol；数值输入统一在状态改写前拒绝 complex、NaN、Inf、错误形状和非法时间。
22. 大型模块职责已拆分：`controllers.py`、`config/_models.py` 和 `systems/alb/assembly.py` 变为小型兼容重导出，实际实现分别进入控制子领域、配置 `*_models` 以及 ALB runtime/builder/factories/linear/surrogate/switch 模块；Rotor 的布局、推进、结果/保存树，coupling 的 runtime/result，以及 harmonic 的 runtime/result/coefficient contract/resource IO 已分别归位。
23. 当前配置采用带 `0.3.0` 版本的 `ALBConfigEnvelope`；legacy 平铺配置只通过独立、单向、默认不覆盖源文件的迁移函数进入当前 schema。strict mypy 以 26 个零错误目标加四领域完整精确基线覆盖实现，当前锁定 62 个领域文件、151 条历史诊断和 46 个文件/错误码组。
24. 发布执行层已拆为候选选择、Git blob 导出、构建、安装、测试/类型检查、证据生成和发布阶段；0.2 runner 实际组合这些阶段，分层 mypy 也成为正式发布门禁。

## 当前验收结论

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 精确行为回归 | 11 个领域、121 个主参考数组使用精确相等检查通过；thermal direct/Newton/transient 的 40 个补充数组、残差历史和提交状态也精确通过 | `refs/full_repo_refactor_v1/`、`refs/full_repo_refactor_addendum_v1/`、`tests/regression/` |
| 242 节点迁移 | 242 个基线节点全部映射；另有 19 个原非收集文件明确分类 | `docs/migrations/0.2.0_test_map.json` |
| 0.2.0 标签验收 | 293 passed、33 skipped、12 warnings、7 subtests passed；测试前后 tracked 状态增量为 0 | `docs/migrations/0.2.0_release_acceptance.json` |
| 发布后数值修正验收 | 297 passed、30 skipped、12 warnings、7 subtests passed；4 个 S0011 节点全部 passed，mypy 19 个文件无问题，tracked 状态增量为 0 | `docs/migrations/0.2.0_post_release_numeric_acceptance.json` |
| 发布后转子时步验收 | 300 passed、30 skipped、12 warnings、7 subtests passed；3 个 RossRotor 时步节点和 4 个 S0011 节点全部 passed，mypy 19 个文件无问题，tracked 状态增量为 0 | `docs/migrations/0.2.0_post_release_rotor_acceptance.json` |
| SURROGATE_TRAIN 消费者迁移及后续修复 | 329 passed、13 skipped、12 warnings、7 subtests passed；23 个 declared 文件中 20 个迁移改写、3 个 context 文件按计划不改；热力 `sx/sy` 四瓦参考另有 4 项精确回归通过；旧平铺 import 为 0 | `docs/migrations/0.2.0_surrogate_train_post_migration_audit.json` |
| CSOrifice 单调求解修正 | 339 passed、13 skipped、1 warning、7 subtests passed；352 个节点全部收集，测试前后 tracked 状态增量为 0；局部、完整热耦合、ALBSV 与 S0011 共 95 个修正参考数组精确通过 | `refs/csorifice_monotonic_reference_v2.json`、`refs/csorifice_monotonic_consumers_reference_v2.json`、`tests/regression/hydraulics/test_csorifice_monotonic_reference.py` |
| 重构后代码审查修正 | 368 passed、13 skipped、0 warnings、9 subtests passed；381 个节点全部收集；mypy 19 个文件无问题；测试前后 tracked 状态增量为 0 | `docs/migrations/0.2.0_post_refactor_review_acceptance.json` |
| 二轮代码审查修正 | 375 passed、13 skipped、0 warnings、9 subtests passed；388 个节点全部收集；contracts/core 的 19 个文件 mypy 无问题；真实 4/6-DOF coupling、LQG 映射和控制生命周期按新参考逐元素精确通过；测试前后 tracked 状态增量为 0 | `docs/migrations/0.2.0_second_review_acceptance.json` |
| 三轮工作树验收（非发布绑定证据） | 390 passed、13 skipped、0 warnings、11 subtests passed；17 个兼容参考数组逐元素精确相等；但 `candidate_commit=e2313c7`，测试时 tracked 工作树已包含第三轮修改，不能证明提交 `7910eaa` 的干净树通过 | `docs/migrations/0.2.0_third_review_acceptance.json` |
| 四轮代码审查修正 | 候选提交 `0abf6dd`：402 passed、13 skipped、0 warnings、15 subtests passed；415 个节点全部收集；第四轮 12 个关键节点及 4 个子测试全部通过；13 个 v4 有效行为数组逐元素精确相等；contracts/core 的 19 个文件 mypy 无问题；测试前后 tracked 状态均为空 | `docs/migrations/0.2.0_fourth_review_acceptance.json` |
| 五轮代码审查修正 | 候选提交 `27729ee`：413 passed、13 skipped、0 warnings、27 subtests passed；426 个节点全部收集；第五轮 11 个关键节点及相关子测试全部通过；27 个 v5 有效行为数组逐元素精确相等；contracts/core 的 19 个文件 mypy 无问题；测试前后 tracked、敏感 untracked/ignored 状态均为空且 HEAD 一致 | `docs/migrations/0.2.0_fifth_review_acceptance.json` |
| 六轮代码审查修正 | 候选提交 `66fe326`：421 passed、13 skipped、0 warnings、27 subtests passed；434 个节点全部收集；第六轮 8 个关键节点全部通过；27 个 v6 有效行为数组逐元素精确相等；contracts/core 19 个文件和独立 runtime 1 个文件严格 mypy 通过；detached worktree 测试前后 HEAD、tracked 状态及敏感输入均保持不变 | `docs/migrations/0.2.0_sixth_review_acceptance.json` |
| 七轮代码审查修正 | 候选提交 `728b198`：436 passed、13 skipped、0 warnings、27 subtests passed；449 个节点全部收集；27 个 v7 合法行为数组逐元素精确相等；pytest 9.0.3、37 个最终插件、精确 skip allowlist、contracts/core 及 harmonic runtime 严格 mypy、现场 wheel 和 detached worktree 前后状态全部通过 | `docs/migrations/0.2.0_seventh_review_acceptance.json` |
| 八轮 wheel 制品身份修正 | 候选提交 `62b53be`：438 passed、13 skipped、0 warnings、27 subtests passed；451 个节点全部收集；4 个制品身份关键节点通过；Git blob 规范摘要、两次构建、detached 安装、最终发布文件、构建报告和验收报告的 wheel SHA 全部一致 | `docs/migrations/0.2.0_eighth_review_acceptance.json` |
| P2 架构正式验收 | 运行时候选 `cac4a05` 与 canonical 候选 `fd5029e` 均为 487 passed、13 skipped、0 warnings、27 subtests passed；500 个节点、87 个关键 nodeid、20 个 strict 目标通过，58 个领域文件的 221 条历史诊断精确匹配；detached 前后 HEAD 和 launcher tracked 状态不变 | `docs/migrations/0.2.0_p2_architecture_acceptance.json`、`docs/migrations/0.2.0_release_acceptance.json`、`docs/migrations/0.2.0_p2_architecture_closure.md` |
| 0.3.0 ADR 架构验收 | 候选 `056e319`：551 passed、13 skipped、0 warnings、27 subtests passed；564 节点、134 个 required nodeid、26 个 strict 目标通过，62 个领域文件的 151 条历史诊断精确锁定；F01-F64 manifest 为 63 项实现、F35 延期；两次规范构建、detached 安装和发布 wheel SHA 一致 | `docs/migrations/0.3.0_release_acceptance.json`、`docs/migrations/0.3.0_build_acceptance.json` |
| PAPER_WORK 消费者迁移 | 27 个 declared 文件和 2 个动态 helper 均有可恢复快照；25 个 direct 与 2 个 helper 已改写，24 个 guarded import smoke 通过，旧平铺 import 为 0；M0031/M0035 package 校验和可信加载通过 | `docs/migrations/0.2.0_paper_work_post_migration_audit.json` |
| 分层与循环依赖 | 116 个模块、217 条内部边无 namespace/module-level 循环；数值层不依赖 infrastructure；47 个旧模块均不存在 | `tests/validation/test_import_boundaries.py` |
| 导入迁移 | 65 个旧模块、479 个定义、9 个公共 alias 和 68 个旧根导出均有机器映射；554 个非删除目标可解析 | `docs/migrations/0.2.0_import_map.json` |
| 分层严格类型 | mypy 2.3.0：26 个 contracts/core/领域边界/发布工具目标零错误；`config/control/dynamics/systems` 全部 62 个 Python 文件进入精确增量基线，当前 151 条历史诊断、46 个文件/错误码组 | `tools/validation/run_layered_mypy.py`、`tools/validation/mypy_layer_baseline.json` |
| Optional dependency | 各领域 namespace 的缺依赖提示与 extra 安装信息测试通过 | `tests/unit/contracts/`、`tests/validation/test_optional_dependency_errors.py` |
| 0.3 同机性能与峰值内存 | 时间比：film 0.9998、thermal 1.0293、ALB 1.0068、ALBNN 0.9868、coupling 0.9825；峰值内存比均约为 1.00，绝对变化均小于 2 KiB；五项精确参考、时间和内存门禁全部通过 | `docs/migrations/0.3.0_performance.json` |
| Wheel | `re_alb-0.2.0-1-py3-none-any.whl` 从候选 Git blob 构建；146 个发布输入逐字节核对、METADATA 与 `pyproject.toml` 一致，稳定双构建、隔离安装、8 组 extras import smoke、namespace smoke 和两个 CLI `--help` 通过 | `docs/migrations/0.2.0_build_acceptance.json`、`docs/migrations/0.2.0_p2_architecture_build_acceptance.json` |

当前 0.3.0 发布 wheel 为 `dist/re_alb-0.3.0-1-py3-none-any.whl`，SHA-256 为
`9553b272ce92aab0f0e65e239cd9537518dbe57ed3546294c90cb25e73d47e80`。同一候选的两次 Git blob
规范构建、detached 实际安装制品、构建报告、验收报告和磁盘最终文件 SHA 完全一致。

## 外部消费者状态

迁移前只读 v1 审计保持不变，覆盖：

- `SURROGATE_TRAIN` 23 个文件：19 个 direct、4 个 context。
- `PAPER_WORK` 27 个文件：25 个 direct、2 个 transitive。

每个文件的原始 SHA-256、旧 import、0.2 目标 namespace 和语义迁移门槛位于 `docs/migrations/0.2.0_external_consumer_audit.json`。SURROGATE_TRAIN 的逐文件新哈希、三个 package manifest 和验证结果见 `docs/migrations/0.2.0_surrogate_train_post_migration_audit.json`。PAPER_WORK 不是 Git 仓库，修改前已创建 29 文件可恢复快照；25 个 direct 和两个审计遗漏的动态 helper 已改写，M0031/M0035 切到 `package_v0_2`，逐文件新哈希与剩余边界见 `docs/migrations/0.2.0_paper_work_post_migration_audit.json`。

## 已知风险与边界

- 原发布验收的 33 个 skip 分为：`SURROGATE_TRAIN` 17、外部 `VALIDATION` 13、S0011 旧路径 3。S0011 与 SURROGATE_TRAIN 两组均已解除；当前全量只剩外部 `VALIDATION` 13 项。
- 两个 liquid-film 测试曾用 `6.0 * miu * omega * l**2 / (ps*c**2)`，把 Reynolds bearing number 放大 4 倍；现统一通过 `FilmNondimScales` 使用生产定义 `1.5`。`ALB.physics.gas` 中的 `6.0` 属于另一套气体轴承定义，不在此次修正范围。
- S0011 v2 已嵌入三条输入、当前 resolved source config 和 fixed-point config，不再读取外部 84.3 MB CSV。历史 `alb12.json5` 哈希一致，但原 `share.json5` 已缺失且当前 hash 不同；因此 v1 到 v2 的 dimensional/S0011 漂移不能归因于 lambda 修正，也不能宣称完成历史配置精确复现。
- `RossRotor._check_time()` 已改为在状态变更前拒绝非有限或不匹配 `dt` 的时间；合法 global/node 轨迹对修正前 v2 参考精确一致，被拒绝调用的时间、载荷和状态保持不变。
- `task/task_albnn_data.py` 已通过 `DirectSpoolBearingInput/DirectSpoolBearingBlock` 传递 `sx/sy`，三个冻结工况的力值逐元素精确相等。`task/task_alb_data2.py` 仍有 dimensional 模型配合 `input(nodim=True)`、`output(nodim=False)` 的混合单位边界，严格端口化前必须另建尺度适配器和冻结参考。
- direct-spool 的旧完成信号已修复：`FilmSystem` 锁存最近一次求解状态，公开查询不再推进自适应阻尼；诊断必须读取 `latest_result` 快照而不是调用会继续迭代的 `output()`。
- CSOrifice 现只接受 `q_leak == 0.0`；旧配置若保存了任何非零泄漏量会在构造阶段失败，必须先明确其物理含义，不能静默忽略。统一单调解在零供油压力、节点负压时仍求同一质量守恒根，避免“结果已收敛但 `fsolve` 因方程尺度继续重复迭代”的假停滞。
- `task/task_thermal_forces.py` 已通过独立 v2 参考修复 `sx/sy`：`sy` 驱动 up/down，`sx` 驱动 right/left，标签为四瓦总力、平均有效温度和全瓦收敛。声明的 `pooln` 仍未接入串行循环。
- 当前实际引用的 M0031、M0035 和 KNN 基线已生成默认不覆盖源文件的 `package_v0_2`；未来 base/expert/residual 训练仍输出松散 checkpoint/scaler，自动生成 0.2 package 尚待独立实现。
- 旧 `ALB.nn` pickle 不属于 0.2 运行时兼容面。必须先使用显式迁移工具生成新的 model package，并只对可信 pickle 启用加载。
- 删除当前工作树中的私人邮件默认值不会抹除 Git 历史；相关 SMTP 凭据仍需在外部轮换。
- thermal 主参考的 direct/Newton/transient 收敛证据已由 addendum 补齐；但现有性能与热参考仍主要是小算例，且 orifice cooling、非零导热、生产尺寸 M0035 和大型 ROSS 性能不在当前精确门禁覆盖内。
- 性能门禁使用固定的小型 film、thermal、ALB、ALBNN 和合成 coupling case，能约束本次重构，不代表生产尺寸 M0035 或大型 ROSS 模型的绝对性能。
- 两张会被重生成的 thermal 热图已解除 Git 跟踪但保留本地文件；`.codex/` 与 `test/control/LQG/` 也保留原地。四类路径均由根 `.gitignore` 精确忽略。
- 第三轮验收 JSON 只证明带未提交修改的工作树通过测试，不绑定提交 `7910eaa`，因此只保留为历史工作树证据。第四轮已完成“代码提交 `dc2de7f`、测试映射提交 `0abf6dd`、干净树验收、证据提交”的闭环；正式报告的 `candidate_commit` 为 `0abf6dd`，测试前后 tracked 状态均为空。
- 第五轮已完成“代码提交 `690d69a`、测试映射提交 `27729ee`、干净候选验收、证据提交”的闭环。新的验收门禁会拒绝 `ALB/`、`tests/` 中未提交文件、`tools/` 中未提交 Python 输入和根目录 Python/config 输入（包括被 ignore 的文件），并要求测试前后 HEAD 不变；正式报告的 `candidate_commit` 为 `27729ee`。
- 第六轮已完成“代码与可移植性修复、测试映射提交 `66fe326`、detached 干净候选验收、证据提交”的闭环。验收器从候选 SHA 建立位于 `ALB_PROJECTS` 下的临时 worktree，使外部 `SURROGATE_TRAIN` 只读测试仍能找到兄弟目录；完成后删除临时 worktree。候选内部扫描任意位置的未提交 `.py/.pyi/.pyd/.so`，并为 mypy 创建、使用和清理全新运行目录；正式报告的 `candidate_commit` 为 `66fe326`。
- 第七轮已完成“v7 合法行为参考、生产与验收门禁修正、449 节点测试映射、wheel 构建证据、detached 候选验收”的闭环。首次正式运行因构建后端在候选树生成 `build/lib/**` 被敏感输入门禁拒绝；修正为运行专属 tracked 源码副本后重跑通过，证明该门禁实际生效。正式报告的 `candidate_commit` 为 `728b198`。
- 八轮已完成“Git blob 规范参考、可复现双构建、451 节点测试映射、detached 安装、最终制品发布和双报告同 SHA”的闭环。旧构建报告 `5266ca0…` 与七轮现场 wheel `6ae4436…` 只保留在 v8 参考中作为问题证据；当前构建报告和正式验收均绑定候选 `62b53be`、源码摘要 `39bece7…` 和发布 wheel `a6750b0d…`。首次八轮正式运行因内部过早清理已验证 wheel 而未生成证据，调整交接顺序后完整重跑通过。
- P2-1 至 P2-12 的完成边界见独立收敛报告。最终补充的 RossRotor 生命周期、`rotor_results` 和 `harmonic_coefficients` 已纳入 strict mypy 与 87 个关键 nodeid 预检；P2 专用和默认 canonical 机器报告均已通过。发布 runner 中 0.2 专用关键 nodeid 集合仍是版本策略，fresh 工具只固定直接版本、尚未使用带哈希 constraints/wheelhouse；这属于后续供应链加固，不改变“通用发布阶段已经拆分并实际复用”的 P2-12 结论。
- 分层 mypy 的历史诊断已从 221 条降至 151 条并精确锁定，不是“全部 strict 零错误”。后续只能按小范围提交减少基线，禁止以宽泛 ignore 或整目录排除伪装清零。
- F01-F64 的当前机器门禁明确记录为 63 项实现、F35 延期到最早 0.4.0。F35 仍取决于 film/thermal/rotor 内外部 Signal 消费者清零和一个完整 0.3.x 兼容周期，不得为了得到“64/64”数字提前删除兼容面。

## 当前下一步

1. 以 0.3.x 兼容周期审计 film/thermal/rotor 和外部 Signal 消费者；只有消费者清零后，最早在 0.4.0 物理删除 legacy adapters。
2. 后续按文件逐步减少 151 条历史 mypy 诊断；每次只降低精确基线，不扩大 relaxations。
3. 将 `run_release_acceptance_0_2.py`、`validate_wheel_0_2.py` 的历史文件名迁为版本无关 launcher；当前逻辑已经验证 0.3，但文件名仍是兼容债务。
4. 为 fresh 工具链增加带哈希 constraints 或 wheelhouse；版本专用关键 nodeid 集合可迁入独立 manifest。

## 证据入口

- 架构：`docs/interface_architecture.md`。
- 下一阶段接口与运行时目标：`docs/next_interface_development_plan.md`。
- 下一阶段架构决定：`docs/adr/README.md`。
- 下一阶段阶段 0 冻结参考：`refs/alb_runtime_transition_reference_v1.{json,npz}`、`refs/alb_runtime_families_reference_v1.{json,npz}`、`refs/bearing_unit_boundary_reference_v1.{json,npz}`、`refs/coupling_failure_save_reference_v1.{json,npz}`。
- 0.3 正式验收：`docs/migrations/0.3.0_release_acceptance.json`、`docs/migrations/0.3.0_build_acceptance.json`。
- 0.3 F01-F64 状态 manifest：`tools/validation/release_feature_manifest_0_3.json`；本轮参考：`refs/adr_review_closure_reference_v1.json`。
- 导入和不兼容迁移：`docs/migrations/0.2.0.md`、`docs/migrations/0.2.0_import_map.json`。
- 测试映射：`docs/migrations/0.2.0_test_map.json`。
- 最终 pytest、mypy、冻结参考和 tracked 工作树门禁：`docs/migrations/0.2.0_release_acceptance.json`。
- 发布后 S0011/lambda 修正门禁：`docs/migrations/0.2.0_post_release_numeric_acceptance.json`。
- 发布后 RossRotor 时步修正门禁：`docs/migrations/0.2.0_post_release_rotor_acceptance.json`。
- 重构后代码审查修正门禁：`docs/migrations/0.2.0_post_refactor_review_acceptance.json`。
- 二轮代码审查修正门禁：`docs/migrations/0.2.0_second_review_acceptance.json`。
- 三轮代码审查修正门禁：`docs/migrations/0.2.0_third_review_acceptance.json`。
- 四轮代码审查修正门禁：`docs/migrations/0.2.0_fourth_review_acceptance.json`。
- 五轮代码审查修正门禁：`docs/migrations/0.2.0_fifth_review_acceptance.json`。
- 六轮代码审查修正门禁：`docs/migrations/0.2.0_sixth_review_acceptance.json`。
- 七轮代码审查修正门禁：`docs/migrations/0.2.0_seventh_review_acceptance.json`。
- 八轮 wheel 制品身份门禁：`docs/migrations/0.2.0_eighth_review_acceptance.json`。
- P2 架构收敛：`docs/migrations/0.2.0_p2_architecture_closure.md`；正式机器验收与构建证据：`docs/migrations/0.2.0_p2_architecture_acceptance.json`、`docs/migrations/0.2.0_p2_architecture_build_acceptance.json`。
- 控制状态和耦合时序参考：`refs/control_state_contract_reference_v1.json`、`refs/control_lifecycle_reference_v2.json`、`refs/rotor_bearing_coupling_time_reference_v3.json`、`refs/rotor_dof_coupling_reference_v4.json`。
- 三轮兼容性参考：`refs/third_review_compatibility_reference_v3.json`。
- 原生控制生命周期参考：`refs/native_control_lifecycle_reference_v9.json`。
- 四轮发布阻塞修正参考：`refs/fourth_review_release_reference_v4.json`。
- RossRotor 合法轨迹参考：`refs/ross_rotor_time_validation_reference_v2.json`。
- CSOrifice 单调求解参考：`refs/csorifice_monotonic_reference_v2.json`、`refs/csorifice_monotonic_consumers_reference_v2.json`。
- 热收敛补充参考：`refs/full_repo_refactor_addendum_v1/thermal_convergence.json`。
- 外部调用：`docs/migrations/0.2.0_external_consumer_audit.md`。
- SURROGATE_TRAIN 迁移后证据：`docs/migrations/0.2.0_surrogate_train_post_migration_audit.md`。
- PAPER_WORK 迁移后证据：`docs/migrations/0.2.0_paper_work_post_migration_audit.md`。
- 性能与峰值内存：`docs/migrations/0.3.0_performance.json`。
- 构建：`docs/migrations/0.2.0_build_acceptance.json`。
