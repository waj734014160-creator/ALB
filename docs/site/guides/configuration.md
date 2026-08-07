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

0.4.5 的主动轴承只接受两种阀配置。标准二阶阀直接使用 Hz：

```json5
valve: {
  model: "second_order",
  natural_frequency_hz: 166.0,
  damping_ratio: 0.7,
  delay: 0.0,
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
`third_order`、`static` 均由严格配置边界拒绝。

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

完整查询：[轴承配置字段参考](../../api/bearing_config_reference.md)。可复制文件：[完整示例](../examples.md)。
