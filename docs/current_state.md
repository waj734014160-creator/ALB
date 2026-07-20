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
- 当前阶段：0.2.0 全仓库重构、迁移资料、性能门禁和 wheel 隔离安装均已完成，进入发布后外部消费者迁移阶段。

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
| 全量 pytest | 293 passed、33 skipped、12 warnings、7 subtests passed；测试前后 tracked 状态增量为 0 | `docs/migrations/0.2.0_release_acceptance.json` |
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

- 33 个 skip 主要对应尚未在所属仓库完成的外部消费者迁移和已有 optional artifact 条件；它们不是静默删除的基线测试。
- 旧 S0011 Newton 精确节点因外部配置 `F:/BaiduSyncdisk/博士论文/task/PAPER/config/alb12.json5` 不存在而明确 skip；其中保留的 `6.0` lambda 构造属于历史测试基线问题，不是本轮 thermal solver 回归。自包含 Newton 精确能力由 thermal addendum 覆盖。
- `RossRotor._check_time()` 仍保留重构前先追加时间、再用末项检查步长的逻辑，因而不能识别错误 `dt`。按本轮约束只记录，不修正；修正时必须另建提交和 v2 参考。
- 旧 `ALB.nn` pickle 不属于 0.2 运行时兼容面。必须先使用显式迁移工具生成新的 model package，并只对可信 pickle 启用加载。
- 删除当前工作树中的私人邮件默认值不会抹除 Git 历史；相关 SMTP 凭据仍需在外部轮换。
- 重构中发现的既有数值或物理问题不在本版本顺带修复；修复必须使用独立提交和 v2 参考。
- 性能门禁使用固定的小型 film、thermal、ALB、ALBNN 和合成 coupling case，能约束本次重构，不代表生产尺寸 M0035 或大型 ROSS 模型的绝对性能。
- 当前用户工作树中的两张热图、`.codex/`、LQG 脚本及其输出未暂存、未移动，也不属于 0.2.0 发布变更。

## 发布后下一步

1. 在 `SURROGATE_TRAIN` 独立分支按 23 文件清单迁移 import、model package 和 remote wrapper，并执行训练/推理 smoke。
2. 在 `PAPER_WORK` 独立分支按 27 文件清单迁移脚本，保持论文任务配置和结果资产原地。
3. 任何数值修正先生成 v2 参考，再独立提交；不得改写 `refs/full_repo_refactor_v1/`。
4. 如需发布 wheel 到外部位置，先重新执行 `tools/validation/validate_wheel_0_2.py` 并核对 SHA-256。

## 证据入口

- 架构：`docs/interface_architecture.md`。
- 导入和不兼容迁移：`docs/migrations/0.2.0.md`、`docs/migrations/0.2.0_import_map.json`。
- 测试映射：`docs/migrations/0.2.0_test_map.json`。
- 最终 pytest、mypy、冻结参考和 tracked 工作树门禁：`docs/migrations/0.2.0_release_acceptance.json`。
- 热收敛补充参考：`refs/full_repo_refactor_addendum_v1/thermal_convergence.json`。
- 外部调用：`docs/migrations/0.2.0_external_consumer_audit.md`。
- 性能：`docs/migrations/0.2.0_performance.json`。
- 构建：`docs/migrations/0.2.0_build_acceptance.json`。
