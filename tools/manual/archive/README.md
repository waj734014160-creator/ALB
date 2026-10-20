# 历史演示入口

本目录保存退出日常工具入口的源码，文件内容保留迁移前字节。

| 文件 | 原位置 | 保留原因与限制 |
| --- | --- | --- |
| `plot_test.py` | `tools/manual/plot_test.py` | 简单的 Matplotlib 动态绘图演示，不属于 ALB 验证。 |
| `alb_gui_app.py` | `tools/manual/alb_gui_app.py` | 旧 GUI 打包入口；它引用的 `tools.manual.alb_gui.window` 源码已不在当前仓库，不能当作现行 GUI 启动器。 |

旧 GUI 分发包与孤立编译文件已保存到本地 `outputs/archive/project_cleanup_20260926/`，具体位置见[清理记录](../../../docs/daily_maintenance/project_cleanup_20260926.md)。编译文件仅用于历史恢复，不保证能够独立运行。

五子棋脚本已按用户要求删除，可从清理记录绑定的 Git HEAD 恢复。旧迁移映射和冻结参考描述的是当时版本，保留原内容；本次去向通过新增清单追溯。
