# 优化与排查计划（`Chth1z/rime-chth1z`）

目标：在保留完整词库、400 MB 万象模型、`s2twp` 台湾繁体转换和英文混输的前提下，继续压低按键延迟（插电 `<= 2.5 ms`、电池 `<= 8 ms`），同时把现有 Lua 脚本过一遍，修掉真正影响使用的问题。

## P0 — 先做回归测试，再合并 Lua 滤镜与查 Bug

- [ ] **写一份功能回归测试（`bench/accuracy-test.ps1`）**
  - 改 Lua 之前先用 `rime.dll` 固定一批测试用例：双拼/全拼长句首选、单字置顶、`corrector` 错音提示、`autocap` 大小写、中英混输（`RTX4090` / `Nous` / `VEGF` / `HEllo`）、`s2twp` 台湾词、日期/农历/计算器，确保提速不会把功能改坏。
- [ ] **过一遍 `lua/*.lua`，核实真正有影响的 Bug**
  - 逐个检查仓库里的 16 个 Lua 文件，看有没有会实际触发报错、误拦截候选或明显浪费性能的地方（比如待复现的 `number_translator.lua` 缺少 `seg:has_tag("number")` 和 `nil` 保护）。
  - 确认是真 Bug 且在干净上游配置下能复现的，按 [`docs/upstream-issues/GUIDELINE.md`](docs/upstream-issues/GUIDELINE.md) 整理好发给上游，并在 [`TRACKER.md`](docs/upstream-issues/TRACKER.md) 里记一笔。
- [ ] **把几个高频 Lua 滤镜合并成一次遍历**
  - 现在 `pin_cand_filter`、`corrector`、`autocap_filter`、`reduce_english_filter` 各自挂一层，每次按键要来回穿 4 次 C++↔Lua，插电占 4.0 ms（电池约 13 ms）。
  - 准备合成一个滤镜（如 `lua/chth1z_pipeline_filter.lua`），一遍遍历做完置顶（带更合理的扫描上限）、跳过单字的 `corrector`、大小写修正和英文降权，并测一下 `force_gc` 能不能降频或去掉。
  - 验收：插电 `<= 2.5 ms`、电池 `<= 8 ms`，`accuracy-test.ps1` 全部通过。
- [ ] **把改动直接写进本仓库的主方案**
  - 直接在 `rime_frost_double_pinyin.schema.yaml` 和 `rime_frost.schema.yaml` 里修正 `pin_cand_filter`、滤镜顺序和不需要的依赖，减少 `profiles/*.custom.yaml` 反复打补丁。

## P1 — 参考雾凇改动与 `melt_eng` 瘦身

- [ ] **看下 `iDvel/rime-ice` 新版 `select_character.lua`**（长句定字和光标不在句尾时的处理），合适就搬过来。
- [ ] **对照 `rime-ice` 近期 `pin_cand_filter.lua` 的边界修复**。
- [ ] **测一下 `melt_eng` 棱镜（目前 `6.82 MB`）能不能缩减**：看看把 `melt_eng_algebra_common.yaml` 里前 2–10 位大写派生缩成前 2–4 位配合 `autocap_filter`，对部署速度、内存和英文首选有没有负面影响。

## P2 — 词库清理、繁体细节与本机自动更新

- [ ] **试试做一份可选的精简词库入口（`rime_frost_clean.dict.yaml`）**
  - 上游词库照常全量同步，另写脚本统计哪些扩展词库（如 `41448`、`GB18030-2022`、`game`、`luna`）容易冒出冷僻词，对比去掉后的首选率和部署耗时。
- [ ] **微调个别 `s2twp` 词条**
  - 保留常用的台湾信息词（`軟體 / 資訊 / 記憶體 / 網路 / 滑鼠 / 預設 / 檔案`），看需要把个别不太习惯的词（比如 `优化` 保留 `優化`）单独覆盖。
- [ ] **把本机 Windows 定时更新切到本仓库**
  - 让 `RimeFrostWeeklyUpdate` 改成拉 `Chth1z/rime-chth1z` 和 `wanxiang-lts-zh-hans.gram`。
