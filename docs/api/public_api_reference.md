# ALB 公开 API 自动参考

## 文档角色

- 角色：由源码与语义元数据生成的稳定公开 API 参考。
- 目的：展示 `ALB` 根命名空间中类、函数、枚举、异常和常量的输入、输出、功能与示例。
- 允许更新：只能通过 `tools/docs/generate_public_api_reference.py` 根据当前源码和元数据重新生成。
- 禁止更新：手工修改生成正文、记录实时运行状态或描述未导出的内部实现。
- 更新时机：`ALB.__all__`、公开签名、公开成员、中文语义说明或示例变化时。
- 事实来源：`ALB.__all__`、运行时签名、源码 docstring 和 `docs/api/public_api_docs.json`。

<!-- This file is generated. Do not edit it directly. -->

- 包版本：`0.4.5`
- 公开符号数：`27`
- 接口表面摘要：`sha256:3607bae80dd00d84`
- 重新生成：`E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_public_api_reference.py`
- 一致性检查：`E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_public_api_reference.py --check`

本文只覆盖普通用户应依赖的 `ALB` 根公开接口。领域实现命名空间用于高级开发，
不应绕过 facade 直接拼装普通计算流程。

## 总览

| 名称 | 类别 | 功能 | 源码 |
| --- | --- | --- | --- |
| `ALBError` | 异常 | 所有用户侧 ALB 稳定异常的基类，适合统一记录或跨层上报。 | `ALB/api/errors.py:8` |
| `AnalysisResult` | 类 | 分析服务返回的不可变通用结果，保存数值结果、诊断元数据和收敛状态。 | `ALB/api/results.py:143` |
| `Bearing` | 类 | 单个已构建轴承的用户 facade，负责顺序计算、最新结果读取、诊断和独立分析入口。 | `ALB/api/bearing.py:26` |
| `BearingAnalysis` | 类 | 基于一个 Bearing 配置执行状态隔离的静平衡、轨迹、动态系数和谐波线性化。 | `ALB/api/analysis.py:926` |
| `BearingConfig` | 类 | 严格校验、深度冻结的 0.4 轴承配置，支持安全覆盖、扫描和序列化。 | `ALB/api/config.py:615` |
| `BearingMount` | 类 | 把一个不可变轴承配置固定挂载到转子节点，并可附加单位和阀芯命令适配器。 | `ALB/api/simulation.py:150` |
| `BearingResult` | 类 | 一次成功二维轴承计算的不可变结果，包含力、时间、单位、收敛状态和完整诊断。 | `ALB/api/results.py:42` |
| `BuildError` | 异常 | 配置已经通过校验，但对应 runtime 无法完成装配时抛出的稳定异常。 | `ALB/api/errors.py:16` |
| `CalculationError` | 异常 | 轴承输入已接受但物理求解失败时抛出的稳定异常，可携带密封失败快照。 | `ALB/api/errors.py:20` |
| `ConfigurationError` | 异常 | JSON5 文档、程序化配置或跨字段约束不合法时抛出的稳定异常。 | `ALB/api/errors.py:12` |
| `EllipseTrajectory` | 类 | 二维椭圆轨迹值对象，分别表达中心、半轴、遍历方向、时间相位和空间转角。 | `ALB/api/analysis.py:275` |
| `EquilibriumOptions` | 类 | 静平衡求解器的不可变参数集合，控制迭代、容差、阻尼、Jacobian 和停滞回退。 | `ALB/api/analysis.py:197` |
| `EquilibriumSolver` | 类 | 直接接收一个已构造 Bearing，并使用既有静平衡算法求载荷平衡。 | `ALB/api/analysis.py:435` |
| `HistoryPolicy` | 类 | 控制仿真已提交历史的字段筛选、降采样、环形缓存或磁盘流式写入。 | `ALB/api/simulation.py:172` |
| `RotorBearingSimulation` | 类 | 拓扑不可变的一次性转子-轴承耦合仿真 facade。 | `ALB/api/simulation.py:379` |
| `SCHEMA_VERSION` | 常量 | bearing 与 simulation JSON5 接受的 schema 版本字符串，独立于 re-alb 包版本。 | `-` |
| `SimulationConfig` | 类 | 一次转子-轴承耦合计算的不可变拓扑、时步、载荷、历史策略和可选依赖。 | `ALB/api/simulation.py:235` |
| `SimulationError` | 异常 | 耦合仿真失败时抛出的稳定异常，可携带截至最后真实提交点的部分结果。 | `ALB/api/errors.py:33` |
| `SimulationResult` | 类 | 转子-轴承仿真中按策略保留的不可变已提交历史。 | `ALB/api/results.py:196` |
| `UnitSystem` | 枚举 | 所有数值积分边界使用的单位制枚举，避免量纲和无量纲值被隐式混用。 | `ALB/contracts/types.py:12` |
| `__version__` | 常量 | 当前导入的 re-alb 包版本字符串。 | `-` |
| `bearing_from_file` | 函数 | 读取严格 0.4 JSON5 轴承文档并一步构建可计算轴承。 | `ALB/api/bearing.py:186` |
| `build_bearing` | 函数 | 从已验证的不可变配置构建一个可直接计算的轴承 facade。 | `ALB/api/bearing.py:175` |
| `build_simulation` | 函数 | 从已验证的仿真配置构建一次性转子-轴承仿真对象。 | `ALB/api/simulation.py:1145` |
| `load_bearing_config` | 函数 | 读取严格 UTF-8 0.4 bearing 文档，安全合并受限 include 并完成校验。 | `ALB/api/config.py:851` |
| `load_simulation_config` | 函数 | 读取严格 0.4 simulation 文档，并解析转子、挂载轴承、时间网格、载荷和历史策略。 | `ALB/api/simulation.py:991` |
| `simulation_from_file` | 函数 | 读取严格 JSON5 仿真文档并一步构建一次性仿真对象。 | `ALB/api/simulation.py:1151` |

## 示例库

<a id="example-package_version"></a>
### 检查安装位置和版本

先确认当前解释器导入的是预期的 ALB 安装，而不是同名目录或旧 wheel。

```python
import ALB

print(ALB.__version__)
print(ALB.SCHEMA_VERSION)
print(ALB.__file__)
```

<a id="example-bearing_from_file"></a>
### 从 JSON5 构建并计算轴承

文件入口适合正式算例；配置先严格校验，再构建为可直接计算的轴承对象。

```python
from pathlib import Path

import ALB

case_path = Path("configs/paper_alb.json5")
config = ALB.load_bearing_config(case_path)
bearing = ALB.build_bearing(config)

# Equivalent one-step helper:
# bearing = ALB.bearing_from_file(case_path)
result = bearing.calculate(
    displacement=(0.02, -0.01),
    velocity=(0.0, 0.0),
    time=0.0,
)
print(result.fx, result.fy, result.convergence.converged)
result.write("outputs/case_001")
```

<a id="example-bearing_programmatic"></a>
### 程序化配置、参数覆盖与扫描

配置对象不可变；覆盖和扫描都会重新执行完整校验。

```python
import ALB

config = ALB.BearingConfig(
    {
        "family": "liquid_film",
        "unit_system": "dimensional",
        "time_step": 1.0e-3,
        "node": 0,
        "film": {
            "circumferential_elements": 5,
            "axial_elements": 3,
            "max_iterations": 5,
            "solver_tolerance": 1.0e-6,
            "eccentricity": 0.0,
        },
        "restrictors": None,
        "thermal": None,
    }
)
high_pressure = config.with_overrides(
    {"film.supply_pressure": 8.0e6}
)
cases = high_pressure.sweep(
    "film.supply_pressure",
    (6.0e6, 7.0e6, 8.0e6),
)
bearing = ALB.build_bearing(cases[1])
result = bearing.calculate(displacement=(0.0, 0.0), time=0.0)
print(result.force)
```

<a id="example-bearing_analysis"></a>
### 轨迹、静平衡和动态系数分析

分析使用独立 runtime，不改变轴承对象上的 latest_result。

```python
import numpy as np

import ALB

bearing = ALB.bearing_from_file("configs/paper_alb.json5")
trajectory = ALB.EllipseTrajectory(
    center=np.array([0.0, 0.0]),
    semi_axes=np.array([1.0e-5, 5.0e-6]),
    orientation_rad=0.25,
)
time_grid = np.arange(100, dtype=float) * 1.0e-3

displacement, velocity = trajectory.samples(
    time_grid,
    frequency_hz=10.0,
)
orbit = bearing.analysis.trace_orbit(
    trajectory,
    time_grid,
    frequency_hz=10.0,
)
coefficients = bearing.analysis.dynamic_coefficients(
    trajectory,
    time_grid,
    frequency_hz=10.0,
)
equilibrium = ALB.EquilibriumSolver(bearing).solve(
    load=(0.0, -5000.0),
)
print(displacement.shape, velocity.shape)
print(orbit.values.keys(), coefficients.values.keys())
print(equilibrium.convergence.converged)
```

<a id="example-harmonic_linearization"></a>
### 方程导数谐波线性化

该入口只支持包概览中声明的量纲液膜和已验证主动润滑拓扑。

```python
import ALB

bearing = ALB.bearing_from_file("configs/harmonic_supported_alb.json5")
linearized = bearing.analysis.harmonic_linearize(
    operating_point=(0.0, 0.0),
    excitation_frequency=50.0,
)
K = linearized.values["stiffness"]
C = linearized.values["damping"]
print(K.shape, C.shape)
```

<a id="example-simulation_from_file"></a>
### 从 JSON5 运行转子-轴承仿真

仿真对象是一次性的；重新计算时应从同一不可变配置重新构建。

```python
import ALB

config = ALB.load_simulation_config("configs/rotor_system.json5")
simulation = ALB.build_simulation(config)

# Equivalent one-step helper:
# simulation = ALB.simulation_from_file("configs/rotor_system.json5")
history = simulation.run()
print(history.time.shape, history.bearing_force.shape)
history.write("outputs/rotor_case_001")
```

<a id="example-simulation_programmatic"></a>
### 程序化装配仿真拓扑

rotor 必须实现 ALB.contracts.RotorProtocol；记录器和 observer 等高级依赖从 ALB.dynamics 导入。普通算例更推荐使用 JSON5 文件入口。

```python
import ALB
from ALB.contracts import RotorProtocol
from ALB.dynamics import CouplingRuntimeDependencies

rotor = make_rotor()  # Project object implementing RotorProtocol.
assert isinstance(rotor, RotorProtocol)
bearing_config = ALB.load_bearing_config("configs/paper_alb.json5")
mount = ALB.BearingMount(config=bearing_config, node=0)
history_policy = ALB.HistoryPolicy(
    mode="ring_buffer",
    fields=("bearing_force",),
    capacity=200,
)
dependencies = CouplingRuntimeDependencies(run_id="case-001")
config = ALB.SimulationConfig(
    rotor=rotor,
    mounts=(mount,),
    time_step=1.0e-3,
    steps=1000,
    history=history_policy,
    dependencies=dependencies,
)
simulation = ALB.build_simulation(config)
```

<a id="example-history_policy"></a>
### 选择仿真历史保留策略

默认 memory 保存全部提交步；长任务可以显式降采样、环形缓存或流式写盘。

```python
from pathlib import Path

import ALB

all_steps = ALB.HistoryPolicy()
recent_only = ALB.HistoryPolicy(
    mode="ring_buffer",
    fields=("bearing_force",),
    downsample=2,
    capacity=500,
)
streamed = ALB.HistoryPolicy(
    mode="disk_stream",
    fields=("bearing_force",),
    downsample=10,
    directory=Path("outputs/history_stream"),
)
```

<a id="example-error_handling"></a>
### 按稳定异常边界处理失败

优先捕获具体异常；只有需要统一上报时才捕获 ALBError。

```python
import ALB

try:
    bearing = ALB.bearing_from_file("configs/paper_alb.json5")
    result = bearing.calculate(displacement=(0.0, 0.0), time=0.0)
except ALB.ConfigurationError as exc:
    print("configuration rejected:", exc)
except ALB.BuildError as exc:
    print("runtime assembly failed:", exc)
except ALB.CalculationError as exc:
    print("calculation failed:", exc)
    snapshot = exc.failure_snapshot
except ALB.SimulationError as exc:
    print("simulation failed:", exc)
    committed_history = exc.partial_result
except ALB.ALBError as exc:
    print("other ALB failure:", exc)
```

<a id="example-unit_system"></a>
### 读取单位制边界

计算输入和输出的单位制由配置固定，调用方不应自行猜测。

```python
import ALB

bearing = ALB.bearing_from_file("configs/paper_alb.json5")
if bearing.unit_system is ALB.UnitSystem.DIMENSIONAL:
    print("calculate() expects dimensional displacement and velocity")
print(ALB.UnitSystem("nondimensional"))
```

<a id="example-result_persistence"></a>
### 读取不可变结果并持久化

结果数组只读；write() 把值和诊断元数据写入一个新目录。

```python
import ALB

bearing = ALB.bearing_from_file("configs/paper_alb.json5")
result = bearing.calculate(displacement=(0.0, 0.0), time=0.0)
print(result.force, result.fx, result.fy, result.friction)
if result.pressure is not None:
    print(result.pressure.shape, result.diagnostics["pressure_unit"])
if result.film_thickness is not None:
    print(result.film_thickness.shape)
bundle = result.as_bundle()
manifest = result.write("outputs/bearing_result")
print(bundle.metadata["schema"], manifest)
```

## 主要对象与结果

### `ALB.AnalysisResult(values: 'Mapping[str, Any]', metadata: 'Mapping[str, Any]', convergence: 'ConvergenceStatus' = ConvergenceStatus(residual=0.0, converged=True, iterations=None, message='')) -> None`

分析服务返回的不可变通用结果，保存数值结果、诊断元数据和收敛状态。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `values` | `Mapping[str, Any]` | 是 | `-` | 位置或关键字 | 分析值映射；数组会转换为只读快照。 |
| `metadata` | `Mapping[str, Any]` | 是 | `-` | 位置或关键字 | 分析诊断、schema 和方法信息。 |
| `convergence` | `ConvergenceStatus` | 否 | `ConvergenceStatus(residual=0.0, converged=True, iterations=None, message='')` | 位置或关键字 | 本次分析的收敛状态，默认表示成功。 |

输出：`ALB.AnalysisResult`。构造一个不可变分析结果；普通用户通常从 BearingAnalysis 的方法获得它。

示例：[轨迹、静平衡和动态系数分析](#example-bearing_analysis)、[方程导数谐波线性化](#example-harmonic_linearization)。

源码：`ALB/api/results.py:143`。

公开数据字段：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `values` | `Mapping[str, Any]` | `-` | 分析值映射；数组会转换为只读快照。 |
| `metadata` | `Mapping[str, Any]` | `-` | 分析诊断、schema 和方法信息。 |
| `convergence` | `ConvergenceStatus` | `ConvergenceStatus(residual=0.0, converged=True, iterations=None, message='')` | 本次分析的收敛状态，默认表示成功。 |

公开成员：

#### `AnalysisResult.diagnostics`

读取不可变分析诊断元数据。

输出：`Mapping[str, Any]`。返回只读键值映射。

#### `AnalysisResult.as_bundle() -> 'ResultBundle'`

把分析结果转换为统一的可持久化 ResultBundle。

输入：

无。

输出：`ResultBundle`。返回包含 values 与 metadata 的不可变结果包。

#### `AnalysisResult.write(path: 'str | Path') -> 'ArtifactManifest'`

把分析结果写入一个新的制品目录。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `path` | `str \| Path` | 是 | `-` | 位置或关键字 | 目标目录；目录必须满足写入器的新制品约束。 |

输出：`ArtifactManifest`。返回已写入文件及摘要信息的 ArtifactManifest。

### `ALB.Bearing(config: 'BearingConfig') -> 'None'`

单个已构建轴承的用户 facade，负责顺序计算、最新结果读取、诊断和独立分析入口。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `config` | `BearingConfig` | 是 | `-` | 位置或关键字 | 经过完整验证的不可变 BearingConfig。 |

输出：`ALB.Bearing`。构造一个可直接计算的 Bearing；通常应通过 build_bearing() 获得。

示例：[从 JSON5 构建并计算轴承](#example-bearing_from_file)、[程序化配置、参数覆盖与扫描](#example-bearing_programmatic)、[读取不可变结果并持久化](#example-result_persistence)。

源码：`ALB/api/bearing.py:26`。

公开成员：

#### `Bearing.config`

读取构建该轴承时使用的不可变配置。

输出：`BearingConfig`。返回原始 BearingConfig。

#### `Bearing.unit_system`

读取 calculate() 所要求的输入和输出单位制。

输出：`UnitSystem`。返回 DIMENSIONAL 或 NONDIMENSIONAL。

#### `Bearing.latest_result`

读取最近一次成功计算的结果，不触发新计算。

输出：`BearingResult`。返回最近的 BearingResult。


可能异常：

| 类型 | 触发条件 |
| --- | --- |
| `RuntimeError` | 尚未成功计算，或调用 reset() 后没有新结果。 |

#### `Bearing.analysis`

创建绑定于当前不可变配置的独立分析服务。

输出：`BearingAnalysis`。返回 BearingAnalysis；其计算不污染 latest_result。

#### `Bearing.reset() -> 'None'`

以同一配置重建内部 runtime，并清空当前会话结果。

输入：

无。

输出：`None`。无返回值。

#### `Bearing.calculate(*, displacement: 'object', velocity: 'object' = (0.0, 0.0), time: 'float', spool: 'object | None' = None) -> 'BearingResult'`

计算一个严格顺序时间点上的二维轴承力。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `displacement` | `object` | 是 | `-` | 仅关键字 | 二维轴心位移 (x, y)，单位由 unit_system 决定。 |
| `velocity` | `object` | 否 | `(0.0, 0.0)` | 仅关键字 | 二维轴心速度 (vx, vy)，默认均为 0。 |
| `time` | `float` | 是 | `-` | 仅关键字 | 当前样本时间；后续调用必须按配置 time_step 严格前进。 |
| `spool` | `object \| None` | 否 | `None` | 仅关键字 | 仅 external_spool 模式使用的归一化二维阀芯命令，范围为 [-1, 1]。 |

输出：`BearingResult`。返回不可变 BearingResult，force 的形状为 (2,)。


可能异常：

| 类型 | 触发条件 |
| --- | --- |
| `ValueError` | 时间不连续，或 spool 与控制模式不匹配。 |
| `CalculationError` | 底层物理求解失败；failure_snapshot 可能包含密封诊断。 |

#### `Bearing.diagnostic_snapshot() -> 'ResultBundle'`

读取 facade 和底层 runtime 的不可变诊断快照。

输入：

无。

输出：`ResultBundle`。返回 ResultBundle；不会推进物理状态。

### `ALB.BearingAnalysis(bearing: 'Any') -> 'None'`

基于一个 Bearing 配置执行状态隔离的静平衡、轨迹、动态系数和谐波线性化。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `bearing` | `Any` | 是 | `-` | 位置或关键字 | 作为配置来源的 Bearing 实例。 |

输出：`ALB.BearingAnalysis`。构造分析服务；普通用户应从 bearing.analysis 取得。

示例：[轨迹、静平衡和动态系数分析](#example-bearing_analysis)、[方程导数谐波线性化](#example-harmonic_linearization)。

源码：`ALB/api/analysis.py:926`。

公开成员：

#### `BearingAnalysis.find_equilibrium(load: 'object', initial_displacement: 'object' = (0.0, 0.0), options: 'EquilibriumOptions' = EquilibriumOptions(max_iterations=30, relative_tolerance=0.0001, damping=0.05, jacobian_step=0.01, fallback_stiffness=(5.0, 5.0), stall_patience=5, stall_relative_tolerance=0.0, time=0.0)) -> 'AnalysisResult'`

使用既有阻尼 Newton、冻结 Jacobian 和固定刚度回退算法求载荷平衡。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `load` | `object` | 是 | `-` | 位置或关键字 | 目标二维外载荷。 |
| `initial_displacement` | `object` | 否 | `(0.0, 0.0)` | 位置或关键字 | Newton 迭代初始二维位移。 |
| `options` | `EquilibriumOptions` | 否 | `EquilibriumOptions(max_iterations=30, relative_tolerance=0.0001, damping=0.05, jacobian_step=0.01, fallback_stiffness=(5.0, 5.0), stall_patience=5, stall_relative_tolerance=0.0, time=0.0)` | 位置或关键字 | 迭代次数、容差、阻尼、差分步长和回退参数。 |

输出：`AnalysisResult`。返回 AnalysisResult，包含平衡位移、力、残差和迭代信息。


可能异常：

| 类型 | 触发条件 |
| --- | --- |
| `CalculationError` | 子求解失败或最终不能形成有效分析结果。 |

#### `BearingAnalysis.trace_orbit(trajectory: 'EllipseTrajectory', time_grid: 'Sequence[float]', *, frequency_hz: 'float', spool: 'Sequence[Sequence[float]] | None' = None) -> 'AnalysisResult'`

在显式时间网格上逐点计算给定椭圆轨迹。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trajectory` | `EllipseTrajectory` | 是 | `-` | 位置或关键字 | 椭圆几何、方向、相位和空间转角。 |
| `time_grid` | `Sequence[float]` | 是 | `-` | 位置或关键字 | 有限、严格递增的一维时间网格。 |
| `frequency_hz` | `float` | 是 | `-` | 仅关键字 | 轨迹频率，单位 Hz。 |
| `spool` | `Sequence[Sequence[float]] \| None` | 否 | `None` | 仅关键字 | external_spool 模式下与时间网格逐点对应的二维命令序列。 |

输出：`AnalysisResult`。返回 AnalysisResult，values 中包含时间、位移、速度和轴承力序列。

#### `BearingAnalysis.dynamic_coefficients(trajectory: 'EllipseTrajectory', time_grid: 'Sequence[float]', *, frequency_hz: 'float', spool: 'Sequence[Sequence[float]] | None' = None) -> 'AnalysisResult'`

在相干 FFT 网格上用正反涡动响应识别刚度 K 和阻尼 C。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trajectory` | `EllipseTrajectory` | 是 | `-` | 位置或关键字 | 用于生成正反涡动的椭圆轨迹。 |
| `time_grid` | `Sequence[float]` | 是 | `-` | 位置或关键字 | 均匀且覆盖目标非 DC FFT bin 的时间网格。 |
| `frequency_hz` | `float` | 是 | `-` | 仅关键字 | 需要识别的目标频率，单位 Hz。 |
| `spool` | `Sequence[Sequence[float]] \| None` | 否 | `None` | 仅关键字 | external_spool 模式下与时间网格逐点对应的二维命令序列。 |

输出：`AnalysisResult`。返回 AnalysisResult，包含已识别系数、轨迹响应和频率诊断。


可能异常：

| 类型 | 触发条件 |
| --- | --- |
| `ValueError` | 时间网格不均匀、目标频率不是非 DC FFT bin，或频率不满足 Nyquist 条件。 |
| `CalculationError` | 轨迹样本未全部收敛，或正反涡动位移矩阵的诊断、条件数检查或反演失败；异常包含 failure_snapshot。 |

#### `BearingAnalysis.harmonic_linearize(operating_point: 'object', excitation_frequency: 'float', *, spool: 'object | None' = None) -> 'AnalysisResult'`

在指定工作点通过压力方程导数计算谐波刚度与阻尼。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `operating_point` | `object` | 是 | `-` | 位置或关键字 | 二维量纲位移工作点。 |
| `excitation_frequency` | `float` | 是 | `-` | 位置或关键字 | 线性化激励频率，单位 Hz。 |
| `spool` | `object \| None` | 否 | `None` | 仅关键字 | 受支持主动润滑拓扑的可选二维阀芯工作点。 |

输出：`AnalysisResult`。返回 AnalysisResult，包含 stiffness、damping 和工作点诊断。


可能异常：

| 类型 | 触发条件 |
| --- | --- |
| `CalculationError` | 轴承家族、单位制或节流拓扑不在已验证支持域内。 |

### `ALB.BearingConfig(spec: 'Mapping[str, Any]', source_path: 'Path | None' = None, resource_root: 'Path | None' = None) -> None`

严格校验、深度冻结的 0.4 轴承配置，支持安全覆盖、扫描和序列化。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `spec` | `Mapping[str, Any]` | 是 | `-` | 位置或关键字 | 0.4 bearing 文档中的 spec 映射。 |
| `source_path` | `Path \| None` | 否 | `None` | 位置或关键字 | 可选源文件绝对或相对路径，用于资源溯源。 |
| `resource_root` | `Path \| None` | 否 | `None` | 位置或关键字 | 可选资源根；未给出时可由 source_path 的父目录推导。 |

输出：`ALB.BearingConfig`。构造经过完整跨字段校验的不可变 BearingConfig。

示例：[程序化配置、参数覆盖与扫描](#example-bearing_programmatic)、[从 JSON5 构建并计算轴承](#example-bearing_from_file)。

源码：`ALB/api/config.py:615`。

公开数据字段：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `spec` | `Mapping[str, Any]` | `-` | 0.4 bearing 文档中的 spec 映射。 |
| `source_path` | `Path \| None` | `None` | 可选源文件绝对或相对路径，用于资源溯源。 |
| `resource_root` | `Path \| None` | `None` | 可选资源根；未给出时可由 source_path 的父目录推导。 |

公开成员：

#### `BearingConfig.family`

读取轴承族判别值。

输出：`str`。返回 liquid_film、active_lubricated、gas_film、multi_pad 或 surrogate。

#### `BearingConfig.unit_system`

读取配置声明的单位制字符串。

输出：`str`。返回 dimensional 或 nondimensional。

#### `BearingConfig.control_mode`

读取主动轴承控制模式；非主动或 fixed surrogate 返回 None。

输出：`str | None`。返回 pid、fuzzy_pid、uncontrolled、external_spool 或 None。

#### `BearingConfig.to_dict() -> 'dict[str, Any]'`

创建调用方可修改的严格 0.4 bearing 文档副本。

输入：

无。

输出：`dict[str, Any]`。返回含 schema_version、kind 和 spec 的普通 dict。

#### `BearingConfig.with_overrides(overrides: 'Mapping[str, Any]') -> "'BearingConfig'"`

按点分路径替换字段并重新执行完整校验。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `overrides` | `Mapping[str, Any]` | 是 | `-` | 位置或关键字 | 点分字段路径到新值的映射，例如 film.supply_pressure。 |

输出：`'BearingConfig'`。返回新的 BearingConfig，原对象不变。


可能异常：

| 类型 | 触发条件 |
| --- | --- |
| `ConfigurationError` | 路径不存在于映射结构，或替换后的配置不合法。 |

#### `BearingConfig.sweep(path: 'str', values: 'Iterable[Any]') -> "tuple['BearingConfig', ...]"`

对一个点分路径逐值生成已验证配置。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `path` | `str` | 是 | `-` | 位置或关键字 | 需要扫描的点分字段路径。 |
| `values` | `Iterable[Any]` | 是 | `-` | 位置或关键字 | 依次写入该字段的值序列或其他可迭代对象。 |

输出：`tuple['BearingConfig', ...]`。返回与 values 顺序一致的 BearingConfig 元组。

### `ALB.BearingMount(config: 'BearingConfig', node: 'int', unit_adapter: 'BearingUnitAdapterProtocol | None' = None, spool_provider: 'SpoolCommandProviderProtocol | None' = None) -> None`

把一个不可变轴承配置固定挂载到转子节点，并可附加单位和阀芯命令适配器。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `config` | `BearingConfig` | 是 | `-` | 位置或关键字 | 挂载点使用的 BearingConfig。 |
| `node` | `int` | 是 | `-` | 位置或关键字 | 非负转子节点编号。 |
| `unit_adapter` | `BearingUnitAdapterProtocol \| None` | 否 | `None` | 位置或关键字 | 可选转子量纲到轴承本地单位制适配器。 |
| `spool_provider` | `SpoolCommandProviderProtocol \| None` | 否 | `None` | 位置或关键字 | external_spool 轴承的可选阀芯命令提供器。 |

输出：`ALB.BearingMount`。构造一个不可变 BearingMount。

示例：[程序化装配仿真拓扑](#example-simulation_programmatic)。

源码：`ALB/api/simulation.py:150`。

公开数据字段：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `config` | `BearingConfig` | `-` | 挂载点使用的 BearingConfig。 |
| `node` | `int` | `-` | 非负转子节点编号。 |
| `unit_adapter` | `BearingUnitAdapterProtocol \| None` | `None` | 可选转子量纲到轴承本地单位制适配器。 |
| `spool_provider` | `SpoolCommandProviderProtocol \| None` | `None` | external_spool 轴承的可选阀芯命令提供器。 |

### `ALB.BearingResult(force: 'FloatArray', time: 'float', unit_system: 'UnitSystem', convergence: 'ConvergenceStatus', details: 'ResultBundle') -> None`

一次成功二维轴承计算的不可变结果，包含力、时间、单位、收敛状态和完整诊断。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `force` | `FloatArray` | 是 | `-` | 位置或关键字 | 形状为 (2,) 的有限二维力数组。 |
| `time` | `float` | 是 | `-` | 位置或关键字 | 该结果对应的时间。 |
| `unit_system` | `UnitSystem` | 是 | `-` | 位置或关键字 | 力和输入所使用的单位制。 |
| `convergence` | `ConvergenceStatus` | 是 | `-` | 位置或关键字 | 底层求解的收敛状态。 |
| `details` | `ResultBundle` | 是 | `-` | 位置或关键字 | 底层 runtime 的完整不可变结果快照。 |

输出：`ALB.BearingResult`。构造 BearingResult；普通用户通常从 Bearing.calculate() 获得。

示例：[从 JSON5 构建并计算轴承](#example-bearing_from_file)、[读取不可变结果并持久化](#example-result_persistence)。

源码：`ALB/api/results.py:42`。

公开数据字段：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `force` | `FloatArray` | `-` | 形状为 (2,) 的有限二维力数组。 |
| `time` | `float` | `-` | 该结果对应的时间。 |
| `unit_system` | `UnitSystem` | `-` | 力和输入所使用的单位制。 |
| `convergence` | `ConvergenceStatus` | `-` | 底层求解的收敛状态。 |
| `details` | `ResultBundle` | `-` | 底层 runtime 的完整不可变结果快照。 |

公开成员：

#### `BearingResult.fx`

读取 x 方向轴承力。

输出：`float`。返回 Python float。

#### `BearingResult.fy`

读取 y 方向轴承力。

输出：`float`。返回 Python float。

#### `BearingResult.diagnostics`

读取底层结果的不可变诊断元数据。

输出：`Mapping[str, Any]`。返回只读键值映射。

#### `BearingResult.friction`

读取本次计算的总摩擦力。

输出：`float | None`。底层轴承提供摩擦力时返回 float，否则返回 None。

#### `BearingResult.pressure`

读取单液膜压力场；量纲结果为 Pa，无量纲结果为 p/ps。

输出：`FloatArray | None`。返回只读压力数组；多瓦或不提供压力的模型返回 None。

#### `BearingResult.film_thickness`

读取单液膜厚度场；量纲结果为 m，无量纲结果为 h/c。

输出：`FloatArray | None`。返回只读液膜厚度数组；多瓦或不提供厚度的模型返回 None。

#### `BearingResult.as_bundle() -> 'ResultBundle'`

转换为统一的可持久化 ResultBundle。

输入：

无。

输出：`ResultBundle`。返回包含 force、details 和结果元数据的不可变结果包。

#### `BearingResult.write(path: 'str | Path') -> 'ArtifactManifest'`

把结果值和诊断写入一个新的制品目录。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `path` | `str \| Path` | 是 | `-` | 位置或关键字 | 目标输出目录。 |

输出：`ArtifactManifest`。返回 ArtifactManifest。

### `ALB.EllipseTrajectory(center: 'FloatArray', semi_axes: 'FloatArray', direction: 'str' = 'forward', phase: 'float' = 0.0, orientation_rad: 'float' = 0.0) -> None`

二维椭圆轨迹值对象，分别表达中心、半轴、遍历方向、时间相位和空间转角。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `center` | `FloatArray` | 是 | `-` | 位置或关键字 | 形状为 (2,) 的椭圆中心。 |
| `semi_axes` | `FloatArray` | 是 | `-` | 位置或关键字 | 形状为 (2,) 且均大于 0 的半轴。 |
| `direction` | `str` | 否 | `'forward'` | 位置或关键字 | forward 或 reverse。 |
| `phase` | `float` | 否 | `0.0` | 位置或关键字 | 时间相位，单位 rad。 |
| `orientation_rad` | `float` | 否 | `0.0` | 位置或关键字 | 椭圆相对坐标轴的空间旋转角，单位 rad。 |

输出：`ALB.EllipseTrajectory`。构造经过有限值和形状校验的不可变椭圆轨迹。

示例：[轨迹、静平衡和动态系数分析](#example-bearing_analysis)。

源码：`ALB/api/analysis.py:275`。

公开数据字段：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `center` | `FloatArray` | `-` | 形状为 (2,) 的椭圆中心。 |
| `semi_axes` | `FloatArray` | `-` | 形状为 (2,) 且均大于 0 的半轴。 |
| `direction` | `str` | `'forward'` | forward 或 reverse。 |
| `phase` | `float` | `0.0` | 时间相位，单位 rad。 |
| `orientation_rad` | `float` | `0.0` | 椭圆相对坐标轴的空间旋转角，单位 rad。 |

公开成员：

#### `EllipseTrajectory.with_direction(direction: 'str') -> "'EllipseTrajectory'"`

保留几何、相位和转角，只替换遍历方向。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `direction` | `str` | 是 | `-` | 位置或关键字 | forward 或 reverse。 |

输出：`'EllipseTrajectory'`。返回新的 EllipseTrajectory。

#### `EllipseTrajectory.samples(time: 'Sequence[float]', *, frequency_hz: 'float') -> 'tuple[FloatArray, FloatArray]'`

在给定时间点采样旋转椭圆的位移和解析速度。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `time` | `Sequence[float]` | 是 | `-` | 位置或关键字 | 非空、有限的一维时间点序列。 |
| `frequency_hz` | `float` | 是 | `-` | 仅关键字 | 正的轨迹频率，单位 Hz。 |

输出：`tuple[FloatArray, FloatArray]`。返回 (displacement, velocity)，两个数组形状均为 (n, 2)。

### `ALB.EquilibriumOptions(max_iterations: 'int' = 30, relative_tolerance: 'float' = 0.0001, damping: 'float' = 0.05, jacobian_step: 'float' = 0.01, fallback_stiffness: 'tuple[float, float]' = (5.0, 5.0), stall_patience: 'int' = 5, stall_relative_tolerance: 'float' = 0.0, time: 'float' = 0.0) -> None`

静平衡求解器的不可变参数集合，控制迭代、容差、阻尼、Jacobian 和停滞回退。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `max_iterations` | `int` | 否 | `30` | 位置或关键字 | 最大迭代次数，必须至少为 1。 |
| `relative_tolerance` | `float` | 否 | `0.0001` | 位置或关键字 | 正的相对残差收敛阈值。 |
| `damping` | `float` | 否 | `0.05` | 位置或关键字 | 正的 Newton 位移阻尼系数。 |
| `jacobian_step` | `float` | 否 | `0.01` | 位置或关键字 | 正的数值 Jacobian 位移步长。 |
| `fallback_stiffness` | `tuple[float, float]` | 否 | `(5.0, 5.0)` | 位置或关键字 | 停滞回退使用的正二维固定刚度。 |
| `stall_patience` | `int` | 否 | `5` | 位置或关键字 | 触发停滞回退前允许的迭代数；0 表示关闭等待。 |
| `stall_relative_tolerance` | `float` | 否 | `0.0` | 位置或关键字 | 区间 [0, 1) 内的停滞相对改善阈值。 |
| `time` | `float` | 否 | `0.0` | 位置或关键字 | 静平衡评估使用的有限时间。 |

输出：`ALB.EquilibriumOptions`。构造经过范围校验的 EquilibriumOptions。

示例：[轨迹、静平衡和动态系数分析](#example-bearing_analysis)。

源码：`ALB/api/analysis.py:197`。

公开数据字段：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `max_iterations` | `int` | `30` | 最大迭代次数，必须至少为 1。 |
| `relative_tolerance` | `float` | `0.0001` | 正的相对残差收敛阈值。 |
| `damping` | `float` | `0.05` | 正的 Newton 位移阻尼系数。 |
| `jacobian_step` | `float` | `0.01` | 正的数值 Jacobian 位移步长。 |
| `fallback_stiffness` | `tuple[float, float]` | `(5.0, 5.0)` | 停滞回退使用的正二维固定刚度。 |
| `stall_patience` | `int` | `5` | 触发停滞回退前允许的迭代数；0 表示关闭等待。 |
| `stall_relative_tolerance` | `float` | `0.0` | 区间 [0, 1) 内的停滞相对改善阈值。 |
| `time` | `float` | `0.0` | 静平衡评估使用的有限时间。 |

### `ALB.EquilibriumSolver(bearing: 'Any', options: 'EquilibriumOptions' = EquilibriumOptions(max_iterations=30, relative_tolerance=0.0001, damping=0.05, jacobian_step=0.01, fallback_stiffness=(5.0, 5.0), stall_patience=5, stall_relative_tolerance=0.0, time=0.0)) -> 'None'`

直接接收一个已构造 Bearing，并使用既有静平衡算法求载荷平衡。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `bearing` | `Any` | 是 | `-` | 位置或关键字 | 通过 build_bearing() 或 bearing_from_file() 构造的 Bearing。 |
| `options` | `EquilibriumOptions` | 否 | `EquilibriumOptions(max_iterations=30, relative_tolerance=0.0001, damping=0.05, jacobian_step=0.01, fallback_stiffness=(5.0, 5.0), stall_patience=5, stall_relative_tolerance=0.0, time=0.0)` | 位置或关键字 | 静平衡迭代、容差、阻尼和回退参数。 |

输出：`ALB.EquilibriumSolver`。构造可由用户或内部模块直接调用的静平衡模型。

示例：[轨迹、静平衡和动态系数分析](#example-bearing_analysis)。

源码：`ALB/api/analysis.py:435`。

公开成员：

#### `EquilibriumSolver.solve(load: 'object', initial_displacement: 'object' = (0.0, 0.0)) -> 'AnalysisResult'`

求使轴承力与二维外载荷平衡的位移。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `load` | `object` | 是 | `-` | 位置或关键字 | 目标二维外载荷。 |
| `initial_displacement` | `object` | 否 | `(0.0, 0.0)` | 位置或关键字 | 静平衡迭代的初始二维位移。 |

输出：`AnalysisResult`。返回 AnalysisResult，包含平衡位移、力、残差和迭代历史。


可能异常：

| 类型 | 触发条件 |
| --- | --- |
| `CalculationError` | 轴承内层计算失败或静平衡最终不收敛。 |

### `ALB.HistoryPolicy(mode: "Literal['memory', 'ring_buffer', 'disk_stream']" = 'memory', fields: 'tuple[str, ...]' = ('rotor_displacement', 'rotor_velocity', 'bearing_force'), downsample: 'int' = 1, capacity: 'int | None' = None, directory: 'Path | None' = None) -> None`

控制仿真已提交历史的字段筛选、降采样、环形缓存或磁盘流式写入。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `mode` | `Literal['memory', 'ring_buffer', 'disk_stream']` | 否 | `'memory'` | 位置或关键字 | memory、ring_buffer 或 disk_stream。 |
| `fields` | `tuple[str, ...]` | 否 | `('rotor_displacement', 'rotor_velocity', 'bearing_force')` | 位置或关键字 | 需要保存的结果字段元组。 |
| `downsample` | `int` | 否 | `1` | 位置或关键字 | 正整数采样间隔，1 表示每个提交步都保留。 |
| `capacity` | `int \| None` | 否 | `None` | 位置或关键字 | ring_buffer 的正整数容量；其他模式通常为 None。 |
| `directory` | `Path \| None` | 否 | `None` | 位置或关键字 | disk_stream 输出目录；其他模式通常为 None。 |

输出：`ALB.HistoryPolicy`。构造经过模式与参数一致性校验的 HistoryPolicy。

示例：[选择仿真历史保留策略](#example-history_policy)、[程序化装配仿真拓扑](#example-simulation_programmatic)。

源码：`ALB/api/simulation.py:172`。

公开数据字段：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `mode` | `Literal['memory', 'ring_buffer', 'disk_stream']` | `'memory'` | memory、ring_buffer 或 disk_stream。 |
| `fields` | `tuple[str, ...]` | `('rotor_displacement', 'rotor_velocity', 'bearing_force')` | 需要保存的结果字段元组。 |
| `downsample` | `int` | `1` | 正整数采样间隔，1 表示每个提交步都保留。 |
| `capacity` | `int \| None` | `None` | ring_buffer 的正整数容量；其他模式通常为 None。 |
| `directory` | `Path \| None` | `None` | disk_stream 输出目录；其他模式通常为 None。 |

### `ALB.RotorBearingSimulation(config: 'SimulationConfig') -> 'None'`

拓扑不可变的一次性转子-轴承耦合仿真 facade。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `config` | `SimulationConfig` | 是 | `-` | 位置或关键字 | 经过完整验证的 SimulationConfig。 |

输出：`ALB.RotorBearingSimulation`。构造可运行一次的 RotorBearingSimulation；通常通过 build_simulation() 获得。

示例：[从 JSON5 运行转子-轴承仿真](#example-simulation_from_file)、[程序化装配仿真拓扑](#example-simulation_programmatic)。

源码：`ALB/api/simulation.py:379`。

公开成员：

#### `RotorBearingSimulation.config`

读取本次仿真的不可变输入和拓扑。

输出：`SimulationConfig`。返回 SimulationConfig。

#### `RotorBearingSimulation.latest_result`

读取最近一次完整或失败前已提交的历史，不触发运行。

输出：`SimulationResult`。返回 SimulationResult。


可能异常：

| 类型 | 触发条件 |
| --- | --- |
| `RuntimeError` | run() 尚未产生任何完整或部分已提交结果。 |

#### `RotorBearingSimulation.run() -> 'SimulationResult'`

执行一次耦合仿真，并按 HistoryPolicy 保留真实提交快照。

输入：

无。

输出：`SimulationResult`。成功时返回完整 SimulationResult。


可能异常：

| 类型 | 触发条件 |
| --- | --- |
| `RuntimeError` | 对同一 simulation 对象重复调用 run()。 |
| `SimulationError` | 物理、history、recorder 或 observer 阶段失败；partial_result 可能包含已提交历史。 |

### `ALB.SimulationConfig(rotor: 'RotorProtocol', mounts: 'tuple[BearingMount, ...]', time_step: 'float', steps: 'int', loads: 'tuple[Mapping[str, Any], ...]' = (), history: 'HistoryPolicy' = HistoryPolicy(mode='memory', fields=('rotor_displacement', 'rotor_velocity', 'bearing_force'), downsample=1, capacity=None, directory=None), dependencies: 'CouplingRuntimeDependencies | None' = None) -> None`

一次转子-轴承耦合计算的不可变拓扑、时步、载荷、历史策略和可选依赖。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `rotor` | `RotorProtocol` | 是 | `-` | 位置或关键字 | 实现 RotorProtocol 且使用 dimensional 单位制的转子对象。 |
| `mounts` | `tuple[BearingMount, ...]` | 是 | `-` | 位置或关键字 | 非空或按模型允许的 BearingMount 元组，节点不得重复。 |
| `time_step` | `float` | 是 | `-` | 位置或关键字 | 正的全局量纲时间步，必须与 rotor.dt 一致。 |
| `steps` | `int` | 是 | `-` | 位置或关键字 | 非负整数推进步数；结果通常包含初始提交点。 |
| `loads` | `tuple[Mapping[str, Any], ...]` | 否 | `()` | 位置或关键字 | 可选外载荷描述映射元组。 |
| `history` | `HistoryPolicy` | 否 | `HistoryPolicy(mode='memory', fields=('rotor_displacement', 'rotor_velocity', 'bearing_force'), downsample=1, capacity=None, directory=None)` | 位置或关键字 | 已提交历史的保留策略。 |
| `dependencies` | `CouplingRuntimeDependencies \| None` | 否 | `None` | 位置或关键字 | 面向高级装配的可选依赖对象。 |

输出：`ALB.SimulationConfig`。构造经过 rotor 能力、节点输出和本地时步一致性校验的 SimulationConfig。

示例：[程序化装配仿真拓扑](#example-simulation_programmatic)、[从 JSON5 运行转子-轴承仿真](#example-simulation_from_file)。

源码：`ALB/api/simulation.py:235`。

公开数据字段：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `rotor` | `RotorProtocol` | `-` | 实现 RotorProtocol 且使用 dimensional 单位制的转子对象。 |
| `mounts` | `tuple[BearingMount, ...]` | `-` | 非空或按模型允许的 BearingMount 元组，节点不得重复。 |
| `time_step` | `float` | `-` | 正的全局量纲时间步，必须与 rotor.dt 一致。 |
| `steps` | `int` | `-` | 非负整数推进步数；结果通常包含初始提交点。 |
| `loads` | `tuple[Mapping[str, Any], ...]` | `()` | 可选外载荷描述映射元组。 |
| `history` | `HistoryPolicy` | `HistoryPolicy(mode='memory', fields=('rotor_displacement', 'rotor_velocity', 'bearing_force'), downsample=1, capacity=None, directory=None)` | 已提交历史的保留策略。 |
| `dependencies` | `CouplingRuntimeDependencies \| None` | `None` | 面向高级装配的可选依赖对象。 |

### `ALB.SimulationResult(time: 'FloatArray', rotor_displacement: 'FloatArray', rotor_velocity: 'FloatArray', bearing_force: 'FloatArray', metadata: 'Mapping[str, Any]', convergence: 'ConvergenceStatus' = ConvergenceStatus(residual=0.0, converged=True, iterations=None, message='')) -> None`

转子-轴承仿真中按策略保留的不可变已提交历史。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `time` | `FloatArray` | 是 | `-` | 位置或关键字 | 形状为 (n,) 的已提交时间数组。 |
| `rotor_displacement` | `FloatArray` | 是 | `-` | 位置或关键字 | 形状为 (n, ndof) 或策略过滤后的转子位移历史。 |
| `rotor_velocity` | `FloatArray` | 是 | `-` | 位置或关键字 | 与 rotor_displacement 同形状的速度历史。 |
| `bearing_force` | `FloatArray` | 是 | `-` | 位置或关键字 | 首维为 n 的挂载轴承二维力历史。 |
| `metadata` | `Mapping[str, Any]` | 是 | `-` | 位置或关键字 | 完成状态、提交步数、history 模式等诊断。 |
| `convergence` | `ConvergenceStatus` | 否 | `ConvergenceStatus(residual=0.0, converged=True, iterations=None, message='')` | 位置或关键字 | 整次仿真的收敛或完成状态。 |

输出：`ALB.SimulationResult`。构造 SimulationResult；普通用户通常从 RotorBearingSimulation.run() 获得。

示例：[从 JSON5 运行转子-轴承仿真](#example-simulation_from_file)。

源码：`ALB/api/results.py:196`。

公开数据字段：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `time` | `FloatArray` | `-` | 形状为 (n,) 的已提交时间数组。 |
| `rotor_displacement` | `FloatArray` | `-` | 形状为 (n, ndof) 或策略过滤后的转子位移历史。 |
| `rotor_velocity` | `FloatArray` | `-` | 与 rotor_displacement 同形状的速度历史。 |
| `bearing_force` | `FloatArray` | `-` | 首维为 n 的挂载轴承二维力历史。 |
| `metadata` | `Mapping[str, Any]` | `-` | 完成状态、提交步数、history 模式等诊断。 |
| `convergence` | `ConvergenceStatus` | `ConvergenceStatus(residual=0.0, converged=True, iterations=None, message='')` | 整次仿真的收敛或完成状态。 |

公开成员：

#### `SimulationResult.diagnostics`

读取不可变仿真诊断元数据。

输出：`Mapping[str, Any]`。返回只读键值映射。

#### `SimulationResult.as_bundle() -> 'ResultBundle'`

转换为统一的可持久化 ResultBundle。

输入：

无。

输出：`ResultBundle`。返回包含四组历史数组和完成元数据的不可变结果包。

#### `SimulationResult.write(path: 'str | Path') -> 'ArtifactManifest'`

把仿真历史和诊断写入一个新的制品目录。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `path` | `str \| Path` | 是 | `-` | 位置或关键字 | 目标输出目录。 |

输出：`ArtifactManifest`。返回 ArtifactManifest。

### `UnitSystem`

所有数值积分边界使用的单位制枚举，避免量纲和无量纲值被隐式混用。

- 输出：`UnitSystem`。返回 DIMENSIONAL 或 NONDIMENSIONAL 枚举成员。
- 源码：`ALB/contracts/types.py:12`

枚举值：

| 名称 | 值 |
| --- | --- |
| `DIMENSIONAL` | `dimensional` |
| `NONDIMENSIONAL` | `nondimensional` |

示例：[读取单位制边界](#example-unit_system)。

## 构建与加载函数

### `ALB.bearing_from_file(path: 'str | Path') -> 'Bearing'`

读取严格 0.4 JSON5 轴承文档并一步构建可计算轴承。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `path` | `str \| Path` | 是 | `-` | 位置或关键字 | 顶层 kind=bearing 的 UTF-8 JSON5 文件路径。 |

输出：`Bearing`。返回已完成 runtime 装配的 Bearing。


可能异常：

| 类型 | 触发条件 |
| --- | --- |
| `ConfigurationError` | schema、include、字段或跨字段约束不合法。 |
| `BuildError` | 合法配置无法装配为 runtime。 |

示例：[从 JSON5 构建并计算轴承](#example-bearing_from_file)。

源码：`ALB/api/bearing.py:186`。

### `ALB.build_bearing(config: 'BearingConfig') -> 'Bearing'`

从已验证的不可变配置构建一个可直接计算的轴承 facade。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `config` | `BearingConfig` | 是 | `-` | 位置或关键字 | BearingConfig；不接受普通 dict。 |

输出：`Bearing`。返回 Bearing。


可能异常：

| 类型 | 触发条件 |
| --- | --- |
| `BuildError` | 底层物理、控制、阀、热或 surrogate runtime 装配失败。 |

示例：[程序化配置、参数覆盖与扫描](#example-bearing_programmatic)、[从 JSON5 构建并计算轴承](#example-bearing_from_file)。

源码：`ALB/api/bearing.py:175`。

### `ALB.build_simulation(config: 'SimulationConfig') -> 'RotorBearingSimulation'`

从已验证的仿真配置构建一次性转子-轴承仿真对象。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `config` | `SimulationConfig` | 是 | `-` | 位置或关键字 | SimulationConfig。 |

输出：`RotorBearingSimulation`。返回 RotorBearingSimulation。

示例：[程序化装配仿真拓扑](#example-simulation_programmatic)、[从 JSON5 运行转子-轴承仿真](#example-simulation_from_file)。

源码：`ALB/api/simulation.py:1145`。

### `ALB.load_bearing_config(path: 'str | Path') -> 'BearingConfig'`

读取严格 UTF-8 0.4 bearing 文档，安全合并受限 include 并完成校验。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `path` | `str \| Path` | 是 | `-` | 位置或关键字 | 顶层 bearing JSON5 文件路径；include 必须保持在该目录树内。 |

输出：`BearingConfig`。返回不可变 BearingConfig。


可能异常：

| 类型 | 触发条件 |
| --- | --- |
| `ConfigurationError` | 文件不存在、编码错误、JSON5 无效、include 越界/循环/重复或配置不合法。 |

示例：[从 JSON5 构建并计算轴承](#example-bearing_from_file)。

源码：`ALB/api/config.py:851`。

### `ALB.load_simulation_config(path: 'str | Path') -> 'SimulationConfig'`

读取严格 0.4 simulation 文档，并解析转子、挂载轴承、时间网格、载荷和历史策略。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `path` | `str \| Path` | 是 | `-` | 位置或关键字 | 顶层 kind=simulation 的 JSON5 文件路径。 |

输出：`SimulationConfig`。返回已物化并完成一致性校验的 SimulationConfig。


可能异常：

| 类型 | 触发条件 |
| --- | --- |
| `ConfigurationError` | 文档、资源路径、rotor、mount、时步或 history 策略不合法。 |

示例：[从 JSON5 运行转子-轴承仿真](#example-simulation_from_file)。

源码：`ALB/api/simulation.py:991`。

### `ALB.simulation_from_file(path: 'str | Path') -> 'RotorBearingSimulation'`

读取严格 JSON5 仿真文档并一步构建一次性仿真对象。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `path` | `str \| Path` | 是 | `-` | 位置或关键字 | 顶层 simulation JSON5 文件路径。 |

输出：`RotorBearingSimulation`。返回 RotorBearingSimulation；尚未执行 run()。


可能异常：

| 类型 | 触发条件 |
| --- | --- |
| `ConfigurationError` | 仿真文档或其引用资源不满足 0.4 合同。 |

示例：[从 JSON5 运行转子-轴承仿真](#example-simulation_from_file)。

源码：`ALB/api/simulation.py:1151`。

## 稳定异常

### `ALB.ALBError(*args: object)`

所有用户侧 ALB 稳定异常的基类，适合统一记录或跨层上报。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `args` | `object` | 是 | `-` | 可变位置参数 | 传给 Python Exception 的可变消息或上下文参数。 |

输出：`ALB.ALBError`。构造一个可抛出的 ALB 基础异常实例。

示例：[按稳定异常边界处理失败](#example-error_handling)。

源码：`ALB/api/errors.py:8`。

### `ALB.BuildError(*args: object)`

配置已经通过校验，但对应 runtime 无法完成装配时抛出的稳定异常。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `args` | `object` | 是 | `-` | 可变位置参数 | 传给 Python Exception 的可变消息或上下文参数。 |

输出：`ALB.BuildError`。构造一个可抛出的 BuildError。

示例：[按稳定异常边界处理失败](#example-error_handling)。

源码：`ALB/api/errors.py:16`。

### `ALB.CalculationError(message: 'str', *, failure_snapshot: 'ResultBundle | None' = None) -> 'None'`

轴承输入已接受但物理求解失败时抛出的稳定异常，可携带密封失败快照。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `message` | `str` | 是 | `-` | 位置或关键字 | 面向用户的失败说明。 |
| `failure_snapshot` | `ResultBundle \| None` | 否 | `None` | 仅关键字 | 可选不可变 ResultBundle，保存失败位置诊断。 |

输出：`ALB.CalculationError`。构造一个 CalculationError。

示例：[按稳定异常边界处理失败](#example-error_handling)。

源码：`ALB/api/errors.py:20`。

### `ALB.ConfigurationError(*args: object)`

JSON5 文档、程序化配置或跨字段约束不合法时抛出的稳定异常。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `args` | `object` | 是 | `-` | 可变位置参数 | 传给 Python Exception 的可变消息或上下文参数。 |

输出：`ALB.ConfigurationError`。构造一个可抛出的 ConfigurationError。

示例：[按稳定异常边界处理失败](#example-error_handling)。

源码：`ALB/api/errors.py:12`。

### `ALB.SimulationError(message: 'str', *, partial_result: 'object | None' = None) -> 'None'`

耦合仿真失败时抛出的稳定异常，可携带截至最后真实提交点的部分结果。

输入：

| 名称 | 类型 | 必填 | 默认值 | 调用方式 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `message` | `str` | 是 | `-` | 位置或关键字 | 面向用户的失败说明。 |
| `partial_result` | `object \| None` | 否 | `None` | 仅关键字 | 可选 SimulationResult 或其他密封的部分提交结果。 |

输出：`ALB.SimulationError`。构造一个 SimulationError。

示例：[按稳定异常边界处理失败](#example-error_handling)。

源码：`ALB/api/errors.py:33`。

## 包元数据

### `SCHEMA_VERSION`

bearing 与 simulation JSON5 接受的 schema 版本字符串，独立于 re-alb 包版本。

- 当前值：`0.4.0`
- 输出：`str`。返回当前严格配置契约版本 0.4.0。
- 源码：`-`
- 示例：[检查安装位置和版本](#example-package_version)。

### `__version__`

当前导入的 re-alb 包版本字符串。

- 当前值：`0.4.5`
- 输出：`str`。返回遵循项目版本号的字符串。
- 源码：`-`
- 示例：[检查安装位置和版本](#example-package_version)。
