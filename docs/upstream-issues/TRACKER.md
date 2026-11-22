# 上游 Issue 记录

按 [GUIDELINE.md](GUIDELINE.md) 记录已经提过和顺手发现的上游问题（平时优化与使用中遇到真 Bug 再记，不刻意刷 Issue）。

| 日期 | 上游仓库 | 类型 | 内容 | 状态 | 链接 / 结果 | 备注 |
|---|---|---|---|---|---|---|
| 2026-11-22 | `gaboolic/rime-frost` | Bug | `lunar.lua:553` 缺 `seg:has_tag` 且 `nil` 拼接报错 | 已修复 | PR `#414` (`5532b4f` / `caf787fe`) | 上游已合并 |
| 2026-11-22 | `gaboolic/rime-frost` | 性能 | 7 套方案的 `pin_cand_filter` 在单字母下放了不可达多字词，导致首键空扫 101 候选，且排在 `corrector` 后面 | 已提交 | 已发至 `gaboolic/rime-frost` | 实测首键 `52.7 / 180.7 ms → 5.5 ms`；另发现全拼 `e -> 而` 同样不可达 |
| 2026-11-22 | `gaboolic/rime-frost` | Bug | `lua/number_translator.lua:148-151` 缺 `seg:has_tag("number")` 且 `get_string` 没判 `nil` | 本仓库已修 / 待顺手汇总 | — | 已在本仓库修复，待后续有空时决定是否顺手反馈上游 |
| 2026-11-22 | `gaboolic/rime-frost` | Bug | `lua/reduce_english_filter.lua:99-105` 候选总数不足时 `pending_cands` 未输出会被吞掉（`rime-ice` 已修，白霜未同步） | 本仓库已修 / 待顺手汇总 | — | 本仓库在 `reduce_english_filter.lua` 与 `chth1z_pipeline_filter.lua` 均已修复 |
| 2026-11-22 | `gaboolic/rime-frost` | 配置 | `translator/grammar_penalty` 是否仍有作用 | 已核实（不提） | — | 已查 `rime.dll`（`librime 1.17.0`）确无该键名，但无实际负面影响，本仓库已删除、不打扰上游 |
