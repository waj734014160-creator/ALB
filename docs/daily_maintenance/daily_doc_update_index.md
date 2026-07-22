# 文档角色与日常更新索引

## 文档角色

- 角色：集中式文档角色索引和日常审计索引。
- 目的：定义维护类文档的角色、允许更新内容、禁止更新内容、更新节奏和日常审计触发条件。
- 允许更新：文档角色条目、日常审计规则、证据来源指针和角色边界修正。
- 禁止更新：实时运行状态、详细 run 历史、源码修改、原始证据堆叠和清理动作。
- 更新节奏：维护文档角色、入口文档或审计规则变化时更新。
- 事实来源 / 相关文档：各被索引文档自己的 `文档角色` 区块。

本文是项目维护文档的集中角色索引。任何文档维护都必须先读本文，再读目标文档自己的 `文档角色` 区块，然后只在该角色允许的范围内编辑。

## 角色索引规则

- 维护类文档只能按本文和自身 `文档角色` 区块列出的角色编辑。
- 如果本文和目标文档的角色说明冲突，停止编辑并报告冲突。
- 如果请求内容属于另一种文档角色，应写入正确文档，或提出迁移建议。
- 未列入本文的文档不是例行维护目标；若要纳入维护，应先补充索引条目和本地 `文档角色` 区块。
- 本文不授权删除、移动、归档、启动任务、编辑源码或重写原始证据。

## 文档语言规则

- 面向人类用户阅读的规定类、概览类、维护类、审计类和操作手册类文档使用中文。
- 适用文件包括但不限于 `docs/current_state.md`、`docs/alb_package_overview.md`、`docs/daily_summary_log.md`、`docs/file_classification.md`、`docs/project_overview.md`、`docs/remote_workstation_connection.md`、`docs/run_index.md`，以及兄弟项目中的同类维护文档。
- 源码中的代码注释、docstring、实现说明、嵌入代码的 CLI help 和生成脚本注释必须继续使用英文，以兼容不同编码方式和开发工具链。
- 文档内的路径、命令、API 名称、参数名、错误文本和日志字段可以保留英文原文。
- 若旧维护文档仍有英文正文，后续维护时应优先把被触及的段落改为中文，避免继续扩展英文规则正文。

## 核心文档角色

| 文件 | 角色 | 简要说明 | 允许更新 | 禁止更新 | 节奏 / 触发条件 |
| --- | --- | --- | --- | --- | --- |
| `ALB_MAIN/docs/daily_maintenance/daily_doc_update_index.md` | 集中式文档角色索引和日常审计索引 | 维护文档角色和审计触发条件的事实来源。 | 文档角色条目、日常审计规则、证据来源指针、角色边界修正。 | 实时运行状态、详细 run 历史、源码修改、原始证据堆叠、清理动作。 | 维护文档角色、入口文档或审计规则变化时。 |
| `ALB_MAIN/docs/project_overview.md` | ALB_MAIN 项目入口概览 | 项目边界、主要目录、首读文档和稳定验证入口。 | 项目职责、目录职责、首读文档、稳定验证入口、跨项目边界说明。 | 实时运行状态、详细实验日志、模型指标流水、原始日志正文。 | 项目拆分、目录职责、首读文档或稳定工作流入口变化时。 |
| `ALB_MAIN/docs/current_state.md` | ALB_MAIN 项目当前状况记录 | 当前开发阶段、已确认基线、验证状态、风险和近期下一步。 | 当前分支和基线、项目级工作重点、已执行验证、当前风险、近期下一步和证据指针。 | 兄弟项目实时进度、完整历史流水、原始日志正文、稳定 API 手册和未经验证的结论。 | ALB_MAIN 开发阶段、工作重点、验证结论、风险或下一步实质变化时。 |
| `ALB_MAIN/docs/alb_package_overview.md` | 稳定包概览 | ALB 包模块图和公共接口组。 | 公共 API、模块归属和包边界说明。 | 实验运行状态、日常维护历史。 | 公共 API、模块归属或包边界变化时。 |
| `ALB_MAIN/docs/interface_architecture.md` | 稳定模块边界与接口协议说明 | ALB 依赖方向、通用模板、领域协议、单位制边界和兼容迁移策略。 | 模块分类、接口契约、兼容层、依赖规则、单位制规则和稳定验证入口。 | 实时运行状态、单次实验指标、训练进度和临时日志。 | 通用接口、模块边界、推荐导入路径或兼容策略变化时。 |
| `ALB_MAIN/docs/alb_albnn_quickstart.md` | 稳定用户操作手册 | 快速构建 ALB 模型、加载 ALBNN packaged model，并说明常见输入输出契约。 | 稳定 API 用法、最小示例、推荐导入路径、常见输入输出契约和排错提示。 | 活跃训练进度、单次 run 指标、远程任务 PID、原始日志正文和临时实验结论。 | ALB / ALBNN 构建 API、配置契约或推荐 quickstart 流程变化时。 |
| `ALB_MAIN/docs/migrations/0.2.0.md` | 稳定版本迁移手册 | 0.1 到 0.2 的 namespace、生命周期、DTO、持久化、配置和模型包迁移规则。 | 0.2 公共契约、导入映射、迁移工具、正式不兼容项和稳定验收入口。 | 实时任务状态、临时日志、未经验证的数值结论。 | 0.2 公共接口、迁移工具或正式验收结论变化时。 |
| `ALB_MAIN/docs/migrations/0.2.0_release_acceptance.json` | 版本化机器验收证据 | 记录最终 pytest、mypy、冻结参考和 tracked 工作树前后门禁。 | 只能由正式发布验收工具按真实执行结果重建。 | 手工填写通过结论、实时任务状态、未经执行的测试结果。 | 0.2 发布候选重新验收时。 |
| `ALB_MAIN/docs/migrations/0.2.0_post_release_numeric_acceptance.json` | 发布后数值修正机器验收证据 | 记录 S0011/lambda 修正后的 pytest、mypy、S0011 节点和 tracked 工作树门禁。 | 只能由正式验收工具按真实执行结果新建。 | 手工填写通过结论、覆盖原始发布验收、实时任务状态和未经执行的测试结果。 | 发布后数值修正重新验收时。 |
| `ALB_MAIN/docs/migrations/0.2.0_post_release_rotor_acceptance.json` | 发布后转子时步修正机器验收证据 | 记录 RossRotor 时步修正后的 pytest、mypy、转子节点、冻结参考和 tracked 工作树门禁。 | 只能由正式验收工具按真实执行结果新建。 | 手工填写通过结论、覆盖既有验收、实时任务状态和未经执行的测试结果。 | 发布后 RossRotor 时步修正重新验收时。 |
| `ALB_MAIN/docs/migrations/0.2.0_post_refactor_review_acceptance.json` | 重构后代码审查机器验收证据 | 记录 13 项代码审查修正后的全量 pytest、mypy、skip 和 tracked 工作树门禁。 | 只能由正式验收工具按真实执行结果新建。 | 手工填写通过结论、覆盖既有验收、实时任务状态和未经执行的测试结果。 | 重构后代码审查修正重新验收时。 |
| `ALB_MAIN/docs/migrations/0.2.0_second_review_acceptance.json` | 二轮代码审查机器验收证据 | 记录 4/6-DOF、真实 coupling、无控制器和显式控制生命周期修正后的全量 pytest、mypy、skip、精确参考和 tracked 工作树门禁。 | 只能由正式验收工具按真实执行结果新建。 | 手工填写通过结论、覆盖既有验收、实时任务状态和未经执行的测试结果。 | 二轮代码审查修正重新验收时。 |
| `ALB_MAIN/docs/migrations/0.2.0_third_review_acceptance.json` | 三轮代码审查机器验收证据 | 记录控制器兼容适配、coupler 失效出口、严格节点、无控制器配置回读和 ServoValve2 生命周期修正后的 pytest、mypy、skip、精确参考及 tracked 工作树门禁。 | 只能由正式验收工具按真实执行结果新建。 | 手工填写通过结论、覆盖既有验收、实时任务状态和未经执行的测试结果。 | 三轮代码审查修正重新验收时。 |
| `ALB_MAIN/docs/migrations/0.2.0_fourth_review_acceptance.json` | 四轮代码审查机器验收证据 | 记录 harmonic 真实控制器注入、永久/定时开关、控制器类型标签、coupler 拓扑失效及干净候选提交门禁。 | 只能在代码与测试映射提交后，由正式验收工具从干净 tracked 工作树生成。 | 手工填写通过结论、用脏工作树运行、覆盖既有验收或记录未经执行的结果。 | 四轮修正形成干净候选提交后。 |
| `ALB_MAIN/docs/migrations/0.2.0_fifth_review_acceptance.json` | 五轮代码审查机器验收证据 | 记录 harmonic 失败重初始化失效、严格嵌套控制器配置、独立默认配置、敏感 untracked/ignored 输入和 HEAD 固定门禁。 | 只能在代码与测试映射提交后，由正式验收工具从无敏感未提交输入的候选提交生成。 | 手工填写通过结论、用未提交源码/测试运行、覆盖既有验收或记录未经执行的结果。 | 五轮修正形成干净候选提交后。 |
| `ALB_MAIN/docs/migrations/0.2.0_external_consumer_audit.md` | 版本化只读迁移证据 | declared 外部调用者的路径、哈希、旧 import 和迁移目标汇总。 | 外部只读快照口径、文件清单、迁移门槛和证据指针。 | 修改外部文件、记录外部实时任务状态、复制原始日志。 | declared 快照或 0.2 迁移目标变化时。 |
| `ALB_MAIN/docs/file_classification.md` | ALB_MAIN 文件归属和清理策略 | 文件组、归属边界、归档/删除策略。 | 文件类别、代表路径、保留/归档规则、清理风险说明。 | 实时运行状态、模型进度、详细 run 历史。 | 主要文件组、归档类别或清理策略变化时。 |
| `ALB_MAIN/docs/run_index.md` | ALB_PROJECTS 全局 run 规则和路径索引 | 项目前缀 run 编号、run ID、current-status 归属和规范路径指针。 | run 编号规则、项目前缀映射、current-status 指针、规范路径和归档指针规则。 | 原始日志、详细进度尾部、模型指标、实时 tick、清理动作。 | run 编号、项目前缀、current-status 归属、路径族或归档指针规则变化时。 |
| `ALB_MAIN/docs/remote_workstation_connection.md` | 稳定远程操作手册 | 远程连接、Task Scheduler、SSH、runner 和 monitor 机制。 | 连接事实、稳定命令模式、wrapper 归属、凭据处理规则、可复用操作经验。 | 当前任务进度、PID、最新 loss、活跃 ETA、单次 run 指标。 | 远程机制、路径、wrapper 或凭据处理规则变化时。 |
| `ALB_MAIN/docs/daily_summary_log.md` | 项目级日常维护摘要 | 文档维护和稳定项目组织决策的简洁日记录。 | 日常维护摘要、清理确认、稳定文档/代码组织决策。 | 实时任务状态、原始日志堆叠、应归入 `albnn_training_log.md` 的详细 ALBNN 指标。 | 日常维护 pass 或显式项目摘要请求。 |
| `ALB_MAIN/docs/daily_maintenance/doc_maintenance_audit_YYYYMMDD.md` | 单次日常审计证据 | 一次计划文档维护的检查证据。 | 已检查文件、决策、无变更原因、陈旧候选、清理确认清单。 | 源码编辑、运行状态归属、长期项目手册内容。 | 每次计划审计创建或刷新。 |
| `ALB_MAIN/docs/formula/thermal_model.md` | 稳定公式和实现参考 | 热压力模型、离散化和实现映射的公式级说明。 | 控制方程、无量纲形式、FEM 离散、边界条件解释、代码到公式映射。 | 实时运行状态、单次 run 指标、任务 PID、原始日志。 | 热压力方程、离散方式或实现映射变化时。 |
| `ALB_MAIN/docs/formula/alb_harmonic_linearization.md` | 稳定公式、离散线性化和数值计算参考 | ALB 压力-温度-节流器解析谐波线性化、固定活动集规则与动态系数计算。 | 控制方程、解析一阶展开、固定活动集规则、频域矩阵、量纲换算、稳定数值结果和实现映射。 | 实时运行状态、训练进度、临时日志和移动空化边界描述函数。 | 控制方程、线性化定义、涡动频率比、数值工作点或正式系数变化时。 |
| `SURROGATE_TRAIN/docs/current_runtime_status.md` | 短期记忆 / 实时状态缓冲区 | 活跃训练、采样、队列和 monitor 工作的唯一实时状态。 | 活跃任务名、PID、最新 loss/进度/ETA、活跃日志路径、检查命令、下一步。 | 耐久经验、完整事故复盘、历史叙事、稳定手册。 | 状态检查、启动、同步、停止或 monitor 运行后。 |
| `SURROGATE_TRAIN/docs/albnn_training_log.md` | 长期记忆 / 时间顺序日志 | “睡前”维护后沉淀的每日 ALBNN 耐久历史。 | 每日最多一条日期记录：完成事件、关键指标、事故根因、可复现命令、最终结论。 | 实时 tick、最新 loss polling、活跃 PID、活跃 ETA、重复 monitor 快照。 | 默认日常维护时更新，或用户显式要求立即沉淀。 |
| `SURROGATE_TRAIN/docs/albnn_training_brief.md` | 稳定当前理解 | ALBNN 工作流首读稳定说明。 | 当前推荐工作流、规范数据/模型指针、输入输出契约、采样设置、耐久经验。 | 活跃 PID、最新 loss、ETA、日志尾部、瞬态 monitor 输出、日常审计细节。 | 工作流结构、规范路径、采样设置或耐久经验变化时。 |
| `SURROGATE_TRAIN/docs/albnn_training_info.md` | 阅读索引 | ALBNN 文档的简短入口。 | 阅读顺序、角色索引指针、事实来源指针。 | 运行状态、指标、历史、操作细节。 | 入口文档或阅读顺序变化时。 |
| `SURROGATE_TRAIN/docs/file_classification.md` | SURROGATE_TRAIN 文件归属和清理策略 | 训练项目文件组、证据类别和清理策略。 | 训练数据/模型/日志/脚本类别、归属边界、归档/删除规则。 | 实时进度、最新指标、详细时间顺序历史。 | 训练输出、脚本、模型、monitor 日志或清理策略变化时。 |

## 条件性工作区角色检查

| 文件 | 角色 | 检查触发条件 |
| --- | --- | --- |
| `ALB_MAIN/AGENTS.md` | 稳定代理策略 | 代理策略、源码修改边界、ALB_MAIN 当前状态入口、文件/路径命名约束、包概览或远程操作规则变化。 |
| `F:/BaiduSyncdisk/博士论文/PAPER_WORK/AGENTS.md` | PAPER_WORK 稳定代理策略 | 论文任务脚本、远程配置、图目录、数据目录、current-status 或证据保留规则变化。 |
| `SURROGATE_TRAIN/AGENTS.md` | 稳定训练项目代理策略 | 本地/远程启动边界、文档频率、训练源码归属或文档角色策略变化。 |
| `ARTIFACTS_ARCHIVE/docs/file_classification.md` | 归档文件归属策略 | 归档结构或保留策略变化。 |
| `DATA_POSTPROCESS/docs/file_classification.md` | 后处理文件归属策略 | 后处理/notebook 类别变化。 |
| `PARAM_SCAN/docs/file_classification.md` | 参数扫描文件归属策略 | 参数扫描任务或产物类别变化。 |
| `VALIDATION/docs/file_classification.md` | 验证文件归属策略 | 验证/测试产物类别变化。 |
| `SPLIT_INDEX.md` | split workspace 索引 | 项目成员或依赖约定变化。 |
| `SURROGATE_TRAIN/docs/run_index.md` | 指向全局 run 规则和 current-status 的指针 | 只有规范全局 run-index 位置或 current-status 路径变化时更新。 |

## 日常审计规则

- 日常审计必须读取核心角色表中存在的每个 required 文件。
- 如果列出的文件需要内容变更，只在该文件角色允许的范围内更新。
- 如果列出的文件无需内容变更，在当天的 `doc_maintenance_audit_YYYYMMDD.md` 记录 no-change 决策。
- 检查被索引叙事文档是否触发压缩：过时经验、过时日志或长度过大。
- 压缩经验时，将其总结为耐久原则、注意事项、可复用检查或日期结论；有用经验被保存后，可以删除维护文档中的陈旧叙事。
- 保留仍有诊断或复现价值的事故案例、根因分析、最终指标和参考工作流。

## 应检查的证据来源

以下是原始证据来源，不是维护叙事文档。日常审计可以把它们总结到正确角色的文档中。

| 证据来源 | 用途 |
| --- | --- |
| `SURROGATE_TRAIN/models/*/metadata.json` | 已完成模型配置和指标。 |
| `SURROGATE_TRAIN/models/*/validation_summary.json` | 独立验证指标。 |
| `SURROGATE_TRAIN/models/*/manual_termination.json` | 手动停止证据。 |
| `SURROGATE_TRAIN/outputs/local_train_logs/` | 本地训练 stdout/stderr 和启动 metadata。 |
| `SURROGATE_TRAIN/outputs/remote_monitor_logs/` | 远程采样 monitor 状态。 |
| `SURROGATE_TRAIN/outputs/queue_logs/` | 远程训练队列状态和同步日志尾部。 |
| `ALB_MAIN/docs/current_state.md` | ALB_MAIN 当前开发阶段、基线、验证状态、风险、下一步和证据指针。 |
| `ALB_MAIN/docs/migrations/0.2.0_release_acceptance.json` | 0.2 最终 pytest、mypy、冻结参考与 tracked 工作树门禁。 |
| `ALB_MAIN/docs/migrations/0.2.0_post_release_numeric_acceptance.json` | S0011/lambda 发布后修正的 pytest、mypy、节点结果与 tracked 工作树门禁。 |
| `ALB_MAIN/docs/migrations/0.2.0_post_release_rotor_acceptance.json` | RossRotor 时步发布后修正的 pytest、mypy、节点结果、冻结参考与 tracked 工作树门禁。 |
| `ALB_MAIN/docs/migrations/0.2.0_post_refactor_review_acceptance.json` | 重构后 13 项代码审查修正的 pytest、mypy、skip 与 tracked 工作树门禁。 |
| `ALB_MAIN/docs/migrations/0.2.0_second_review_acceptance.json` | 二轮代码审查修正的 pytest、mypy、skip、4/6-DOF coupling 与控制生命周期门禁。 |
| `ALB_MAIN/docs/migrations/0.2.0_third_review_acceptance.json` | 三轮代码审查修正的 pytest、mypy、skip、控制器兼容、coupler 失效出口、严格节点和配置回读门禁。 |
| `ALB_MAIN/docs/migrations/0.2.0_fourth_review_acceptance.json` | 四轮代码审查修正的干净候选提交、pytest、mypy、控制器真实生命周期、开关、配置标签和拓扑门禁。 |
| `ALB_MAIN/docs/migrations/0.2.0_fifth_review_acceptance.json` | 五轮代码审查修正的固定候选 HEAD、敏感未提交输入、harmonic 失效边界、严格配置和独立默认值门禁。 |
| `ALB_MAIN/refs/full_repo_refactor_addendum_v1/` | 从重构前隔离源码生成的 thermal direct/Newton/transient 不可覆盖补充参考。 |
| `ALB_MAIN/docs/run_index.md` | 人类可读的工作区全局 run 编号和路径策略。 |
| `F:/BaiduSyncdisk/博士论文/PAPER_WORK/AGENTS.md` | 论文任务文件管理、路径命名和证据保留规则。 |
| `F:/BaiduSyncdisk/博士论文/PAPER_WORK/docs/current_task_status.md` | 论文任务当前状态、最新输出路径、检查命令和下一步。 |
| `SURROGATE_TRAIN/docs/current_runtime_status.md` | 当前活跃 run 定位、进度和下一步状态。 |
| `ALB_MAIN/docs/daily_maintenance/latest_codex_daily_doc_maintenance_status.txt` | 指向最近一次计划维护的机器可读状态；由审计流程生成，不是维护叙事文档。 |
| `ALB_MAIN/docs/daily_maintenance/logs/` | 计划维护 stdout/stderr/final-message 证据。 |
