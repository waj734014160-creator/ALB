# 分析工作流

每个 `Bearing` 都提供 `bearing.analysis`。分析使用 fresh runtime，不覆盖 `bearing.latest_result`。

## 椭圆轨迹

```python
trajectory = ALB.EllipseTrajectory(
    center=(0.0, 0.0),
    semi_axes=(1.0e-6, 0.5e-6),
    direction="forward",
)
result = bearing.analysis.trace_orbit(
    trajectory,
    time_grid,
    frequency_hz=125.0,
)
```

结果包含 `time`、`displacement`、`velocity`、`force` 和逐点收敛数组。

## 静态平衡点

```python
options = ALB.EquilibriumOptions(
    relative_tolerance=1.0e-4,
    max_iterations=30,
)
result = bearing.analysis.find_equilibrium(
    load=(1000.0, -5000.0),
    options=options,
)
```

载荷必须非零。external-spool 配置不能由平衡求解器自动推断 spool。

## 动态系数

`dynamic_coefficients()` 使用正反涡动响应识别刚度和阻尼。时间网格必须均匀，目标频率必须落在非 DC FFT bin 且低于 Nyquist。

- 网格和频率不合法：`ValueError`。
- 轨迹未收敛、位移矩阵奇异/病态或反演失败：带 `failure_snapshot` 的 `CalculationError`。

## 谐波线性化

`harmonic_linearize()` 在给定工作点直接装配方程导数，返回刚度和阻尼。
量纲液膜及不启用热模型的主动润滑轴承沿用已有压力导数算法；启用热模型的
主动润滑轴承使用压力、温度、节流器的耦合解析方程。

以下示例从仓库根目录运行，配置和工作点来自随工具提供的数值验证算例：

```python
import ALB

bearing = ALB.bearing_from_file("tools/analysis/thermal_harmonic_example.json5")
result = bearing.analysis.harmonic_linearize(
    operating_point=(10e-6, -60e-6),
    excitation_frequency=50.0,
    spool=(-0.08838834764831843, -0.12374368670764582),
)
K = result.values["stiffness"]
C = result.values["damping"]
G = result.values["spool_transfer"]
result.write("outputs/harmonic_50hz")
```

`operating_point` 使用 m，激励频率使用 Hz，`spool` 为归一化阀芯位移。
`external_spool` 配置必须传入 `spool`；内部控制配置从静态控制状态取得基准阀芯，
此时不传 `spool`。每次分析独立求解基态，可改变工作点和激励频率重新计算。

| 输出 | 含义和单位 |
| --- | --- |
| `stiffness`、`damping` | 2×2 实矩阵，N/m、N·s/m |
| `spool_transfer` | 热耦合路径的 2×2 复矩阵，N/归一化阀芯位移；`spool_jacobian` 为同值键 |
| `dynamic_stiffness_real`、`dynamic_stiffness_imag` | 复动态刚度的实部 K 和虚部 ωC，N/m |
| `static_force` | 严格耦合基态的力，N |
| `production_static_force` | 重求基态前的生产求解器力，N |
| `pad_base_state`、`pad_pressurized` | 各瓦块的基态数组和固定有压节点掩码 |
| `metadata["pad_diagnostics"]` | 各瓦块的互补残差、活动节点数、迭代历史和线性方程残差 |

力的约定为 `δF = -(K+iωC)δx + Gδspool`，这些系数不包含控制器或伺服阀动态。
复数 G 应与同频输入复幅值相乘，再重建实值响应。

热惯性由配置 `thermal.transient_enabled` 决定。开启后装配 `J+iωM`，因此
K、C、G 随频率变化；关闭后使用稳态热切线。数值时间步不用于代替连续频域的 iω。
SUPG 稳定化参数在生产基态冻结；温度入口和供油冷源分支在基态固定。
基态先解压力互补问题，检查不存在双活动空化节点，随后固定活动集求六列解析右端。

热耦合入口当前支持量纲四瓦主动轴承、每瓦一个三支路 `CSOrifice`、完整节点黏温
耦合、传统张量网格（不填写 `mesh_type`）、零压力非周期周界及 Reynolds 空化。
供油支持 `nearest_node` 和 `element_shape`，压力和温度均使用实际孔位。
半耦合、显式三角形/四边形高阶网格、零阀芯换向点和不满足严格互补条件的基态
会明确报错。严格基态须位于生产温度限幅范围内，并避开黏度限幅切换点。
基态或频域求解失败时，`CalculationError.failure_snapshot` 保留诊断。

也可直接使用命令行工具，输出目录必须尚不存在：

```powershell
E:/Anaconda2023/envs/ALB/python.exe tools/analysis/run_harmonic_linearization.py `
  --config tools/analysis/thermal_harmonic_example.json5 `
  --operating-point 0.00001 -0.00006 --frequency-hz 50 `
  --spool -0.08838834764831843 -0.12374368670764582 `
  --output outputs/harmonic_50hz
```
