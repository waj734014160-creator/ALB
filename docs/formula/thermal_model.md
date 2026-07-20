# 热效应计算原理

## 文档角色

- 角色：稳定公式和实现参考。
- 目的：说明 `ALB/thermal.py` 的热压力模型、有限元离散、无量纲形式，以及代码到公式的映射。
- 允许更新：控制方程、离散步骤、边界条件、耦合流程和实现映射。
- 禁止更新：实时运行状态、活跃任务进度、PID、ETA、单次 run 指标和原始日志堆叠。
- 更新节奏：热压力方程、离散方式、边界处理或实现映射变化时更新。
- 事实来源 / 相关文档：
  `docs/daily_maintenance/daily_doc_update_index.md`,
  `ALB/thermal.py`, `ALB/nondim.py` 和 `ALB/config.py`。

## 1 概述

`ThermalHydroBearing` 模块在油膜润滑计算的基础上，引入温度场与粘度场的双向耦合：

- **正向**：粘度 → 剪切生热 → 温度场
- **反向**：温度场 → 粘度更新 → Reynolds 方程

通过迭代求解实现热-流-粘度三场的自洽平衡。

## 离散计算流程（当前实现）

本节按当前代码执行顺序说明温度场如何离散计算。压力场先由带局部粘度比的 Reynolds 方程求得；温度场再用压力梯度、膜厚和粘度场组装对流-扩散-热源方程；最后通过温度-粘度关系把二者耦合迭代。

当前对外有两种输入接口，但并不是两套独立的热求解内核：

- `ThermalHydroBearing` 接收有量纲油膜输入，在初始化时把压力模型转换为
  `NodimViscositySkfemNewtonFilm`，随后继承并调用无量纲耦合内核。
- `NodimThermalHydroBearing` 直接接收无量纲油膜输入。
- 两个接口最终均由 `SkfemThermalModelNondim` 组装温度方程；保留在源码中的
  `SkfemThermalModel` 不是当前 `ThermalHydroBearing` 的实际调用路径。
- `iter_method="direct"` 的无量纲温度求解支持稳态和隐式 Euler 非稳态项；
  `iter_method="newton"` 的 `solve_segregated_newton()` 当前只支持稳态，非稳态会明确抛出
  `NotImplementedError`。

### 1. 压力场计算步骤

压力场使用与温度相关的局部粘度比

$$
\bar{\mu}_i = \frac{\mu_i}{\mu_0}
$$

修正 Reynolds 方程左端的 Poiseuille 扩散项。对当前迭代步给定膜厚 $\bar h$、参考轴承数 $\Lambda_0$、长径比

$$
l_r = \frac{L}{2R}
$$

代码中的转子涡动速度先按

$$
\omega=\frac{2\pi n}{60},\qquad
xct=\frac{\dot x_c}{c\,v_f\omega},\qquad
yct=\frac{\dot y_c}{c\,v_f\omega}
$$

转换。因此 `xct`、`yct` 是无量纲速度，而不是 m/s。为避免把代码变量与真实的无量纲时间导数混淆，定义

$$
\dot{\bar h}_{\mathrm{code}}
=xct\sin\theta-yct\cos\theta,
\qquad
\bar t=\omega t,
\qquad
\frac{\partial\bar h}{\partial\bar t}
=v_f\dot{\bar h}_{\mathrm{code}}.
$$

也就是说，`vf` 已经包含在 `xct` 的归一化分母中，但在恢复真实的
$\partial\bar h/\partial\bar t$ 时必须乘回；不能在没有先说明时间尺度和 `xct` 定义时直接删掉 `vf`。

以及局部粘度比 $\bar\mu$，无量纲压力方程采用：

$$
l_r^2\frac{\partial}{\partial\bar x}
\left(
\frac{\bar h^3}{\bar\mu}
\frac{\partial\bar p}{\partial\bar x}
\right)
+
\frac{\partial}{\partial\bar z}
\left(
\frac{\bar h^3}{\bar\mu}
\frac{\partial\bar p}{\partial\bar z}
\right)
=
\Lambda_0\frac{\partial \bar h}{\partial\bar x}
+2\Lambda_0\frac{\partial \bar h}{\partial\bar t}
=
\Lambda_0\frac{\partial \bar h}{\partial\bar x}
+2\Lambda_0v_f\dot{\bar h}_{\mathrm{code}}.
$$

取测试函数 $v$，并对左端分部积分，得到当前实现装配的弱式：

$$
\int_{\Omega_h}
\frac{\bar h^3}{\bar\mu}
\left(
l_r^2\frac{\partial\bar p}{\partial\bar x}\frac{\partial v}{\partial\bar x}
+\frac{\partial\bar p}{\partial\bar z}\frac{\partial v}{\partial\bar z}
\right)d\Omega
=
\int_{\Omega_h}
\left(
   -\Lambda_0\frac{\partial \bar h}{\partial\bar x}
   -2\Lambda_0 v_f\dot{\bar h}_{\mathrm{code}}
\right)v\,d\Omega.
$$

离散时在膜网格上取线性有限元形函数 $N_i$，令

$$
p_h(x,z)=\sum_j p_j N_j(x,z),
$$

得到线性系统

$$
K^{p}_{ij}p_j=f^p_i,
$$

其中

$$
K^{p}_{ij}
=
\int_{\Omega_h}
\frac{\bar h^3}{\bar\mu}
\left(
l_r^2\frac{\partial N_j}{\partial\bar x}\frac{\partial N_i}{\partial\bar x}
+\frac{\partial N_j}{\partial\bar z}\frac{\partial N_i}{\partial\bar z}
\right)d\Omega,
$$

$$
f^p_i
=
\int_{\Omega_h}
\left(
   -\Lambda_0\frac{\partial \bar h}{\partial\bar x}
   -2\Lambda_0 v_f\dot{\bar h}_{\mathrm{code}}
\right)N_i\,d\Omega.
$$

实现步骤为：

1. `ThermalHydroBearing` 将当前粘度场写入膜节点的 `miu_ratio`。
2. `ViscositySkfemNewtonFilm.calc_matrixs_rights()` 在积分点插值 $\bar h$ 和 $\bar\mu$，形成
   $\bar h^3/\bar\mu$。
3. `_reynolds_lhs_miu` 装配 $K^p$，`_reynolds_rhs_miu0` 装配 $f^p$。右端仍使用参考粘度对应的 $\Lambda_0$，局部粘度只进入左端扩散项。
4. 膜模型的边界处理器施加压力边界条件，然后求解 $K^p p=f^p$。
5. 温度网格复用结构化膜网格的节点序，`MeshTri.init_tensor(x_axis, z_axis)` 构造三角形 P1 网格；求得压力后，用差分更新温度方程需要的压力梯度：

$$
\left(\frac{\partial p}{\partial x}\right)_i
\approx
\operatorname{gradient}_x(p)_i,\qquad
\left(\frac{\partial p}{\partial z}\right)_i
\approx
\operatorname{gradient}_z(p)_i.
$$

### 2. 温度场计算步骤

#### 2.1 用于量纲核对的有量纲温度方程

当前公开包装器实际调用无量纲内核；本节保留有量纲式，用于说明无量纲化来源并逐项核对单位。给定当前压力梯度和粘度场后，面内单位宽度体积通量为：

$$
q_x
=
\frac{Uh}{2}
-\frac{h^3}{12\mu}\frac{\partial p}{\partial x},
\qquad
q_z
=
-\frac{h^3}{12\mu}\frac{\partial p}{\partial z}.
$$

热源由 Couette 剪切和 Poiseuille 压力梯度耗散组成：

$$
\Phi
=
\alpha_h
\left[
\frac{\mu U^2}{h}
+
\frac{h^3}{12\mu}
\left(
\left(\frac{\partial p}{\partial x}\right)^2
+
\left(\frac{\partial p}{\partial z}\right)^2
\right)
\right].
$$

稳态温度控制方程写为

$$
\rho c_p
\left(
q_x\frac{\partial T}{\partial x}
+q_z\frac{\partial T}{\partial z}
\right)
=
\nabla\cdot\left(k_{\mathrm{lub}}h\nabla T\right)+\Phi.
$$

这里的 `k_lub` 是润滑油三维导热率 $k_{\mathrm{lub}}$，单位为 W/(m·K)。
薄膜厚度积分后，面内二维导热系数为

$$
k_{2D}=k_{\mathrm{lub}}h\quad [\mathrm{W/K}],
$$

因此弱式扩散项必须使用局部膜厚 $h$，不能把 W/(m·K) 的体导热率直接当成
W/K 的常数。默认 `k_lub = 0.0` 表示忽略通常很小的面内物理热传导；
空间对流的数值稳定仍由 SUPG 独立提供。

量纲逐项为：

| 项 | 单位 |
|---|---|
| $\rho c_p h\,\partial T/\partial t$ | W/m$^2$ |
| $\rho c_p q_x\,\partial T/\partial x$、$\rho c_p q_z\,\partial T/\partial z$ | W/m$^2$ |
| $\mu U^2/h$、$h^3|\nabla p|^2/(12\mu)$ | W/m$^2$ |
| $\nabla\cdot(k_{\mathrm{lub}}h\nabla T)$ | W/m$^2$ |

因此在当前默认 `k_lub = 0.0` 下，储热、对流和耗散热源之间量纲一致。

把扩散项移到左端，并用线性有限元近似

$$
T_h(x,z)=\sum_j T_jN_j(x,z),
$$

标准 Galerkin 离散得到

$$
K^T_{ij}T_j=f^T_i,
$$

其中

$$
K^T_{ij}
=
\int_{\Omega_h}
k_{\mathrm{lub}}h\nabla N_j\cdot\nabla N_i\,d\Omega
+
\int_{\Omega_h}
\rho c_p
\left(
q_x\frac{\partial N_j}{\partial x}
+q_z\frac{\partial N_j}{\partial z}
\right)N_i\,d\Omega,
$$

$$
f^T_i
=
\int_{\Omega_h}\Phi N_i\,d\Omega.
$$

如果启用非稳态项，则控制方程为

$$
\rho c_p h\frac{\partial T}{\partial t}
+
\rho c_p
\left(
q_x\frac{\partial T}{\partial x}
+q_z\frac{\partial T}{\partial z}
\right)
=
\nabla\cdot\left(k_{\mathrm{lub}}h\nabla T\right)+\Phi.
$$

当前无量纲内核的直接求解路径使用有量纲时间步长 `dt`，并以隐式 Euler 离散时间项：

$$
\frac{\partial T}{\partial t}
\approx
\frac{T^{n+1}-T^n}{\Delta t}.
$$

离散线性系统变为

$$
\left(K^T+M_t\right)T^{n+1}
=
f^T+M_tT^n,
$$

其中

$$
(M_t)_{ij}
=
\int_{\Omega_h}
\frac{\rho c_p h}{\Delta t}N_jN_i\,d\Omega.
$$

#### 2.2 无量纲温度方程

无量纲路径在 $\hat\Omega=\{(\bar x,\bar z)\}$ 上组装。给定

$$
\bar h=\frac{h}{c},\qquad
\bar\mu=\frac{\mu}{\mu_0},\qquad
\bar T=\frac{T-T_{\mathrm{supply}}}{\Delta T},
$$

当前实现计算无量纲通量：

$$
\bar q_x
=
\Lambda_0\bar h
-l_r^2\frac{\bar h^3}{\bar\mu}
\frac{\partial \bar p}{\partial\bar x},
\qquad
\bar q_z
=
-l_r\frac{\bar h^3}{\bar\mu}
\frac{\partial \bar p}{\partial\bar z}.
$$

由于 $\bar z=2z/L$ 的坐标缩放，温度方程中的轴向对流速度使用

$$
\bar q_{z,\mathrm{conv}}=\frac{\bar q_z}{l_r}.
$$

无量纲热源为

$$
\bar\Phi_E
=
\Theta_E
\left[
\frac{\Lambda_0^2}{3l_r^2}\frac{\bar\mu}{\bar h}
+
\frac{\bar h^3}{\bar\mu}
\left(
l_r^2
\left(
\frac{\partial\bar p}{\partial\bar x}
\right)^2
+
\left(
\frac{\partial\bar p}{\partial\bar z}
\right)^2
\right)
\right],
$$

其中

$$
\Theta_E
=
\frac{\alpha_h p_s}{\rho c_p\Delta T}.
$$

代码中的温度尺度为

$$
\Delta T
=
\begin{cases}
\texttt{delta\_t\_scale}, & \text{if explicitly configured},\\
\alpha_h p_s/(\rho c_p), & \text{otherwise}.
\end{cases}
$$

因此默认情况下 $\Theta_E=1$。

无量纲温度离散系统为

$$
\bar K^T_{ij}\bar T_j=\bar f^T_i,
$$

$$
\bar K^T_{ij}
=
\int_{\hat\Omega}
D_x
\frac{\partial N_j}{\partial\bar x}
\frac{\partial N_i}{\partial\bar x}
+
D_z
\frac{\partial N_j}{\partial\bar z}
\frac{\partial N_i}{\partial\bar z}
\,d\hat\Omega
+
\int_{\hat\Omega}
\left(
\bar q_x\frac{\partial N_j}{\partial\bar x}
+
\frac{\bar q_z}{l_r}
\frac{\partial N_j}{\partial\bar z}
\right)N_i\,d\hat\Omega,
$$

$$
\bar f^T_i
=
\int_{\hat\Omega}
\bar\Phi_E N_i\,d\hat\Omega.
$$

其中

$$
D_x(\bar h)=\frac{k_{\mathrm{lub}}c\bar h}{\rho c_p Q_f R},
\qquad
D_z(\bar h)=\frac{D_x(\bar h)}{l_r^2},
$$

$$
Q_f=\frac{p_sc^3}{12\mu_0l_r^2R},
\qquad
Q_w=Q_fl_rR=\frac{p_sc^3}{12\mu_0l_r}.
$$

其中 $Q_f$ 是面内体积通量尺度，单位为 m$^2$/s；$Q_w$ 是供油孔体积流量尺度，
单位为 m$^3$/s。`k_lub` 是三维导热率 W/(m·K)，因此无量纲扩散系数必须随
局部膜厚 $\bar h$ 变化。

#### 2.3 SUPG 稳定化、边界与点源

温度方程通常是对流占优问题。当前默认使用 `k_lub = 0.0` 并开启 SUPG，让空间对流稳定化由 SUPG 承担；若设置 `k_lub > 0`，则显式启用由局部膜厚积分得到的物理面内导热。保留的有量纲离散形式中，局部单元 Péclet 数和稳定参数为

$$
\mathrm{Pe}_h
=
\frac{|\mathbf q|h_e}{2\alpha_{\mathrm{stab}}},
\qquad
\alpha_{2D}(h)
=
\frac{k_{\mathrm{lub}}h}{\rho c_p},
$$

$$
\tau
=
\left(
\coth(\mathrm{Pe}_h)-\frac{1}{\mathrm{Pe}_h}
\right)
\frac{h_e}{2|\mathbf q|}.
$$

附加矩阵和载荷为

$$
K^{\mathrm{SUPG}}_{ij}
=
\int_{\Omega_h}
\tau\,\rho c_p
\left(\mathbf q\cdot\nabla N_i\right)
\left(\mathbf q\cdot\nabla N_j\right)d\Omega,
$$

$$
f^{\mathrm{SUPG}}_i
=
\int_{\Omega_h}
\tau
\left(\mathbf q\cdot\nabla N_i\right)\Phi\,d\Omega.
$$

无量纲路径使用相同结构，但不再乘 $\rho c_p$，并以无量纲对流向量

$$
\bar{\mathbf q}_{\mathrm{conv}}
=
\left(\bar q_x,\frac{\bar q_z}{l_r}\right)
$$

计算 $\tau$。

温度边界条件在当前实现中为：

- 入口边界 $x=x_{\min}$：Dirichlet，$T=T_{\mathrm{supply}}$；
- 轴向侧边界：由 `axial_side_bc` 控制，可为固定温度、绝热自然边界，或只在流入侧固定温度；
- 出口边界：自然边界，扩散通量项不额外指定，热量主要由对流带出。

供油孔注入作为节点点源加入。对每个正向注入流量 $Q_i$，找到最近温度节点 $j$，有量纲路径修改线性系统：

$$
K_{jj}\mathrel{+}= \rho c_p Q_i,
\qquad
f_j\mathrel{+}= \rho c_p Q_i T_{\mathrm{supply}}.
$$

无量纲路径对应为

$$
\bar K_{jj}\mathrel{+}= \bar Q_i,
\qquad
\bar f_j\mathrel{+}= \bar Q_i\bar T_{\mathrm{supply}},
$$

其中当前温度标度下 $\bar T_{\mathrm{supply}}=0$。

这里无量纲点源流量定义为

$$
q_{n,i}=\frac{Q_i}{Q_w},
\qquad
Q_w=Q_fl_rR
=\frac{p_sc^3}{12\mu_0l_r}.
$$

供油孔接口同时提供 `position_nondim`、`position_dim`、`q_nondim`、`q_vol` 和
同一个 `qw`。热包装只把无量纲位置与 `q_nondim` 传入无量纲核心，旧 `flow`
三元组仅保留为有量纲兼容输出，不再参与热核装配。

最终施加 Dirichlet 条件后，用稀疏线性求解器求解温度节点值：

$$
K_{\mathrm{bc}}T=f_{\mathrm{bc}}.
$$

有量纲结果再裁剪到

$$
T_{\mathrm{supply}}-5
\le T_i \le
T_{\mathrm{supply}}+\texttt{max\_delta\_t},
$$

无量纲结果按相同物理上下限换算后裁剪。

### 3. 压力-温度耦合计算流程

热-流耦合迭代的未知量是节点粘度场 $\mu_i$。第 $k$ 次迭代中的计算流程为：

1. 初始化

$$
\mu_i^{(0)}=\mu_0.
$$

2. 把当前粘度比写入压力节点：

$$
\bar\mu_i^{(k)}=\frac{\mu_i^{(k)}}{\mu_0}.
$$

3. 固定参考尺度。压力方程右端的 $\Lambda_0$ 由参考粘度 $\mu_0$ 定义，迭代中不随局部粘度漂移：

$$
\Lambda_0
=
\frac{3\mu_0\omega L^2}{2p_sc^2}.
$$

4. 求解 Reynolds 方程，得到压力场 $p^{(k)}$，并更新温度方程使用的梯度
   $\nabla p^{(k)}$。

5. 根据耦合模式选择温度方程粘度输入：

$$
\mu_T^{(k)}(x,z)
=
\begin{cases}
\mu_i^{(k)} \text{ mapped to thermal nodes}, & \texttt{coupling="full"},\\
\overline{\mu}^{(k)}, & \texttt{coupling="half"}.
\end{cases}
$$

6. 用 $h^{(k)}$、$p^{(k)}$、$\nabla p^{(k)}$ 和 $\mu_T^{(k)}$ 组装并求解温度方程，得到
   $T^{(k)}$。

7. 将温度场映射回膜节点，并由指数粘温关系计算目标粘度：

有量纲形式：

$$
\mu_{\mathrm{target},i}^{(k)}
=
\mu_0
\exp\left[-\beta\left(T_i^{(k)}-T_{\mathrm{ref}}\right)\right].
$$

无量纲形式：

$$
\frac{\mu_{\mathrm{target},i}^{(k)}}{\mu_0}
=
\exp\left[
-\beta_{\mathrm{nd}}
\left(
\bar T_i^{(k)}-\bar T_{\mathrm{ref}}
\right)
\right].
$$

8. 用松弛因子 $\alpha$ 更新粘度场：

$$
\mu_i^{(k+1)}
=
(1-\alpha)\mu_i^{(k)}
+\alpha\mu_{\mathrm{target},i}^{(k)}.
$$

9. 计算收敛误差：

$$
\varepsilon_\mu^{(k)}
=
\frac{
\max_i|\mu_i^{(k+1)}-\mu_i^{(k)}|
}{
\max_i|\mu_i^{(k)}|
}.
$$

当

$$
\varepsilon_\mu^{(k)} < \texttt{tol}
$$

时认为热-流-粘度耦合收敛；否则进入下一次迭代。若启用自适应松弛，`AdaptiveDampController` 会根据误差变化调整 $\alpha$。

收敛后，代码再用最终粘度场执行一次压力求解和一次温度求解，输出最终压力、温度、
粘度、供油孔流量以及结构化后处理场。流量诊断同时给出
`q_orifice_total_nondim` 和 `q_orifice_total_vol`；兼容字段 `q_orifice_total`
固定表示 m$^3$/s。若启用非稳态热项，第一次调用会先求稳态温度作为 $T^0$；
之后每次 `output()` 使用上一时刻缓存的 $T^n$，并只在当前步收敛后回写
$T^{n+1}$。稳态初始化或瞬态步未收敛时抛出错误并保留旧缓存。

---

## 2 物理模型与公式

### 2.1 粘度-温度关系

采用指数衰减模型。在当前实现中，变量命名统一为 `miu_*`，其物理意义对应动力粘度 $\mu$：

$$
\mu(T) = \mu_{\text{ref}} \exp\bigl[-\beta\,(T - T_{\text{ref}})\bigr]
$$

| 符号 | 含义 | 配置参数 |
|------|------|----------|
| $\mu_{\text{ref}}$ | 参考温度下的动力粘度 | `miu0`（默认取初始粘度） |
| $T_{\text{ref}}$ | 参考温度 | `t_ref`（默认取 `t_in`） |
| $\beta$ | 粘温系数 | `beta = 0.03` |

### 2.2 能量方程

默认情况下，在油膜 $x$-$z$ 平面上求解稳态对流-扩散能量方程：

$$
\rho\, c_v \left( q_x \frac{\partial T}{\partial x} + q_z \frac{\partial T}{\partial z} \right)
= \nabla\cdot\left(k_{\mathrm{lub}}h\nabla T\right) + \Phi
$$

当启用非稳态项时，控制方程扩展为：

$$
\rho c_v h\,\frac{\partial T}{\partial t}
+ \rho c_v \left( q_x \frac{\partial T}{\partial x} + q_z \frac{\partial T}{\partial z} \right)
= \nabla\cdot\left(k_{\mathrm{lub}}h\nabla T\right) + \Phi
$$

其中时间项前乘以局部膜厚 $h$，表示按单位轴承面积积算油膜内的热容储存。

说明：本模型按不可压缩液体处理，采用 $c_p \approx c_v$。代码中只配置了 `cp_lub`，并通过

$$
\rho c_v \approx \rho c_p = \rho\,\texttt{cp\_lub}
$$

构造离散系数 `rho_cv`，未重复定义单独的 `cv` 配置变量。

#### 面内体积通量

$$
q_x = \frac{Uh}{2} - \frac{h^3}{12\mu} \frac{\partial p}{\partial x}, \qquad
q_z = -\frac{h^3}{12\mu} \frac{\partial p}{\partial z}
$$

其中 $U = \omega R$ 为轴颈表面线速度，$\omega = 2\pi n / 60$。

#### 耗散热源

$$
\Phi = \alpha_h \left( \frac{\mu\, U^2}{h} + \frac{h^3}{12\mu} \left[ \left(\frac{\partial p}{\partial x}\right)^2 + \left(\frac{\partial p}{\partial z}\right)^2 \right] \right)
$$

第一项为 Couette 剪切生热，第二项为 Poiseuille 压力梯度耗散，$\alpha_h$ 为热分配系数（`heat_partition = 0.9`）。

| 符号 | 含义 | 配置参数 |
|------|------|----------|
| $k_{\mathrm{lub}}$ | 润滑油三维导热率，单位 W/(m·K)；二维系数为 $k_{\mathrm{lub}}h$ | `k_lub = 0.0` 默认值 |
| $\rho c_v$ | 体积热容；当前配置以 $c_p\approx c_v$ 记作 `cp_lub` | `cp_lub = 2000` J/(kg·K)，故 $\rho c_p$ 的单位为 J/(m³·K) |
| $h$ | 油膜厚度（有量纲） | 从 film 模型获取 |
| $\nabla p$ | 压力梯度 | 由 Reynolds 求解结果差分得到 |

#### 能量方程的无量纲化

以下沿用轴承主方程的无量纲记号：

$$
\bar{x} = \frac{x}{R}, \qquad
\bar{z} = \frac{2z}{L}, \qquad
\bar{h} = \frac{h}{c}, \qquad
\bar{p} = \frac{p}{p_s}, \qquad
\bar{t} = \Omega t, \qquad
\bar{\mu} = \frac{\mu}{\mu_0}
$$

并引入温度无量纲化和面内体积通量标度：

$$
\bar{T} = \frac{T - T_{\text{supply}}}{\Delta T},
\qquad
q_x = Q_f\,\bar{q}_x,
\qquad
q_z = Q_f\,\bar{q}_z,
\qquad
l_r = \frac{L}{2R}
$$

其中 $\Delta T$ 为选定的特征温升，$Q_f$ 是面内体积通量标度。于是有

$$
x = R\bar{x},
\qquad
z = l_r R\bar{z},
\qquad
\frac{\partial}{\partial x} = \frac{1}{R}\frac{\partial}{\partial \bar{x}},
\qquad
\frac{\partial}{\partial z} = \frac{1}{l_r R}\frac{\partial}{\partial \bar{z}},
\qquad
\frac{\partial}{\partial t} = \Omega\frac{\partial}{\partial \bar{t}}
$$

将

$$
T = T_{\text{supply}} + \Delta T\,\bar{T},
\qquad
h = c\bar{h},
\qquad
q_x = Q_f\bar{q}_x,
\qquad
q_z = Q_f\bar{q}_z
$$

代入非稳态能量方程

$$
\rho c_v h\,\frac{\partial T}{\partial t}
+ \rho c_v \left(q_x\frac{\partial T}{\partial x} + q_z\frac{\partial T}{\partial z}\right)
= \nabla\cdot\left(k_{\mathrm{lub}}h\nabla T\right) + \Phi
$$

得到

$$
\rho c_v c\Omega\Delta T\,\bar{h}\,\frac{\partial \bar{T}}{\partial \bar{t}}
+ \rho c_v Q_f\Delta T
\left(
\frac{\bar{q}_x}{R}\frac{\partial \bar{T}}{\partial \bar{x}}
+ \frac{\bar{q}_z}{l_r R}\frac{\partial \bar{T}}{\partial \bar{z}}
\right)
= \frac{k_{\mathrm{lub}}c\Delta T}{R^2}
\left[
\frac{\partial}{\partial\bar x}
\left(\bar h\frac{\partial\bar T}{\partial\bar x}\right)
+\frac{1}{l_r^2}\frac{\partial}{\partial\bar z}
\left(\bar h\frac{\partial\bar T}{\partial\bar z}\right)
\right]
+ \Phi
$$

再整体除以对流项尺度 $\rho c_v Q_f\Delta T / R$，可得无量纲能量方程：

$$
\mathrm{St}_{\Omega}\,\bar{h}\,\frac{\partial \bar{T}}{\partial \bar{t}}
+ \bar{q}_x\frac{\partial \bar{T}}{\partial \bar{x}}
+ \frac{1}{l_r}\bar{q}_z\frac{\partial \bar{T}}{\partial \bar{z}}
= D_0
\left[
\frac{\partial}{\partial\bar x}
\left(\bar h\frac{\partial\bar T}{\partial\bar x}\right)
+\frac{1}{l_r^2}\frac{\partial}{\partial\bar z}
\left(\bar h\frac{\partial\bar T}{\partial\bar z}\right)
\right]
+ \bar{\Phi}_E
$$

其中

$$
 D_0 = \frac{k_{\mathrm{lub}}c}{\rho c_v Q_f R},
\qquad
\mathrm{Pe}_0 = \frac{1}{D_0}
=\frac{\rho c_v Q_f R}{k_{\mathrm{lub}}c},
\qquad
\mathrm{St}_{\Omega} = \frac{c\Omega R}{Q_f},
\qquad
\bar{\Phi}_E = \frac{R\Phi}{\rho c_v Q_f\Delta T}.
$$

上式是从原始对流-扩散能量方程直接得到的**完整无量纲形式**。但对当前油膜工况而言，通常有

$$
\mathrm{Pe}_0 \gg 1
$$

因此温度场在物理上属于明显的**对流主导**问题，面内导热项

$$
D_0
\left[
\frac{\partial}{\partial\bar x}
\left(\bar h\frac{\partial\bar T}{\partial\bar x}\right)
+\frac{1}{l_r^2}\frac{\partial}{\partial\bar z}
\left(\bar h\frac{\partial\bar T}{\partial\bar z}\right)
\right]
$$

可视为高阶小量。在后续建模与代理训练中，推荐把它从**物理控制方程**中忽略，得到约化温度方程：

$$
\mathrm{St}_{\Omega}\,\bar{h}\,\frac{\partial \bar{T}}{\partial \bar{t}}
+ \bar{q}_x\frac{\partial \bar{T}}{\partial \bar{x}}
+ \frac{1}{l_r}\bar{q}_z\frac{\partial \bar{T}}{\partial \bar{z}}
= \bar{\Phi}_E
$$

若完全去掉扩散项，纯对流 Galerkin 离散更容易出现网格依赖和非物理振荡。当前默认实现令
`k_lub = 0.0` 并用 SUPG 稳定空间对流。只有显式设置 `k_lub > 0` 时，才组装下列带物理面内导热项的温度方程：

$$
\mathrm{St}_{\Omega}\,\bar{h}\,\frac{\partial \bar{T}}{\partial \bar{t}}
+ \bar{q}_x\frac{\partial \bar{T}}{\partial \bar{x}}
+ \frac{1}{l_r}\bar{q}_z\frac{\partial \bar{T}}{\partial \bar{z}}
=D_0
\left[
\frac{\partial}{\partial\bar x}
\left(\bar h\frac{\partial\bar T}{\partial\bar x}\right)
+\frac{1}{l_r^2}\frac{\partial}{\partial\bar z}
\left(\bar h\frac{\partial\bar T}{\partial\bar z}\right)
\right]
+ \bar{\Phi}_E
$$

高 Péclet 工况下，这项物理面内导热通常很小；默认零值时，SUPG 的流线稳定仍然有效，
但不能把 SUPG 的数值稳定作用解释为物理导热。

其中热源项 $\bar{\Phi}_E$ 还可以继续按 $\bar{h}$、$\bar{\mu}$、$\bar{p}$ 展开。由

$$
\Phi = \alpha_h \left( \frac{\mu U^2}{h} + \frac{h^3}{12\mu} \left[ \left(\frac{\partial p}{\partial x}\right)^2 + \left(\frac{\partial p}{\partial z}\right)^2 \right] \right)
$$

代入

$$
\mu = \mu_0\bar{\mu},
\qquad
h = c\bar{h},
\qquad
p = p_s\bar{p},
\qquad
U = \omega R,
\qquad
\frac{\partial p}{\partial x} = \frac{p_s}{R}\frac{\partial \bar{p}}{\partial \bar{x}},
\qquad
\frac{\partial p}{\partial z} = \frac{p_s}{l_r R}\frac{\partial \bar{p}}{\partial \bar{z}}
$$

并使用当前代码 `ThermalNondimScales.qf` 中的面内体积通量标度

$$
Q_f = \frac{p_s c^3}{12\mu_0 l_r^2 R}
$$

可得

$$
\bar{\Phi}_E
= \frac{R\Phi}{\rho c_v Q_f\Delta T}
= \Theta_E
\left[
\frac{\Lambda_0^2}{3l_r^2}\frac{\bar{\mu}}{\bar{h}}
+ \frac{\bar{h}^3}{\bar{\mu}}
\left(
l_r^2\left(\frac{\partial \bar{p}}{\partial \bar{x}}\right)^2
+ \left(\frac{\partial \bar{p}}{\partial \bar{z}}\right)^2
\right)
\right]
$$

其中把所有纯参数系数合并为

$$
\Theta_E = \frac{\alpha_h p_s}{\rho c_v\Delta T}
$$

而

$$
\Lambda_0 = \frac{3\mu_0\omega L^2}{2p_s c^2}
$$

与 Reynolds 方程中的参考轴承数保持一致。

上式已经是一个比较紧凑的表示：

- 场变量只保留 $\bar{h}$、$\bar{\mu}$、$\bar{p}$。
- 额外无量纲参数只保留 $\Theta_E$、$\Lambda_0$、$l_r$。
- 其中第一项对应 Couette 剪切生热，第二项对应 Poiseuille 压力梯度耗散。

如果目标是做代理训练，通常希望进一步压缩参数维数。此时最自然的做法是把温升尺度直接选为

$$
\Delta T_E = \frac{\alpha_h p_s}{\rho c_v}
$$

则有 $\Theta_E = 1$，热源项进一步化简为

$$
\bar{\Phi}_E
= \frac{\Lambda_0^2}{3l_r^2}\frac{\bar{\mu}}{\bar{h}}
+ \frac{\bar{h}^3}{\bar{\mu}}
\left(
l_r^2\left(\frac{\partial \bar{p}}{\partial \bar{x}}\right)^2
+ \left(\frac{\partial \bar{p}}{\partial \bar{z}}\right)^2
\right)
$$

此时无量纲热源中只剩下 $\Lambda_0$ 和 $l_r$ 两个显式参数，更适合后续代理模型训练，因为：

- 温度方程中的源项幅值不再额外携带一个可变前因子。
- 热源结构被压缩成“剪切项 + 压差耗散项”的固定模板。
- Reynolds 方程与能量方程共享同一组核心无量纲参数，更利于统一输入特征。

若只考虑稳态热场，则时间项消失，无量纲方程退化为

$$
\bar{q}_x\frac{\partial \bar{T}}{\partial \bar{x}}
+ \frac{1}{l_r}\bar{q}_z\frac{\partial \bar{T}}{\partial \bar{z}}
= \bar{\Phi}_E
$$

这表明：

- 在物理模型层面，稳态温度场可近似看成“对流输运 + 耗散热源”的平衡。
- 在数值求解层面，仍可额外保留 $\mathrm{Pe}_{\text{stab}}^{-1}\nabla^2\bar{T}$ 作为稳定项。
- 因此高 Péclet 工况下，$\mathrm{Pe}$ 不再作为主导物理输入，而更接近一个数值稳定化量。

若进一步代入

$$
U = \omega R = \gamma\Omega R,
\qquad
\Lambda_0 = \frac{3\mu_0\omega L^2}{2p_s c^2},
\qquad
\gamma = \frac{\omega}{\Omega}
$$

则无量纲通量 $\bar{q}_x, \bar{q}_z$ 可继续写成 $\bar{h}$、$\bar{p}$、$\bar{\mu}$ 与参考轴承数 $\Lambda_0$ 的函数；也就是说，在物理约化模型中温度方程的主导无量纲输入由 Reynolds 方程给出，而扩散项只在数值实现中作为稳定化项保留。

#### 边界条件

- **入口**（$x = x_{\min}$）与 **两侧**（$z = z_{\min},\, z_{\max}$）：Dirichlet $T = T_{\text{supply}}$
- **出口**（$x = x_{\max}$）：自然边界条件 $\partial T/\partial n = 0$（对流将热量带出）

#### 非稳态项的时间离散

当前实现采用**一阶隐式 Euler**推进。记时间层为

$$
t_n = n\Delta t, \qquad t_{n+1} = (n+1)\Delta t
$$

其中第 $n$ 步温度场 $T^n = T(x,z,t_n)$ 已知，第 $n+1$ 步温度场 $T^{n+1} = T(x,z,t_{n+1})$ 为当前时间步的**待求变量**。时间导数在 $t_{n+1}$ 处采用后向差分：

$$
\left.\rho c_v h\,\frac{\partial T}{\partial t}\right|_{t_{n+1}}
\approx
\rho c_v h^{n+1}\,\frac{T^{n+1} - T^n}{\Delta t}
$$

这里 $h^{n+1}$、$q_x^{n+1}$、$q_z^{n+1}$ 与热源 $\Phi^{n+1}$ 都取当前时刻 $t_{n+1}$ 的值；因此隐式 Euler 离散后的控制方程应写为：

$$
\rho c_v h^{n+1}\,\frac{T^{n+1} - T^n}{\Delta t}
+ \rho c_v \left(
q_x^{n+1} \frac{\partial T^{n+1}}{\partial x}
+ q_z^{n+1} \frac{\partial T^{n+1}}{\partial z}
\right)
= \nabla\cdot\left(k_{\mathrm{lub}}h^{n+1}\nabla T^{n+1}\right)
+ \Phi^{n+1}
$$

进一步整理为有限元线性系统：

$$
\left(K_{\text{adv-diff}}^{n+1} + M_t^{n+1}\right) T^{n+1}
= f_{\Phi}^{n+1} + M_t^{n+1} T^n
$$

其中

$$
M_t^{n+1} = \int_\Omega \frac{\rho c_v h^{n+1}}{\Delta t} u v\, d\Omega
$$

表示当前步左端附加的瞬态质量矩阵，对应代码中的瞬态质量项 `_transient_mass_form`；而

$$
\int_\Omega \frac{\rho c_v h^{n+1}}{\Delta t} T^n v\, d\Omega
$$

表示右端历史温度项，对应 `_transient_rhs_form`。这里唯一来自上一步 $t_n$ 的量是历史温度场 $T^n$；矩阵中的系数项仍按当前步 $t_{n+1}$ 组装。

因此每个时间步内，温度场求解不是显式更新，而是通过一次新的有限元线性系统直接得到 $T^{n+1}$，稳定性优于显式格式。

### 2.3 SUPG 稳定化

在本文推荐的物理近似中，面内热传导很小，温度场本质上是一个对流主导方程。
默认 `k_lub = 0.0` 时并不存在额外的各向同性扩散层；当前实现只使用
**SUPG（Streamline Upwind Petrov-Galerkin）** 沿流线方向稳定空间对流离散。
只有用户显式设置正的 `k_lub` 时，才同时出现由局部膜厚积分得到的物理面内导热项。

因此这里的单元 Péclet 数主要用于构造 SUPG 稳定参数：

**单元 Péclet 数**：

$$
\mathrm{Pe}_{h,e} = \frac{|\mathbf{q}|\, h_e}{2\alpha_{2D,e}},
\quad
\alpha_{2D,e} = \frac{k_{\mathrm{lub}}h_e^{\mathrm{film}}}{\rho c_v}
$$

**稳定参数**：

$$
\tau = \frac{\xi(\mathrm{Pe}_{h,e})\, h_e}{2|\mathbf{q}|}, \quad \xi(\mathrm{Pe}) = \coth(\mathrm{Pe}) - \frac{1}{\mathrm{Pe}}
$$

**附加刚度与载荷**：

$$
K_{\text{SUPG}} = \int_\Omega \tau\, \rho c_v\, (\mathbf{q} \cdot \nabla v)\,(\mathbf{q} \cdot \nabla u)\, d\Omega
$$

$$
f_{\text{SUPG}} = \int_\Omega \tau\, (\mathbf{q} \cdot \nabla v)\, \Phi\, d\Omega
$$

当前 SUPG 实现只对空间对流-热源残差做流线稳定化，不把隐式 Euler 的瞬态储热项并入
SUPG 残差。它的用途是稳态/每个时间步空间对流方程的数值稳定，不负责时间离散稳定；
按当前建模目的，这一点不作为推导错误，也不需要修改瞬态质量项。

> 默认 `ThermalConfig.supg = True` 且 `k_lub = 0.0`，没有额外的各向同性扩散层；
> 对流稳定仅由 SUPG 提供。正的 `k_lub` 表示另行启用随局部膜厚变化的物理面内导热。

### 2.4 变粘度下的弱形式推导与一致性检查

本节给出压力场与温度场弱形式，并与代码实现逐项对照。

#### 2.4.1 压力方程（Reynolds）弱形式

在当前实现中采用"LHS 用局部粘度，RHS 固定参考粘度"的策略。
无量纲 Reynolds 方程的强形式为（不含节流流量项 $\bar{q}$，对应教材公式 1-16）：

$$
l_r^2\frac{\partial}{\partial\bar x}\!\left(\frac{\bar h^3}{\bar\mu}\frac{\partial\bar p}{\partial\bar x}\right)
+\frac{\partial}{\partial\bar z}\!\left(\frac{\bar h^3}{\bar\mu}\frac{\partial\bar p}{\partial\bar z}\right)
= \Lambda_0\,\frac{\partial\bar h}{\partial\bar x}
+2\Lambda_0\frac{\partial\bar h}{\partial\bar t}
= \Lambda_0\,\frac{\partial\bar h}{\partial\bar x}
+2\Lambda_0v_f\dot{\bar h}_{\mathrm{code}}
$$

其中 $\bar\mu=\mu/\mu_0$，$l_r = L/(2R)$，$\Lambda_0$ 为参考粘度 $\mu_0$ 对应的无量纲轴承数；代码实现中仍沿用历史变量名 `vx_ref`。
注意 RHS 为 **正号**，与教材 (1-16) 一致（$l_r^2$ 等价于教材中 $\psi^2$，$\psi = L/D$）。
取测试函数 $v$，对 LHS 做分部积分（Green 公式，忽略边界项）：

$$
\int_\Omega v\,\nabla\!\cdot\!\left(\frac{h^3}{\bar\mu}\nabla p\right)d\Omega
\;\xrightarrow{\text{IBP}}\;
-\int_\Omega \frac{h^3}{\bar\mu}\nabla p\cdot\nabla v\,d\Omega
$$

代入强形式得弱式（分部积分引入负号）：

$$
\int_\Omega \frac{h^3}{\bar\mu}
\left(l_r^2\frac{\partial p}{\partial x}\frac{\partial v}{\partial x}
+\frac{\partial p}{\partial z}\frac{\partial v}{\partial z}\right)\,d\Omega
=
\int_\Omega \left(-\Lambda_0\frac{\partial\bar h}{\partial\bar x}-2\Lambda_0 v_f\dot{\bar h}_{\mathrm{code}}\right) v\,d\Omega
$$

即 FEM 系统 $Kp = f$，其中 $f_i$ 的被积函数带负号。

对应代码实现：

- 左端（`BilinearForm`）：`_reynolds_lhs_miu` → `h3_over_miu * (lr² ∂u/∂x ∂v/∂x + ∂u/∂z ∂v/∂z)`
- 右端（`LinearForm`）：`_reynolds_rhs_miu0` →
  `(-lambda0 * dh_dx - 2*lambda0*vf*dh_dt) * v`，其中代码内的
  `dh_dt = xct*sin(theta) - yct*cos(theta)` 是 $\dot{\bar h}_{\mathrm{code}}$，不是已经乘过
  `vf` 的 $\partial\bar h/\partial\bar t$。

**符号一致性**：强形式 RHS 正号 → 分部积分后弱形式 RHS 负号 → 与代码 `_reynolds_rhs_miu0` 完全一致。

### 2.5 压力与温度方程的符号压缩

若目标是做代理训练，则应尽量减少“可独立输入”的无量纲量个数。对当前压力方程与温度方程而言，以下符号实际上都可以压缩：

- $\bar{q}_x$、$\bar{q}_z$ 不是独立变量，而是由 $\bar{h}$、$\bar{\mu}$、$\bar{p}$、$l_r$、$\Lambda_0$ 派生。
- $\bar{\Phi}_E$ 不是独立变量，而是由 $\bar{h}$、$\bar{\mu}$、$\bar{p}$、$l_r$、$\Lambda_0$ 派生。
- 旧记号 $v_{x0}$ 只是代码变量名 `vx_ref` 的物理映射，其正确物理记号应统一为 $\Lambda_0$。

因此，两套方程在**物理模型层面**可以统一压缩到同一组核心无量纲量：

$$
\{l_r,\,\Lambda_0,\,\mathrm{St}_{\Omega},\,v_f\}
$$

以及四个场变量：

$$
\{\bar{h},\,\bar{\mu},\,\bar{p},\,\bar{T}\}
$$

其中：

- $l_r$ 必须保留，因为它直接控制轴向与周向导数的各向异性尺度。
- $\Lambda_0$ 必须保留，因为它同时进入 Reynolds 方程源项、通量的 Couette 分量和热源的剪切项。
- $\mathrm{St}_{\Omega}$ 只在非稳态热方程中保留；若只做稳态代理，可从输入中去掉。
- $v_f$ 只在挤压项存在时保留；若仅做静态膜厚问题，也可去掉。

若训练数据来自显式设置 `k_lub > 0` 的有限元求解器，则可额外引入

$$
D_0=\frac{k_{\mathrm{lub}}c}{\rho c_vQ_fR}
$$

作为物理导热参数记录；但对当前高 Péclet 工况，它通常不应与 $l_r$、$\Lambda_0$
一样被视为主导输入。SUPG 参数属于离散设置，不应混入物理参数集。

在这组最小符号集中，Reynolds 方程可写成

$$
l_r^2\frac{\partial}{\partial \bar{x}}\!\left(\frac{\bar h^3}{\bar\mu}\frac{\partial \bar p}{\partial \bar x}\right)
+ \frac{\partial}{\partial \bar z}\!\left(\frac{\bar h^3}{\bar\mu}\frac{\partial \bar p}{\partial \bar z}\right)
= \Lambda_0\frac{\partial \bar h}{\partial \bar x}
+ 2\Lambda_0\frac{\partial \bar h}{\partial \bar t}
= \Lambda_0\frac{\partial \bar h}{\partial \bar x}
+ 2\Lambda_0v_f\dot{\bar h}_{\mathrm{code}}
$$

对应的无量纲通量不再单独作为独立符号输入，而是直接压缩为

$$
\bar q_x = \Lambda_0\bar h - l_r^2\frac{\bar h^3}{\bar\mu}\frac{\partial \bar p}{\partial \bar x},
\qquad
\bar q_z = -l_r\frac{\bar h^3}{\bar\mu}\frac{\partial \bar p}{\partial \bar z}
$$

若采用前述推荐温升尺度

$$
\Delta T_E = \frac{\alpha_h p_s}{\rho c_v}
$$

则热源项也不必再保留独立系数 $\Theta_E$，可直接写成

$$
\bar{\Phi}_E
= \frac{\Lambda_0^2}{3l_r^2}\frac{\bar{\mu}}{\bar{h}}
+ \frac{\bar{h}^3}{\bar{\mu}}
\left(
l_r^2\left(\frac{\partial \bar{p}}{\partial \bar{x}}\right)^2
+ \left(\frac{\partial \bar{p}}{\partial \bar{z}}\right)^2
\right)
$$

于是温度方程可以进一步压缩为

$$
\mathrm{St}_{\Omega}\,\bar h\frac{\partial \bar T}{\partial \bar t}
+ \left(\Lambda_0\bar h - l_r^2\frac{\bar h^3}{\bar\mu}\frac{\partial \bar p}{\partial \bar x}\right)
\frac{\partial \bar T}{\partial \bar x}
- \frac{\bar h^3}{\bar\mu}\frac{\partial \bar p}{\partial \bar z}
\frac{\partial \bar T}{\partial \bar z}
= \bar{\Phi}_E
$$

轴向项中没有额外的 $1/l_r$：代码先定义
$\bar q_z=-l_r(\bar h^3/\bar\mu)\,\partial_{\bar z}\bar p$，随后对流系数使用
$\bar q_z/l_r$，两者正好约去。旧版在压缩式中保留 $1/l_r$ 是代数错误。

这样，原先作为中间符号存在的 $\bar q_x$、$\bar q_z$、$\bar{\Phi}_E$ 都被压缩回了核心场变量和核心参数中。

若配置 `k_lub > 0`，则在上式右端再补上

$$
D_0
\left[
\frac{\partial}{\partial\bar x}
\left(\bar h\frac{\partial\bar T}{\partial\bar x}\right)
+\frac{1}{l_r^2}\frac{\partial}{\partial\bar z}
\left(\bar h\frac{\partial\bar T}{\partial\bar z}\right)
\right]
$$

作为物理面内导热项。

对代理训练而言，可进一步按任务裁剪：

- 稳态温度代理：保留 $\{l_r,\Lambda_0\}$。
- 非稳态温度代理：保留 $\{l_r,\Lambda_0,\mathrm{St}_{\Omega}\}$。
- 含挤压膜厚代理：在以上基础上再加入 $v_f$。
- 若训练数据来自固定 `k_lub` 的求解器，可不显式输入 $D_0$；若改变物理导热率，则再把 $D_0$ 作为输入或数据标签加入。
- 若膜厚场 $\bar h$ 已由上游模型给定，则它应作为场输入，而不是新的全局无量纲参数。

#### 2.4.2 温度方程弱形式

在物理上忽略热扩散后，温度方程可写为：

$$
\rho c_v h\,\frac{\partial T}{\partial t} + \rho c_v(\mathbf q\cdot\nabla T)=\Phi
$$

若显式配置 `k_lub > 0`，计算式再加入物理面内导热项：

$$
-\nabla\cdot\left(k_{\mathrm{lub}}h\nabla T\right)
+ \rho c_v h\,\frac{\partial T}{\partial t}
+ \rho c_v(\mathbf q\cdot\nabla T)=\Phi
$$

取测试函数 $v$，标准 Galerkin 弱式：

$$
\int_\Omega k_{\mathrm{lub}}h\nabla T\cdot\nabla v\,d\Omega
+\int_\Omega \rho c_v h\,\frac{\partial T}{\partial t} v\,d\Omega
+\int_\Omega \rho c_v(\mathbf q\cdot\nabla T) v\,d\Omega
=\int_\Omega \Phi v\,d\Omega
$$

若把时间项单独写到“仅在非稳态启用”的形式，则弱式可表示为：

$$
\int_\Omega \rho c_v h\,\frac{\partial T}{\partial t} v\,d\Omega
+\int_\Omega k_{\mathrm{lub}}h\nabla T\cdot\nabla v\,d\Omega
+\int_\Omega \rho c_v(\mathbf q\cdot\nabla T) v\,d\Omega
=\int_\Omega \Phi v\,d\Omega
$$

采用隐式 Euler 后，在 $t_{n+1}$ 时刻以 $T^{n+1}$ 为待求变量、以 $T^n$ 为已知历史场，有：

$$
\int_\Omega \frac{\rho c_v h^{n+1}}{\Delta t} T^{n+1} v\,d\Omega
+\int_\Omega k_{\mathrm{lub}}h^{n+1}\nabla T^{n+1}\cdot\nabla v\,d\Omega
+\int_\Omega \rho c_v(\mathbf q^{n+1}\cdot\nabla T^{n+1}) v\,d\Omega
=\int_\Omega \Phi^{n+1} v\,d\Omega
+\int_\Omega \frac{\rho c_v h^{n+1}}{\Delta t} T^n v\,d\Omega
$$

若改用前述无量纲温度场，记计算域为

$$
\hat{\Omega} = \{(\bar{x},\bar{z})\},
\qquad
d\hat{\Omega}=d\bar{x}\,d\bar{z}
$$

并取无量纲测试函数 $\bar v\in V_0$。从含物理面内导热的无量纲强形式出发：

$$
\mathrm{St}_{\Omega}\,\bar h\frac{\partial \bar T}{\partial \bar t}
+ \bar q_x\frac{\partial \bar T}{\partial \bar x}
+ \frac{1}{l_r}\bar q_z\frac{\partial \bar T}{\partial \bar z}
=
D_0
\left[
\frac{\partial}{\partial\bar x}
\left(\bar h\frac{\partial\bar T}{\partial\bar x}\right)
+\frac{1}{l_r^2}\frac{\partial}{\partial\bar z}
\left(\bar h\frac{\partial\bar T}{\partial\bar z}\right)
\right]
+ \bar\Phi_E
$$

将扩散项移到左端，并乘以 $\bar v$ 在 $\hat{\Omega}$ 上积分：

$$
\int_{\hat{\Omega}}
\mathrm{St}_{\Omega}\,\bar h
\frac{\partial \bar T}{\partial \bar t}\bar v\,d\hat{\Omega}
+
\int_{\hat{\Omega}}
\left(
\bar q_x\frac{\partial \bar T}{\partial \bar x}
+ \frac{1}{l_r}\bar q_z\frac{\partial \bar T}{\partial \bar z}
\right)\bar v\,d\hat{\Omega}
-
\int_{\hat{\Omega}}
D_0
\left[
\frac{\partial}{\partial\bar x}
\left(\bar h\frac{\partial\bar T}{\partial\bar x}\right)
+\frac{1}{l_r^2}\frac{\partial}{\partial\bar z}
\left(\bar h\frac{\partial\bar T}{\partial\bar z}\right)
\right]\bar v\,d\hat{\Omega}
=
\int_{\hat{\Omega}}\bar\Phi_E\bar v\,d\hat{\Omega}
$$

对扩散项分部积分，有

$$
-
\int_{\hat{\Omega}}
D_0
\left[
\frac{\partial}{\partial\bar x}
\left(\bar h\frac{\partial\bar T}{\partial\bar x}\right)
+\frac{1}{l_r^2}\frac{\partial}{\partial\bar z}
\left(\bar h\frac{\partial\bar T}{\partial\bar z}\right)
\right]\bar v\,d\hat{\Omega}
=
\int_{\hat{\Omega}}
D_0\bar h
\left(
\frac{\partial \bar T}{\partial \bar x}
\frac{\partial \bar v}{\partial \bar x}
+ \frac{1}{l_r^2}
\frac{\partial \bar T}{\partial \bar z}
\frac{\partial \bar v}{\partial \bar z}
\right)d\hat{\Omega}
- \int_{\partial\hat{\Omega}}
D_0\bar h
\left(
\frac{\partial \bar T}{\partial \bar x}n_{\bar x}
+ \frac{1}{l_r^2}\frac{\partial \bar T}{\partial \bar z}n_{\bar z}
\right)\bar v\,d\hat{\Gamma}
$$

入口和两侧 Dirichlet 边界上 $\bar v=0$；出口若采用自然边界，则边界项取零。因此无量纲 Galerkin 弱式为：

$$
\int_{\hat{\Omega}}
\mathrm{St}_{\Omega}\,\bar h
\frac{\partial \bar T}{\partial \bar t}\bar v\,d\hat{\Omega}
+
\int_{\hat{\Omega}}
D_0\bar h
\left(
\frac{\partial \bar T}{\partial \bar x}
\frac{\partial \bar v}{\partial \bar x}
+ \frac{1}{l_r^2}
\frac{\partial \bar T}{\partial \bar z}
\frac{\partial \bar v}{\partial \bar z}
\right)d\hat{\Omega}
+
\int_{\hat{\Omega}}
\left(
\bar q_x\frac{\partial \bar T}{\partial \bar x}
+ \frac{1}{l_r}\bar q_z\frac{\partial \bar T}{\partial \bar z}
\right)\bar v\,d\hat{\Omega}
=
\int_{\hat{\Omega}}\bar\Phi_E\bar v\,d\hat{\Omega}
$$

其中扩散项中的 $1/l_r^2$ 来自轴向坐标缩放 $z=l_rR\bar z$，$D_0\bar h$
体现三维导热率按局部膜厚积分；对流项中的 $1/l_r$ 来自一阶轴向导数缩放。
若采用物理约化的纯对流温度方程，只需令 $D_0=0$；若只求稳态场，则同时去掉第一项。

用无量纲时间步长

$$
\Delta\bar t=\Omega\Delta t
$$

做隐式 Euler 离散，可得 $t_{n+1}$ 层的无量纲有限元方程：

$$
\int_{\hat{\Omega}}
\frac{\mathrm{St}_{\Omega}\,\bar h^{n+1}}{\Delta\bar t}
\bar T^{n+1}\bar v\,d\hat{\Omega}
+
\int_{\hat{\Omega}}
D_0\bar h^{n+1}
\left(
\frac{\partial \bar T^{n+1}}{\partial \bar x}
\frac{\partial \bar v}{\partial \bar x}
+ \frac{1}{l_r^2}
\frac{\partial \bar T^{n+1}}{\partial \bar z}
\frac{\partial \bar v}{\partial \bar z}
\right)d\hat{\Omega}
+
\int_{\hat{\Omega}}
\left(
\bar q_x^{n+1}\frac{\partial \bar T^{n+1}}{\partial \bar x}
+ \frac{1}{l_r}\bar q_z^{n+1}\frac{\partial \bar T^{n+1}}{\partial \bar z}
\right)\bar v\,d\hat{\Omega}
=
\int_{\hat{\Omega}}\bar\Phi_E^{n+1}\bar v\,d\hat{\Omega}
+
\int_{\hat{\Omega}}
\frac{\mathrm{St}_{\Omega}\,\bar h^{n+1}}{\Delta\bar t}
\bar T^n\bar v\,d\hat{\Omega}
$$

这个无量纲弱式与当前无量纲内核的矩阵结构一一对应：瞬态质量项对应
$\mathrm{St}_{\Omega}\bar h/\Delta\bar t$，可选物理面内导热项对应 $D_0\bar h$，
对流项对应 $\bar q_x\partial_{\bar x}\bar T + l_r^{-1}\bar q_z\partial_{\bar z}\bar T$，
右端载荷对应 $\bar\Phi_E$。

对应代码：

- 扩散 + 对流：`_nondim_advection_diffusion_form`
- 热源载荷：`_source_form`
- 系数：`rho_cv = rho * cp_lub`
- 瞬态质量项：`_transient_mass_form`
- 瞬态历史项：`_transient_rhs_form`

SUPG 项采用：

$$
K_{\text{SUPG}} = \int_\Omega \tau\,\rho c_v\,(\mathbf q\cdot\nabla v)(\mathbf q\cdot\nabla u)\,d\Omega,
\quad
f_{\text{SUPG}} = \int_\Omega \tau\,(\mathbf q\cdot\nabla v)\,\Phi\,d\Omega
$$

当前无量纲内核对应 `_nondim_supg_stiffness_form`、`_nondim_supg_load_form`。

#### 2.4.3 本次检查结论

1. `cp_lub` 与 $c_v$ 未重复建模：仅有 `cp_lub` 配置，离散中统一用 `rho_cv = rho * cp_lub`。
2. `xct`、`yct` 是按 $c\,v_f\omega$ 归一化的无量纲速度；代码 RHS 中的
   `vf * dh_dt` 恰好恢复 $\partial\bar h/\partial\bar t$，不应删除 `vf`。
3. 压力弱形式正确体现“LHS 变粘度、RHS 固定参考粘度”的修正。
4. 无量纲温度压缩式的旧版轴向对流项多写了 $1/l_r$；已按
   `qz_bar / lr` 的实际装配关系修正。
5. 非稳态直接求解通过隐式 Euler 将时间项转化为“左端附加质量矩阵 + 右端历史温度项”，
   与代码一致；SUPG 只稳定空间对流残差，不包含瞬态储热残差，这不影响其稳态对流稳定用途。
6. 点源接口已明确区分 `q_nondim` 与 `q_vol`；无量纲热核只消费 `q_nondim`，
   不再从兼容 `flow` 三元组猜测单位。

### 2.6 含粘度场的 Reynolds 方程

无量纲 Reynolds 方程中，粘度比 $\bar{\mu}_i = \mu_i / \mu_{\text{ref}}$ 主要影响扩散项：

**扩散项（刚度矩阵）**：直接采用无量纲粘度比写法

$$
\int_\Omega \frac{h^3}{\bar{\mu}}
\left(l_r^2\frac{\partial p}{\partial x}\frac{\partial v}{\partial x}
+\frac{\partial p}{\partial z}\frac{\partial v}{\partial z}\right) d\Omega
$$

因此当前启用实现直接在节点/积分点上使用

$$
\frac{h_i^3}{\bar{\mu}_i}
$$

作为扩散系数，对应 `ALB/thermal.py` 中 `_reynolds_lhs_miu` 与 `h3_over_miu` 的装配逻辑。也就是说，局部粘度升高时，扩散系数按 $1/\bar{\mu}_i$ 减小。

说明：源码中仍保留一个历史 `h_eff` 写法分支，但它不再作为设置项对外开放。若只从代数等价角度把 $h^3/\bar{\mu}$ 改写为等效膜厚，应满足

$$
h_{\text{eff},i}^3 = \frac{h_i^3}{\bar{\mu}_i}, \qquad
h_{\text{eff},i} = h_i \cdot \bar{\mu}_i^{-1/3}
$$

而不是 $h_i \cdot \bar{\mu}_i^{1/3}$。

**源项（载荷向量）**：固定参考粘度标度（$\mu_0$）

$$
\mathbf{f}_e = \mathbf{f}_e(h, v_{x0}) + \mathbf{f}_{vf}(v_{x0}, v_f, h_t)
$$

即源项不再显式乘以局部粘度比，避免 RHS 与温度迭代产生额外尺度漂移。

---

## 3 供油孔局部冷却模型

当轴承含有节流孔时，冷供油通过供油孔注入，在局部区域与热油膜混合，降低局部温度。采用**点源 FEM** 方法，将供油孔注入的冷油作为源项直接嵌入有限元方程。

### 3.1 供油孔流量

无量纲节流流量 $q_{n,i}$ 转换为有量纲体积流量：

$$
Q_i=q_{n,i}Q_w,
\qquad
Q_w=\frac{p_sc^3}{12\mu_0l_r}
$$

### 3.2 点源 FEM

将供油孔注入的冷油作为**源项直接嵌入有限元方程**，在 `spsolve` **之前**修改刚度矩阵和载荷向量。

对每个供油孔 $i$，找到距离最近的热网格节点 $j$，加入点源贡献：

$$
K_{jj} \mathrel{+}= \rho c_v \, Q_i
$$

$$
f_j \mathrel{+}= \rho c_v \, Q_i \, T_{\text{supply}}
$$

物理含义：在节点 $j$ 处注入流量 $Q_i$ 的冷油（温度 $T_{\text{supply}}$），相当于对该节点增加了一个 "对流换热" 源项，将局部温度拉向 $T_{\text{supply}}$。

公开包装器进入无量纲热内核时直接传递 $q_{n,i}$；`q_vol` 仅用于有量纲输出与兼容接口。
所有孔口共享同一个由固定参考黏度 $\mu_0$ 定义的 $Q_w$。

**特点**：

- 冷却效应仅作用于单个节点（点源），在该节点处会出现局部温度突降
- 当存在**均压槽**（tank）时，膜厚增大主要通过
  $q_x=Uh/2-h^3p_x/(12\mu)$ 与 $q_z=-h^3p_z/(12\mu)$ 改变槽内对流输运；
  其中 Couette 通量随 $h$ 变化，Poiseuille 通量随 $h^3$ 变化，同时流速变化会改变 SUPG 的
  等效流线数值扩散。即使 `k_lub > 0` 时二维物理导热系数只随 $h$ 线性增加，槽区主要变化仍来自
  对流输运，不能夸大热传导作用
- 对网格密度有一定敏感性：粗网格时节点覆盖面积大，点源影响域大；细网格时节点面积小，点源更集中
- 点源对网格敏感，不能沿用旧版“从 40×28 起基本收敛”的无条件结论；应在修复流量归一化后重新做网格收敛检查

### 3.3 能量平衡中的供油孔修正

供油孔注入的冷油增加了总质量流量，降低了整体温升：

$$
\dot{m} = \rho\,(Q_{\text{Couette}} + Q_{\text{orifice,total}})
$$

$$
\Delta T = \frac{P_{\text{fric}}}{\dot{m}\, c_p}
$$

供油孔流量越大，$\dot{m}$ 越大，$\Delta T$ 越小。

---

## 4 耦合模式

通过 `ThermalConfig.coupling` 参数选择：

| 模式 | 热源粘度输入 | 特点 |
|------|-------------|------|
| `"full"` | 逐节点粘度场 $\mu(x,z)$ | 热源 $q$ 反映局部粘度变化，耦合更精确 |
| `"half"` | 平均粘度 $\overline{\mu}$ | 热源 $q$ 使用均匀粘度，计算简单 |

两种模式下 Reynolds 方程均使用逐节点粘度场求解，差异仅在于热源计算。

---

## 5 迭代求解流程

```
若 transient_enabled = False：
    直接执行单时刻热-粘耦合迭代

若 transient_enabled = True：
    第一次调用时先求一次稳态热场，作为 T^0 初场
    后续每个时间步缓存上一时刻温度场 T^n

单时间步内：
初始化：μ_field = μ_ref（均匀）
构建热网格：mesh_data = build_mesh(model)    ← 仅调用一次

for iter = 1, 2, ..., max_iter:
    ├─ 1. 写入逐节点粘度比 miu_ratio = μ_i / μ_ref
    ├─ 2. 同步参考压力参数，保持参考粘度 μ0 对应的 lambda0 固定
    ├─ 3. 求解 Reynolds 方程 → 压力场 p(x,z)
    ├─ 4. 收集供油孔流量 Q_i（依赖压力场）
    ├─ 5. 更新压力梯度：update_pressure_gradients(model, mesh_data)
    ├─ 6. 求解温度场：
    │       a. 计算面内通量 qx, qz 和耗散源 Φ
    │       b. 组装对流-扩散 FEM 系统 K·T = f
    │       c. 若为非稳态：加入 (ρcvh/Δt)·T^{n+1} 到左端
    │       d. 若为非稳态：加入 (ρcvh/Δt)·T^n 到右端
    │       e. 添加 SUPG 稳定项（如启用）
    │       f. 供油孔点源处理：以 q_nondim 修改 K, f → spsolve → T(x,z)
    ├─ 7. 映射温度到油膜节点（预计算索引查表）
    ├─ 8. 计算目标粘度 μ_target = μ_ref·exp[-β(T - T_ref)]
    ├─ 9. 松弛更新：μ_new = (1-α)μ_old + α·μ_target
    └─ 10. 收敛判断：max|μ_new - μ_old| / max|μ_old| < tol ?

收敛后：
    ├─ 最终求解 Reynolds + 更新压力梯度 + 温度场 → 输出结果
    └─ 若为非稳态：保存当前 T^{n+1} 作为下一时刻的 T^n

未收敛时：
    └─ 抛出明确错误并保留旧的 _temperature_prev，不提交失败的初场或时间步
```

### 5.1 网格缓存与压力梯度分离

`build_mesh()` 完成以下工作并返回 `mesh_data` 字典：

1. 构建三角网格 `MeshTri` 和有限元基 `Basis`
2. 计算油膜厚度 $h$ 在热节点上的映射
3. **预计算 film ↔ thermal 映射索引**：通过共享的结构化网格 $(i_x, i_z)$ 建立双向查表
   - `film_to_thermal_idx`：油膜节点 → 最近热节点索引
   - `thermal_to_film_idx`：热节点 → 最近油膜节点索引
4. 初始计算压力梯度 $\nabla p$

**迭代内不重建网格**，仅调用 `update_pressure_gradients()` 更新压力梯度字段。

### 5.2 向量化映射

温度/粘度在两套网格间的传递利用预计算索引，实现 O(1) 查表：

```python
# 热 → 油膜（替代 O(n²) 暴力搜索）
t_film = t_nodal[mesh_data["film_to_thermal_idx"]]

# 油膜 → 热（替代 O(n²) 暴力搜索）
miu_thermal = miu_field[mesh_data["thermal_to_film_idx"]]
```

### 5.3 非稳态初场与时间推进

当 `transient_enabled = True` 时，`ThermalHydroBearing.output()` 的控制逻辑为：

1. 若尚无历史温度场，则先调用 `initialize_thermal_state()` 求一遍**稳态热场**；
2. 将该稳态温度场缓存为 `self._temperature_prev`，作为非稳态初场 $T^0$；
3. 后续每次输出时，将 `self._temperature_prev` 作为历史场传入热求解器；
4. 只有当前步收敛后，新温度场才覆盖 `self._temperature_prev`；失败时保留旧状态并抛错。

这样做的目的有两点：

- 避免从任意均匀温度直接启动非稳态计算带来的大幅初始数值跳变；
- 使周期轨迹计算更快收敛到周期稳态温度响应。

### 5.4 松弛因子

$$
\mu^{(k+1)} = (1 - \alpha)\,\mu^{(k)} + \alpha\,\mu_{\text{target}}^{(k)}
$$

$\alpha$ = `relax`（默认 0.5），避免粘度场更新过快导致振荡。

### 5.5 收敛准则

$$
\frac{\max_i |\mu_i^{(k+1)} - \mu_i^{(k)}|}{\max_i |\mu_i^{(k)}|} < \varepsilon
$$

$\varepsilon$ = `tol`（默认 $10^{-6}$）。

---

## 6 配置参数汇总

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `t_in` | 40.0 °C | 入口油温 |
| `t_ref` | `None`→`t_in` | 参考温度 |
| `miu0` | `None`→初始粘度 | 参考粘度 |
| `beta` | 0.03 1/°C | 粘温系数 |
| `k_lub` | 0.0 W/(m·K) | 润滑油三维导热率；弱式使用局部 $k_{\mathrm{lub}}h$ |
| `cp_lub` | 2000 J/(kg·K) | 原方程热容常数按不可压缩液体近似使用 $c_v\approx c_p$ |
| `flow_rate_factor` | 1.0 | deprecated/no-op；仅允许 1.0，其他值直接报错 |
| `max_delta_t` | 80 °C | 温升上限 |
| `heat_partition` | 0.9 | 热分配系数 |
| `relax` | 0.5 | 松弛因子 |
| `miu_update` | `"linear"` | 外层粘度更新方式，可选 `"linear"` 或 `"log"` |
| `miu_update_max_ratio` | `None` | 对数粘度更新时的单步粘度倍率上限 |
| `heat_partition_steps` | `None` | 热分配 continuation 序列，末项自动补齐到 `heat_partition` |
| `tol` | 1e-6 | 收敛容差 |
| `max_iter` | 60 | 最大迭代次数 |
| `miu_min` | 1e-4 Pa·s | 粘度下限 |
| `miu_max` | 1.0 Pa·s | 粘度上限 |
| `coupling` | `"full"` | 自动转为小写，仅允许 `full` 或 `half` |
| `t_supply` | `None`→`t_in` | 供油温度 |
| `supg` | `True` | 是否启用 SUPG 对流稳定化 |
| `transient_enabled` | `False` | 是否启用非稳态热容项 |
| `dt` | `None` | 非稳态时间步长，单位 s |

`transient_enabled=True` 当前只允许 `iter_method="direct"`；瞬态 Newton 尚未实现，
`newton` 与 `direct_then_newton` 组合会在配置阶段直接报错。

---

## 7 类结构

```
ThermalHydroBearing (NodimThermalHydroBearing)
├── 接收有量纲 film/config
├── _ensure_pressure_backend()
│   └── 转换为 NodimViscositySkfemNewtonFilm
└── 继承无量纲耦合与温度求解流程

NodimThermalHydroBearing (BaseCSystem)
├── bearing: HydrostaticBearing             # 压力/流量模型
├── thermal_model: SkfemThermalModelNondim  # 当前实际温度求解器
├── config: ThermalConfig
├── _collect_orifice_info()                 # 只向热核传无量纲位置和 q_nondim
└── _solve_coupled_for_method()
    ├── direct: fixed-point，支持稳态和隐式 Euler 非稳态
    ├── newton: segregated Newton，当前只支持稳态
    └── direct_then_newton: direct 未收敛后转 Newton

SkfemThermalModelNondim
├── build_mesh(model)                       # 每次耦合求解构建一次网格/映射
├── update_pressure_gradients(model, mesh_data)
└── solve(model, viscosity, mesh_data, orifice_data, temperature_prev, transient)
    ├── 无量纲对流/局部膜厚物理导热 FEM（_nondim_advection_diffusion_form）
    ├── 空间对流 SUPG（_nondim_supg_stiffness_form + _nondim_supg_load_form）
    ├── 可选隐式 Euler 质量项（_transient_mass_form + _transient_rhs_form）
    ├── 点源 K[j,j] += q_nondim
    └── Dirichlet BC + spsolve → T_bar，再恢复 T

NodimThermalHydroBearing.output()
├── initialize_thermal_state()        # 先求稳态热场，作为非稳态初场
└── output()
    ├── steady: 直接求当前热-粘耦合结果
    └── transient: 读取 T^n → 求 T^{n+1} → 仅在收敛后回写 _temperature_prev
```
