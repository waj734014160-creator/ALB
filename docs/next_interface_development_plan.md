# ALB 0.4.0 无 Legacy 兼容与友好 API 发布计划

## 文档角色

- 角色：下一阶段开发目标和验收边界。
- 目的：固定 0.4.0 的公共接口、删除边界、消费者迁移和发布门禁。
- 允许更新：目标特性、接口、阶段、兼容边界、验收条件和非目标。
- 禁止更新：把规划项写成已通过、复制单次日志或记录外部实时状态。
- 更新时机：公共接口方案或验收边界变化时。
- 事实来源：ADR-0006、`release_feature_manifest_0_4.json`、
  `docs/migrations/0.4.0_test_map.json`。

## 目标

0.4.0 是明确的不兼容版本。目标是让普通用户只接触严格配置、友好构建入口、
`calculate()`/`run()` 和不可变结果，同时从 wheel 和所有活跃运行路径物理删除
0.3 兼容面。

目标用法：

```python
import ALB

bearing = ALB.bearing_from_file("bearing.json5")
result = bearing.calculate(
    displacement=(x, y),
    velocity=(vx, vy),
    time=t,
)
```

## 必须完成的发布特性

1. 根 namespace 只公开 facade、配置、结果和稳定异常。
2. 五种 bearing family 收敛到同一可计算 facade。
3. `Bearing` 构造即 ready，不公开 `init()`，以 `reset()` 开启新会话。
4. mixed liquid-film 由 `restrictors` 是否非空自然决定。
5. PID/FuzzyPID、热配置、Gas、MultiPad 和 direct-spool 使用严格生命周期。
6. 分析服务使用独立 runtime；仿真挂载和默认全历史策略不可变。
7. JSON5 include、override/sweep 和跨字段校验完全严格。
8. ALBNN 使用 v0.4 package、`weights_only=True` 和 NPZ scaler。
9. `Signal`、legacy adapter、旧 factories、宽松配置和兼容 CLI 物理删除。
10. SURROGATE_TRAIN 与 PAPER_WORK 的声明活跃消费者迁移为公开 0.4 API。

V4-01 至 V4-24 的测试映射是这些目标的机器可执行定义。0.3 F01-F66 manifest
保持历史不修改；F35 由 V4-17 的 Signal removal 正式关闭。

## 阶段边界

### 阶段 A：冻结与可恢复性

- 在生产修改前冻结 active 控制模式、液膜、热、Gas、MultiPad、harmonic、
  coupling 和 ALBNN 结果。
- `refs/**` 只增不改。
- PAPER_WORK 修改前生成哈希清单和可恢复快照。

### 阶段 B：包内收敛

- 建立 `ALB.api` facade、严格 0.4 配置与不可变结果。
- 将各 bearing family、分析和 simulation 接入正式 runtime。
- 删除 package 内旧模块、alias、Signal、adapter 和 fallback。

### 阶段 C：消费者迁移

- SURROGATE_TRAIN 形成独立 Git 提交。
- PAPER_WORK 只修改声明活跃脚本和配置；历史 outputs、refs、日志和图件不动。
- 所有候选 wheel smoke 必须在安装态运行，不能依赖源码 shadow import。

### 阶段 D：候选与发布

- 完整 pytest、required nodeid、严格/增量 mypy、零未处理 warning。
- tracked-clean 后固定候选 SHA。
- detached worktree 连续构建并比较 wheel SHA，审计 wheel 成员与源码 token。
- 隔离安装同一个 wheel，执行 ALB_MAIN、SURROGATE_TRAIN 和 PAPER_WORK smoke。
- 机器报告不得反向写入所验收的候选提交。

## 不兼容边界

不提供弃用警告、兼容转发或旧配置自动迁移。旧配置和旧模型转换器只位于
`tools/migrations/`，不安装 console entry point，不进入 wheel。历史文档和不可变
证据允许读取旧格式，但不得成为运行时依赖。

## 非目标

- 不改变 Reynolds、热、控制、Gas、转子或 ALBNN 的有效数值公式。
- 不删除历史 refs、remote payload、outputs/results、日志或图件数据。
- 不为默认 simulation 设置隐式历史容量上限。
- 不把 detached 验收报告写回其候选提交。

## 发布完成条件

只有当候选 tracked-clean、V4 manifest 全部 nodeid 可收集、完整测试和 mypy
通过、wheel 双构建可复现、安装制品 legacy-zero、外部消费者 smoke 通过时，
才允许把 `v0.4.0` 标签和发布 wheel 绑定到该候选 SHA。
