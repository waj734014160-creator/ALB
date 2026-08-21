# ALB 压力-流量-温度耦合仿真完整推导

## 文档角色

- 角色：ALB 液体油膜压力、供油流量、温度与黏度耦合的稳定公式和实现参考。
- 目的：从薄膜润滑基本方程出发，完整推导当前程序实际使用的膜厚、速度分布、面内流量、Reynolds 方程、孔口流量、油膜能量方程、无量纲形式、有限元弱式和耦合迭代。
- 允许更新：控制方程、无量纲尺度、边界条件、离散形式、求解流程、实现映射和明确的模型边界。
- 禁止更新：实时运行状态、单次 run 指标、PID、ETA、训练进度和原始日志。
- 事实来源：`ALB/physics/film/solver.py`、`ALB/physics/thermal/solver.py`、`ALB/physics/thermal/scales.py`、`ALB/physics/hydraulics/orifice.py`、`ALB/physics/bearing/solver.py`、`ALB/config/film_models.py` 和 `ALB/config/thermal_models.py`。
- 相关推导：频域热惯性、固定空化活动集以及 `K(γ)`、`C(γ)`、`G_{x_v}(γ)` 的推导见 `docs/formula/alb_harmonic_linearization.md`。

本文以当前代码为权威实现依据。连续方程、离散方程和程序近似分别说明，避免把物理模型、数值稳定项和经验后处理公式混为一体。

---

## 1. 推导范围、符号与基本假设

### 1.1 本文覆盖的仿真闭环

本文推导以下非线性计算链：

$$
(x,y,\dot x,\dot y,x_v)
\longrightarrow h
\longrightarrow (Q_i,p)
\longrightarrow (q_\theta,q_z,\Phi)
\longrightarrow T
\longrightarrow \mu(T)
\longrightarrow p
\longrightarrow F.
$$

其中，$x_v$ 表示孔口或阀控供油输入，$Q_i$ 表示第 $i$ 个孔口的体积流量，$q_\theta$ 与 $q_z$ 表示油膜厚度方向积分后的面内体积通量。两类流量的量纲不同，不能混用。

### 1.2 坐标系

采用局部圆柱展开坐标：

- $x=R\theta$：周向弧长，$\theta$ 为程序中的第一坐标；
- $z$：轴向坐标；
- $y_f\in[0,h]$：油膜厚度方向坐标；
- $R$：轴颈半径；
- $L$：轴承长度；
- $c$：名义径向间隙；
- $h(x,z,t)$：局部有量纲膜厚。

为避免与轴承中心的 $y$ 位移混淆，本文用 $y_f$ 表示跨膜坐标。

当前程序采用

$$
\bar x=\theta=\frac{x}{R},
\qquad
\bar z=\zeta=\frac{2z}{L},
\qquad
l_r=\frac{L}{2R}.
$$

默认 `lz=2` 时，$\zeta\in[-1,1]$ 对应 $z\in[-L/2,L/2]$。若 `lz` 不是 2，程序仍按 $z=(L/2)\zeta$ 映射，实际轴向计算域随 `lz` 改变。

### 1.3 流量记号和单位

| 符号 | 含义 | 单位 | 程序对应 |
| --- | --- | --- | --- |
| $q_\theta$ | 周向单位横向宽度的面内体积通量，$\int_0^h u\,dy_f$ | m$^2$/s | `qx` |
| $q_z$ | 轴向单位横向宽度的面内体积通量，$\int_0^h w\,dy_f$ | m$^2$/s | `qz` |
| $Q_i$ | 第 $i$ 个孔口进入油膜的体积流量 | m$^3$/s | `q_vol` |
| $\bar q_\theta$ | $q_\theta/Q_f$ | 1 | `qx_nondim` |
| $\bar q_z$ | $q_z/Q_f$ | 1 | `qz_nondim` |
| $q_{n,i}$ | $Q_i/Q_w$ | 1 | `q_nondim` |

热有限元装配使用的无量纲轴向对流系数是 $\bar q_z/l_r$，而输出字段 `qz_nondim` 保存的是 $\bar q_z$。这两个量必须区分。

### 1.4 当前模型假设

当前 ALB 液体油膜模型采用以下假设：

1. 润滑油不可压缩，密度 $\rho$ 在压力和温度求解中视为常数。
2. 膜厚远小于周向和轴向尺度，满足薄膜润滑近似。
3. 压力沿膜厚方向不变，即 $\partial p/\partial y_f=0$。
4. 忽略面内惯性，周向和轴向速度由黏性力与压力梯度平衡。
5. 黏度可随 $(x,z)$ 变化，但在每个局部截面的膜厚方向取同一值。
6. 温度采用跨膜平均值 $T(x,z,t)$；程序不解析 $T(y_f)$。
7. 采用 $c_p\approx c_v$ 的不可压缩液体近似；代码只配置 `cp_lub`。
8. 默认不求轴颈和瓦块实体温度，也不包含局部壁面换热项 $K_w(T-T_b)$。
9. `k_lub` 表示润滑油三维导热率；它只产生面内导热 $\nabla\cdot(k_{\mathrm{lub}}h\nabla T)$。
10. 压力空化由非负压力约束处理；温度方程没有液相体积分数或 JFO 质量守恒空化变量。

因此，本文所称“完整”是指当前 ALB 程序所实现的压力-供油流量-平均温度-黏度闭环，而不是包含固体传热、跨膜温度分布和两相空化的三维全热流体模型。

---

## 2. 油膜几何与运动学

### 2.1 膜厚

对程序的 `ex_ey` 输入方式，无量纲膜厚为

$$
\boxed{
\bar h(\theta,z,t)
=1+e_x(t)\sin\theta-e_y(t)\cos\theta
+\bar h_{\mathrm{tank}}(\theta,z),
}
$$

有量纲膜厚为

$$
h=c\bar h.
$$

`e_angle` 方式使用

$$
\bar h=1+e\cos(\theta-\alpha)+\bar h_{\mathrm{tank}}.
$$

两式是程序中的两种替代输入方式。若论文采用不同的偏心方向或三角函数约定，应先完成坐标映射，不能直接比较交叉刚度或力分量的符号。

### 2.2 挤压速度

令转子角速度为

$$
\omega=\frac{2\pi n}{60},
$$

并定义无量纲时间

$$
\tau=\omega t.
$$

由 `ex_ey` 膜厚式可得

$$
\frac{\partial\bar h}{\partial t}
=\dot e_x\sin\theta-\dot e_y\cos\theta,
$$

以及

$$
\frac{\partial\bar h}{\partial\tau}
=\frac{\dot x_c}{c\omega}\sin\theta
-\frac{\dot y_c}{c\omega}\cos\theta.
$$

程序定义

$$
xct=\frac{\dot x_c}{c\,v_f\omega},
\qquad
yct=\frac{\dot y_c}{c\,v_f\omega},
$$

因此代码中的膜厚时间导数应解释为

$$
\boxed{
\bar h_{,\tau}
=v_f(xct\sin\theta-yct\cos\theta).
}
$$

`vf` 不是可从挤压项中随意删除的重复系数；它与 `xct`、`yct` 的归一化定义共同恢复真实的 $\bar h_{,\tau}$。

---

## 3. 从薄膜动量方程推导速度分布与面内流量

### 3.1 薄膜动量方程

设轴颈表面沿正 $x$ 方向以

$$
U=\omega R
$$

运动，瓦块表面静止。忽略面内惯性后，周向和轴向动量方程为

$$
\mu\frac{\partial^2u}{\partial y_f^2}=\frac{\partial p}{\partial x},
\qquad
\mu\frac{\partial^2w}{\partial y_f^2}=\frac{\partial p}{\partial z}.
$$

边界条件取

$$
u(0)=U,
\quad
u(h)=0,
\quad
w(0)=w(h)=0.
$$

两次积分得到

$$
\boxed{
u(y_f)=U\left(1-\frac{y_f}{h}\right)
+\frac{p_{,x}}{2\mu}(y_f^2-hy_f),
}
$$

$$
\boxed{
w(y_f)=\frac{p_{,z}}{2\mu}(y_f^2-hy_f).
}
$$

第一式由 Couette 速度分量和 Poiseuille 压差分量组成；第二式只有 Poiseuille 分量。

### 3.2 厚度积分后的面内体积通量

定义

$$
q_\theta=\int_0^h u\,dy_f,
\qquad
q_z=\int_0^h w\,dy_f.
$$

代入速度分布并积分：

$$
\int_0^hU\left(1-\frac{y_f}{h}\right)dy_f=\frac{Uh}{2},
$$

$$
\int_0^h(y_f^2-hy_f)dy_f=-\frac{h^3}{6}.
$$

因此

$$
\boxed{
q_\theta=\frac{Uh}{2}-\frac{h^3}{12\mu}p_{,x},
\qquad
q_z=-\frac{h^3}{12\mu}p_{,z}.
}
$$

这两式是 Reynolds 方程和油膜能量方程共享的流量基础。它们的单位是 m$^2$/s，不是孔口体积流量 m$^3$/s。

---

## 4. 质量守恒、供油孔与 Reynolds 方程

### 4.1 含离散供油孔的质量守恒

从不可压缩连续方程出发：

$$
u_{,x}+v_{,y_f}+w_{,z}=0.
$$

对 $y_f\in[0,h]$ 积分，并对含移动上边界的积分使用 Leibniz 公式；再代入两侧壁面的不可穿透/运动学条件，可得

$$
\frac{\partial h}{\partial t}
+\frac{\partial}{\partial x}\int_0^h u\,dy_f
+\frac{\partial}{\partial z}\int_0^h w\,dy_f=0.
$$

因此，$h_{,t}$ 不是附加经验项，而是由移动油膜边界引入的局部体积储存项。加入离散孔口后，右端再增加点体积源。

以流入油膜为正，设第 $i$ 个孔口位于 $(x_i,z_i)$，体积流量为 $Q_i$。二维质量守恒为

$$
\boxed{
h_{,t}+q_{\theta,x}+q_{z,z}
=\sum_iQ_i\,\delta(x-x_i)\delta(z-z_i).
}
$$

将第 3.2 节的通量代入，得到有量纲 Reynolds 方程

$$
\boxed{
\frac{\partial}{\partial x}
\left(\frac{h^3}{\mu}p_{,x}\right)
+\frac{\partial}{\partial z}
\left(\frac{h^3}{\mu}p_{,z}\right)
=6U h_{,x}+12h_{,t}
-12\sum_iQ_i\delta_i.
}
$$

正供油流量在压力扩散方程右端以负号出现，是因为它已经在原始连续方程中作为正质量源。有限元分部积分后，该流量会以正节点载荷加入压力方程，见第 4.5 节。

### 4.2 压力与流量尺度

定义

$$
\bar p=\frac{p}{p_s},
\qquad
\bar h=\frac{h}{c},
\qquad
\bar\mu=\frac{\mu}{\mu_0},
\qquad
a=\frac{\bar h^3}{\bar\mu}.
$$

参考 Reynolds 轴承数为

$$
\boxed{
\lambda_0
=\frac{3\mu_0\omega L^2}{2p_sc^2}
=\frac{6\mu_0\omega l_r^2R^2}{p_sc^2}.
}
$$

面内通量尺度和孔口体积流量尺度分别为

$$
\boxed{
Q_f=\frac{p_sc^3}{12\mu_0l_r^2R}
\quad[\mathrm{m^2/s}],
}
$$

$$
\boxed{
Q_w=Q_fl_rR
=\frac{p_sc^3}{12\mu_0l_r}
\quad[\mathrm{m^3/s}].
}
$$

于是

$$
\bar q_\theta=\frac{q_\theta}{Q_f},
\qquad
\bar q_z=\frac{q_z}{Q_f},
\qquad
q_{n,i}=\frac{Q_i}{Q_w}.
$$

### 4.3 无量纲 Reynolds 方程

利用

$$
x=R\theta,
\qquad
z=l_rR\zeta,
\qquad
t=\frac{\tau}{\omega},
$$

有量纲方程化为

$$
\boxed{
l_r^2\frac{\partial}{\partial\theta}
\left(a\bar p_{,\theta}\right)
+\frac{\partial}{\partial\zeta}
\left(a\bar p_{,\zeta}\right)
=\lambda_0\bar h_{,\theta}
+2\lambda_0\bar h_{,\tau}
-\sum_iq_{n,i}\hat\delta_i.
}
$$

其中 $\hat\delta_i$ 满足

$$
\int_{\hat\Omega}\hat\delta_i\,d\theta d\zeta=1.
$$

当前热耦合实现固定 $\lambda_0$，局部温度只通过 $a=\bar h^3/\bar\mu$ 修改左端 Poiseuille 流动能力；不会用局部平均黏度反复重定义 $\lambda_0$。

### 4.4 无量纲面内通量与质量守恒复核

由第 3.2 节直接得到

$$
\boxed{
\bar q_\theta
=\lambda_0\bar h
-l_r^2a\bar p_{,\theta},
}
$$

$$
\boxed{
\bar q_z
=-l_ra\bar p_{,\zeta}.
}
$$

在无量纲坐标中，轴向散度和热对流使用 $\bar q_z/l_r$。对由有量纲参数一致生成的模型，定义

$$
\mathrm{St}_\omega
=\frac{c\omega R}{Q_f},
$$

则恒有

$$
\boxed{\mathrm{St}_\omega=2\lambda_0.}
$$

无量纲质量守恒可写成

$$
\boxed{
2\lambda_0\bar h_{,\tau}
+\bar q_{\theta,\theta}
+\frac{1}{l_r}\bar q_{z,\zeta}
=\sum_iq_{n,i}\hat\delta_i.
}
$$

把两条通量式代入上式，可逐项恢复第 4.3 节的 Reynolds 方程。这是压力方程、流量式和时间尺度之间最直接的闭环检查。

对直接构造的无量纲模型，程序允许 `lambda0` 与附带的物理参考尺度分别输入；若两者并非来自同一组有量纲参数，则不应额外假定 $\mathrm{St}_\omega=2\lambda_0$。

### 4.5 压力有限元弱式

全液膜区域内取测试函数 $v$。将 Reynolds 方程的扩散项分部积分并忽略已由边界条件处理的边界项，得到

$$
\boxed{
\int_{\hat\Omega}a
\left(
l_r^2\bar p_{,\theta}v_{,\theta}
+\bar p_{,\zeta}v_{,\zeta}
\right)d\hat\Omega
=\int_{\hat\Omega}
\left(-\lambda_0\bar h_{,\theta}
-2\lambda_0\bar h_{,\tau}\right)v,d\hat\Omega
+\sum_iq_{n,i}v(\theta_i,\zeta_i).
}
$$

令共有 $n_h$ 个供油孔、$n_p$ 个压力自由度，并定义孔到压力自由度的投影矩阵

$$
W\in\mathbb R^{n_h\times n_p}.
$$

对 `flow_projection="nearest_node"`，每行只有最近节点上的一个单位权重；对
`flow_projection="element_shape"`，第 $a$ 个孔所在单元的原生形函数给出
$W_{aj}=N_j(\theta_a,\zeta_a)$。因此 Q1、P1、P2、Q2 分别使用 4、3、6、9 个
局部自由度，不把高阶单元退化为四角节点。实现要求每行权重有限且
$\sum_jW_{aj}=1$；P2/Q2 的局部权重允许为负。

孔位压力向量为

$$
\boxed{p_h=Wp,}
$$

孔口流量对压力方程的节点载荷为

$$
\boxed{f_Q=W^\mathsf Tq(p_h,x_v).}
$$

对第 $a$ 个孔，上式展开为

$$
(p_h)_a=\sum_jW_{aj}p_j,
$$

离散系统为

$$
K_p(\bar\mu,\bar h)p
=f_h(\bar h,\bar h_{,\tau})+W^\mathsf Tq(Wp,x_v).
$$

矩阵和基础载荷分别为

$$
(K_p)_{ij}
=\int_{\hat\Omega}a
\left(l_r^2N_{j,\theta}N_{i,\theta}
+N_{j,\zeta}N_{i,\zeta}\right)d\hat\Omega,
$$

$$
(f_h)_i
=\int_{\hat\Omega}
\left(-\lambda_0\bar h_{,\theta}
-2\lambda_0\bar h_{,\tau}\right)N_i,d\hat\Omega.
$$

孔口流量依赖局部压力时，压力残差为

$$
R_p(p)=K_pp-f_h-W^\mathsf Tq(Wp,x_v),
$$

其 Newton 切线为

$$
\boxed{
J_p=K_p-W^\mathsf T
\frac{\partial q}{\partial p_h}W.
}
$$

代码把 $W^\mathsf Tq$ 加入右端。若以
$J_q=-\partial q/\partial p_h$ 表示求解器按残差符号返回的流量切线，则矩阵更新
写成 $K\mathrel{+}=W^\mathsf TJ_qW$。最近节点模式仍使用原有逐孔装配顺序，
所以缺省配置保持逐元素精确回归。

### 4.6 普通孔口与主动毛细管-缝隙节流器

#### 普通孔口

普通孔口采用平方根压差关系：

$$
\bar Q_i
=c_q|x_v|\operatorname{sign}(\bar p_s-\bar p_i)
\sqrt{|\bar p_s-\bar p_i|}.
$$

若参考压力就是 $p_s$，孔口面积为 $A_0$，则

$$
c_q
=\frac{C_dA_0\sqrt{2p_s/\rho}}{Q_w}
=\frac{12\mu_0l_rC_dA_0}{c^3}
\sqrt{\frac{2}{\rho p_s}}.
$$

#### `CSOrifice`

当前主动毛细管-缝隙节流器先求公共阀腔压力 $\bar p_{sv}$，再求各供油节点流量。零泄漏的活动方程为

$$
\boxed{
\bar q_s=\sum_{i=1}^{m}\bar q_i,
}
$$

$$
\boxed{
\bar q_s
=\operatorname{sign}(\bar p_s-\bar p_{sv})
c_{q0}|x_v|\sqrt{|\bar p_s-\bar p_{sv}|},
}
$$

$$
\boxed{
\frac{c_{q1}}{\bar h_i^2}\bar q_i|\bar q_i|
+c_{q2}\bar q_i
=\bar p_{sv}-\bar p_i.
}
$$

当前实现要求 `q_leak=0`；非零泄漏不是活动模型的一部分。$x_v\ge0$ 时选择高压端，$x_v<0$ 时选择回油端，求解中使用 $|x_v|$。$\bar q_i>0$ 表示向油膜注油，$\bar q_i<0$ 表示从油膜抽油。

有量纲 `CSOrifice` 将几何系数转换为上述无量纲系数：

$$
c_{q0}
=\frac{C_dw\sqrt{2/\rho}\sqrt{p_s}}{Q_w},
$$

$$
c_{q1}
=\frac{\rho}{5(\pi cd)^2}\frac{Q_w^2}{p_s},
\qquad
c_{q2}
=\frac{128\mu_0l_p}{\pi d^4}\frac{Q_w}{p_s}.
$$

这里 $d$、$l_p$、$w$ 分别对应当前 `CsoArgs` 的孔径、管长和有效阀口宽度参数。节点方程中的二次阻力再除以局部 $\bar h_i^2$。

### 4.7 压力边界与空化

程序支持三类压力处理：

1. `reynold=True`：用 Fischer-Burmeister 方程求非负压力互补问题。
2. `reynold="half_reynold"`：线性修正后截断负压力，是数值近似，不是质量守恒 JFO 空化模型。
3. `reynold=False`：允许出现有符号压力。

为与代码矩阵残差一致，定义

$$
\mathcal R_p
=-l_r^2\partial_\theta(a\bar p_{,\theta})
-\partial_\zeta(a\bar p_{,\zeta})
+\lambda_0\bar h_{,\theta}
+2\lambda_0\bar h_{,\tau}
-\sum_iq_{n,i}\hat\delta_i.
$$

`reynold=True` 对应

$$
\boxed{
\bar p\ge0,
\qquad
\mathcal R_p\ge0,
\qquad
\bar p\,\mathcal R_p=0.
}
$$

若反过来把等式左端定义为残差，则互补不等号也必须反向；不能只改变残差符号而保留同一不等号。

轴向端部通常施加环境压力。周向边界由 `coe` 选择周期连续或固定环境压力；非周期瓦块通常在两条周向边界施加环境压力。

---

## 5. 载荷、摩擦与总流量守恒

### 5.1 油膜力

程序的无量纲单瓦力为

$$
\boxed{
\bar F_x=\int_{\hat\Omega}\bar p\sin\theta,d\theta d\zeta,
\qquad
\bar F_y=-\int_{\hat\Omega}\bar p\cos\theta,d\theta d\zeta.
}
$$

有量纲力尺度为

$$
F_0=p_sR\frac{L}{2},
$$

所以

$$
F_x=F_0\bar F_x,
\qquad
F_y=F_0\bar F_y.
$$

多瓦轴承的总力为各瓦块全局坐标力之和：

$$
\mathbf F_{\mathrm{bearing}}=\sum_k\mathbf F_k.
$$

### 5.2 摩擦

由第 3.1 节速度分布，作用在运动表面的切向阻力幅值可写为

$$
\tau_f=\frac{\mu U}{h}+\frac{h}{2}p_{,x}.
$$

程序按单元积分得到摩擦力，并在空化单元对 Couette 项使用专门的回退膜厚。该摩擦后处理与温度方程中的全液膜耗散模型并不完全相同，尤其不能用摩擦后处理的空化回退直接替代第 6.3 节的热源。

### 5.3 边界流量和整体质量平衡

任意油膜域 $\Omega$ 的总体积为

$$
V_f(t)=\int_\Omega h\,dA.
$$

对质量守恒积分：

$$
\boxed{
\frac{dV_f}{dt}
+\int_{\partial\Omega}\mathbf q\cdot\mathbf n,ds
=\sum_iQ_i.
}
$$

稳态时，边界净流出量等于孔口净注入量。当前结果字段 `q_orifice_total_vol` 是孔口流量绝对值之和，`q_orifice_net_vol` 才是带符号净孔口流量；二者都不是完整的边界泄漏量。旧式

$$
\dot m=\rho(Q_{\mathrm{Couette}}+Q_{\mathrm{orifice}})
$$

没有定义控制面，也不是当前 PDE 求解器使用的总流量关系，不应作为能量方程的起点。

---

## 6. 含流量的油膜能量方程：从三维式到二维式

### 6.1 三维能量方程

对不可压缩 Newton 流体，忽略压力功、体热源和材料热物性随温度的变化，三维温度方程为

$$
\rho c_p
\left(
T_{,t}+uT_{,x}+vT_{,y_f}+wT_{,z}
\right)
=k_{\mathrm{lub}}\nabla^2T+\phi_v.
$$

当前程序进一步采用跨膜平均温度假设

$$
T=T(x,z,t),
\qquad
T_{,y_f}=0.
$$

将三维式沿 $y_f\in[0,h]$ 积分，并忽略上下壁面的净导热通量，面内导热项变为

$$
\nabla_{xz}\cdot(k_{\mathrm{lub}}h\nabla_{xz}T).
$$

因此 `k_lub` 的单位仍为 W/(m·K)，厚度积分后的二维系数是 $k_{\mathrm{lub}}h$，单位为 W/K。

### 6.2 保守形式与孔口焓流

仅写 $q_\theta T_{,x}+q_zT_{,z}$ 还不能解释供油孔冷却。必须先写含质量源的保守焓平衡。

定义

$$
Q_i^+=\max(Q_i,0),
\qquad
Q_i^-=\min(Q_i,0).
$$

正流量带入外部供油温度 $T_{s,i}$；负流量从油膜抽出，其流出温度就是局部油温 $T_i$。保守形式为

$$
\begin{aligned}
\rho c_p\left[
\frac{\partial(hT)}{\partial t}
+\frac{\partial(q_\theta T)}{\partial x}
+\frac{\partial(q_zT)}{\partial z}
\right]
={}&\nabla_{xz}\cdot(k_{\mathrm{lub}}h\nabla_{xz}T)+\Phi\\
&+\rho c_p\sum_i
\left(Q_i^+T_{s,i}+Q_i^-T_i\right)\delta_i.
\end{aligned}
$$

展开左端：

$$
\frac{\partial(hT)}{\partial t}
+\nabla\cdot(\mathbf qT)
=hT_{,t}+\mathbf q\cdot\nabla T
+T(h_{,t}+\nabla\cdot\mathbf q).
$$

再用质量守恒

$$
h_{,t}+\nabla\cdot\mathbf q
=\sum_i(Q_i^++Q_i^-)\delta_i,
$$

可得

$$
\boxed{
\rho c_p
\left[
hT_{,t}+q_\theta T_{,x}+q_zT_{,z}
\right]
=\nabla_{xz}\cdot(k_{\mathrm{lub}}h\nabla_{xz}T)
+\Phi
+\rho c_p\sum_iQ_i^+(T_{s,i}-T_i)\delta_i.
}
$$

这就是当前程序对应的“含流量油膜能量方程”。它同时说明：

1. 正向注油产生局部混合冷源 $Q_i^+(T_s-T)$；
2. 负向抽油不需要额外温度源项，因为抽出的油已经按局部温度携带焓离开；
3. 代码只对 `q_nondim > 0` 的孔口装配热源是守恒形式展开后的结果，而不是遗漏负流量项。

### 6.3 黏性耗散热源

跨膜黏性耗散为

$$
\Phi_d
=\int_0^h\mu
\left[
\left(\frac{\partial u}{\partial y_f}\right)^2
+\left(\frac{\partial w}{\partial y_f}\right)^2
\right]dy_f.
$$

由第 3.1 节

$$
u_{,y_f}
=-\frac{U}{h}
+\frac{p_{,x}}{\mu}\left(y_f-\frac h2\right),
$$

$$
w_{,y_f}
=\frac{p_{,z}}{\mu}\left(y_f-\frac h2\right).
$$

由于

$$
\int_0^h\left(y_f-\frac h2\right)dy_f=0,
\qquad
\int_0^h\left(y_f-\frac h2\right)^2dy_f=\frac{h^3}{12},
$$

Couette 与压力梯度交叉项消失，得到

$$
\boxed{
\Phi_d
=\frac{\mu U^2}{h}
+\frac{h^3}{12\mu}
\left(p_{,x}^2+p_{,z}^2\right).
}
$$

程序用 `heat_partition = α_h` 表示进入润滑油平均温度方程的耗散比例：

$$
\boxed{
\Phi=\alpha_h\Phi_d.
}
$$

第一项为 Couette 剪切生热，第二项为 Poiseuille 压差耗散。$\Phi$ 的单位为 W/m$^2$。当前配置默认 $\alpha_h=0.9$；剩余耗散热并未进入程序求解的油膜平均温度方程。

### 6.4 各项量纲

| 项 | 单位 |
| --- | --- |
| $\rho c_phT_{,t}$ | W/m$^2$ |
| $\rho c_pq_\theta T_{,x}$、$\rho c_pq_zT_{,z}$ | W/m$^2$ |
| $\nabla\cdot(k_{\mathrm{lub}}h\nabla T)$ | W/m$^2$ |
| $\Phi$ | W/m$^2$ |
| $\rho c_pQ_i(T_s-T)\delta_i$ | W/m$^2$ |

### 6.5 当前代码没有实现的热项

若论文希望描述油膜向轴颈或瓦块的局部换热，应另加例如

$$
-K_w(T-T_b)
$$

或与固体温度方程耦合。该项是零阶反应项，均匀温度场下仍可传热；它与

$$
\nabla\cdot(k_{\mathrm{lub}}h\nabla T)
$$

这种面内 Fourier 导热不是同一个算子。当前 `ThermalConfig` 没有 $K_w$ 或 $T_b$，因此不能把 `k_lub` 解释为壁面换热系数。

---

## 7. 温度-黏度关系

当前程序采用指数黏温关系

$$
\boxed{
\mu(T)=\mu_0
\exp[-\beta(T-T_{\mathrm{ref}})].
}
$$

数值上再裁剪到

$$
\mu_{\min}\le\mu\le\mu_{\max}.
$$

温度无量纲化为

$$
\bar T=\frac{T-T_s}{\Delta T},
\qquad
\beta_*=\beta\Delta T,
\qquad
\bar T_{\mathrm{ref}}
=\frac{T_{\mathrm{ref}}-T_s}{\Delta T}.
$$

因此

$$
\boxed{
\bar\mu
=\frac{\mu}{\mu_0}
=\exp[-\beta_*(\bar T-\bar T_{\mathrm{ref}})].
}
$$

当前温度尺度为

$$
\Delta T=
\begin{cases}
\texttt{delta\_t\_scale}, & \text{显式配置时},\\
\alpha_hp_s/(\rho c_p), & \text{否则}.
\end{cases}
$$

---

## 8. 油膜能量方程的无量纲化

### 8.1 无量纲系数

定义

$$
\Theta_E
=\frac{\alpha_hp_s}{\rho c_p\Delta T},
$$

$$
D_0
=\frac{k_{\mathrm{lub}}c}{\rho c_pQ_fR},
$$

$$
\mathrm{St}_\omega
=\frac{c\omega R}{Q_f}.
$$

默认温度尺度下 $\Theta_E=1$。局部二维无量纲导热系数为

$$
D_\theta=D_0\bar h,
\qquad
D_\zeta=\frac{D_0\bar h}{l_r^2}.
$$

### 8.2 无量纲耗散热源

定义

$$
\bar\Phi
=\frac{R\Phi}{\rho c_pQ_f\Delta T}.
$$

将 $U=\omega R$、$p=p_s\bar p$、$h=c\bar h$ 和 $\mu=\mu_0\bar\mu$ 代入第 6.3 节，得到

$$
\boxed{
\bar\Phi
=\Theta_E
\left[
\frac{\lambda_0^2}{3l_r^2}
\frac{\bar\mu}{\bar h}
+\frac{\bar h^3}{\bar\mu}
\left(
l_r^2\bar p_{,\theta}^2
+\bar p_{,\zeta}^2
\right)
\right].
}
$$

### 8.3 强形式

以 $\bar T_s=0$ 为默认供油温度，无量纲能量方程为

$$
\boxed{
\begin{aligned}
\mathrm{St}_\omega\bar h\bar T_{,\tau}
&+\bar q_\theta\bar T_{,\theta}
+\frac{\bar q_z}{l_r}\bar T_{,\zeta}\\
&=D_0\left[
\partial_\theta(\bar h\bar T_{,\theta})
+\frac{1}{l_r^2}
\partial_\zeta(\bar h\bar T_{,\zeta})
\right]
+\bar\Phi
+\sum_iq_{n,i}^+
(\bar T_{s,i}-\bar T_i)\hat\delta_i.
\end{aligned}
}
$$

代入面内通量后，对流部分可压缩为

$$
\left(
\lambda_0\bar h
-l_r^2\frac{\bar h^3}{\bar\mu}\bar p_{,\theta}
\right)\bar T_{,\theta}
-\frac{\bar h^3}{\bar\mu}\bar p_{,\zeta}\bar T_{,\zeta}.
$$

第二项没有额外 $1/l_r$，因为 $\bar q_z$ 本身已经含有一个 $l_r$。

当前默认 `k_lub=0`，即 $D_0=0$。此时物理方程是对流-耗散-注油混合方程；SUPG 仍会提供数值流线稳定，但不能把 SUPG 解释为物理导热。

---

## 9. 温度有限元弱式与离散

### 9.1 Galerkin 弱式

将面内导热移到左端，取测试函数 $v$，得到

$$
\begin{aligned}
&\int_{\hat\Omega}
\mathrm{St}_\omega\bar h\bar T_{,\tau}v,d\hat\Omega\\
&+\int_{\hat\Omega}D_0\bar h
\left(
\bar T_{,\theta}v_{,\theta}
+\frac{1}{l_r^2}\bar T_{,\zeta}v_{,\zeta}
\right)d\hat\Omega\\
&+\int_{\hat\Omega}
\left(
\bar q_\theta\bar T_{,\theta}
+\frac{\bar q_z}{l_r}\bar T_{,\zeta}
\right)v,d\hat\Omega\\
&+\sum_iq_{n,i}^+\bar T_i v_i\\
&=\int_{\hat\Omega}\bar\Phi v,d\hat\Omega
+\sum_iq_{n,i}^+\bar T_{s,i}v_i.
\end{aligned}
$$

令

$$
\bar T_h=\sum_jT_jN_j,
$$

则稳态离散系统为

$$
\boxed{
(K_D+K_A+K_Q+K_{\mathrm{SUPG}})T
=f_\Phi+f_Q+f_{\mathrm{SUPG}}.
}
$$

各矩阵为

$$
(K_D)_{ij}
=\int D_0\bar h
\left(N_{j,\theta}N_{i,\theta}
+l_r^{-2}N_{j,\zeta}N_{i,\zeta}\right)d\hat\Omega,
$$

$$
(K_A)_{ij}
=\int
\left(\bar q_\theta N_{j,\theta}
+\frac{\bar q_z}{l_r}N_{j,\zeta}\right)N_i,d\hat\Omega,
$$

对第 $a$ 个正向供油孔，令 $W_T$ 是同一投影模式在温度有限元空间中的权重，
则热混合项装配为

$$
\boxed{
(K_Q)_{ij}\mathrel{+}=q_{n,a}^+(W_T)_{ai}(W_T)_{aj},
\qquad
(f_Q)_i\mathrel{+}=q_{n,a}^+\bar T_{s,a}(W_T)_{ai}.
}
$$

最近节点模式的 $W_T$ 是单个单位权重；单元形函数模式在孔口真实坐标处使用
温度空间的 P1/P2/Q1/Q2 形函数。由于每行权重和为 1，矩阵元素总和为
$q_{n,a}^+$，载荷总和为 $q_{n,a}^+\bar T_{s,a}$，分别守恒质量混合系数和供油焓。
两种方式都表示集中点源，不是有限面积内均匀分布的供油源。

### 9.2 SUPG 稳定化

无量纲对流向量定义为

$$
\mathbf q_c
=\left(\bar q_\theta,\frac{\bar q_z}{l_r}\right).
$$

当前代码采用的空间残差为

$$
r_s=\mathbf q_c\cdot\nabla\bar T-\bar\Phi,
$$

并增加

$$
\boxed{
R_{\mathrm{SUPG}}(v)
=\int_{\hat\Omega}
\tau(\mathbf q_c\cdot\nabla v)
(\mathbf q_c\cdot\nabla\bar T-\bar\Phi)
d\hat\Omega.
}
$$

程序中的稳定参数为

$$
\mathrm{Pe}_h
=\frac{|\mathbf q_c|h_e}{2\alpha_e},
\qquad
\xi(\mathrm{Pe})=\coth(\mathrm{Pe})-\frac1{\mathrm{Pe}},
$$

$$
\tau
=\xi(\mathrm{Pe}_h)
\frac{h_e}{2|\mathbf q_c|}.
$$

其中 $\alpha_e$ 由 $D_\theta$、$D_\zeta$ 的较大值构造。对于显式统一结构网格，
程序按实际热网格坐标跨度、宏观单元数和单元阶次 $p$ 计算

$$
h_\theta=\frac{\theta_{\max}-\theta_{\min}}{n_\theta p},
\qquad
h_\zeta=\frac{\zeta_{\max}-\zeta_{\min}}{n_\zeta p},
\qquad
\boxed{h_e=\sqrt{h_\theta^2+h_\zeta^2}}.
$$

该定义恢复了原坐标间距算法对均匀 P1/P2/Q1/Q2 网格的名义尺度，同时避免
Q2 中几何重合的高阶自由度因浮点尾数被误判为 $10^{-16}$ 量级的网格间距。
未显式声明网格类型和阶次的旧路径仍沿用坐标唯一值之间的最小间距，以保持旧配置
结果不变。这里的 $h_e$ 是当前结构网格实现使用的对角尺度，不是随局部流向变化的
通用单元尺度，因此本修补的适用范围仍是当前均匀结构网格。

当前 SUPG 残差不包含瞬态储热、孔口点源和扩散强残差；默认 $D_0=0$ 时，
它主要用于稳定纯对流项。

### 9.3 隐式 Euler 时间离散

程序的 `dt` 使用秒。令

$$
\Delta\tau=\omega\Delta t,
$$

则

$$
\bar T_{,\tau}^{n+1}
\approx
\frac{\bar T^{n+1}-\bar T^n}{\Delta\tau}.
$$

瞬态质量矩阵为

$$
(M_T)_{ij}
=\int_{\hat\Omega}
\frac{\mathrm{St}_\omega\bar h^{n+1}}{\Delta\tau}
N_jN_i,d\hat\Omega.
$$

由于

$$
\frac{\mathrm{St}_\omega}{\Delta\tau}
=\frac{cR}{Q_f\Delta t},
$$

它与代码中的

$$
\frac{\bar h cR}{Q_f\Delta t}
$$

完全相同。最终时间步方程为

$$
\boxed{
(K_D+K_A+K_Q+K_{\mathrm{SUPG}}+M_T)T^{n+1}
=f_\Phi+f_Q+f_{\mathrm{SUPG}}+M_TT^n.
}
$$

---

## 10. 热边界条件

当前无量纲热核施加：

1. 周向计算域入口 $\theta=\theta_{\min}$：$\bar T=0$，即 $T=T_s$。
2. 轴向侧边界由 `axial_side_bc` 控制：
   - `fixed`：两侧固定为 `axial_side_t`，默认等于 $T_s$；
   - `adiabatic`：不施加温度 Dirichlet 条件，保留自然导热边界；
   - `inflow_fixed`：根据该侧平均轴向对流方向，只在流入侧固定温度。
3. 周向出口：不施加温度 Dirichlet 条件；导热采用自然边界，对流将能量带出。

`inflow_fixed` 依据整条侧边界的平均流向判断，不是逐节点流入边界判定。周向入口则始终固定在 $\theta_{\min}$，即使局部 $\bar q_\theta$ 反向也不会自动交换入口和出口。

当前热核对所有正向孔口使用同一个全局供油温度 $T_s$，尚不支持每个孔口独立的 $T_{s,i}$。线性系统求解后还会施加数值保护

$$
T_s-5\ \mathrm{K}\le T\le T_s+\texttt{max\_delta\_t},
$$

该裁剪是求解器保护，不是能量守恒方程的物理边界条件。

---

## 11. 压力-流量-温度-黏度耦合算法

### 11.1 当前默认直接迭代

对一个给定时刻，第 $k$ 次外迭代为：

1. 初始化或读取节点黏度场 $\mu^{(k)}$。
2. 写入

   $$
   \bar\mu_i^{(k)}=\mu_i^{(k)}/\mu_0.
   $$

3. 固定参考 $\lambda_0$ 与 $\mu_0$，求解压力-孔口耦合方程，得到 $p^{(k)}$ 和 $Q_i^{(k)}$。
4. 在结构化节点网格上用数值梯度计算 $\bar p_{,\theta}$、$\bar p_{,\zeta}$。
5. 用第 4.4 节和第 8.2 节计算 $\bar q_\theta^{(k)}$、$\bar q_z^{(k)}$、$\bar\Phi^{(k)}$。
6. 组装并求解温度有限元方程，得到 $T^{(k)}$。
7. 由黏温关系得到目标黏度

   $$
   \mu_{\mathrm{target}}^{(k)}
   =\mu_0\exp[-\beta(T^{(k)}-T_{\mathrm{ref}})].
   $$

8. 线性松弛更新

   $$
   \mu^{(k+1)}
   =(1-\alpha)\mu^{(k)}
   +\alpha\mu_{\mathrm{target}}^{(k)},
   $$

   或按 `miu_update="log"` 在对数黏度空间更新。
9. 检查

   $$
   \varepsilon_\mu^{(k)}
   =\frac{\max_i|\mu_i^{(k+1)}-\mu_i^{(k)}|}
   {\max_i|\mu_i^{(k)}|}
   <\texttt{tol}.
   $$

10. 收敛后用最终黏度场再执行一次压力求解和一次温度求解，形成输出。

### 11.2 `full` 与 `half` 耦合

两种模式下，压力方程始终使用节点局部黏度场。差别发生在温度子问题：

$$
\mu_T^{(k)}=
\begin{cases}
\mu^{(k)}(\theta,\zeta), & \texttt{full},\\
\operatorname{mean}(\mu^{(k)}), & \texttt{half}.
\end{cases}
$$

因此 `half` 不仅改变耗散热源，也同时改变温度方程中的 Poiseuille 通量 $\bar q_\theta$、$\bar q_z$。把两者差异描述为“只影响热源”是不准确的。

### 11.3 瞬态状态提交

`transient_enabled=True` 时：

1. 第一次求解先计算稳态温度场作为 $T^0$；
2. 后续每个物理时间步读取缓存的 $T^n$；
3. 只有当前压力-温度-黏度迭代收敛后，才把 $T^{n+1}$ 写回缓存；
4. 失败时保留旧状态。

当前瞬态热求解只允许 `iter_method="direct"`。

### 11.4 显式热 Newton 路径的边界

`iter_method="newton"` 在固定压力场下对 $\mu(T)$、$q(T)$ 和 $\Phi(T)$ 形成温度残差切线，但当前实现：

1. 冻结 SUPG 的 $\tau$；
2. 只加入普通 Galerkin 对流与热源的系数导数；
3. 未加入 SUPG 残差中 $q(T)$ 和 $\Phi(T)$ 的完整导数；
4. 不支持瞬态温度项。

因此该路径应称为分离式准 Newton，而不是完整单体 Newton。默认 `direct` 路径不使用这套不完整切线。

---

## 12. 当前程序的离散和实现映射

| 公式模块 | 当前实现位置 | 实现要点 |
| --- | --- | --- |
| 膜厚与挤压速度 | `ALB/physics/film/solver.py:1156-1268`、`1805-1865` | `ex_ey`/`e_angle` 膜厚；`xct`,`yct`,`vf` 映射 |
| 压力尺度 | `ALB/physics/thermal/scales.py:20-136` | $l_r$、$\lambda_0$、有量纲速度到无量纲速度 |
| 变黏度 Reynolds 弱式 | `ALB/physics/thermal/solver.py:235-343` | $\bar h^3/\bar\mu$ 进入左端，$\lambda_0$ 固定在右端 |
| 压力空化互补 | `ALB/physics/film/solver.py:688-811` | Fischer-Burmeister 或截断路径 |
| 压力边界 | `ALB/physics/film/solver.py:1928-2065` | 轴向环境压力、周向周期或固定压力 |
| 普通孔口 | `ALB/physics/hydraulics/orifice.py:96-336` | 平方根压差流量及压力导数 |
| 主动 `CSOrifice` | `ALB/physics/hydraulics/orifice.py:339-977` | 阀腔标量根求解、支路流量、压力 Jacobian |
| 热尺度 | `ALB/physics/thermal/scales.py:145-285` | $\Delta T$、$Q_f$、$Q_w$、$\Theta_E$、$\beta_*$ |
| 有量纲流量与耗散核对 | `ALB/physics/thermal/solver.py:519-565` | $q_\theta$、$q_z$、$\Phi$、$k_{\mathrm{lub}}h$ |
| 无量纲温度方程 | `ALB/physics/thermal/solver.py:1189-1401`、`1680-1845` | 对流、导热、SUPG、隐式 Euler、正流量点源 |
| 热-压-黏度外迭代 | `ALB/physics/thermal/solver.py:2644-3126` | `direct`、准 Newton、continuation、最终复算 |
| 油膜力与摩擦 | `ALB/physics/film/solver.py:1406-1598` | 压力积分、力尺度、空化感知摩擦后处理 |
| 多瓦合力 | `ALB/physics/bearing/solver.py:941-1222` | 子瓦力和摩擦直接求和 |

当前有量纲 `ThermalHydroBearing` 会把压力后端转换为无量纲变黏度求解器；有量纲和无量纲公共入口最终共享 `SkfemThermalModelNondim`。保留的 `SkfemThermalModel` 主要用于独立有量纲核对，不是公开热轴承包装器的另一套活动内核。

---

## 13. 旧推导中的主要问题与本版修正

| 旧推导风险 | 本版处理 |
| --- | --- |
| 直接从二维温度方程开始，缺少速度分布和流量来源 | 从薄膜动量方程推导 $u,w,q_\theta,q_z$ |
| 混用面内通量 $q$ 和孔口体积流量 $Q$ | 明确 $Q_f$ 与 $Q_w$ 两套尺度和单位 |
| 孔口冷却只作为经验点源给出 | 从保守焓方程和质量守恒严格推出 $Q_i^+(T_s-T)$ |
| 用 $Q_{\mathrm{Couette}}+Q_{\mathrm{orifice}}$ 写整体温升 | 改为控制体边界流量守恒；该经验式不再作为 PDE 推导 |
| `full`/`half` 被描述为只改变热源 | 明确它同时改变温度方程的通量和耗散 |
| 两侧温度边界被无条件写成固定温度 | 按 `fixed`、`adiabatic`、`inflow_fixed` 三种活动配置说明 |
| $\bar q_z$ 与热装配中的轴向对流系数混为同一符号 | 区分 $\bar q_z$ 和 $\bar q_z/l_r$ |
| 空化残差改符号后仍沿用原互补不等号 | 用矩阵残差方向定义 $\mathcal R_p\ge0$ |
| 把面内导热与壁面局部换热混为同一物理项 | 明确 `k_lub h` 是面内导热，$K_w(T-T_b)$ 当前未实现 |
| 把显式热 Newton 描述为完整 Jacobian | 明确当前为缺少 SUPG 完整导数的准 Newton |
| 未说明空化区的热模型 | 明确温度核没有液相体积分数，仍按连续液膜计算通量与耗散 |

---

## 14. 公式自洽检查

对任何由同一组有量纲参数生成的算例，至少应满足以下恒等关系：

$$
\boxed{Q_w=Q_fl_rR,}
$$

$$
\boxed{\mathrm{St}_\omega=2\lambda_0,}
$$

$$
\boxed{
\frac{q_\theta}{Q_f}
=\lambda_0\bar h
-l_r^2\frac{\bar h^3}{\bar\mu}\bar p_{,\theta},
}
$$

$$
\boxed{
\frac{q_z}{Q_f}
=-l_r\frac{\bar h^3}{\bar\mu}\bar p_{,\zeta},
}
$$

$$
\boxed{
\frac{R\Phi}{\rho c_pQ_f\Delta T}
=\Theta_E
\left[
\frac{\lambda_0^2}{3l_r^2}\frac{\bar\mu}{\bar h}
+\frac{\bar h^3}{\bar\mu}
(l_r^2\bar p_{,\theta}^2+\bar p_{,\zeta}^2)
\right].
}
$$

还应检查：

1. 压力方程积分后的边界净流量与孔口净流量、油膜体积变化一致；
2. 正向孔口点源满足 $\sum_{ij}(K_Q)_{ij}{+}=q_{n,i}$、
   $\sum_j(f_Q)_j{+}=q_{n,i}\bar T_s$；最近节点是其单单位权重特例；
3. `k_lub=0` 时物理扩散矩阵严格为零，但 SUPG 可非零；
4. 均匀温度下，面内导热为零，而未实现的壁面换热一般不为零；
5. 有量纲与无量纲公共包装器在相同物理输入下给出一致的力、温度和黏度。

---

## 15. 适用边界

当前推导和代码适用于层流、不可压缩、薄膜、跨膜平均温度的 ALB 液体润滑计算。下列物理过程不在当前模型中：

- 轴颈和瓦块实体三维导热及共轭传热；
- 跨膜温度梯度和黏度沿 $y_f$ 的分布；
- 温度相关密度、比热和导热率；
- 湍流修正、惯性修正和压力功；
- JFO/Elrod-Adams 质量守恒空化及空化区液相率；
- 孔口、管路和伺服阀内部的热生成；
- 局部壁面换热项 $K_w(T-T_b)$；
- 移动空化边界的完整非线性频域线性化。

若论文声称求解“完整热流体动压润滑”或“油膜-轴颈-瓦块共轭传热”，则当前程序证据不足；准确表述应是“含主动供油点混合、面内流量输运、黏性耗散、可选面内导热和温黏反馈的二维跨膜平均热流体润滑模型”。
