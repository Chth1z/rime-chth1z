# 上游 Issue 记录

按 [GUIDELINE.md](GUIDELINE.md) 记录已经提过和顺手发现的上游问题（平时优化与使用中遇到真 Bug 再记，不刻意刷 Issue）。

| 日期 | 上游仓库 | 类型 | 内容 | 状态 | 链接 / 结果 | 备注 |
|---|---|---|---|---|---|---|
| 2026-11-22 | `gaboolic/rime-frost` | Bug | `lunar.lua:553` 缺 `seg:has_tag` 且 `nil` 拼接报错 | 已修复 | PR `#414` (`5532b4f` / `caf787fe`) | 上游已合并 |
| 2026-11-22 | `gaboolic/rime-frost` | 性能 | 7 套方案的 `pin_cand_filter` 在单字母下放了不可达多字词，导致首键空扫 101 候选 | 已修复 | [Issue #420](https://github.com/gaboolic/rime-frost/issues/420) / [PR #423](https://github.com/gaboolic/rime-frost/pull/423) (`4fade2a`) | 上游已合并（仅保留单字固顶并去重计数）；干净上游复测自然码 `w`：`1.44 → 0.30 ms`（上游 13700KF `4.62 → 0.65 ms`），当时报的 `52.7 / 180.7 ms` 被本地旧 `rime.lua` 的 `inc(80, 300)` 放大；全拼 `e -> 而` 仍不可达 |
| 2026-11-22 | `gaboolic/rime-frost` | 配置 | `translator/grammar_penalty` 是否仍有作用 | 已核实（不提） | — | 已查 `rime.dll`（`librime 1.17.0`）确无该键名，但无实际负面影响，本仓库已删除、不打扰上游 |
| 2026-11-23 | `iDvel/rime-ice` | Bug | `cn_en_{abc,ziguang}.txt`「T.S.艾略特」错码及 `opencc/others.txt` 化学式错误 | 草稿已复核（可提交） | [草稿](2026-11-23-rime-ice-cnen-abc-and-opencc-others.md) | 已基于 `927e1cf` 逐行核对并实机复现；`others.txt` 同步影响 `rime-frost@c982966`（已核实智能 ABC `V怪客 Vgcke` 为正确编码） |
| 2026-11-24 | `iDvel/rime-ice` | Bug | `lua/select_character.lua` 吞 IPv6 `[` 与模式字符报错，及 `lua/number_translator.lua` 漏判 tag 误劫持邮箱 | 已提交 | [Issue #1648](https://github.com/iDvel/rime-ice/issues/1648)（[留档](2026-11-24-rime-ice-lua-select-character-and-number-translator.md)） | 已基于 `927e1cf` 实机复现 `http://[` 吞字、`http://my-site.com[` 抛 Lua `L45 nil` 错误与 `R123@a.com` 被劫持；同步影响 `rime-frost@c982966` |
| 2026-11-24 | `iDvel/rime-ice` | Bug | `opencc/emoji.txt` 10 处黑白方块反转与 `拇指向上`/`红发男` 混入，及 `symbols_v.yaml` 缺逗号/漏 `¾` | 草稿已复核（可提交） | [草稿](2026-11-24-rime-ice-emoji-and-symbols-v-bugs.md) | 已基于 `927e1cf` 逐行核实并实机复现；同步影响 `rime-frost@c982966` |
| 2026-11-23 | `gaboolic/rime-frost` | Bug | 7 份 `cn_dicts_cell` 细胞词库混入约 16.8 万条非领域抓取/广告/电子书前言垃圾块 | 草稿已复核（可提交） | [草稿](2026-11-23-rime-frost-cell-dict-scrape-dumps.md) | 已基于最新 `c982966` 复核全部锚点行号与实机复现，本仓库已清除 |
| 2026-11-23 | `gaboolic/rime-frost` | Bug | `base` `均订 junding` 双拼不可达、`place` 17 条不可输入编码、批量自动注音错误（含 `函数重载`/33 处背俞穴/`大黄靴`/476 条角斗士）及 569 条 `lue/nue` 不统一 | 草稿已复核（可提交） | [草稿](2026-11-23-rime-frost-dict-pinyin-and-encoding-bugs.md) | 已基于最新 `c982966` 逐条核实精确条数、行号并实机复现，本仓库已修正 |
| 2026-11-23 | `gaboolic/rime-frost` | Bug | `opencc/{english_chinese,chinese_english,emoji,others}.txt` 格式损坏、释义错贴、`食盐` 遮蔽 `NaCl` 与白霜独有错字键 | 草稿已复核（可提交） | [草稿](2026-11-23-rime-frost-opencc-ce-ec-corruptions.md) | 已基于最新 `c982966` 合并整理并实机复现，本仓库已修复 |
| 2026-11-24 | `gaboolic/rime-frost` | Bug | `lua/calculator.lua` 阶乘 21!/66! int64 溢出与函数指针泄漏、`reduce_english_filter.lua` 双拼吞英文候选（`bench`/`benz`）、`select_character.lua` 吞 `[` | 已提交 | [Issue #434](https://github.com/gaboolic/rime-frost/issues/434)（[留档](2026-11-24-rime-frost-lua-calculator-and-reduce-english-bugs.md)） | 已基于最新 `c982966` 实机复现并验证 LuaJIT / Lua 5.4 / 5.5 兼容改法；本仓库已修复 |
| 2026-11-24 | `gaboolic/rime-frost` | Bug | `symbols_v.yaml` `/you` 残留 `'/ 友'`、`/weishengdongwu` 拼写错误及 `/dn` `/fs` 遗漏 | 草稿已复核（可提交） | [草稿](2026-11-24-rime-frost-symbols-v-typos.md) | 已基于最新 `c982966` 实机复现，本仓库已修复（另已核实 `melt_eng_algebra.yaml` 紫光 `#` 上游已正确，不提） |
