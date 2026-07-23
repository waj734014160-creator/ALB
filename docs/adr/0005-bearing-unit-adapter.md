# ADR-0005：Bearing 单位适配器与尺度元数据

## 文档角色

- 角色：dimensional/nondimensional bearing 接入和结果尺度的架构决策。
- 状态：Accepted，第四轮审查批准并补充 P2 metadata 字段语义。
- 允许更新：尺度值对象、转换方向、阀芯规则、残差和元数据要求。
- 禁止更新：根据数值大小猜测单位、只乘单一比例或在没有参考时定义新的物理尺度。
- 相关文档：`docs/next_interface_development_plan.md`、`docs/interface_architecture.md`。

## 背景

dimensional rotor 不能直接消费 nondimensional bearing。一个只对位移或力乘单个比例的 adapter
不足以保证速度、时间、阀芯、收敛残差和结果元数据的一致性。

## 决策

1. 所有 scale 的数学方向统一定义为“一个 nondimensional unit 对应的 dimensional 数值”：

   ```text
   x_dim = x_nd * Sx
   t_dim = t_nd * St
   v_dim = v_nd * Sv
   F_dim = F_nd * Sf
   p_dim = p_nd * Sp
   ```

   因此反向转换固定为除以对应 scale。所有 scale 必须为有限正实数。
2. 默认要求 `Sv = Sx / St`，并使用与数值尺度量级相称的严格验证容差。模型若有不同速度定义，
   必须提供非空 `velocity_definition_id` 和独立冻结参考，不能只关闭一致性检查。
3. 任意转换统一经过 canonical dimensional domain：

   ```text
   source -> dimensional canonical domain -> target
   ```

   adapter 不直接拼接任意 source/target 比例，也不根据当前对象组合推导临时比例。
4. `BearingUnitAdapter` 只接受已经验证的不可变 `BearingScaleSet`，不从数值或对象类名猜测尺度。
5. `BearingScaleSet` 至少明确：

   ```text
   source and target UnitSystem
   Sx displacement scale
   St time scale
   Sv velocity scale
   Sf force scale
   Sp pressure scale
   pressure scale source
   velocity_definition_id
   residual_definition_id
   scale provenance/identifier
   ```

6. displacement、velocity、time/`dt`、force 和 pressure 分别转换，不能复用一个无单位名称的比例。
7. normalized spool 固定为 nondimensional `[-1, 1]`，默认做身份传递。物理执行器位移到 normalized
   spool 的换算属于单独 actuator adapter，不隐藏在 bearing unit adapter 中。
8. 全局 ledger 始终保留 rotor domain 的 `StepContext`。adapter 为 bearing 创建 local context：

   - `step_index` 保持不变；
   - `time` 和 `dt` 按 `St` 转换；
   - `unit_system` 改为 bearing domain；
   - local context 不进入全局 ledger。

9. bearing 输出必须先转换回 rotor domain，才能交给 coupler、`RotorLoadInput`、全局
   `ResultBundle` 和正常端口输出。
10. 运行时的 local context、输入、输出、力和 residual 转换必须共享同一个不可变
    `BearingScaleSet` 实例。`StepContext`、端口 DTO 和 `ResultBundle.metadata` 不直接保存该
    dataclass 实例。
11. `ResultBundle.metadata["unit_adapter"]` 保存与摘要 v1 兼容的 primitive descriptor：

    ```python
    {
        "schema": "alb.bearing-scale-set.v1",
        "scale_id": "...",
        "source_unit": "dimensional",
        "target_unit": "nondimensional",
        "scale_definition": "dimensional_per_nondimensional",
        "applied_transform": "rotor_to_bearing",
        "Sx": 1.0,
        "St": 1.0,
        "Sv": 1.0,
        "Sf": 1.0,
        "Sp": 1.0,
        "velocity_definition_id": "...",
        "residual_definition_id": "...",
        "provenance": "...",
    }
    ```

    所有 key 必须是字符串；值只能使用 `alb.result-bundle.sha256.v1` 支持的 finite 基础类型，
    不使用 dataclass、`repr()`、pickle 或对象地址。global context 和 bearing-local context 也
    以规范 primitive mapping 保存。
12. `scale_definition` 固定描述 scale 的数学定义，取值
    `"dimensional_per_nondimensional"`，不表示本次数据流方向。`applied_transform` 单独记录本次
    转换，只允许 `"rotor_to_bearing"` 或 `"bearing_to_rotor"`。metadata 同时记录 global
    context、bearing-local context、source/target unit、scale ID 和 provenance。
13. adapter 必须双向定义：

   - rotor/input domain 到 bearing domain；
   - bearing force/result domain 回到 rotor/output domain。

14. 收敛 residual 不使用一个通用乘法比例。`residual_definition_id` 必须标识 residual 的定义、
    分子/分母、单位和转换方法；film、thermal、control 等不同 residual 可以拥有不同转换器。
    无已知定义时只保留 bearing-local residual，并在 global metadata 中明确其 local unit。
15. 实现前先冻结当前 dimensional/nondimensional 对应工况、时间尺度、速度尺度、力尺度和残差
   解释。无法由当前模型配置唯一确定的尺度必须报错，不补默认猜测。
16. 单位转换参考在固定 CPU、dtype 和依赖环境中要求精确相等；只要转换不涉及并行/GPU，不使用
   放宽容差掩盖定义不一致。

## 影响

- 混合单位 coupling 的每个转换量都有可审计来源。
- direct-spool 的 normalized command 不会和物理阀芯位移混为一谈。
- 结果文件可以根据 metadata 还原尺度，而不是依赖调用者记忆。
