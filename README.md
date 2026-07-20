# ALB_MAIN

`ALB_MAIN` 是 `G:/ALB_PROJECTS` split workspace 中的稳定 ALB 包项目，保存核心包代码、源码测试和项目维护文档。

主要内容：

- `ALB/`：核心包代码。
- `test/`：Python 测试、调试文件和轻量配置。
- `docs/`：项目文档、包概览、文件分类、run 规则和远程操作手册。
- `refs/`：行为参考和回归基线。
- `pyproject.toml`、`README.md`、`AGENTS.md`：包元数据和项目入口规则。

首读文档：

- `docs/project_overview.md`：项目边界、目录职责和首读顺序。
- `docs/current_state.md`：ALB_MAIN 当前开发阶段、验证状态、风险和近期下一步。
- `docs/alb_package_overview.md`：`ALB/` 模块图和公共接口组。
- `docs/alb_albnn_quickstart.md`：快速构建默认 ALB、加载 ALBNN packaged model 的用户手册。
- `docs/remote_workstation_connection.md`：稳定远程工作站连接和长任务操作说明。
- `docs/file_classification.md`：仓库文件归属和清理约束。
- `docs/run_index.md`：工作区全局 run 编号、路径和 current-status 边界规则。

刻意排除的内容：`.env`、`.git`、IDE 目录、缓存、notebook、模型输出和生成产物。

ALB GUI 的打包产物位于 `G:/ALB_PROJECTS/TOOL/ALB_GUI`。启动器和打包入口已迁移到 `G:/ALB_PROJECTS/TOOL/start_alb_gui.bat` 与 `G:/ALB_PROJECTS/TOOL/pack_alb_gui.bat`。
