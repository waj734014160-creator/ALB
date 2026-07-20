# ALB 模块分类与接口架构

## 文档角色

- 角色：稳定模块边界与接口协议说明。
- 目的：定义 ALB package 的依赖方向、通用模板、领域协议、单位制边界、兼容策略和后续迁移顺序。
- 允许更新：模块分类、接口契约、兼容层、依赖规则、单位制规则和稳定验证入口。
- 禁止更新：实时运行状态、单次实验指标、训练进度、临时日志和未验证的迁移结论。
- 更新时机：通用接口、模块边界、推荐导入路径或兼容策略变化时。
- 事实来源 / 相关文档：`ALB/contracts/`、`ALB/core/`、`ALB/adapters/`、`test/contracts/`、`docs/alb_package_overview.md`。

本文给出 2026-07-20 首轮接口重构后的稳定架构。首轮目标不是一次性移动 `film.py`、`thermal.py`、`controller.py`、`nn.py` 等大型实现，而是先建立可验证的依赖方向和接口边界，再允许实现逐个迁移。旧模块路径继续可用，避免破坏 `SURROGATE_TRAIN`、论文脚本和历史 pickle。

## 已固定的重构基线

重构前源码和行为参考均已固定，不应重写现有 v1 参考：

| 类型 | Git 对象 | 用途 |
| --- | --- | --- |
| 源码基线 | commit `24ea190becf19c6f0e33e3c05686c0052dfdbedd`；tag `pre-interface-refactor-20260720` | 定位重构前生产源码。 |
| 行为参考 | commit `597f3fe`；tag `pre-interface-refactor-refs-20260720` | 固定接口元数据、信号顺序、谐波轴承、旧线性代理、转子耦合和 scaler pickle 行为。 |
| 数值参考 | `refs/interface_contract_reference_v1.json`、`refs/interface_contract_reference_v1.npz` | 精确回归，不使用容差覆盖行为漂移。 |
| 回归入口 | `test/contracts/test_interface_contract_reference.py` | 校验旧 import、旧 public export 目标及所有参考数组。 |

如果未来有意修改数值行为，应新增 v2 参考并说明物理或数值原因，不能覆盖 v1。

## 设计原则

1. 不建立包含通用 `input/output/solve` 语义的万能基类。轴承、转子、控制器和伺服阀对这些方法的含义不同。
2. 继承只复用生命周期、事件、结果、组合关系和单位制元数据；领域行为由窄 `Protocol` 定义。
3. 物理求解模块不能依赖邮件、远程执行、GUI 或实验 workflow。告警通过注入的端口完成。
4. 有量纲和无量纲对象必须显式声明 `unit_system`；有量纲转子耦合拒绝显式无量纲轴承。
5. 老 import 路径作为兼容 facade 保留至少一个明确的迁移周期。
6. 所有跨模块迁移先运行固定参考，再修改实现，最后运行精确回归。

## 目标依赖方向

```text
ALB.contracts
    ^
ALB.core
    ^
ALB.physics / ALB.control / ALB.dynamics / ALB.surrogate
    ^
ALB.systems
    ^
task / remote / GUI / external workflows

ALB.adapters 连接旧实现与新协议，但不拥有物理方程。
```

允许上层依赖下层；下层不得反向依赖 workflow 或基础设施。`ALB.base`、`ALB.bearing`、`ALB.controller` 等旧模块目前仍是兼容入口，不代表目标依赖方向。

## 模块分类

| 分类 | 新入口 | 当前职责 | 兼容实现位置 |
| --- | --- | --- | --- |
| 结构协议 | `ALB.contracts` | 轴承、线性系数能力、控制器、伺服阀、转子、时间网格、持久化、通知和收敛状态。 | 无；这是接口事实来源。 |
| 通用核心 | `ALB.core` | `ComponentBase`、旧模板兼容类、`Signal`、`TimeIter`、验证和限幅。 | `ALB.base`、`ALB.servovalve.limit_signal` 继续 re-export。 |
| 兼容适配器 | `ALB.adapters` | `BearingDecoratorBase`、`LegacyBearingAdapter`。 | 热 wrapper 已迁移到 decorator 模板。 |
| 物理模型 | `ALB.physics` | 油膜、轴承、节流孔、气膜、热模型的分类入口。 | `film.py`、`bearing.py`、`orifice.py`、`gas.py`、`thermal.py`。 |
| 控制 | `ALB.control` | PID、Fuzzy PID、LQG、伺服阀、限幅和自适应阻尼。 | `controller.py`、`servovalve.py`、`damping.py`、`lti.py`。 |
| 动力学 | `ALB.dynamics` | 转子、转子-轴承耦合和时间网格。 | `rotor.py`、`couple.py`。 |
| 系统装配 | `ALB.systems` | ALB / NodimALB 和谐波线性 ALB 装配入口。 | `alb.py`、`harmonic_linear.py`。 |
| 代理模型 | `ALB.surrogate` | 部署侧 ALBNN / ALBNet 分类入口。 | `nn.py`；旧路径用于 checkpoint/pickle 兼容。 |

分类 namespace 使用 lazy export，因此不会仅因导入分类包就加载全部可选依赖。

## 通用模板与领域接口

### 通用模板

| 模板 | 共享内容 | 明确不共享的内容 |
| --- | --- | --- |
| `ComponentBase` | `results`、`signal`、开始/结束事件钩子、`unit_system` 元数据。 | 物理输入、求解算法和输出语义。 |
| `BaseSimpleModel` | 保留旧抽象方法集合和 import 兼容。 | 不作为新领域接口定义。 |
| `BaseSystem` | 主模型与辅助模型组合、无重复 signal 注册、允许 `main_model=None`。 | 不规定主模型类型。 |
| `BaseCSystem` | peer component 组合的旧兼容模板。 | 不承诺轴承或转子协议。 |
| `BearingComponentBase` | 二自由度状态/力校验和默认有量纲声明。 | 不实现任何具体轴承力。 |
| `BearingDecoratorBase` | 轴承方法、结果和保存行为委托。 | 不隐式进行有量纲/无量纲换算。 |

### 窄协议

| 协议 | 最小语义 |
| --- | --- |
| `BearingProtocol` | `node_link`、`signal`、`unit_system`、`init()`、`input(uxy, uxyt, t)`、`output()["force"]`、`calc_is_finished()`、`results`、`save()`。 |
| `BearingCoefficientProtocol` | 可选的 `K`、`C`、复 `G_xv` 能力，不要求所有非线性轴承提供。 |
| `RotorProtocol` | `init()`、按节点读取 `uxy/uxyt`、用当前和前一步节点力推进、`save()`。 |
| `ControllerProtocol` | `init()`、`input(t, error)`、`output()`、`save()`。 |
| `ServoValveProtocol` | `init()`、`input(t, command)`、`output()`、完成状态和保存。 |
| `TimeGridProtocol` | `num`、`dt`、`t_list` 和迭代行为。 |
| `NotifierProtocol` | `notify(message, subject=None)`；物理模块只依赖此端口。 |
| `PersistableProtocol` | `save(...)` 返回结果树对象，并可选择写盘。 |

`Protocol` 用于结构检查和类型检查；具体求解类仍可使用旧继承关系。这样可以先确定接口，再逐步迁移实现。

## 标准轴承协议

### 输入

```python
bearing.input(uxy=position_xy, uxyt=velocity_xy, t=time_s)
```

- `uxy` 必须是有限的二元素向量。
- `uxyt` 必须是有限的二元素向量。
- `t` 是当前样本时刻。
- `unit_system="dimensional"` 时，位移为 m、速度为 m/s；`unit_system="nondimensional"` 时使用模型自己的明确无量纲尺度。

### 输出

```python
output = bearing.output()
force = output["force"]
```

- `output` 必须是 mapping。
- `force` 必须是有限的二元素向量。
- `friction` 和诊断字段是可选能力，组合器不能假定所有轴承都提供。
- `save()` 应返回 `SaveTreeNode` 或兼容结果树，而不是只产生隐式文件副作用。

### 转子耦合边界

`RsRotorBearingCouple` 当前是有量纲耦合器：

- 显式 `unit_system="nondimensional"` 的轴承会在装配时被拒绝。
- 未声明单位制的第三方旧轴承暂时按兼容模式接收；应使用 `LegacyBearingAdapter` 补齐元数据。
- 每次轴承输出均验证 `force` 的类型、形状和有限性。
- 现有“先用轴承力推进转子，再读取下一步状态”的时序由 v1 参考固定。

## 单位制与收敛语义

### 单位制

允许值只有：

- `dimensional`
- `nondimensional`
- `unspecified`，仅用于未迁移的兼容对象

当前正式声明包括 `ALB`、`HydrostaticBearing`、`GasBearing`、`ThermalHydroBearing` 和 `ALBHarmonicLinear` 为有量纲；对应 `Nodim*` 类型为无量纲。`MultiPad` 要求所有 pad 的单位制和 `node_link` 一致。

### 收敛

旧 `calc_error()` 仍存在三类历史返回：残差标量、布尔值和空值。首轮不批量改变数值求解器，避免把布尔值误解释为残差。新接口使用：

```python
ConvergenceStatus(
    residual=<finite nonnegative float>,
    converged=<bool>,
    iterations=<nonnegative int or None>,
    message=<diagnostic text>,
)
```

后续应逐个 solver 增加明确的 `convergence_status`，完成验证后再弃用其含糊返回值。

## 首轮已完成的实现迁移

- `Signal`、`TimeIter`、`TimeIterDt`、`BaseSimpleModel`、`BaseSystem`、`BaseCSystem` 已从 `base.py` 的混合职责中提取到 `ALB.core`；旧 import 继续工作。
- `BaseSystem` 支持空主模型，并修复批量添加辅助模型时 signal 重复注册。
- `limit_signal` 的唯一实现位于 `ALB.core.validation`；旧 `ALB.servovalve.limit_signal` 保留兼容 wrapper。
- `ALBHarmonicLinear` 已使用 `BearingComponentBase`，仍保持原 `K/C/G_xv` 数值和标准轴承接口。
- 热轴承 wrapper 已使用 `BearingDecoratorBase`，不再依靠隐式的宽泛组合基类。
- `CsoArgs` 的唯一所有者为 `ALB.config`；`ALB.orifice.CsoArgs` 只做 re-export。
- `FilmSystem` 不再直接构造邮件发送器；异常通知由可选 `NotifierProtocol` 注入。
- `MultiPad` 增加空集合、单位制和节点一致性检查，不再修改第一个 pad 返回的字典，并把 `friction` 视为可选字段。
- `ALB.__all__` 由 lazy export map 唯一生成，消除手工列表漂移。

## 兼容策略

以下路径暂时不能直接删除或改名：

- `ALB.base`
- `ALB.alb`
- `ALB.bearing`
- `ALB.controller`
- `ALB.servovalve`
- `ALB.nn`
- `ALB.orifice`
- `ALB.matrix.dynmaic`

原因包括外部论文脚本、`SURROGATE_TRAIN` 导入、checkpoint/scaler pickle 的模块限定名以及历史配置。新代码优先从分类 namespace 或接口模块导入；旧实现内部可在不改变外部路径的情况下逐步变薄为 facade。

## 后续迁移顺序

1. 为 `FilmSystem`、热 solver、控制器和转子逐个增加明确的结果快照及 `ConvergenceStatus`，每个类型单独建立参考。
2. 把 `film.py`、`thermal.py`、`controller.py`、`nn.py` 的内部实现拆到对应分类子包，旧文件只保留 re-export；一次只移动一个物理域。
3. 把 `RossRotor.output()` 中“读取状态”和“推进状态”拆成显式接口，并先固定时序参考。
4. 为 wheel/package 安装环境增加隔离 import 测试，验证 lazy export 和 pickle 兼容。
5. 清理 infrastructure：`ALB/tool.py::EmailSender` 当前仍含嵌入式默认认证配置。相关凭据应立即轮换，随后改为环境变量或系统凭据管理器，并把邮件实现迁移到基础设施模块。重构文档和日志中不得记录凭据值。

大型求解器的物理文件移动属于下一阶段；首轮已经建立足够的协议和精确参考，使这些移动可以按域验证，而不是一次性承担全库风险。

## 验证入口

```powershell
E:/Anaconda2023/envs/ALB/python.exe -m pytest `
  test/contracts/test_component_contracts.py `
  test/contracts/test_interface_contract_reference.py -q
```

参考测试要求旧数值数组逐元素相等；接口测试覆盖 Protocol、模板、adapter、signal 去重、单位制边界、`CsoArgs` 唯一所有者、通知注入和分类 namespace。
