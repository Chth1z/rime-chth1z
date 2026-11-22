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

通过本机 `rime.dll` 隔离测试（不碰线上 `userdb`，同一组短中长句）：

| 状态 | 电池（首键 / 后续键） | 插电（首键 / 后续键） |
| :--- | :---: | :---: |
| 白霜原始 `pin_cand_filter`（单字母含不可达多字词） | `180.7 ms / 18.1 ms` | `52.7 ms / 5.5 ms` |
| 删掉单字母不可达多字词 ＋ 挪到 `corrector` 之前 | `~18 ms / ~15 ms` | **`5.4 ms / 5.1 ms`**（26 键最高 `8.3 ms`） |
| 关掉全部 4 个高频 Lua 滤镜和 `force_gc`（纯 C++ 参照） | `3.5 ms / 3.9 ms` | **`1.1 ms / 1.1 ms`** |

已经核实的事实：
1. 400 MB 万象模型本身几乎不拖慢按键（开关差 < 0.2 ms）；`s2twp` 约 1 ms；`melt_eng` < 1 ms；界面渲染线程全天只占 0.42 s CPU。
2. 这台机器插电和电池相差约 3.3 倍，所以看延迟时要照顾电池状态（尽量压在 16 ms 一帧以内）。
3. 剩下的 4.3 ms（电池约 14 ms）主要来自多个 Lua 滤镜逐层遍历：
   - `corrector` + `spelling_hints: 8`：`+1.5 ms`（`corrections.dict.yaml` 里没有单字词条，却对单字也做反查）
   - `pin_cand_filter` 空跑透传：`+1.2 ms`
   - `reduce_english_filter`：`+0.9 ms`
   - `autocap_filter`：`+0.4 ms`
   - `force_gc`：`+0.3 ms`

## 4. 平时协作的基本约定

- **看实测数据**：改完性能或配置都用 `bench/bench-rime.ps1` 和回归测试验证，不凭感觉下结论。
- **文档保持朴素**：README 和仓库里的文档写清楚事实和用法就行，不堆虚词。
- **别改同步目录**：`cn_dicts/`、`cn_dicts_cell/`、`en_dicts/` 留给自动任务同步，自己的改动放在 `lua/`、根目录方案、`profiles/`、`themes/`、`bench/`、`scripts/`。
- **提上游 Issue 从严**：遵守 [`docs/upstream-issues/GUIDELINE.md`](docs/upstream-issues/GUIDELINE.md)，只提实测复现、有实际影响的真 Bug，不提视角或习惯分歧带来的伪问题。
