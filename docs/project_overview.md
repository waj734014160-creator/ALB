# ALB 项目说明

## 1. 项目简介

ALB 是一个面向气液润滑轴承场景的计算与分析项目，核心覆盖以下能力：

- 静态/动态压力场求解
- 多瓦块轴承建模与耦合计算
- 节流孔与供油系统建模
- 热-流体耦合与粘温效应分析
- 对比脚本与实验性验证脚本

项目采用 Python 开发，主体代码在 ALB 目录中，运行脚本与测试代码分别放在 run 与 test 目录。

---

## 2. 目录结构

- ALB
  - 核心求解与模型代码（如 film.py, bearing.py, thermal.py, orifice.py）
- .github/agents/
  - VS Code 自定义 Agent 定义文件（代码审查、文档生成、测试调试、任务规划等 8 个 Agent）
- run
  - 示例脚本与对比脚本（如 compare_orifice_methods.py, compare_diffusion.py）
- test
  - 单元测试、回归测试与实验性测试
  - gui_bearing.py：PySide6 轴承分析 GUI（静态承载力/刚度/阻尼矩阵 + 压力场可视化）
- docs
  - 文档（当前文件与热模型文档）

---

## 3. 核心模块说明

- ALB/film.py
  - 油膜方程求解主逻辑（Newton/GS 等）
  - 边界条件处理（包含 coe 连续边界）
- ALB/bearing.py
  - 单瓦块与多瓦块轴承对象封装
- ALB/orifice.py
  - 节流孔/供油孔模型与流量耦合
- ALB/thermal.py
  - 热-流体耦合求解
  - 点源供油孔热源处理
- ALB/config.py
  - 配置对象定义（HydConfig, FPBConfig 等）
- .github/agents/
  - VS Code 自定义 Agent（共 8 个），覆盖 Plan→Fix→Review→Test 自动化闭环：
  - `doc-generator.agent.md`（pro）：Sphinx 英文 docstring 生成
  - `code-review.agent.md`（flash）：代码质量审查 + 项目特定陷阱检查
  - `code-fixer.agent.md`（pro）：精确代码修改与语法验证
  - `test-debug.agent.md`（flash）：pytest 执行与失败诊断
  - `task-planner.agent.md`（flash）：需求分解与结构化规划
  - `git-helper.agent.md`（flash）：git commit / branch / diff
  - `loop-orchestrator.agent.md`（pro）：Plan→Fix→Review→Test 闭环迭代
  - `AskU.agent.md`：交互式 ask-before-execute 助手
- test/gui_bearing.py
  - PySide6 轴承分析 GUI，支持静态承载力/摩擦力和动态刚度/阻尼矩阵计算，内嵌 matplotlib 压力场可视化，QThread 后台计算

---

## 4. 环境与安装

### 4.1 Python 版本

- 建议 Python 3.9+
- 当前项目元信息中要求 >= 3.9

### 4.2 安装方式

在项目根目录执行：

pip install -e .

如果你使用 Conda 环境，建议先激活目标环境再执行安装。

---

## 5. 快速运行

### 5.1 运行主要对比脚本

在项目根目录执行：

python run/compare_orifice_methods.py

该脚本会输出多个对比图到：

run/_compare_orifice/

典型输出包含：

- 点源温度场
- 网格收敛对比
- 压力场有槽/无槽对比
- 右下偏向下温度随偏心率变化

### 5.2 运行扩散项对比脚本

python run/compare_diffusion.py

输出目录：

run/_compare_diffusion/

### 5.3 无量纲 ALB 入口

无量纲接口用于跳过物理尺寸到无量纲参数的转换，直接输入压力膜和 CS 节流器的无量纲系数：

- `NodimCSOrifice(position, cq0, cq1, cq2)`：CS 节流器无量纲核心类，旧 `CSOrifice` 仍保留量纲参数入口并继承它。
- `NodimHydrostaticBearing(lambda_value, lr, x0, lx, lz, ...)`：单瓦块无量纲构造入口，`x0` 和 `lx` 单位为 °。
- `nodim_alb(lambda_value, lr, lx, lz, position, cq0, cq1, cq2, ...)`：四瓦块 ALB 无量纲装配入口，`lx` 和 `bias` 单位为 °。
- 热耦合可传入 `ThermalConfig(args_nodim=True, ...)`，由 `NodimThermalHydroBearing` 包装无量纲压力模型。

最小示例：

```python
import numpy as np

from ALB import ALBConfig, PIDConfig, nodim_alb

cfg = ALBConfig()
cfg.servo = "static"
cfg.controller_config = PIDConfig()

alb = nodim_alb(
  lambda_value=1.2,
  lr=1.0,
  lx=90.0,
  lz=2.0,
  nx=21,
  nz=11,
  position=np.array([[0.5, 0.5]]),
  cq0=0.2,
  cq1=1.0,
  cq2=0.1,
  alb_config=cfg,
  coe=False,
)

alb.init()
alb.input(np.array([0.05, 0.0]), np.array([0.0, 0.0]), t=0.0, nodim=True)
result = alb.output(nodim=True)
```

---

## 6. 测试与验证

### 6.1 热模型回归测试（推荐）

python -m pytest test/bearing/test_thermal_wrapper.py -v

或直接运行：

run_test.bat

### 6.2 连续边界专项测试（单瓦块 360°）

python -m pytest test/bearing/test_coe_boundary_fullpad.py -v

该测试用于验证：

- 单瓦块全覆盖时左右边界是否正确连接
- 连续边界下压力场左右缝合误差是否足够小

---

## 7. 常见工作流

### 7.1 修改求解器后建议验证顺序

1. 先跑专项测试（修改点对应测试）
2. 再跑热模型回归测试
3. 最后跑 run/compare_orifice_methods.py 观察图像与趋势是否合理

### 7.2 关注的稳定性指标

- final_iter 是否明显接近 max_iter
- 是否出现 iter of filmsystem is max
- 是否出现 NaN/Inf 压力或温度
- 连续边界左右缝合误差是否可接受

---

## 8. 已有文档

- docs/thermal_model.md
  - 热模型、耦合流程与参数说明
- docs/symbol_conventions.md
  - 物理符号命名约定、初始量后缀规则与供油孔 flow_info 接口说明
- docs/daily_summary_log.md
  - 每日开发总结与验证记录（按日期持续追加）
- docs/pressure_temperature_consistency_review.md
  - 压力方程 (Reynolds) 与温度方程代码-公式一致性核对
- /memories/repo/comment_conventions.md
  - 英文 Sphinx docstring 标准与符号命名约定
- /memories/repo/（其他）
  - alb_config_system.md、alb_nondim_interfaces.md、gas_foil_bearing.md、thermal_nondim_solver.md、thermal_orbit_constraints.md

---

## 9. 备注

- 本项目包含部分实验性脚本与历史测试，建议优先使用 test/bearing/test_thermal_wrapper.py 与 run 下对比脚本进行主流程验证。
- 若需扩展文档，建议按主题拆分（边界条件、节流孔模型、热耦合、调参与收敛诊断）。
