# rime-chth1z

个人自用的 Rime 配置仓库，面向 Windows 小狼毫（Weasel）环境。

日常以自然码双拼为主、全拼为辅，搭配白霜词库、万象语法模型、可选端侧神经整句重排（[Chth1z/rime-neural](https://github.com/Chth1z/rime-neural)）和台湾繁体双出转换（首选 `s2twp` 台湾用法，存在词汇差异时次选 `s2tw` 台湾正体保留原词；全局记忆上次切换状态，`Claude` 桌面端默认臺繁，其余应用默认简中）。

> 本仓库按个人习惯定制；如需通用拼音方案或独立神经重排插件，请直接使用上游方案或 [Chth1z/rime-neural](https://github.com/Chth1z/rime-neural)。

## 来源与致谢

- [gaboolic/rime-frost（白霜拼音）](https://github.com/gaboolic/rime-frost)：词库（`cn_dicts/`、`cn_dicts_cell/`、`en_dicts/`）、OpenCC 词表与初始方案来源（起始版本 `970a6d6`），词库目录每周自动同步上游。
- [iDvel/rime-ice（雾凇拼音）](https://github.com/iDvel/rime-ice)：白霜上游，部分 Lua 脚本与方案写法参考于此。
- [Chth1z/rime-neural](https://github.com/Chth1z/rime-neural)：独立的 Apache-2.0 端侧 ONNX 神经整句重排插件，通过 GitHub Release 安装与自动更新。
- [amzxyz/rime-wanxiang-data](https://github.com/amzxyz/rime-wanxiang-data)：配合使用的 `wanxiang-lts-zh-hans.gram` 语法模型（按需下载至本地 Rime 目录，不入本仓库）。
- [gaboolic/rime-schema-compare](https://github.com/gaboolic/rime-schema-compare)：离线整句与文字准确率评测口径参考来源。
- [rime/weasel（小狼毫）](https://github.com/rime/weasel) / [rime/librime](https://github.com/rime/librime)：Windows 客户端与核心引擎。

## 目录说明

- `cn_dicts/`、`cn_dicts_cell/`、`en_dicts/`、`opencc/`：同步自白霜上游并经 `scripts/clean-dicts.py` 清洗校准的词库与 OpenCC 词表
- `lua/`：6 个自用脚本——单遍合并管线（`chth1z_pipeline_filter.lua`）、台湾繁体双出滤镜（`tw_dual_filter.lua`，支持单字一简对多繁展开）以及日期、农历、计算器、以词定字脚本；神经重排脚本 `rime_neural.lua` 与原生 DLL 由 `Chth1z/rime-neural` 发行包管理
- `profiles/`：`rime.lua`（Lua 5.4 GC 参数）及预留的本机临时覆盖文件 `*.custom.yaml`
- `themes/`：小狼毫外观配置（`apple_graphite_dark`，含 `claude.exe` / `claude-desktop.exe` `app_options` 臺繁设定）
- `bench/`：调用本机 `rime.dll` 的功能回归测试（`accuracy-test.ps1`）、按键耗时测试（`bench-rime.ps1`）与语料准确率评测（`eval-accuracy.py`）
- `scripts/`：本地同步与清洗词库（`sync-dicts-local.ps1`、`clean-dicts.py`）、检查上游更新、安装或升级 `Chth1z/rime-neural`（`install-rime-neural.ps1`）、本地部署（`deploy-local.ps1`）及本机周更脚本（`update-local.ps1`）
- `docs/`：向上游反馈问题的约定与记录（`upstream-issues/`）
- `PROJECT_CONTEXT.md` / `ROADMAP.md`：项目背景记录与优化清单

## 自动任务

- `.github/workflows/sync-upstream-dicts.yml`：每周日 02:00（UTC+8）自动从 `gaboolic/rime-frost` 同步词库与 OpenCC 文本词表，并运行 `scripts/clean-dicts.py` 执行清洗与不变量校验。
- `scripts/update-local.ps1`（本机任务 `RimeChth1zWeeklyUpdate`）：每周日 03:30（UTC+8）检查并拉取本仓库、`Chth1z/rime-neural` 最新发行版与万象 LTS 模型，随后部署至 `%APPDATA%\Rime`。
- `.github/workflows/upstream-watch.yml`：每周一追踪白霜、雾凇（`lua/`）、`rime-neural`、知意模型、小狼毫 Nightly 与万象模型的新版本，并汇总至固定 Issue。

## 协议

沿用上游协议，按 [GNU GPL v3.0](LICENSE) 开源，保留原有版权说明并标明修改来源。
