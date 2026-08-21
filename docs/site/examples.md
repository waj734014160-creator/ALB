# 完整配置示例

以下 UTF-8 JSON5 文件由 integration smoke test 通过公开 facade 加载、构建并至少计算一次。它们不含机器绝对路径或 legacy key。

## 量纲液膜

[下载 `liquid_film_minimal.json5`](../api/examples/liquid_film_minimal.json5){ .md-button }

```json5
--8<-- "docs/api/examples/liquid_film_minimal.json5"
```

## 量纲气膜

[下载 `gas_film_minimal.json5`](../api/examples/gas_film_minimal.json5){ .md-button }

```json5
--8<-- "docs/api/examples/gas_film_minimal.json5"
```

## 主动润滑 PID

[下载 `active_lubricated_pid.json5`](../api/examples/active_lubricated_pid.json5){ .md-button }

```json5
--8<-- "docs/api/examples/active_lubricated_pid.json5"
```

## 嵌套多瓦

[下载 `multi_pad_nested.json5`](../api/examples/multi_pad_nested.json5){ .md-button }

```json5
--8<-- "docs/api/examples/multi_pad_nested.json5"
```

## 代理轴承资源模板

[下载 `surrogate_bearing.json5`](../api/examples/templates/surrogate_bearing.json5){ .md-button }

```json5
--8<-- "docs/api/examples/templates/surrogate_bearing.json5"
```

!!! warning "需要用户资源"
    这是经过 JSON5 结构检查的资源模板，不是独立可运行 smoke。请把 `models/albnn_package` 替换为实际 ALBNN model package，并按 package 合同补齐 runtime parameters 后再调用 `load_bearing_config` 或 `bearing_from_file`。

## ROSS Excel 仿真资源模板

[下载 `simulation_ross_excel.json5`](../api/examples/templates/simulation_ross_excel.json5){ .md-button }

```json5
--8<-- "docs/api/examples/templates/simulation_ross_excel.json5"
```

!!! warning "需要用户资源"
    这是经过 JSON5 结构与占位路径检查的模板。`resources/rotor.xlsx` 和两个 `bearings/*.json5` 必须由用户提供，且均须位于配置文件的资源根目录内；因此测试不会把该模板伪装成可直接构建的仿真。字段含义和结果形状见[仿真配置参考](../api/simulation_config_reference.md)。
