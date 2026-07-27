# ALB 0.4 与 ALBNN 快速使用手册

## 文档角色

- 角色：稳定用户操作手册。
- 目的：说明 0.4 轴承、分析、仿真和 ALBNN package 的推荐用法。
- 允许更新：稳定 API、最小示例、输入输出契约和排错提示。
- 禁止更新：训练实时进度、PID、单次日志和临时实验结论。
- 更新时机：构建 API、配置或推荐流程变化时。
- 事实来源：`ALB/__init__.py`、`ALB/api/`、`ALB/surrogate/package.py`。

## 安装检查

```powershell
E:/Anaconda2023/envs/ALB/python.exe -c "import ALB; print(ALB.__version__, ALB.__file__)"
```

兄弟项目应安装候选 wheel；不要复制 `ALB/`、修改 `sys.path` 或 shadow import
源码目录。

## 从文件计算轴承

可直接从 [`docs/api/examples/`](api/examples/) 复制最接近的完整 JSON5：

- `liquid_film_minimal.json5`：最小量纲液膜；
- `gas_film_minimal.json5`：固定 `skfem_newton` 与一基织构索引；
- `active_lubricated_pid.json5`：正式节流器、阀和 PID 配置；
- `multi_pad_nested.json5`：自包含嵌套多瓦。

完整字段、单位和条件约束见
[`docs/api/bearing_config_reference.md`](api/bearing_config_reference.md)。

```python
import ALB

config = ALB.load_bearing_config(
    "docs/api/examples/liquid_film_minimal.json5"
)
bearing = ALB.build_bearing(config)
# Equivalent shorthand: bearing = ALB.bearing_from_file(path)
result = bearing.calculate(
    displacement=(0.02, -0.01),
    velocity=(0.0, 0.0),
    time=0.0,
)

print(result.fx, result.fy)
result.write("outputs/case_001")
```

`calculate()` 只接受 keyword 参数。`velocity` 可省略，`time` 不可省略。
后续调用的时间必须按配置中的 `time_step` 前进。`latest_result` 只读且不重新
求解；使用 `bearing.reset()` 清空当前会话并按同一不可变配置重建 runtime。

## 程序化配置

```python
import ALB

config = ALB.BearingConfig(
    {
        "family": "liquid_film",
        "unit_system": "dimensional",
        "time_step": 0.001,
        "node": 0,
        "film": {
            "circumferential_elements": 21,
            "axial_elements": 9,
            "supply_pressure": 7.0e6,
        },
        "restrictors": None,
        "thermal": None,
    }
)

high_pressure = config.with_overrides(
    {"film.supply_pressure": 8.0e6}
)
cases = config.sweep(
    "film.supply_pressure",
    [6.0e6, 7.0e6, 8.0e6],
)
```

配置不可原地修改。每个 override/sweep 都重新执行完整校验。

## 严格 JSON5 与 include

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

profile 使用 `kind: "bearing_profile"`。include 按顺序合并，当前 `spec` 最后
覆盖；mapping 深度合并，数组和标量整体替换，显式 `null` 不表示继承。

## 混合液膜轴承

用户不声明动压、静压或混合模式：

```json5
spec: {
  family: "liquid_film",
  // ...
  restrictors: {
    positions: [[0.5, 0.25], [0.5, 0.50], [0.5, 0.75]],
    radius: 0.0005,
    pressure: 7000000.0,
    discharge_coefficient: 0.7,
  },
}
```

`restrictors: null` 表示普通液膜；非空列表在构造时自然启用节流耦合。运行后
不能追加节流器或修改 topology。

## 主动控制与 external spool

控制模式只接受 `pid`、`fuzzy_pid`、`uncontrolled`、`external_spool`。
只有 external-spool 轴承允许：

```python
result = bearing.calculate(
    displacement=(x, y),
    velocity=(vx, vy),
    spool=(sx, sy),
    time=t,
)
```

`spool` 是归一化二轴值。external-spool 缺少 spool，或其他模式传入 spool，
都会立即报错。

## 分析服务

```python
import numpy as np
import ALB

trajectory = ALB.EllipseTrajectory(
    center=np.array([0.0, 0.0]),
    semi_axes=np.array([1.0e-5, 5.0e-6]),
    orientation_rad=0.25,
)
time = np.arange(100) * 1.0e-3

orbit = bearing.analysis.trace_orbit(
    trajectory,
    time,
    frequency_hz=10.0,
)
coefficients = bearing.analysis.dynamic_coefficients(
    trajectory,
    time,
    frequency_hz=10.0,
)
```

静平衡模型直接接收已经构造的轴承：

```python
solver = ALB.EquilibriumSolver(bearing)
equilibrium = solver.solve(
    load=(0.0, -5000.0),
    initial_displacement=(0.0, 0.0),
)
```

`bearing.analysis.find_equilibrium(...)` 是同一模型的便捷入口，不包含另一套
静平衡算法。该入口同时适用于液膜轴承和受内部控制或不受控的主动润滑轴承；
`external_spool` 配置不会擅自推断外部阀芯状态，因此不属于该静平衡入口。
需要调整迭代参数时，再把 `ALB.EquilibriumOptions(...)` 作为第二个参数传入。

`dynamic_coefficients()` 会从同一椭圆自动生成正反涡动。`phase` 是时间相位，
`orientation_rad` 是空间旋转。时间网格必须有限、严格递增且均匀，目标频率
必须命中非 DC FFT bin；上面的 100 个 `dt=0.001` 样本恰好覆盖一个 10 Hz
周期。`harmonic_linearize(operating_point,
excitation_frequency, spool=...)` 使用方程导数，只支持量纲液膜和已验证的
三节点 CSOrifice 主动润滑拓扑。每次分析使用独立 runtime，返回值包含完整
采样点，不改变 `bearing.latest_result`；任一子求解不收敛时抛出带 snapshot
的 `CalculationError`。

## 转子轴承仿真

```python
import ALB

simulation = ALB.simulation_from_file("paper_rotor_system.json5")
history = simulation.run()
history.write("outputs/rotor_case_001")
```

挂载通过配置中的不可变 mount 列表一次性给出。默认保存所有已提交时间步；
需要降采样或 ring buffer 时才显式配置 `HistoryPolicy`。失败不会发布半完成
物理步骤；若 recorder/observer 在提交后失败，`SimulationError` 的 partial
result 会包含该真实提交，但仿真不会重试或继续。转子使用全局 `time_step`；
mount、嵌套 `MultiPad` 及其控制器、阀和热模型必须使用 unit adapter 转换后的
bearing-local `time_step`。磁盘流通过原子替换发布快照和 manifest。同一个
simulation 对象只能调用一次 `run()`；需要重新计算时使用同一不可变配置重新
调用 `build_simulation()`。

## ALBNN package

surrogate bearing 的 `spec.family` 为 `surrogate`，`model_package` 指向
`alb.surrogate-package.v0.4` 目录。目录必须包含：

```text
manifest.json
weights.pt
input_scaler.npz
output_scaler.npz
metadata.json
```

运行时严格校验 schema、artifact role、metadata 和 SHA-256，并以
`weights_only=True` 加载权重。0.3/v0.2 package 和 pickle scaler 不受支持。

## 常见错误

- `ConfigurationError`：schema、include、未知字段或跨字段约束错误。
- `BuildError`：配置合法但 runtime 无法装配。
- `CalculationError`：单轴承求解失败，可读取密封 `failure_snapshot`。
- `SimulationError`：仿真失败，可读取截至最后成功提交的 partial result。

不要调用 `init()`、访问 `.signal/.pads/.controller/.valve`，也不要使用旧工厂
或旧配置字段；这些入口在 0.4 中不存在。
