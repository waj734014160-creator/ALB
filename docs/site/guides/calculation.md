# 计算与结果

`Bearing` 构建后即可计算，不需要额外 `init()`。普通调用只使用 keyword 参数：

```python
result = bearing.calculate(
    displacement=(x, y),
    velocity=(vx, vy),
    time=t,
    spool=(sx, sy),  # 仅 external_spool
)
```

## 输入契约

- `displacement`：二轴位移；量纲轴承通常为 m，无量纲轴承为 `e/c` 坐标。
- `velocity`：可省略；单位跟随 bearing unit system。
- `time`：必填，首次通常为 `0.0`，后续必须按 `time_step` 严格前进。
- `spool`：归一化二轴命令，只允许 external-spool 模式。

## 读取结果

```python
print(result.fx, result.fy)
print(result.pressure)
print(result.film_thickness)
print(result.friction)
print(result.convergence)
print(result.diagnostics)
```

结果数组和嵌套映射只读。多瓦和主动轴承不存在唯一总压力场时，各瓦数据位于 family-specific `details.values`，不要把内部键视为根 API 的永久承诺。

`bearing.latest_result` 返回最近一次成功结果，不重新求解。首次计算前访问会报错。

## 持久化与失败

```python
manifest = result.write("outputs/case_001")
```

数值失败使用 `CalculationError`；若有可恢复证据，可从 `failure_snapshot` 读取已计算坐标、力、残差和诊断：

```python
try:
    result = bearing.calculate(displacement=(x, y), time=t)
except ALB.CalculationError as exc:
    if exc.failure_snapshot is not None:
        print(exc.failure_snapshot.metadata)
```
