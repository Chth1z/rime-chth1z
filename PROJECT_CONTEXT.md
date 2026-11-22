# 项目背景与交接说明（`Chth1z/rime-chth1z`）

这份文档记录 `D:\Github\rime-chth1z` 的现状、已经测过的数据和基本约定，方便切到这个目录开新会话时直接接着做。

## 1. 仓库定位与上游关系

`https://github.com/Chth1z/rime-chth1z` 是个人自用的独立公开仓库（GPL-3.0，不作为 GitHub Fork，从白霜 `970a6d6` 起步）。

基本分工：词库自动跟白霜上游同步；Lua 脚本、方案配置、小狼毫外观和性能测试自己维护；排查中如果发现上游真有 Bug，按约定整理后反馈给上游。

| 上游 | 关注什么 | 怎么跟进 |
| :--- | :--- | :--- |
| `upstream`（`gaboolic/rime-frost`） | `cn_dicts/`、`cn_dicts_cell/`、`en_dicts/`、`opencc/` | `.github/workflows/sync-upstream-dicts.yml` 每周自动同步；本地可用 `scripts/sync-dicts-local.ps1` |
| `upstream`（`gaboolic/rime-frost`） | `lua/` 与方案改动 | 本地只读远端 `upstream`（已锁 `no_push`，可随时 `git show` 对比）＋ `upstream-watch.yml` 每周汇总 |
| `rime-ice`（`iDvel/rime-ice`） | 母库 `lua/` 修复与改进 | 本地只读远端 `rime-ice`（已锁 `no_push`）＋ `upstream-watch.yml` 每周汇总 |
| `amzxyz/rime-wanxiang-data`（`LTS`） | `wanxiang-lts-zh-hans.gram`（不入 Git） | `upstream-watch.yml` 记录 SHA-256，本机单独更新 |
| `rime/weasel`（`latest` Nightly） | Windows 客户端与 `librime` 版本 | `upstream-watch.yml` ＋ `scripts/check-upstreams.ps1` |

## 2. 本机环境（2026-11-22）

- **系统与硬件**：Windows 11（`zh-Hant-TW` / `0x0404`），Intel Core Ultra 7 255HX，32 GB 内存
- **输入法**：Weasel Nightly `0.17.4.98.f96ed24`（`librime 1.17.0`、`Lua 5.4.8`、Direct2D WARP）
- **字体**：系统已装 Google 官方完整版 `NotoSansCJK.ttc` + `NotoSerifCJK.ttc`（繁简日韩无缺字），以及 `Chiron GoRound TC VF`、`Inter Variable Text`、`LXGW WenKai TC`、`Newsreader`、`Source Serif 4`、`Plus Jakarta Sans`
- **当前自用配置**：自然码双拼（主力）＋ 全拼（备用），挂 `wanxiang-lts-zh-hans.gram`（372.68 MB）、`s2twp.json`（台湾字形＋台湾惯用词）、竖排 5 候选（`F4` 菜单单页 6 项），主题 `apple_graphite_dark`（`#262626`、`#2C62CE`、`Noto Sans CJK TC:medium` 13pt / 11pt 阿拉伯数字）

## 3. 已测出的性能数据（`bench/bench-rime.ps1`）

通过本机 `rime.dll` 隔离测试（不碰线上 `userdb`，有效自然码双拼短/中/长句，均含 400 MB 万象模型＋`s2twp`＋`melt_eng`）：

| 状态 | 电池（首键 / 后续键） | 插电（首键 / 后续键） | 备注 |
| :--- | :---: | :---: | :--- |
| 白霜原始 `pin_cand_filter`（单字母含不可达多字词） | `180.7 ms / 18.1 ms` | `52.7 ms / 5.5 ms` | 上游默认 |
| 删掉单字母不可达词 ＋ 旧版 `rime.lua`（`inc(80,300)`） | `~18 ms / ~15 ms` | `5.3 ms / 6.0 ms` | `pause < 100` 导致 Lua 5.4 无间歇 GC |
| 修正 GC（`inc(150,200)`）＋ 合并滤镜 `chth1z_pipeline_filter` | `~0.4 ms / ~1.0 ms`（估） | **`0.1 ms / 0.3 ms`**（峰值 `0.8 ms`） | 万键压测均值 `0.17 ms`、`p99 0.46 ms`、`dMem +0.05 MB` |

已经核实的事实：
1. 400 MB 万象模型本身几乎不拖慢按键（开关差 < 0.2 ms）；`s2twp` 约 0.1–0.2 ms；`melt_eng` 缩减前 5–10 位大写派生后 `melt_eng.prism.bin` 从 `6.82 MB` 降到 `4.97 MB`。
2. 之前剩下的 4–5 ms 主要根因是 `profiles/rime.lua` 里误写了 `collectgarbage("incremental", 80, 300)`：Lua 5.4 中 `pause < 100` 会取消 GC 间隔，每次分配都在持续跑完整 GC，导致每个 Lua 滤镜都被放大约 1 ms。改为 `collectgarbage("incremental", 150, 200)` 并合并 4 个高频滤镜为 `lua/chth1z_pipeline_filter.lua`（内建每 16 键一次 `step`）后，双拼压到 `0.1 / 0.3 ms`，全拼压到 `0.1 / 0.7 ms`（且清除了全拼 `e -> 而` 不可达造成的 `19.5 ms` 尖峰）。
3. 这台机器插电和电池相差约 3.3 倍，现在插电均值不到 `0.3 ms`、峰值 `< 1.0 ms`，电池下也能稳在单帧（`16 ms`）以内。

## 4. 平时协作的基本约定

- **看实测数据**：改完性能或配置都用 `bench/bench-rime.ps1` 和回归测试验证，不凭感觉下结论。
- **文档保持朴素**：README 和仓库里的文档写清楚事实和用法就行，不堆虚词。
- **别改同步目录**：`cn_dicts/`、`cn_dicts_cell/`、`en_dicts/` 留给自动任务同步，自己的改动放在 `lua/`、根目录方案、`profiles/`、`themes/`、`bench/`、`scripts/`。
- **提上游 Issue 从严**：遵守 [`docs/upstream-issues/GUIDELINE.md`](docs/upstream-issues/GUIDELINE.md)，只提实测复现、有实际影响的真 Bug，不提视角或习惯分歧带来的伪问题。
