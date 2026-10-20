# 文档路径索引

以下列出工作区文档、任务记录与证据的路径，便于按实际需要查找资料。

## 常用文档

| 路径 | 内容说明 |
| --- | --- |
| `ALB_MAIN/docs/daily_maintenance/daily_doc_update_index.md` | 文档路径和内容说明。 |
| `ALB_MAIN/docs/project_overview.md` | 项目边界、主要目录、阅读入口和稳定验证入口。 |
| `ALB_MAIN/docs/current_state.md` | 当前开发阶段、已确认基线、验证状态、风险和近期下一步。 |
| `ALB_MAIN/docs/alb_package_overview.md` | ALB 包模块图和公共接口组。 |
| `ALB_MAIN/docs/api/README.md` | API 文档范围、阅读入口、生成方式和一致性门禁。 |
| `ALB_MAIN/docs/site/**/*.md` | 面向用户的安装、快速开始、任务指南、API 边界和文档贡献页面。 |
| `ALB_MAIN/docs/interface_architecture.md` | ALB 依赖方向、通用模板、领域协议、单位制边界和兼容迁移策略。 |
| `ALB_MAIN/docs/adr/README.md` 与 `docs/adr/NNNN-*.md` | 管理跨模块、公共接口和验收语义的 Accepted/Proposed 决策及修订关系。 |
| `ALB_MAIN/docs/alb_albnn_quickstart.md` | 快速构建 ALB 模型、加载 ALBNN packaged model，并说明常见输入输出契约。 |
| `ALB_MAIN/docs/file_classification.md` | 文件组、归属边界、归档/删除策略。 |
| `ALB_MAIN/docs/daily_maintenance/project_cleanup_YYYYMMDD.md` | 记录已授权处置、保留项和恢复入口。 |
| `ALB_MAIN/docs/daily_maintenance/project_cleanup_YYYYMMDD_manifest.json` | 保存真实动作、资产摘要和验证结果。 |
| `ALB_MAIN/docs/run_index.md` | 项目前缀 run 编号、run ID、current-status 归属和规范路径指针。 |
| `ALB_MAIN/docs/remote_workstation_connection.md` | 远程连接、Task Scheduler、SSH、runner 和 monitor 机制。 |
| `ALB_MAIN/docs/formula/thermal_model.md` | 压力-流量-温度-黏度耦合模型、离散化和实现映射的完整公式说明。 |
| `ALB_MAIN/docs/formula/alb_harmonic_linearization.md` | ALB 压力-温度-节流器解析谐波线性化、固定活动集规则、包内实现和历史热源孔位修正。 |
| `ALB_MAIN/docs/site/guides/analysis.md` | 分析接口及热耦合谐波工具的 Python/命令行用法、系数单位与适用范围。 |
| `ALB_MAIN/docs/formula/pressure_temperature_consistency_review.md` | 活动调用链、单位、投影装配与回归边界。 |
| `ALB_MAIN/docs/formula/symbol_conventions.md` | 区分物理符号、内部字段及公开配置名称。 |
| `SURROGATE_TRAIN/docs/current_runtime_status.md` | 活跃训练、采样、队列和 monitor 运行记录。 |
| `SURROGATE_TRAIN/docs/albnn_training_log.md` | “睡前”维护后沉淀的每日 ALBNN 耐久历史。 |
| `SURROGATE_TRAIN/docs/albnn_training_brief.md` | ALBNN 工作流说明。 |
| `SURROGATE_TRAIN/docs/albnn_training_info.md` | ALBNN 文档的简短入口。 |
| `SURROGATE_TRAIN/docs/file_classification.md` | 训练项目文件组、证据类别和清理策略。 |

## 版本化资料

| 路径 | 内容说明 |
| --- | --- |
| `ALB_MAIN/docs/migrations/0.2.0.md` | 0.1 到 0.2 的 namespace、生命周期、DTO、持久化、配置和模型包迁移规则。 |
| `ALB_MAIN/docs/migrations/0.2.0_release_acceptance.json` | 记录最终 pytest、mypy、冻结参考和 tracked 工作树前后门禁。 |
| `ALB_MAIN/docs/migrations/0.2.0_post_release_numeric_acceptance.json` | 记录 S0011/lambda 修正后的 pytest、mypy、S0011 节点和 tracked 工作树门禁。 |
| `ALB_MAIN/docs/migrations/0.2.0_post_release_rotor_acceptance.json` | 记录 RossRotor 时步修正后的 pytest、mypy、转子节点、冻结参考和 tracked 工作树门禁。 |
| `ALB_MAIN/docs/migrations/0.2.0_post_refactor_review_acceptance.json` | 记录 13 项代码审查修正后的全量 pytest、mypy、skip 和 tracked 工作树门禁。 |
| `ALB_MAIN/docs/migrations/0.2.0_second_review_acceptance.json` | 记录 4/6-DOF、真实 coupling、无控制器和显式控制生命周期修正后的全量 pytest、mypy、skip、精确参考和 tracked 工作树门禁。 |
| `ALB_MAIN/docs/migrations/0.2.0_third_review_acceptance.json` | 记录控制器兼容适配、coupler 失效出口、严格节点、无控制器配置回读和 ServoValve2 生命周期修正后的 pytest、mypy、skip、精确参考及 tracked 工作树门禁。 |
| `ALB_MAIN/docs/migrations/0.2.0_fourth_review_acceptance.json` | 记录 harmonic 真实控制器注入、永久/定时开关、控制器类型标签、coupler 拓扑失效及干净候选提交门禁。 |
| `ALB_MAIN/docs/migrations/0.2.0_fifth_review_acceptance.json` | 记录 harmonic 失败重初始化失效、严格嵌套控制器配置、独立默认配置、敏感 untracked/ignored 输入和 HEAD 固定门禁。 |
| `ALB_MAIN/docs/migrations/0.2.0_sixth_review_acceptance.json` | 记录 harmonic 运行中异常失效、detached candidate、Python 环境清理、fresh mypy 和全局 shadow 输入门禁。 |
| `ALB_MAIN/docs/migrations/0.2.0_seventh_review_acceptance.json` | 记录 harmonic 复杂数拒绝、pytest 版本/插件/skip/warning 策略、隔离子进程和现场 wheel 源码绑定门禁。 |
| `ALB_MAIN/docs/migrations/0.2.0_eighth_review_acceptance.json` | 记录 candidate Git blob 规范摘要、稳定构建时间、连续双构建、build tag 1、detached 安装和最终发布 wheel 的同一 SHA 门禁。 |
| `ALB_MAIN/docs/migrations/0.2.0_p2_architecture_acceptance.json` | 记录最终候选的完整 pytest、分层 mypy、detached worktree 和精确发布 wheel 身份。 |
| `ALB_MAIN/docs/migrations/0.2.0_p2_architecture_build_acceptance.json` | 记录 P2 候选的 Git blob 源摘要、双构建、METADATA、隔离安装、extras/CLI smoke 与 wheel SHA。 |
| `ALB_MAIN/docs/migrations/0.3.0_release_acceptance.json` | 记录 0.3 候选的全量 pytest、分层 mypy、冻结参考、detached worktree 和发布制品身份。 |
| `ALB_MAIN/docs/migrations/0.3.0_build_acceptance.json` | 记录 0.3 候选的 Git blob 源摘要、双构建、METADATA、隔离安装、extras/CLI smoke 与 wheel SHA。 |
| `ALB_MAIN/docs/migrations/0.4.0.md` | 记录无兼容 Python API、严格 JSON5、v0.4 surrogate package 和外部消费者迁移边界。 |
| `ALB_MAIN/docs/migrations/0.4.0_release_acceptance.json` | 记录固定实现候选的 Git blob 源、可复现 wheel、pytest、mypy、资源、隔离安装和外部消费者 smoke。 |
| `ALB_MAIN/docs/migrations/0.4.0_test_map.json` | 映射 V4-01 至 V4-24 的源码、测试和文档证据。 |
| `ALB_MAIN/docs/migrations/0.4.1.md` | 记录分析算法恢复、time-step 不变量、倾瓦移除和版本边界。 |
| `ALB_MAIN/docs/migrations/0.4.1_test_map.json` | 映射 V4P 功能、冻结参考、源码和 required nodeid。 |
| `ALB_MAIN/docs/migrations/0.4.1_release_acceptance.json` | 记录固定实现候选的数值参考、双 wheel、pytest、mypy、资源、隔离安装和外部 smoke。 |
| `ALB_MAIN/docs/migrations/0.4.2.md` | 记录输入域、local time-step、仿真失败原子性、磁盘事务和版本边界。 |
| `ALB_MAIN/docs/migrations/0.4.2_test_map.json` | 映射 V4P2 功能、冻结参考、源码和 required nodeid。 |
| `ALB_MAIN/docs/migrations/0.4.2_deferred_debt.md` | 记录 mypy 旧基线和无明确契约 TODO 的影响与关闭条件。 |
| `ALB_MAIN/docs/migrations/0.4.2_release_acceptance.json` | 记录固定实现候选的参考、双 wheel、pytest、mypy、资源、隔离安装和外部 smoke。 |
| `ALB_MAIN/docs/migrations/0.4.3.md` | 记录 rotor coupling、静平衡浮点边界、严格 JSON5 和 surrogate spool 修复。 |
| `ALB_MAIN/docs/migrations/0.4.4.md` | 记录根 schema 版本入口、独立版本流和迁移边界。 |
| `ALB_MAIN/docs/migrations/0.4.5.md` | 记录二阶 Hz、静态、任意传递函数、迁移规则和参考边界。 |
| `ALB_MAIN/docs/migrations/0.2.0_external_consumer_audit.json` | declared 外部调用者的路径、哈希、旧 import 和迁移目标快照。 |
| `ALB_MAIN/docs/migrations/0.2.0_paper_work_post_migration_audit.json` | PAPER_WORK 的 0.2 迁移后哈希、模型校验、验证摘要与保留边界。 |
| `ALB_MAIN/docs/migrations/0.2.0_surrogate_train_post_migration_audit.json` | SURROGATE_TRAIN 的 0.2 迁移后提交、模型校验、验证摘要与保留边界。 |

## 其他工作区与入口

| 路径 | 内容说明 |
| --- | --- |
| `ALB_MAIN/AGENTS.md` 与 `ALB_MAIN/CLAUDE.md` | 通用代理策略与 Claude 特有约定 |
| `ALB_MAIN/docs/api/public_api_reference.md` | 生成式稳定公开 API 参考 |
| `F:/BaiduSyncdisk/博士论文/PAPER_WORK/AGENTS.md` | PAPER_WORK 稳定代理策略 |
| `SURROGATE_TRAIN/AGENTS.md` | 稳定训练项目代理策略 |
| `ARTIFACTS_ARCHIVE/docs/file_classification.md` | 归档文件归属策略 |
| `DATA_POSTPROCESS/docs/file_classification.md` | 后处理文件归属策略 |
| `PARAM_SCAN/docs/file_classification.md` | 参数扫描文件归属策略 |
| `VALIDATION/docs/file_classification.md` | 验证文件归属策略 |
| `SPLIT_INDEX.md` | split workspace 索引 |
| `SURROGATE_TRAIN/docs/run_index.md` | 指向全局 run 规则和 current-status 的指针 |

## 数据与日志路径

| 路径 | 内容说明 |
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
| `ALB_MAIN/docs/migrations/0.2.0_sixth_review_acceptance.json` | 六轮代码审查修正的 detached candidate、harmonic 半推进失效、环境隔离、fresh mypy 和 shadow 输入门禁。 |
| `ALB_MAIN/docs/migrations/0.2.0_seventh_review_acceptance.json` | 七轮代码审查修正的复杂数失效、pytest 证据策略、隔离工具链和现场 wheel 源码绑定门禁。 |
| `ALB_MAIN/docs/migrations/0.2.0_eighth_review_acceptance.json` | 八轮制品身份修正的 Git blob 规范源、双构建一致性、detached 安装和最终发布 wheel 同一 SHA 门禁。 |
| `ALB_MAIN/docs/migrations/0.4.0_release_acceptance.json` | 0.4 固定实现候选的可复现 wheel、pytest、mypy、资源、隔离安装和外部消费者 smoke 门禁。 |
| `ALB_MAIN/refs/full_repo_refactor_addendum_v1/` | 从重构前隔离源码生成的 thermal direct/Newton/transient 不可覆盖补充参考。 |
| `ALB_MAIN/refs/thermal_harmonic_migration_v1.*` 与 `thermal_harmonic_projection_v1.*` | 从原始解析脚本分别冻结的旧热源坐标和修正后热源坐标参考，含来源哈希、配置及三个频率的系数和各瓦基态。 |
| `ALB_MAIN/outputs/thermal_harmonic_integration_20261008/verification.json` | 热耦合谐波工具的当前工作树、参考差异、相关测试、定向类型检查及最终 wheel 隔离计算证据。 |
| `ALB_MAIN/docs/run_index.md` | 人类可读的工作区全局 run 编号和路径策略。 |
| `F:/BaiduSyncdisk/博士论文/PAPER_WORK/AGENTS.md` | 论文任务文件管理、路径命名和证据保留规则。 |
| `F:/BaiduSyncdisk/博士论文/PAPER_WORK/docs/current_task_status.md` | 论文任务当前状态、最新输出路径、检查命令和下一步。 |
| `SURROGATE_TRAIN/docs/current_runtime_status.md` | 当前活跃 run 定位、进度和下一步状态。 |

## 文档维护与恢复

- 当前开发、验证和风险见 `ALB_MAIN/docs/current_state.md`。
- 2026-10-06 按用户授权清理旧文档与维护日志；逐项清单和工作树原文恢复副本见
  `ALB_MAIN/outputs/maintenance/document_cleanup_20261006_8f066d8f/manifest.json`。
- 旧每日文档维护任务 `ALB_DailyDocMaintenanceAudit` 已禁用，最近一次运行为 2026-05-13；
  外层脚本保留在 `G:/ALB_PROJECTS/.agents/doc-maintenance/`。
