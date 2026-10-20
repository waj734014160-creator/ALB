# ALB_MAIN 项目概览

相关文件：
  `AGENTS.md`、
  `docs/daily_maintenance/daily_doc_update_index.md`、
  `docs/current_state.md`、
  `docs/alb_package_overview.md`、
  `docs/api/README.md`、
  `docs/interface_architecture.md`、
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

训练数据、模型 run 和队列记录可在 `SURROGATE_TRAIN` 查找，论文计算脚本和任务记录可在 `PAPER_WORK` 查找。外部项目安装或引用本包，避免复制 `ALB/` 源码。

## 主要目录

| 路径 | 职责 |
| --- | --- |
| `ALB/` | 0.4 稳定包代码，普通用户从根 facade 调用；实现按 contracts、core、config、physics、control、dynamics、surrogate、systems、infrastructure 和 workflows 分层。 |
| `tests/` | 唯一测试树；包含单元、集成、精确回归、工程验证，以及不参与收集的 `fixtures/legacy/` 历史资产。 |
| `tools/` | analysis、benchmarks、diagnostics、docs、hooks、manual、migrations、reference 和 validation 工具；入口及历史脚本边界见[工具索引](../tools/README.md)。 |
| `refs/` | 不可覆盖的行为参考、固定输入和历史回归资产。 |
| `docs/` | 稳定说明、公共文档站点源码、生成式 API 参考、当前状态、迁移资料、run 规则和维护文档；站点输出 `site/` 不跟踪。 |
| `.github/workflows/` | Python 兼容性、文档合同与 GitHub Pages 自动发布工作流。 |
| `scripts/` | 仓库维护脚本；代码注释和 CLI help 使用英文。 |
| `outputs/archive/` | 经授权整理的本地历史任务和分发包；归档仍 ignored，路径映射与摘要由 `docs/daily_maintenance/` 保存。 |
| `paper_config/` | 仍由本项目跟踪的稳定论文调用配置资产，不存放论文任务运行状态。 |
| `pyproject.toml` | Python 版本、核心依赖、领域 extras、CLI、构建和测试配置。 |
| `AGENTS.md` | 环境路径、编码、代码与操作约束。 |

## 按任务选择入口

路径与操作约束见 `AGENTS.md`；以下资料可按任务需要查找。

| 任务 | 阅读入口 |
| --- | --- |
| 当前开发、发布和风险 | `docs/current_state.md` |
| 查找文档或任务记录 | `docs/daily_maintenance/daily_doc_update_index.md` |
| public API、包级导出或跨模块边界 | `docs/alb_package_overview.md`、`docs/interface_architecture.md` |
| 用户示例和生成参考 | `docs/api/README.md`、`docs/alb_albnn_quickstart.md` |
| 数值算法、提交、recorder 或单位契约 | `docs/adr/README.md` 中适用决策 |
| 版本迁移 | `docs/migrations/` 中相应版本说明，当前开发接口包括 0.4.3、0.4.4、0.4.5、0.4.6 |
| 资产归属与清理 | `docs/file_classification.md` |
| run 编号与状态归属 | `docs/run_index.md` |
| 远程连接、启动和监控 | `docs/remote_workstation_connection.md` |

ALBNN 活跃工作转向以下兄弟项目文档：

- `../SURROGATE_TRAIN/docs/current_runtime_status.md`：当前 run、日志和下一步。
- `../SURROGATE_TRAIN/docs/albnn_training_brief.md`：稳定训练流程和数据契约。
- `../SURROGATE_TRAIN/docs/albnn_training_log.md`：已完成事件和耐久结论。

论文活跃任务状态转向 `F:/BaiduSyncdisk/博士论文/PAPER_WORK/docs/current_task_status.md`。

## 开发和验证入口

公共用户指南与 API Reference：<https://waj734014160-creator.github.io/ALB/>。发布工作流为 `.github/workflows/docs-pages.yml`；它在当前开发分支和 `main` 上先执行生成参考漂移检查、目标测试与严格 MkDocs 构建，再把可再生静态站点发布到公开 Pages 仓库的 `ALB/` 子目录。ALB 源仓库继续保持私有。

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
E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_simulation_config_reference.py --check
E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_namespace_reference.py --check
E:/Anaconda2023/envs/ALB/python.exe -m mkdocs build --strict
```

按改动选择相关验证，不将文档修正自动扩大为完整数值验收。四类生成参考的详细命令及文档目标测试见 `docs/api/README.md`。

分层类型检查对稳定边界执行 strict mypy，并要求其余安装源码不扩大已记录诊断
基线。0.4.2 正式发布验收从固定 SHA 的 detached worktree 执行数值合同、完整
测试、双 wheel、资源门禁、隔离安装和外部消费者 smoke；实时结论与候选指针见
`docs/current_state.md`。`run_release_acceptance_0_4_2` 只接受对应版本的候选，不能对其他开发版本的 `HEAD` 直接套用。新版本发布应先具备匹配版本的 manifest、测试映射和验收工具。

## 跨项目与文件边界

- 训练、采样和论文任务记录可从相应工作区的 `docs/` 和任务目录查找。
- 外部项目默认只读。用户明确授权跨项目修改时，在目标目录遵循其代理规则并分别验证；有 Git 的项目保留独立提交，无 Git 的项目使用其快照机制。历史 0.2.0 迁移报告不限制后续已授权工作。
- 原始 `.csv`、`.json`、`.log`、`.pth`、`.pkl` 和图件不会因文档整理而删除。
- `outputs/`、`dist/`、`build/`、缓存和隔离安装目录是生成物，不构成稳定源码边界。
- 人类可读维护文档使用中文；源码注释、docstring、CLI help 和生成脚本注释使用英文。
