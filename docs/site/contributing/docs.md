# 文档贡献流程

站点页面、API reference 和配置字段参考有不同事实源。修改时按下列顺序工作，避免手工内容被生成器覆盖。

## 1. 修改正确的事实源

| 内容 | 事实源 |
| --- | --- |
| 根 API 签名与成员 | `ALB.__all__` 和源码 docstring |
| 根 API 中文语义 | `docs/api/public_api_docs.json` |
| bearing 字段 | `ALB/api/_config_fields.py` 与配置参考 source |
| 高级 namespace | namespace 字面量 `_EXPORTS` 与 `namespace_reference_docs.json` |
| 使用流程 | `docs/site/` 中的稳定中文指南 |

## 2. 重建参考

```powershell
E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_public_api_reference.py
E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_bearing_config_reference.py
E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_namespace_reference.py
```

## 3. 检查和构建

```powershell
E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_public_api_reference.py --check
E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_bearing_config_reference.py --check
E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_namespace_reference.py --check
E:/Anaconda2023/envs/ALB/python.exe -m mkdocs build --strict
```

## 4. 内容规则

- 面向用户的指南、说明和维护正文使用中文。
- 源码 docstring、代码注释和 CLI help 使用英文。
- 不把实时状态、PID、远程连接、daily logs、审计证据或单次实验写入公共站点。
- `site/` 是可复现 build artifact，不提交。
- 对外发布不是本地 build 的默认结果；启用 Pages 或其他 hosting 前必须单独确认。
