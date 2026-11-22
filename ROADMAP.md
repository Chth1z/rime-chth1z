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

## P2 — 词库清理、繁体细节与本机自动更新

- [ ] **试试做一份可选的精简词库入口（`rime_frost_clean.dict.yaml`）**
  - 上游词库照常全量同步，另写脚本统计哪些扩展词库（如 `41448`、`GB18030-2022`、`game`、`luna`）容易冒出冷僻词或干扰词（例如顺手看下 `xianzaiyongxialaihaiyouyixieyanchi` 为何将 `鹽池` 排在 `延遲` 前面），对比去掉后的首选率和部署耗时。
- [ ] **微调个别 `s2twp` 词条**
  - 保留常用的台湾信息词（`軟體 / 資訊 / 記憶體 / 網路 / 滑鼠 / 預設 / 檔案`），看需要把个别不太习惯的词（比如 `优化` 保留 `優化`）单独覆盖。
- [x] **把本机 Windows 定时更新切到本仓库**
  - 新增 `scripts/update-local.ps1`（由 `deploy-local.ps1` 同步至 `%APPDATA%\Rime\auto_update\Update-RimeChth1z.ps1`），Windows 计划任务已切换为 `RimeChth1zWeeklyUpdate`（每周日 03:30，紧随 GitHub Actions 02:00 词库同步），拉取 `Chth1z/rime-chth1z` 与 `wanxiang-lts-zh-hans.gram`；本地仓库干净时自动 `git pull --ff-only`，有未提交改动时走临时 zip 隔离更新。
- [ ] **电池模式实测留档**
  - 下次拔电时顺手跑一次 `bench/bench-rime.ps1`，补全 `PROJECT_CONTEXT.md` 的电池实测值。
