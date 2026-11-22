# rime-chth1z

个人自用的 Rime 配置仓库，主要配合 Windows 下的小狼毫（Weasel）使用。

日常以自然码双拼为主、全拼为辅，搭配白霜词库、万象语法模型、可选端侧神经整句重排（[Chth1z/rime-neural](https://github.com/Chth1z/rime-neural)）和台湾繁体双出转换（首选 `s2twp` 台湾用法、次选 `s2tw` 台湾正体保留原词；全局记忆上次切换状态，`Claude` 桌面端默认臺繁、其余默认简中）。

> 这是高度按个人习惯改过的配置，只照顾自己常用的小狼毫环境；如果需要通用方案或独立神经重排插件，建议使用上游方案或 [Chth1z/rime-neural](https://github.com/Chth1z/rime-neural)。

## 来源与致谢

- [gaboolic/rime-frost（白霜拼音）](https://github.com/gaboolic/rime-frost)：词库（`cn_dicts/`、`cn_dicts_cell/`、`en_dicts/`）、OpenCC 词表和初始方案的来源（起始版本 `970a6d6`），词库部分每周自动同步上游。
- [iDvel/rime-ice（雾凇拼音）](https://github.com/iDvel/rime-ice)：白霜的上游，不少 Lua 脚本和方案写法参考了这里。
- [Chth1z/rime-neural](https://github.com/Chth1z/rime-neural)：本仓库拆出的独立 Apache-2.0 端侧 ONNX 神经整句重排插件（通过官方 GitHub Release 安装与自动更新，未安装或关闭 `neural_rerank` 时自动零开销透传）。
- [gaboolic/rime-schema-compare](https://github.com/gaboolic/rime-schema-compare)：离线整句与文字准确率评测口径参考来源。
- [rime/weasel（小狼毫）](https://github.com/rime/weasel) / [rime/librime](https://github.com/rime/librime)：Windows 客户端与核心引擎。
- [amzxyz/rime-wanxiang-data](https://github.com/amzxyz/rime-wanxiang-data)：配合使用的 `wanxiang-lts-zh-hans.gram` 语法模型（体积较大，不放进本仓库）。

## 目录说明

- `cn_dicts/`、`cn_dicts_cell/`、`en_dicts/`、`opencc/`：自动同步自白霜上游的词库与词表
- `lua/`：仅保留 6 个自用核心脚本——单遍合并管线（`chth1z_pipeline_filter.lua`）、台湾繁体双出滤镜（`tw_dual_filter.lua`）及日期/农历/计算器/以词定字脚本（神经重排脚本 `rime_neural.lua` 与原生 DLL 由 `Chth1z/rime-neural` 发行包管理）
- `profiles/`：`rime.lua`（Lua 5.4 GC 调优）及留空的 `*.custom.yaml`（核心配置已收口至根目录方案）
- `themes/`：小狼毫外观配置（`apple_graphite_dark`，含 `claude.exe` / `claude-desktop.exe` `app_options` 臺繁设定）
- `bench/`：调用本机 `rime.dll` 的功能回归测试（`accuracy-test.ps1`）、按键耗时测试（`bench-rime.ps1`）和语料准确率评测（`eval-accuracy.py`）
- `scripts/`：本地同步词库、查看上游更新、安装/升级官方 `Chth1z/rime-neural`（`install-rime-neural.ps1`）、部署到 `%APPDATA%\Rime` 及本机周更脚本
- `docs/`：向上游反馈问题的约定与记录（`upstream-issues/`）
- `PROJECT_CONTEXT.md` / `ROADMAP.md`：背景记录与待办清单

## 自动任务

- `.github/workflows/sync-upstream-dicts.yml`：每周日 02:00（UTC+8）自动从 `gaboolic/rime-frost` 同步词库和 OpenCC 数据，不动自定义代码和配置。
- `scripts/update-local.ps1`（本机任务 `RimeChth1zWeeklyUpdate`）：每周日 03:30（UTC+8）拉取本仓库、`Chth1z/rime-neural` 最新正式发行版和万象 LTS 模型并部署到 `%APPDATA%\Rime`。
- `.github/workflows/upstream-watch.yml`：每周一查看白霜、雾凇（`lua/`）、`rime-neural`、知意模型、小狼毫 Nightly 和万象模型的新变化，汇总到一个固定 Issue 里方便翻看。

## 协议

沿用上游协议，按 [GNU GPL v3.0](LICENSE) 开源，保留原有版权说明并标明修改来源。
