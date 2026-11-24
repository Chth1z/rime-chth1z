# rime-chth1z

面向 Windows 小狼毫（Weasel）的 Rime 输入法配置与词库治理仓库。

仓库包含两部分内容：

1. **可复现的声明式词库清洗与治理层**：以 [gaboolic/rime-frost（白霜拼音）](https://github.com/gaboolic/rime-frost) 为上游基座，通过 `rules/` 声明式规则库（9,989 条规则）、确定性清洗引擎 `scripts/clean-dicts.py` 与静态门禁 `scripts/dict_lint.py`，对中文核心词库、22 份活跃细胞词库、英文词库、7 种拼音布局中英混输词表及 OpenCC 文本词表执行幂等清洗、审音校对、词形规范、双读音建档与同音碰撞校验。
2. **个人日常输入方案与运行时配置**：以自然码双拼为主、全拼为辅，搭配万象语法模型、可选端侧神经整句重排（[Chth1z/rime-neural](https://github.com/Chth1z/rime-neural)）及台湾繁体双出滤镜（首选 `s2twp` 台湾用法，存在词汇差异时次选 `s2tw` 台湾正体保留原词；全局记忆上次切换状态，`Claude` 桌面端默认臺繁，其余应用默认简中）。

> 方案键位、外观与 `app_options` 按个人习惯定制；词库文件、`rules/` 声明式规则、清洗与门禁脚本及治理规范 [docs/DICTIONARY_SPEC.md](docs/DICTIONARY_SPEC.md) 可独立参考或复用。如需通用上游方案或独立神经重排插件，可直接使用 [gaboolic/rime-frost](https://github.com/gaboolic/rime-frost) 或 [Chth1z/rime-neural](https://github.com/Chth1z/rime-neural)。

## 词库治理与清洗体系

全部词库修订均遵循 [docs/DICTIONARY_SPEC.md](docs/DICTIONARY_SPEC.md) 定义的五级审音依据链（L1 现行国家规范《普通话异读词审音表》/《通用规范汉字表》/《现代汉语词典》第 7 版 → L2 全国科技名词委/民政地名/药典 → L3 品牌/人名/古诗文训诂 → L4 2016 审音修订稿 → L5 两岸与大规模社会通行习惯）、五类读音决策矩阵（A–E）及五级官民异形词标准（W1–W5）。

### 声明式规则架构（`rules/` SSOT）

所有相对上游的增删改调权均沉淀在 `rules/` 目录下的纯文本规则表中，由 `scripts/clean-dicts.py` 在每次上游同步后确定性重放（`cn_dicts/`、`cn_dicts_cell/`、`en_dicts/` 与 `opencc/*.txt` 共 42 份受管文件二次执行 SHA-256 差异为 `0`）：

| 治理维度 | 规则文件 | 当前规模 | 主要内容 |
| :--- | :--- | :---: | :--- |
| **双读音双注释（A 类）** | `rules/dual_readings.tsv` | `158` 组 | 行业防混淆异读（如 `镀铬`、`淬火`、`跖骨`、`格栅`、`曝气`）、临床/药典双轨、2016 审音拟与两岸/旧读并存词；单点声明并同步生成主库双音与 `corrections.dict.yaml` 零权双向对照注释 |
| **错音与错字纠偏（B/C 类）** | `rules/corrections.tsv` | `931` 条 | 高频多音误读、生僻字/地名/人名/成语易错音与错字触发项（`corrections.dict.yaml` 活跃词条共 `1,247` 条），排除 D 类识字硬伤与模糊音，严控权重低于同音高频正词 |
| **审音校对** | `rules/phonetics_fix.tsv` | `2,499` 条 | 修正 `8105`、核心词库与细胞词库中的确定性多音误注（如背俞穴、自动注音切分失误、古诗文与专名错音） |
| **词形规范** | `rules/word_fixes.tsv` | `731` 条 | 统一官方淘汰异形词（W3）、错别字与混入的非规范繁日异体字（保留合法语义分工词 W1 与规范并存词 W2） |
| **精确清理** | `rules/deletions.tsv` | `2,765` 条 | 清除已核实错别字（W5）、垃圾词条与冗余错音克隆；配合清洗脚本同步清理细胞词库中的非领域抓取块（POI、广告、模板尾块等约 17.1 万条）及 2.4 万条重复项 |
| **权重校准** | `rules/weights.tsv` | `1,265` 条 | 校准 `8105` 主音排序、翻转 W2 规范词形倒挂、限制专名/细胞词抢占通用词；对 `.gram` 语法路径高频词采用温和降权保护 |
| **词条补录** | `rules/additions.tsv` | `629` 条 | 补齐 `8105` 规范缺失多音及常用现代通用词、城市地名与多义项读音 |
| **英文、中英混输与字母数字** | `rules/en_{additions,fixes}.tsv`、`cn_en_source.tsv`、`alphanum_additions.txt` | `760` 条 | 维护 `en_ext` 现代开发/AI/硬件词表、清理 `en` 错词并去重；通过 `scripts/build_cn_en.py` 从单一源同步生成全部 7 种拼音布局的 `en_dicts/cn_en*.txt`（各 `1,113` 条） |
| **OpenCC 文本词表** | `rules/opencc_fixes.tsv` | `251` 条 | 修复 `emoji.txt`（色块互换、释义错配与 `食盐` 遮蔽）、`others.txt`（化学式与重复 emoji）、`chinese_english.txt` 与 `english_chinese.txt`（清理 `NUM` 尾垃圾、断行截断与不可达多词键） |

### 自动化校验与四级门禁

- **静态门禁与幂等校验（`scripts/dict_lint.py`）**：强制校验 5 项零容忍不变量（非法音节、字音长度失配、残留 `lue/nue`、单文件重复、26 份活跃中文词库跨文件重复均为 `0`），同时校验 YAML 语法、`rules/` 零冲突、A/B/C 类同音碰撞安全边界、`cn_en` 7 布局一致性及二次清洗 SHA-256 零差异。
- **引擎部署与确定性回归（`bench/accuracy-test.ps1`）**：基于本机 `rime.dll` 在隔离目录执行 `242` 项确定性回归断言，覆盖双读音注释、纠错排序、同音碰撞边界、台繁双出、中英混输、OpenCC 与 Lua 滤镜行为。
- **盲测防退化监控（`bench/eval-accuracy.py`）**：参考 [gaboolic/rime-schema-compare](https://github.com/gaboolic/rime-schema-compare) 公开语料与同义归一化口径，在双拼/全拼 × 纯统计/神经重排四组模式下执行 A/B 对比，防止调权或删词引发整句准确率退化。

### 词库与规则复用方式

如需在本地验证或基于上游白霜词库重放清洗管线（需 Python 3.10+）：

```powershell
# 运行确定性清洗（并输出规则命中报告，验证 0 零命中过期规则）
python scripts/clean-dicts.py --manifest clean_manifest.json

# 运行完整静态门禁：不变量、规则冲突、同音碰撞护栏与二次运行幂等校验
python scripts/dict_lint.py --strict --idempotent --check-collisions

# 若仅维护中英混输单一源，同步派生全部 7 种拼音布局
python scripts/build_cn_en.py
```

如仅需直接复用清洗后的词库，可按需取用 `cn_dicts/`、`cn_dicts_cell/`、`en_dicts/` 与 `opencc/*.txt`（与 `gaboolic/rime-frost` 目录结构兼容）。

## 目录说明

- `cn_dicts/`、`cn_dicts_cell/`、`en_dicts/`、`opencc/`：同步自白霜上游并经 `scripts/clean-dicts.py` 清洗校准的词库与 OpenCC 词表（当前 27 份活跃中文词库共 `1,658,757` 条，含 `corrections.dict.yaml` `1,247` 条）
- `rules/`：词库审音、双读音、纠错、权重、词形修正、英文、中英混输与 OpenCC 修复的声明式规则单一事实源（SSOT，共 `9,989` 条）
- `lua/`：6 个自用脚本——单遍合并管线（`chth1z_pipeline_filter.lua`）、台湾繁体双出滤镜（`tw_dual_filter.lua`，支持单字一简对多繁展开与拆字简形透传）以及日期、农历、计算器（含大数阶乘防溢出与求值校验）、以词定字脚本；神经重排脚本 `rime_neural.lua` 与原生 DLL 由 `Chth1z/rime-neural` 发行包管理
- `profiles/`：`rime.lua`（Lua 5.4 GC 参数）及预留的本机临时覆盖文件 `*.custom.yaml`
- `themes/`：小狼毫外观配置（`apple_graphite_dark`，含 `claude.exe` / `claude-desktop.exe` `app_options` 臺繁设定）
- `bench/`：调用本机 `rime.dll` 的功能回归测试（`accuracy-test.ps1`、`accuracy-cases.json`）、按键耗时测试（`bench-rime.ps1`）与语料准确率评测（`eval-accuracy.py`）
- `scripts/`：本地同步与清洗词库（`sync-dicts-local.ps1`、`clean-dicts.py`、`dict_rules.py`、`dict_lint.py`、`build_cn_en.py`）、检查上游更新、安装或升级 `Chth1z/rime-neural`（`install-rime-neural.ps1`）、本地部署（`deploy-local.ps1`）及本机周更脚本（`update-local.ps1`）
- `docs/`：词库维护与治理规范（`DICTIONARY_SPEC.md`）及向上游反馈问题的约定与记录（`upstream-issues/`）
- `PROJECT_CONTEXT.md` / `ROADMAP.md`：项目背景记录与优化清单

## 自动任务

- `.github/workflows/sync-upstream-dicts.yml`：每周日 02:00（UTC+8）自动从 `gaboolic/rime-frost` 同步词库与 OpenCC 文本词表，执行 `scripts/clean-dicts.py` 清洗与 `scripts/dict_lint.py --strict --idempotent --diff-budget` 静态门禁；超出变更阈值（活跃词条 `|Δ| > 5,000`、`corrections` `> 50` 行或 `cn_en` `> 200` 行）时自动转 PR 交人工复核。
- `scripts/update-local.ps1`（本机任务 `RimeChth1zWeeklyUpdate`）：每周日 03:30（UTC+8）检查并拉取本仓库、`Chth1z/rime-neural` 最新发行版与万象 LTS 模型，随后部署至 `%APPDATA%\Rime`。
- `.github/workflows/upstream-watch.yml`：每周一追踪白霜、雾凇（`lua/`）、`rime-neural`、知意模型、小狼毫 Nightly 与万象模型的新版本，并汇总至固定 Issue。

## 来源与致谢

- [gaboolic/rime-frost（白霜拼音）](https://github.com/gaboolic/rime-frost)：词库（`cn_dicts/`、`cn_dicts_cell/`、`en_dicts/`）、OpenCC 词表与初始方案来源（起始版本 `970a6d6`），词库目录每周自动同步上游。
- [iDvel/rime-ice（雾凇拼音）](https://github.com/iDvel/rime-ice)：白霜上游，部分 Lua 脚本与方案写法参考于此。
- [Chth1z/rime-neural](https://github.com/Chth1z/rime-neural)：独立的 Apache-2.0 端侧 ONNX 神经整句重排插件，通过 GitHub Release 安装与自动更新。
- [amzxyz/rime-wanxiang-data](https://github.com/amzxyz/rime-wanxiang-data)：配合使用的 `wanxiang-lts-zh-hans.gram` 语法模型（按需下载至本地 Rime 目录，不入本仓库）。
- [gaboolic/rime-schema-compare](https://github.com/gaboolic/rime-schema-compare)：离线整句与文字准确率评测口径参考来源。
- [rime/weasel（小狼毫）](https://github.com/rime/weasel) / [rime/librime](https://github.com/rime/librime)：Windows 客户端与核心引擎。

## 协议

沿用上游协议，按 [GNU GPL v3.0](LICENSE) 开源，保留原有版权说明并标明修改来源。
