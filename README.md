# ALB_MAIN 0.2.0

`ALB_MAIN` 是 `G:/ALB_PROJECTS` split workspace 中的稳定 ALB Python 包。0.2.0 采用破坏式、命名空间优先的 API，将 Reynolds 油膜、热耦合、控制、转子动力学和 ALBNN 实现按领域拆分，同时保持冻结参考中的数值行为不变。

## 目录

- `ALB/`：0.2.0 包代码；领域实现必须从明确 namespace 导入。
- `tests/`：正式 pytest，分为 `unit`、`integration`、`regression` 和 `validation`。
- `tools/`：基准、诊断、迁移、参考生成、验证和手动工具。
- `refs/full_repo_refactor_v1/`：不可覆盖的 0.2.0 重构前精确行为参考。
- `refs/full_repo_refactor_addendum_v1/`：不覆盖主 v1 的 thermal 收敛、Newton 和时序补充参考。
- `docs/`：项目状态、接口架构、迁移指南、文件分类和远程操作手册。
- `test/`：迁移后保留的历史图件和轻量配置，不属于 pytest 收集目录。

## 安装与验证

最低 Python 版本为 3.10。核心安装只包含通用数值依赖；领域依赖通过 extras 安装：

```powershell
E:/Anaconda2023/envs/ALB/python.exe -m pip install -e ".[all,test]"
E:/Anaconda2023/envs/ALB/python.exe -m pytest
```

`ALB.__init__` 只导出版本、`UnitSystem`、`StepContext`、`ConvergenceStatus` 和基础计算块协议。示例：

```python
from ALB import ComputationalBlock, StepContext, UnitSystem, __version__
from ALB.physics.film import SkfemNewtonFilm
from ALB.systems.alb import BearingBlock, nodim_alb
```

旧 `ALB.alb`、`ALB.film`、`ALB.nn`、`ALB.remote` 等平铺模块已经删除。完整导入映射和不兼容说明见 `docs/migrations/0.2.0.md`。

## 首读文档

- `docs/current_state.md`：当前发布状态、验证结论、风险和下一步。
- `docs/project_overview.md`：项目边界、目录职责和稳定工作流入口。
- `docs/alb_package_overview.md`：0.2.0 模块图和公共接口组。
- `docs/interface_architecture.md`：计算块、DTO、单位、时步提交和持久化契约。
- `docs/alb_albnn_quickstart.md`：ALB 与迁移后 ALBNN model package 的最小用法。
- `docs/file_classification.md`：文件归属、生成物和清理约束。
- `docs/remote_workstation_connection.md`：远程工作站稳定机制。

`SURROGATE_TRAIN` 与 `PAPER_WORK` 是独立项目。0.2.0 只生成它们的只读迁移审计，不在本仓库重写外部文件或记录外部实时任务状态。
