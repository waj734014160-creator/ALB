# 每日总结记录

## 文档角色

- 角色：项目级日常维护摘要。
- 目的：保存简洁的文档维护摘要和稳定项目组织决策。
- 允许更新：日常维护摘要、清理确认、稳定文档变更和稳定项目级决策。
- 禁止更新：实时任务状态、原始日志堆叠、详细 ALBNN 指标、活跃 PID 和瞬态 ETA。
- 更新节奏：日常维护 pass 或显式项目摘要请求。
- 事实来源 / 相关文档：
  `docs/daily_maintenance/daily_doc_update_index.md`.

本文档用于沉淀日常开发、验证和方案设计工作。后续记录按日期持续追加，不再分散到多个零散说明文件中。旧历史条目保留原样；若后续维护触及历史条目，应只做必要的事实性修正或压缩，避免重写证据链。

## 每日记录模板

复制以下模板并在文末追加：

```md
## YYYY-MM-DD

### 今日目标
- 

### 代码与文档修改
- 

### 今日完成内容
- 

### 验证与结果
- 

### 关键结论
- 

### 风险与遗留问题
- 

### 明日计划
- 

### 相关文件
- 
```

---

## 2026-04-24

### 今日目标
- 完成热流耦合模型的文档补充、公式与代码一致性核对。
- 完成热效应相关后处理、验证脚本和工程估算对比。
- 梳理热效应代理模型的时序建模方案，为后续与转子耦合做准备。

### 代码与文档修改
- 补充并修订了热模型说明文档，重点包括非稳态项、隐式 Euler 时间离散、Kadv-diff 的物理含义与代码对应关系，以及有量纲/无量纲量转换一致性检查。
- 约束热模型配置中 pressure_backend 仅允许 skfem 路线，旧 h_eff 分支保留为参考实现但不再作为用户可选项。
- 在 ALB.tool 中补充轴承油膜 Nastran 网格导出与三维预览能力，并处理了 COMSOL 导入时的兼容性问题。
- 新增热流耦合后处理能力，支持压力场、温度场、黏度场的结构化四边形云图、数据保存与一维曲线提取。
- 完成热效应系统验证脚本扩展，加入边界条件对比、网格收敛、热开关对比，以及工程方法迭代黏度后的承载力对比。

### 今日完成内容
- 完成热模型文档与代码的一致性梳理，明确了温度方程中的扩散、对流、热源、瞬态项在代码中的装配位置。
- 完成右下瓦块工况的热效应验证脚本，设置为偏心率 0.5、姿态角 90°、瓦块包角 90°、转速 50 Hz，并输出温度场、压力场和汇总信息。
- 完成热效应后处理类，能够直接输出结构化 temperature_field、pressure_field 与 viscosity_field_grid，便于验证和后续数据集构造。
- 完成工程方法验证逻辑修正：验证目标由“温升对比”调整为“工程迭代黏度对应的承载力与热耦合承载力对比”。
- 完成参考边界条件修正，明确当前代码中的混合边界条件对应 axial_side_bc = inflow_fixed。
- 完成热效应代理模型方案梳理，明确后续不能仅使用平均温度或有效温度作为唯一状态。

### 验证与结果
- 参考热效应工况改为 mixed 边界，对应代码项为 inflow_fixed。
- 网格收敛结果已经输出到 run/validation/outputs/validation_thermal_right_lower/validation_thermal_right_lower_mesh_convergence.csv。
- 细网格参考工况结果：thermal_load_N = 4204.233 N，engineering_load_N = 3766.484 N，load_ratio = 0.895879。
- 热开关对比结果显示，开启热效应后承载力相对热关闭工况下降，趋势符合“温升导致黏度下降、承载力减小”的预期。
- 工程摩擦功率两种换算路径一致性已核对，consistency_ratio 约为 1.0，说明无量纲摩擦功率与量纲恢复关系自洽。

### 关键结论
- 热模型在当前实现中已经具备瞬态推进能力，内部通过上一时刻节点温度场递推，而不是只依赖标量温度。
- 对启动段或突加速度进入轨迹的场景，仅使用有效温度或平均温度不足以描述热场记忆；需要显式维护可递推的高维热状态。
- 后续热效应代理模型应采用状态空间式建模，而不是简单的静态映射模型。
- 若采用 GNN + Transformer 路线，GNN 更适合处理温度场的空间图结构，Transformer 更适合处理短时历史；时间步长更适合作为图级条件量或全局 token，而不是简单复制为普通节点特征。

### 风险与遗留问题
- 当前代理模型方案仍停留在架构设计阶段，尚未进入数据集生成、训练脚本实现和在线耦合验证阶段。
- 启动瞬态对热场初值敏感，若后续代理要覆盖启动段，需要保留多维热状态而非单一温度指标。
- 当前工作树中存在与本次主题无关的历史 notebook 和脚本改动，本记录仅覆盖今天完成的热效应、验证与代理建模相关内容。
- 当前待办列表中的气膜求解器相关事项尚未开展，包括 GasConfig、气体膜 Newton-skfem 求解器、GasBearing 系统类和对应测试。

### 明日计划
- 明确热场代理的数据组织格式，优先确定节点/边/全局特征字段。
- 设计面向转子时域耦合的状态缓存接口，明确代理输入输出张量格式。
- 视需要补充热场降阶或图状态编码方案，用于替代单标量温度状态。

### 相关文件
- docs/thermal_model.md
- ALB/thermal.py
- ALB/tool.py
- test/bearing/test_thermal_wrapper.py
- test/tool/test_bearing_film_nastran_export.py
- run/validation/validation_thermal_right_lower.py
- run/validation/outputs/validation_thermal_right_lower/validation_thermal_right_lower_mesh_convergence.csv
- ALB/nn.py
- run/train_alb_agent.py

---

## 2026-04-25 ~ 2026-04-27

### 今日目标
- 完成无量纲热耦合求解器的类层次重构，实现 NodimThermalHydroBearing / ThermalHydroBearing 分离。
- 统一物理符号命名，整理压力-温度耦合一致性检查文档。

### 代码与文档修改
- 新增 `ALB/nondim.py`，提供 `ThermalNondimScales` 用于温度、黏度、热源、热通量的量纲/无量纲双向转换。
- 热输入拆分为 `ThermalDimensionalConfig` / `ThermalNondimConfig`；`ThermalConfig.from_dict(...)` 保持为兼容工厂。
- `args_nodim=True` 对应无量纲热输入/配置路径；有量纲构造者应使用 `ThermalDimensionalConfig`.
- `delta_t_scale` 替代 `delta_t_mode` / `delta_t_char` 旧对，移除 `unit_system`。
- 无量纲热求解器目前仅支持稳态求解；瞬态抛出 `NotImplementedError`。
- `output(..., nodim=True)` 对于 `args_nodim=True` 配置是必需的；有量纲输出会抛出 `TypeError`。
- 新增 `NodimThermalHydroBearing(BaseCSystem)` 作为基类，`ThermalHydroBearing(NodimThermalHydroBearing)` 继承并负责 dim↔nondim 转换。
- `ThermalHydroBearing` 必须在每次 `input()` 改变膜几何后重建 `_thermal_grid`，否则能量方程使用过时的膜厚。
- 新增 `docs/pressure_temperature_consistency_review.md`：压力方程 (Reynolds) 与温度方程代码-公式一致性核对。
- 新增 `docs/symbol_conventions.md`：统一命名 `miu`/`miu0`/`lambda`/`lambda0`/`beta_nondim`/`theta_e`。
- 更新 `docs/thermal_model.md`：补充无量纲热求解器架构说明。

### 今日完成内容
- 完成 NodimThermalHydroBearing / ThermalHydroBearing 类拆分，镜像 FilmModel / NodimFilmModel 模式。
- 完成热配置的有量纲/无量纲拆分，`ThermalConfig.from_dict()` 作为兼容工厂。
- 完成压力-温度耦合公式一致性核对文档。
- 完成物理符号命名约定文档。

### 验证与结果
- `pytest test/test_nondim_thermal_field_case.py test/bearing/test_thermal_nondim_solver.py -q` 10 tests passed。
- 无量纲热求解器在 `delta_t_scale=25~30K`、`heat_partition=0~0.8` 范围内输出有限物理场。
- 零热分配工况温度上升为零，验证热源项推导正确。

### 关键结论
- 无量纲热求解器的类层次应镜像 `FilmModel` → `NodimFilmModel` 模式：基类处理无量纲，子类处理 dim↔nondim。
- `_thermal_grid` 不能复用构造时缓存的 `h_grid`，每次耦合求解需基于最新膜厚重建。
- 符号统一后不再存在 `u`/`u_ref`/`vx`/`vx_ref` 等历史别名。

### 风险与遗留问题
- 无量纲瞬态热求解器尚未实现，当前仅支持稳态。
- 部分历史脚本和 notebook 仍使用旧符号 `u`/`vx`，尚未全部迁移。

### 相关文件
- ALB/nondim.py（新增）
- ALB/thermal.py
- ALB/config.py
- docs/pressure_temperature_consistency_review.md（新增）
- docs/symbol_conventions.md（新增）
- docs/thermal_model.md
- test/bearing/test_thermal_nondim_solver.py
- test/test_nondim_thermal_field_case.py
- run/nondim_thermal_field_case.py

---

## 2026-04-28 ~ 2026-05-04

### 今日目标
- 完成热配置的 Pad-Centric 重构，将 thermal_enabled/thermal_config 从 ALBConfig 下沉到 FPBConfig。
- 完成无量纲接口系统的全面对接（孔口、膜、轴承、ALB、热耦合）。
- 完成轨道路径约束验证与热力时间项对比脚本。

### 代码与文档修改
- `ThermalConfig` 迁移至 `ALB/config.py`（`ALB/thermal.py` 重导出保持向后兼容）。
- `build_thermal_config(thermal_enabled, thermal_data, *, dt=None, transient_default=False)` 置于 `ALB.config`。
- `FPBConfig.thermal_config: Optional[ThermalConfig]`；`FPBConfig.thermal_enabled` 改为 property。
- `FPBConfig.from_dict` 接受 `thermal_config` (ThermalConfig | dict) 或旧 `thermal_enabled`+`thermal` dict。
- `ALBConfig` 不再持有 `thermal_enabled`/`thermal` 字段，均通过 property 转发至 `pad_config.thermal_config`。
- `NodimPadConfig.thermal_config` 镜像 `FPBConfig`（相同旧格式兼容）。
- `NodimALBConfig` 同样移除 `thermal_enabled`/`thermal`，改 property 转发。
- 有量纲/无量纲拆分改为基于类的策略：`NodimThermalHydroBearing` 基类 `_DEFAULT_ARGS_NODIM=True`，`ThermalHydroBearing` 覆盖为 `False`。
- 两个类均通过 `dataclasses.replace()` 将 `thermal_config.args_nodim` 强制对齐到类默认值。
- `output(*, nodim=None)` 默认使用类级别的 `_DEFAULT_OUTPUT_NODIM`。
- 新增 `NodimCSOrifice`、`NodimFilmModel`、`NodimNewtonFilm`、`NodimHydrostaticBearing` 等无量纲入口。
- `nodim_alb(config)` 禁止传入 `c/r/l/ps/rho/miu/w` 等有量纲尺度参数。
- 新增 `run/thermal_force_time_term_compare.py`：对比有/无热瞬态项的力迹线，区分 `no_thermal`（beta=0）和 `bare_hydro`（无热模型）。
- FPBConfig 默认间隙 `c = 80e-6 m`，轨道约束：`sqrt(x0²+y0²)+radius < c`。
- PAPER 配置中 `share.json5` 新增 Moog 伺服键 (`delay`, `tw`, `zeta`, `tp3`) 和热占位符 (`thermal_enabled` + 嵌套 `thermal` 对象)。
- 新增 `ALB/gas.py` 中 `GasFoilTextureCoupling`，新增 `run/paper_textured_foil_compare.py` 对比光滑/织构箔片轴承。

### 今日完成内容
- 完成热配置从 ALBConfig → FPBConfig 的下沉重构，热配置归一化到单个瓦块层级。
- 完成 NodimCSOrifice → NodimFilmModel → NodimHydrostaticBearing → NodimALB 的完整无量纲链路。
- 完成无量纲热耦合验证：单瓦块油膜力、热耦合 ALB 总油膜力的有量纲/无量纲对比。
- 完成热力时间项对比：`no_thermal` vs `bare_hydro` 双参考基准，导出末步场诊断。
- 完成轨道可行性验证与自动缩径。
- 完成气体箔片轴承织构对比脚本，smooth vs textured load 对比。

### 验证与结果
- `test/bearing/test_nodim_interfaces.py` 全部通过（压力、热耦合单瓦块、热耦合 ALB）。
- `test/bearing/test_thermal_nondim_solver.py` 全部通过。
- `test/bearing/test_thermal_wrapper.py` 全部通过（含 legacy pressure_backend 被拒测试）。
- `test/config/test_task.py` 全部通过（含 thermal_enabled 配置构建）。
- 织构箔片轴承：光滑负载 0.7773，织构负载 0.8629，相对增益 11.02%（分布#1，S_theta=0.33，S_z=1，深度 4μm，转速 1.4e5 rpm，e=0.2）。

### 关键结论
- Pad-Centric 热配置避免了 ALB 级别冗余，热启用/配置归属于瓦块本身。
- 无量纲链路覆盖已完整，从孔口 → 膜 → 轴承 → ALB → 热耦合全路径均支持。
- 类层次（基类=无量纲，子类=有量纲）比配置标志位 (`args_nodim`) 更清晰，`output()` 默认行为无需显式传参。
- 轨道计算前必须验证偏心距可行性，避免 `_input_rotoru` 因偏心>1 崩溃。

### 风险与遗留问题
- 部分历史脚本（`Run/`, `Task/` 子目录）仍使用旧 `u`/`vx` 符号，尚未迁移。
- 无量纲瞬态热求解器待实现。
- 气体箔片轴承仅完成稳态对比，瞬态/转子耦合待补充。

### 相关文件
- ALB/config.py
- ALB/thermal.py
- ALB/nondim.py
- ALB/bearing.py
- ALB/gas.py（新增）
- test/bearing/test_nodim_interfaces.py
- test/bearing/test_thermal_nondim_solver.py
- test/bearing/test_thermal_wrapper.py
- test/config/test_task.py
- run/thermal_force_time_term_compare.py（新增）
- run/paper_textured_foil_compare.py（新增）
- run/nondim_thermal_field_case.py
- task/PAPER/config/share.json5

---

## 2026-05-05

### 今日目标
- 运行项目全部测试，修复所有失败用例，确保测试套件绿色。

### 代码与文档修改
- **`ALB/rotor.py`**：将 `rotor0()` 内部嵌套类 `ShaftElement` 提取为模块级类，支持 `alpha`/`beta` 阻尼参数；同步更新 `rotor0()` 内部使用。
- **`test/control/LQG/test_alblqg.py`**：将模块级立即执行的 `test_lqg()` 调用包裹在 `if __name__ == '__main__':` 中，避免 pytest 收集阶段触发 `FileNotFoundError`（硬编码路径 `G:\...\elements.xls`）。
- **`test/couple/test_add_gravity.py`**：修复 `from ALB.rotor import ShaftElement` 导入错误（此前为局部类），并将模块级执行代码用 `if __name__ == '__main__':` 包裹。
- **`run/nondim_thermal_field_case.py`**：修复 `solve_nondim_thermal_field_case()` 中有量纲/无量纲类不匹配——当 `args_nodim=True` 时改用 `NodimThermalHydroBearing` + `NodimHydrostaticBearing`。

### 今日完成内容
- 修复 2 个 pytest 收集错误（test_alblqg, test_add_gravity）。
- 修复 1 个导入错误（ShaftElement 不可导入）。
- 修复 4 个无量纲热场用例的 TypeError（类层次不匹配）。
- 测试套件：71 passed, 0 failed, 5 subtests passed。

### 验证与结果
- `pytest test/ -v` → **71 passed, 0 failed**，全部通过，耗时 82s。
- 通过的测试涵盖：轴承（气膜、静压、可倾瓦、热耦合、无量纲接口、验证精度）、配置（校验、Paper 任务构建）、控制（LQG 已跳过）、热力时间项对比、热 KC 辨识、Nastran 网格导出。

### 关键结论
- 测试文件中不应包含模块级立即执行的副作用代码（如调 `test_lqg()`、画图、写文件），需用 `if __name__ == '__main__':` 包裹。
- 有量纲/无量纲类层次（`ThermalHydroBearing` / `NodimThermalHydroBearing`）要求调用方在构造时选择正确的类，而非依赖配置标志位自动分发。

### 风险与遗留问题
- `test/control/LQG/test_alblqg.py` 被改为仅在 `__main__` 下运行（原有逻辑依赖外部文件），该文件不再是有效的 pytest 用例。
- 5 个 warnings（4 个 FigureCanvasAgg 非交互警告 + 1 个 skfuzzy 除零警告）均为非关键，暂不处理。
- 部分历史目录（`Run/`, `Task/`, `TEST/`, `Learning_note/`）中存在大量未纳入测试套件的脚本，不在本次覆盖范围。

### 相关文件
- ALB/rotor.py
- test/control/LQG/test_alblqg.py
- test/couple/test_add_gravity.py
- run/nondim_thermal_field_case.py

---

## 2026-05-05 ~ 2026-05-06

### 今日目标
- 构建 VS Code 自定义 Agent 体系，实现 Plan→Fix→Review→Test 自动化闭环。
- 完成代码注释英文化（gas.py）与 fuzzy PID 除零 bug 修复。
- 开发轴承分析 GUI 第一阶段（静态/动态矩阵）。
- 更新项目知识库与文档。

### 代码与文档修改
- **`.github/agents/`**（新增目录，8 个 agent）：
  - `test-debug.agent.md`（flash）：pytest 执行与失败诊断
  - `git-helper.agent.md`（flash）：git commit / branch / diff 操作
  - `code-review.agent.md`（flash）：代码质量审查，含项目特定陷阱检查
  - `doc-generator.agent.md`（pro）：Sphinx 风格英文 docstring 生成，强制 ALL COMMENTS IN ENGLISH
  - `task-planner.agent.md`（flash）：需求分解与结构化规划
  - `code-fixer.agent.md`（pro）：精确代码修改与语法验证
  - `loop-orchestrator.agent.md`（pro）：自动化 Plan→Fix→Review→Test 闭环迭代（最多 3 轮）
  - `AskU.agent.md`：交互式 ask-before-execute 助手（预置）
- **`ALB/controller.py`** L246：FuzzyPID 范围步长计算增加 `len(x) > 1` 守卫，消除除零 RuntimeWarning。
- **`ALB/gas.py`**：全部 14 个方法 docstring 从中文转换为英文 Sphinx 风格。
- **`test/gui_bearing.py`**（新增）：PySide6 轴承分析 GUI 第一阶段。
  - 4 个渐进式参数面板（Geometry → Operating → Fluid → Solver）
  - 静态分析：承载力 (Fx, Fy, |F|) + 摩擦力 + 压力场 pcolormesh
  - 动态分析：刚度 K (2×2) 与阻尼 C (2×2) 矩阵
  - matplotlib FigureCanvas 嵌入压力场与力矢量图
  - QThread 后台计算避免 UI 冻结
- **`test/gomoku_game.py`**（新增）：五子棋 GUI 游戏，作为闭环自动化流程演示案例。
- **`/memories/repo/comment_conventions.md`**（新增）：英文 Sphinx docstring 标准与符号命名约定。

### 今日完成内容
- 完成 8 个 VS Code 自定义 Agent 的创建与配置，覆盖开发全流程。
- DocGenerator 从 flash（14% 覆盖率）升级为 pro（100% 覆盖率），强制英文注释。
- CodeReview + TestDebug 在 controller.py fuzzy PID 除零修复上完成联合验证，消除 2 个 warning。
- 完成完整闭环演示：通过 Plan→Fix→Review→Test 构建五子棋 GUI 游戏。
- 修复 gas.py 全部方法注释为英文 Sphinx 风格。
- 完成轴承分析 GUI 第一阶段，支持静态力/矩阵与动态刚度/阻尼计算。
- GUI 审查发现并修复 4 个问题：w=0 守卫、worker traceback 捕获、摩擦力单位标签、类型守卫。

### 验证与结果
- DocGenerator pro 模式对 gas.py 实现 100% 方法 docstring 覆盖率（14/14），全部为英文。
- CodeReview 对 controller.py 检测到 fuzzy PID 除零风险，修复后 RuntimeWarning 消失。
- 五子棋 GUI 通过完整 Plan→Fix→Review→Test 闭环验证。
- 轴承分析 GUI 可正常加载、计算并显示压力场云图与力矢量图。

### 关键结论
- Agent 模式标签（flash vs pro）直接影响工具可用性与执行深度：flash 轻量快速适合简单任务，pro 适合需要多轮文件修改的复杂任务。
- 闭环编排器（loop-orchestrator）可在 3 轮内自动完成 Plan→Fix→Review→Test 迭代，显著减少人工干预。
- 项目特定陷阱检查（如 FuzzyPID 除零、无量纲/有量纲类层次不匹配）应编码到 code-review agent 的检查规则中。
- GUI 中 QThread + matplotlib FigureCanvas 嵌入是可行的实时可视化方案，但需注意线程安全与异常捕获。

### 风险与遗留问题
- Agent 体系尚未与 CI/CD 流水线集成，当前仅支持 VS Code 内手动触发。
- 轴承分析 GUI 第二阶段（瞬态轨道、热耦合、伺服阀动态）尚未开发。
- 部分 agent（task-planner, git-helper）尚未在真实场景中充分验证。
- `/memories/repo/` 知识库条目仍需持续维护与更新。

### 明日计划
- 轴承分析 GUI 第二阶段：瞬态轨道轨迹绘制与热耦合开关。
- Agent 体系与 pytest 套件深度集成，实现代码变更自动触发审查与测试。
- 补充 agent 使用文档与项目 README 更新。

### 相关文件
- .github/agents/*.agent.md（8 个新增）
- ALB/controller.py
- ALB/gas.py
- test/gui_bearing.py（新增）
- test/gomoku_game.py（新增）
- /memories/repo/comment_conventions.md（新增）

## 2026-05-09

### 今日目标
- 维护 `G:/ALB_PROJECTS` split workspace 的稳定文档，压缩过时远程训练信息。
- 明确 `ALB.remote` 与 `SURROGATE_TRAIN/run/remote` 的职责边界。
- 记录当前 force3 GELU minmax patience-500 远程训练和默认监控行为。

### 代码与文档修改
- `ALB_MAIN/docs/file_classification.md`：补充 `ALB/remote/`、`test/remote/` 和 remote reference 文件分类，移除旧大小写目录迁移描述。
- `SURROGATE_TRAIN/docs/file_classification.md`：从旧 `RE_ALB`/核心包分类改为训练项目专用分类。
- `SURROGATE_TRAIN/docs/albnn_training_info.md`：更新 force5 minmax 已完成指标、force3 当前训练状态和本地 monitor 日志路径。
- `SURROGATE_TRAIN/README.md`：补充 remote wrapper、queue config 和 queue log 的项目职责说明。
- `SURROGATE_TRAIN/TODO.md`：保留 pending 状态说明；`SURROGATE_TRAIN/docs/PLAN.md` 在当日仍作为 historical 计划检查，后续于 2026-05-10 确认删除。

### 今日完成内容
- 完成远程工具职责沉淀：核心实现位于 `ALB_MAIN/ALB/remote`，训练项目只保留兼容 wrapper 和实验 JSON 配置。
- force5 minmax 训练状态由“running”更新为 completed，并补充独立验证指标。
- force3 GELU minmax patience-500 训练记录为维护时仍在运行，且已有本地监控日志。
- 未移动、删除或归档任何训练数据、模型、日志或配置文件。

### 验证与结果
- force3 状态查询时间：`2026-05-09 20:15 +08:00`。
- 当前状态：`running`，epoch `2500/30000`，elapsed `17.7` min，Python PID `1568`。
- 本地 monitor 日志：
  `SURROGATE_TRAIN/outputs/queue_logs/force3_gelu_minmax_p500_monitor_20260509_200142.stdout.log`。

### 关键结论
- 后续远程 ALBNN 训练默认应启动本地监控；优先使用 JSON queue wrapper。
- `run/remote/configs/*.json` 属于实验参数，应留在 `SURROGATE_TRAIN`，不要搬入 `ALB_MAIN`。
- 旧计划内容可通过审计报告和每日摘要保留证据链；`SURROGATE_TRAIN/docs/PLAN.md` 文件本身后续于 2026-05-10 确认删除。

### 风险与遗留问题
- `daily_summary_log.md` 仍包含早期历史内容和中文模板，本次只做文末追加/替换，没有重排历史记录。
- force3 训练仍在运行，最终指标需要训练完成后再次写入 `albnn_training_info.md`。

### 明日计划
- force3 训练完成后同步最终 `validation_summary.json`、`metadata.json` 和 queue monitor 摘要。
- 继续检查旧计划与实际训练状态是否还有冲突项。

### 相关文件
- docs/file_classification.md
- ../SURROGATE_TRAIN/docs/file_classification.md
- ../SURROGATE_TRAIN/docs/albnn_training_info.md
- ../SURROGATE_TRAIN/README.md
- ../SURROGATE_TRAIN/TODO.md

## 2026-05-10

### 日常文档维护
- Scheduled maintenance pass for split workspace `G:/ALB_PROJECTS`.
- Detailed report: `ALB_MAIN/docs/daily_maintenance/doc_maintenance_audit_20260510.md`.
- Stable docs updated: added current split ownership notes to `ARTIFACTS_ARCHIVE/docs/file_classification.md`, `DATA_POSTPROCESS/docs/file_classification.md`, `PARAM_SCAN/docs/file_classification.md`, and `VALIDATION/docs/file_classification.md`.
- Human confirmations resolved: delete `ARTIFACTS_ARCHIVE/test/couple/logs/film-5305.log`; keep `SURROGATE_TRAIN/docs/PLAN.md` deleted; retain only one day of scheduler logs under `ALB_MAIN/docs/daily_maintenance/logs`; archive `SURROGATE_TRAIN/outputs/queue_logs` with their corresponding model artifacts after training ends.
- Applied cleanup: removed `film-5305.log` and the 2026-05-09 scheduler run logs under `ALB_MAIN/docs/daily_maintenance/logs`.
- No source code, remote SSH, training, sampling, commits, moves, renames, or artifact archives were performed.

## 2026-05-11

### 文档维护
- Manual maintenance pass for split workspace `G:/ALB_PROJECTS`.
- Detailed report: `ALB_MAIN/docs/daily_maintenance/doc_maintenance_audit_20260511.md`.
- New stable ALB package orientation: `ALB_MAIN/docs/alb_package_overview.md`.
- `ALB_MAIN/AGENTS.md` now points agents to the package overview before public
  API or module-boundary changes.
- `SURROGATE_TRAIN` docs now record local packaged-model testing with
  `run/analysis/compare_packaged_albnn_force_kc.py`.
- Local model test summary: 12 complete local models tested from
  `SURROGATE_TRAIN/models`; 1 passed all downstream shell/core criteria and 11
  failed the configured force-comparison thresholds.
- Passing model:
  `valid40000_aug_v2_standard_384_384_192_96_lr7em04_isolated`.
- Aggregate model-test report:
  `SURROGATE_TRAIN/outputs/analysis_logs/compare_packaged_albnn_force_kc_20260511/aggregate_summary.csv`.
- Local incomplete model cleanup already removed three partial directories that
  had `best_albnn.pth` but lacked `metadata.json` and `validation_summary.json`;
  remote model directories were not deleted.
- No code behavior, training, sampling, remote launch, commit, or artifact
  archive was performed during this documentation maintenance pass.

### 计划日常文档维护
- Scheduled pass refreshed
  `ALB_MAIN/docs/daily_maintenance/doc_maintenance_audit_20260511.md`.
- Stable docs changed: `SURROGATE_TRAIN/TODO.md` and
  `SURROGATE_TRAIN/docs/file_classification.md` now avoid describing the old
  force3 queue as the active workflow.
- Local evidence was checked; realtime process and loss details remain in
  `SURROGATE_TRAIN/docs/current_runtime_status.md` and the audit report.
- Remote 100000-sample monitor evidence was ambiguous after the last running
  snapshot, so the uncertainty is kept in the audit report for human review.
- Old-file candidates for next-day confirmation: same-day scheduler logs under
  `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260511_*`.
- No source code, remote SSH, training, sampling, commits, deletes, moves,
  renames, or artifact archives were performed.

### 交互式文档维护跟进
- Refreshed the live-status buffer
  `SURROGATE_TRAIN/docs/current_runtime_status.md` from local process/log
  evidence.
- Kept the unresolved remote monitor state in the live buffer and
  `ALB_MAIN/docs/daily_maintenance/doc_maintenance_audit_20260511.md`, not in
  stable manuals or the ALBNN brief.
- No source code, remote SSH, training, sampling, deletes, moves, renames, or
  artifact archives were performed.

## 2026-05-12

### 计划日常文档维护
- Scheduled pass for split workspace `G:/ALB_PROJECTS`.
- Detailed report:
  `ALB_MAIN/docs/daily_maintenance/doc_maintenance_audit_20260512.md`.
- Local evidence was folded into role-owned docs:
  `SURROGATE_TRAIN/docs/current_runtime_status.md` now records queue PID
  `67356` and current GELU 256 PID `82848`;
  `SURROGATE_TRAIN/docs/albnn_training_log.md` records completed polar29 GELU
  512 and polar15 sin 256 validation summaries.
- Stable manuals and briefs were left unchanged; remote 100000-sample status
  remains ambiguous until a one-shot monitor or SSH check confirms it.
- Old-file candidates for next-day confirmation are generated daily-maintenance
  logs under `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260511_*`
  and `codex_daily_doc_maintenance_20260512_090001.*`; no non-generated
  source/doc cleanup candidates were found.
- No source code, remote SSH, training, sampling, commits, deletes, moves,
  renames, or artifact archives were performed.
