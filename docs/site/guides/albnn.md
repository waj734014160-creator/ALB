# ALBNN 模型包

ALBNN 代理轴承通过与物理轴承一致的 `BearingConfig -> Bearing -> BearingResult` facade 使用。模型包负责保存模型、scaler、输入契约和运行参数，不应复制 ALB 包源码。

!!! info "需要 surrogate extra"
    ```powershell
    E:/Anaconda2023/envs/ALB/python.exe -m pip install "re-alb[surrogate]"
    ```

## 配置形状

```json5
{
  family: "surrogate",
  unit_system: "dimensional",
  time_step: 0.001,
  node: 0,
  model_package: {
    path: "models/current_package",
    use_augment: true,
  },
  runtime: {
    spool_mode: "fixed",
    spool: [0.0, 0.0],
    parameters: {},
  },
}
```

`model_package.path` 必须是相对于配置文档目录的安全路径，不允许绝对路径或 `..` 逃逸。

## spool 模式

- `fixed`：在配置中提供二轴 `spool`，范围 `[-1, 1]`。
- `external`：每次 `calculate()` 显式传入 spool，配置中不能再定义固定 spool。

完整训练过程、实时 loss、远程 PID 和 queue 状态不属于用户 API 文档。模型训练与数据契约应查阅拥有该任务的 SURROGATE_TRAIN 文档。
