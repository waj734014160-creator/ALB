# ALB_MAIN 文件分类

## 文档角色

- 角色：ALB_MAIN 文件归属和清理策略。
- 目的：分类 ALB_MAIN 中的文件组、归属边界、产物类别和清理策略。
- 允许更新：文件类别、代表路径、保留/归档规则、清理风险说明和归属边界。
- 禁止更新：实时运行状态、模型进度、最新指标和详细运行历史。
- 更新节奏：当主要文件组、归档类别或清理策略变化时更新。
- 事实来源 / 相关文档：
  `docs/daily_maintenance/daily_doc_update_index.md`、
  `docs/current_state.md`、
  `docs/project_overview.md`。

本文只定义归属和处理策略。移动、删除、归档或清理仍需独立任务和明确确认。

## 分类原则

- `ALB/` 是稳定 package 边界；领域代码不得复制到兄弟项目。
- `tests/` 是唯一测试树；仓库根目录不再保留并行的 `test/`。
- 原始证据优先保留。图、CSV、JSON、日志、checkpoint 和 pickle 不因文档整理而删除。
- 生成物与源码分离。缓存、wheel、隔离安装和运行输出不得成为 package import 依赖。
- 当前 `git status` 中与任务无关的修改视为用户工作，未经明确授权不暂存、不移动、不覆盖。
- 外部项目有独立所有权；ALB_MAIN 只保存只读迁移审计，不替外部项目落地改动。

## 稳定 tracked 内容

| 类别 | 代表路径 | 处理规则 |
| --- | --- | --- |
| 包源码 | `ALB/contracts/`、`core/`、`config/`、`physics/`、`control/`、`dynamics/`、`surrogate/`、`systems/`、`infrastructure/`、`workflows/` | 保留；按 `docs/interface_architecture.md` 的依赖方向维护。 |
| 正式测试 | `tests/unit/`、`tests/integration/`、`tests/regression/`、`tests/validation/` | 保留；所有测试输出使用 pytest `tmp_path`。 |
| 工具 | `tools/benchmarks/`、`diagnostics/`、`docs/`、`manual/`、`migrations/`、`reference/`、`validation/` | 保留；诊断/manual 不纳入默认 pytest 收集；docs 生成器只更新指定生成文档。 |
| 行为参考 | `refs/full_repo_refactor_v1/`、`refs/full_repo_refactor_addendum_v1/` 及其他版本化 refs | 永久保留并按版本新增；不得覆盖现有 v1 或 addendum v1。 |
| 人类文档 | `README.md`、`AGENTS.md`、`docs/` | 保留；按文档角色索引更新，维护类文档使用中文。 |
| 包和测试配置 | `pyproject.toml`、`.editorconfig`、`.gitignore` | 保留；`testpaths` 只能指向 `tests`。 |
| 维护脚本 | `scripts/` | 保留；注释、docstring 和 CLI help 使用英文。 |
| 稳定调用配置 | `paper_config/` | 保留；只存稳定配置，不写论文实时任务状态。 |
| 历史测试资产 | `tests/fixtures/legacy/bearing/` | 保存从旧 `test/` 归并的气膜图件、热耦合图件和 Fuzzy ALB 配置；不参与 pytest 收集。两张会被本地运行反复覆盖的 thermal 图保持 local-only。 |

## 测试与工具边界

| 内容 | 当前路径 | 判定 |
| --- | --- | --- |
| 小范围纯逻辑测试 | `tests/unit/` | 默认快速执行。 |
| 多组件和 IO 边界测试 | `tests/integration/` | 使用临时目录，不写 tracked 文件。 |
| 冻结行为等价 | `tests/regression/` | 对 v1 数组使用精确相等；不以放宽容差掩盖漂移。 |
| 架构、物理和发布验收 | `tests/validation/` | 包含 import、optional dependency、wheel、迁移、时序和工程门禁。 |
| 历史测试资产 | `tests/fixtures/legacy/` | 只保存迁移后仍需保留的图件和轻量配置；不是测试模块，也不得作为测试输出目录。 |
| 自动诊断 | `tools/diagnostics/` | 人工触发；输出必须去 ignored/临时目录。 |
| API 与站点文档生成 | `tools/docs/`、`docs/api/`、`docs/site/`、`mkdocs.yml` | 从根公开接口、配置字段和高级 namespace 显式导出生成稳定参考；`--check` 不写文件并纳入 pytest，`site/` 是 ignored 可再生输出。 |
| 手动 GUI/绘图 | `tools/manual/` | 不由 pytest 自动运行。 |
| 基准 | `tools/benchmarks/` | 先过精确参考，再执行计时。 |
| 参考生成 | `tools/reference/` | 只创建新版本 reference；禁止覆盖 v1。 |

重构前 242 个 pytest 节点和 19 个非收集文件的逐项去向固定在 `docs/migrations/0.2.0_test_map.json`，不能通过删除测试文件来绕过映射。

## 生成物与本地内容

以下内容默认不是稳定 tracked 源码：

| 类别 | 常见路径 | 策略 |
| --- | --- | --- |
| Python 与开发工具缓存 | `**/__pycache__/`、`*.pyc`、`.cache/{pytest,mypy,ruff}/` | 可再生；统一存放在根目录 `.cache/` 并保持 ignored。 |
| 构建产物 | `dist/`、`build/`、`*.egg-info/` | 可再生；发布前核对 wheel digest，通常不提交二进制 wheel。 |
| 本地验证环境 | `outputs/.devtools/`、`outputs/wheel_smoke/` | 可再生；保持 ignored，不作为运行时依赖。 |
| 训练/计算输出 | `outputs/`、模型目录、远程日志目录 | 原始证据；默认不删除，按所属项目状态文档定位。 |
| 本地代理配置 | `.codex/` | 用户/工具状态；未经请求不提交。 |
| notebook/手动输出 | `*.ipynb`、`*.png`、`*.html`、`*.log` | 先确认研究用途和归属，再决定归档。 |

即使生成物 ignored，也不能在不了解目标绝对路径时递归删除。清理前必须解析并核对路径位于预期工作区。

## 本地忽略的实验资产

以下内容按用户确认保留在本机，但不再进入 Git 工作树状态或后续提交：

- `tests/fixtures/legacy/bearing/thermal_plots/alb_thermal_4pads.png`
- `tests/fixtures/legacy/bearing/thermal_plots/orifice_thermal_comparison.png`
- `.codex/`
- `tools/manual/control/LQG/albnn_rotor0_lqg_small_signal.py`
- `tools/manual/control/LQG/output/`

两张 thermal 图从 tracked 集合解除但本地文件不删除；可从 `v0.2.0` 或更早提交恢复历史版本。`.codex/` 保持原位，LQG 本地脚本和输出归入 `tools/manual/control/LQG/`。以上路径均由根 `.gitignore` 的精确规则覆盖，不应再被误报为测试副作用。

## 外部项目归属

| 项目 | 所有权 | ALB_MAIN 可做的工作 |
| --- | --- | --- |
| `../SURROGATE_TRAIN` | 数据集、训练脚本、模型、队列和运行状态 | 只读导入/语义审计；报告保存在 `docs/migrations/`。 |
| `F:/BaiduSyncdisk/博士论文/PAPER_WORK` | 论文计算脚本、配置、图、数据和任务状态 | 只读迁移审计；不得在本仓库任务中修改。 |
| `G:/ALB_PROJECTS/TOOL/ALB_GUI` | GUI 打包与发布资产 | 只引用稳定 ALB 包；GUI 变更属于独立项目。 |

0.2.0 外部快照固定为 SURROGATE_TRAIN 23 个文件和 PAPER_WORK 27 个文件。详细哈希和目标 namespace 见 `docs/migrations/0.2.0_external_consumer_audit.json`。

## 私密信息与配置

- tracked 邮件 example 只能包含占位值，不得包含私人地址、授权码、密码、key 或恢复码。
- `SmtpNotifier` 只接受注入配置或环境变量；secret 不写入源码、文档、测试 reference 或日志。
- 从当前树删除私人值不会删除 Git 历史；如凭据曾出现，必须在外部轮换。

## 清理决策顺序

1. 用 `git status --short` 和 `git ls-files` 区分 tracked、modified、untracked 和 ignored。
2. 查本文件与目标目录的本地规则，确认所有权。
3. 判断文件是源码、测试、reference、原始证据、生成物还是用户工作。
4. 对原始证据、用户工作、外部项目或不明内容停止并请求确认。
5. 只对明确可再生且目标绝对路径已核验的生成物执行清理。
6. 清理后报告删除范围和可恢复性；不得使用 `git reset --hard` 处理混合工作树。
