# ALB 仿真配置字段参考

## 文档角色

- 角色：面向普通用户的 rotor-bearing simulation JSON5 结构、字段、资源边界和程序化入口说明。
- 目的：让用户明确区分文件配置能表达的内容、`SimulationConfig` 的高级运行时对象，以及每个输入和输出的单位与生命周期。
- 允许更新：公开 simulation 文档结构、资源路径规则、载荷、历史策略和结果合同。
- 禁止更新：内部耦合 helper、远程运行状态、本机绝对路径和未进入稳定入口的 ROSS 细节。
- 更新时机：`ALB/api/simulation.py` 或 `ALB/api/_config_fields.py` 的公开合同变化时。
- 事实来源：`ALB/api/simulation.py`、`ALB/api/_config_fields.py` 和 `ALB.dynamics` 显式导出的高级类型。

## 两种构造方式

文件入口 `ALB.load_simulation_config(path)` 读取严格 UTF-8 JSON5，构建并返回
`SimulationConfig`；`ALB.simulation_from_file(path)` 再把它包装成可运行的
`RotorBearingSimulation`。文件配置当前只接受 `rotor.model: "ross_excel"`，因此
需要用户提供一个实际存在的 ROSS Excel 资源和至少一个轴承 JSON5 文件。

程序化入口 `ALB.SimulationConfig(...)` 接受已经满足 `RotorProtocol` 的量纲转子、
`BearingMount` 对象、载荷和 `HistoryPolicy`。记录器、observer 及后提交失败策略只能通过
高级 `ALB.dynamics.CouplingRuntimeDependencies` 对象提供；它们不能序列化进普通 JSON5。
程序化转子的 `rotor.dt` 必须与 `time_step` 完全相等，`rotor.unit_system` 必须为
`dimensional`。

## 文档、include 与资源边界

顶层文档固定使用 `schema_version: "0.4.0"` 和 `kind: "simulation"`。
`includes` 只能引用同一外层文档目录下的相对 `simulation_profile` 文件；绝对路径、
越过根目录的路径、重复 include 和循环 include 会在构建前拒绝。profile 按列表顺序
深度合并，当前文档的 `spec` 最后覆盖。

`rotor.path` 和 `history.directory` 会解析后检查仍位于外层 simulation 文档目录内。
`mounts[].bearing` 也是相对 simulation 文档的轴承配置路径；轴承文档内部的 profile、
模糊规则、子瓦和模型包继续按该轴承文档自己的资源根处理。示例中的占位路径不是随包
提供的数据资产，必须替换为用户自己的文件。

## 时间与提交语义

`time_grid.steps` 表示初始状态之后的推进次数，因此未下采样的内存历史通常有
`steps + 1` 个提交样本。仿真对象是一次性的：第一次 `run()` 后不能再次运行，重复计算
需要重新构建。物理步提交后若 recorder、observer 或磁盘历史失败，运行不会重复该物理
步；`SimulationError.partial_result` 和 `failure_snapshot` 保存已经提交的可审计边界。

## 载荷

- `static` 在一个节点施加固定 `[Fx, Fy]`，单位 N。
- `gravity` 在 y 方向施加重力；显式负加速度可反转方向。
- `unbalance` 使用节点、质量、偏心、频率、相位和可选斜坡生成转子激励。

载荷在 `SimulationConfig` 构造时完成字段和值域校验并冻结；`run()` 不重新解释未知键。

## 历史与输出

`memory` 保存全部策略选中的提交；`ring_buffer` 只保留最近 `capacity` 个；
`disk_stream` 把每个保留步原子写入 `directory`，内存结果的对应数组为空尾维，
`SimulationResult.metadata["history_path"]` 指向历史目录。`downsample` 总是保留索引 0
和整除该值的提交，完成或失败时还会强制保留最后一个已提交状态。

`SimulationResult.time` 第一维与全部保留数组一致；转子位移/速度通常为
`(samples, rotor_dofs)`，轴承力通常为 `(samples, mount_count, 2)`，单位分别为 m、m/s
和 N。`SimulationResult.as_bundle()` 返回只读持久化快照，`write(path)` 只写入一个新的
目标目录。
