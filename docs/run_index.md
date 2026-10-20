# ALB_PROJECTS 运行索引

相关文件：
  `docs/daily_maintenance/daily_doc_update_index.md`,
  `docs/current_state.md`,
  `docs/file_classification.md`,
  `../SURROGATE_TRAIN/docs/file_classification.md`,
  `../SURROGATE_TRAIN/docs/current_runtime_status.md`。

本文列出 `G:/ALB_PROJECTS` 工作区的运行编号和路径。`SURROGATE_TRAIN` 的任务状态、输出路径和进度记录可从以下文件查找：

```text
../SURROGATE_TRAIN/docs/current_runtime_status.md
```

`ALB_MAIN/docs/current_state.md` 提供 ALB_MAIN 的开发记录、验证、风险和下一步信息。

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

涉及 ALB_MAIN 当前包开发或迁移工作时，应先读取：

```text
docs/current_state.md
```

agent 在启动、恢复、监控或归档 SURROGATE_TRAIN 活跃工作之前，应先读取：

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

日志路径以 launcher、queue wrapper、remote runner 或 run output bundle 的实际输出为准，可在任务记录中附上诊断所需的日志指针。

`outputs/archive/<run_id>/` 只在任务完成且用户确认该运行已不活跃或已废弃后使用。对于 active、running、stopped、failed-but-not-archived 的运行，不要在活跃 locator 块中写入未来归档路径，除非归档已经真实存在。

## 论文任务外部路径

论文任务使用外部工作区 `F:/BaiduSyncdisk/博士论文/PAPER_WORK`，不分配 `ALB_PROJECTS` 项目前缀 run number。该工作区的路径族、命名、current-status 和证据保留规则由 `F:/BaiduSyncdisk/博士论文/PAPER_WORK/AGENTS.md` 维护；本文只保留该外部入口指针。

## 项目归属

- `SURROGATE_TRAIN` 负责 ALBNN 采样、训练、模型测试、队列配置、运行证据和实验输出。
- `ALB_MAIN` 负责可复用 package 代码、稳定远程 helper、package 回归参考、全局文档和本文档。
- 其它子项目在创建长时间任务、生成证据包或归档运行时，应使用各自项目的前缀。


## 模型名称
模型名称需要加入数字前缀，例如 `M0001`，以区分它们与 run ID, 分配规则为查看模型目录中是否已经存在编号，若存在则分配下一个编号。模型名称还需要尽量简短，最主要是包含核心信息，以及区别特征，例如
本次模型修改了损失权重和交叉项权重，那么模型名称可以包含 `fdw200_crossw2` 等关键信息。
