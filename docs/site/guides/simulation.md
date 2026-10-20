# 转子-轴承仿真

仿真把一个 dimensional rotor、唯一节点挂载、载荷声明和历史策略冻结为 `SimulationConfig`。

!!! info "需要 dynamics extra"
    使用 ROSS 转子文件或动力学能力前安装 `re-alb[dynamics]`。仅构造自定义 `RotorProtocol` 实现时不应依赖内部 ROSS adapter 路径。

```python
mount = ALB.BearingMount(config=bearing_config, node=0)
history = ALB.HistoryPolicy(
    mode="memory",
    fields=("rotor_displacement", "bearing_force"),
    downsample=1,
)
simulation_config = ALB.SimulationConfig(
    rotor=rotor,
    mounts=(mount,),
    time_step=0.001,
    steps=100,
    loads=(
        {"type": "static", "node": 0, "force": [0.0, -1000.0]},
        {"type": "gravity", "acceleration": 9.80665},
    ),
    history=history,
)
result = ALB.build_simulation(simulation_config).run()
```

## 积分器与控制器采样

!!! warning "功能不完善"
    0.4.6 的 ROS2 积分器标记为功能不完善（实验性）：代理模型族未做数值收敛验证，
    不支持热模型轴承，外部阀芯 provider 通道只有一阶精度，冻结 Jacobian 没有自适应刷新。
    正式计算继续使用默认 `staggered`；ROS2 结果应先与 staggered 细步长解或独立参考交叉核对。详见 [0.4.6 迁移说明](../../migrations/0.4.6.md)。

缺省 `integrator="staggered"`：轴承力按上一提交状态计算、滞后一步，数值路径与
0.4.5 相同。`integrator="ros2"` 选择两级 Rosenbrock-W 积分器，在 stage 状态同步
计算轴承力，需要连续时间 `ALB.dynamics.RossRotor`：

```python
from ALB.dynamics import Ros2Options

simulation_config = ALB.SimulationConfig(
    rotor=rotor,
    mounts=(mount,),
    time_step=2.0e-5,
    steps=5000,
    integrator="ros2",
    ros2=Ros2Options(jacobian_refresh="control_period"),
)
```

ROS2 支持无热液膜、气膜、surrogate、子瓦只含无热液膜/气膜/固定阀芯 surrogate 的
`MultiPad` 和无热主动轴承；带热模型的轴承，以及含主动或外部阀芯子瓦的 `MultiPad`，
以 `ConfigurationError` 拒绝。`initial_rotor_state` 可对全部三种积分器给出完整初始
转子状态，例如静平衡状态；它与 `Ros2Options.jacobian_state` 都保存为浮点数元组。

### 预测-校正积分器（0.4.7）

`integrator="predictor_corrector"` 在保持轴承黑箱的前提下消除轴承力的一步滞后：
每步先预测界面力，再用“从已提交状态出发、不提交”的轴承试算校正，必要时迭代到
界面一致，最后每个轴承只提交一次。它不需要导数，也不拆分模型，因此支持热模型、
主动轴承（控制器和阀留在轴承内部）及其 `MultiPad`：

```python
from ALB.dynamics import PredictorCorrectorOptions

simulation_config = ALB.SimulationConfig(
    rotor=rotor,
    mounts=(mount,),
    time_step=2.0e-5,
    steps=5000,
    integrator="predictor_corrector",
    predictor_corrector=PredictorCorrectorOptions(
        mode="iterate",          # or "pece": one trial and one commit per step
        relaxation="aitken",     # "iqn_ils", "constant", "none"
        on_nonconvergence="warn",
    ),
)
result = ALB.build_simulation(simulation_config).run()
diagnostics = result.metadata["predictor_corrector_diagnostics"]
print(diagnostics["iterations_per_step"], diagnostics["nonconverged_steps"])
```

无副作用的轴承用 `probe_force` 试算；热模型、主动轴承和含它们的 `MultiPad` 通过
存档/回退协议（`ALB.contracts.CheckpointableRuntimeProtocol`）走正常生命周期试算，
试算后立即回到提交状态，控制器仍按提交次数每 `m` 次运行一次。刚度大、阻尼大的油膜
可能使不加松弛的迭代发散，此时保留默认 `"aitken"` 或改用 `"iqn_ils"`。迭代未收敛时，
`"warn"` 提交最后一次迭代并在每次运行中发出一次 `ALB.CouplingIterationWarning`；
`"raise"` 以 `SimulationError` 结束运行。唯一被拒绝的拓扑是 `MultiPad` 内需要外部阀芯
的子瓦。完整说明见 [0.4.7 迁移说明](../../migrations/0.4.7.md)。

主动轴承声明 `control.control_period` 时，控制器每 `m = Ts / time_step` 步采样一次。
若 `time_step` 不能整除 `Ts`，构造 `SimulationConfig` 时步长改为
`Ts / ceil(Ts / time_step)`，步数按请求结束时间向上取整到整数个控制周期，并发出
`ALB.TimeStepAdjustedWarning`。构造后应读取 `simulation_config.time_step`、`steps`
和 `time_step_adjustment` 的实际值。警告发出后，同一转子对象才被原位重新离散，因此
把警告提升为异常时转子保持不变。被重新离散的转子不要再给其他按原步长校验的配置
使用，否则构建仿真时报 `ConfigurationError`。完整边界见
[0.4.6 迁移说明](../../migrations/0.4.6.md)。

## 载荷

| type | 必填字段 | 主要可选字段 |
| --- | --- | --- |
| `static` | `node`, `force=[Fx, Fy]` | 无 |
| `gravity` | 无 | `acceleration=9.80665` |
| `unbalance` | `node` | `phase`, `t_max`, `m`, `freq`, `e`, `no_step` |

所有节点必须是非负整数，声明在构造时被复制并冻结。

## 历史策略

- `memory`：保留选定的全部采样。
- `ring_buffer`：只保留最近 `capacity` 个采样。
- `disk_stream`：写入 `directory`，对应内存数组为空。
- `downsample=N`：保留提交索引能被 N 整除的采样，包括初始索引 0。步长被控制周期调整后，`downsample` 和 `capacity` 仍按索引计数。

`steps` 表示初始提交点之后的 advance 次数，因此默认 memory history 有 `steps + 1` 个时间点。simulation 是 one-shot；需要重跑时重新构建。
