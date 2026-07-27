# ALB 0.4 模块分类与接口架构

## 文档角色

- 角色：稳定模块边界与接口协议说明。
- 目的：定义 0.4 的依赖方向、用户 facade、领域协议、单位制、提交和无兼容边界。
- 允许更新：模块分类、接口契约、依赖规则、单位制规则和稳定验证入口。
- 禁止更新：实时状态、单次指标、训练进度和临时日志。
- 更新时机：公共接口、模块边界或验证入口变化时。
- 事实来源：`ALB/api/`、`ALB/contracts/`、`ALB/dynamics/`、
  `tests/validation/test_import_boundaries.py`。

## 核心原则

1. 包根是面向用户的窄 facade；领域 namespace 是严格 DTO 和研究扩展边界。
2. 配置、构建、计算、分析、提交历史和写盘是独立职责。
3. 数值公式和有效结果由冻结参考保护；接口重构不得替换已验证核心算法。算法
   变化必须单独立项并冻结变更前后两侧参考。
4. `Signal`、隐式 `lead_loop`、旧工厂和兼容 adapter 不进入任何运行时路径。
5. 单位制、控制模式、阀类型、spool 和挂载拓扑必须显式，禁止运行时猜测。
6. 所有公开结果不可变；读取属性不得触发计算或提交。
7. runtime 复用应选择最小机制：禁止仅为改变继承形式而创建逐方法转发壳。
   无状态薄 mixin 可以把 DTO 生命周期叠加到既有求解器，但不得复制数值方法
   或新增第二份状态来源；是否保留以行为回归而非结构检查决定。

mixed-film runtime 直接使用量纲或无量纲 `FilmSystem` 的数值实现，并以薄
生命周期 mixin 发布 DTO 和不可变结果。它不再维护 `_film_solver` 代理，也不
重复转发 `solve()`、`calc_capacity()`、`save()` 等原生方法。量纲、带节流器
量纲和无量纲三条路径由冻结数值参考逐元素检查。

## 用户 facade

```text
strict JSON5 / BearingConfig
             ↓
        build_bearing
             ↓
 Bearing.calculate(...) ──→ immutable BearingResult
             ├────────────→ isolated BearingAnalysis
             └────────────→ explicit reset()

SimulationConfig / JSON5
             ↓
       build_simulation
             ↓
RotorBearingSimulation.run() → immutable SimulationResult
```

`Bearing.calculate()` 为 keyword-only，`velocity` 默认为 `(0, 0)`，`time`
必须显式给出并按 `time_step` 前进。`external_spool` 必须提供归一化
`spool=(sx, sy)`；其他模式禁止 spool。

facade 不公开 `init()`、可变 `.pads/.controller/.valve`、`.signal` 或旧
save fallback。`reset()` 通过重新构建内部 runtime 开启同配置的新会话。

## 领域生命周期

高级代码可以直接使用 `BearingInput`、`DirectSpoolBearingInput` 和正式
bearing runtime 的 `input/evaluate/output/step`。其职责固定为：

```text
input(dto) → validate and latch
evaluate() → exactly one calculation
output() → read completed immutable snapshot
step(dto) → input + evaluate + output
```

公开协议不要求用户初始化。组合所有者需要重新开始子会话时调用私有 reset
hook 或创建新 runtime。失败状态是终止性的；failure snapshot 不泄漏原异常
路径、配置正文或凭据。

`MultiPad` 和 `GasFilmRuntime` 与 active、liquid-film、harmonic 和 surrogate
使用同一生命周期。`MultiPad.evaluate()` 每步只推进每个子瓦一次并发布汇总力，
不默认积累历史。

## 数值分析边界

`EquilibriumSolver(bearing).solve()` 是可由用户和内部模块直接构造的静平衡
模型，使用独立静态 runtime 会话和专用阻尼 Newton 算法；
`bearing.analysis.find_equilibrium()` 只转发到同一模型；
液膜轴承与内部控制或不受控的主动润滑轴承共用这一实现，主动润滑静态试探会
在每次评估前复位静态伺服阀；`external_spool` 不在此入口中隐式推断；
`dynamic_coefficients()` 从一个 `EllipseTrajectory` 生成独立正反涡动并调用
复数识别；`harmonic_linearize()` 直接计算压力方程导数和已验证的节流耦合。
空间方向使用 `orientation_rad`，时间相位使用 `phase`，两者不可混用。任何
内层或轨迹样本不收敛时均不发布分析结果。动态系数的时间网格必须均匀并使目标
频率命中非 DC FFT bin；正反涡动复位移矩阵必须有限、满秩且条件数受限。精确
零载荷不属于既有相对残差静平衡算法的输入域。

公开分析 facade 可以改变参数命名和结果组织，但内部算法变化受 ADR-0007
约束。0.4.1 不包含可倾瓦轴承实现。

## 配置边界

所有可运行配置文档采用：

```json5
{
  schema_version: "0.4.0",
  kind: "bearing",
  includes: ["profiles/base.json5"],
  spec: { /* current document overrides last */ }
}
```

include 按声明顺序深度合并 mapping；数组和标量整体替换；显式 `null` 是最终值。
路径必须是 UTF-8 相对路径且不得逃逸最外层配置目录。循环、重复路径、跨 kind
引用、未知字段和跨字段不一致立即抛出 `ConfigurationError`。

资源路径始终相对最外层可运行文档解析。`BearingConfig` 只保存不可变快照；
override/sweep 不原地修改，且必须重新完成 schema 与跨字段校验。

## 组合与提交

转子轴承仿真只接收构造期固定的 `BearingMount` 元组。每个 mount 固定
`BearingConfig`、节点以及可选 unit adapter/spool provider；运行期没有
`add_bearing()`。`RotorProtocol` 显式声明只读 `dt`。无 adapter 的 mount
使用全局步长；有 adapter 的 mount 使用转换后的 bearing-local 步长。根配置、
嵌套 `MultiPad` 以及物化控制器、阀和热组件必须与该 local 步长一致，不一致
在任何物理 runtime 创建前失败。

底层 coupling 按以下顺序推进：

```text
preflight → mutable execute → immutable candidate
          → atomic commit → publish → recorder → observer
```

提交前失败不发布半步；提交后 recorder/observer 异常不得把已提交物理状态
改写为无效。高层仿真不重试、不继续，但会从 ledger 和只读 output 取回该真实
提交。partial result 分别报告物理步骤、历史发布和 post-commit 完整性。
磁盘流只在临时快照 flush/fsync 并原子替换成功后发布 retained 状态；manifest
使用同一事务边界。simulation 对象是一次性会话，成功或失败后第二次
`run()` 都会明确拒绝；新会话必须构建新对象。

## 结果与副作用

`BearingResult`、`AnalysisResult` 和 `SimulationResult` 的数组只读。结果的
`write(path)` 是唯一面向用户的写盘入口，内部委托 artifact writer；数值模块
不决定路径。单轴承只保留 `latest_result`，分析结果包含完整采样点，仿真历史
由 `HistoryPolicy` 显式控制。

单液膜结果直接提供 `force`、`friction`、`pressure` 和 `film_thickness`：
量纲压力/膜厚为 Pa/m，无量纲压力/膜厚为 `p/ps`、`h/c`。多瓦和主动轴承的
各瓦场保存在 `pad_pressure` 和 `pad_film_thickness`，避免构造没有物理意义的
合成压力场。字段含义、单位和配置缺省值见
`docs/api/bearing_config_reference.md`。

## 研究扩展

研究组件只能通过 typed component factory、build dependency、spool provider
和 observer 注入。配置文件不反序列化 Python 类或回调；运行后组件拓扑不可变。
领域 namespace 可以公开严格 DTO 和协议，但不得重新导出 0.3 兼容名称。

## 无兼容边界

0.4 wheel 中以下内容必须为零：

- `Signal` 与 `lead_loop` 消费者；
- `Legacy*Adapter`、`BearingBlock` 兼容族和旧 factories；
- 旧根导出、旧配置字段、宽松 materialize/envelope 用户入口；
- 旧 surrogate package、pickle scaler 运行时加载和兼容 CLI；
- 安装到 wheel 的 `tools/migrations`。

历史 ADR、refs、outputs 和机器证据可以提及旧名称；可执行源码与安装制品不可以。

## 稳定验证入口

```powershell
E:/Anaconda2023/envs/ALB/python.exe -m pytest -q
E:/Anaconda2023/envs/ALB/python.exe tools/validation/run_layered_mypy.py
E:/Anaconda2023/envs/ALB/python.exe -m tools.validation.run_release_acceptance_0_4_2 --candidate HEAD
```

发布验收必须从固定 SHA 建立 detached worktree，连续构建两个相同 wheel，
审计 wheel 内容、隔离安装并执行主仓库及声明外部消费者 smoke。
