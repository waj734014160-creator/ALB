# 压力-温度耦合一致性检查文档

## 1. 检查范围

- 压力方程实现与公式一致性（当前 skfem 后端）
- 温度方程实现与公式一致性（scikit-fem）
- 黏度命名统一性（eta -> miu）
- 历史 legacy 分支与当前 skfem 分支的差异记录
- 图像输出：压力云图与温度云图，标题含峰值

涉及文件：

- ALB/thermal.py
- test/bearing/test_thermal_wrapper.py

## 2. 压力方程检查（Reynolds）

### 2.1 目标形式（无量纲）

参考目标：

Pi = psi^2 * d/dxbar( hbar^3/mubar * dpbar/dxbar )
   + d/dzbar( hbar^3/mubar * dpbar/dzbar )
   + qbar - Lambda * dhbar/dxbar - 2*Lambda*gamma*dhbar/dtbar = 0

### 2.2 代码映射

在 ALB/thermal.py 中，当前启用路径为：

- `ViscositySkfemNewtonFilm`:
  - LHS: `_reynolds_lhs_miu` 使用 `h3_over_miu * (lr^2 gradx + gradz)`
  - RHS: `_reynolds_rhs_miu0` 使用 `vx0`（mu0 基准）计算 `-vx0*dh_dx - 2*vx0*vf*dh_dt`
- 历史保留代码：`ViscosityFilmElem` 中仍留有基于 `h_eff` 的旧写法，但它不再作为设置项对外开放，不能作为当前实现依据。

### 2.3 一致性结论

- LHS 对 miu(T) 的依赖实现正确：当前启用实现的扩散系数与 `h^3/miu` 一致。
- RHS 使用 mu0（环境温度参考黏度）实现正确，满足“右手项应采用 mu0”的要求。
- 当前对外支持的压力装配路径为 skfem；legacy 分支仅保留作内部历史参考。

## 3. 温度方程检查（Advection-Diffusion）

### 3.1 目标形式

rho*cp*(qx*dT/dx + qz*dT/dz) = k*laplacian(T) + Phi

其中：

- qx = U*h/2 - h^3/(12*miu) * dp/dx
- qz =       - h^3/(12*miu) * dp/dz
- Phi = heat_partition * [ miu*U^2/h + h^3/(12*miu)*(dpdx^2 + dpdz^2) ]

### 3.2 代码映射

在 ALB/thermal.py 中 `SkfemThermalModel.solve`:

- `h3_over_12mu = h^3/(12*viscosity_nodal)`
- `qx_nodal`, `qz_nodal` 与上式一致
- `phi_couette + phi_poiseuille` 与上式一致
- 使用 `asm(_advection_diffusion_form)` 组装对流-扩散项
- 可选 SUPG 稳定项 `_supg_stiffness_form` 与 `_supg_load_form`
- 边界条件：入口定温、侧边可配置、出口自然边界
- 线性系统由 `enforce + spsolve` 求解

### 3.3 一致性结论

- 温度方程中通量与热源项与目标公式一致。
- 对流主导情况下使用 SUPG 提升稳定性，做法合理。
- 压力梯度来自同一 film 模型更新，压力-热耦合链路闭合。

## 4. 命名统一检查（eta -> miu）

已完成：

- `ThermalConfig.eta_ref/eta_min/eta_max` -> `miu_ref/miu_min/miu_max`
- 节点比值统一为 `miu_ratio`
- 内部变量与方法统一：`miu_field`、`miu_mean`、`_apply_miu_ratio_to_nodes`、`_map_miu_to_thermal`
- 测试与输出文案中 `eta` 文本统一替换为 `miu`

## 5. 对比测试与图像产出

测试项：

- `TestThermalHydroBearing::test_legacy_pressure_backend_rejected`

结果：

- 通过
- `legacy` 压力后端会被显式拒绝，避免误用历史 `h_eff` 分支。

图像产出：

- 当前文档不再维护 legacy/skfem 对比图，避免将历史分支误认为现行支持路径。

## 6. 审查发现与风险

### 6.1 已确认项

- 压力和温度实现与目标公式一致性良好。
- mu0 右手项基准已落实到当前 skfem 后端。
- 历史 legacy 分支保留在源码中，但不再通过设置暴露给用户。

### 6.2 残余风险（低）

- `viscosity` / `viscosity_field` 输出键名仍为英文通用词，非数学符号 `miu`。这不影响物理正确性，但若需符号级统一，可再改为 `miu` / `miu_field`（会影响外部脚本兼容性）。
- cavitation FB 迭代仍可能出现极小负压数值噪声（1e-6 量级内），当前测试容忍策略合理。

## 7. 结论

本次改造满足以下目标：

1. 压力计算对外仅支持并实际使用 scikit-fem 后端。
2. 压力方程右手项采用 mu0 基准。
3. 对比输出包含压力与温度云图，子图标题给出峰值。
4. 热耦合代码中的 eta 命名已统一为 miu。
5. 对压力与温度公式一致性完成代码审查并形成文档。
