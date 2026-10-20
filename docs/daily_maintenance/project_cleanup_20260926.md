# 2026-09-26 项目清理与归档记录

参考来源：[机器处置清单](project_cleanup_20260926_manifest.json)及本地 `outputs/maintenance/project_cleanup_20260926/`。

## 范围与基线

用户授权直接删除五子棋，其余按既定计划完成缓存清理、脚本分类和研究资产归档。

- 仓库：`G:/ALB_PROJECTS/ALB_MAIN`。
- 分支：`codex/alb-0.4.5`；HEAD：`aafb9fc8e099aa8191a7a12293787ec5ed6ac6b9`。
- 清理前已有 26 个修改文件和 18 个未跟踪状态条目。未提交的热求解、热记忆、测试、配置及代理工具工作不随清理撤销。
- 本次不修改 ALB 数值实现、不重算历史结果、不修改外部项目文件，也不暂存或提交用户改动。
- 改动前保存文件哈希、受影响文档的工作树副本及 pytest 收集日志；备份包含原有未提交文档修改。

## 已执行处置

| 类别 | 已执行动作 |
| --- | --- |
| 五子棋 | 删除 `tools/manual/gomoku_game.py`，原摘要和恢复提交记入清单。 |
| 检查缓存 | 清理 45 个 outputs 顶层 mypy 缓存目录，以及 17 个验收目录内的 mypy 缓存；验收报告保留原位。 |
| 构建与隔离环境 | 清理 `build/`、`site/`、两处空临时目录和四个旧隔离安装目录；保留验证工具使用的 `outputs/.devtools/`。 |
| Python 编译缓存 | 只删除有对应源码的编译缓存；自动再生缓存单独计数，不反复删除。 |
| 旧演示源码 | `plot_test.py`、`alb_gui_app.py` 移入 `tools/manual/archive/`，保留原字节和使用限制。 |
| 交互 notebook | 两份 `tests/user/` notebook 移入 `tools/manual/notebooks/`；`test.ipynb` 更名为 `bearing_config_exploration.ipynb`。内容不变，原空目录移除。 |
| 已完成本地任务 | 伺服阀报告、静平衡结果、Sharma 暂存成果、文献渲染、简历审阅等迁入本地归档，保留完整任务结构。 |
| 历史 GUI | `dist/ALB_GUI.7z` 与部分仅存编译文件的旧 GUI、实验和维护脚本归档保存。 |
| 分类规则 | 为临时目录、Claude 工作树及独立文档门户补齐精确忽略规则；新增工具索引，明确 notebook 与历史入口。 |

主清单共完成 533 项动作，累计删除文件逻辑大小为 3,389,224,264 bytes，约 3.16 GiB。该数字不是磁盘分配簇测量；自动再生缓存及扣除后值见机器清单。

迁移总量为 278,888,457 bytes，共 187 个文件。所有迁移文件逐项核对 SHA-256，文件内容不变。

## 归档和恢复入口

本地资产包：`outputs/archive/project_cleanup_20260926/`。

| 子目录 | 内容 |
| --- | --- |
| `local_tasks/tmp/` | 按原任务名保存研究脚本、配置、数据、图件、报告和日志。 |
| `distribution/` | 历史 GUI 分发包。 |
| `legacy_bytecode/` | 孤立编译文件的恢复线索，保留原相对目录。 |

包内 `README.md` 说明恢复方法。机器清单中的 `move` 条目记录原路径、归档路径和逐文件摘要。历史快照正文未重写；重跑包含旧绝对路径的脚本前，在独立副本中按映射恢复目录并核对依赖和外部数据。恢复前检查目标，避免覆盖后续工作。

五子棋可从上述 HEAD 的原路径恢复。旧迁移映射和冻结参考描述其绑定版本，本次通过新增处置清单追溯，不改写原映射。

## 原位保留与限制

- ALB 数值源码、正式测试、冻结参考和历史迁移验收内容保持清理前字节。
- 六个历史 wheel 保留在 `dist/`，发布报告仍使用原路径。
- LQG 原始结果保留在 `tools/manual/control/LQG/output/`，继续沿用本地脚本及引用。
- `.cache/` 中的热记忆短跑、失败诊断和训练快照按证据保留。
- `tmp/sharma_task/numba_cache/` 仍被 PAPER_WORK 的 `Sharma固定偏心率热分配系数流量复核.py` 引用，保持原位；`tmp/__pycache__/` 的孤立编译文件也保留。
- `tools/dev_docs_portal/` 是独立 Git 仓库，本次不处理其源码、依赖或部署。
- 两个额外 Git 工作树各有未跟踪文件：Claude 工作树的三份文本、参考工作树的 `capture_0_4_1_refs.py` 均保留。
- 11 处旧测试目录拒绝读取，`dist/re_alb-0.2.0-py3-none-any.whl` 也拒绝读取内容。本次未更改权限或强制清理，精确路径见机器清单；这些内容不计入已核验的可释放空间。

本地归档继续被 Git 忽略，仍位于同一磁盘；不能替代异地备份。

## 验证

文件保护检查已确认 575 个源码、配置和文档文件，以及 1,845 个本地证据文件的摘要一致；允许变更的分类文档和明确处置项单独核对。

| 检查 | 实际结果 |
| --- | --- |
| pytest 收集 | 清理前后均为 631 项，节点顺序和摘要完全一致。 |
| 历史测试资产、依赖边界和文档合同 | 14 passed、1 failed；失败属于以下已有源码依赖问题。 |
| 严格文档构建 | 通过，验证站点写入本地清理证据目录，未重新生成根 `site/`。 |
| notebook 格式 | 两份移动后的 notebook 均通过 nbformat 校验，未执行数值重算。 |
| Git 差异空白检查 | 通过；原有换行转换提示未改变文件内容。 |

失败节点为 `tests/validation/test_import_boundaries.py::test_production_imports_obey_namespace_layers`。
`ALB/surrogate/training/thermal_memory_training.py:417` 导入 `ALB.dynamics.identification`，
不在测试定义的 surrogate 依赖白名单内。触发源码及测试在清理前后的 SHA-256
分别保持 `b25ea4686f775ec4993cf37c09c519f9c4d4b4461f2f0dc42edc00d43b78095f`
和 `d20ed153e09c1666fc0501aa152a9d73a15616fd5a1531df41eb993d43ba99b5`，其余 ALB
源码也通过保护检查，因此该问题不是本次清理引入。留给原热记忆实现任务处理，本次不放宽依赖规则。

pytest 同时保留一个已有 `Unknown config option: cache_dir` 提示，来自当前禁用 cacheprovider 的配置组合。完整数值回归和固定 SHA 发布验收不属于本次文件组织变更的验证范围。

## 执行证据

`outputs/maintenance/project_cleanup_20260926/` 保存清理前清单、原文档副本、逐项执行日志、访问限制检查、测试日志及验证结果。删除与迁移均核验绝对路径，并排除链接及嵌套 Git 状态。

执行汇总发生一次 PowerShell 字典类型错误，修复时根据完整逐项日志生成汇总，未重放文件动作。混合空目录删除与核验的命令曾被自动审批拒绝；只读确认后，限定单个明确空目录的操作执行成功。
