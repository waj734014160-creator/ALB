# ALB_PROJECTS 运行索引

## 文档角色

- 角色：ALB_PROJECTS 全局运行编号与路径规则索引。
- 目的：定义项目级 run number、run ID 格式、主要路径族，以及当前状态文档的归属。
- 允许更新：运行编号规则、项目前缀映射、run ID 格式、规范路径指针、归档指针规则，以及帮助定位当前状态文档的简短说明。
- 禁止更新：原始日志、详细进度尾部、完整指标报告、清理操作、破坏性归档决策。
- 更新时机：运行编号规则、项目前缀、当前状态归属、路径族或归档指针规则发生变化时。
- 事实来源 / 相关文档：
  `docs/daily_maintenance/daily_doc_update_index.md`,
  `docs/file_classification.md`,
  `../SURROGATE_TRAIN/docs/file_classification.md`,
  `../SURROGATE_TRAIN/docs/current_runtime_status.md`。

本文档是 `G:/ALB_PROJECTS` 工作区的全局运行规则索引。它不是实时监控日志，也不应复制原始证据。当前活跃运行的状态、路径、进度和下一步操作归属于对应项目的结构化 current-status 文档；对于 `SURROGATE_TRAIN`，当前入口是：

```text
../SURROGATE_TRAIN/docs/current_runtime_status.md
```

## 运行编号规则

- 每个项目维护自己的 run number 序列。
- run number 使用项目前缀加四位数字，例如 `S0001` 或 `A0001`。
- 不使用裸数字目录名，例如 `0001`，因为它容易和日期、样本数或随机种子混淆。
- 新 run ID 使用项目内 run number 前置格式：

```text
<project_run_no>_<domain>_<purpose>_<size-or-key>_<date>
```

- 新启动配置建议记录顶层 `run_id`。任务名、输出目录和日志文件名如果工具支持，也应包含或能清楚推导出同一个 `run_id`。
- 目标规则是后续生成 metadata 时也写入 `run_id`。在所有代码都支持之前，配置文件和结构化 current-status 条目共同构成活跃运行的映射。

示例：

```text
S0001_fd_full_jacobian_20000_h1em03_20260517
S0002_queue_force3_gelu_minmax_p500_20260509
A0001_remote_helper_reference_v1_20260517
```

## 项目前缀

| 前缀 | 项目 | 分配规则 |
| --- | --- | --- |
| `A` | `ALB_MAIN` | 稳定 package helper、参考输出、ALB_MAIN 自有证据。 |
| `S` | `SURROGATE_TRAIN` | ALBNN 采样、训练、模型测试、队列配置和实验输出。 |
| `P` | `PARAM_SCAN` | 参数扫描任务和生成证据包。 |
| `D` | `DATA_POSTPROCESS` | 产生持久输出的数据后处理任务。 |
| `V` | `VALIDATION` | 正式验证运行和选定验证输出。 |
| `X` | `ARTIFACTS_ARCHIVE` | 仅用于归档自有 bundle；默认不分配新的实验运行。 |

分配下一个编号时，先检查所属项目的 current-status 文档、近期配置文件和输出目录。运行仍活跃时，编号和当前定位信息应维护在 current-status 中。

## 当前状态规则

agent 在启动、恢复、监控或归档活跃工作之前，应先读取当前状态文档：

```text
../SURROGATE_TRAIN/docs/current_runtime_status.md
```

每个活跃运行应保留稳定的结构化块，至少包含：

```text
run_no, run_id, state, config, output root, remote root, task name, monitor command,
latest check, progress, evidence/log pointers, current issue, next action
```

current-status 块替代单独的 JSONL locator 文件。它可以随着事实变化被重写；详细原始日志和完成后的长期历史仍归属于原始 artifact 或相应的 chronological log。

## 路径规则

新运行优先使用所属项目内的这些路径族：

```text
run/remote/configs/<run_id>.json
outputs/<domain>/<run_id>/
outputs/archive/<run_id>/   # 仅在确认归档后使用
```

`outputs/<domain>/<run_id>/` 用于 CSV、JSON metadata、图、摘要和其它结果 artifact。

日志不再由本文档统一管理，也不要求迁移到统一的 `logs/` 目录。日志应保留在 launcher、queue wrapper、remote runner 或 run output bundle 实际写入的位置。current-status 块只需要记录当前诊断所需的日志指针。

`outputs/archive/<run_id>/` 只在任务完成且用户确认该运行已不活跃或已废弃后使用。对于 active、running、stopped、failed-but-not-archived 的运行，不要在活跃 locator 块中写入未来归档路径，除非归档已经真实存在。

## 项目归属

- `SURROGATE_TRAIN` 负责 ALBNN 采样、训练、模型测试、队列配置、运行证据和实验输出。
- `ALB_MAIN` 负责可复用 package 代码、稳定远程 helper、package 回归参考、全局文档和本文档。
- 其它子项目在创建长时间任务、生成证据包或归档运行时，应使用各自项目的前缀。
