# 配置与 JSON5

`BearingConfig` 是公开配置边界：构造时完整校验，随后深度只读。支持的 family 是 `liquid_film`、`active_lubricated`、`gas_film`、`multi_pad` 和 `surrogate`。

## 严格文档结构

```json5
{
  schema_version: "0.4.0",
  kind: "bearing",
  includes: ["profiles/liquid_base.json5"],
  spec: {
    film: { supply_pressure: 7000000.0 },
    thermal: null,
  },
}
```

profile 使用 `kind: "bearing_profile"`。include 按顺序合并，本地 `spec` 最后覆盖；mapping 深度合并，数组和标量整体替换，显式 `null` 表示关闭而不是继承。

## 主动轴承伺服阀

自 0.4.5 起，主动轴承接受三种阀配置。标准二阶阀直接使用 Hz：

```json5
valve: {
  model: "second_order",
  natural_frequency_hz: 166.0,
  damping_ratio: 0.7,
  delay: 0.0,
}
```

无动态响应的单位增益静态阀不需要额外参数：

```json5
valve: {
  model: "static",
}
```

任意高阶或已辨识模型使用完整连续时间传递函数，系数按 `s` 的降幂排列：

```json5
valve: {
  model: "transfer_function",
  numerator: [1.0],
  denominator: [1.0e-9, 2.0e-6, 1.0e-3, 1.0],
}
```

`transfer_function` 的分子已经包含增益及任何有理延迟近似，不能再额外设置
`delay`。旧字段 `response_time`、`third_order_time_constant` 以及旧模型名
`third_order` 均由严格配置边界拒绝；`static` 只允许 `model` 字段。

## 控制器采样周期

真实数字控制器以固定周期 `Ts` 采样。0.4.6 起，`pid` 与 `fuzzy_pid` 可在
`control` 中声明 `control_period`，单位与 `time_step` 相同（量纲轴承为 s）：

```json5
spec: {
  family: "active_lubricated",
  unit_system: "dimensional",
  time_step: 2.0e-5,
  control: {
    mode: "pid",
    frequency_hz: 50.0,
    sensor_angles_deg: [45.0, 135.0],
    gains: { kp: 1.0, ki: 0.0, kd: 0.0, feedforward: 0.0 },
    control_period: 1.0e-3,
  },
  // film, restrictors, tank, valve, ...
}
```

控制器每 `m = Ts / time_step = 50` 次求值运行一次，其余求值保持指令；阀、液膜和
转子仍按 `time_step` 推进。省略该字段时与 0.4.5 相同，控制器逐步运行。

- 独立轴承要求 `Ts` 恰为 `time_step` 的整数倍，否则构建前报 `ConfigurationError`。
  采样按求值次数计数，因此独立调用 `calculate()` 时应按 `time_step` 推进时间。
- 在仿真中，若全局步长 `h` 不能整除 `Ts`，`SimulationConfig` 保持 `Ts`，改用
  `h' = Ts / ceil(Ts / h)`，按请求结束时间重算整数个控制周期的步数，并发出
  `ALB.TimeStepAdjustedWarning`。实际值可从 `config.time_step`、`config.steps` 和
  `config.time_step_adjustment` 读取。
- 其他控制模式不接受该字段。

## 程序化 override 与 sweep

```python
high_pressure = config.with_overrides(
    {"film.supply_pressure": 8.0e6}
)

cases = config.sweep(
    "film.supply_pressure",
    (6.0e6, 7.0e6, 8.0e6),
)
```

路径相对于 `spec`，每个中间段必须已经是 mapping。每个新配置都会重新校验，原配置保持不变。

## 单位与资源

- `dimensional` 量默认使用字段参考中标明的 SI 单位；角度和比例按字段说明。
- `nondimensional` 使用归一化输入，通过 `scale_*` 字段声明工程尺度。
- 气膜当前只支持 dimensional。
- 从文件加载时，文档父目录成为 `resource_root`，用于相对 pad、模糊规则和 surrogate package 路径。

轴承的完整查询入口是[轴承配置参考](../../api/bearing_config_reference.md)。其中每个公开字段都列出值类型、单位、必填性或默认值、可选值、约束、适用 family/unit system、原生映射和源码英文合同。

## 转子-轴承仿真配置

仿真文件使用同一套 UTF-8 JSON5 envelope，但声明 `kind: "simulation"`。`spec` 由 `rotor`、`time_grid`、`mounts`、`loads` 和 `history` 组成：

```json5
{
  schema_version: "0.4.0",
  kind: "simulation",
  includes: [],
  spec: {
    rotor: {
      model: "ross_excel",
      path: "resources/rotor.xlsx",
      frequency_hz: 50.0,
    },
    time_grid: { time_step: 1e-4, steps: 1000 },
    mounts: [
      { bearing: "bearings/left.json5", node: 0 },
      { bearing: "bearings/right.json5", node: 4 },
    ],
    loads: [{ type: "gravity", acceleration: 9.80665 }],
    history: { mode: "memory", downsample: 1 },
  },
}
```

`time_grid` 还可选择耦合积分器。缺省 `integrator: "staggered"` 保持 0.4.5
的数值路径；`"ros2"` 使用两级 Rosenbrock-W 方法同步计算轴承力，并可设置
Jacobian 刷新策略（ROS2 在 0.4.6 标记为功能不完善，见下方提示）：

```json5
time_grid: {
  time_step: 2.0e-5,
  steps: 50000,
  integrator: "ros2",
  jacobian_refresh: "control_period",  // null, positive integer N, or "control_period"
},
```

!!! warning "功能不完善"
    0.4.6 的 ROS2 积分器标记为功能不完善（实验性）：代理模型族未做数值收敛验证，
    不支持热模型轴承，外部阀芯 provider 通道只有一阶精度，冻结 Jacobian 没有自适应刷新。
    正式计算继续使用默认 `staggered`；ROS2 结果应先与 staggered 细步长解或独立参考交叉核对。详见 [0.4.6 迁移说明](../../migrations/0.4.6.md)。

ROS2 不支持带热模型的轴承，也不支持含主动或外部阀芯子瓦的 `multi_pad`，构造时会以
`ConfigurationError` 拒绝。`"control_period"` 在阀驱动主动轴承的每个控制器采样时刻
刷新；没有这类轴承时每步刷新。适用范围和其他选项见
[0.4.6 迁移说明](../../migrations/0.4.6.md)。

文件中的转子 Excel、bearing 配置和 disk-stream history 路径必须位于配置文件的资源根目录内。程序化构造的 `SimulationConfig` 还可以承载 adapter、spool provider、recorder 和 observer；这些 runtime object 不能写入 JSON5。

完整字段、提交语义、数组形状和失败边界见[仿真配置参考](../../api/simulation_config_reference.md)。轴承与仿真的可复制文件集中在[完整示例](../examples.md)。
