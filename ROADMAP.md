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
- [x] **跨领域防过拟合审计与无偏个人调参重构（已完成）**
  - 在 840 句完全未触碰过的新闻/小说/散文/旧科技/08-30 知乎语料上实跑盲测，抓出并移除在知乎开发集轻微领域过拟合的 `w_ctx_lp = -0.39` 项，切回跨领域最优通用先验 `[1.0, -1.4, 0.05, 0.15, 0.0]`（840 句 OOD `60.48% → 68.57%`，文字 `93.52%`）。
  - 抓出旧版 `tune-personal-fusion.py` 因 10% 首项抽样选择偏差＋30 样本阈值导致的严重过拟合（零假设 25/25 伤精度），改为 100% 无偏日志＋Newton MAP＋5 折 NLL＋成对 95% 置信检验（`min_samples = 100`），25 轮仿真零假设误伤 `0/25`、真实偏移检出 `88%–100%`。
- [x] **拆分独立开源插件仓库 [`Chth1z/rime-neural`](https://github.com/Chth1z/rime-neural) 并发布正式版 `v1.0.0`**
  - 将端侧神经重排拆至独立 Apache-2.0 仓库 `Chth1z/rime-neural`（`rime_neural.dll` ＋ `lua/rime_neural.lua` ＋ 通用示例配置 ＋ 自动编译发版 CI ＋ 一键安装/MAP 调参脚本），并在发版前完成深度全面审计与优化：
    - 修复自然码 `ZERO_ZRM` 缺失 5 项自引零声母别名（`aj/ak/al/ef/ez`），3,008 项 7 大双拼全量码表 0 失配；修复全拼 `walk` 缺少记忆化可能导致最坏指数回溯问题并尊重显式 `'` 分隔符；
    - 修复 Electron/Chromium 下 UIA 跨出输入框泄漏周边按钮文字问题（`RangeFromChild` 钳制 ＋ `U+FFFC` 截断）、首键异步预热、窗口切换竞态与 `s2twp` 反馈抓取原词；
    - 新增 ONNX 模型动态层数/头数与 `choice_compact` 自省（同时支持 12 层 `ML-pumpkin-1103` 与 8 层 `zhen-feather`）、选择性 ORT 输出裁剪、零 HashMap 分配 `char_logits` 解码、零堆分配 `.gram` 评分与真 LRU 缓存。
  - `rime-chth1z` 同步移除重复的原生源码，改为直接消费 `Chth1z/rime-neural` 正式 Release（`scripts/install-rime-neural.ps1` 与周更脚本 `update-local.ps1` 自动校验 SHA-256 升级），同时完成自用部分体检（修复 `calculator.lua` 超大阶乘上限、`lunar.lua` 整理为 `M.init` 模块并移除死函数、`chth1z_pipeline_filter.lua` `autocap` 保留 `preedit`、清理主方案死 `recognizer` 正则）。

## P5 — 词库 SSOT 治理体系、AI Agent 技能包与双仓库安全/可靠性全面升级（已完成）

- [x] **建立声明式词库治理层（`rules/` SSOT ＋ `docs/DICTIONARY_SPEC.md` ＋ 四级上线门禁）**
  - 收口全部 10,183 条词库覆写规则至 `rules/`（12 份纯文本表），统一由 `scripts/dict_common.py`、`scripts/clean-dicts.py`、`scripts/dict_rules.py`、`scripts/build_cn_en.py` 确定性重放（前置字形规范化 → `rules/` 权威覆写 → 生成器 → 保权跨表去重 → 内存态全量校验 → 原子落盘），消除全部二次运行往复漂移。
  - `scripts/dict_lint.py` 覆盖 5 项零容忍不变量、严格无 BOM UTF-8、YAML 重复键、`rime_frost.dict.yaml` 活跃词表顺序一致性、跨词库同词异读守卫、A/B/C 同音碰撞护栏、对称差异 `--diff-budget` 熔断（含全部 7 份 `cn_en*.txt`）与内存态幂等校验；配套 18 项单元测试 `tests/test_dict_pipeline.py`。
- [x] **AI Agent 一键安装与验收技能包（`skills/rime-chth1z-setup/`）与 `rime-neural v1.1.0+` 零明文反馈升级**
  - 新增独立免依赖的 `inspect-env.ps1`、`bootstrap.ps1`、`verify-setup.ps1`（PE32+ 导出表 Lua 5.4 检测、全链路 SHA-256 闭环校验、非生成 `*.custom.yaml` 自动备份、部署日志精准锚定）。
  - 配合 `Chth1z/rime-neural` 升级至 Rust Edition 2024、零明文纯数值 v2 反馈、单遍 `.gram` 前向 trie、令牌级 KV-cache 与 fail-closed MTA UIA。
- [x] **安全加固、零残留压测架构与 CI 门禁（`.github/workflows/ci.yml`）**
  - `lua/calculator.lua` 重写为纯 Lua 递归下降解析器（彻底消除 `load()` 字符串元表沙箱逃逸与 ReDoS/OOM 风险，并修复浮点阶乘、溢出、负零与 Welford 均值/方差）；`chth1z_pipeline_filter.lua` 改为活跃分段驱动并精确保护驼峰品牌词；`tw_dual_filter.lua` 增加 `tags_match` 与 `pcall`；`date_translator.lua` 改用 UCRT `%z` 防 DST 偏差；`select_character.lua` 改用 `toSegmentation()` 精确前缀提取；清理 `rime_frost.schema.yaml` 3 条全拼高频英文劫持 `fuzz/` 规则与 `melt_eng_algebra_common.yaml` 冗余规则。
  - `bench/{accuracy-test,audit-surface,bench-rime}.ps1` 与 `bench/eval-accuracy.py` 全部升级为父子进程隔离沙箱（退出后释放 `rime.dll`/glog 句柄并动态安全卸载 NTFS Junction，实测 `%TEMP%` 零残留），回归测试扩充至 329 项大小写敏感用例并通过 `audit-surface.ps1` 全表面巡检。
  - 新增 `push`/`pull_request` CI 门禁 `.github/workflows/ci.yml`，统一全仓 `.ps1` 为无 BOM 纯 ASCII 并修复 `.gitattributes` 行尾一致性。
