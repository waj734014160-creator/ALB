# ALB_MAIN 当前状态

## 文档角色

- 角色：ALB_MAIN 项目当前状况记录。
- 目的：集中记录 ALB_MAIN 当前开发阶段、最近确认的基线、当前验证状态、已知问题和下一步，使接手者能够快速恢复上下文。
- 允许更新：当前分支和基线、正在进行的项目级工作、已经实际执行的验证及结果、当前风险或阻塞、近期下一步、相关证据指针。
- 禁止更新：SURROGATE_TRAIN 的训练/采样实时进度、论文任务实时状态、完整历史流水、原始日志正文、稳定 API 手册和未经验证的结论。
- 更新节奏：ALB_MAIN 的开发阶段、工作重点、验证结论、风险或下一步发生实质变化时更新；旧状态应压缩为结论，不在本文持续堆叠时间线。
- 事实来源 / 相关文档：
  `AGENTS.md`,
  `docs/daily_maintenance/daily_doc_update_index.md`,
  `docs/project_overview.md`,
  `docs/interface_architecture.md`,
  `docs/alb_package_overview.md`,
  `docs/run_index.md`,
  Git 提交和与当前工作直接相关的测试结果。

本文只记录 `ALB_MAIN` 自身的项目状态。ALBNN 训练、采样、远程队列和 monitor 的实时状态属于 `../SURROGATE_TRAIN/docs/current_runtime_status.md`；论文计算的实时状态属于 `F:/BaiduSyncdisk/博士论文/PAPER_WORK/docs/current_task_status.md`。

## 当前快照

- 快照日期：2026-07-21。
- 当前分支：`codex/full-repo-refactor`。
- 最近提交：`721a3902063a7d8427488bf23b6446cdb92942dd`（`refactor: define ALB component interfaces`）。
- 当前阶段：首轮 ALB package 接口与模块分类重构已经完成、验证并提交；现已启动 `0.2.0` 全仓库破坏式、命名空间优先重构，正在固定生产源码改动前的基线。
- 当前提交相对行为参考提交 `597f3fe` 新增 38 个文件变更，共 `1463 insertions / 440 deletions`。
- 当前没有未提交的生产源码重构。工作树仍包含本轮启动前已有或不属于本轮范围的两张热图、`.codex`、LQG 脚本和输出；这些文件不得随全仓库重构自动清理或混入后续提交。

## 当前工作重点

1. 在任何生产源码改动前建立 `refs/full_repo_refactor_v1/`，冻结依赖、随机种子、输入输出、残差历史和关键时序；现有 v1 参考不得覆盖。
2. `0.2.0` 采用破坏式、命名空间优先的新 API；顶层 `ALB.__init__` 只保留版本、基础单位/时步/收敛 DTO 和计算块协议，最终删除旧平铺 facade。
3. 生产实现按 `contracts/core/config/physics/control/dynamics/surrogate/systems/infrastructure/workflows` 分层，一次只迁移一个领域，不同时改变方程、矩阵装配顺序或迭代准则。
4. `SURROGATE_TRAIN` 和 `PAPER_WORK` 只做只读迁移审计；发现数值或物理问题只报告，修正必须另建提交和 v2 参考。

## 本轮已完成

- 提取 `ComponentBase`、`BearingComponentBase`、`BaseSimpleModel`、`BaseSystem`、`BaseCSystem`、`Signal`、`TimeIter`、`TimeIterDt` 和共用验证 helper。
- 定义 `BearingProtocol`、`BearingCoefficientProtocol`、`RotorProtocol`、`ControllerProtocol`、`ServoValveProtocol`、`TimeGridProtocol`、`NotifierProtocol`、`PersistableProtocol` 和 `ConvergenceStatus`。
- 新增 `BearingDecoratorBase` 和 `LegacyBearingAdapter`；热轴承 wrapper 已迁移到 decorator 模板。
- `ALBHarmonicLinear` 已迁移到标准轴承基类，原 `K/C/G_xv` 和耦合时域行为保持参考一致。
- `RsRotorBearingCouple` 增加有量纲边界与二维有限力检查，同时兼容尚未声明单位制的旧第三方轴承。
- `MultiPad` 增加空集合、单位制和节点一致性检查，不再原位修改首个 pad 的输出字典，并允许缺省 `friction`。
- `CsoArgs` 统一由 `ALB.config` 定义；`ALB.orifice` 只保留兼容 re-export。
- `FilmSystem` 已解除对邮件实现的直接依赖，异常通知改为可选 `NotifierProtocol` 注入。
- `limit_signal` 的唯一实现迁至 `ALB.core.validation`；旧 `ALB.servovalve.limit_signal` 仍可导入。
- `ALB.__all__` 由唯一 lazy export map 生成，消除手工列表漂移。

## 已确认基线

- 重构前源码基线：commit `24ea190becf19c6f0e33e3c05686c0052dfdbedd`，tag `pre-interface-refactor-20260720`。
- 行为参考基线：commit `597f3fe`，tag `pre-interface-refactor-refs-20260720`。
- 精确回归资产：`refs/interface_contract_reference_v1.json`、`refs/interface_contract_reference_v1.npz`。
- 详细架构、兼容策略和迁移顺序以 `docs/interface_architecture.md` 为准。

## 当前验证状态

2026-07-20 已执行：

```powershell
E:/Anaconda2023/envs/ALB/python.exe -m pytest `
  test/contracts `
  test/config `
  test/couple `
  test/bearing/test_alb_harmonic_linear.py `
  test/bearing/test_nodim_interfaces.py `
  test/bearing/test_nodim_alb_equivalence.py `
  test/bearing/test_thermal_nondim_solver.py `
  test/bearing/test_thermal_wrapper_nodim_core.py `
  -q -p no:cacheprovider
```

结果：`94 passed, 2 subtests passed, 12 warnings`，耗时约 `22.43 s`。

- 12 条 warning 来自既有 `skfuzzy` 除法数值提示和 `scipy.optimize` 迭代进展提示，不是本次接口重构产生的测试失败。
- `test/contracts/test_interface_contract_reference.py` 已确认旧 import、旧 export 目标、信号传播、谐波轴承、旧线性代理、转子耦合及 scaler pickle 参考保持一致。
- 所有 34 个 v1 数值参考数组均使用 `numpy.testing.assert_array_equal` 逐元素比较通过。
- 已对 `ALB/` 和 `test/contracts/` 共 67 个 Python 文件执行无写盘语法编译检查，全部通过。
- 已成功构建 `re_alb-0.1.0-py3-none-any.whl`，在隔离目录安装后成功导入 68 个顶层 export 以及五个分类 namespace；临时 wheel、安装目录、`build/` 和 `re_alb.egg-info` 已清理。

## 当前风险与待处理事项

- 大型求解器实现尚未迁入分类子包；当前分类 namespace 仍主要提供兼容映射，不能表述为大型单体模块已经完全拆分。
- `calc_error()` 的历史返回仍混有残差标量、布尔值和空值。新代码已有 `ConvergenceStatus`，但必须逐 solver 迁移，不能批量改变旧返回语义。
- `RsRotorBearingCouple` 暂时允许 `unit_system="unspecified"` 的旧轴承；`0.2.0` 目标只允许 dimensional/nondimensional，因此收紧前必须先完成显式单位适配和精确回归。
- `RossRotor.output()` 仍同时承担状态读取和推进相关语义；拆分为明确读/写时序前必须固定转子推进参考。
- `ALB/tool.py::EmailSender` 仍存在嵌入式默认认证配置风险。凭据值不得写入文档或日志；应单独完成凭据轮换和基础设施迁移。
- 本轮没有执行仓库内全部探索性、GUI、远程和会生成固定图片的测试；当前结论只覆盖上述 94 项稳定相关测试及 wheel 隔离导入。全仓库重构必须重新收集并逐项映射当前测试节点。

## 当前工作树中未纳入本轮提交的文件

- 已修改：`test/bearing/_thermal_plots/alb_thermal_4pads.png`。
- 已修改：`test/bearing/_thermal_plots/orifice_thermal_comparison.png`。
- 未跟踪：`.codex/`。
- 未跟踪：`test/control/LQG/albnn_rotor0_lqg_small_signal.py`。
- 未跟踪：`test/control/LQG/output/`。

上述文件当前均不得按接口重构产物处理。是否提交、归档或清理需要按各自来源另行确认。

## 下一步

1. 将本状态入口与 `AGENTS.md`、`README.md`、文档角色索引、文件分类和 run 索引作为独立状态文档包提交，并创建 `pre-full-repo-refactor-20260720` annotated tag。
2. 建立 `refs/full_repo_refactor_v1/`、环境 manifest、领域参考和测试节点迁移映射；提交后创建 `pre-full-repo-refactor-refs-20260720` annotated tag。
3. 按 `contracts/core/config` 基础层和固定领域依赖顺序实施机械迁移，每个阶段运行精确参考并形成独立提交。
4. 单独处理私人邮件配置和 `SmtpNotifier`；删除当前 tracked 私人信息，但不改写 Git 历史，并明确提示在仓库外轮换凭据。
5. 完成外部只读迁移报告、性能阈值、wheel/隔离安装/extras/CLI 验收后更新本文档并创建 `0.2.0` 最终 tag。

## 证据指针

- 接口与模块规则：`docs/interface_architecture.md`。
- 稳定 package 导览：`docs/alb_package_overview.md`。
- 重构前精确参考：`refs/interface_contract_reference_v1.json`、`refs/interface_contract_reference_v1.npz`。
- 新接口测试：`test/contracts/test_component_contracts.py`。
- 兼容数值回归：`test/contracts/test_interface_contract_reference.py`。
- 最终重构提交：`721a3902063a7d8427488bf23b6446cdb92942dd`。
