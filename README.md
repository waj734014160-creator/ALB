# ALB_MAIN 0.4

`ALB_MAIN` 是 `G:/ALB_PROJECTS` split workspace 中的稳定 ALB Python 包。
包名为 `re-alb`，导入名为 `ALB`，最低 Python 版本为 3.10。当前工作树版本以
`pyproject.toml` 和 `ALB.__version__` 为准；发布状态、验证结论和风险见
`docs/current_state.md`。

## 用户入口

0.4 普通用户只从包根使用配置、构建、轴承、分析、仿真、不可变结果和稳定异常：

```python
import ALB

config = ALB.load_bearing_config("bearing.json5")
bearing = ALB.build_bearing(config)
result = bearing.calculate(
    displacement=(0.0, 0.0),
    velocity=(0.0, 0.0),
    time=0.0,
)
print(result.fx, result.fy)
```

- `docs/api/README.md`：自动 API 文档的范围、生成方式和一致性门禁。
- `docs/api/public_api_reference.md`：全部根公开类、函数、输入、输出、异常和示例。
- `docs/alb_albnn_quickstart.md`：轴承、分析、仿真和 ALBNN package 快速用法。
- `docs/alb_package_overview.md`：模块图、公共接口组和安装制品边界。

## 目录

- `ALB/`：0.4 包代码；普通流程使用根 facade，高级实现按明确 namespace 分层。
- `tests/`：正式 pytest，分为 unit、integration、regression 和 validation。
- `tools/`：benchmark、诊断、文档、迁移、参考生成和发布验证工具。
- `refs/`：不可覆盖的行为参考、固定输入和历史回归资产。
- `docs/`：API、架构、当前状态、迁移、文件分类和远程操作说明。
- `test/`：迁移后保留的历史图件和轻量配置，不属于 pytest 收集目录。

## 安装与验证

```powershell
E:/Anaconda2023/envs/ALB/python.exe -m pip install -e ".[all,test]"
E:/Anaconda2023/envs/ALB/python.exe -m pytest
E:/Anaconda2023/envs/ALB/python.exe tools/validation/run_layered_mypy.py
E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_public_api_reference.py --check
```

API 参考由 `ALB.__all__`、真实运行时签名和中文语义元数据生成。公开接口变化后运行：

```powershell
E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_public_api_reference.py
```

## 首读文档

- `docs/current_state.md`：当前开发阶段、验证结论、风险和下一步。
- `docs/project_overview.md`：项目边界、目录职责和稳定工作流入口。
- `docs/interface_architecture.md`：依赖方向、生命周期、DTO、单位和持久化契约。
- `docs/adr/README.md`：公共接口和数值算法决策。
- `docs/file_classification.md`：文件归属、生成物和清理约束。
- `docs/remote_workstation_connection.md`：远程工作站稳定机制。
- `docs/migrations/0.2.0.md`、`0.4.0.md` 至 `0.4.3.md`：历史和当前迁移说明。

`SURROGATE_TRAIN` 与 `PAPER_WORK` 是独立项目。本仓库不保存它们的实时训练或
论文任务状态，也不应复制它们的任务脚本和运行产物。
