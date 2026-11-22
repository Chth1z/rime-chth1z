# 上游 Issue 记录

按 [GUIDELINE.md](GUIDELINE.md) 记录已经提过和顺手发现的上游问题（平时优化与使用中遇到真 Bug 再记，不刻意刷 Issue）。

| 日期 | 上游仓库 | 类型 | 内容 | 状态 | 链接 / 结果 | 备注 |
|---|---|---|---|---|---|---|
| 2026-11-22 | `gaboolic/rime-frost` | Bug | `lunar.lua:553` 缺 `seg:has_tag` 且 `nil` 拼接报错 | 已修复 | PR `#414` (`5532b4f` / `caf787fe`) | 上游已合并 |
| 2026-11-22 | `gaboolic/rime-frost` | 性能 | 7 套方案的 `pin_cand_filter` 在单字母下放了不可达多字词，导致首键空扫 101 候选 | 已修复 | [Issue #420](https://github.com/gaboolic/rime-frost/issues/420) / [PR #423](https://github.com/gaboolic/rime-frost/pull/423) (`4fade2a`) | 上游已合并（仅保留单字固顶并去重计数）；干净上游复测自然码 `w`：`1.44 → 0.30 ms`（上游 13700KF `4.62 → 0.65 ms`），当时报的 `52.7 / 180.7 ms` 被本地旧 `rime.lua` 的 `inc(80, 300)` 放大；全拼 `e -> 而` 仍不可达 |
| 2026-11-22 | `gaboolic/rime-frost` | Bug | `lua/number_translator.lua:148-151` 缺 `seg:has_tag("number")` 且 `get_string` 没判 `nil` | 本仓库已修 / 待顺手汇总 | — | 已在本仓库修复，待后续有空时决定是否顺手反馈上游 |
| 2026-11-22 | `gaboolic/rime-frost` | Bug | `lua/reduce_english_filter.lua:99-105` 候选总数不足时 `pending_cands` 未输出会被吞掉（`rime-ice` 已修，白霜未同步） | 本仓库已修 / 待顺手汇总 | — | 本仓库在 `reduce_english_filter.lua` 与 `chth1z_pipeline_filter.lua` 均已修复 |
| 2026-11-22 | `gaboolic/rime-frost` | 配置 | `translator/grammar_penalty` 是否仍有作用 | 已核实（不提） | — | 已查 `rime.dll`（`librime 1.17.0`）确无该键名，但无实际负面影响，本仓库已删除、不打扰上游 |
