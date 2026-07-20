# ALB_MAIN 0.2.0 全仓库重构参考

## 参考角色

- 角色：`0.2.0` 生产源码迁移前的不可变行为与性能基线。
- 基线提交：`a4b2be1abc2efdea0d49e49cf4996ec48fb531c2`。
- 基线标签：`pre-full-repo-refactor-20260720`。
- 生成器：`tools/reference/generate_full_repo_refactor_references.py`。
- 测试节点清单生成器：`tools/reference/capture_full_repo_refactor_test_nodes.py`。
- 禁止操作：不得覆盖、重生成或移动本目录中的 v1 文件；若数值算法需要修正，应建立 v2 参考和独立提交。

## 内容

每个计算领域使用同名 JSON 与 NPZ 文件：JSON 保存输入、配置、收敛摘要、数组清单和 SHA-256；NPZ 无损保存数组。领域包括：

- `core_fem`
- `film`
- `hydraulics_orifice`
- `bearing`
- `gas`
- `thermal`
- `control_valve`
- `dynamics_coupling`
- `systems_alb_harmonic`
- `surrogate_training`
- `remote_persistence`

`environment.json` 保存 Python、依赖、线程和固定随机种子；`performance_baseline.json` 保存 film、thermal、ALB、ALBNN 和 coupling 的同机重复计时。`test_node_migration_map.json` 是 242 个旧测试节点的不可变初始清单与迁移计划，不承担最终完成状态；最终实际映射写入 `docs/migrations/0.2.0_test_map.json`。

## 生成命令

以下命令只允许在上述基线提交、生产源码干净且本目录尚无目标文件时执行：

```powershell
$env:PYTHONHASHSEED='0'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONUTF8='1'
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:NUMEXPR_NUM_THREADS='1'

E:/Anaconda2023/envs/ALB/python.exe `
  tools/reference/generate_full_repo_refactor_references.py
```

重构后的精确回归必须重新构造相同输入，并对所有冻结数组执行 `numpy.testing.assert_array_equal`。性能比较只有在数值数组精确通过后才有效；候选中位时间超过基线 15% 时暂停对应领域迁移并复核。
