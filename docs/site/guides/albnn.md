# ALBNN 模型包

ALBNN 代理轴承通过与物理轴承一致的 `BearingConfig -> Bearing -> BearingResult` facade 使用。模型包负责保存模型、scaler、输入契约和运行参数，不应复制 ALB 包源码。

!!! info "需要 surrogate extra"
    ```bash
    python -m pip install "re-alb[surrogate]"
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
    symmetry: "c4",
  },
  runtime: {
    spool_mode: "fixed",
    spool: [0.0, 0.0],
    parameters: {},
  },
}
```

`model_package.path` 必须是相对于配置文档目录的安全路径，不允许绝对路径或 `..` 逃逸。

## 推理对称性

只在 `ex >= 0, ey >= 0` 象限训练的四瓦模型包（如 M35、M42）需要 `symmetry: "c4"`：偏心、速度和阀芯向量一起旋入训练象限，推理后再把力旋回。`symmetry: "none"` 使用原网络。省略该字段时按模型包 metadata 的 `inference_symmetry` 声明执行；未声明但输入 scaler 显示只在第一象限拟合的模型包会在构建时报错，要求显式选择。`use_augment` 只控制特征增强，与对称性无关。

## spool 模式

- `fixed`：在配置中提供二轴 `spool`，范围 `[-1, 1]`。
- `external`：每次 `calculate()` 显式传入 spool，配置中不能再定义固定 spool。

完整训练过程、实时 loss、远程 PID 和 queue 状态不属于用户 API 文档。模型训练与数据契约应查阅拥有该任务的 SURROGATE_TRAIN 文档。
