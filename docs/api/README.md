# ALB 自动 API 文档

## 文档角色

- 角色：稳定公开 API 文档入口和自动跟踪机制说明。
- 目的：说明 API 文档的覆盖范围、阅读入口、生成方式和一致性门禁。
- 允许更新：公开 API 文档范围、生成流程、元数据规则、验证命令和阅读入口。
- 禁止更新：实时运行状态、单次实验结果、未导出的内部实现和手工复制的接口清单。
- 更新时机：公开 API 策略、生成器、元数据格式或验证入口变化时。
- 事实来源：`ALB.__all__`、高级 namespace 的显式导出、`ALB/api/_config_fields.py`、
  三类文档生成器、`docs/api/public_api_docs.json`、
  `docs/api/namespace_reference_docs.json` 和生成后的公开参考。

## 阅读入口

线上站点统一发布用户指南与 API Reference：

- [根公开 API](https://waj734014160-creator.github.io/ALB/api/public_api_reference/)
- [轴承配置字段](https://waj734014160-creator.github.io/ALB/api/bearing_config_reference/)
- 高级 namespace：[Control](https://waj734014160-creator.github.io/ALB/api/namespaces/control/)、[Dynamics](https://waj734014160-creator.github.io/ALB/api/namespaces/dynamics/) 和 [Surrogate](https://waj734014160-creator.github.io/ALB/api/namespaces/surrogate/)

[公开 API 自动参考](public_api_reference.md) 是仓库内的主文档，完整展示当前
`ALB` 根命名空间中的：

- 类、枚举、异常、函数和包版本；
- 构造函数与公开方法的真实运行时签名；
- 参数类型、是否必填、默认值、调用方式和中文说明；
- 返回类型、结果语义、常见异常和源码位置；
- 轴承构建、参数扫描、分析、仿真、结果持久化和异常处理示例。

[轴承配置字段参考](bearing_config_reference.md) 逐项说明 `film`、
`restrictors`、主动润滑和热模型字段的单位、缺省值与功能。编写程序化
`BearingConfig` 或 JSON5 时应以该文档为用户入口。可直接运行的完整 JSON5
位于 [`examples/`](examples/)；推荐阅读顺序是：先在 IDE/docstring 中确认入口和
字段形状，再复制最接近的示例，最后用字段参考查询全部约束。

[高级 namespace 参考](namespaces/control.md)只覆盖 `ALB.control`、
`ALB.dynamics` 和 `ALB.surrogate` 的显式导出。它们属于需要对应 optional extra 的
高级 API；可导入的实现模块和私有 helper 不因此成为公开接口。

普通用户只应把 `ALB.__all__` 视为稳定的友好 API。`ALB.config`、
`ALB.physics`、`ALB.control`、`ALB.dynamics`、`ALB.surrogate` 等领域
namespace 面向高级开发和内部装配，其模块边界见
[`docs/alb_package_overview.md`](../alb_package_overview.md) 和
[`docs/interface_architecture.md`](../interface_architecture.md)。

## 自动跟踪原理

公开 API 生成器直接导入当前工作树的 `ALB`，以 `ALB.__all__` 为事实来源，并
通过 Python introspection 读取公开对象、真实签名、公开属性/方法、返回标注和源码
位置。中文功能说明、参数语义、异常条件和示例保存在
`public_api_docs.json`，不与生成正文混写。

配置参考生成器读取 `ALB/api/_config_fields.py` 中的结构化字段元数据，并把稳定的
字段表与中文说明组合为 `bearing_config_reference.md`。公开字段名、原生映射、单位、
适用 family/unit system、缺省值和约束不应在生成器或手册中另建一份事实源。

高级 namespace 生成器以静态方式读取各 namespace 的字面量 `_EXPORTS`，不导入可选
backend；中文用途、安装 extra 和稳定性标签来自
`namespace_reference_docs.json`。生成结果只包含显式导出，并分别写入
`docs/api/namespaces/`。

以下变化会被检查捕获：

- `ALB.__all__` 新增、删除或重命名符号；
- 类、函数或公开方法的参数、默认值、类型标注和返回标注变化；
- 类的公开 property 或 method 新增、删除或重命名；
- 新接口缺少中文说明、参数说明或示例；
- 元数据仍引用已经删除的接口、参数、成员或示例；
- 生成后的 Markdown 与当前源码或元数据不一致；
- 高级 namespace 元数据与其显式导出不一致；
- 示例代码存在 Python 语法错误；
- 公共站点导航或构建包含禁止公开的维护和运行材料。

## 生成与检查

在仓库根目录运行：

```powershell
E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_public_api_reference.py
E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_bearing_config_reference.py
E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_namespace_reference.py
E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_public_api_reference.py --check
E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_bearing_config_reference.py --check
E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_namespace_reference.py --check
E:/Anaconda2023/envs/ALB/python.exe -m pytest tests/unit/api/test_public_api_reference.py tests/unit/api/test_bearing_config_reference.py tests/unit/docs tests/integration/api/test_documented_examples.py tests/integration/docs -q
E:/Anaconda2023/envs/ALB/python.exe -m mkdocs build --strict
```

前三条命令分别重建根 API、配置字段和高级 namespace 参考；三条 `--check`
命令只比较内容且不写文件；pytest 固定生成内容、元数据约束、公共内容边界和可复制
示例；最后的 MkDocs 命令以 warning-as-error 方式构建完整站点。

## 接口变化时的维护顺序

1. 修改并验证公开源码、namespace `_EXPORTS` 或 `_config_fields.py` 字段元数据。
2. 根 API 语义变化时，在 `public_api_docs.json` 中调整中文参数、异常和示例引用；
   高级 namespace 变化时同步修改 `namespace_reference_docs.json`。
3. 运行三类生成器，重建根 API、配置字段和高级 namespace 参考。
4. 运行三条 `--check`、目标 pytest、示例 smoke 和 `mkdocs build --strict`。

不要手工修改生成参考；下一次生成会覆盖手工内容。
