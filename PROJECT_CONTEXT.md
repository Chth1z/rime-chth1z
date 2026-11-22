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
- **当前自用配置**：自然码双拼（主力）＋ 全拼（备用），挂 `wanxiang-lts-zh-hans.gram`（372.68 MB，`collocation_penalty: -15.5`、`non_collocation_penalty: -4`、`contextual_suggestions: false`）、台湾繁体双出滤镜（`tw_dual_filter.lua`：首选 `s2twp` 台湾用法，次选 `s2tw` 台湾正体保留原词）、竖排 5 候选（`F4` 菜单单页 6 项），主题 `apple_graphite_dark`（`#262626`、`#2C62CE`、`Noto Sans CJK TC:medium` 13pt / 11pt 阿拉伯数字）

## 3. 已测出的性能与准确率数据

### 按键延迟（`bench/bench-rime.ps1`）

通过本机 `rime.dll` 隔离测试（不碰线上 `userdb`，有效自然码双拼短/中/长句，均含 400 MB 万象模型＋台湾繁体双出＋`melt_eng`）：

| 状态 | 电池（首键 / 后续键） | 插电（首键 / 后续键） | 备注 |
| :--- | :---: | :---: | :--- |
| 白霜原始 `pin_cand_filter`（单字母含不可达多字词） | `180.7 ms / 18.1 ms` | `52.7 ms / 5.5 ms` | 上游默认 |
| 删掉单字母不可达词 ＋ 旧版 `rime.lua`（`inc(80,300)`） | `~18 ms / ~15 ms` | `5.3 ms / 6.0 ms` | `pause < 100` 导致 Lua 5.4 无间歇 GC |
| 修正 GC（`inc(150,200)`）＋ 合并滤镜 ＋ 台湾双出 ＋ 语法调优 | `~0.4 ms / ~1.0 ms`（估） | **`0.1 ms / 0.3 ms`**（峰值 `0.6 ms`） | 全拼 `0.1 / 0.7 ms`，88 项回归测试全过 |

### 语料准确率评测（`bench/eval-accuracy.py`，复用 `gaboolic/rime-schema-compare` 公开语料与同义归一化口径）

- **调优前**（`collocation_penalty: -14`、`contextual_suggestions: true`，全量 30 张词表）：
  - 科技周刊 200 句：整句 `82.50%` / 文字 `97.29%`（`0.30 ms/key`）
  - 知乎热榜前 600 句：整句 `66.50%` / 文字 `93.73%`（`0.30 ms/key`）
  - 1,600 句混合（200 科技 + 400 开发 + 1,000 未见验证）：整句 `74.75%`（1196/1600）
  - 2,956 条同段落连续子句：`contextual_suggestions: true` 整句 `75.07%` vs `false` `75.58%`
- **调优后**（`collocation_penalty: -15.5`、`contextual_suggestions: false`，注释 `41448` / `GB18030-2022` 生僻字表）：
  - 科技周刊 200 句：整句 `82.00%` / 文字 `97.24%`（`0.26 ms/key`）
  - 知乎热榜前 600 句：整句 **`69.00%`**（`+2.50%`，+15 句） / 文字 **`94.10%`**（`0.25 ms/key`）
  - 1,600 句混合：整句 **`75.94%`**（1215/1600，`+1.19%`，其中 1,000 句未见验证集 `75.80% → 76.40%`）

已经核实的事实：
1. 400 MB 万象模型本身几乎不拖慢按键；`melt_eng` 缩减前 5–10 位大写派生后 `melt_eng.prism.bin` 从 `6.82 MB` 降到 `4.97 MB`。
2. 之前 `5–6 ms` 的主因是 `profiles/rime.lua` 里误写了 `collectgarbage("incremental", 80, 300)`（`pause < 100` 取消 GC 间隔）；改为 `(150, 200)` 并合并滤镜后，双拼压到 `0.1 / 0.3 ms`（峰值 `0.6 ms`），全拼压到 `0.1 / 0.7 ms`。
3. 词库消融（800 句实测）：去掉 `41448` 和 `GB18030-2022` 准确率零损失（`622/800 = 77.75%`），可减少 ~10 万生僻字干扰；`composite`（62 万加权短语）贡献 `+1.13%`，必须保留；加入 `tencent` 增重 `10 MB` 但准确率贡献 `0.00%`，保持关闭；双拼下开启 `enable_correction` 会让整句率从 `72.88%` 暴跌至 `57.57%`，保持关闭。
4. 这台机器插电和电池相差约 3.3 倍，现在插电峰值 `0.6 ms`，电池下也能稳在单帧（`16 ms`）以内。

## 4. 平时协作的基本约定

- **看实测数据**：改完性能或配置都用 `bench/bench-rime.ps1` 和回归测试验证，不凭感觉下结论。
- **文档保持朴素**：README 和仓库里的文档写清楚事实和用法就行，不堆虚词。
- **别改同步目录**：`cn_dicts/`、`cn_dicts_cell/`、`en_dicts/` 留给自动任务同步，自己的改动放在 `lua/`、根目录方案、`profiles/`、`themes/`、`bench/`、`scripts/`。
- **提上游 Issue 从严**：遵守 [`docs/upstream-issues/GUIDELINE.md`](docs/upstream-issues/GUIDELINE.md)，只提实测复现、有实际影响的真 Bug，不提视角或习惯分歧带来的伪问题。
