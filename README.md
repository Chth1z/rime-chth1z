# rime-chth1z

个人自用的 Rime 配置仓库，主要配合 Windows 下的小狼毫（Weasel）使用。

日常以自然码双拼为主、全拼为辅，搭配白霜词库、万象语法模型和台湾繁体双出转换（首选 `s2twp` 台湾用法、次选 `s2tw` 台湾正体保留原词）。仓库主要用于存放个人配置、自用外观、回归与准确率/延迟测试脚本，以及对 Lua 脚本和方案参数做针对性优化。

> 这是高度按个人习惯改过的配置，只照顾自己常用的小狼毫环境；如果需要通用方案，建议直接使用上游项目。

## 来源与致谢

- [gaboolic/rime-frost（白霜拼音）](https://github.com/gaboolic/rime-frost)：词库（`cn_dicts/`、`cn_dicts_cell/`、`en_dicts/`）、OpenCC 词表和初始方案的来源（起始版本 `970a6d6`），词库部分每周自动同步上游。
- [iDvel/rime-ice（雾凇拼音）](https://github.com/iDvel/rime-ice)：白霜的上游，不少 Lua 脚本和方案写法参考了这里。
- [gaboolic/rime-schema-compare](https://github.com/gaboolic/rime-schema-compare)：离线整句与文字准确率评测口径参考来源。
- [rime/weasel（小狼毫）](https://github.com/rime/weasel) / [rime/librime](https://github.com/rime/librime)：Windows 客户端与核心引擎。
- [amzxyz/rime-wanxiang-data](https://github.com/amzxyz/rime-wanxiang-data)：配合使用的 `wanxiang-lts-zh-hans.gram` 语法模型（体积较大，不放进本仓库）。
- [dd1000001000/zhiyi_ime（知意输入法）](https://github.com/dd1000001000/zhiyi_ime) / [dd1000001000/zhiyi_models](https://github.com/dd1000001000/zhiyi_models)：可选的端侧神经整句重排模型 `知意 ML-pumpkin-1103` int8 KV-cache ONNX（Apache-2.0，由安装脚本按需下载并做 SHA-256 校验，不入 Git）。

## 目录说明

- `cn_dicts/`、`cn_dicts_cell/`、`en_dicts/`、`opencc/`：自动同步自白霜上游的词库与词表
- `lua/`：仅保留 7 个实际启用脚本——端侧神经重排滤镜（`zhiyi_rerank_filter.lua`）、单遍合并管线（`chth1z_pipeline_filter.lua`）、台湾繁体双出滤镜（`tw_dual_filter.lua`）及日期/农历/计算器/以词定字脚本（其余未引用上游脚本已清理）
- `native/rime_zhiyi/`：Rust 编写的 Lua 5.4 原生扩展模块（v0.3.0，Apache-2.0），动态解析官方小狼毫 `rime.dll` 导出的 Lua C API，支持全拼与 7 种主流双拼、前缀 KV-cache ONNX 推理、`.gram` 共享内存映射、KV 缓存 Pass-2 交叉验证 P2C 合成、非阻塞后台 Windows UIA 跨应用上下文（窗口隔离防串味＋密码框硬屏蔽）及本地脱敏反馈记录，无需重新编译 `rime.dll`（详见 [docs/neural-reranker-guide.md](docs/neural-reranker-guide.md)）
- `profiles/`：`rime.lua`（Lua 5.4 GC 调优）及留空的 `*.custom.yaml`（核心配置已收口至根目录方案）
- `themes/`：小狼毫外观配置（`apple_graphite_dark`）
- `bench/`：调用本机 `rime.dll` 的功能回归测试（`accuracy-test.ps1`）、按键耗时测试（`bench-rime.ps1`）和语料准确率评测（`eval-accuracy.py`）
- `scripts/`：本地同步词库、查看上游更新、编译安装神经重排模块（`install-zhiyi-reranker.ps1`）、个人融合权重离线校准（`tune-personal-fusion.py`）、部署到 `%APPDATA%\Rime` 及本机周更脚本
- `docs/`：神经重排模块通用接入指南（`neural-reranker-guide.md`）及向上游反馈问题的约定与记录（`upstream-issues/`）
- `PROJECT_CONTEXT.md` / `ROADMAP.md`：背景记录与待办清单

## 自动任务

- `.github/workflows/build-native-reranker.yml`：每次修改原生模块时自动运行 `cargo fmt`、`cargo clippy`、`cargo test` 并产出 Windows x64 `rime_zhiyi.dll` 预编译包与 SHA-256。

- `.github/workflows/sync-upstream-dicts.yml`：每周日 02:00（UTC+8）自动从 `gaboolic/rime-frost` 同步词库和 OpenCC 数据，不动自定义代码和配置。
- `scripts/update-local.ps1`（本机任务 `RimeChth1zWeeklyUpdate`）：每周日 03:30（UTC+8）拉取本仓库和万象 LTS 模型并部署到 `%APPDATA%\Rime`。
- `.github/workflows/upstream-watch.yml`：每周一查看白霜、雾凇（`lua/`）、小狼毫 Nightly 和万象模型的新变化，汇总到一个固定 Issue 里方便翻看。

## 协议

沿用上游协议，按 [GNU GPL v3.0](LICENSE) 开源，保留原有版权说明并标明修改来源。
