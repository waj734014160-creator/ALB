# 文档贡献流程

站点页面、API reference 和配置字段参考有不同事实源。修改时按下列顺序工作，避免手工内容被生成器覆盖。

## 1. 修改正确的事实源

| 内容 | 事实源 |
| --- | --- |
| 根 API 签名、成员与英文合同 | `ALB.__all__` 和源码 docstring |
| 根 API 中文语义 | `docs/api/public_api_docs.json` |
| bearing/simulation 字段英文合同 | `ALB/api/_config_fields.py` |
| 配置分组中文标题与摘要 | `docs/api/config_reference_docs.json` |
| 配置流程与跨字段规则 | 对应的 `*_config_reference_source.md` |
| 高级 namespace 英文合同 | namespace 字面量 `_EXPORTS` 与定义源码 docstring |
| 高级 namespace 中文语义 | `docs/api/namespace_reference_docs.json` |
| 使用流程 | `docs/site/` 中的稳定中文指南 |

## 2. 重建参考

```powershell
python tools/docs/generate_public_api_reference.py
python tools/docs/generate_bearing_config_reference.py
python tools/docs/generate_simulation_config_reference.py
python tools/docs/generate_namespace_reference.py
```

## 3. 检查和构建

```powershell
python tools/docs/generate_public_api_reference.py --check
python tools/docs/generate_bearing_config_reference.py --check
python tools/docs/generate_simulation_config_reference.py --check
python tools/docs/generate_namespace_reference.py --check
python -m pytest tests/unit/docs tests/unit/api/test_public_api_reference.py tests/unit/api/test_bearing_config_reference.py tests/unit/api/test_simulation_config_reference.py tests/integration/api/test_documented_examples.py tests/integration/docs -q
python -m mkdocs build --strict
```

## 4. 对外发布

- 正式站点发布到 <https://waj734014160-creator.github.io/ALB/>；用户指南和 API Reference 使用同一站点与同一版本。
- ALB 源仓库保持私有；生成后的静态站点单独发布到公开仓库 `waj734014160-creator/waj734014160-creator.github.io` 的 `ALB/` 子目录。
- `.github/workflows/docs-pages.yml` 负责严格检查、构建和跨仓库发布；当前开发分支 `codex/alb-0.4.5` 与后续 `main` 更新会触发发布，也可从 GitHub Actions 手动运行。
- 发布前必须通过四类生成参考漂移检查、文档/API 目标测试、严格 MkDocs 构建和公共站点内容边界测试。不要绕过工作流直接上传手工修改的 `site/`。
- Pages 仓库只保存可再生的静态站点；部署凭据使用只对该仓库有写权限的 SSH deploy key，并保存为源仓库 Actions secret `PAGES_DEPLOY_KEY`。
- 源仓库为私有仓库，但 GitHub Pages 站点和 Pages artifact 仓库面向公众；任何进入站点的内容都必须按公开材料审查。

## 5. 内容规则

- 面向用户的指南、说明和维护正文使用中文。
- 源码 docstring、代码注释和 CLI help 使用英文。
- 不把实时状态、PID、远程连接、daily logs、审计证据或单次实验写入公共站点。
- `site/` 是可复现 build artifact，不提交。
