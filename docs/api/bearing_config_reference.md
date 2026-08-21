# ALB 轴承配置字段参考

## 文档角色

- 角色：面向普通用户的轴承配置字段、单位、缺省值和用途说明。
- 目的：让用户不必阅读内部 `HydConfig`、`GasConfig` 或装配代码即可编写 `BearingConfig` 和 JSON5。
- 允许更新：公开配置字段、单位、缺省值、约束和结果字段。
- 禁止更新：内部临时变量、单次运行状态和未进入公开配置的实验参数。
- 更新时机：`ALB/api/_config_fields.py`、原生配置缺省值或公开装配规则发生变化时。
- 事实来源：`ALB/api/_config_fields.py`、`ALB/api/config.py`、`ALB/api/building.py` 和 `ALB/config/` 中的原生配置类。

配置可以直接传给 `ALB.BearingConfig(spec)`，也可以放在严格 0.4 JSON5
文档的 `spec` 节点下。字段名采用完整英文，不使用内部求解器的 `e`、`c`、
`ps`、`nx` 等缩写。未写字段时使用下表缺省值；这不是“自动猜测”，而是固定
的原生配置缺省值。

## 顶层字段

| 字段 | 类型/单位 | 是否必填 | 含义 |
| --- | --- | --- | --- |
| `family` | 字符串 | 是 | 轴承族：`liquid_film`、`active_lubricated`、`gas_film`、`multi_pad` 或 `surrogate`。 |
| `unit_system` | 字符串 | 是 | `dimensional` 表示量纲输入输出；`nondimensional` 表示无量纲输入输出。气膜当前只支持量纲制。 |
| `time_step` | s | 是 | 轴承局部时间步，必须为有限正数；热、阀和控制子模型使用同一时间步。 |
| `node` | 非负整数或 `null` | 否 | 转子耦合节点。独立轴承计算可以为 `null`；仿真挂载节点由 `BearingMount.node` 明确给出。 |
| `film` | 映射 | 液膜/主动/气膜必填 | 液膜或气膜的几何、物性、网格和求解参数。 |
| `restrictors` | 映射或 `null` | 液膜可选、主动必填 | 液膜节流孔或主动轴承节流器。 |
| `thermal` | 映射或 `null` | 液膜/主动可选 | 热黏耦合参数；`null` 表示关闭热模型。 |
| `pads` | 列表 | 多瓦必填 | 子瓦配置或相对配置文件路径；至少包含一个子瓦。 |
| `model_package` | 映射 | 代理模型必填 | ALBNN 模型包路径和数据增强开关。 |
| `runtime` | 映射 | 代理模型可选 | 代理模型运行参数、固定阀芯或外部阀芯模式。 |

## 量纲液膜 `film`

下列缺省值来自 `HydConfig`。主动润滑轴承的单瓦也使用这些物理量；多瓦角度
由装配拓扑进一步确定。

| 字段 | 单位 | 缺省值 | 含义 |
| --- | --- | --- | --- |
| `eccentricity` | 1 | `0.0` | 初始偏心率 `e/c`，范围 `[0, 1)`。 |
| `attitude_angle_deg` | deg | `0` | 初始偏心方向角。 |
| `rotation_frequency_hz` | Hz | `50` | 轴颈转频，必须为正数。 |
| `start_angle_deg` | deg | `0` | 单个液膜区域的周向起始角。 |
| `arc_angle_deg` | deg | `360` | 液膜区域的周向角跨度，必须为正数。 |
| `axial_length_ratio` | 1 | `2` | 建模轴向长度与轴承长度的比值。 |
| `circumferential_elements` | 个 | `59` | 周向有限元数量，至少为 2。节点数为该值加 1。 |
| `axial_elements` | 个 | `39` | 轴向有限元数量，至少为 2。节点数为该值加 1。 |
| `mesh_type` | 字符串 | 不启用显式网格 | 显式压力-热同网格拓扑：`triangular` 或 `quadrilateral`；必须与 `element_order` 同时提供。 |
| `element_order` | 整数 | 不启用显式网格 | 显式压力-热基函数阶次：`1` 或 `2`；必须与 `mesh_type` 同时提供。 |
| `viscosity` | Pa·s | `0.0195` | 润滑油动力黏度。变量在内部统一命名为 `miu`。 |
| `clearance` | m | `8e-5` | 轴承径向间隙 `c`。 |
| `radius` | m | `0.04` | 轴颈半径。 |
| `length` | m | `0.06` | 轴承实际轴向长度。 |
| `supply_pressure` | Pa | `7e6` | 供油/参考压力，必须为正数。压力结果按此值量纲化。 |
| `density` | kg/m³ | `872` | 润滑油密度。 |
| `reynolds_boundary` | 布尔或字符串 | `true` | `true` 启用 Reynolds 空化边界；也可使用 `"half_reynold"`。 |
| `continuous_boundary` | 布尔 | `true` | 是否连接周向首尾边界。部分瓦通常由其原生配置改为 `false`。 |
| `ambient_pressure` | Pa | `0` | 环境边界压力。 |
| `solver_tolerance` | 1 | `1e-10` | 液膜非线性迭代的相对收敛容差，必须为正数。 |
| `max_iterations` | 次 | `120` | 液膜最大非线性迭代次数。 |
| `relaxation` | 1 | `0.8` | 固定迭代松弛因子。 |
| `vibration_enabled` | 布尔 | `false` | 是否包含挤压膜速度项。 |
| `x_velocity` | m/s | `null` | 初始轴心 x 方向速度；未给出时由输入样本提供。 |
| `y_velocity` | m/s | `null` | 初始轴心 y 方向速度；未给出时由输入样本提供。 |
| `whirl_ratio` | 1 | `1` | 涡动频率与轴颈转频之比。 |
| `solver` | 字符串 | `"newton"` | 求解器：`newton`、`gauss`、`lsq` 或 `skfem_newton`。 |
| `save_pressure` | 布尔 | `false` | 是否在原生持久化输出中保存压力；不影响 `BearingResult.pressure`。 |
| `save_thickness` | 布尔 | `false` | 是否在原生持久化输出中保存膜厚；不影响 `BearingResult.film_thickness`。 |
| `gauss_points` | 次 | `50` | Gauss 方法的迭代/积分点数量。 |
| `gauss_relaxation` | 1 | `1.2` | Gauss 方法松弛因子。 |
| `gauss_tolerance` | 1 | `1e-3` | Gauss 方法允许残差。 |
| `pad_bias_deg` | deg | `0` | 瓦块相对基准位置的角偏置。 |
| `adaptive_damping` | 布尔或映射 | `null` | 自适应松弛配置；`null` 表示使用固定 `relaxation`。 |

显式网格模式当前只用于量纲 `active_lubricated` 稳态热耦合，且要求
`solver: "skfem_newton"`、`continuous_boundary: false`、
`thermal.iter_method: "direct"` 和 `thermal.transient_enabled: false`。压力与温度
共享拓扑、阶次和自由度位置，三角 P1/P2 与四边形 Q1/Q2 均固定使用 8 阶积分；
不满足这些边界的配置在构建前直接拒绝。未填写两个显式字段时仍走原有 Q1
压力和三角 P1 热模型。供油孔如何耦合到这些自由度由
`restrictors.flow_projection` 独立控制，不能根据是否使用显式网格自动推断。

## 无量纲液膜 `film`

无量纲配置中的几何/网格字段与上表含义相同，但压力、膜厚、速度等为比值。
`scale_*` 字段只负责把无量纲结果换算为工程单位，不改变无量纲方程。

| 字段 | 单位 | 缺省值 | 含义 |
| --- | --- | --- | --- |
| `bearing_number` | 1 | `1.0` | 当前工况无量纲轴承数。 |
| `reference_bearing_number` | 1 | `null` | 参考轴承数；未给出时由原生模型按当前值处理。 |
| `length_ratio` | 1 | `1.0` | 轴承长度与轴颈半径之比。 |
| `arc_angle_deg` | deg | `360` | 液膜周向角跨度。 |
| `axial_length_ratio` | 1 | `2.0` | 建模轴向长度比。 |
| `circumferential_elements` | 个 | `59` | 周向有限元数量，至少为 2。 |
| `axial_elements` | 个 | `39` | 轴向有限元数量，至少为 2。 |
| `pad_bias_deg` | deg | `0.0` | 瓦块角偏置。 |
| `eccentricity` | 1 | `0.0` | 初始偏心率，范围 `[0, 1)`。 |
| `attitude_angle_deg` | deg | `0.0` | 初始偏心方向角。 |
| `reynolds_boundary` | 布尔或字符串 | `true` | Reynolds 空化边界开关。 |
| `continuous_boundary` | 布尔 | `true` | 周向首尾连续边界开关。 |
| `ambient_pressure` | `p/ps` | `0.0` | 无量纲环境压力。 |
| `solver_tolerance` | 1 | `1e-10` | 非线性迭代相对容差。 |
| `max_iterations` | 次 | `120` | 最大非线性迭代次数。 |
| `relaxation` | 1 | `0.8` | 固定迭代松弛因子。 |
| `x_velocity` | 1 | `0.0` | 无量纲轴心 x 速度。 |
| `y_velocity` | 1 | `0.0` | 无量纲轴心 y 速度。 |
| `whirl_ratio` | 1 | `1.0` | 涡动频率比。 |
| `x_center_velocity` | 1 | `0.0` | 无量纲移动坐标系 x 速度。 |
| `y_center_velocity` | 1 | `0.0` | 无量纲移动坐标系 y 速度。 |
| `scale_viscosity` | Pa·s | `1.0` | 结果量纲化使用的黏度。 |
| `scale_clearance` | m | `1.0` | 位移和膜厚量纲化使用的间隙。 |
| `scale_radius` | m | `1.0` | 结果量纲化使用的轴颈半径。 |
| `scale_length` | m | `null` | 结果量纲化使用的轴承长度。 |
| `scale_pressure` | Pa | `1.0` | 压力和承载力量纲化使用的压力尺度。 |
| `scale_density` | kg/m³ | `1.0` | 结果量纲化使用的密度。 |
| `scale_speed_rpm` | rpm | `null` | 结果量纲化使用的转速。 |
| `save_pressure` | 布尔 | `false` | 原生持久化压力开关。 |
| `save_thickness` | 布尔 | `false` | 原生持久化膜厚开关。 |
| `adaptive_damping` | 布尔或映射 | `null` | 自适应松弛配置。 |

## 气膜附加字段

气膜使用量纲液膜公共字段，并增加下列字段。气膜缺省 `solver` 为
`"skfem_newton"`，`ambient_pressure` 为 `1.0`。

| 字段 | 单位 | 缺省值 | 含义 |
| --- | --- | --- | --- |
| `ambient_pressure_pa` | Pa | `101325` | 绝对环境气压。 |
| `gas_frequency_ratio` | 1 | `1.0` | 气膜频率比系数。 |
| `foil_enabled` | 布尔 | `false` | 是否计算柔性箔片变形。 |
| `texture_enabled` | 布尔 | `false` | 是否启用表面织构。 |
| `texture_type` | 整数/名称 | `1` | 织构几何类型。 |
| `texture_depth` | m | `null` | 织构绝对深度。 |
| `texture_depth_ratio` | 1 | `null` | 织构深度与间隙之比；与绝对深度按模型规则选用。 |
| `texture_circumferential_fraction` | 1 | `0.0` | 周向织构覆盖比例。 |
| `texture_axial_fraction` | 1 | `0.0` | 轴向织构覆盖比例。 |
| `texture_start_theta_index` | 网格索引 | `1` | 织构开始的周向网格索引。 |
| `texture_start_axial_index` | 网格索引 | `1` | 织构开始的轴向网格索引。 |
| `foil_relaxation` | 1 | `0.5` | 箔片变形迭代松弛因子。 |
| `foil_tolerance` | 1 | `1e-6` | 箔片变形收敛容差。 |
| `foil_stiffness` | N/m³ | `null` | 箔片分布支撑刚度；未给出时由几何和材料推导。 |
| `foil_pitch` | m | `0.004572` | 箔片支撑周向节距。 |
| `foil_half_length` | m | `0.001717` | 箔片模型半长。 |
| `foil_thickness` | m | `0.00013` | 箔片厚度。 |
| `foil_young_modulus` | Pa | `2.1e11` | 箔片杨氏模量。 |
| `foil_poisson_ratio` | 1 | `0.3` | 箔片泊松比。 |

## 液膜节流孔 `restrictors`

`liquid_film` 可以把该节点设为 `null`，表示纯动压/静压膜而不附加节流孔。
存在节流孔时，`radius` 与 `flow_coefficient` 必须且只能提供一个。
该轴承族不接受主动轴承专用的 `flow_projection` 字段。

| 字段 | 单位 | 缺省值 | 含义 |
| --- | --- | --- | --- |
| `positions` | 无量纲坐标列表 | 必填 | 每个节流孔的 `(周向比例, 轴向比例)`。 |
| `radius` | m | 与 `flow_coefficient` 二选一 | 节流孔半径。 |
| `flow_coefficient` | 1 | 与 `radius` 二选一 | 已无量纲化的节流流量系数。 |
| `pressure` | Pa 或 `p/ps` | 使用液膜供压 | 节流孔供压。 |
| `discharge_coefficient` | 1 | `0.6` | 孔口流量系数。 |

## 主动润滑字段

主动轴承除 `film` 外还需要 `restrictors`、`tank`、`valve` 和 `control`。

- `restrictors.positions`：节流器位置列表。
- `restrictors.supply_pressure` / `tank_pressure`：Pa；量纲主动轴承缺省分别继承
  液膜供压和 `0`。
- `restrictors.flow_coefficient`：无量纲流量系数。
- `restrictors.orifice_diameter` / `orifice_length` / `valve_area`：m、m、m²，
  都必须为正数。
- `restrictors.discharge_coefficient`：孔口流量系数，缺省 `0.6`。
- `restrictors.flow_projection`：供油孔点流量到压力和温度自由度的投影方式，
  缺省为 `"nearest_node"`，把每个孔的全部流量装配到最近节点并保持历史结果；
  `"element_shape"` 在孔所在单元使用原生形函数。Q1、P1、P2、Q2 分别作用于
  4、3、6、9 个局部自由度。两种方式都守恒孔口总流量，且都仍是集中点源，
  不是有限孔径面源。
- 无量纲主动轴承还可使用 `base_flow_coefficient`、
  `spool_flow_coefficient` 和 `pressure_flow_coefficient`。
- `tank.x_range`、`z_range`：油腔在局部坐标中的范围；
  `depth_ratio`：油腔深度与间隙之比。
- `valve.model: second_order`：必须输入 `natural_frequency_hz`（Hz）和
  `damping_ratio`（1），可选 `delay`（s，缺省 `0`）。运行时使用
  `tw = 1 / (2*pi*natural_frequency_hz)` 保持既有二阶传递函数。
- `valve.model: static`：无记忆、单位增益阀，只允许 `model` 字段。
- `valve.model: transfer_function`：必须输入 `numerator` 和 `denominator`；
  两者都是按连续时间变量 `s` 降幂排列的有限实数多项式系数。分子包含完整
  增益及任何有理延迟近似，不再接受独立 `delay`。传递函数必须因果且 proper，
  即分子阶数不得高于分母阶数。
- `control.mode`：`pid`、`fuzzy_pid`、`uncontrolled` 或 `external_spool`。
  `pid` 模式的 `gains` 包含 `kp`、`ki`、`kd` 和 `feedforward`；
  `frequency_hz` 是控制频率；`sensor_angles_deg` 是两个传感器角度。
- 模糊 PID 的 `error_range`、`delta_error_range`、`kp_range`、`ki_range`、
  `kd_range` 和 `rule_path` 分别定义输入/输出范围及规则文件。
- `transforms.displacement_to_control` 与 `velocity_to_control` 是从物理输入到
  控制器输入的显式比例；不提供时使用装配层固定缺省值。

## 热模型 `thermal`

| 字段 | 单位/类型 | 缺省值 | 含义 |
| --- | --- | --- | --- |
| `t_in` | °C | `40` | 入口油温。 |
| `t_ref` | °C | `null` | 黏温关系参考温度；未给出时使用模型参考值。 |
| `miu0` | Pa·s | `null` | 参考温度下黏度；未给出时继承液膜黏度。 |
| `beta` | 1/°C | `0.03` | 量纲黏温系数。 |
| `k_lub` | W/(m·K) | `0.0` | 润滑油导热系数。 |
| `cp_lub` | J/(kg·K) | `2000` | 润滑油比热。 |
| `max_delta_t` | °C | `80` | 允许的最大温升。 |
| `heat_partition` | 1 | `0.9` | 摩擦热进入润滑油的比例。 |
| `relax` | 1 | `0.5` | 热-流体外迭代松弛因子。 |
| `tol` | 1 | `1e-6` | 热迭代收敛容差。 |
| `max_iter` | 次 | `60` | 热迭代最大次数。 |
| `adaptive_damp` | 布尔或映射 | `null` | 热迭代自适应松弛配置。 |
| `miu_min` / `miu_max` | Pa·s | `1e-4` / `1.0` | 黏度截断下限和上限。 |
| `coupling` | 字符串 | `"full"` | 热-流体耦合模式。 |
| `t_supply` | °C | `null` | 供油温度；未给出时使用入口温度。 |
| `axial_side_bc` | 字符串 | `"inflow_fixed"` | 轴向侧边界条件。 |
| `axial_side_t` | °C | `null` | 轴向侧边界固定温度。 |
| `supg` | 布尔 | `true` | 是否使用 SUPG 稳定化。 |
| `delta_t_scale` | °C | `null` | 无量纲温升尺度。 |
| `beta_nondim` | 1 | `null` | 无量纲黏温系数。 |
| `t_ref_nondim` | 1 | `null` | 无量纲参考温度。 |
| `transient_enabled` | 布尔 | `false` | 是否启用热瞬态项。 |
| `iter_method` | 字符串 | `"direct"` | 热方程迭代方法。 |
| `thermal_newton_max_iter` | 次 | `30` | 热 Newton 最大次数。 |
| `thermal_newton_tol` | 1 | `null` | 热 Newton 容差；未给出时使用热模型默认关系。 |
| `thermal_newton_damp` | 1 | `1.0` | 热 Newton 初始阻尼。 |
| `thermal_newton_min_damp` | 1 | `0.001` | 热 Newton 线搜索最小阻尼。 |
| `thermal_newton_line_search` | 布尔 | `false` | 是否启用热 Newton 线搜索。 |
| `miu_update` | 字符串 | `"linear"` | 黏度更新方式。 |
| `miu_update_max_ratio` | 1 | `null` | 单次黏度更新的最大比例。 |
| `heat_partition_steps` | 元组 | `null` | 分阶段热分配比例。 |

`thermal.dt` 和内部 `args_nodim` 不属于公开字段：装配器分别从顶层
`time_step` 和 `unit_system` 唯一推导，用户不应重复填写。

## 结果单位

- `BearingResult.force`：量纲轴承为 N；无量纲轴承为对应无量纲承载力。
- `BearingResult.friction`：有摩擦输出时为量纲/无量纲总摩擦力。
- `BearingResult.pressure`：量纲液膜为 Pa，无量纲液膜为 `p/ps`。
- `BearingResult.film_thickness`：量纲液膜为 m，无量纲液膜为 `h/c`。
- 多瓦和主动轴承不存在唯一的“总压力场”，因此各瓦压力和膜厚分别位于
  `result.details.values["pad_pressure"]` 和
  `result.details.values["pad_film_thickness"]`。
- 网格字段的二维形状和单位也记录在 `result.diagnostics` 中。
- 显式网格结果还记录 `mesh_type`、`element_order`、`integration_order`、
  `actual_element_count`、`pressure_dofs` 和 `temperature_dofs`。

## 源码同步字段合同

<!-- Generated by tools/docs/generate_bearing_config_reference.py. -->

- 配置字段组：`17`
- 源码合同摘要：`sha256:6614bc678d6663a3`
- 对应规则：字段名、类型、单位、必填性、默认值、可选值、约束、适用范围和原生映射均来自 `ALB.api._config_fields`。
- 阅读方式：上文中文章节解释物理语义和跨字段关系；下表逐项给出可执行源码合同，英文列保留源码原文。

<a id="config-group-document"></a>
### JSON5 文档外壳

顶层文档和 profile 共用的版本、角色、include 与 spec 合同。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `schema_version` | `string` | `version` | "0.4.0" | ["0.4.0"] | - | 全部 | 与公开字段同名 | Exact document schema version. |
| `kind` | `string` | `name` | 必填 | ["bearing", "bearing_profile"] | - | 全部 | 与公开字段同名 | Document role at the top level or in an include. |
| `includes` | `array[string]` | `path list` | [] | - | relative, unique, acyclic, and contained below document root | 全部 | 与公开字段同名 | Ordered relative bearing-profile paths merged before spec. |
| `spec` | `object` | `mapping` | 必填 | - | - | 全部 | 与公开字段同名 | Bearing specification overlaid after included profiles. |

<a id="config-group-spec"></a>
### 轴承 spec 顶层

轴承族、单位制、时间步和按 family 选择的子配置。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `family` | `string` | `name` | 必填 | ["liquid_film", "active_lubricated", "gas_film", "multi_pad", "surrogate"] | - | 全部 | 与公开字段同名 | Bearing runtime family discriminator. |
| `unit_system` | `string` | `name` | 必填 | ["dimensional", "nondimensional"] | gas_film requires dimensional | 全部 | 与公开字段同名 | Input and output unit system for this bearing. |
| `time_step` | `number` | `s or local time unit` | 必填 | - | finite and > 0 | 全部 | 与公开字段同名 | Bearing-local integration time step. |
| `node` | `integer or null` | `index` | null | - | >= 0 when provided | 全部 | 与公开字段同名 | Optional rotor node used by direct coupling metadata. |
| `film` | `object` | `mapping` | 适用时必填 | - | - | liquid_film, active_lubricated, gas_film | 与公开字段同名 | Film geometry, material, mesh, and solver section. |
| `restrictors` | `object or null` | `mapping` | null | - | - | liquid_film, active_lubricated | 与公开字段同名 | Optional liquid restrictors or required active restrictors. |
| `thermal` | `object or null` | `mapping` | null | - | - | liquid_film, active_lubricated | 与公开字段同名 | Optional thermo-hydrodynamic coupling section. |
| `tank` | `object` | `mapping` | 适用时必填 | - | - | active_lubricated | 与公开字段同名 | Active-bearing recess/tank geometry. |
| `valve` | `object` | `mapping` | 适用时必填 | - | - | active_lubricated | 与公开字段同名 | Active-bearing servo-valve model. |
| `control` | `object` | `mapping` | 适用时必填 | - | - | active_lubricated | 与公开字段同名 | Active-bearing controller declaration. |
| `transforms` | `object` | `mapping` | {} | - | - | active_lubricated | 与公开字段同名 | Optional physical-to-controller input transforms. |
| `pads` | `array[string or object]` | `list` | 适用时必填 | - | at least one item; child time_step and unit_system must agree | multi_pad | 与公开字段同名 | Nonempty child bearing specs or relative bearing-file paths. |
| `model_package` | `object` | `mapping` | 适用时必填 | - | - | surrogate | 与公开字段同名 | Validated ALBNN package location and augmentation override. |
| `runtime` | `object` | `mapping` | {} | - | - | surrogate | 与公开字段同名 | Surrogate runtime parameters and spool source. |

<a id="config-group-film_dimensional"></a>
### 量纲液膜 film

量纲液膜、主动润滑单瓦和气膜继承的几何、物性、网格及求解参数。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `eccentricity` | `number` | `1` | 0.0 | - | 0 <= value < 1 | 全部 | `e` | Initial eccentricity ratio e/c. |
| `attitude_angle_deg` | `number` | `deg` | 0.0 | - | finite | 全部 | `angle` | Initial eccentricity attitude angle. |
| `rotation_frequency_hz` | `number` | `Hz` | 50.0 | - | > 0 | 全部 | `freq` | Journal rotation frequency. |
| `start_angle_deg` | `number` | `deg` | 0.0 | - | finite | 全部 | `x0` | Circumferential start angle of the film domain. |
| `arc_angle_deg` | `number` | `deg` | 360.0 | - | > 0 | 全部 | `lx` | Circumferential angular span of the film domain. |
| `axial_length_ratio` | `number` | `1` | 2.0 | - | > 0 | 全部 | `lz` | Modeled axial length divided by bearing length. |
| `circumferential_elements` | `integer` | `count` | 59 | - | >= 2 | 全部 | `nx` | Finite-element count around the film arc. |
| `axial_elements` | `integer` | `count` | 39 | - | >= 2 | 全部 | `nz` | Finite-element count along the bearing axis. |
| `mesh_type` | `string or null` | `name` | null | ["triangular", "quadrilateral"] | required together with element_order | 全部 | `mesh_type` | Explicit pressure/thermal mesh topology. |
| `element_order` | `integer or null` | `count` | null | [1, 2] | 1 or 2; required together with mesh_type | 全部 | `element_order` | Polynomial order of the explicit pressure/thermal basis. |
| `viscosity` | `number` | `Pa*s` | 0.0195 | - | > 0 | 全部 | `miu` | Lubricant dynamic viscosity. |
| `clearance` | `number` | `m` | 8e-05 | - | > 0 | 全部 | `c` | Radial bearing clearance. |
| `radius` | `number` | `m` | 0.04 | - | > 0 | 全部 | `r` | Journal radius. |
| `length` | `number` | `m` | 0.06 | - | > 0 | 全部 | `l` | Physical bearing axial length. |
| `supply_pressure` | `number` | `Pa` | 7000000.0 | - | > 0 | 全部 | `ps` | Reference or restrictor supply pressure. |
| `density` | `number` | `kg/m^3` | 872.0 | - | > 0 | 全部 | `rho` | Lubricant density. |
| `reynolds_boundary` | `boolean or 'half_reynold'` | `bool` | true | - | finite | 全部 | `reynold` | Enable the Reynolds cavitation boundary. |
| `continuous_boundary` | `boolean` | `bool` | true for liquid_film; false for active_lubricated | - | finite | 全部 | `coe` | Couple the circumferential end boundaries. |
| `ambient_pressure` | `number` | `Pa` | 0.0 | - | finite | 全部 | `p_set` | Pressure prescribed on ambient film boundaries. |
| `solver_tolerance` | `number` | `1` | 1e-10 | - | > 0 | 全部 | `error_set` | Relative convergence tolerance of the film solve. |
| `max_iterations` | `integer` | `count` | 120 | - | >= 1 | 全部 | `max_iter` | Maximum nonlinear film iterations. |
| `relaxation` | `number` | `1` | 0.8 | - | finite | 全部 | `damp` | Fixed relaxation factor used by the film iteration. |
| `vibration_enabled` | `boolean` | `bool` | false | - | finite | 全部 | `vib` | Include squeeze-film velocity terms. |
| `x_velocity` | `number or null` | `m/s` | null | - | finite | 全部 | `dxt` | Initial journal-center velocity on the x axis. |
| `y_velocity` | `number or null` | `m/s` | null | - | finite | 全部 | `dyt` | Initial journal-center velocity on the y axis. |
| `whirl_ratio` | `number` | `1` | 1.0 | - | finite | 全部 | `vf` | Whirl frequency divided by journal rotation frequency. |
| `solver` | `string` | `name` | "newton" | - | finite | 全部 | `iter_method` | Native film iteration method identifier. |
| `save_pressure` | `boolean` | `bool` | false | - | finite | 全部 | `save_p` | Include pressure in native persistence outputs. |
| `save_thickness` | `boolean` | `bool` | false | - | finite | 全部 | `save_h` | Include film thickness in native persistence outputs. |
| `gauss_points` | `integer` | `count` | 50 | - | finite | 全部 | `ngauss` | Quadrature points used by Gauss integration. |
| `gauss_relaxation` | `number` | `1` | 1.2 | - | finite | 全部 | `gdamp` | Relaxation factor for the Gauss solver. |
| `gauss_tolerance` | `number` | `1` | 0.001 | - | finite | 全部 | `err` | Convergence tolerance for the Gauss solver. |
| `pad_bias_deg` | `number` | `deg` | 0.0 | - | finite | 全部 | `bias` | Angular offset applied to this pad. |
| `adaptive_damping` | `boolean or mapping or null` | `bool` | null | - | finite | 全部 | `adaptive_damp` | Adapt the iteration relaxation factor. |

<a id="config-group-film_nondimensional"></a>
### 无量纲液膜 film

无量纲压力、速度和用于工程单位换算的 scale 字段。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `bearing_number` | `number` | `1` | 1.0 | - | > 0 | 全部 | `lambda_value` | Operating nondimensional bearing number. |
| `reference_bearing_number` | `number or null` | `1` | null | - | finite | 全部 | `lambda0` | Reference bearing number used for scaling. |
| `length_ratio` | `number` | `1` | 1.0 | - | > 0 | 全部 | `lr` | Bearing length divided by journal radius. |
| `arc_angle_deg` | `number` | `deg` | 360.0 | - | > 0 | 全部 | `lx` | Circumferential angular span of the film domain. |
| `axial_length_ratio` | `number` | `1` | 2.0 | - | > 0 | 全部 | `lz` | Modeled axial length divided by bearing length. |
| `circumferential_elements` | `integer` | `count` | 59 | - | >= 2 | 全部 | `nx` | Finite-element count around the film arc. |
| `axial_elements` | `integer` | `count` | 39 | - | >= 2 | 全部 | `nz` | Finite-element count along the bearing axis. |
| `pad_bias_deg` | `number` | `deg` | 0.0 | - | finite | 全部 | `bias` | Angular offset applied to this pad. |
| `eccentricity` | `number` | `1` | 0.0 | - | 0 <= value < 1 | 全部 | `e` | Initial eccentricity ratio e/c. |
| `attitude_angle_deg` | `number` | `deg` | 0.0 | - | finite | 全部 | `angle` | Initial eccentricity attitude angle. |
| `reynolds_boundary` | `boolean or 'half_reynold'` | `bool` | true | - | finite | 全部 | `reynold` | Enable the Reynolds cavitation boundary. |
| `continuous_boundary` | `boolean` | `bool` | true | - | finite | 全部 | `coe` | Couple the circumferential end boundaries. |
| `ambient_pressure` | `number` | `p/ps` | 0.0 | - | finite | 全部 | `p_set` | Nondimensional ambient boundary pressure. |
| `solver_tolerance` | `number` | `1` | 1e-10 | - | > 0 | 全部 | `error_set` | Relative convergence tolerance of the film solve. |
| `max_iterations` | `integer` | `count` | 120 | - | >= 1 | 全部 | `max_iter` | Maximum nonlinear film iterations. |
| `relaxation` | `number` | `1` | 0.8 | - | finite | 全部 | `damp` | Fixed relaxation factor used by the film iteration. |
| `x_velocity` | `number` | `1` | 0.0 | - | finite | 全部 | `dxt` | Nondimensional journal-center x velocity. |
| `y_velocity` | `number` | `1` | 0.0 | - | finite | 全部 | `dyt` | Nondimensional journal-center y velocity. |
| `whirl_ratio` | `number` | `1` | 1.0 | - | finite | 全部 | `vf` | Whirl frequency divided by journal rotation frequency. |
| `x_center_velocity` | `number` | `1` | 0.0 | - | finite | 全部 | `xct` | Nondimensional moving-frame x velocity. |
| `y_center_velocity` | `number` | `1` | 0.0 | - | finite | 全部 | `yct` | Nondimensional moving-frame y velocity. |
| `scale_viscosity` | `number` | `Pa*s` | 1.0 | - | > 0 | 全部 | `scale_miu` | Viscosity used to dimensionalize outputs. |
| `scale_clearance` | `number` | `m` | 1.0 | - | > 0 | 全部 | `scale_c` | Clearance used to dimensionalize displacement. |
| `scale_radius` | `number` | `m` | 1.0 | - | > 0 | 全部 | `scale_r` | Journal radius used for dimensional scaling. |
| `scale_length` | `number or null` | `m` | null | - | None or > 0 | 全部 | `scale_l` | Bearing length used for dimensional scaling. |
| `scale_pressure` | `number` | `Pa` | 1.0 | - | > 0 | 全部 | `scale_ps` | Pressure used to dimensionalize pressure and force. |
| `scale_density` | `number` | `kg/m^3` | 1.0 | - | > 0 | 全部 | `scale_rho` | Density used for dimensional scaling. |
| `scale_speed_rpm` | `number or null` | `rpm` | null | - | None or > 0 | 全部 | `scale_w` | Journal speed used for dimensional scaling. |
| `save_pressure` | `boolean` | `bool` | false | - | finite | 全部 | `save_p` | Include pressure in native persistence outputs. |
| `save_thickness` | `boolean` | `bool` | false | - | finite | 全部 | `save_h` | Include film thickness in native persistence outputs. |
| `adaptive_damping` | `boolean or mapping or null` | `bool` | null | - | finite | 全部 | `adaptive_damp` | Adapt the iteration relaxation factor. |

<a id="config-group-film_gas_additions"></a>
### 气膜覆盖与附加 film 字段

列出气膜对通用量纲 film 默认值的覆盖，以及气体压力、织构和柔性箔片耦合参数。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `continuous_boundary` | `boolean` | `bool` | true | - | finite | 全部 | `coe` | Couple the circumferential end boundaries. |
| `ambient_pressure` | `number` | `Pa` | 1.0 | - | >= 0 | 全部 | `p_set` | Pressure prescribed on ambient film boundaries. |
| `solver` | `string` | `name` | "skfem_newton" | ["skfem_newton"] | finite | 全部 | `iter_method` | Native film iteration method identifier. |
| `ambient_pressure_pa` | `number` | `Pa` | 101325.0 | - | > 0 | 全部 | `pa` | Absolute ambient gas pressure. |
| `gas_frequency_ratio` | `number` | `1` | 1.0 | - | > 0 | 全部 | `gamma` | Gas-film frequency-ratio coefficient. |
| `foil_enabled` | `boolean` | `bool` | false | - | finite | 全部 | `foil_enabled` | Enable compliant-foil deformation. |
| `texture_enabled` | `boolean` | `bool` | false | - | finite | 全部 | `texture_enabled` | Enable the configured surface texture. |
| `texture_type` | `integer` | `integer` | 1 | [1, 2, 3] | finite | gas_film:dimensional | `texture_type` | Surface-texture geometry identifier. |
| `texture_depth` | `number or null` | `m` | null | - | None or >= 0 | 全部 | `texture_depth` | Absolute texture depth. |
| `texture_depth_ratio` | `number or null` | `1` | null | - | None or >= 0 | 全部 | `texture_depth_ratio` | Texture depth divided by clearance. |
| `texture_circumferential_fraction` | `number` | `1` | 0.0 | - | 0 <= value <= 1 | 全部 | `texture_circ_fraction` | Textured fraction around the film arc. |
| `texture_axial_fraction` | `number` | `1` | 0.0 | - | 0 <= value <= 1 | 全部 | `texture_axial_fraction` | Textured fraction along the bearing axis. |
| `texture_start_theta_index` | `integer` | `index` | 1 | - | >= 1 | gas_film:dimensional | `texture_start_theta_index` | One-based circumferential mesh index where texture begins. |
| `texture_start_axial_index` | `integer` | `index` | 1 | - | >= 1 | gas_film:dimensional | `texture_start_z_index` | One-based axial mesh index where texture begins. |
| `foil_relaxation` | `number` | `1` | 0.5 | - | 0 < value <= 1 | 全部 | `foil_relaxation` | Relaxation factor for foil deformation. |
| `foil_tolerance` | `number` | `1` | 1e-06 | - | > 0 | 全部 | `foil_tol` | Convergence tolerance for foil deformation. |
| `foil_stiffness` | `number or null` | `N/m^3` | null | - | None or > 0 | 全部 | `foil_stiffness` | Distributed support stiffness of the foil. |
| `foil_pitch` | `number` | `m` | 0.004572 | - | > 0 | 全部 | `foil_pitch` | Circumferential pitch of foil supports. |
| `foil_half_length` | `number` | `m` | 0.001717 | - | > 0 | 全部 | `foil_half_length` | Half-length used by the foil model. |
| `foil_thickness` | `number` | `m` | 0.00013 | - | > 0 | 全部 | `foil_thickness` | Foil material thickness. |
| `foil_young_modulus` | `number` | `Pa` | 210000000000.0 | - | > 0 | 全部 | `foil_young` | Foil Young's modulus. |
| `foil_poisson_ratio` | `number` | `1` | 0.3 | - | -1 < value < 0.5 | 全部 | `foil_poisson` | Foil Poisson ratio. |

<a id="config-group-restrictors_liquid"></a>
### 液膜 restrictors

可选静压节流孔位置、几何/流量系数和供压。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `positions` | `array[array[number, 2]]` | `normalized coordinate pairs` | 必填 | - | nonempty | 全部 | 与公开字段同名 | Restrictor circumferential/axial positions. |
| `radius` | `number or null` | `m` | null | - | exactly one of radius and flow_coefficient | 全部 | 与公开字段同名 | Physical restrictor radius. |
| `flow_coefficient` | `number or null` | `1` | null | - | exactly one of radius and flow_coefficient | 全部 | 与公开字段同名 | Already nondimensionalized restrictor flow coefficient. |
| `pressure` | `number or null` | `Pa or p/ps` | null | - | - | 全部 | 与公开字段同名 | Optional restrictor supply pressure override. |
| `discharge_coefficient` | `number` | `1` | 0.6 | - | > 0 | 全部 | 与公开字段同名 | Orifice discharge coefficient. |

<a id="config-group-restrictors_active"></a>
### 主动 restrictors

量纲或无量纲主动供油节流器及点源投影方式。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `positions` | `array[array[number, 2]]` | `normalized coordinate pairs` | 必填 | - | nonempty | 全部 | 与公开字段同名 | Active restrictor locations. |
| `supply_pressure` | `number` | `Pa or p/ps` | film.supply_pressure for dimensional; 1.0 for nondimensional | - | - | 全部 | 与公开字段同名 | Restrictor supply pressure. |
| `tank_pressure` | `number` | `Pa or p/ps` | 0.0 | - | - | 全部 | 与公开字段同名 | Tank/reference pressure. |
| `flow_coefficient` | `number or null` | `1` | null | - | - | 全部 | 与公开字段同名 | Legacy active flow coefficient or dimensional cq1 override. |
| `orifice_diameter` | `number` | `m` | 0.002 | - | > 0 | active_lubricated:dimensional | 与公开字段同名 | Dimensional orifice diameter. |
| `orifice_length` | `number` | `m` | 0.02 | - | > 0 | active_lubricated:dimensional | 与公开字段同名 | Dimensional orifice length. |
| `valve_area` | `number` | `m^2` | 1.22e-06 | - | > 0 | active_lubricated:dimensional | 与公开字段同名 | Dimensional valve reference area. |
| `discharge_coefficient` | `number` | `1` | 0.6 | - | > 0 | active_lubricated:dimensional | 与公开字段同名 | Dimensional orifice discharge coefficient. |
| `flow_projection` | `string` | `name` | "nearest_node" | ["nearest_node", "element_shape"] | - | 全部 | 与公开字段同名 | Point-source projection onto pressure/thermal degrees of freedom. |
| `base_flow_coefficient` | `number` | `1` | 1.0 | - | - | active_lubricated:nondimensional | 与公开字段同名 | Nondimensional base-flow coefficient cq0. |
| `spool_flow_coefficient` | `number` | `1` | flow_coefficient when provided; otherwise 1.0 | - | - | active_lubricated:nondimensional | 与公开字段同名 | Nondimensional spool-flow coefficient cq1. |
| `pressure_flow_coefficient` | `number` | `1` | 0.0 | - | - | active_lubricated:nondimensional | 与公开字段同名 | Nondimensional pressure-flow coefficient cq2. |

<a id="config-group-tank"></a>
### 主动 tank

油腔局部范围与深度比。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `x_range` | `array[number, 2]` | `normalized pair` | [0.49, 0.51] | - | - | 全部 | 与公开字段同名 | Circumferential tank/recess interval. |
| `z_range` | `array[number, 2]` | `normalized pair` | [0.2, 0.8] | - | - | 全部 | 与公开字段同名 | Axial tank/recess interval. |
| `depth_ratio` | `number` | `h/c` | 2.0 | - | - | 全部 | 与公开字段同名 | Tank depth divided by clearance. |

<a id="config-group-valve_second_order"></a>
### 二阶 valve

二阶伺服阀的频率、阻尼和延迟。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `model` | `string` | `name` | 必填 | ["second_order", "static", "transfer_function"] | - | 全部 | 与公开字段同名 | Servo-valve model discriminator. |
| `natural_frequency_hz` | `number` | `Hz` | 必填 | - | > 0 | 全部 | 与公开字段同名 | Second-order natural frequency. |
| `damping_ratio` | `number` | `1` | 必填 | - | > 0 | 全部 | 与公开字段同名 | Second-order damping ratio. |
| `delay` | `number` | `s` | 0.0 | - | >= 0 | 全部 | 与公开字段同名 | Nonnegative command delay. |

<a id="config-group-valve_static"></a>
### 静态 valve

无记忆单位增益阀，仅使用模型判别字段。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `model` | `string` | `name` | 必填 | ["second_order", "static", "transfer_function"] | - | 全部 | 与公开字段同名 | Servo-valve model discriminator. |

<a id="config-group-valve_transfer_function"></a>
### 传递函数 valve

连续时间 proper 传递函数的分子和分母多项式。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `model` | `string` | `name` | 必填 | ["second_order", "static", "transfer_function"] | - | 全部 | 与公开字段同名 | Servo-valve model discriminator. |
| `numerator` | `array[number]` | `descending powers of s` | 必填 | - | finite, nonempty, nonzero leading coefficient; transfer proper | 全部 | 与公开字段同名 | Continuous-time numerator coefficients. |
| `denominator` | `array[number]` | `descending powers of s` | 必填 | - | finite, nonempty, nonzero leading coefficient | 全部 | 与公开字段同名 | Continuous-time denominator coefficients. |

<a id="config-group-control"></a>
### 主动 control

PID、模糊 PID、无控制和外部阀芯模式的公共控制字段。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `mode` | `string` | `name` | 必填 | ["pid", "fuzzy_pid", "uncontrolled", "external_spool"] | - | 全部 | 与公开字段同名 | Controller ownership and algorithm mode. |
| `gains` | `object or null` | `mapping` | null | - | - | pid | 与公开字段同名 | PID gains; accepted only for pid mode. |
| `frequency_hz` | `number` | `Hz` | 50.0 for pid; 5.0 for fuzzy_pid | - | - | pid, fuzzy_pid | 与公开字段同名 | Controller update/reference frequency. |
| `sensor_angles_deg` | `array[number, 2]` | `deg` | [45.0, 135.0] | - | - | pid, fuzzy_pid | 与公开字段同名 | Two sensor directions used by PID/fuzzy PID. |
| `error_range` | `array[number, 3]` | `[min, max, step]` | [-1.0, 1.0, 0.01] | - | - | fuzzy_pid | 与公开字段同名 | Fuzzy error universe. |
| `delta_error_range` | `array[number, 3]` | `[min, max, step]` | [-1.0, 1.0, 0.01] | - | - | fuzzy_pid | 与公开字段同名 | Fuzzy error-change universe. |
| `kp_range` | `array[number, 3]` | `[min, max, step]` | [0.0, 1.0, 0.01] | - | - | fuzzy_pid | 与公开字段同名 | Fuzzy proportional-gain universe. |
| `ki_range` | `array[number, 3]` | `[min, max, step]` | [0.0, 0.0, 0.01] | - | - | fuzzy_pid | 与公开字段同名 | Fuzzy integral-gain universe. |
| `kd_range` | `array[number, 3]` | `[min, max, step]` | [0.0, 1.0, 0.01] | - | - | fuzzy_pid | 与公开字段同名 | Fuzzy derivative-gain universe. |
| `rule_path` | `string` | `relative path` | "fuzzy_rules.csv" | - | - | fuzzy_pid | 与公开字段同名 | Fuzzy rule CSV resolved below resource_root. |

<a id="config-group-control_pid_gains"></a>
### PID gains

PID 比例、积分、微分与前馈增益。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `kp` | `number` | `controller units` | 0.0 | - | - | 全部 | 与公开字段同名 | Proportional gain. |
| `ki` | `number` | `controller units` | 0.0 | - | - | 全部 | 与公开字段同名 | Integral gain. |
| `kd` | `number` | `controller units` | 0.0 | - | - | 全部 | 与公开字段同名 | Derivative gain. |
| `feedforward` | `number` | `controller units` | 0.0 | - | - | 全部 | 与公开字段同名 | Constant feed-forward term. |

<a id="config-group-transforms"></a>
### 主动 transforms

物理位移/速度到控制器输入的显式变换矩阵。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `displacement_to_control` | `array[array[number]]` | `matrix` | [[1.0, 0.0], [0.0, 1.0]] | - | - | 全部 | 与公开字段同名 | Physical-displacement to controller-input transform. |
| `velocity_to_control` | `array[array[number]]` | `matrix` | [[0.0, 0.0], [0.0, 0.0]] | - | - | 全部 | 与公开字段同名 | Physical-velocity to controller-input transform. |

<a id="config-group-thermal"></a>
### thermal

稳态或瞬态热黏耦合、边界条件、黏度更新与 Newton 参数。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `t_in` | `number` | `degC` | 40.0 | - | - | 全部 | 与公开字段同名 | Lubricant inlet temperature. |
| `t_ref` | `number or null` | `degC` | null | - | - | 全部 | 与公开字段同名 | Reference temperature for viscosity. |
| `miu0` | `number or null` | `Pa*s` | null | - | None or > 0 | 全部 | 与公开字段同名 | Viscosity at t_ref; inherits film viscosity when absent. |
| `beta` | `number` | `1/degC` | 0.03 | - | - | 全部 | 与公开字段同名 | Dimensional viscosity-temperature coefficient. |
| `k_lub` | `number` | `W/(m*K)` | 0.0 | - | >= 0 | 全部 | 与公开字段同名 | Lubricant thermal conductivity. |
| `cp_lub` | `number` | `J/(kg*K)` | 2000.0 | - | > 0 | 全部 | 与公开字段同名 | Lubricant heat capacity. |
| `max_delta_t` | `number` | `degC` | 80.0 | - | - | 全部 | 与公开字段同名 | Maximum accepted temperature rise. |
| `heat_partition` | `number` | `1` | 0.9 | - | - | 全部 | 与公开字段同名 | Fraction of friction heat entering lubricant. |
| `relax` | `number` | `1` | 0.5 | - | - | 全部 | 与公开字段同名 | Outer thermal relaxation factor. |
| `miu_update` | `string` | `name` | "linear" | ["linear", "log"] | - | 全部 | 与公开字段同名 | Outer viscosity update rule. |
| `miu_update_max_ratio` | `number or null` | `1` | null | - | None or > 1 | 全部 | 与公开字段同名 | Optional multiplier cap for log viscosity updates. |
| `heat_partition_steps` | `array[number] or null` | `sequence` | null | - | - | 全部 | 与公开字段同名 | Optional positive continuation schedule ending at heat_partition. |
| `iter_method` | `string` | `name` | "direct" | ["direct", "newton", "direct_then_newton"] | - | 全部 | 与公开字段同名 | Thermal nonlinear iteration method. |
| `tol` | `number` | `1` | 1e-06 | - | > 0 | 全部 | 与公开字段同名 | Thermal outer-iteration tolerance. |
| `max_iter` | `integer` | `count` | 60 | - | > 0 | 全部 | 与公开字段同名 | Thermal outer-iteration limit. |
| `adaptive_damp` | `boolean or object or null` | `mapping` | null | - | - | 全部 | 与公开字段同名 | Optional adaptive outer-relaxation policy. |
| `miu_min` | `number` | `Pa*s` | 0.0001 | - | - | 全部 | 与公开字段同名 | Viscosity clipping lower bound. |
| `miu_max` | `number` | `Pa*s` | 1.0 | - | - | 全部 | 与公开字段同名 | Viscosity clipping upper bound. |
| `coupling` | `string` | `name` | "full" | ["full", "half"] | - | 全部 | 与公开字段同名 | Nodal or mean-viscosity thermal coupling. |
| `t_supply` | `number or null` | `degC` | null | - | - | 全部 | 与公开字段同名 | Orifice supply temperature; falls back to t_in. |
| `axial_side_bc` | `string` | `name` | "inflow_fixed" | ["fixed", "adiabatic", "inflow_fixed"] | - | 全部 | 与公开字段同名 | Axial-side thermal boundary condition. |
| `axial_side_t` | `number or null` | `degC` | null | - | - | 全部 | 与公开字段同名 | Fixed axial-side temperature; falls back to t_supply. |
| `supg` | `boolean` | `bool` | true | - | - | 全部 | 与公开字段同名 | Enable SUPG stabilization. |
| `delta_t_scale` | `number or null` | `degC` | null | - | > 0 when beta_nondim or t_ref_nondim is provided | 全部 | 与公开字段同名 | Characteristic nondimensional temperature rise. |
| `beta_nondim` | `number or null` | `1` | null | - | - | 全部 | 与公开字段同名 | Optional nondimensional viscosity-temperature coefficient. |
| `t_ref_nondim` | `number or null` | `1` | null | - | - | 全部 | 与公开字段同名 | Optional nondimensional reference temperature. |
| `transient_enabled` | `boolean` | `bool` | false | - | requires iter_method='direct' | 全部 | 与公开字段同名 | Enable the thermal transient term. |
| `thermal_newton_max_iter` | `integer` | `count` | 30 | - | > 0 | 全部 | 与公开字段同名 | Maximum Newton iterations per thermal subsolve. |
| `thermal_newton_tol` | `number or null` | `1` | null | - | None or > 0 | 全部 | 与公开字段同名 | Newton residual tolerance; falls back to tol. |
| `thermal_newton_damp` | `number` | `1` | 1.0 | - | > 0 | 全部 | 与公开字段同名 | Initial Newton damping factor. |
| `thermal_newton_min_damp` | `number` | `1` | 0.001 | - | 0 < value <= thermal_newton_damp | 全部 | 与公开字段同名 | Minimum line-search damping factor. |
| `thermal_newton_line_search` | `boolean` | `bool` | false | - | - | 全部 | 与公开字段同名 | Enable residual-decreasing Newton line search. |

<a id="config-group-model_package"></a>
### 代理 model_package

ALBNN 0.4 模型包的受限相对路径和增强覆盖。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `path` | `string` | `relative directory` | 必填 | - | nonempty, relative, no '..' segment | 全部 | 与公开字段同名 | ALBNN package directory below the outer document. |
| `use_augment` | `boolean or null` | `bool` | null | - | - | 全部 | 与公开字段同名 | Optional inference augmentation override. |

<a id="config-group-surrogate_runtime"></a>
### 代理 runtime

推理参数、固定阀芯或外部阀芯输入模式。

| 字段 | 值类型 | 单位 | 必填/默认值 | 可选值 | 约束 | 适用范围 | 原生映射 | 源码英文合同 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `parameters` | `object` | `mapping` | {} | - | - | 全部 | 与公开字段同名 | Attributes exposed on the inference runtime config. |
| `spool_mode` | `string` | `name` | "fixed" | ["fixed", "external"] | - | 全部 | 与公开字段同名 | Use a fixed normalized spool or require external input. |
| `spool` | `array[number, 2]` | `normalized pair` | [0.0, 0.0] | - | each value in [-1, 1]; forbidden when spool_mode='external' | 全部 | 与公开字段同名 | Fixed normalized spool command. |
