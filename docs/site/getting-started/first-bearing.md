# 第一个轴承计算

使用仓库中的最小量纲液膜示例：

```python
import ALB

config = ALB.load_bearing_config(
    "docs/api/examples/liquid_film_minimal.json5"
)
bearing = ALB.build_bearing(config)
result = bearing.calculate(
    displacement=(0.0, 0.0),
    velocity=(0.0, 0.0),
    time=0.0,
)

print(result.fx, result.fy)
print(result.convergence.converged)
```

## 这条路径完成了什么

1. `load_bearing_config()` 读取 UTF-8 JSON5，并在运行前验证 family、单位、字段和约束。
2. `build_bearing()` 物化原生模型并返回 ready-to-use `Bearing`。
3. `calculate()` 执行一个时间点，返回 immutable `BearingResult`。
4. `fx`、`fy` 是命名力分量；压力、膜厚、摩擦和诊断信息按 family 可用。

后续时间必须按配置中的 `time_step` 前进：

```python
next_result = bearing.calculate(
    displacement=(1.0e-6, -2.0e-6),
    time=0.001,
)
```

需要重新开始时调用 `bearing.reset()`；它会按同一不可变配置重建 runtime。要改变配置，请使用 `with_overrides()` 创建新配置，而不是修改 `config.spec`。

## 下一步

- [配置与 JSON5](../guides/configuration.md)
- [计算与结果](../guides/calculation.md)
- [完整配置字段参考](../../api/bearing_config_reference.md)
- [根公开 API](../../api/public_api_reference.md)
