# rime-chth1z

个人自用的 Rime 配置仓库，主要配合 Windows 下的小狼毫（Weasel）使用。

日常以自然码双拼为主、全拼为辅，搭配白霜词库、万象语法模型和台湾繁体词表（`s2twp`）。仓库主要用于存放个人配置、自用外观、按键延迟测试脚本，以及顺手做一些 Lua 脚本和方案上的优化与修复。

> 这是高度按个人习惯改过的配置，只照顾自己常用的小狼毫环境；如果需要通用方案，建议直接使用上游项目。

## 来源与致谢

- [gaboolic/rime-frost（白霜拼音）](https://github.com/gaboolic/rime-frost)：词库（`cn_dicts/`、`cn_dicts_cell/`、`en_dicts/`）、OpenCC 词表和初始方案的来源（起始版本 `970a6d6`），词库部分每周自动同步上游。
- [iDvel/rime-ice（雾凇拼音）](https://github.com/iDvel/rime-ice)：白霜的上游，不少 Lua 脚本和方案写法参考了这里。
- [rime/weasel（小狼毫）](https://github.com/rime/weasel) / [rime/librime](https://github.com/rime/librime)：Windows 客户端与核心引擎。
- [amzxyz/rime-wanxiang-data](https://github.com/amzxyz/rime-wanxiang-data)：配合使用的 `wanxiang-lts-zh-hans.gram` 语法模型（体积较大，不放进本仓库）。

## 目录说明

- `cn_dicts/`、`cn_dicts_cell/`、`en_dicts/`、`opencc/`：自动同步自白霜上游的词库与词表
- `lua/`：保留并自行修改的 Lua 脚本
- `profiles/`：个人用的 `*.custom.yaml` 补丁和 `rime.lua`
- `themes/`：小狼毫外观配置
- `bench/`：调用本机 `rime.dll` 测按键耗时的脚本
- `scripts/`：本地同步词库、查看上游更新、部署到 `%APPDATA%\Rime` 的脚本
- `docs/upstream-issues/`：向上游反馈问题的约定、模板和记录
- `PROJECT_CONTEXT.md` / `ROADMAP.md`：背景记录与待办清单

## 自动任务

- `.github/workflows/sync-upstream-dicts.yml`：每周日自动从 `gaboolic/rime-frost` 同步词库和 OpenCC 数据，不动自定义代码和配置。
- `.github/workflows/upstream-watch.yml`：每周一查看白霜、雾凇（`lua/`）、小狼毫 Nightly 和万象模型的新变化，汇总到一个固定 Issue 里方便翻看。

## 协议

沿用上游协议，按 [GNU GPL v3.0](LICENSE) 开源，保留原有版权说明并标明修改来源。
