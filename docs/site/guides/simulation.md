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
以 `ConfigurationError` 拒绝。`initial_rotor_state` 可对两种积分器给出完整初始转子
状态，例如静平衡状态；它与 `Ros2Options.jacobian_state` 都保存为浮点数元组。

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
