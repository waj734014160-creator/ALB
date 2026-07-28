# 转子-轴承仿真

仿真把一个 dimensional rotor、唯一节点挂载、载荷声明和历史策略冻结为 `SimulationConfig`。

!!! info "需要 dynamics extra"
    使用 ROSS 转子文件或动力学能力前安装 `re-alb[dynamics]`。仅构造自定义 `RotorProtocol` 实现时不应依赖内部 ROSS adapter 路径。

```python
mount = ALB.BearingMount(config=bearing_config, node=0)
history = ALB.HistoryPolicy(
    mode="memory",
    fields=("rotor_displacement", "bearing_force"),
    downsample=1,
)
simulation_config = ALB.SimulationConfig(
    rotor=rotor,
    mounts=(mount,),
    time_step=0.001,
    steps=100,
    loads=(
        {"type": "static", "node": 0, "force": [0.0, -1000.0]},
        {"type": "gravity", "acceleration": 9.80665},
    ),
    history=history,
)
result = ALB.build_simulation(simulation_config).run()
```

## 载荷

| type | 必填字段 | 主要可选字段 |
| --- | --- | --- |
| `static` | `node`, `force=[Fx, Fy]` | 无 |
| `gravity` | 无 | `acceleration=9.80665` |
| `unbalance` | `node` | `phase`, `t_max`, `m`, `freq`, `e`, `no_step` |

所有节点必须是非负整数，声明在构造时被复制并冻结。

## 历史策略

- `memory`：保留选定的全部采样。
- `ring_buffer`：只保留最近 `capacity` 个采样。
- `disk_stream`：写入 `directory`，对应内存数组为空。
- `downsample=N`：保留提交索引能被 N 整除的采样，包括初始索引 0。

`steps` 表示初始提交点之后的 advance 次数，因此默认 memory history 有 `steps + 1` 个时间点。simulation 是 one-shot；需要重跑时重新构建。
