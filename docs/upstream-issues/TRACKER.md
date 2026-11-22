# 上游问题回馈追踪表

按 [GUIDELINE.md](GUIDELINE.md) 记录已提交及待审计打包的上游问题。

| 日期 | 目标上游 | 类别 | 摘要 | 状态 | 上游链接 / 修复 | 备注 |
|---|---|---|---|---|---|---|
| 2026-11-22 | `gaboolic/rime-frost` | Bug | `lunar.lua:553` `nil` 拼接崩溃 + 缺少 `seg:has_tag("gregorian_to_lunar")` | **Fixed** | PR `#414` (`5532b4f` / `caf787fe`) | 上游已修复 |
| 2026-11-22 | `gaboolic/rime-frost` | Perf | 全/双拼 7 方案 `pin_cand_filter` 单字母不可达 2–3 字词导致首键空扫 101 候选 + 滤镜顺序在 `corrector` 之后 | **Open** | 已提交至 `gaboolic/rime-frost` | 本地实测 `52.7 ms / 180.7 ms → 5.5 ms` |
| 2026-11-22 | `gaboolic/rime-frost` | Bug | `lua/number_translator.lua:148-151` 缺少 `seg:has_tag("number")`（误劫持 `RTX4090`/`RFC9110`）及 `get_string` 缺 `nil` 保护 | **Draft (待全量 Lua 审计后打包)** | — | 待审计完其余 `lua/*.lua` 与 `grammar_penalty` 死键后合并高质量提报 |
| 2026-11-22 | `gaboolic/rime-frost` | Config | `translator/grammar_penalty` 死配置（需对照 `librime 1.17` 源码确认是否已完全废弃） | **Investigating** | — | 查实 `librime` 源码后再决定是否纳入提报 |
