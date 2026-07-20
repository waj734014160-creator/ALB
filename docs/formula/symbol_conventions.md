# 物理符号命名约定

本文档记录 ALB 中物理量的统一命名规则，后续新增模型、配置和结果字段应遵守这些约定。

## 基本规则

- 物理量命名优先使用明确的英文物理符号，不混用拼音、缩写别名和历史变量名。
- 所有初始值、参考值、冻结基准值统一使用 `0` 后缀，例如 `miu0`、`lambda0`。
- 希腊字母统一使用英文拼写作为字段名，例如 `lambda`、`theta`、`beta`。
- Python 保留字不能作为局部变量名时，局部变量使用带语义的替代名，例如 `lambda_value`；字典键仍可使用 `"lambda"`。
- 不再为润滑模型保留 `u`、`u_ref`、`vx`、`vx_ref` 等历史别名。

## 润滑模型

| 物理意义 | 标准命名 | 说明 |
| --- | --- | --- |
| 动力黏度 | `miu` | 替代历史 `u`。 |
| 初始/参考动力黏度 | `miu0` | 替代历史 `u_ref`、`miu_ref`。 |
| Reynolds 方程速度系数/轴承数 | `lambda` | 替代历史 `vx`。 |
| 初始/参考 Reynolds 方程速度系数 | `lambda0` | 替代历史 `vx_ref`。 |
| 温升特征系数 | `theta_e` | 使用英文希腊字母 `theta`，保留物理下标 `e`。 |
| 黏温系数 | `beta` | 配置中的量纲形式。 |
| 无量纲黏温系数 | `beta_nondim` | 无量纲形式。 |

## 配置与接口

- `HydConfig` 使用 `miu` 作为黏度输入。
- `film_args_trans`、`FilmModel`、`NewtonFilm`、`SkfemNewtonFilm` 使用 `miu` 作为构造参数。
- 模型运行参数 `model.args` 中只写入 `miu`、`miu0`、`lambda`、`lambda0`。
- 热耦合冻结基准时只同步 `miu0` 与 `lambda0`，不再写入 `u_ref` 或 `vx_ref`。

## Orifice 信息接口

- 所有供油孔模型继承 `BaseOrifice` 或提供同形接口。
- 供油孔信息统一通过 `flow_info(model=None)` 提供，不再使用 `thermal_flow_info`。
- 固定参考流量尺度为
  $Q_w=p_sc^3/(12\mu_0l_r)$，单位 m$^3$/s；面内通量尺度为
  $Q_f=Q_w/(l_rR)$，单位 m$^2$/s。代码中使用 `ThermalNondimScales.qf`；
  `flow_scale` 仅为只读兼容别名。
- 单孔体积流量严格按 $Q_i=q_{n,i}Q_w$ 换算，不另设 `Qvol0`。
- `flow_info` 返回字典，包含三类信息：
  - `structure`: 供油孔结构参数，如位置、供油压力、流量系数、几何参数。
  - `flow_params`: 每个条目明确包含 `position_nondim`、`position_dim`、
    `q_nondim`、`q_vol` 和同一个 `qw`。
  - `flow`: 有量纲兼容三元组列表 `(x_dim, z_dim, q_vol)`；无量纲热核不得消费该字段。
- 无量纲热核只接收 `(position_nondim, q_nondim)`，并按
  `K[j,j] += q_nondim`、`f[j] += q_nondim*T_supply_nondim` 装配点源。
- 热结果字段 `q_orifice_total_nondim` 表示无量纲总流量，
  `q_orifice_total_vol` 和兼容字段 `q_orifice_total` 均表示 m$^3$/s。

## 非润滑物理符号例外

- 控制器中的 `u` 表示控制输入，不是黏度。
- 轨道/动力学输出中的 `ux`、`uy`、`vx`、`vy` 表示位移与速度分量，不是 Reynolds 方程中的 `lambda`。
- scikit-fem 弱式函数中的形式参数 `u`、`v` 是有限元试探函数和测试函数的标准记号，不表示黏度。
