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
- 无量纲主动轴承还可使用 `base_flow_coefficient`、
  `spool_flow_coefficient` 和 `pressure_flow_coefficient`。
- `tank.x_range`、`z_range`：油腔在局部坐标中的范围；
  `depth_ratio`：油腔深度与间隙之比。
- `valve.model`：`second_order`、`third_order` 或 `static`；
  `response_time`：s；`damping_ratio`：1；`third_order_time_constant`：s；
  `delay`：s。
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

## `SimulationConfig.loads`

每个载荷都是一个带 `type` 的普通映射。构造 `SimulationConfig` 时只校验一次
字段和值域并生成深度只读副本；`run()` 不再重复解释未知字段。

| `type` | 字段 | 单位/缺省值 | 含义 |
| --- | --- | --- | --- |
| `static` | `node` | 非负整数，必填 | 施加载荷的转子节点。 |
| `static` | `force` | N，长度 2，必填 | 固定 `[Fx, Fy]`，两个分量必须有限。 |
| `gravity` | `acceleration` | m/s²，缺省 `9.80665` | y 方向重力加速度；有限负值可显式反转方向。 |
| `unbalance` | `node` | 非负整数或非空整数序列，必填 | 不平衡激励节点。 |
| `unbalance` | `phase` | rad，缺省 `0` | 初始相位。 |
| `unbalance` | `t_max` | s，缺省 `1` | 斜坡/门控使用的正时间尺度。 |
| `unbalance` | `m` | kg，缺省 `0` | 等效不平衡质量。 |
| `unbalance` | `freq` | Hz，缺省 `0` | 激励频率。 |
| `unbalance` | `e` | m，缺省 `0` | 不平衡质量偏心半径。 |
| `unbalance` | `no_step` | 布尔，缺省 `false` | `true` 时用 `[0, t_max]` 线性斜坡代替阶跃启用。 |

程序化仿真的 `rotor` 必须满足 `ALB.contracts.RotorProtocol`。高级记录器和
observer 通过 `ALB.dynamics.CouplingRuntimeDependencies` 提供；该类型显式列出
`run_id`、`recorder`、`observers`、记录失败策略和 observer 失败策略，不使用
任意 `object` 容器。
