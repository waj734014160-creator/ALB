# ALB 与 ALBNN 快速使用手册

## 文档角色

- 角色：稳定用户操作手册。
- 目的：说明如何在 `ALB_MAIN` 中快速构建默认 ALB 模型、加载迁移后的 ALBNN model package，并按需把代理模型接入 ALB shell。
- 允许更新：稳定 API 用法、最小示例、推荐导入路径、常见输入输出契约和排错提示。
- 禁止更新：活跃训练进度、单次 run 指标、远程任务 PID、原始日志正文和临时实验结论。
- 更新时机：ALB / ALBNN 构建 API、配置契约或推荐 quickstart 流程变化时。
- 事实来源 / 相关文档：
  `docs/daily_maintenance/daily_doc_update_index.md`、
  `docs/alb_package_overview.md`、
  `docs/interface_architecture.md`、
  `../SURROGATE_TRAIN/docs/albnn_training_brief.md`。

本文使用 0.3.0 的显式 namespace。旧 `ALB.alb` 和 `ALB.nn` 已删除；不要把旧 import 示例复制到新脚本。

## 环境准备

```powershell
E:/Anaconda2023/envs/ALB/python.exe -c "import ALB; print(ALB.__version__, ALB.__file__)"
```

源码环境可安装全部运行时能力：

```powershell
E:/Anaconda2023/envs/ALB/python.exe -m pip install -e ".[all]"
```

如果从兄弟项目运行，应安装 wheel/editable 包，或把 `G:/ALB_PROJECTS/ALB_MAIN` 明确放入 `PYTHONPATH`。不要复制 `ALB/` 目录。

## 以严格轴承端口运行默认 ALB

推荐把当前配置包装为带 `unit_system` 和 `control_mode` 的 envelope，再由公开 builder 直接得到运行时；普通用户不需要创建 `BearingBlock`：

```python
import numpy as np

from ALB import UnitSystem
from ALB.config import NodimALBConfig, current_config_envelope
from ALB.contracts import BearingInput
from ALB.systems.alb import build_alb

envelope = current_config_envelope(NodimALBConfig(node_link=0))
bearing = build_alb(envelope)
bearing.init()

request = BearingInput(
    displacement=np.array([0.05, 0.00]),
    velocity=np.array([0.00, 0.00]),
    time=0.0,
    unit_system=UnitSystem.NONDIMENSIONAL,
)
response = bearing.step(request)
force = response.force
```

`step()` 等价于 `input()`、`evaluate()`、`output()`，但不提交物理时步。需要检查生命周期时可显式拆开：

```python
bearing.input(request)
bearing.evaluate()
response = bearing.output()
```

`input()` 后、`evaluate()` 前调用 `output()` 会抛出 `RuntimeError`。`output()` 不求解，也不推进状态。`build_alb_from_file()` 位于 `ALB.workflows`，只接受 0.3 envelope；旧 JSON5 必须先用 `alb-migrate-config` 另存迁移。

`NodimALBConfig()` 保留冻结的默认物理和数值参数。轻量 smoke 可按需从 `ALB.config.film` 和 `ALB.config.hydraulics` 构建更小网格，但改变网格会改变物理离散，不应替代正式验证配置。

## 谐波线性轴承

谐波实现使用同一个端口，并额外提供正式系数能力：

```python
from ALB.systems.alb import alb_harmonic_linear

bearing = alb_harmonic_linear(node_link=0)
bearing.init()

K = bearing.K
C = bearing.C
G_xv = bearing.G_xv
```

构建参数以 `ALB.systems.alb.harmonic.alb_harmonic_linear` 的签名为准。`K`、`C` 和复数 `G_xv` 均返回副本。

## 迁移旧 ALBNN artifacts

旧 `best_albnn.pth`、`scaler_X.pkl`、`scaler_y.pkl` 不能直接视为 0.2 package。先复制到新的 versioned package；默认不覆盖任何文件：

```powershell
alb-migrate-surrogate `
  G:/path/to/best_albnn.pth `
  G:/path/to/scaler_X.pkl `
  G:/path/to/scaler_y.pkl `
  G:/path/to/model_package_0_2 `
  --metadata G:/path/to/metadata.json
```

等价源码入口是：

```powershell
E:/Anaconda2023/envs/ALB/python.exe tools/migrations/migrate_surrogate_0_2.py --help
```

生成目录包含 `manifest.json`、`model.pt`、`input_scaler.pkl`、`output_scaler.pkl` 和 `metadata.json`，manifest 记录每个 artifact 的 SHA-256。迁移是结构和完整性转换，不会证明旧模型在新调用处语义正确；仍需核对输入列、feature set、scaler 和 target transform。

## 加载并调用 ALBNN package

scaler 使用 pickle。只有 package 来源可信时才显式允许加载：

```python
import pandas as pd

from ALB.surrogate.package import load_albnn_package

net = load_albnn_package(
    r"G:/path/to/model_package_0_2",
    trust_pickle=True,
)

x = pd.DataFrame(
    [{
        "ex": 0.05,
        "ey": 0.00,
        "vx": 0.00,
        "vy": 0.00,
        "sx": 0.00,
        "sy": 0.00,
        "lambda_value": 0.7384145233,
        "beta_nondim": 0.1083715596,
        "lr": 0.75,
        "cq0": 4.5417787734,
        "cq1": 0.0411235398,
        "cq2": 0.0028973273,
    }]
)
force_nondim = net.predict(x, nodim=True)
```

上例是基础 12 输入契约：

```text
ex, ey, vx, vy, sx, sy, lambda_value, beta_nondim, lr, cq0, cq1, cq2
```

输出通常为 `fx, fy`。真正列顺序和派生特征以 package `metadata.json` 为准；调用前检查 `net.input_cols`。不同 feature set 或 expert/residual package 不能只靠列数判断兼容。

## 接入 ALB shell

只有经过 shell-agent smoke 的 model package 才应替换 pad force core：

```python
from ALB.config.surrogate import ALBNetConfig
from ALB.config.system import NodimALBConfig
from ALB.surrogate.package import open_model_package
from ALB.systems.alb import nodim_alb
from ALB.systems.alb.assembly import nn_agent

package = open_model_package(r"G:/path/to/model_package_0_2")
model_config = ALBNetConfig(
    model=str(package.model),
    scaler_X=str(package.input_scaler),
    scaler_y=str(package.output_scaler),
    metadata=str(package.metadata),
)

physical_shell = nodim_alb(alb_config=NodimALBConfig())
alb_with_nn = nn_agent(physical_shell, model_config)
```

`nn_agent` 是明确 assembly 子模块中的集成函数，不在 package 根重新导出。组合结果已经原生满足
`BearingRuntimeProtocol`，不再需要用户额外创建 `BearingBlock`；仍应使用模型训练条件内的固定
样本比较 `fx, fy`。

## 接入转子耦合与显式历史

新 coupling 使用 `CoupledBearingBinding` 明确节点、单位 adapter 和 direct-spool provider。
普通同量纲轴承的最小形式如下：

```python
from ALB.dynamics import CoupledBearingBinding, RsRotorBearingCouple

binding = CoupledBearingBinding(bearing=bearing, node_link=0)
coupling = RsRotorBearingCouple(rotor, time_grid, binding)
coupling.init()
result = coupling.advance(step_context)
```

若 bearing 是 direct-spool 类型，binding 必须注入
`SpoolCommandProviderProtocol`；缺失时构造立即失败，不会默认为零阀芯。若 rotor 与 bearing
单位不同，必须注入带完整 `Sx/St/Sv/Sf/Sp` 的 `BearingUnitAdapter`。

轴承自身默认只保存当前不可变结果。需要时间历史时由 coupling 注入 recorder：

```python
from ALB.dynamics import CouplingRuntimeDependencies
from ALB.infrastructure import InMemoryResultRecorder

recorder = InMemoryResultRecorder()
dependencies = CouplingRuntimeDependencies(
    run_id="case-001",
    recorder=recorder,
)
coupling = RsRotorBearingCouple(
    rotor,
    time_grid,
    binding,
    dependencies=dependencies,
)
```

recorder 在物理步提交后执行。记录失败不会重复推进 rotor/bearing；默认阻止下一步，调用
`coupling.retry_pending_record()` 只重试记录。GUI、日志或监控使用
`StepObserverProtocol`，observer 异常默认隔离为诊断信息。

## 常见问题

- `No module named ALB.alb` 或 `ALB.nn`：仍在使用 0.1 import；查看 `docs/migrations/0.2.0_import_map.json`。
- `ALBNN input is missing columns`：DataFrame 缺少 metadata 声明的基础或派生列。
- manifest digest mismatch：package 中至少一个 artifact 已改变；不要绕过校验，重新确认来源并迁移。
- `PermissionError` 提示 pickle trust：只在确认 artifact 来源可信后传入 `trust_pickle=True`。
- checkpoint 可加载但预测异常：检查 checkpoint、两个 scaler、metadata、feature set 和 target transform 是否来自同一训练 run。
- 单位制不匹配：`BearingInput.unit_system` 必须与 block 一致；通过显式尺度/adapter 转换，不要修改标签掩盖不一致。
- `output()` 抛出 `RuntimeError`：当前输入尚未执行对应的 `evaluate()`、`solve()`、`compute_command()` 或 `advance()`。
