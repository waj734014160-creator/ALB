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

- 分支：`codex/alb-0.4.5`。
- 开发版本：`0.4.5`；包名 `re-alb`；导入名 `ALB`；最低 Python 3.10。
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
- 0.4.2 实现候选为 `ff491e4dc9668f49e41870c37898f3c4d3a4ddc3`；
  `v0.4.2` 固定指向该候选。正式机器报告位于其后的 evidence-only 提交，
  不反向修改候选。
- 0.4.3 从 0.4.2 evidence 提交 `50c7b4a` 创建。修复前有效路径参考为
  `refs/alb_0_4_3_guard_reference_v1.json/.npz`，NPZ SHA-256 为
  `3a8e017ca25466c7612f47ce2325968af368ff60aa433f92fda7c9b592a08ef8`；数值、
  API 收敛和公共文档站点开发边界已提交，但未形成固定发布候选或正式标签。
- 0.4.4 从 0.4.3 文档站点提交 `59682b8` 创建，目标是让配置 schema 版本可从
  包根直接发现；当前同样不是固定发布候选。
- 0.4.5 在测试树归并提交 `7308f54` 后创建；修改前伺服阀数值参考固定于
  `2ecb97e`，目标是把主动轴承公开阀配置收敛为二阶 Hz 参数和任意传递函数。

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
- 0.4.3 已拒绝非 dimensional 或输出字段/形状非法的自定义 rotor；静平衡在
  相对残差分母下溢或溢出时不再发布虚假收敛。JSON5 禁止重复键和标量静默
  转换，surrogate fixed spool 与 external spool 统一限制为 `[-1, 1]`。
- 0.4.4 将已有 `ALB.api.SCHEMA_VERSION` 显式提升为根入口
  `ALB.SCHEMA_VERSION`；包版本为 `0.4.4`，JSON5 schema 与 surrogate package
  格式仍为 `0.4.0`，不改变配置、数值或制品合同。
- 0.4.5 的主动轴承 JSON5 阀配置接受 `second_order`、`static` 和
  `transfer_function`。二阶阀直接使用 `natural_frequency_hz`、
  `damping_ratio` 和可选 `delay`；静态阀为无参数单位增益模型；任意高阶阀
  直接使用连续时间分子/分母多项式系数。
- SURROGATE_TRAIN 迁移已形成独立本地提交 `70934ae`。
- PAPER_WORK 在修改前保存 150 个声明活跃文件；清单摘要为
  `89663a1c3f093d7478efe3df3d96677a86556fd8f0edb4a3c9f6adbd7f1f98af`，
  快照位于 `docs/migrations/alb_0_4_pre_migration_20260724/`（PAPER_WORK 内）。
- mixed-film runtime 已删除逐属性、逐方法转发的 `_film_solver` 代理；量纲与
  无量纲实现直接使用原生 `FilmSystem` 数值方法，薄 mixin 只负责 DTO 生命周期、
  结果和失败诊断。结构型继承门禁已取消，量纲、带节流器量纲和无量纲路径继续
  由冻结行为参考保护。
- 静平衡已收口为唯一的公开 `EquilibriumSolver(bearing)` 模型；用户和内部模块
  均可直接构造，`bearing.analysis.find_equilibrium()` 只转发到该模型。旧
  `_InternalEquilibriumSolver` 和第二个数值 solver 已删除，主动润滑静态试探
  会复位静态伺服阀，能够连续评估不同位移。
- 主动润滑轴承显式网格模式已支持三角 P1/P2 和四边形 Q1/Q2；压力与温度共享
  网格、阶次和自由度。供油孔新增 `restrictors.flow_projection`：缺省
  `nearest_node` 在所有网格上保持统一最近节点行为，`element_shape` 在真实孔位
  使用 P1/P2/Q1/Q2 原生形函数，并以同一投影矩阵装配压力载荷、流量 Jacobian、
  热混合源和主动轴承阀芯线性化。两种模式都仍是集中点源。旧缺省路径和修改前
  显式形函数路径分别由独立 JSON/NPZ 冻结参考保护。

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
  精确旧基线，没有扩大。
- 第一轮数值/API 审查发现并关闭 2 项 P2、0 项 P1；修复后目标检查
  `40 passed`、V4P2 required nodeid `48 passed`。
- 第二轮事务/发布审查发现并关闭 2 项 P1、2 项 P2；事务目标检查
  `30 passed`，开发 wheel 为 `0.4.2` 且 150 个成员的 legacy/tool/token
  命中为零。两轮结束时开放 P1/P2 为零。
- 两轮后完整开发工作树复验：
  `341 passed, 13 skipped, 10 subtests passed`；V4P2 required nodeid
  `54 passed`；三项资源门禁通过；wheel 隔离的根 API、PAPER_WORK、
  SURROGATE_TRAIN、训练 CLI 和 remote CLI 共 6 项 smoke 均通过。
- 0.4.2 固定 SHA detached 正式验收状态为 `passed`；完整证据见
  `docs/migrations/0.4.2_release_acceptance.json`。Git blob 源连续构建的两个
  wheel 字节一致，`re_alb-0.4.2-py3-none-any.whl` 的 SHA-256 为
  `d796289af82df61c2fd2b021fbdd67bfdad40511304421da7c71f09f49093893`。
  正式验收重新通过完整 pytest、V4P2、分层 mypy、资源门禁、wheel 内容审计、
  隔离安装及 PAPER_WORK、SURROGATE_TRAIN 和 remote CLI smoke。
- 0.4.3 目标、邻近和精确参考测试为 `57 passed`；修复前后的静平衡、
  simulation 和区间内 fixed-spool surrogate 数组逐元素相等。
- 0.4.3 开发工作树在 mixed-film 组合重构后完整 pytest 为
  `371 passed, 13 skipped, 10 subtests passed`。重构前参考覆盖量纲、
  带节流器量纲和无量纲三条路径，力与压力场逐元素相等；既有 thermal wrapper
  参考 smoke 仍通过。分层 mypy 为 23 个 strict target 零错误，实施层旧基线
  从 363 条、85 组降至 356 条、84 组，没有新增诊断。
- 开发工作树已构建 150 个成员的 `re_alb-0.4.3-py3-none-any.whl`，以
  `--no-deps --target` 隔离安装后，根 API、版本和液膜最小计算 smoke 通过；
  该制品不是固定 SHA 正式发布 wheel。
- 静平衡收口及 API 收敛后，编辑前冻结的液膜与主动润滑结果逐元素相等；
  mixed-film 代理移除后的量纲、带节流器量纲和无量纲路径继续精确匹配参考。
  API/unit/regression 目标组为 `133 passed`；完整 pytest 为
  `390 passed, 13 skipped, 10 subtests passed`。分层 mypy 的 23 个 strict
  target 零错误，实现层旧基线保持 352 条、82 组并覆盖 146 个源码文件；
  26 个顶层公开符号及 3 个高级 namespace 的生成文档漂移检查通过。公共文档
  站点的 19 项目标测试与严格 MkDocs 构建通过，机器 JSON 证据不进入站点。
- 0.4.4 根 API、生成参考、文档和 optional-import 目标组为 `33 passed`；完整
  pytest 为 `414 passed, 13 skipped, 10 subtests passed`。27 个根符号的生成
  漂移检查、严格 MkDocs 构建和 `0.4.4/0.4.0` 双版本 import smoke 均通过。
- 0.4.5 伺服阀接口、配置、既有分析参考和文档示例目标组为
  `52 passed, 10 subtests passed`；完整 pytest 为
  `435 passed, 13 skipped, 10 subtests passed`。修改前参考覆盖四组阀模型、
  43 个数组；二阶、静态和传递函数接口的连续矩阵、离散矩阵和固定命令响应
  逐元素精确相等。23 个 strict mypy target 零错误，生成参考漂移检查与严格
  MkDocs 构建通过；PAPER_WORK 的共享主动轴承配置已迁移为 166 Hz 二阶阀。
- ALB 压力-热耦合网格无关性矩阵的 80 个四瓦冷启动工况已全部完成并保存；
  初次计算有 69 个达到压力与温度双收敛，11 个 Q2 工况为热迭代未收敛，
  求解异常为零。Q2 失稳已定位为高阶自由度重合坐标的浮点尾数进入
  `unique` 后产生伪极小网格间距，使四个瓦块的 SUPG 尺度不一致。显式结构网格
  现按实际坐标跨度、宏观单元数和阶次计算解析尺度；旧配置路径保持原算法。
  修补后原 11 个未收敛工况均以四瓦 5--7 次热迭代收敛，汇总已刷新为
  `80/80` 收敛、0 未收敛、0 求解异常；新场温度为 `19.932--22.289 °C`，
  压力非负且全部数组有限。修补前 11 例完整场已独立备份。
  三角对角线镜像的最大力差约为 `1.3e-14`，8/10 阶积分最大力差约为
  `1.7e-15`。供油 P1、P2 和 Q1 的压力耦合在把研究脚本的迭代上限从 60 提高
  到 240 后收敛；旧默认路径和物理方程未修改。旧路径逐元素精确回归及显式网格
  目标组为 `26 passed`，当前 unit/regression 为
  `393 passed, 10 subtests passed`。此前完整 pytest 为
  `458 passed, 13 skipped, 10 subtests passed`。
- 供油孔投影参数化的缺省最近节点参考继续使用
  `refs/mesh_independence_legacy_reference_v1.json/.npz`；修改前显式形函数行为冻结在
  `refs/supply_flow_element_shape_reference_v1.json/.npz`，后者 NPZ SHA-256 为
  `6f2e99de9096c5503a7459632702c0060abced3dd7c03fcf60abe3b03401bad3`。配置、P1/P2/Q1/Q2 权重、
  压力右端与 Jacobian、热焓守恒、量纲/无量纲热耦合及阀芯线性化目标组为
  `71 passed`；完整 pytest 为
  `492 passed, 13 skipped, 10 subtests passed`。配置参考和公共 API 参考生成检查均
  通过，缺省主动线性化与无量纲热 runtime 仍通过既有逐元素精确参考。

## 当前风险与边界

- 0.4.0 的分析 facade 曾以新数值方法替换旧算法且验收未覆盖双侧数值比较；
  `0.4.1` 恢复算法，`0.4.2` 进一步关闭输入域、local dt 和仿真失败原子性
  缺陷并完成正式 detached 验收，仍是当前推荐发布版本。0.4.3 已完成开发提交但
  未执行固定 SHA detached 发布验收；0.4.5 继续处于开发复验阶段。历史
  `v0.4.0`、`v0.4.1`、`v0.4.2` 标签、wheel 和验收证据保持不变。
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
- 请求范围内只重算了原 11 个未收敛 Q2 工况；另外 9 个原已收敛 Q2 工况仍是
  修补前结果。因此当前 80 例汇总可用于确认“失败点已恢复”，但完整 Q2 收敛序列
  和 GCI 在同一 SUPG 定义下重算前仍是临时结果。供油开启时四种离散的
  `200x100` 力也仍未全部达到 1% 的共同渐近要求，不能据此声明四种离散已有
  共同渐近解。解析对角尺度修补限定于当前均匀结构网格；局部加密、畸变网格或
  非零润滑油扩散仍需要流向/Jacobian 尺度和完整强残差验证。

## 当前下一步

1. 如需发布，形成干净实现候选后再新增对应 manifest/test map 和固定 SHA
   detached 验收；不移动 `v0.4.2`。
2. observer 与资源路径 containment 债务继续按独立 P3 维护范围处理；数值算法
   变化继续遵守 ADR-0007。
3. 如需把 Q2 收敛序列和 GCI 用于论文结论，先用同一解析 SUPG 尺度重算另外 9 个
   既有 Q2 工况，再重新检查单调性、GCI、温度/黏度变化及四离散细网格差异；不得
   把当前混合算法版本的 GCI 直接作为最终结论。

## 稳定入口

- 用户手册：`docs/alb_albnn_quickstart.md`
- 架构：`docs/interface_architecture.md`
- 发布计划：`docs/next_interface_development_plan.md`
- 迁移：`docs/migrations/0.4.0.md`
- 0.4.1 修复：`docs/migrations/0.4.1.md`
- 0.4.2 修复：`docs/migrations/0.4.2.md`
- 0.4.3 修复：`docs/migrations/0.4.3.md`
- 0.4.4 API 易用性：`docs/migrations/0.4.4.md`
- 0.4.5 伺服阀接口：`docs/migrations/0.4.5.md`
- 0.4.2 保留债务：`docs/migrations/0.4.2_deferred_debt.md`
- 0.4.2 两轮审查：`docs/migrations/0.4.2_review_log.md`
- 决策：`docs/adr/0006-alb-0-4-no-legacy-friendly-api.md`
- 数值算法决策：`docs/adr/0007-preserve-validated-numerical-algorithms.md`
- 伺服阀配置决策：`docs/adr/0008-servovalve-public-configuration.md`
- 功能门禁：`tools/validation/release_feature_manifest_0_4.json`
- 0.4.1 功能门禁：`tools/validation/release_feature_manifest_0_4_1.json`
- 0.4.2 功能门禁：`tools/validation/release_feature_manifest_0_4_2.json`
- detached 验收：`tools/validation/run_release_acceptance_0_4_2.py`
- 0.4.0 正式证据：`docs/migrations/0.4.0_release_acceptance.json`
- 0.4.1 正式证据：`docs/migrations/0.4.1_release_acceptance.json`
- 0.4.2 正式证据：`docs/migrations/0.4.2_release_acceptance.json`
