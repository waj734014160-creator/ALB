# 热记忆 MLP 代理

## 模型与状态契约

`ALB.surrogate.ThermalMemoryMLP` 在冻结的 M35 稳态网络上学习热历史的力修正。
输入是原始无量纲量，按 `ex, ey, vx, vy, sx, sy, lambda_value, beta_nondim,
lr, cq0, cq1, cq2` 排列；输出是无量纲总力 `fx, fy`。M35 固定物理族的
力尺度为 8400 N。速度的定义为位移偏心率对实际秒求导，再除以轴转角频率。
一个周期有多少采样点只决定时间离散精度，不定义记忆的长短。

每组潜在状态满足指数松弛更新，时间常数的单位为秒。四个固定 C4 坐标组
分别保存状态，共享编码器、时间常数和修正头。修正先转为无量纲力，再反旋转
并平均。修正头的平衡输出被显式扣除，默认配置下平衡记忆状态保留原 M35 预测。
M35 本身继续使用原有象限规范化；其归一化器与记忆分支的对称归一化器独立。

构造参数 `static_correction=True` 可额外启用 12→64→64→2 的当前工况修正
（隐藏宽度随 `hidden_size` 设置）。该分支同样按四组坐标计算、还原并平均，
用于学习基线已有的稳态拟合偏差。默认关闭，保持原有模型行为；模型包保存该开关。
开启时，平衡状态输出为 M35 加当前工况修正，动态记忆修正仍为零；
`reset()` 返回新的平衡记忆状态，不表示把全部输出恢复为原 M35。

原 M35 的象限分支在偏心坐标轴和原点存在总力旋转不一致的边界。冻结基线
保留此行为；四组记忆修正的等变性不能消除基线已有的误差。验收分别报告
基线、修正和总力的 C4 误差，坐标轴或原点未达标时明确记为失败，不宣称
全域总力严格旋转一致。

初版模型假设起始输入已建立稳态温场、轨迹内转速恒定，面向周期运动与平滑
工况变化。冷启动及运行中变速不属于本次训练范围。训练得到的有效时间域及
物理配置记录在模型包 metadata 中；模型是否可用于计算，以独立验收报告为准。

## 显式预测接口

```python
import torch
from ALB.surrogate import load_thermal_memory_package

model = load_thermal_memory_package("model_package", device="cuda")
model.eval()
# x0 and x1 are raw M35 inputs with shape [batch, 12].
with torch.no_grad():
    state = model.initialize(x0)
    force, next_state = model.predict_step(x1, 0.001, state)
    reset_state = model.reset(x0)
```

状态形状是 `[batch, 4, 64]`，应与模型保持相同设备和浮点类型。调用不修改
旧状态；上层程序自行决定何时提交 `next_state`。逐步接口要求正的 `dt`，
单位为秒。整段接口输入 `[batch, time, 12]`，首样本代表稳态初值时可使用
零时间增量；后续样本使用相邻实际时间之差。变步长时仍按真实时间更新。

此接口独立于 `Bearing` 和转子仿真 runtime。本轮不将热记忆包自动注册为
现有稳态代理的替代品。

## 数据、训练与验收

可复用的流程入口位于 `ALB.surrogate.training`：

- `thermal_memory_sampling`：轨迹级并行、轨迹内顺序求解、原子保存、物理时间
  步审计、绝对预算和进度记录。恢复时跳过完整轨迹，未完整轨迹从稳态重算。
- `thermal_memory_training`：数据门禁、冻结基线的 FP32 训练、截断反向传播、
  验证集选模及独立测试验收。
- `thermal_memory_workflow`：监控明确指定的远程任务、同步完整数据，通过
  门禁后衔接本地训练。该入口本身不创建远程计算任务。

训练记录 `Trajectory` 可附带 `quasisteady_force`，表示同一输入、时间、物理族
和初场下关闭热惯性的配对力。实验加载器必须核验这些配对条件，不能将不同
轨迹的准稳态力直接拼接。`fit_thermal_memory()` 的
`paired_memory_loss_weight` 监督“完整预测减去 `steady_force()`”与物理热差，
`paired_steady_loss_weight` 监督准稳态力与 `steady_force()`，后者要求开启
`static_correction`。两个权重均在 `training` 配置中设置，默认零，不改变原训练目标。
配对标签只允许放在训练组；验证集仍单独按总力误差选模。配对标签参与续训
身份校验，截断段和混合批次保持原来的等轨迹、按秒积分权重。

该分解避免当前工况修正吸收配对的热惯性差。推理时仍只需要工况输入、时间
步和显式记忆状态，不读取真实力或温度。若同一物理工况的一个时间步版本
参加训练，其他时间步版本只能作为同组诊断，不能称作独立泛化验证。

实验配置、冻结物理配置、采样输出、模型及评价报告归属兄弟项目
`SURROGATE_TRAIN`，当前运行状态统一见其 `docs/current_runtime_status.md`。
本次实验的评价目标由运行配置和验收实现共同固定，未执行或未通过的项目
保留明确结论。稳态误差、小样本物理探针或数据生成结束均不代表瞬态模型已通过验收。

## 统一总残差 LSTM 实验接口

`ALB.surrogate.thermal_residual_lstm` 提供 `ThermalResidualLSTM`，以及独立的
`save_thermal_residual_lstm_package()` / `load_thermal_residual_lstm_package()`。
模型类型是 `albnn_unified_residual_lstm`，不改变既有 `ThermalMemoryMLP` 包。
实际输出为 `M35(x_t) + readout(x_t,h_t)`；只有一个残差读出层，当前误差与
历史影响由同一目标学习。四组固定旋转坐标共享参数，原 M35 的轴线上对称性
限制仍然保留。

`variant="lstm_dt"` 将 `log1p(dt_s/time_reference_s)` 加入标准 LSTM 输入。
`variant="tlstm_dt"` 额外参考 Baytas et al. (KDD 2017) 的 cell 子空间时间折扣，
折扣为 `1/log(e+dt_s/time_reference_s)`。两个量纲尺度均写入包配置；时间参考值
和等方向残差尺度须只用训练集拟合。该方法并非热能方程积分，也不保证细分
时间步前后的输出严格一致。

初始化由当前输入学习 h/c，适用于训练数据的稳态初场；不代表任意初温冷启动。
状态是 `[batch,4,2,H]`，第三维依次为 h、c。`initialize/reset` 创建新状态，
`predict_step` 接收正的实际秒数并返回新状态；`predict_sequence` 的无状态首点
允许 `dt=0`，分块续算首点则使用与上一块末点之间的正时间间隔。调用者负责
提交状态；求解器试算或牛顿迭代不能误当作新的物理时间步连续推进。

`reset_force(x)` 表示每个样本重新初始化后的历史消融。它保留训练后的读出层，
所以不是原 M35、单独训练的无记忆基线或关闭热惯性的物理真值。
`baseline_force(x)` 才是冻结的原 M35 输出。

共享训练器支持模型自定义 `training_contract()`，将结构、时间尺度、初始化和
冻结基线计入恢复身份校验。没有此接口的旧模型沿用原校验结构，既有恢复文件
不因该扩展改变身份。本轮 LSTM 训练的配对损失权重为零，只监督总力残差。
