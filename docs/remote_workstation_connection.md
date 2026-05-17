# 远程工作站连接与操作手册

## 文档角色

- 角色：稳定远程操作手册。
- 目的：保存可复用的远程连接、Task Scheduler、SSH、runner 和 monitor 机制。
- 允许更新：连接事实、稳定命令模式、wrapper 归属、凭据处理规则和可复用远程操作经验。
- 禁止更新：当前任务进度、PID、最新 loss、活跃 ETA 和单次 run 指标。
- 更新节奏：远程机制、路径、wrapper 或凭据处理规则变化时更新。
- 事实来源 / 相关文档：
  `docs/daily_maintenance/daily_doc_update_index.md`,
  `../SURROGATE_TRAIN/docs/current_runtime_status.md`,
  `../SURROGATE_TRAIN/docs/albnn_training_brief.md`。

本文只保存稳定、非密钥的连接事实和经过验证的远程工作流。实时任务名、PID、ETA、当前模型名和日志尾部不写入本文，应放在 `../SURROGATE_TRAIN/docs/current_runtime_status.md`。

## 远程端点

主远程工作站：

- Hostname: `desktop-1pvi7rp`
- LAN IP: `192.168.3.90`
- ZeroTier IP: `10.182.216.22`
- Username: `desktop-1pvi7rp\workstationg`
- Local SSH key: `C:/Users/73401/.ssh/re_alb_desktop_1pvi7rp_ed25519`
- Remote work directory: `F:/GWJ/20260507-train`
- Remote output directory: `F:/GWJ/20260507-train/outputs`
- 已验证 ZeroTier 端口：`SSH 22`, `SMB 445`, `RPC 135`
- 最近一次检查未开放：`WinRM 5985`, `RDP 3389`

64-core 工作站：

- Hostname: `AMD64`
- ZeroTier IP: `10.182.216.30`
- Username: `amd64\amd64-0`
- Local SSH key: `C:/Users/73401/.ssh/alb_64core_zt_10_182_216_30_ed25519`
- Candidate remote work directory: `G:/GWJ/20260512-train-thermal`
- ALB Python environment: `G:/GWJ/envs/ALB/python.exe`
- System Python also available: `E:/Program Files/Python312/python.exe`
- 硬件：AMD Ryzen Threadripper 7980X，64 cores / 128 logical processors，约 256GB RAM。
- 2026-05-12 已验证：ZeroTier `SSH 22`。
- 2026-05-12 已验证 ALB 环境依赖：
  Python 3.10.13，`numpy`、`pandas`、`scipy`、`tqdm`、`matplotlib`、`skfem` 可用。该 ALB 环境未安装 `sklearn` 和 `torch`，因此优先用于 ALB 样本生成；训练需要另行安装包或使用单独训练环境。

## 连接检查

不在同一 LAN 时优先使用 ZeroTier IP：

```powershell
Test-Connection -ComputerName 10.182.216.22 -Count 2 -Quiet
Test-NetConnection -ComputerName 10.182.216.22 -Port 22
ssh-keyscan -T 8 -p 22 10.182.216.22
```

确认主机身份：

```powershell
ssh -i C:/Users/73401/.ssh/re_alb_desktop_1pvi7rp_ed25519 desktop-1pvi7rp\workstationg@10.182.216.22 hostname
ssh -i C:/Users/73401/.ssh/re_alb_desktop_1pvi7rp_ed25519 desktop-1pvi7rp\workstationg@10.182.216.22 whoami
```

预期结果：

```text
DESKTOP-1PVI7RP
desktop-1pvi7rp\workstationg
```

## 远程 PowerShell

远程 SSH 默认 shell 表现更接近 `cmd`，直接发送 PowerShell pipeline 可能被拆分。多步骤 PowerShell 检查应在本地编码后发送：

```powershell
$remoteScript = @'
Get-ChildItem F:/GWJ/20260507-train/outputs
'@
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($remoteScript))
ssh -i C:/Users/73401/.ssh/re_alb_desktop_1pvi7rp_ed25519 desktop-1pvi7rp\workstationg@10.182.216.22 "powershell -NoProfile -EncodedCommand $encoded"
```

## 长任务规则

不要依赖 SSH 会话内的 `Start-Process` 来启动长时间训练任务。测试中，SSH 断开后子进程不能稳定存活。

持久化训练工作流：

1. 在 `F:/GWJ/20260507-train` 写入 `.ps1` runner。
2. 使用 Windows Task Scheduler 启动。
3. 用 `schtasks /Query` 检查任务状态。
4. 查看 `F:/GWJ/20260507-train/outputs/.../reports/logs` 下的日志。

优先使用本地 wrapper：

```powershell
E:/Anaconda2023/envs/ALB/python.exe ../SURROGATE_TRAIN/run/remote/remote_job.py launch --config ../SURROGATE_TRAIN/run/remote/configs/<job>.json
E:/Anaconda2023/envs/ALB/python.exe ../SURROGATE_TRAIN/run/remote/remote_job.py monitor --config ../SURROGATE_TRAIN/run/remote/configs/<job>.json
E:/Anaconda2023/envs/ALB/python.exe ../SURROGATE_TRAIN/run/remote/remote_job.py queue --config ../SURROGATE_TRAIN/run/remote/configs/<job>.json
E:/Anaconda2023/envs/ALB/python.exe ../SURROGATE_TRAIN/run/remote/remote_queue_albnn_activation_sweep.py --config ../SURROGATE_TRAIN/run/remote/configs/<queue>.json
E:/Anaconda2023/envs/ALB/python.exe ../SURROGATE_TRAIN/run/remote/remote_start_albnn_train.py
E:/Anaconda2023/envs/ALB/python.exe ../SURROGATE_TRAIN/run/remote/remote_query_albnn_status.py
E:/Anaconda2023/envs/ALB/python.exe ../SURROGATE_TRAIN/run/remote/remote_monitor_job.py --task-name <task> --process-match <needle>
```

稳定实现维护在 `ALB.remote`：`job`、`albnn_queue`、`albnn_start`、`albnn_status`、`monitor` 和 `transport`。`SURROGATE_TRAIN/run/remote` 下的脚本是兼容入口，用于保持旧命令和 JSON queue config 可用。

新建非训练远程任务时，优先使用配置驱动的通用 wrapper：

```powershell
E:/Anaconda2023/envs/ALB/python.exe ../SURROGATE_TRAIN/run/remote/remote_job.py launch --config <json>
E:/Anaconda2023/envs/ALB/python.exe ../SURROGATE_TRAIN/run/remote/remote_job.py monitor --config <json>
E:/Anaconda2023/envs/ALB/python.exe ../SURROGATE_TRAIN/run/remote/remote_job.py queue --config <json>
```

JSON schema 的职责边界：

- `profile`：连接设置。
- `uploads`：需要复制的文件。
- `job`：计划任务 runner 命令和日志。
- `monitor`：状态检查输入。
- `queue.jobs[*].wait_for`：顺序任务的等待条件。

生成的 runner 使用共享日志字段：`START_TIME`、`TASK`、`WORK`、`COMMAND`、`STDOUT`、`STDERR`、`END_TIME`、`EXIT_CODE`。同一 monitor API 可检查 Task Scheduler 状态、PID/process 状态、metadata、CSV 输出和日志尾部。

默认启动策略：远程 ALBNN training 启动后也要启动本地 monitoring。优先使用 JSON queue wrapper，因为它能恢复活跃任务、轮询状态，并把 `status.json`、`status.jsonl` 和日志尾部同步到配置的 queue output path。若直接用 start wrapper 启动，应立即启动对应 queue monitor。

训练启动前置检查：远程 start wrapper 会确认配置的 train/validation CSV 存在且非空，然后才创建 Task Scheduler run。对于 generation-to-training watcher，还必须用 split 成功、train/validation CSV 存在、split summary 存在、行数非零、train/validation 输入无重叠来 gate queue launch。不要只因为 generation metadata 达到 attempted row count 就启动训练队列。

非训练长任务如样本生成，应使用 `remote_job.py` 或通用 monitor wrapper，避免临时 SSH 状态片段。它通过短 PowerShell 命令检查 Task Scheduler、PID 或匹配进程、metadata 进度、CSV/log 时间戳和 ETA。

AMD64 上的非训练 solver 任务，如 ALB 样本生成或 finite-difference label evaluation，应通过 `remote_job.py` 和 Task Scheduler 使用 `G:/GWJ/envs/ALB/python.exe`。数值库保持单线程，Python 进程使用进程并行，例如 `pooln=60`：

```text
OMP_NUM_THREADS=1
MKL_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
NUMEXPR_NUM_THREADS=1
```

此模式用于 solver/sampling 工作。AMD64 ALB 环境已验证 solver 依赖，例如 `scikit-fem`，但未单独检查前不要假设它是 torch training 环境。

通用一次性 monitor 示例：

```powershell
E:/Anaconda2023/envs/ALB/python.exe ../SURROGATE_TRAIN/run/remote/remote_monitor_job.py `
  --task-name <task-name> `
  --process-match <stable-commandline-needle> `
  --metadata <remote-metadata-json> `
  --csv <remote-output-csv> `
  --log stdout=<remote-stdout-log> `
  --log stderr=<remote-stderr-log>
```

## ALBNN 任务指针

当前 ALBNN 数据、模型、任务和采样经验属于 `../SURROGATE_TRAIN/docs/albnn_training_brief.md`；详细日期历史属于 `../SURROGATE_TRAIN/docs/albnn_training_log.md`。本文只记录稳定远程操作机制和帮助操作者找到活跃任务的短指针。

活跃远程 ALBNN 工作流指针：

- 实时状态缓冲区：`../SURROGATE_TRAIN/docs/current_runtime_status.md`
- ALBNN 首读稳定说明：`../SURROGATE_TRAIN/docs/albnn_training_brief.md`

不要在本文保存活跃任务名、PID、ETA、queue root 或当前模型名。实时状态写入 `current_runtime_status.md`，日期历史写入 `albnn_training_log.md`。

## PowerShell runner 注意事项

PowerShell 5.1 在 `$ErrorActionPreference = 'Stop'` 与 `2>&1 | Tee-Object` 组合时，可能把 native program 的 `stderr` 转成 terminating error。这会导致 Task Scheduler 报告 `LAST_RESULT=1`，即使 Python 进程只是打印了 solver warning。长 ALB sampling/training runner 应避免该模式。

推荐规则：

- 让 Task Scheduler 承担长时间顶层 runner。
- 不要从 SSH 会话中直接用 `Start-Process` 启动长任务。
- 不要在定时 watcher 中使用 `codex exec` 或其他 Codex CLI agent 做远程状态检查；这会周期性消耗 Codex 配额，只应保留给用户显式要求的一次性分析。
- 远程 launcher 日志默认保持结构化和英文。`schtasks.exe` 等 Windows native 工具可能通过 SSH 输出本地化文本；混合 PowerShell CLIXML、UTF-8 和 CP936/GBK 时可能产生替换字符，并曾触发本地 Python `UnicodeEncodeError`。正常日志中只暴露结构化信息，原始 native 输出只放在显式 verbose/debug 模式。
- 可能打印远程输出的 Python wrapper，应把 `stdout` 和 `stderr` 配置为 UTF-8 并使用 replacement handling；一个 wrapper 启动另一个 wrapper 时设置 `PYTHONIOENCODING=utf-8`。
- 计划任务控制器需要子进程时，将 stdout 和 stderr 分别重定向到文件，并显式检查子进程 exit code。
- 长 watcher/controller 的 Task Scheduler `ExecutionTimeLimit` 应显式设为至少覆盖 runner deadline。默认可能是 `PT72H`，会在多日依赖链完成前停止健康 watcher。
- 不依赖 `Tee-Object` 维护 native 长时间 Python 日志。
- 统计 CSV 行数时使用 `switch -File` 这类行迭代方式，不使用 `Get-Content -ReadCount ... | Measure-Object -Line`，因为 chunked reads 可能少计行。

事故记录：

- 2026-05-08 targeted residual sampling shards 曾使用 15 个并发计划任务和 `2>&1 | Tee-Object`。许多 shard task 在 `iter of filmsystem is max` 等 solver 消息后报告 `LAST_RESULT=1`。替代 runner 使用计划任务 wave controller、较低并发和显式日志文件。
- 2026-05-08 旧 `codex_cli_boundary_watch_20260508.ps1` monitor 周期性运行 `codex exec` 来检查 `RE_ALB_boundary_sample_20260508`，会快速消耗 Codex 配额。未来远程监控必须使用直接 PowerShell/Python 状态脚本，除非用户明确要求一次性 Codex CLI review。

## 路径查找

本文档本地路径：

```text
G:/ALB_PROJECTS/ALB_MAIN/docs/remote_workstation_connection.md
```

从 `G:/ALB_PROJECTS` 查找本文：

```powershell
rg --files | rg "remote_workstation_connection.md"
```

查找远程训练日志：

```powershell
$remoteScript = @'
Get-ChildItem F:/GWJ/20260507-train/outputs -Recurse -File -Filter *.log |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 30 FullName,LastWriteTime,Length
'@
```

不要把密码、私钥、恢复码、API key 或一次性 token 写入本文。
