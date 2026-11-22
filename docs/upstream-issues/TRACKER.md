# 上游 Issue 记录

按 [GUIDELINE.md](GUIDELINE.md) 记录已经提过和待核实的上游问题。

| 日期 | 上游仓库 | 类型 | 内容 | 状态 | 链接 / 结果 | 备注 |
|---|---|---|---|---|---|---|
| 2026-11-22 | `gaboolic/rime-frost` | Bug | `lunar.lua:553` 缺 `seg:has_tag` 且 `nil` 拼接报错 | 已修复 | PR `#414` (`5532b4f` / `caf787fe`) | 上游已合并 |
| 2026-11-22 | `gaboolic/rime-frost` | 性能 | 7 套方案的 `pin_cand_filter` 在单字母下放了不可达多字词，导致首键空扫 101 候选，且排在 `corrector` 后面 | 已提交 | 已发至 `gaboolic/rime-frost` | 实测首键 `52.7 / 180.7 ms → 5.5 ms` |
| 2026-11-22 | `gaboolic/rime-frost` | Bug | `lua/number_translator.lua:148-151` 缺 `seg:has_tag("number")`（打 `RTX4090` 等会被注入大写金额）且 `get_string` 没判 `nil` | 待复现与汇总 | — | 等把其余 `lua/*.lua` 一并查完、在干净上游配置实测后再决定是否合并提交 |
| 2026-11-22 | `gaboolic/rime-frost` | 配置 | `translator/grammar_penalty` 是否已无实际作用 | 待核实 | — | 需先看 `librime 1.17` 源码确认，不构成实际影响就不提 |
