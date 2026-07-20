# ALB_MAIN 文件分类

## 文档角色

- 角色：ALB_MAIN 文件归属和清理策略。
- 目的：分类 ALB_MAIN 中的文件组、归属边界、产物类别和清理策略。
- 允许更新：文件类别、代表路径、保留/归档规则、清理风险说明和归属边界。
- 禁止更新：实时运行状态、模型进度、最新指标和详细运行历史。
- 更新节奏：当主要文件组、归档类别或清理策略变化时更新。
- 事实来源 / 相关文档：
  `docs/daily_maintenance/daily_doc_update_index.md`。

本文档记录当前项目文件面向的主要需求、代表目录/文件、建议处理方式和风险点。它只用于建立分类清单和后续整理建议；不移动文件、不修改 import、不清理训练产物。

## 分类原则

- 保持源码布局稳定。`ALB/` 仍是稳定 Python 包边界。
- 保留实验证据。`outputs/` 默认视为归档候选，不视为删除目标。
- 区分可重复测试和探索性工作。pytest 文件、诊断脚本、notebook、GUI 工具和产物应分别标注。
- 将当前 git 状态视为用户正在进行的工作。移动、删除或产物清理必须作为单独确认步骤。
- 日志是原始证据，不作为统一托管树维护；稳定规则写入文档，实时定位写入当前状态文件。

## 需求分类

| 需求类型 | 代表路径 | 建议处理 | 风险说明 |
| --- | --- | --- | --- |
| 稳定库代码 | `ALB/`, `pyproject.toml` | 新代码按 `contracts/core/adapters/physics/control/dynamics/systems/surrogate` 分类；旧实现路径保留兼容。 | 移动大型实现会牵涉 import、pickle 和外部脚本，应按物理域逐步迁移。 |
| 任务和批处理入口 | `task/`, `ALB/task.py` | 保留现有入口；后续再区分可复用工作流和一次性脚本。 | 部分脚本使用本地绝对路径，并会把任务文件复制到输出目录。 |
| 运行脚本和实验 | `run/`, `run/validation/`, `run/JKW/` | 保留可复现脚本；将生成的子目录标为产物。 | 部分脚本面向论文/演示，可能写入 `run/_*` 目录。 |
| 远程 ALBNN 工具 | `ALB/remote/`, `test/remote/`, `refs/remote_albnn_*_reference_v1.json` | 保留为远程 helper 的稳定实现和回归基线。 | 兼容入口在兄弟项目 `SURROGATE_TRAIN/run/remote/`；不要恢复重复实现。 |
| run 与 current-status 规则 | `docs/run_index.md`, `../SURROGATE_TRAIN/docs/current_runtime_status.md` | `docs/run_index.md` 维护可复用 run 编号/路径规则；拥有项目的 current-status 文档维护活跃 run 定位状态。 | 不把 Markdown 当数据库解析；不主动回填历史 run，除非要复用、审计或归档。 |
| pytest 和工程验证 | `test/*.py`, `test/bearing/`, `test/config/`, `test/thermal/` | 先在文档中区分回归、单元、集成、验证和诊断目的。 | `test/` 同时包含 notebook、GUI、日志和图片，不能简单视为纯 pytest 目录。 |
| 历史数据处理和 notebook | `data_process/`, `learning_note/`, `test/**/*.ipynb` | 作为研究历史保留；后续可迁移到 `notebooks/` 或 `experiments/notebooks/`。 | 许多 notebook 可能包含嵌入输出和硬编码本地路径。 |
| 文档和约定 | `docs/`, `AGENTS.md`, `README.md` | 保留并持续改进；文档作为项目组织的第一层。 | 旧文档可能存在编码问题，复用前需要审查。 |
| 训练数据、模型、图、日志 | `outputs/`, `run/_*`, `test/**/_*`, `*.png`, `*.csv`, `*.json`, `*.pkl`, `*.pth` | 按实验目标/日期归档；默认不删除。 | metadata、scaler、模型权重和 CSV 可能是复现必需资产。 |
| IDE、缓存和临时文件 | `.idea/`, `.vscode/`, `.pytest_cache/`, `__pycache__/`, `output.txt` | 确认不是刻意跟踪后，标记为清理候选。 | 当前工作区可能有未提交修改；清理必须单独复查。 |

## 外部论文工作区规则入口

`F:/BaiduSyncdisk/博士论文/PAPER_WORK` 是论文任务的外部工作区，不是 `ALB_MAIN` 仓库的一部分；`ALB_MAIN` 只提供包代码、远程 helper 和稳定文档规则。该工作区的脚本、日志、远程配置、图目录、数据目录、图片审计和 current-status 归属规则已迁移到 `F:/BaiduSyncdisk/博士论文/PAPER_WORK/AGENTS.md`。整理或审计论文任务文件前，应先读取该文件。

## ALB 模块图

`ALB/` 目前应继续作为公共包边界。下表只提供职责视图；维护公共接口和包边界时，应优先阅读 `docs/alb_package_overview.md`。

| 区域 | 文件 | 目的 |
| --- | --- | --- |
| 结构协议与核心模板 | `contracts/`, `core/`, `adapters/`, `base.py` | 窄领域协议、生命周期/事件/时间模板、验证、兼容 adapter；`base.py` 保留旧 import 和有限元基础类型。 |
| 分类 namespace | `physics/`, `control/`, `dynamics/`, `systems/`, `surrogate/` | 新代码的职责入口；通过 lazy export 指向当前兼容实现。 |
| 数值基础 | `mesh.py`, `boundary.py`, `gauss.py`, `matrix/` | 节点/单元管理、网格生成、边界处理、矩阵组装和迭代求解。 |
| 油膜和轴承模型 | `film.py`, `bearing.py`, `orifice.py`, `gas.py` | Reynolds 油膜求解、静压/气体轴承、多瓦组装、节流孔和供油流量模型。 |
| ALB 系统和控制 | `alb.py`, `controller.py`, `servovalve.py`, `lti.py` | ALB 装配、PID/fuzzy/LQG 相关控制、伺服阀模型和状态空间工具。 |
| 热模型和无量纲模型 | `thermal.py`, `nondim.py` | 热流体耦合、黏温耦合、无量纲尺度和包装求解器。 |
| 转子耦合 | `rotor.py`, `orbit.py`, `couple.py` | ROSS 转子集成、轨迹生成、转子-轴承耦合和时域响应流程。 |
| 代理模型 | `nn.py` | ALBNN 和热代理模型定义、特征增强、推理/训练 helper。 |
| 远程工作站工具 | `remote/` | SSH、PowerShell、Task Scheduler、ALBNN 启动/状态/队列 helper，供兄弟训练项目使用。 |
| 工具、配置和结果 | `tool.py`, `config.py`, `results.py`, `postprocess.py`, `logger.py` | 配置对象、json5 读取、结果树、日志、绘图/后处理和通用工具。 |

注意：

- 本阶段不要重命名 `ALB/matrix/dynmaic.py`。该拼写已进入现有 import，若后续修改必须有兼容计划。
- `ALB/tool.py` 和 `ALB/config.py` 仍较宽，适合未来渐进拆分，但不适合在文档整理中直接移动。
- `ALB/task.py` 与 `task/*.py` 在工作流职责上有重叠。后续清理应先定义哪些 API 是可复用库工作流，哪些是命令行实验入口。

## 输出和产物

实验输出、运行日志、队列状态快照和训练配置默认属于兄弟项目 `SURROGATE_TRAIN`，除非它们是正式的 `ALB` 包回归 fixture。工作区全局 run 规则由 `ALB_MAIN/docs/run_index.md` 维护，活跃 run 定位状态由拥有项目的 current-status 文档维护。

未来 run 应使用项目编号前缀和放置策略：配置放在拥有子项目下，结果产物放在该子项目的 `outputs` 下，日志路径保留在负责工具实际写入的位置，短期非活跃归档放在该子项目的 `outputs/archive`。日志是原始证据，不另外统一维护成单独树。

`outputs/` 应视为归档候选，而不是清理目标：

| 产物组 | 代表路径 | 建议标签 |
| --- | --- | --- |
| 当前热 ALBNN 数据/模型尝试 | `outputs/albnn_data_lr_cq_*`, `outputs/albnn_model_lr_cq_*` | 按热 ALBNN 实验归档，保留 `metadata.json`、CSV、scaler、权重和诊断图。 |
| 历史或对比 ALBNN 结果 | `outputs/albnn_model_r2_1000`, `outputs/albnn_validation_review`, `outputs/model2_*` | 作为历史/模型对比证据归档，不与当前 12 列热 ALBNN 输入混用。 |
| 热 MLP 输出 | `outputs/thermal_mlp`, `outputs/thermal_mlp_data` | 按热力代理模型工作归档。 |
| 热诊断和对比 | `outputs/thermal_kc_compare`, `outputs/thermal_force_time_term_compare`, `outputs/transient_thermal` | 作为验证和诊断结果归档。 |
| 演示和论文图片 | `run/_compare_orifice`, `run/_paper_textured_foil`, `run/_tilting_pad_demo`, `outputs/_gas_bearing_demo` | 如被文档、报告或 notebook 引用则保留。 |
| smoke 和极小样本输出 | `outputs/albnn_smoke*`, `outputs/albnn_data_smoke*`, `outputs/albnn_data_parallel_smoke` | 只有确认不是快速回归 fixture 后，才作为清理候选。 |
| 远程 helper 回归产物 | `refs/remote_albnn_*_reference_v1.json`, `test/remote/` | 与 `ALB.remote` 一起保留，用于重构时维持 CLI/wrapper 行为。 |

不要在未检查配套实验资产关系前建议删除 `.csv`、`.json`、`.pth` 或 `.pkl` 文件。

## test 目录分类

`test/` 包含多种工作，不应当视为单一 pytest-only 区域。

| 测试区域 | 代表路径 | 建议未来位置 |
| --- | --- | --- |
| 单元/配置测试 | `test/config/test_config_validate.py`, `test/test_logging_dedup.py`, `test/tool/test_bearing_film_nastran_export.py` | `test/unit/` |
| 集成测试 | `test/bearing/test_thermal_wrapper.py`, `test/bearing/test_tilting_pad_bearing.py`, `test/bearing/test_gas_bearing.py` | `test/integration/` |
| 回归/等价测试 | `test/bearing/test_nodim_interfaces.py`, `test/bearing/test_nodim_alb_equivalence.py`, `test/test_nondim_thermal_field_case.py` | `test/regression/` |
| 工程验证 | `test/bearing/validation_runner.py`, `test/bearing/validation_reference_data.py`, `test/bearing/test_validation_smoke.py`, `test/bearing/test_validation_precision.py` | `test/validation/` |
| 诊断脚本 | `test/thermal/_thermal_*_diagnose.py` | `experiments/diagnostics/` 或 `test/diagnostics/` |
| 手动工具和 notebook | `test/gui_bearing.py`, `test/gomoku_game.py`, `test/**/*.ipynb`, `test/**/*.png`, `test/**/*.html`, `test/**/*.log` | `tools/manual/`, `notebooks/` 或 `test/artifacts/` |

## 未来目录建议

以下是后续阶段可选目标结构；本文档不会实施这些迁移。

| 目标路径 | 内容 |
| --- | --- |
| `archive/YYYYMMDD_<experiment>/` | 按日期和实验目的分组保存的输出包。 |
| `notebooks/alb/`, `notebooks/control/`, `notebooks/ansys/`, `notebooks/symbolic/`, `notebooks/misc/` | 当前位于 `learning_note/`、`data_process/` 和 `test/` 下的探索 notebook。 |
| `experiments/diagnostics/` | 有价值但不属于正式 pytest 的一次性诊断脚本。 |
| `ALB/remote/` | 稳定 LAN/远程 helper API；`SURROGATE_TRAIN/run/remote/` 应保持为轻量兼容入口。 |
| `tools/manual/` | GUI demo、手动可视化 helper、邮件/Nastran 工具和非测试脚本。 |
| `test/artifacts/` | 测试生成的图、日志、HTML 和参考输出快照。 |

## 实施约束

- 不要在引入分类文档的同一变更中移动源码文件。
- 文档整理不修改 `pyproject.toml`、包发现规则或公共 import 路径。
- 未经单独复现性审查，不删除训练数据、模型权重、scaler 或 metadata。
- 任何实际迁移前，先捕获干净文件清单，并针对受影响区域运行聚焦测试。
- 保持 `AGENTS.md` 中的本地约定：代码注释使用英文，黏度变量使用 `miu`，Python 中使用 `lambda_value` 而不是裸 `lambda`。
