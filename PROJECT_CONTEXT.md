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
| 修正 GC（`inc(150,200)`）＋ 合并滤镜 ＋ 台湾双出 ＋ 语法调优（纯统计） | `~0.4 ms / ~1.0 ms`（估） | **`0.1 ms / 0.4 ms`**（峰值 `0.9 ms`） | `max_sentences: 8, cutoff: 0.3`，88 项回归全过 |
| ＋ 端侧知意 ONNX 神经整句重排（v0.1.0，`1.4V2-Long-L12`，8 线程 CPU） | 待拔电实测 | `0.1 ms / 2.1 ms`（峰值 `12.9 ms`） | 全拼 `0.1 / 5.0 ms`（峰值 `15.7 ms`），88 项回归全过 |
| ＋ 端侧神经重排 v0.2.0（`ML-pumpkin-1103` KV-cache ＋ `.gram` 融合 ＋ P2C） | 待拔电实测 | **`0.1 ms / 1.6 ms`**（峰值 **`9.8 ms`**） | 全拼 `0.1 / 4.2 ms`（峰值 `12.6 ms`），88 项回归全过 |

### 语料准确率评测（`bench/eval-accuracy.py`，复用 `gaboolic/rime-schema-compare` 公开语料与同义归一化口径）

- **纯统计调优**（`collocation_penalty: -15.5`、`contextual_suggestions: false`，注释 `41448` / `GB18030-2022` 生僻字表，关闭 `translator/enable_user_dict` 严格隔离）：
  - 1,600 句混合（科技周刊 200 + 知乎开发 400 + 知乎未见验证 1,000）：双拼基线整句 **`75.12%`**（1202/1600）/ 文字 **`95.51%`**（科技 `81.00%`、开发 `70.50%`、验证 `75.80%`）
  - 解锁 `translator/sentence_cutoff_threshold: 0.1 → 0.3`（`max_sentences: 8`）：仅放宽已有 beam 输出阈值，Top-8 召回上限从 `87.75%` 升至 **`90.25%`**（Top-10 达 `91.12%`），同时对 `21.5%` 高置信句子（准确率 `97.4%`）保持单候选跳过神经重排
- **＋ 端侧神经重排 v0.1.0（`知意 1.4V2-Long-L12` int8 ONNX，Apache-2.0）**：
  - 离线多模型横向实测（1,600 句双拼）：`msime-4M` 最高 `76.12%`（+1.00%）、`msime-25M` 最高 `78.81%`（+3.69%）、`知意 1.4V2-Long-L12` Top-8 + 排位先验 `α=1.4` 达 `83.06%`（无上下文 `79.44%`）
  - 官方小狼毫 `0.17.4` 端到端实跑（真实 `commit_history`、无标点最严苛连续上屏，1,600 句双拼）：整句 `75.12% → 81.31%`（`+6.19%`，科技 `90.50%`、验证 `80.00%`），文字 `96.83%`；全拼科技 200 句 `80.50% → 91.50%`（含段落上下文）
- **＋ 端侧神经重排 v0.2.0（`知意 ML-pumpkin-1103` 融合前缀 KV-cache ＋ 直接 mmap `wanxiang-lts-zh-hans.gram` 五维融合 ＋ 零额外推理 `char_logits` P2C 候选合成 ＋ 本地脱敏反馈采集）**：
  - 离线实测（1,600 句双拼，带标点段落上下文）：`ML-pumpkin-1103` 纯神经 `83.94%`（无上下文 `81.31%`），叠加 `.gram` + `char_logits` 五维低维融合（仅在 400 句开发集拟合）达 **`84.31%`**（盲测验证集 **`83.80%`**，误改量从 `-33` 压至 **`-18`**）；叠加 `char_logits` P2C 合成额外救回 +25 条 Rime 词格遗漏生僻人名/热词（合并召回上限 **`92.06%`**，实得约 **`84.5%`**）
  - **官方小狼毫 `0.17.4` 端到端实跑（1,600 句双拼，无标点最严苛连续上屏）**：
    - 无上下文：`75.12% →` **`80.75%`**（1292/1600，`+5.63%`，科技 **`90.00%`**、验证 **`80.00%`**），`2.93 ms/key`（较 v0.1.0 提速约 1.7×）
    - 真实 `commit_history` ＋ P2C：`75.12% →` **`81.94%`**（1311/1600，**`+6.82%`**，净多对 109 句，文字 **`96.90%`**、开发 **`80.75%`**、验证 **`80.80%`**），`3.25 ms/key`
    - 全拼科技 200 句（零上下文单句隔离）：`80.50% →` **`90.50%`**（文字 **`98.52%`**）

已经核实的事实：
1. 400 MB 万象模型本身几乎不拖慢按键；`melt_eng` 缩减前 5–10 位大写派生后 `melt_eng.prism.bin` 从 `6.82 MB` 降到 `4.97 MB`。
2. 之前 `5–6 ms` 的主因是 `profiles/rime.lua` 里误写了 `collectgarbage("incremental", 80, 300)`（`pause < 100` 取消 GC 间隔）；改为 `(150, 200)` 并合并滤镜后，纯统计双拼压到 `0.1 / 0.4 ms`（峰值 `0.9 ms`）。
3. 词库消融（800 句实测）：去掉 `41448` 和 `GB18030-2022` 准确率零损失（`622/800 = 77.75%`），可减少 ~10 万生僻字干扰；`composite`（62 万加权短语）贡献 `+1.13%`，必须保留；加入 `tencent` 增重 `10 MB` 但准确率贡献 `0.00%`，保持关闭；双拼下开启 `enable_correction` 会让整句率从 `72.88%` 暴跌至 `57.57%`，保持关闭。
4. 官方小狼毫 `0.17.4` 的 `rime.dll` 原生导出全部 154 个 Lua 5.4 C API 符号且开放 `package.loadlib`。`native/rime_zhiyi`（v0.2.0）通过 `GetModuleHandleA("rime.dll")` 动态解析符号，并用 `GetModuleHandleExA(PIN | FROM_ADDRESS)` 钉驻宿主进程避免重新部署崩溃；同时以 Win32 `CreateFileMappingW` 直接共享映射 `wanxiang-lts-zh-hans.gram`（0 MB 额外物理内存，`~0.01 ms`），利用 `laya.one.fused.int8g.onnx` 16 槽前缀 KV-cache 缓存上下文、同次前向解码 `char_logits` 合成 P2C 候选，并经 `commit_notifier` 将脱敏后的选词纠错事件写入本地 `%APPDATA%\Rime\zhiyi\feedback.jsonl`（5 MiB 自动轮转，不入 Git，配合 `scripts/tune-personal-fusion.py` 5 折交叉验证岭回归离线微调 5 维先验权重）。
5. 仓库 `lua/` 目录已完成收口清理：删除 12 个未被引用的上游遗留脚本（仅保留 7 个实际启用脚本），并在 `deploy-local.ps1` / `update-local.ps1` 中同步自动清理 `%APPDATA%\Rime\lua\`。
6. 这台机器插电和电池相差约 3.3 倍，开启 v0.2.0 神经重排插电峰值 `9.8 ms`（双拼均值 `1.6 ms`），电池实测待补。

## 4. 平时协作的基本约定

- **看实测数据**：改完性能或配置都用 `bench/bench-rime.ps1` 和回归测试验证，不凭感觉下结论。
- **文档保持朴素**：README 和仓库里的文档写清楚事实和用法就行，不堆虚词。
- **别改同步目录**：`cn_dicts/`、`cn_dicts_cell/`、`en_dicts/` 留给自动任务同步，自己的改动放在 `lua/`、根目录方案、`profiles/`、`themes/`、`bench/`、`scripts/`。
- **提上游 Issue 从严**：遵守 [`docs/upstream-issues/GUIDELINE.md`](docs/upstream-issues/GUIDELINE.md)，只提实测复现、有实际影响的真 Bug，不提视角或习惯分歧带来的伪问题。
