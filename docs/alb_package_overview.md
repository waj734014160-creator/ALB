# ALB 0.4 包概览

## 文档角色

- 角色：稳定包概览。
- 目的：说明 `ALB` 的公共 API、模块归属和安装制品边界。
- 允许更新：公共 API、模块归属和包边界。
- 禁止更新：实验运行状态、训练进度和单次验收日志。
- 更新时机：公共 API、模块归属或 wheel 边界变化时。
- 事实来源：`ALB/__init__.py`、`ALB/api/`、`pyproject.toml`。

## 包定位

`re-alb` 是轴承物理、主动润滑控制、转子耦合和 ALBNN 推理的稳定 Python
包，导入名为 `ALB`，最低 Python 版本为 3.10。0.4 是不兼容版本：wheel
只包含当前实现，不包含旧工厂、旧别名、`Signal`、legacy adapter、旧配置
解析器或迁移 CLI。

普通用户只从包根导入：

```python
import ALB

config = ALB.load_bearing_config("bearing.json5")
bearing = ALB.build_bearing(config)
result = bearing.calculate(displacement=(0.0, 0.0), time=0.0)
```

完整的类、函数、输入、输出和示例见
[`docs/api/public_api_reference.md`](api/public_api_reference.md)。该参考直接从
`ALB.__all__` 和运行时签名生成，并通过 `--check` 与 pytest 检查是否跟随源码
更新；维护流程见[文档贡献流程](site/contributing/docs.md)。`ALB.control`、
`ALB.dynamics` 和 `ALB.surrogate` 的显式高级接口分别见
[Control](api/namespaces/control.md)、[Dynamics](api/namespaces/dynamics.md) 和
[Surrogate](api/namespaces/surrogate.md)。生成器静态读取各 namespace 的字面量
`_EXPORTS`，不会导入可选 backend 或扩大公开边界。

根 namespace 分为五组：

- 版本元数据：`__version__` 表示当前安装包版本，`SCHEMA_VERSION` 表示
  bearing/simulation JSON5 配置契约版本；二者独立演进。
- 配置与构建：`BearingConfig`、`SimulationConfig`、`load_bearing_config()`、
  `build_bearing()`、`bearing_from_file()`、`build_simulation()` 和
  `simulation_from_file()`。
- 用户对象：`Bearing`、`BearingAnalysis`、`RotorBearingSimulation`、
  `BearingMount`、`HistoryPolicy`、`EllipseTrajectory` 和
  `EquilibriumOptions`；需要独立持有静平衡模型时可直接构造
  `EquilibriumSolver(bearing)`。
- 不可变结果：`BearingResult`、`AnalysisResult` 和 `SimulationResult`。
- 稳定错误：`ALBError`、`ConfigurationError`、`BuildError`、
  `CalculationError` 和 `SimulationError`。

## 模块图

```text
ALB.contracts / ALB.core
        ↓
ALB.config   ALB.physics   ALB.control   ALB.dynamics   ALB.surrogate
        \          |             |             |             /
                     ALB.systems.alb
                            ↓
                         ALB.api
                            ↓
                         用户代码

ALB.infrastructure 只承载持久化、记录和远程等副作用边界
```

- `ALB.api` 是 0.4 用户 facade，负责严格配置、构建、分析、仿真、结果和稳定异常。
- `ALB.contracts` 保存严格 DTO、单位、结果快照和内部领域协议。
- `ALB.physics` 保存液膜、气膜、热、节流器和 `MultiPad` 数值实现。
- `ALB.control` 保存 PID、FuzzyPID、阀和高级控制实现。
- `ALB.dynamics` 保存转子、挂载 binding 和提交型耦合 runtime。
- `ALB.surrogate` 保存 v0.4 模型包、NPZ scaler、推理 runtime 和训练公共组件。
- `ALB.systems.alb` 只负责主动润滑轴承内部装配，不是普通用户入口。
- `ALB.infrastructure` 保存 artifact writer、recorder、observer 和远程运行工具。

## 轴承族

`BearingConfig.family` 只接受：

- `liquid_film`
- `active_lubricated`
- `gas_film`
- `multi_pad`
- `surrogate`

`liquid_film` 不再区分动压、静压或混合类名。`restrictors` 为空时求解普通
液膜；非空时由构建器在构造期装配节流耦合。所有 facade 对象构造完成即可
计算，不公开 `init()`；新会话使用 `Bearing.reset()`。

## 配置与结果

0.4 JSON5 文档固定使用 `schema_version: "0.4.0"`、`kind`、可选
`includes` 和 `spec`。0.4.5 可通过根入口 `ALB.SCHEMA_VERSION` 读取该契约版本，
无需从内部配置模块导入或把它与 `ALB.__version__` 混同。`BearingConfig` 不可变，`with_overrides()` 与
`sweep()` 每次都重新执行完整校验。

`Bearing.calculate()` 不累计历史，只更新只读 `latest_result`。分析服务用
独立 runtime，不污染当前轴承状态。转子轴承仿真默认保留全部已提交步骤；
只有显式 `HistoryPolicy` 才能降采样或使用 ring buffer。

量纲主动润滑轴承可成对设置 `film.mesh_type` 与 `film.element_order`，显式选择
三角 P1/P2 或四边形 Q1/Q2 压力-热同网格离散。该模式当前限定为非周期单瓦、
`skfem_newton` 和稳态直接热耦合，并统一采用 8 阶积分；省略字段时继续使用
原有数值路径。完整约束和结果元数据见
[`docs/api/bearing_config_reference.md`](api/bearing_config_reference.md)。

主动轴承的 `restrictors.flow_projection` 独立选择供油孔耦合：缺省
`nearest_node` 保持统一最近节点路径，`element_shape` 则在压力和温度空间按
孔所在单元的原生形函数守恒分配。该选择贯通量纲/无量纲装配和主动轴承解析
线性化；普通 `liquid_film` 节流孔不接受此字段。

0.4.5 的主动轴承公开阀配置接受 `second_order`、`static` 和
`transfer_function`。二阶阀直接使用 `natural_frequency_hz`、
`damping_ratio` 和可选 `delay`；静态阀是无参数、无记忆的单位增益模型；
传递函数阀直接使用按连续时间 `s` 降幂排列的 `numerator` / `denominator`
多项式系数。

0.4.1 的静平衡保留专用阻尼 Newton、冻结 Jacobian 和固定刚度回退算法；
动态系数由同一旋转椭圆自动生成正反涡动并使用复数识别；谐波线性化使用压力
方程导数与节流耦合，不再以轨迹最小二乘拟合代替。谐波接口当前只支持已有
数值参考的量纲液膜和三节点 CSOrifice 主动润滑轴承。可倾瓦轴承不属于
0.4.1 安装包能力。

0.4.2 不改变上述算法。动态系数入口只接受可表示目标频率的均匀 FFT 网格和
可逆的正反涡动位移矩阵；静平衡拒绝无法使用相对残差定义的精确零载荷。
`RotorProtocol.dt` 是显式能力，每个 mount 按 unit adapter 转换得到自己的
bearing-local 步长，构建器在物理 runtime 创建前递归检查 `MultiPad` 及物化
控制器、阀和热模型。

0.4.3 继续保持上述有效数值路径不变。simulation 只接受 dimensional rotor，
并在构建配置时验证 node 输出包含有限、形状明确的 `uxy/uxyt`。静平衡相对
残差使用防下溢/溢出的模长门禁，但普通量级继续使用原二范数结果。JSON5
拒绝重复键及字符串、布尔或浮点数到整数的静默转换；surrogate fixed spool
与 external spool 共用 `[-1, 1]` 归一化边界。

所有公开结果都是不可变对象，数组设为只读，并提供 `write(path)`。计算失败
通过稳定异常携带密封 failure snapshot。仿真遇到提交后 recorder/observer
异常时不会重算物理步骤；partial result 包含已真实提交的步骤，并分别报告
物理完成、历史完成和 post-commit 完整性。`disk_stream` 通过同目录临时文件、
flush/fsync 和原子替换发布快照及 manifest。每个
`RotorBearingSimulation` 只能调用一次 `run()`；成功或失败后再次运行必须
重新构建 simulation，避免恢复操作重放物理步骤。

## ALBNN 制品

0.4 运行时只接受 `alb.surrogate-package.v0.4`：`weights.pt` 使用
`weights_only=True` 加载，输入/输出 scaler 为 NPZ，manifest、metadata 和
SHA-256 摘要必须完整匹配。旧 package 与 pickle scaler 只能在升级前由
`tools/migrations/` 中不安装的工具显式转换。

## 安装与验证

```bash
python -m pip install -e ".[all]"
python -m pytest -q
python tools/validation/run_layered_mypy.py
python tools/docs/generate_public_api_reference.py --check
```

0.4.0 发布功能以 `tools/validation/release_feature_manifest_0_4.json` 和
`docs/migrations/0.4.0_test_map.json` 为历史证据；0.4.1 数值一致性补丁以
`tools/validation/release_feature_manifest_0_4_1.json` 和
`docs/migrations/0.4.1_test_map.json` 为历史数值证据；0.4.2 审阅修复以
`tools/validation/release_feature_manifest_0_4_2.json` 和
`docs/migrations/0.4.2_test_map.json` 为准。0.4.3 的有效路径参考为
`refs/alb_0_4_3_guard_reference_v1.json/.npz`；正式发布门禁尚未生成。0.3 的
F01-F66 manifest 仅保留为历史证据。
