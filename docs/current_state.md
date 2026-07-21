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
- 当前阶段：0.2.0 全仓库重构、迁移资料、性能门禁和 wheel 隔离安装均已完成；发布后已完成 S0011/lambda 独立数值修正，下一阶段仍是外部消费者迁移。

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

## 当前验收结论

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 精确行为回归 | 11 个领域、121 个主参考数组使用精确相等检查通过；thermal direct/Newton/transient 的 40 个补充数组、残差历史和提交状态也精确通过 | `refs/full_repo_refactor_v1/`、`refs/full_repo_refactor_addendum_v1/`、`tests/regression/` |
| 242 节点迁移 | 242 个基线节点全部映射；另有 19 个原非收集文件明确分类 | `docs/migrations/0.2.0_test_map.json` |
| 0.2.0 标签验收 | 293 passed、33 skipped、12 warnings、7 subtests passed；测试前后 tracked 状态增量为 0 | `docs/migrations/0.2.0_release_acceptance.json` |
| 发布后数值修正验收 | 297 passed、30 skipped、12 warnings、7 subtests passed；4 个 S0011 节点全部 passed，mypy 19 个文件无问题，tracked 状态增量为 0 | `docs/migrations/0.2.0_post_release_numeric_acceptance.json` |
| 分层与循环依赖 | 116 个模块、217 条内部边无 namespace/module-level 循环；数值层不依赖 infrastructure；47 个旧模块均不存在 | `tests/validation/test_import_boundaries.py` |
| 导入迁移 | 65 个旧模块、479 个定义、9 个公共 alias 和 68 个旧根导出均有机器映射；554 个非删除目标可解析 | `docs/migrations/0.2.0_import_map.json` |
| 严格类型 | mypy 2.3.0 检查 `ALB/contracts` 与 `ALB/core`，19 个源文件无问题 | `docs/migrations/0.2.0_release_acceptance.json` |
| Optional dependency | 各领域 namespace 的缺依赖提示与 extra 安装信息测试通过 | `tests/unit/contracts/`、`tests/validation/test_optional_dependency_errors.py` |
| 同机性能 | film 0.8943、thermal 0.9114、ALB 0.9098、ALBNN 0.9028、coupling 0.9550，均低于 1.15 阈值 | `docs/migrations/0.2.0_performance.json` |
| Wheel | `re_alb-0.2.0-py3-none-any.whl` 构建、隔离安装、8 组 extras 独立 import smoke、namespace smoke 和两个 CLI `--help` 通过 | `docs/migrations/0.2.0_build_acceptance.json` |

wheel 当前 SHA-256 为 `9c031a19c67d20b917d687a9cad61c24634adfa3e096a0780fcf197ebd8dea76`。它包含 122 个成员，不包含已删除的旧平铺模块。

## 外部消费者状态

本轮只读审计已覆盖：

- `SURROGATE_TRAIN` 23 个文件：19 个 direct、4 个 context。
- `PAPER_WORK` 27 个文件：25 个 direct、2 个 transitive。

每个文件的 SHA-256、旧 import、0.2 目标 namespace 和语义迁移门槛位于 `docs/migrations/0.2.0_external_consumer_audit.json`。所有条目均标记 `external_file_modified=false`；本轮没有修改外部项目。

## 已知风险与边界

- 原发布验收的 33 个 skip 分为：`SURROGATE_TRAIN` 17、外部 `VALIDATION` 13、S0011 旧路径 3。S0011 三项已修复；当前 30 个 skip 只剩 `SURROGATE_TRAIN` 17 和 `VALIDATION` 13。
- `SURROGATE_TRAIN` 的 17 项中，16 项确需外部旧 namespace 迁移；M0031 的 1 项是本仓库测试把 sibling 项目错误拼成 `ALB_MAIN/SURROGATE_TRAIN`，实际 5 个 artifact 存在，尚待独立修正。
- 两个 liquid-film 测试曾用 `6.0 * miu * omega * l**2 / (ps*c**2)`，把 Reynolds bearing number 放大 4 倍；现统一通过 `FilmNondimScales` 使用生产定义 `1.5`。`ALB.physics.gas` 中的 `6.0` 属于另一套气体轴承定义，不在此次修正范围。
- S0011 v2 已嵌入三条输入、当前 resolved source config 和 fixed-point config，不再读取外部 84.3 MB CSV。历史 `alb12.json5` 哈希一致，但原 `share.json5` 已缺失且当前 hash 不同；因此 v1 到 v2 的 dimensional/S0011 漂移不能归因于 lambda 修正，也不能宣称完成历史配置精确复现。
- `RossRotor._check_time()` 仍保留重构前先追加时间、再用末项检查步长的逻辑，因而不能识别错误 `dt`。按本轮约束只记录，不修正；修正时必须另建提交和 v2 参考。
- 旧 `ALB.nn` pickle 不属于 0.2 运行时兼容面。必须先使用显式迁移工具生成新的 model package，并只对可信 pickle 启用加载。
- 删除当前工作树中的私人邮件默认值不会抹除 Git 历史；相关 SMTP 凭据仍需在外部轮换。
- thermal 主参考的 direct/Newton/transient 收敛证据已由 addendum 补齐；但现有性能与热参考仍主要是小算例，且 orifice cooling、非零导热、生产尺寸 M0035 和大型 ROSS 性能不在当前精确门禁覆盖内。
- 性能门禁使用固定的小型 film、thermal、ALB、ALBNN 和合成 coupling case，能约束本次重构，不代表生产尺寸 M0035 或大型 ROSS 模型的绝对性能。
- 两张会被重生成的 thermal 热图已解除 Git 跟踪但保留本地文件；`.codex/` 与 `test/control/LQG/` 也保留原地。四类路径均由根 `.gitignore` 精确忽略。

## 发布后下一步

1. 在 `SURROGATE_TRAIN` 独立分支按 23 文件清单迁移 import、model package 和 remote wrapper，并执行训练/推理 smoke。
2. 在 `PAPER_WORK` 独立分支按 27 文件清单迁移脚本，保持论文任务配置和结果资产原地。
3. `RossRotor._check_time()` 如需修正，继续遵循“先生成新参考、再独立提交”；不得改写任何既有 v1 或本次 thermal v2。
4. 如需发布 wheel 到外部位置，先重新执行 `tools/validation/validate_wheel_0_2.py` 并核对 SHA-256。

## 证据入口

- 架构：`docs/interface_architecture.md`。
- 导入和不兼容迁移：`docs/migrations/0.2.0.md`、`docs/migrations/0.2.0_import_map.json`。
- 测试映射：`docs/migrations/0.2.0_test_map.json`。
- 最终 pytest、mypy、冻结参考和 tracked 工作树门禁：`docs/migrations/0.2.0_release_acceptance.json`。
- 发布后 S0011/lambda 修正门禁：`docs/migrations/0.2.0_post_release_numeric_acceptance.json`。
- 热收敛补充参考：`refs/full_repo_refactor_addendum_v1/thermal_convergence.json`。
- 外部调用：`docs/migrations/0.2.0_external_consumer_audit.md`。
- 性能：`docs/migrations/0.2.0_performance.json`。
- 构建：`docs/migrations/0.2.0_build_acceptance.json`。
