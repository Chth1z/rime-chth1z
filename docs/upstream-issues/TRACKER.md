# 上游 Issue 记录

按 [GUIDELINE.md](GUIDELINE.md) 记录已经提过和顺手发现的上游问题（平时优化与使用中遇到真 Bug 再记，不刻意刷 Issue）。

| 日期 | 上游仓库 | 类型 | 内容 | 状态 | 链接 / 结果 | 备注 |
|---|---|---|---|---|---|---|
| 2026-11-22 | `gaboolic/rime-frost` | Bug | `lunar.lua:553` 缺 `seg:has_tag` 且 `nil` 拼接报错 | 已修复 | PR `#414` (`5532b4f` / `caf787fe`) | 上游已合并 |
| 2026-11-22 | `gaboolic/rime-frost` | 性能 | 7 套方案的 `pin_cand_filter` 在单字母下放了不可达多字词，导致首键空扫 101 候选 | 已修复 | [Issue #420](https://github.com/gaboolic/rime-frost/issues/420) / [PR #423](https://github.com/gaboolic/rime-frost/pull/423) (`4fade2a`) | 上游已合并（仅保留单字固顶并去重计数）；干净上游复测自然码 `w`：`1.44 → 0.30 ms`（上游 13700KF `4.62 → 0.65 ms`），当时报的 `52.7 / 180.7 ms` 被本地旧 `rime.lua` 的 `inc(80, 300)` 放大；全拼 `e -> 而` 仍不可达 |
| 2026-11-22 | `gaboolic/rime-frost` | Bug | `lua/number_translator.lua:148-151` 缺 `seg:has_tag("number")` 且 `get_string` 没判 `nil` | 待顺手汇总 | — | 上游仍存在该问题（本仓库方案未启用 `number_translator.lua`） |
| 2026-11-22 | `gaboolic/rime-frost` | Bug | `lua/reduce_english_filter.lua:99-105` 候选总数不足时 `pending_cands` 未输出会被吞掉（`rime-ice` 已修，白霜未同步） | 本仓库已修 / 待顺手汇总 | — | 本仓库在 `chth1z_pipeline_filter.lua` 中已内置修复 |
| 2026-11-22 | `gaboolic/rime-frost` | 配置 | `translator/grammar_penalty` 是否仍有作用 | 已核实（不提） | — | 已查 `rime.dll`（`librime 1.17.0`）确无该键名，但无实际负面影响，本仓库已删除、不打扰上游 |
| 2026-11-23 | `iDvel/rime-ice` | Bug | `cn_en_{abc,ziguang}.txt`「T.S.艾略特」错码及 `opencc/others.txt` 化学式错误 | 草稿待复核 | [草稿](2026-11-23-rime-ice-cnen-abc-and-opencc-others.md) | 已在干净上游复现；`others.txt` 同步影响 `rime-frost@ab64ecf`，本仓库已修复（已核实智能 ABC `V怪客 Vgcke` 为正确编码） |
| 2026-11-23 | `gaboolic/rime-frost` | Bug | 7 份 `cn_dicts_cell` 细胞词库混入约 16.8 万条非领域抓取/广告/电子书前言垃圾块 | 草稿待复核 | [草稿](2026-11-23-rime-frost-cell-dict-scrape-dumps.md) | 已基于 `ab64ecf` 逐行核实锚点与实机复现，本仓库已清除 |
| 2026-11-23 | `gaboolic/rime-frost` | Bug | `base` `均订 junding` 双拼不可达、批量自动注音错误及 569 条 `lue/nue` 编码不统一（75 对重复） | 草稿待复核 | [草稿](2026-11-23-rime-frost-dict-pinyin-and-encoding-bugs.md) | 已基于 `ab64ecf` 逐条实机复现并核对 7 套方案拼写代数，本仓库已修正 |
| 2026-11-23 | `gaboolic/rime-frost` | Bug | `opencc/{english_chinese,chinese_english,others}.txt` 批量格式损坏、释义错贴与重复 emoji | 草稿待复核 | [草稿](2026-11-23-rime-frost-opencc-ce-ec-corruptions.md) | 已基于 `ab64ecf` 开启 `chinese_english`/`emoji` 开关实机复现，本仓库已修复 |
| 2026-11-24 | `gaboolic/rime-frost` | Bug | `lua/calculator.lua` 阶乘 21! int64 溢出与函数对象指针泄漏、`select_character.lua` 非选词态吞 `[`、`symbols_v.yaml` `/dn` `/fs` `/you` 错项、`opencc/emoji.txt` 颜色块互换与 `食盐` 遮蔽 | 本仓库已修 / 待顺手汇总 | — | 均已在本仓库修复并通过回归校验；按需合并整理后提交上游 |
