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
  `docs/alb_package_overview.md`、
  `docs/run_index.md`、
  Git 提交和本文列出的验收报告。

本文只记录 `ALB_MAIN`。ALBNN 活跃训练状态属于 `../SURROGATE_TRAIN/docs/current_runtime_status.md`；论文计算状态属于 `F:/BaiduSyncdisk/博士论文/PAPER_WORK/docs/current_task_status.md`。

## 当前快照

- 分支：`codex/full-repo-refactor`。
- 包版本：`0.2.0`；最低 Python：`3.10`。
- 发布标签：`v0.2.0`。
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
- 当前阶段：第六轮新发现的 2 个 P1 已修复并完成干净候选验收：harmonic 运行中半推进异常立即使 runtime 失效；发布验收从候选 SHA 的 detached worktree 执行，清理 Python/pytest 注入环境并使用本次新建的固定版本 mypy 目录。候选 `66fe326` 得到 421 passed、13 skipped、0 warnings、27 subtests passed；测试前后 HEAD 一致，tracked 状态及敏感 untracked/ignored 输入均为空。因此本轮两个发布阻塞项已关闭，可解除针对这两项的 `Request changes`。

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
| PAPER_WORK 消费者迁移 | 27 个 declared 文件和 2 个动态 helper 均有可恢复快照；25 个 direct 与 2 个 helper 已改写，24 个 guarded import smoke 通过，旧平铺 import 为 0；M0031/M0035 package 校验和可信加载通过 | `docs/migrations/0.2.0_paper_work_post_migration_audit.json` |
| 分层与循环依赖 | 116 个模块、217 条内部边无 namespace/module-level 循环；数值层不依赖 infrastructure；47 个旧模块均不存在 | `tests/validation/test_import_boundaries.py` |
| 导入迁移 | 65 个旧模块、479 个定义、9 个公共 alias 和 68 个旧根导出均有机器映射；554 个非删除目标可解析 | `docs/migrations/0.2.0_import_map.json` |
| 严格类型 | mypy 2.3.0 检查 `ALB/contracts` 与 `ALB/core`，19 个源文件无问题 | `docs/migrations/0.2.0_release_acceptance.json` |
| Optional dependency | 各领域 namespace 的缺依赖提示与 extra 安装信息测试通过 | `tests/unit/contracts/`、`tests/validation/test_optional_dependency_errors.py` |
| 同机性能 | film 0.8943、thermal 0.9114、ALB 0.9098、ALBNN 0.9028、coupling 0.9550，均低于 1.15 阈值 | `docs/migrations/0.2.0_performance.json` |
| Wheel | `re_alb-0.2.0-py3-none-any.whl` 构建、隔离安装、8 组 extras 独立 import smoke、namespace smoke 和两个 CLI `--help` 通过 | `docs/migrations/0.2.0_build_acceptance.json` |

wheel 当前 SHA-256 为 `9c031a19c67d20b917d687a9cad61c24634adfa3e096a0780fcf197ebd8dea76`。它包含 122 个成员，不包含已删除的旧平铺模块。

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
- 四轮审查涉及的具体缺陷已经关闭，但三个结构性欠账仍在：`thermal/solver.py` 等 6 个主要模块仍为约 1269-3259 行的单体；ServoValve2 仍以兼容方式保留 `input()` 内计算，LQG 和 RepetitiveController 也尚未原生迁入严格状态机；mypy 严格门禁仍只覆盖 contracts/core 的 19 个文件。这些属于分阶段重构工作，不能用本轮局部修复宣称完成。

## 发布后下一步

1. 按依赖顺序逐个拆分 6 个千行级模块，每个领域先建精确参考，禁止再次进行无参考的全仓机械搬迁。
2. 盘点仍在 `output()` 中计算、推进或写历史的公开旧类，逐一迁到严格 block/adapter，避免双生命周期继续扩散。
3. 在 contracts/core 已通过的基础上，按 control、dynamics、systems 顺序扩大 mypy 严格覆盖。
4. 为 `task/task_alb_data2.py` 的混合单位调用先建立参考与显式尺度适配器；不要直接套用 nondimensional strict port。
5. 将新 base/expert/residual 训练输出自动封装为 0.2 model package；residual 的主模型嵌套关系需先定义 manifest 语义。
6. 为 PAPER_WORK 四个顶层执行脚本增加主入口隔离，并为两个 M0035 内部代理建立 DTO block 参考后再迁移。
7. 为 `task/task_thermal_forces.py` 接入真实 `pooln` 并单独验证并行输出次序和确定性。
8. 如需重新发布 wheel，先执行完整 wheel 隔离安装门禁并核对新 SHA-256。

## 证据入口

- 架构：`docs/interface_architecture.md`。
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
- 控制状态和耦合时序参考：`refs/control_state_contract_reference_v1.json`、`refs/control_lifecycle_reference_v2.json`、`refs/rotor_bearing_coupling_time_reference_v3.json`、`refs/rotor_dof_coupling_reference_v4.json`。
- 三轮兼容性参考：`refs/third_review_compatibility_reference_v3.json`。
- 四轮发布阻塞修正参考：`refs/fourth_review_release_reference_v4.json`。
- RossRotor 合法轨迹参考：`refs/ross_rotor_time_validation_reference_v2.json`。
- CSOrifice 单调求解参考：`refs/csorifice_monotonic_reference_v2.json`、`refs/csorifice_monotonic_consumers_reference_v2.json`。
- 热收敛补充参考：`refs/full_repo_refactor_addendum_v1/thermal_convergence.json`。
- 外部调用：`docs/migrations/0.2.0_external_consumer_audit.md`。
- SURROGATE_TRAIN 迁移后证据：`docs/migrations/0.2.0_surrogate_train_post_migration_audit.md`。
- PAPER_WORK 迁移后证据：`docs/migrations/0.2.0_paper_work_post_migration_audit.md`。
- 性能：`docs/migrations/0.2.0_performance.json`。
- 构建：`docs/migrations/0.2.0_build_acceptance.json`。
