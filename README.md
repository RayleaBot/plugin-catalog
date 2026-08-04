# RayleaBot Plugin Catalog

本仓库维护 RayleaBot 插件商店的静态目录。`catalog.json` 是待签名的目录正文；发布工作流使用 Ed25519 对文件的原始字节签名，并生成 `catalog.sig.json`。RayleaBot Server 只接受通过内置公钥注册表验证的目录，不从插件 manifest 推导官方身份、发布者身份或下载摘要。

目录中的每个版本必须列出 Windows x64、Linux x64 和 macOS arm64 的 GitHub Release ZIP、归档大小、归档 SHA-256 与 `info.json` SHA-256。插件发布仓库完成三平台 Release 后，再在本仓库增加对应 release 条目。

签名工作流需要仓库 secret `PLUGIN_CATALOG_SIGNING_KEY_PEM` 和 variable `PLUGIN_CATALOG_SIGNING_KEY_ID`。密钥轮换期间还可配置 `PLUGIN_CATALOG_SECONDARY_KEY_PEM` 与 `PLUGIN_CATALOG_SECONDARY_KEY_ID`。签名文件由工作流提交，私钥不得进入仓库、日志或插件包。

当前目录预先列出以下官方发布者条目；在 release 数组为空时，商店会显示“尚未发布”，不会提供安装操作：

- `raylea.echo`
- `raylea.fortune`
- `raylea.game-guide`
- `raylea.subscription-hub`

