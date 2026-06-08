# ALB 与 ALBNN 快速使用手册

## 文档角色

- 角色：稳定用户操作手册。
- 目的：说明如何在 `ALB_MAIN` 中快速构建默认 ALB 模型、加载已训练 ALBNN 模型，并把二者组合成使用神经网络力核心的 ALB shell。
- 允许更新：稳定 API 用法、最小示例、推荐导入路径、常见输入输出契约和排错提示。
- 禁止更新：活跃训练进度、单次 run 指标、远程任务 PID、原始日志正文和临时实验结论。
- 更新时机：ALB / ALBNN 构建 API、配置契约或推荐 quickstart 流程变化时。
- 事实来源 / 相关文档：
  `docs/daily_maintenance/daily_doc_update_index.md`、`docs/alb_package_overview.md`、`../SURROGATE_TRAIN/docs/albnn_training_brief.md`。

本文面向只想快速调用模型的用户。训练数据生成、远程训练队列和实验历史不放在本文；这些内容属于 `../SURROGATE_TRAIN/docs/albnn_training_brief.md` 和对应 run 记录。

## 环境准备

在 `G:/ALB_PROJECTS/ALB_MAIN` 下运行示例：

```powershell
E:/Anaconda2023/envs/ALB/python.exe -c "import ALB; print(ALB.__file__)"
```

如果在兄弟项目中运行，先把 `G:/ALB_PROJECTS/ALB_MAIN` 加入 `PYTHONPATH`，或使用已经安装本包的环境。

## 快速构建默认 ALB 模型

推荐先使用无量纲入口 `nodim_alb`。它不依赖已训练神经网络，也不需要模型文件：

```python
import numpy as np

from ALB.alb import nodim_alb
from ALB.config import NodimALBConfig

cfg = NodimALBConfig()
alb = nodim_alb(cfg)

alb.init()
alb.input(
    uxy=np.array([0.05, 0.00]),   # ex, ey
    uxyt=np.array([0.00, 0.00]),  # vx, vy
    t=0.0,
    sv=np.array([0.00, 0.00]),    # sx, sy
    nodim=True,
)
out = alb.output(nodim=True)
force = out["force"]
```

`NodimALBConfig()` 是真实默认配置，网格为 `nx=59, nz=39`，适合保留默认物理/数值契约。若只是做 import 或接口 smoke test，可以手动降低网格并使用静态伺服阀：

```python
import numpy as np

from ALB.alb import nodim_alb
from ALB.config import NodimALBConfig, NodimOrificeConfig, NodimPadConfig

cfg = NodimALBConfig(
    pad_config=NodimPadConfig(
        lambda_value=1.2,
        lr=1.0,
        nx=5,
        nz=3,
        coe=False,
        max_iter=3,
        error_set=1e-5,
    ),
    orifice_config=NodimOrificeConfig(
        position=np.array([[0.5, 0.5]]),
        cq0=0.2,
        cq1=1.0,
        cq2=0.1,
    ),
    servo="static",
)
alb = nodim_alb(cfg)
```

## 快速构建 ALBNN 模型

这里的“构建 ALBNN”通常指加载一个已经训练完成、可推理的 packaged model。一个完整 ALBNN 目录至少应包含：

- `best_albnn.pth`
- `scaler_X.pkl`
- `scaler_y.pkl`
- `metadata.json`（推荐，旧模型可能缺失）

加载示例：

```python
import numpy as np
import pandas as pd

from ALB.config import ALBNetConfig
from ALB.nn import albnn

model_dir = r"G:/ALB_PROJECTS/SURROGATE_TRAIN/models/<model_name>"

cfg = ALBNetConfig(
    model=f"{model_dir}/best_albnn.pth",
    scaler_X=f"{model_dir}/scaler_X.pkl",
    scaler_y=f"{model_dir}/scaler_y.pkl",
    metadata=f"{model_dir}/metadata.json",
    lambda_value=0.7384145233,
    beta_nondim=0.1083715596,
    lr=0.75,
    cq0=4.5417787734,
    cq1=0.0411235398,
    cq2=0.0028973273,
)
net = albnn(cfg)

x = pd.DataFrame(
    [{
        "ex": 0.05,
        "ey": 0.00,
        "vx": 0.00,
        "vy": 0.00,
        "sx": 0.00,
        "sy": 0.00,
        "lambda_value": cfg.lambda_value,
        "beta_nondim": cfg.beta_nondim,
        "lr": cfg.lr,
        "cq0": cfg.cq0,
        "cq1": cfg.cq1,
        "cq2": cfg.cq2,
    }]
)
force_nondim = net.predict(x, nodim=True)
```

也可以使用 `input` / `output` 风格：

```python
net.input(
    uxy=np.array([0.05, 0.00]),
    uxyt=np.array([0.00, 0.00]),
    sxy=np.array([0.00, 0.00]),
    nodim=True,
)
force_nondim = net.output(nodim=True)
```

如果只需要创建一个未训练的默认 MLP 结构用于调试，不要把它当作可用 ALBNN 力模型：

```python
from ALB.nn import Net

net = Net([12, 128, 128, 64, 2], activation="gelu")
```

## 把 ALBNN 接入 ALB shell

当前推荐的下游替换模式是保留 ALB shell，只把 pad force core 替换为神经网络 agent。旧式 `ALBNet` 包装入口是：

```python
from ALB.alb import nn_agent, nodim_alb
from ALB.config import ALBNetConfig, NodimALBConfig

alb = nodim_alb(NodimALBConfig())
albnet_config = ALBNetConfig(
    model=r"G:/ALB_PROJECTS/SURROGATE_TRAIN/models/<model_name>/best_albnn.pth",
    scaler_X=r"G:/ALB_PROJECTS/SURROGATE_TRAIN/models/<model_name>/scaler_X.pkl",
    scaler_y=r"G:/ALB_PROJECTS/SURROGATE_TRAIN/models/<model_name>/scaler_y.pkl",
    metadata=r"G:/ALB_PROJECTS/SURROGATE_TRAIN/models/<model_name>/metadata.json",
)
alb_with_nn = nn_agent(alb, albnet_config)
```

注意：`nn_agent` 目前走 legacy `ALBNet` 包装，适合已有 agent-style 模型。新的 12 列 thermal ALBNN packaged model 优先直接用 `ALB.nn.albnn(ALBNetConfig(...))` 做力预测；要做 ALB shell 内核替换时，应先确认该模型目录和 `ALBNetConfig` 字段与 `ALB.alb.ALBNNAgent` 预期一致。

## 输入输出契约

默认 thermal ALBNN 的 12 个输入列为：

```text
ex, ey, vx, vy, sx, sy, lambda_value, beta_nondim, lr, cq0, cq1, cq2
```

输出为：

```text
fx, fy
```

默认输出是无量纲力。调用 `predict(..., nodim=False)` 或 `output(nodim=False)` 时，`ALBNN` 会使用 `ALBNetConfig` 中的 `ps * l * r / 2` 转为有量纲力。

## 常见问题

- `ALBNN input is missing columns`：输入 DataFrame 缺少模型 metadata 声明的列。先检查 `net.input_cols`。
- `ALBNN scaled input is missing columns`：模型训练时启用了派生特征或 feature set，但当前 metadata / scaler / 输入列不匹配。优先检查模型目录中的 `metadata.json`。
- `best_albnn.pth` 能加载但预测不可信：未训练 MLP 或 scaler 与 checkpoint 不配套。必须同时使用同一模型目录下的 `best_albnn.pth`、`scaler_X.pkl`、`scaler_y.pkl` 和 `metadata.json`。
- `nodim_alb` 报 dimensional scale 错误：无量纲入口不接受 `c/r/l/ps/rho/miu/w` 这类有量纲尺度参数；需要有量纲 builder 时使用 `ALBConfig` 相关入口。
