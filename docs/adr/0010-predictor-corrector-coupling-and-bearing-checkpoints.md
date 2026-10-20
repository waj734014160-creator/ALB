# ADR-0010：预测-校正分区耦合与轴承存档/回退契约

- 状态：Accepted。新增可选积分器，默认 staggered 与 ROS2 行为不变；真实模型（M42 代理、
  hb34 FEM 液膜、热模型、热记忆与 LSTM 代理）的本地核对尚未完成，见“验证状态”。
相关文件：`docs/adr/0007-preserve-validated-numerical-algorithms.md`、
  `docs/adr/0009-controller-sampling-period-and-ros2-integrator.md`、
  `docs/migrations/0.4.7.md`、
  `ALB/dynamics/predictor_corrector.py`、`ALB/core/checkpoint.py`、
  `refs/coupling_staggered_pre_0_4_7_reference_v1.json`、
  `refs/coupling_staggered_pre_0_4_7_reference_v1.npz`、
  `refs/predictor_corrector_0_4_7_reference_v1.json`、
  `refs/predictor_corrector_0_4_7_reference_v1.npz`。

## 背景

默认 staggered 格式用上一步提交的转子状态计算轴承力，即 `F_{n+1} ≈ F(y_n)`，轴承力
滞后一步，耦合精度为一阶。它把轴承当作黑箱，只走 `input → evaluate → output` 生命周期，
因此瞬态热、控制器和阀等带内部记忆的模型都能使用。

0.4.6 的 ROS2 消除了滞后，达到二阶，但要求轴承力是无副作用的纯函数，并需要雅可比
`J`。热模型因此被拒绝，主动轴承必须拆成“采样控制器 + 阀芯状态 + 瓦块求力”。用户在
M42 准稳态代理上的本地核对表明，依赖导数的格式对 `J` 的取值位置很敏感：默认 `J`
取在轴颈居中处（代理刚度奇异），每转 400 步时误差为 −23%，每 20 步重算 `J` 后为
−0.06%。hb34 FEM 液膜的 `probe_force` 虽是纯函数，但力在网格尺度上有跳变（位置变
0.05 μm 或速度变 0.05 mm/s 时，力跳 77～181 N），推测与空化边界逐节点切换有关。

需求是：保留 staggered 的黑箱特性（不求导、不拆模型、支持带记忆的模型），同时消除
轴承力的一步滞后。

## 决策

1. **新增可选积分器。** `SimulationConfig(integrator="predictor_corrector",
   predictor_corrector=PredictorCorrectorOptions(...))`，文件配置为
   `spec.time_grid.integrator: "predictor_corrector"` 与
   `spec.time_grid.predictor_corrector: {...}`。默认仍为 `"staggered"`；staggered 与
   ROS2 路径的语句不变（`INTEGRATORS` 只增加名称）。

2. **每步算法（n → n+1）。** 记 `x_n` 为已提交转子状态，`F_n` 为已提交轴承力，
   `G_n = L(t_n) + M F_n` 为已提交全局载荷，`M` 为轴承力到全局载荷向量的线性映射：

   ```text
   L1  = L(t_{n+1})                                  外载荷（不写日志的 force_at）
   P^0 = 2 F_n - F_{n-1}（linear，首步 F_n）或 F_n（constant）
   k = 0, 1, ...
     x^k  = Prop(x_n, G_n, L1 + M P^k)               转子试算，纯函数
     F~^k = Trial(y(x^k); t_{n+1})                   各轴承同时试算（Jacobi）
     r^k  = F~^k - P^k                               界面残差，单位 N
     iterate：||r^k||_inf <= rtol max(||F~^k||_inf, f_ref) + atol 时收敛
     pece：k = 0 后直接退出
     否则按松弛规则得到 P^{k+1}
   P*      = F~^k
   x_{n+1} = Prop(x_n, G_n, L1 + M P*)
   F_{n+1} = Commit(y(x_{n+1}); t_{n+1})             每个轴承只提交一次
   G_{n+1} = L1 + M F_{n+1}
   ```

   `Prop` 是 `RossRotor._propagate_trial`，与 `_propagate` 使用同一套公式（连续模型
   为一阶保持精确离散，离散模型为 ROSS 零阶保持），不改动转子对象。`f_ref` 取
   `||F_n||_inf` 与 1 N 中的较大者。提交的状态与力相互一致：力在校正后的状态上重算，
   与常微分方程 PECE 的约定相同。`||F_{n+1} - P*||_inf` 作为事后一致性残差写入诊断。
   PECE 每步 2 次求值（1 次试算 + 1 次提交），与 ROS2 相同但不需要 `J`；迭代版为
   试算次数 + 1。

3. **试算。** 试算从轴承在 `t_n` 已提交的全部内部状态出发，用试算输入（轴颈位移、
   速度、时间 `t_{n+1}`，以及阀芯开度）完整执行一次单步求值，取出力，然后使轴承回到
   `t_n` 的提交状态。带记忆的模型因此在每次试算中用试算输入推进一次自己的记忆；迭代
   收敛后，记忆通道也与转子一致，而不是冻结在 `t_n`。按运行时能力分两类：

   - 有可用 `probe_force` 的无副作用 runtime（无热液膜、气膜、固定阀芯代理、只由这些
     组成的多瓦，以及给定阀芯时的直接阀芯轴承）直接探测；`MultiPad` 与主动轴承通过
     `probe_force_supported` 报告子瓦是否都能探测。
   - 其余 runtime 实现存档协议：每步存档一次，每次试算走正常生命周期后立即回退。

4. **存档/回退契约。** `ALB.contracts.CheckpointableRuntimeProtocol` 定义
   `checkpoint() -> object` 与 `restore(token) -> None`：

   - 完整性：令牌覆盖所有影响此后结果的状态（热场与粘度缓存、控制器积分与差分记忆、
     采样计数与保持指令、阀状态、节流器滚动缓冲、生命周期与最新输出/结果/收敛状态、
     可选的压力和膜厚保存历史与后处理记录）。
   - 逐位契约：“存档 → 任意次试算 → 回退 → 正常求值”与“直接正常求值”逐位相同；
     令牌可重复回退，试算失败（`FAILED`）后同样可回退。
   - 只存时变状态：网格、FEM 组装对象和 torch 模型只保留引用，不做 `deepcopy`。
   - 复合轴承（多瓦、主动轴承、热包装）委托给各子对象的令牌。
   - 随包实现使用 `ALB.core.checkpoint` 的组件快照：每个 runtime 列出持有时变状态的
     对象，快照保存其属性字典，字典、列表和数组原地恢复以保持共享引用一致。元素矩阵
     和全局装配矩阵是每次求解都重建的求解器临时量，不存档。

5. **松弛与加速。** `relaxation` 取 `"aitken"`（默认，动态 Aitken 松弛，Küttler 与
   Wall 2008）、`"iqn_ils"`（最小二乘逆雅可比的界面拟牛顿，Degroote、Bathe 与
   Vierendeels 2009）、`"constant"` 或 `"none"`。不加松弛时，迭代收敛条件是一步映射为
   压缩映射，即 `ρ(∂F/∂y · ∂y/∂P) < 1`，`∂y/∂P` 来自 `Bd1`：对位移约为 `h²/(6m)`，
   对速度约为 `h/(2m)`。刚度大、尤其阻尼大的油膜在实用步长下可能使 `ρ > 1`，此时
   `none` 和 PECE 发散或失稳，必须使用 Aitken 或 IQN-ILS；两者都不需要导数。分区
   分析的一般讨论见 Felippa、Park 与 Farhat（2001）。

6. **不收敛与失败。** `on_nonconvergence="warn"`（默认）在达到 `max_iterations` 时
   提交最后一次迭代，整个运行只在第一次发出 `ALB.CouplingIterationWarning`
   （`UserWarning` 子类），不收敛步数和最大残差写入诊断与结果元数据；`"raise"` 抛出
   `CouplingIterationError`，按 ADR-0002～0004 的失败封存契约处理，运行时失效。试算中
   轴承抛出异常时，先在 `finally` 中回退存档，再以 `CouplingTrialError`（原异常为
   `__cause__`）封存该步失败；不静默重试，也不自动减小步长。非有限值同样按失败处理。

7. **外部阀芯 provider。** 实现了 `checkpoint()`/`restore()` 的 provider 在每次试算时
   用试算输入调用，并与轴承一起回退；未实现的 provider 与 ROS2 相同，在每次提交时采样
   一次，阀芯在下一步的试算中保持，该通道为一阶精度。

8. **控制周期。** ADR-0009 的控制周期校验和步长调整对新格式同样适用。主动轴承的控制器
   留在黑箱内部，按提交次数计数；试算被回退，不影响计数，控制器恰好每 `m` 次提交执行
   一次。迭代收敛后，控制器在 `t_{n+1}` 采样的就是提交状态，与 ROS2 的采样语义一致。
   阀模型对输入指令做一阶保持插值（ADR-0009 第 2 条），因此 `m > 1` 时采样时刻的指令
   跳变被摊到采样时刻之前的一步内，阀芯通道降为一阶（解析算例实测误差比约 2）；`m = 1`
   时为二阶。本次不修改阀的离散方式。

9. **元数据。** 只有预测-校正运行在结果元数据中写入 `predictor_corrector_options` 与
   `predictor_corrector_diagnostics`（步数、试算次数、提交次数、每步迭代次数的均值/
   最大值/直方图、不收敛步数、最大最终残差、最大一致性残差、残差比、Aitken 因子范围、
   各轴承试算方式与阀芯来源）。默认路径的元数据与 `result.write()` 文件集合不变；ROS2 与
   控制周期运行保持 0.4.6 的键集合。

10. **参考。** 实现前在未改动的 `9432c06` 上冻结 staggered 下的热液膜（瞬态与稳态）、
    带热主动轴承、含子瓦的多瓦和外部阀芯轴承参考；0.4.6 的两份参考继续精确相等。新格式
    的行为参考在实现完成后单独生成并冻结，均不为迎合实现而重新生成。

## 与 ADR-0007、ADR-0009 的关系

- ADR-0007 第 1 条：预测-校正是新增的可选算法，没有替换已验证的 staggered 或 ROS2；
  两条路径的语句不变，默认路径数值逐位不变。
- ADR-0007 第 5 条：修改前从固定提交冻结输入、完整数组和环境元数据，并做精确相等回归；
  新行为参考在实现完成后另行冻结。
- ADR-0007 第 6 条：新算法单独立项，给出数值理由（消除一步滞后、保持黑箱、无导数、
  收敛阶证据），并冻结修改前（staggered）和新算法两侧参考。
- ADR-0009：控制周期例外与步长调整规则原样适用；ROS2 的“功能不完善”状态不变，其默认
  `J` 问题不在本 ADR 范围内。预测-校正在收敛时与 ROS2 的采样语义一致；阀的一阶保持
  插值在两种格式下的影响不同（见决策第 8 条）。

## 显式状态模型的接入方式

本地的热记忆代理（`ALB/surrogate/thermal_memory*.py`，状态进、状态出的 MLP）与 LSTM
残差代理（`thermal_residual_lstm.py`，隐状态 `h`、`c`）不需要提供 `probe_force`，也
不需要导数，只需实现存档协议：`checkpoint()` 返回已提交的显式状态（记忆向量或
`(h, c)` 张量的副本、最近一次输入时间，以及生命周期、最新输出和结果快照的引用），
`restore(token)` 把这些值写回；torch 模块本身只保留引用。由于它们不是无副作用的
纯函数，预测-校正会自动走“存档 → 生命周期试算 → 回退”路径，每次试算用试算输入推进
一次记忆，收敛后在提交时再推进一次；若它们包装液膜 runtime，存档委托给液膜的令牌。
ROS2 仍不支持这类模型。

## 验证状态

云端用解析转子与解析轴承验证了收敛阶（线性轴承对矩阵指数精确解、硬化轴承自收敛、
带记忆黑箱轴承、采样主动黑箱轴承）、迭代机制（刚性阻尼算例、不收敛、试算失败、求值
计数）以及全部随包轴承族的存档/回退逐位契约，并在小网格瞬态热液膜上运行了新格式。
仓库中没有训练好的 ALBNN 代理模型，代理模型族只做了接口层验证；M42 代理、hb34 FEM
液膜、热模型和本地热记忆/LSTM 代理的核对由用户在本地完成。

## 影响

- 新增根符号 `CouplingIterationWarning`，根 API 由 28 个符号增至 29 个；新增高级导出
  `ALB.dynamics.PredictorCorrectorOptions` 和契约 `CheckpointableRuntimeProtocol`。
- 新增可选配置字段 `time_grid.predictor_corrector` 及其 10 个选项；`time_grid.integrator`
  增加取值 `"predictor_corrector"`。JSON5 `schema_version` 和 `ALB.SCHEMA_VERSION`
  仍为 `0.4.0`，合法的 0.4.6 配置无需迁移。
- 随包 runtime 新增 `checkpoint()`/`restore()`；`MultiPad` 与主动轴承新增
  `probe_force_supported`。staggered 路径不调用这些方法。
- 每步代价为试算次数加一次提交；存档令牌在小网格算例上约 0.5～5 ms，相对 FEM 求解
  可忽略。
- Python 包版本升级为 `0.4.7`。迁移和能力边界见 `docs/migrations/0.4.7.md`。

## 修订关系

本文补充 ADR-0009：在控制周期例外与可选 ROS2 之外，再增加一个不依赖导数、保持轴承
黑箱的可选耦合积分器。ADR-0007 的数值算法保留原则与参考冻结规则继续有效。
