# 优化与排查计划（`Chth1z/rime-chth1z`）

目标：在保留完整词库、400 MB 万象模型、`s2twp` 台湾繁体转换和英文混输的前提下，把按键延迟压低到亚毫秒级（插电 `<= 2.5 ms`、电池 `<= 8 ms`），并持续围绕小狼毫和个人双拼/全拼习惯做深度定制。

## P0 — 回归测试、合并 Lua 滤镜与主方案整合（已完成）

- [x] **建立功能回归测试（`bench/accuracy-test.ps1` ＋ `bench/accuracy-cases.json`）**
  - 覆盖 85 条用例（双拼与全拼长句、26 键置顶及开关、`corrector` 错音提示、`autocap` 大小写、中英混输与降权、`s2twp` 台湾词与简繁切换、日期/ISO 时区/农历/计算器、以词定字长句与光标中段、反引号直出，以及日志 Lua 报错检查）。
  - 同时修正 `bench/bench-rime.ps1` 里的双拼长句样本为真实有效的自然码双拼编码。
- [x] **排查 Lua 延迟根因与脚本细节问题**
  - 实测发现之前 `5–6 ms` 的主要根因是 `profiles/rime.lua` 里 `collectgarbage("incremental", 80, 300)`（`pause < 100` 导致 Lua 5.4 取消 GC 间隔持续全堆扫描），修正为 `(150, 200)` 后延迟直接下降 20 倍以上。
  - 修复全拼 `e -> 而` 不可达导致的 `19.5 ms` 尖峰（改为 `er -> 而`）；修复 `date_translator` 模块全局变量串味及 Windows ISO 时区偏移；修复 `reduce_english_filter` 少量候选丢词、`number_translator` 缺 `seg:has_tag` 及 `nil` 保护、`calculator` `load` 判空。
- [x] **合并高频 Lua 滤镜为单遍管线（`lua/chth1z_pipeline_filter.lua`）**
  - 一次遍历完成 `pin_cand`（`pin_max_scan: 40`）＋ `corrector`（跳过单字查表、模块级缓存词表）＋ `autocap`（字节首判、防正则元字符）＋ `reduce_english`（修复尾项输出）＋ 每 16 键一次轻量增量 GC 步进（移除独立 `force_gc` 翻译器）。
  - 实测（插电）：双拼 `0.1 ms / 0.3 ms`（峰值 `0.8 ms`，10,440 键压测均值 `0.17 ms`、`p99 0.46 ms`、`dMem +0.05 MB`）；全拼 `0.1 ms / 0.7 ms`（峰值 `3.0 ms`）；85 项回归测试全过。
- [x] **将核心配置直接整合进根目录主方案**
  - 整理 `default.yaml`、`melt_eng.schema.yaml`、`rime_frost_double_pinyin.schema.yaml`、`rime_frost.schema.yaml`，移除未使用的依赖与死配置（含 `librime 1.17` 已不读取的 `grammar_penalty`），`profiles/*.custom.yaml` 精简为空白留作本机临时覆盖。

## P1 — 吸收雾凇改进与 `melt_eng` 瘦身（已完成）

- [x] **升级 `lua/select_character.lua`**
  - 参考 `iDvel/rime-ice` 2025-05 版支持长句定字及光标不在句尾时保留右侧输入，并改用 `cand._end` 与 `plain` 匹配修复句首光标重复回填、重复词误替换及特殊字符问题（已入回归测试）。
- [x] **对照 `rime-ice` 修复 `pin_cand` 与 `reduce_english` 边界问题**
  - 已全部吸收到 `chth1z_pipeline_filter.lua`（分隔符 `\x1f`、`nil` 保护、同 `preedit` 边界、末尾 `pending` 必出）。
- [x] **精简 `melt_eng_algebra_common.yaml` 缩减棱镜体积**
  - 保留前 2–4 位大写派生（注释 5–10 位），`melt_eng.prism.bin` 从 `6.82 MB` 缩减至 `4.97 MB`（−27.1%），完整部署仅 `4.43 s`，回归测试全部通过。

## P2 — 解码准确率调优、台湾繁体双出、配置清理与自动更新

- [x] **建立社区语料评测脚本并完成解码参数与词库消融（`bench/eval-accuracy.py`）**
  - 复用 `gaboolic/rime-schema-compare` 公开语料与评测口径，在 1,600 句（科技周刊 200 + 知乎热榜 1,400，含 1,000 句未见验证集）与 2,956 条同段落连续子句上完成参数网格寻优及 6 组词库消融。
  - 实测将 `collocation_penalty` 从 `-14` 调至 `-15.5`、关闭跨句污染的 `contextual_suggestions`（改为 `false`），1,600 句整句率从 `74.75%` 提至 `75.94%`（知乎前 600 句 `66.50% → 69.00%`），同时每键再提速 16–20%。
  - 注释 `rime_frost.dict.yaml` 中准确率贡献为 `0.00%` 的 `41448` 与 `GB18030-2022` 生僻字表；核实 `composite` 贡献 `+1.13%` 必留、`tencent` 贡献 `0.00%` 不开、双拼下 `enable_correction` 会暴跌 15 个百分点不开。
- [x] **实现台湾繁体双出滤镜（`lua/tw_dual_filter.lua`）**
  - 替代原生单向 `simplifier@traditionalize`：繁简开关开启时，首选输出 `s2twp` 台湾用法，仅当存在词汇差异时次选紧跟 `s2tw` 台湾正体保留原词（如 `1. 程式最佳化 | 2. 程序優化`、`1. 最佳化 | 2. 優化`），关闭时透传简体，已纳入 88 项回归测试。
- [x] **配置细节与正确性体检**
  - 为方案中 `pin_cand_filter` 含 Tab 项补齐双引号，全仓库 15 份 YAML 全部通过严格 YAML 1.1/1.2 校验无告警；`default.yaml` 补回小键盘四则运算符供 `/vs` 计算器使用；`deploy-local.ps1` / `update-local.ps1` 清理 `%APPDATA%\Rime` 内 6 处早期遗留无用文件。
- [x] **把本机 Windows 定时更新切到本仓库**
  - 新增 `scripts/update-local.ps1`（由 `deploy-local.ps1` 同步至 `%APPDATA%\Rime\auto_update\Update-RimeChth1z.ps1`），Windows 计划任务已切换为 `RimeChth1zWeeklyUpdate`（每周日 03:30，紧随 GitHub Actions 02:00 词库同步），拉取 `Chth1z/rime-chth1z` 与 `wanxiang-lts-zh-hans.gram`；本地仓库干净时自动 `git pull --ff-only`，有未提交改动时走临时 zip 隔离更新。
- [x] **电池模式实测留档（2026-11-23，电量 94–95%）**
  - 纯统计双拼 `0.4 / 1.6 ms`（峰值 `5.2 ms`）；v0.2.0 神经重排双拼 **`0.4 / 4.1 ms`**（峰值 **`22.3 ms`**）、全拼 `0.3 / 9.2 ms`（峰值 `27.9 ms`）；同时修正 `bench-rime.ps1` / `accuracy-test.ps1` 的 `-WaitNeural` 等待时长（`2000 → 4500 ms`）以适配电池下约 `2.7 s` 的后台冷加载。
- [ ] **（按需）静态词库顽固冷词降权**
  - 若日常使用中遇到 `Ctrl+K` 删不掉的静态词库干扰词，再考虑轻量移植 `rime-ice` 的 `cold_word_drop`。

## P3 — 端侧神经整句重排（零魔改官方小狼毫，已完成）

- [x] **离线评估 Rime 多整句召回上限与多款开源重排模型**
  - 定位到 `librime 1.17` 默认 `translator/sentence_cutoff_threshold: 0.1` 会截断 `55.4%` 的多整句 beam；调至 `0.3`（`max_sentences: 8`）以几乎零开销把 Top-8 Oracle 拉到 `90.25%`（Top-10 `91.12%`），同时保留对高置信单候选（准确率 `97.4%`）的零开销跳过。
  - 在 1,600 句双拼语料上横向实测 `msime-4M`（`76.12%`）、`msime-25M`（`78.81%`）与 `知意 1.4V2-Long-L12` ONNX（`83.06%–84.25%`），确认联合交叉编码器架构的知意模型（Apache-2.0）表现与性价比最优。
- [x] **编写原生 Rust Lua 5.4 ONNX 模块并接入官方未修改小狼毫（`native/rime_zhiyi/` ＋ `lua/zhiyi_rerank_filter.lua`）**
  - 利用小狼毫 `rime.dll` 导出的 154 个 Lua 5.4 C API 符号动态绑定，无需重新编译 `rime.dll`；使用 `GetModuleHandleExA(PIN)` 钉驻进程解决重新部署卸载崩溃，配合后台异步预热（0 ms 启动延迟）、256 条 LRU 缓存、自然码全音节双射还原、`t2s.json` 繁体上下文归一化与严格 `sentence`-only 门控。
  - 配套一键构建/校验安装脚本 `scripts/install-zhiyi-reranker.ps1`（SHA-256 校验模型包）；未安装模型或关闭 `neural_rerank` 时自动零开销透传。
  - 官方小狼毫 `0.17.4` 端到端实测通过：1,600 句双拼整句率 `75.12% → 81.31%`（科技 `81.00% → 90.50%`，全拼科技 `80.50% → 91.50%`），插电按键均值 `2.1 ms` / 峰值 `12.9 ms`，3 轮连续重新部署零崩溃，88/88 回归测试全过。

## P4 — 神经重排 v0.2.0（KV-cache ＋ `.gram` 融合 ＋ P2C ＋ 个人反馈闭环）与仓库架构收口（已完成）

- [x] **升级 `知意 ML-pumpkin-1103` 融合前缀 KV-cache ONNX（`laya.one.fused.int8g.onnx`，Apache-2.0）**
  - 在 `native/rime_zhiyi` 实现 16 槽前缀 KV-cache 缓存与零拷贝 `TensorRef` 传入，上下文编码与按键解码彻底解耦。
  - 官方小狼毫插电实测双拼按键压至 **`1st-key 0.1 ms / rest 1.6 ms / 峰值 9.8 ms`**（全拼 `4.2 ms / 峰值 12.6 ms`），同时 1,600 句无上下文 live 整句率从 `79.44%` 跃升至 **`80.75%`**，真实 `commit_history` 跃升至 **`81.94%`**（离线带标点上下文 **`84.31%–84.5%`**，盲测验证集 **`83.80%`**）。
- [x] **直接共享内存映射 `wanxiang-lts-zh-hans.gram` ＋ 零开销 `char_logits` P2C 候选合成**
  - 新增 `native/rime_zhiyi/src/gram.rs`（Win32 `CreateFileMappingW` 零额外物理内存复用 `Rime::Grammar/1.0` Darts trie，`~0.01 ms` 查出精确 N-gram 逐字对数分差），配合五维低维先验融合 `[0.91, -1.26, 0.05, 0.40, -0.39]` 将神经误改量压低近一半（`-33 → -18`）。
  - 同次 ONNX 前向解码 `char_logits` 头，对高置信 OOV 人名/热词在首/次位合成神经候选（合并召回上限 **`92.06%`**，零额外推理耗时）。
- [x] **隐私优先本地选词反馈记录与离线个体权重校准**
  - 新增 `native/rime_zhiyi/src/feedback.rs` 与 `lua/zhiyi_rerank_filter.lua` `commit_notifier` 挂钩（严格在首次 `yield` 前保存候选快照，避开 Rime `Menu` 懒求值协程暂停）：自动脱敏数字串/邮箱/URL 为 `<REDACTED>`、截断上下文 64 字、5 MiB 自动轮转、全量记录翻页纠错＋10% 抽样首项确认，测试临时目录自动关闭不污染线上日志。
  - 新增 `scripts/tune-personal-fusion.py`：在通用先验附近以 5 折交叉验证 L2 岭回归微调 5 维权重（样本 `< 30` 条时自动保护不改先验）。
- [x] **仓库架构清理与全量代码审计**
  - 删除 `lua/` 中 12 个未被引用的上游遗留脚本（仅留 7 个活跃脚本），更新 `deploy-local.ps1` / `update-local.ps1` 自动清理旧文件并同步 `opencc/t2s.json`；修正 `install-zhiyi-reranker.ps1` NuGet ORT 版本回退与 SHA-256 校验；通过 3/3 Rust 单元测试、88/88 冷/热回归测试与 3 轮重新部署零崩溃验证。
- [x] **v0.3.0 开源级通用架构重构、Windows UIA 跨应用上下文与 Pass-2 校验 P2C（已完成）**
  - **通用全布局支持（`src/pinyin.rs`）**：重构为数据驱动 `PinyinLayout`，自动识别并支持全拼 ＋ 7 种主流 Rime 双拼（自然码 / 小鹤 / 微软 / 搜狗 / 智能 ABC / 紫光 / 拼音加加，完整兼容微软/搜狗/紫光的分号 `;` 韵母键），通过全 7 套方案 × 425 音节穷举往返单测。
  - **KV 缓存 Pass-2 跨编码器 ＋ `.gram` 交叉验证 P2C（`src/zhiyi.rs`）**：仅对 `7.7%` 高潜力新颖 P2C 候选复用前缀 KV-cache 做 3 候选直面校验，同时在有/无上下文生效；离线带标点上下文推至 **`85.19%`**（盲测验证 **`84.60%`**，`+15/-1`），官方小狼毫无标点连续实跑推至 **`82.31%`**（文字 **`97.00%`**），全拼科技零上下文 **`91.00%`**（文字 `98.67%`）。
  - **非阻塞后台 Windows UIA 跨应用光标前文（`src/uia.rs`）**：独立 STA 线程读取光标前 64 字、自动剥离行内预编辑串；热路径仅同步比对 `HWND` ＋ 读取短锁快照（`< 2 µs`，永不阻塞），切窗口立刻清空旧窗口上下文防跨应用串味，硬屏蔽 `IsPassword` 与常见密码管理器进程；3 轮热部署 0 崩溃、0 Lua 报错。
  - **CI/CD 与开源发布准备**：新增 `.github/workflows/build-native-reranker.yml`（`cargo fmt --check` ＋ 严格 `clippy -D warnings` ＋ `cargo test` ＋ Windows x64 预编译包与 SHA-256）、`scripts/install-zhiyi-reranker.ps1 -PrebuiltDll`、`docs/neural-reranker-guide.md`；Rust 模块协议已切为 `Apache-2.0`，待确定正式仓库命名后即可一键拆出独立开源插件仓库。
- [ ] **拆分独立开源插件仓库（待定最终命名）**
  - 将已打磨完毕的 `native/rime_zhiyi/`、`lua/zhiyi_rerank_filter.lua`、安装/调参脚本与 CI workflow 拆至独立 Apache-2.0 仓库并发布首个带预编译 DLL 的 GitHub Release。
