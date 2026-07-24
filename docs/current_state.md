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

- 分支：`codex/alb-0.4.2`。
- 开发版本：`0.4.2`；包名 `re-alb`；导入名 `ALB`；最低 Python 3.10。
  JSON5 schema 和 surrogate package 格式继续使用 `0.4.0`。
- 起点：`codex/full-repo-refactor` 的 `93dd63d`。
- 迁移前参考提交：`f23975d`，新增
  `refs/alb_0_4_pre_migration_reference_v1.json`，旧参考未覆盖。
- 0.4.0 实现候选：`b0761f991452a3c3060e9e51d0cbad6f98a7b296`；无 legacy、友好
  facade、严格 JSON5、v0.4 surrogate package 和不可变 simulation topology
  已收口并通过正式验收。
- 历史发布标签：`v0.4.0` 固定指向上述实现候选；其后的 0.4.0 分支提交只保存机器验收证据，
  不改变已验收实现或标签目标。
- 0.3 F01-F66 manifest 保持历史不修改；0.4 使用独立 V4-01 至 V4-24 manifest。
- 0.4.1 使用独立 V4P manifest。迁移前数值合同固定于 `93dd63d`，参考提交为
  `c93624c`，NPZ SHA-256 为
  `78440877f4816b1286979659c3615f7ff22001299d54932613db1e4c516e02d7`。
- 0.4.1 实现候选为 `a26435e2eb7652d6d64af2194865dd3cf05db61d`；
  `v0.4.1` 固定指向该候选。正式机器报告保存在其后的 evidence-only 提交中，
  不反向修改候选。
- 0.4.2 从 0.4.1 evidence 分支创建；新增成功路径合同固定于上述 0.4.1
  实现候选，参考提交为 `e4fb9c6`，NPZ SHA-256 为
  `72eb8e591b27b40be0098ebc55d8c373c00159902b7a362e04b33fe86355e52b`。

## 已完成的实现边界

- 根 namespace 已收敛为 `Bearing`/simulation facade、不可变配置与结果、稳定异常。
- active、liquid-film、Gas、MultiPad、harmonic 和 surrogate 使用正式 bearing runtime。
- `Bearing.calculate()`、`reset()`、分析服务和默认全历史 simulation 已接入。
- 0.4 JSON5 include、override/sweep 和资源根解析已实现。
- `Signal`、legacy adapter、旧工厂、宽松配置入口和旧 console entry point 已删除。
- ALBNN v0.4 package 使用 `weights_only=True` 与 NPZ scaler。
- 0.4.1 已恢复专用静平衡迭代、旋转椭圆正反涡动复数识别以及液膜/主动润滑
  方程导数线性化，并以固定参考执行精确数组回归。
- `SimulationConfig` 已在运行前统一转子、mount、嵌套 `MultiPad` 和物化组件的
  `time_step`；可倾瓦实现已从活跃 package 源码删除。
- 0.4.2 已在求解前校验 FFT 网格、目标 bin 与正反涡动矩阵，并拒绝既有相对
  残差静平衡算法不支持的精确零载荷；合法输入仍精确匹配 0.4.1 合同。
- `RotorProtocol.dt` 已成为显式能力。simulation 按 unit adapter 的真实转换
  得到 bearing-local 步长；独立构建和 simulation 共用递归 `MultiPad` 与物化
  组件时间树校验。
- simulation 已在 post-commit 失败后取回真实提交、封存 recorder 并分别报告
  物理、历史和 post-commit 完整性；disk-stream 使用临时文件、flush/fsync
  和原子替换。
- SURROGATE_TRAIN 迁移已形成独立本地提交 `70934ae`。
- PAPER_WORK 在修改前保存 150 个声明活跃文件；清单摘要为
  `89663a1c3f093d7478efe3df3d96677a86556fd8f0edb4a3c9f6adbd7f1f98af`，
  快照位于 `docs/migrations/alb_0_4_pre_migration_20260724/`（PAPER_WORK 内）。

## 当前验证

- 0.4.0 固定 SHA detached 验收状态：`passed`；正式证据见
  `docs/migrations/0.4.0_release_acceptance.json`。
- 0.4.1 开发工作树完整 pytest：`287 passed, 13 skipped, 10 subtests passed`，
  无未处理 warning。
- 0.4.1 分层 mypy：22 个 strict target 零错误，覆盖 144 个源码文件；删除倾瓦
  死代码后实现层基线降为 363 条诊断、85 个文件/错误码组。
- 0.4.1 目标数值合同与 V4P required nodeid 为 `20 passed`；三项资源门禁
  已通过开发工作树检查。
- 0.4.1 固定 SHA detached 正式验收状态为 `passed`；完整证据见
  `docs/migrations/0.4.1_release_acceptance.json`。两个连续构建的 wheel
  字节一致，`re_alb-0.4.1-py3-none-any.whl` 的 SHA-256 为
  `1d908096727705f1f4442499291b1c0501ac9a09be17254e5acbbeb41abff38e`。
- 0.4.1 detached 验收重新通过完整 pytest、V4P required nodeid、分层 mypy、
  资源门禁、wheel 内容审计、隔离安装，以及 PAPER_WORK、SURROGATE_TRAIN 和
  remote CLI smoke。
- 两次独立 Git blob 源构建得到字节一致的
  `re_alb-0.4.0-py3-none-any.whl`；SHA256 为
  `18bffa0977d48d48438f57244a4f8bd98f2f77015b369d598dbf0605401f4495`。
- wheel 内容审计、隔离安装、根 API、PAPER_WORK、SURROGATE_TRAIN 和 remote
  CLI smoke 均通过；wheel 不含 migration tools、旧接口命中或禁止成员。
- liquid、Gas 和 rotor-bearing facade 的资源门禁均低于 10 秒和 512 MiB 上限。
- SURROGATE_TRAIN：在当前 ALB 0.4 源码下 `7 passed`。
- 声明的 ALB_MAIN、SURROGATE_TRAIN 和 PAPER_WORK 活跃源码旧 API 扫描门禁已
  纳入 `tests/validation/test_release_0_4_gates.py`。
- 0.4.2 初始修复工作树完整 pytest：
  `333 passed, 13 skipped, 10 subtests passed`，无未处理 warning。
- 0.4.2 目标修复、失败注入与成功路径合同：`41 passed`。
- 0.4.2 分层 mypy：23 个 strict target 零错误；实现层仍为 363 条、85 组
  精确旧基线，没有扩大。正式两轮审查和 detached 发布验收尚未完成。

## 当前风险与边界

- 0.4.0 的分析 facade 曾以新数值方法替换旧算法且验收未覆盖双侧数值比较；
  `0.4.1` 已完成数值合同和正式 detached 验收，现作为推荐发布版本取代
  `0.4.0`。历史 `v0.4.0` 标签、wheel 和验收证据保持不变。
- 0.4.1 谐波线性化只声明量纲液膜和三节点 CSOrifice 主动润滑拓扑；无量纲、
  Gas、MultiPad、surrogate、热包装及其他节流拓扑会明确失败。
- 0.4.1 不支持可倾瓦轴承；未来重新加入必须作为新功能设计和验证。
- 0.4.2 明确保留 363 条实现层 mypy 旧基线和三个无明确契约的 TODO；其影响
  与关闭条件见 `docs/migrations/0.4.2_deferred_debt.md`，本轮不借机改动核心
  数值算法。
- SURROGATE_TRAIN 当前没有 Git remote；迁移提交可本地固定，但不能在没有远端
  配置时推送。
- PAPER_WORK 没有 Git；其恢复能力依赖迁移前快照与哈希清单，历史证据目录不在
  legacy-zero 扫描范围。
- 0.4 不兼容旧配置和旧模型；迁移工具只在仓库外使用，不进入 wheel。
- implementation mypy 基线不是全部 strict 零错误；只能逐步减少，不能扩大忽略。

## 当前下一步

1. 对 0.4.2 相对 0.4.1 的完整 diff 完成数值/API 审查和事务/发布审查，关闭
   全部 P1/P2，并记录真实发现与复验。
2. 形成 tracked-clean 实现候选，从固定 SHA detached worktree 完成双 wheel、
   完整 pytest、required nodeid、mypy、资源和外部消费者正式验收。
3. 正式报告写入候选后的 evidence-only 提交；验收通过后再创建和推送
   `v0.4.2`，不得移动历史标签。

## 稳定入口

- 用户手册：`docs/alb_albnn_quickstart.md`
- 架构：`docs/interface_architecture.md`
- 发布计划：`docs/next_interface_development_plan.md`
- 迁移：`docs/migrations/0.4.0.md`
- 0.4.1 修复：`docs/migrations/0.4.1.md`
- 0.4.2 修复：`docs/migrations/0.4.2.md`
- 0.4.2 保留债务：`docs/migrations/0.4.2_deferred_debt.md`
- 决策：`docs/adr/0006-alb-0-4-no-legacy-friendly-api.md`
- 数值算法决策：`docs/adr/0007-preserve-validated-numerical-algorithms.md`
- 功能门禁：`tools/validation/release_feature_manifest_0_4.json`
- 0.4.1 功能门禁：`tools/validation/release_feature_manifest_0_4_1.json`
- 0.4.2 功能门禁：`tools/validation/release_feature_manifest_0_4_2.json`
- detached 验收：`tools/validation/run_release_acceptance_0_4_2.py`
- 0.4.0 正式证据：`docs/migrations/0.4.0_release_acceptance.json`
- 0.4.1 正式证据：`docs/migrations/0.4.1_release_acceptance.json`
