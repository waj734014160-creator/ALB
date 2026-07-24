# ALB_MAIN 当前状态

## 文档角色

- 角色：ALB_MAIN 项目当前状况记录。
- 目的：记录当前开发阶段、基线、已执行验证、风险和近期下一步。
- 允许更新：分支、基线、项目级工作、真实验证结果、风险和证据指针。
- 禁止更新：兄弟项目实时训练状态、完整历史、稳定 API 手册和未经验证结论。
- 更新节奏：开发阶段、验证结论、风险或下一步实质变化时。
- 事实来源：Git、`docs/interface_architecture.md`、0.4 manifest 和验收报告。

本文只记录 `ALB_MAIN`。SURROGATE_TRAIN 实时运行状态属于
`../SURROGATE_TRAIN/docs/current_runtime_status.md`；论文任务实时状态属于
`F:/BaiduSyncdisk/博士论文/PAPER_WORK/docs/current_task_status.md`。

## 当前快照

- 分支：`codex/alb-0.4.0`。
- 开发版本：`0.4.0`；包名 `re-alb`；导入名 `ALB`；最低 Python 3.10。
- 起点：`codex/full-repo-refactor` 的 `93dd63d`。
- 迁移前参考提交：`f23975d`，新增
  `refs/alb_0_4_pre_migration_reference_v1.json`，旧参考未覆盖。
- 当前状态：无 legacy、友好 facade、严格 JSON5、v0.4 surrogate package
  和不可变 simulation topology 的实现已收口；本文所在提交作为正式验收候选。
- 0.3 F01-F66 manifest 保持历史不修改；0.4 使用独立 V4-01 至 V4-24 manifest。

## 已完成的实现边界

- 根 namespace 已收敛为 `Bearing`/simulation facade、不可变配置与结果、稳定异常。
- active、liquid-film、Gas、MultiPad、harmonic 和 surrogate 使用正式 bearing runtime。
- `Bearing.calculate()`、`reset()`、分析服务和默认全历史 simulation 已接入。
- 0.4 JSON5 include、override/sweep 和资源根解析已实现。
- `Signal`、legacy adapter、旧工厂、宽松配置入口和旧 console entry point 已删除。
- ALBNN v0.4 package 使用 `weights_only=True` 与 NPZ scaler。
- SURROGATE_TRAIN 迁移已形成独立本地提交 `70934ae`。
- PAPER_WORK 在修改前保存 150 个声明活跃文件；清单摘要为
  `89663a1c3f093d7478efe3df3d96677a86556fd8f0edb4a3c9f6adbd7f1f98af`，
  快照位于 `docs/migrations/alb_0_4_pre_migration_20260724/`（PAPER_WORK 内）。

## 当前验证

- 主仓库完整 pytest：`260 passed, 13 skipped, 10 subtests passed`，无未处理 warning。
- V4 required nodeid：`23 passed`。
- 分层 mypy：21 个 strict target 零错误，覆盖 143 个源码文件；实现层基线为
  376 条诊断、86 个文件/错误码组，未新增漂移。
- SURROGATE_TRAIN：在当前 ALB 0.4 源码下 `7 passed`。
- 声明的 ALB_MAIN、SURROGATE_TRAIN 和 PAPER_WORK 活跃源码旧 API 扫描门禁已
  纳入 `tests/validation/test_release_0_4_gates.py`。
- 0.4 候选资源门禁使用 `run_resource_acceptance_0_4.py` 对 liquid、Gas 和
  rotor-bearing facade 执行显式运行时间与 tracemalloc 峰值内存上限；正式数值
  只进入 detached 报告，不写回候选。

以上是开发工作树证据，不等同于固定 SHA 的正式 wheel 验收。

## 当前风险与边界

- detached 双构建、wheel 内容审计、隔离安装和 external consumer smoke 尚未
  对本文所在固定 SHA 执行；本地工作树结果不能替代该证据。
- SURROGATE_TRAIN 当前没有 Git remote；迁移提交可本地固定，但不能在没有远端
  配置时推送。
- PAPER_WORK 没有 Git；其恢复能力依赖迁移前快照与哈希清单，历史证据目录不在
  legacy-zero 扫描范围。
- 0.4 不兼容旧配置和旧模型；迁移工具只在仓库外使用，不进入 wheel。
- implementation mypy 基线不是全部 strict 零错误；只能逐步减少，不能扩大忽略。

## 当前下一步

1. 确认实现候选 tracked-clean，并记录固定 SHA。
2. 从该 SHA 的 detached worktree 连续构建 wheel、隔离安装并执行正式验收。
3. 验收通过后推送 `codex/alb-0.4.0`；机器报告不反向写入候选提交。

## 稳定入口

- 用户手册：`docs/alb_albnn_quickstart.md`
- 架构：`docs/interface_architecture.md`
- 发布计划：`docs/next_interface_development_plan.md`
- 迁移：`docs/migrations/0.4.0.md`
- 决策：`docs/adr/0006-alb-0-4-no-legacy-friendly-api.md`
- 功能门禁：`tools/validation/release_feature_manifest_0_4.json`
- detached 验收：`tools/validation/run_release_acceptance_0_4.py`
