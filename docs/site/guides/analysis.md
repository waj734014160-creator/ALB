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

谐波压力导数路径当前只验证 dimensional `liquid_film` 和 `active_lubricated`，不支持 thermal wrapper。主动路径要求既有三节点 `CSOrifice` 拓扑；这不是任意 Orifice 插件入口。

!!! warning "能力边界"
    分析 API 会主动拒绝未验证 family、单位或 topology，而不是返回看似完整但无参考保障的系数。
