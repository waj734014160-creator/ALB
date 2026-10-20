# 工具索引

本目录保存 ALB_MAIN 的分析、维护和手动工具。可复用数值实现属于 `ALB/`，论文和训练任务的脚本、配置及产物分别属于 PAPER_WORK 和 SURROGATE_TRAIN。

| 目录 | 用途 | 执行与输出边界 |
| --- | --- | --- |
| `analysis/` | 谐波线性化、网格独立性分析、供油收敛诊断、0.4.7 耦合积分器对比研究 | 人工选择配置和输出目录；不能仅因脚本名称含 diagnose 就删除。 |
| `benchmarks/` | 行为核对后的性能比较 | 保留对应参考；不将计时替代数值验证。 |
| `diagnostics/` | 热模型等局部诊断 | 人工触发，产物写入任务输出或临时目录。 |
| `docs/` | API、配置和 namespace 文档生成 | 通过生成器更新文档；`--check` 用于漂移检查。 |
| `hooks/` | 编辑后的文件检查 | 与调用配置和 `tests/unit/test_changed_file_hook.py` 一起维护。 |
| `manual/` | 谐波复核、绘图、控制实验 | 不加入默认 pytest 收集。 |
| `manual/notebooks/` | 配置探索、M35 十点物理重算 notebook | 手动运行；保留外部数据依赖和原数值结果的适用范围。 |
| `manual/archive/` | 旧绘图演示和旧 GUI 入口 | 见[历史入口说明](manual/archive/README.md)，不属于支持中的操作入口。 |
| `migrations/` | 版本配置迁移和历史审计生成 | 被历史证据引用的脚本保留；运行前核对目标版本。 |
| `reference/` | 创建新版本行为参考 | 不覆盖既有冻结参考。 |
| `validation/` | 分层类型检查、资源与发布验收 | 保持固定候选和制品身份要求，输出路径按各 CLI 契约处理。 |

## 手动入口

- 谐波系数计算：`analysis/run_harmonic_linearization.py`，调用包内 `bearing.analysis.harmonic_linearize()`；可运行配置为 `analysis/thermal_harmonic_example.json5`，用法见[分析工作流](../docs/site/guides/analysis.md)。
- 谐波时域复核：`manual/run_alb_harmonic_kcg_validation.py`。
- 0.4.7 耦合积分器对比：`analysis/run_predictor_corrector_0_4_7_study.py`，在解析转子/轴承和小网格液膜上比较 staggered、ROS2 与预测-校正的误差、收敛阶、迭代次数和代价，输出 JSON（默认 `.cache/tmp/predictor_corrector_0_4_7_study.json`）；依赖 `tests/_support` 的解析测试替身，结论见 `docs/alb_0_4_7_predictor_corrector_report.md`。
- 谐波力重建绘图：`manual/plot_alb_harmonic_time_response.py`。
- LQG 演示与本地结果：`manual/control/LQG/`；结果仍按既有引用原位保留。
- 配置探索：`manual/notebooks/bearing_config_exploration.ipynb`。
- M35 训练样本的物理重算：`manual/notebooks/m35_training_10_sample_refactored_alb_validation.ipynb`；需要外部模型数据和论文配置，本次仅移动文件，未重新计算。

## 本地独立项目

`dev_docs_portal/` 是具有自身 Git 历史的独立站点仓库，通过精确忽略规则与本包分开。它的源码、依赖和部署状态按独立项目管理，不随 ALB_MAIN 工具缓存递归清理。

## 临时输出与历史资产

新的一次性检查优先使用 `.cache/tmp/` 或明确的 `outputs/<domain>/`。分层 mypy 的现有默认目录仍是 `outputs/mypy_layered_cache/`，其缓存可以在未被使用时重建；`outputs/.devtools/` 是验证工具依赖，不能把它的移除当作无影响的普通缓存清理。

清理规则见[文件分类](../docs/file_classification.md)，本次路径变更和恢复方法见[清理记录](../docs/daily_maintenance/project_cleanup_20260926.md)。
