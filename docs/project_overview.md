# ALB_MAIN 项目概览

## 文档角色

- 角色：ALB_MAIN 项目入口概览。
- 目的：给人类用户和代理提供项目边界、主要目录、首读文档和常用验证入口。
- 允许更新：项目职责、目录职责、首读文档、稳定验证入口和跨项目边界说明。
- 禁止更新：实时运行状态、详细实验日志、模型指标流水、原始日志正文和源码实现细节。
- 更新节奏：项目拆分、目录职责、首读文档或稳定工作流入口变化时更新。
- 事实来源 / 相关文档：
  `AGENTS.md`、
  `docs/daily_maintenance/daily_doc_update_index.md`、
  `docs/current_state.md`、
  `docs/alb_package_overview.md`、
  `docs/api/README.md`、
  `docs/interface_architecture.md`、
  `docs/next_interface_development_plan.md`、
  `docs/adr/README.md`、
  `docs/alb_albnn_quickstart.md`、
  `docs/file_classification.md`、
  `docs/run_index.md`。

## 项目定位

`ALB_MAIN` 是 `G:/ALB_PROJECTS` split workspace 中可复用的 ALB 数值库。当前
0.4 包负责维护以下稳定能力：

- Reynolds 油膜、节流孔、液体/气体轴承和热流耦合模型。
- PID、Fuzzy、LQG、伺服阀、降阶和控制辅助算法。
- 转子、耦合、轨迹、频域识别和谐波线性轴承能力。
- ALBNN 特征、网络、scaler、model package、推理和训练基础设施。
- 强类型组件契约、统一结果快照、持久化边界和通用远程工作站机制。

本项目不承担 `SURROGATE_TRAIN` 的训练数据、模型 run 和实时队列状态，也不承担 `PAPER_WORK` 的论文计算脚本和任务状态。外部项目应安装或引用本包，不应复制 `ALB/` 源码。

## 主要目录

| 路径 | 职责 |
| --- | --- |
| `ALB/` | 0.4 稳定包代码，普通用户从根 facade 调用；实现按 contracts、core、config、physics、control、dynamics、surrogate、systems、infrastructure 和 workflows 分层。 |
| `tests/` | 唯一 pytest 收集树；包含单元、集成、精确回归和工程验证。 |
| `tools/` | benchmarks、diagnostics、docs、manual、migrations、reference 和 validation 工具。 |
| `refs/` | 不可覆盖的行为参考、固定输入和历史回归资产。 |
| `docs/` | 稳定说明、公共文档站点源码、生成式 API 参考、当前状态、迁移资料、run 规则和维护文档；站点输出 `site/` 不跟踪。 |
| `scripts/` | 仓库维护脚本；代码注释和 CLI help 使用英文。 |
| `paper_config/` | 仍由本项目跟踪的稳定论文调用配置资产，不存放论文任务运行状态。 |
| `test/` | 从旧测试树保留的图件和轻量配置；不在 `pyproject.toml` 的 pytest `testpaths` 中。 |
| `pyproject.toml` | Python 版本、核心依赖、领域 extras、CLI、构建和测试配置。 |
| `AGENTS.md` | 代理环境、编码、文档边界和远程操作规则。 |

## 首读顺序

1. `AGENTS.md`：确认环境、编码、变更边界和远程规则。
2. `docs/daily_maintenance/daily_doc_update_index.md`：编辑维护文档前确认其角色。
3. `docs/current_state.md`：恢复当前发布状态、验证结论和风险。
4. `docs/alb_package_overview.md`：修改 package module 或 public interface 前查看模块归属。
5. `docs/api/README.md`：查询根公开类、函数、输入输出和示例，或维护自动 API 文档时使用。
6. `docs/interface_architecture.md`：定义接口、移动模块或接入组件前确认依赖方向和生命周期。
7. `docs/next_interface_development_plan.md`：实施下一阶段用户构建、轴承原生生命周期、coupling、recorder 或 Signal 替换前确认目标和验收边界。
8. `docs/adr/README.md`：查看公共版本、`step()`、失败封锁、recorder、observer 和单位适配的 Accepted ADR。
9. `docs/migrations/0.2.0.md`：迁移 0.1 import、配置、pickle 或外部调用时使用。
10. `docs/file_classification.md`：整理、归档或清理文件前使用。
11. `docs/run_index.md`：需要 run 编号、路径或 current-status 所有权时使用。
12. `docs/remote_workstation_connection.md`：远程连接、Task Scheduler、runner 或 monitor 操作时使用。

ALBNN 活跃工作转向以下兄弟项目文档：

- `../SURROGATE_TRAIN/docs/current_runtime_status.md`：当前 run、日志和下一步。
- `../SURROGATE_TRAIN/docs/albnn_training_brief.md`：稳定训练流程和数据契约。
- `../SURROGATE_TRAIN/docs/albnn_training_log.md`：已完成事件和耐久结论。

论文活跃任务状态转向 `F:/BaiduSyncdisk/博士论文/PAPER_WORK/docs/current_task_status.md`。

## 开发和验证入口

默认环境：

```powershell
E:/Anaconda2023/envs/ALB/python.exe
```

稳定验证入口：

```powershell
E:/Anaconda2023/envs/ALB/python.exe -m pytest --collect-only
E:/Anaconda2023/envs/ALB/python.exe -m pytest
E:/Anaconda2023/envs/ALB/python.exe -m pytest tests/regression/api/test_review_fixes_0_4_2_reference.py -q
E:/Anaconda2023/envs/ALB/python.exe tools/validation/run_layered_mypy.py
E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_public_api_reference.py --check
E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_bearing_config_reference.py --check
E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_namespace_reference.py --check
E:/Anaconda2023/envs/ALB/python.exe -m mkdocs build --strict
E:/Anaconda2023/envs/ALB/python.exe -m tools.validation.run_release_acceptance_0_4_2 --candidate HEAD
```

分层类型检查对稳定边界执行 strict mypy，并要求其余安装源码不扩大已记录诊断
基线。0.4.2 正式发布验收从固定 SHA 的 detached worktree 执行数值合同、完整
测试、双 wheel、资源门禁、隔离安装和外部消费者 smoke；实时结论与候选指针见
`docs/current_state.md`。

## 跨项目与文件边界

- 训练、采样、论文脚本和外部实时日志不得写入 ALB_MAIN 当前状态文档。
- `SURROGATE_TRAIN` 与 `PAPER_WORK` 的 0.2.0 迁移必须在各自项目独立提交；本仓库只保留只读审计和目标映射。
- 原始 `.csv`、`.json`、`.log`、`.pth`、`.pkl` 和图件不会因文档整理而删除。
- `outputs/`、`dist/`、`build/`、缓存和隔离安装目录是生成物，不构成稳定源码边界。
- 人类可读维护文档使用中文；源码注释、docstring、CLI help 和生成脚本注释使用英文。
