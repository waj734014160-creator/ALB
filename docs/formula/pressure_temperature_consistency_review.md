# 压力-温度耦合一致性检查

## 1. 文档角色与检查范围

- 角色：当前压力-温度耦合实现的代码证据审查。
- 允许更新：活动调用链、量纲契约、离散方程、已知边界和回归证据。
- 禁止更新：实验运行状态、训练进度和外部论文任务配置。

本次检查以 `ThermalHydroBearing` / `NodimThermalHydroBearing` 的活动路径为准，
不再把历史有量纲温度求解器或已停用的 `h_eff` 分支当作当前实现依据。

涉及文件：

- `ALB/physics/thermal/scales.py`
- `ALB/physics/hydraulics/orifice.py`
- `ALB/physics/thermal/solver.py`
- `ALB/config/film.py` 与 `ALB/config/thermal.py`
- `tests/regression/bearing/test_nodim_alb_equivalence.py`
- 热模型与孔口契约的邻近单元测试

## 2. 当前活动调用链

有量纲入口并不维护第二套独立温度算法：

1. `ThermalHydroBearing` 接受有量纲 film 与 `ThermalConfig`。
2. 包装器把压力模型转换为无量纲压力后端，并建立统一参考尺度。
3. `NodimThermalHydroBearing` 负责热-流-黏度迭代。
4. `SkfemThermalModelNondim` 组装和求解温度有限元方程。
5. 有量纲包装器只在输出边界恢复温度、流量和力的单位。

因此，有量纲/无量纲等价性必须在公开包装器的完整调用链上验证，不能只比较两个
孤立 helper 的公式。

## 3. 压力方程与参考黏度

当前无量纲 Reynolds 方程采用“左端局部黏度、右端固定参考黏度”的契约：

$$
K_p\sim\frac{\bar h^3}{\bar\mu},
\qquad
f_p\sim\lambda_0\frac{\partial\bar h}{\partial\bar x}
+2\lambda_0v_f\frac{\partial\bar h}{\partial\bar t}.
$$

- 有量纲包装器中，若 `ThermalConfig.miu0` 显式给出，它是唯一参考黏度；
  压力无量纲化之前同步重算 `lambda0` 与流量尺度。
- 直接无量纲模型中，`model.args["lambda0"]` 与 `lr` 是权威系数；若额外
  `miu0` 与模型携带的物理参考尺度冲突，应直接报错，不能静默改写既有无量纲系数。
- `xct`、`yct` 是无量纲运动速度。挤压项中的 `vf` 用于恢复
  $\partial\bar h/\partial\bar t$，不是多余量纲因子。

## 4. 热方程与导热率量纲

厚度积分后的活动热方程为

$$
\rho c_p h\frac{\partial T}{\partial t}
+\rho c_p\left(q_x\frac{\partial T}{\partial x}
+q_z\frac{\partial T}{\partial z}\right)
=\nabla\cdot\left(k_{\mathrm{lub}}h\nabla T\right)+\Phi.
$$

其中 `k_lub` 是三维导热率，单位 W/(m·K)；二维弱式系数是局部
$k_{\mathrm{lub}}h$，不能把 `k_lub` 直接当作 W/K 常数。当前默认
`k_lub=0.0`，因为面内物理热传导很小；空间对流稳定由 SUPG 单独提供。

代码字段 `cp_lub` 沿用既有命名。模型按不可压缩液体近似使用
$c_v\approx c_p$，不存在同时配置两套热容常数的问题。

均压槽内膜厚增大时，Couette 通量随 $h$ 变化，Poiseuille 通量随 $h^3$
变化；槽区温度场的主要改变来自对流输运和相应 SUPG 流线尺度。即使启用物理导热，
$k_{\mathrm{lub}}h$ 也只随膜厚线性变化，不应把槽区效应主要归因于热传导。

## 5. 唯一流量尺度与供油孔点源

流量尺度固定为

$$
Q_w=\frac{p_sc^3}{12\mu_0l_r}\quad[\mathrm{m^3/s}],
\qquad
Q_f=\frac{Q_w}{l_rR}\quad[\mathrm{m^2/s}],
$$

且单孔体积流量为

$$
Q_i=q_{n,i}Q_w.
$$

不再引入 `Qvol0`。`ThermalNondimScales.qf` 是活动面内通量尺度；
`flow_scale` 只保留为只读兼容别名。

`flow_info()` 明确提供 `position_nondim`、`position_dim`、`q_nondim`、
`q_vol` 和同一个 `qw`。旧 `flow=(x_dim,z_dim,q_vol)` 仅用于有量纲兼容输出。
无量纲热核只消费无量纲位置和 `q_nondim`，点源装配为

$$
K_{jj}\mathrel{+}=q_{n,i},
\qquad
f_j\mathrel{+}=q_{n,i}\bar T_{\mathrm{supply}}.
$$

结果中的 `q_orifice_total_nondim` 表示无量纲总流量；
`q_orifice_total_vol` 与兼容字段 `q_orifice_total` 均表示 m³/s。

## 6. 求解配置与状态提交

- `coupling` 统一转为小写，只接受 `full` 或 `half`。
- `transient_enabled=True` 当前只允许 `iter_method="direct"`；瞬态 Newton
  尚未实现，非法组合在配置阶段报错。
- `flow_rate_factor` 仅为 deprecated/no-op 兼容字段，只允许 `1.0`。
- 稳态初始化或瞬态步未收敛时抛出明确错误，不更新 `_temperature_prev`；
  只有收敛结果才能成为下一步历史温度。

## 7. 回归判据与边界

回归测试应同时覆盖：

1. $Q_w=Q_fl_rR$ 与 $Q_i=q_{n,i}Q_w$ 的严格单位关系。
2. 普通孔口、固定流量孔口和无量纲孔口的双坐标/双流量契约。
3. 有孔有量纲/无量纲公开包装器的力、温度和黏度严格等价。
4. 孔位局部冷却量级，防止只检查温降方向而遗漏大尺度归一化错误。
5. 任意 `lambda0`、有量纲 `miu0` 覆盖、非零 `k_lub`、非法配置和失败状态不提交。
6. 已有无孔 JSON/NPZ reference 保持不变；错误的旧含孔结果不建立新基线。

本轮不处理“孔口先求解、随后才包装热模型”时缓存节点的重绑定，也不实现瞬态 Newton。
这两项属于明确边界，不应通过静默回退掩盖。
