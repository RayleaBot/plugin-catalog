# RayleaBot Plugin Catalog

本仓库发布 RayleaBot 默认插件源的静态 `catalog.json`。目录只描述每个插件当前可安装版本，不保存历史版本、签名文件或逐文件清单。

## 维护方式

- `sources.json` 维护插件名称、仓库、分类等稳定信息。
- `scripts/sync_catalog.py` 读取各插件最新的 GitHub Release，识别 Windows x64、Linux x64 与 macOS arm64 的 artifact v2 ZIP，计算归档 SHA-256，并生成 `catalog.json`。
- 发布工作流每 6 小时同步一次，也可手动触发。没有兼容 artifact v2 Release 的插件仍会出现在商店中，但不提供安装按钮。

新增插件时，只需在 `sources.json` 增加一项。插件发布符合下列命名的 ZIP 后，目录会自动收录可用平台：

```text
<plugin-id>-<version>-<platform>.zip
```

每个 ZIP 必须只有一个以插件 ID 命名的顶层目录；该目录包含与 Release 版本一致的 `info.json`，以及只含 `artifact_version`、`target_platform`、`entry` 三个字段的 `artifact.json`。

本地检查当前目录：

```bash
python -m unittest discover -s tests
python scripts/sync_catalog.py --validate-only
```

当前官方插件：

- `raylea.echo`
- `raylea.fortune`
- `raylea.game-guide`
- `raylea.subscription-hub`
- `raylea.delta-force`
- `raylea.oil-price`
