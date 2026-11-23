# 词库维护与治理规范（`Chth1z/rime-chth1z`）

本文档定义 `Chth1z/rime-chth1z` 词库的职责边界、格式不变量、审音依据、纠错与错字判定标准、权重标尺、声明式规则架构以及自动化门禁流程。所有词库修订、上游同步与周期性审计均以本规范为准。

---

## 1. 五层管线职责边界

`rime-chth1z` 的候选输出由五层管线协同完成。修改词库前应先确认问题归属层，避免通过修改静态词库越权替代其他层的功能：

| 层级 | 核心组件 | 负责事项 | 非静态词库职责 |
| :--- | :--- | :--- | :--- |
| **1. 静态词库层** | `cn_dicts/`、`cn_dicts_cell/`、`en_dicts/`、`rime_frost.dict.yaml` | 收词准确、读音规范、基础候选序稳定、双读音与纠错覆盖、零格式与重复缺陷 | 不堆砌低质量百万级大词库（消融实测 `tencent` 增重 10 MB 且准确率收益 `0.00%`） |
| **2. 语法模型层** | `wanxiang-lts-zh-hans.gram` | 2–5 元上下文搭配与整句路径打分 | 承担高频 `.gram` 转移路径的粘连短语严禁硬删（见第 5.2 节） |
| **3. 神经重排层** | `Chth1z/rime-neural`（ONNX + P2C） | 长句语义消歧、跨应用前文理解、高置信 OOV 人名/热词的 P2C 合成 | 静态词库保持克制收词，偶发冷门人名与瞬时网络词由 P2C 兜底 |
| **4. 管道滤镜层** | `lua/chth1z_pipeline_filter.lua` | 单键/简码置顶（`pin_cand_filter`）、`corrections` 注释挂载、英文大小写派生、短英文降权（`reduce_english_filter`） | 短英文撞码通过 `reduce_english_filter` 处理，不删 `en.dict.yaml`；单字/个人常用置顶走 `pin_cand_filter` 或 `custom_phrase.txt` |
| **5. 繁简转换层** | `lua/tw_dual_filter.lua`（`s2twp` / `s2tw`） | 运行时大陆简体转台湾繁体双出 | 活跃中文词库统一保持大陆规范简体字形，保障 `tw_dual_filter` 与 `t2s.json` 映射稳定 |

### 1.1 词库分层归属与去重权威顺序

主词表 `rime_frost.dict.yaml` 与 `melt_eng.dict.yaml` 及清洗脚本 `cn_plan` 的顺序共同定义跨文件去重归属权（靠前词表优先保留 `(text, code)`）：

| 层级 | 文件 | 定位与准入条件 | 专项约定 |
| :--- | :--- | :--- | :--- |
| **核心单字** | `cn_dicts/8105.dict.yaml` | 《通用规范汉字表》8,105 字及必要基础多音字 | 仅调整权重或补全规范多音，不删除合法规范读音 |
| **核心词库** | `cn_dicts/base.dict.yaml`、`cn_dicts/ext.dict.yaml` | 现代汉语高频通用词、常用多字词与主流通用新词 | 最高质量门槛；新增现代通用词与双标准第二读音优先归口于此 |
| **杂项容错** | `cn_dicts/others.dict.yaml` | 叠字拆字、少量约定俗成的方言/古音容错词（如 `伯伯 bai bai`、`坐骑 zuo ji`） | 无纠错注释，仅收录无须纠偏的习用/工具项 |
| **纠错与注释** | `cn_dicts/corrections.dict.yaml` | 错音/错字纠偏词条 ＋ 双读音 `w=0` 注释覆盖层 | 唯一允许与活跃表 `(text, code)` 重叠的文件（仅限 `weight=0` 注释行） |
| **活跃细胞词库（21 份）** | `cn_dicts_cell/*.dict.yaml`（不含 `luna`） | 专业领域、地名、人名、成语、游戏、医疗、数理化、`composite` 高频短语 | `composite` 对整句准确率有实测正贡献（`+1.13%`），保持启用并清理尾部低质拼接段 |
| **停用上游库** | `41448`、`GB18030-2022`、`tencent`、`luna` | 保留文件以维持上游同步结构，在 `rime_frost.dict.yaml` 中注释关闭 | 不参与活跃表编译；`luna` 由清洗脚本锁定保持关闭 |
| **英文与中英混输** | `en_dicts/en.dict.yaml`、`en_ext.dict.yaml`、`cn_en*.txt` | 英文主库、现代科技补充词、7 种拼音布局中英混合词表 | `en_ext` 置于 `en` 之前；7 份 `cn_en*.txt` 由 `rules/cn_en_source.tsv` ＋ `scripts/build_cn_en.py` 统一派生同步 |
| **字母数字组合** | `rime_frost.dict.yaml` 尾部词块 | 日常高频短字母数字组合（如 `5G`、`4K`、`3C认证`、`PS5`、`2FA`） | 由 `rules/alphanum_additions.txt` 管理，控制体量 |
| **OpenCC 文本表** | `opencc/{chinese_english,english_chinese,emoji,others}.txt` | 翻译与 Emoji 辅助滤镜文本源 | 与本地 `.ocd2` 二进制（`s2twp`/`s2tw`/`t2s`）隔离，上游同步不覆盖 `.ocd2` |

---

## 2. 格式、字符与拼写硬规范（强制不变量）

以下不变量由 `scripts/dict_lint.py` 自动检查，任何一项非零即阻断提交或上游自动推送：

1. **编码与行尾**：UTF-8 无 BOM，统一 LF 换行（由 `.gitattributes` 锁定）。
2. **列格式与字符洁净度**：
   - 词条行以单 Tab 分隔：`text\tcode[\tweight[\tcomment]]`。
   - 词条数据行（不含 `#` 注释行与 `opencc/emoji.txt` / `opencc/others.txt` 值列中的 Emoji ZWJ 序列）严禁首尾多余空格、空列/双连续 Tab、全角空格（`U+3000`，`.dict.yaml` 与 `en_dicts/*.txt` 严禁）、零宽字符（`U+200B–U+200D`、`U+FEFF`）与不可见控制字符。
3. **合法音节集**：中文词条音节必须属于合法普通话无调音节全集（以 `8105.dict.yaml` 单字音节集合为基准，另含规范叹词 `hm`、`hng`、`m`、`n`、`ng`）。
4. **`ü` 拼写统一**：`lü`/`nü`/`lüe`/`nüe` 统一写作 `lv`/`nv`/`lve`/`nve`，禁止出现 `lue`、`nue`；`j/q/x/y` 后省点写作 `u`。
5. **字音长度一致**：除 `corrections.dict.yaml` 中的刻意错字触发项外，词条去除间隔号 `·`（`U+00B7`）后的字数必须严格等于 `code.split()` 音节数。
6. **规范简体字形**：活跃中文词库统一使用大陆《通用规范汉字表》规范简体字形，清理混入的港台繁体、日本新字体及非规范异体字；规范表内特殊字（如 `𬞟`、`𬶨`、`祇`）除外。
7. **唯一性约束**：
   - 单文件内 `(text, code)` 重复数 = `0`。
   - 27 个活跃中文词库（不含 `corrections` 与停用的 `luna`）跨文件 `(text, code)` 重复数 = `0`。
   - `corrections.dict.yaml` 中若存在与活跃表重叠的 `(text, code)`，其 `weight` 必须严格等于 `0` 且 `comment` 非空（用于挂载主读音注释而不叠加词频）。
8. **幂等性约束**：对已清洗仓库二次运行 `scripts/clean-dicts.py`，全部受管文件 SHA-256 差异数 = `0`。

---

## 3. 审音权威依据链与多音字判定原则

遇到读音争议或疑似误注时，严格按以下五级顺序查证裁决：

| 优先级 | 权威依据 | 适用范围与裁决效力 |
| :---: | :--- | :--- |
| **L1** | 1985《普通话异读词审音表》（现行有效国家规范）＋ 2013《通用规范汉字表》＋ 《现代汉语词典》（第 7 版） | 通用汉语读音最高现行规范依据 |
| **L2** | 全国科学技术名词审定委员会审定名词 ＋ 民政部标准地名库 / 地方轨道交通与民政官方读音 | 科技、医学、化工术语（如 `密钥`、`氙气`）及地名（如 `宝幢 bǎo chuáng`、`六安 lù ān`、`鄱阳湖 pó`） |
| **L3** | 品牌官方中文读音 / 公众人物本人或所属地通用读音 / 古诗文传统训诂 | 外来品牌与人名（如 `雪佛兰`、`张柏芝`、`郭明錤`、`温庭筠`） |
| **L4** | 2016《普通话异读词审音表（修订稿）》（未正式颁布的征求意见稿） | 不单方面取代 L1 规范音；与 L1 存在分歧时（如 `荨麻`、`血`）作为 A 类双读音保留依据 |
| **L5** | 台湾教育部《重编国语辞典》及大陆大规模社会通行习惯 | 用于识别双标准并存或高频习惯容错，不直接覆写 L1 规范音 |

### 多音字维护准则

- **单字表（`8105.dict.yaml`）**：保证《现代汉语词典》第 7 版常用读音完备；多音字各读音按真实字频排序，避免冷僻读音在同音竞争中挤占常用字。
- **词组表（`base` / `ext` / `cell`）**：按词义绑定读音，不使用无校验的批量自动注音覆盖人工校对结果：
  - `谁`：`shéi` 与 `shuí` 同为规范音，高频含“谁”词条保持双音齐全。
  - `角`：角色/主角/配角/角逐/口角（争吵）规范为 `jué`；几何/角落/钱币为 `jiǎo`。
  - `车`：常规为 `chē`；中国象棋棋子专用词（`车马炮`、`双车错` 等）规范为 `jū`。
  - `行`：行业/银行/排行/行列/太行山为 `háng`；行走/执行/一行（数量）为 `xíng`。
  - `模`：模样/模具/模板/一模一样规范为 `mú`；模型/模仿/模范/规模为 `mó`（`模板` 归 A 类双标准）。
  - `血`：复音书面词规范 `xuè`，口语单用及特定口语词（如 `流血`、`鸡血`、`血淋淋`）兼容 `xiě`。

---

## 4. 纠错、容错与错字五类决策矩阵

所有疑似错音、异读、错别字词条均按以下五类标准分类处置：

| 类别 | 判定条件 | 主词库处理 | `corrections.dict.yaml` 处理 | 权重约束 | 典型示例 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A 类：双标准 / 争议 / 极冷门专业音** | ① L1 与 L2/L3/L4 存在官方或行业分歧；② 规范音极冷门且另一读音已成跨圈层通行习惯；③ 两岸或旧读长期并行 | **双读音全部保留** | **双方均挂双读音注释**；主词库已有读音通过 `w=0` 行挂载注释 | 主读音保留自然词频；次读音取合理中低权重（通常 `30–200`） | `味噌`、`雪佛兰`、`密钥`、`私钥`、`公钥`、`模板`、`荨麻`、`荨麻疹`、`说服`、`呆板`、`鼻塞`、`比萨`、`血脉偾张`、`陈寅恪`、`吐蕃`、`槟榔`、`混淆`、`张柏芝`、`宝幢` |
| **B 类：个人多音字习惯** | 词中含合法多音字，因长期习惯或类推使用其**另一合法字音**，且日常输入高频 | 仅存规范音 | 收录该习惯读音并标注规范正音 | `50–450`，且**严格低于同音全部常用正词**（如 `zhu jiao` 下 `助教 > 主教 > 主角`） | `主角/角色/配角 (jiao)`、`关卡 (ka)`、`露出 (lu)`、`单薄 (bao)`、`游说 (shuo)`、`称职 (cheng)`、`埋怨 (mai)`、`发酵 (xiao)`、`强劲 (jin)`、`下载 (zai)` |
| **C 类：冷僻字 / 专名 / 地名 / 成语易错音** | 含生僻字、古音字、地名特读或典故成语，高学历群体亦常误读 | 仅存规范音 | 收录高频易错读音并附正音提示 | `15–150`，不干扰同音常用词 | `纨绔`、`草薙`、`贾平凹`、`鄱阳湖`、`鸭绿江`、`大腹便便`、`虚与委蛇`、`饮鸩止渴`、`宫商角徵羽`、`高句丽`、`脑卒中`、`潟湖` |
| **D 类：低文化 / 识字硬伤误读** | ① 非多音字义项混淆；② 基础声韵母错误（`f/h`、`n/ng`、`zh/z` 等，属模糊音范畴）；③ 常见字读半边且未形成行业双标准 | 不收录（上游引入即删） | **一律不收录；上游存在则清除** | 删除 | `阈值 fa zhi`、`应该 yin gai`、`曾经 ceng jin`、`崩溃 ben kui`、`非常 hui chang`、`两个 lia ge`、`哺乳 pu ru`、`头皮屑 xue`、`感慨 gan gai`、`歇斯底里 jie*`、`损人利己 li yi`、`角斗士 jiao` |
| **E1 类：高频顽固习惯错写** | 全网长期极高频混用、存在明确检索容错需求（严格白名单制，总量 `<= 10` 条） | 可保留极低权重 | 视情况保留极低权重错写或引导至正词 | **`<= 30`**，且 `<= 对应正词权重 / 20` | `经验贴`（`30` vs `经验帖 1700`）、`截止目前`（`30` vs `截至目前 819`）、`准确的说`（`30` vs `准确地说 1000`） |
| **E2 类：明确错别字 / 语法硬伤 / 外文拼错** | 违背现代汉语用字或语法规范，无双标准争议 | **一律删除** | 仅允许以正确词形入 `corrections` 纠偏（如 `烘培 -> 烘焙`），主词库不保留错字词形 | 删除错字词形 | `亦或是`、`懂得都懂`、`完型填空`、`反应出`、`为人处事`、`拿的出手`、`看的出来`、`算的上是`、`过敏源`、`必须品`、`自已的` |

### 4.1 `corrections.dict.yaml` 注释排版格式

为适配竖排 5 候选界面（`Noto Sans CJK TC 13pt`），第 4 列注释常规纠错建议不超过 **24 个字符**，双读音对照建议不超过 **32 个字符**，硬上限 **40 个字符**（`dict_lint.py` 强制校验）：

1. **双字词纯纠错**：标完整带调拼音，如 `zhǔ jué`、`mú yàng`、`dào heng`。
2. **三字及以上纯纠错**：仅在易错字后括号标调，如 `高句(gōu)丽`、`优惠券(quàn)`、`宫商角(jué)徵羽`。
3. **错字纠偏**：使用 `错字(正字zhèng yīn)`，如 `烘培(焙bèi)`、`饮鸠(鸩zhèn)止渴`、`粘(黏nián)膜`。
4. **A 类双标准注释**：使用 `标签A 读音A / 标签B 读音B`，标签统一从以下 4 组中选取：
   - `规范 ... / 常见 ...`
   - `规范 ... / 旧读 ...`
   - `规范 ... / 习惯 ...`
   - `现汉 ... / 审音拟 ...` 或 `大陆 ... / 台湾 ...`

---

## 5. 权重标尺与工程红线

### 5.1 六档静态权重标尺

| 档位 | 权重区间 | 适用对象 | 调权原则 |
| :--- | :---: | :--- | :--- |
| **T0 单字表** | `8105` 原统计量级 | 规范单字 | 仅在同音单字倒挂时局部校准 |
| **T1 核心高频词** | `5,000+` | 国民级高频日常双/三字词 | 原则上冻结；修改前须跑盲测 A/B |
| **T2 常用现代词** | `500 – 4,999` | 常规实词、高频技术与行业词 | 新增常见现代词建议起评 `500 – 1,000`，再按同音竞争表微调 |
| **T3 专名 / 社区词 / 领域词** | `50 – 499` | 人名、品牌、新流行词（如 `丈育 300`）、专业术语 | 不得高于同音常见通用词 |
| **T4 纠错 / 容错 / 碎片** | `10 – 450` | B/C 类纠错、E1 习惯错写（`<= 30`）、口语弱碎片（如 `鸡的 150`） | 严格受同音安全边界约束 |
| **T5 零权覆盖层** | `0` | `corrections` 主音注释行、冷僻叠字/拆字 | 不叠加静态权重，依赖主表或上下文召回 |

### 5.2 四条工程红线

1. **`.gram` 粘连保护（只降权，不硬删）**：凡在 `wanxiang-lts-zh-hans.gram` 中承担高频转移路径的粘连短语（常见于含 `的/了/在/一/是/不` 的短语，如 `时间的`、`我的`、`一行`），严禁硬删（DELETE），只允许温和降权（REWEIGHT），且降权后须经盲测验证无整句退化。
2. **同音竞争安全边界（Collision Guard）**：新增或上调权重的词条须通过 `python scripts/dict_lint.py --check-collisions` 检查同一 `code` 下 Top-5 竞争词；B/C 类纠错词与 E1 习惯错写严禁反超同音高频正词。
3. **长尾污染清理标准**：满足明显截断拼接尾块（如 `composite` 尾部抓取垃圾段）、非法标点/数字乱码、低俗广告、无意义人名乱拼、已核实错误音译、且不在 `.gram` 高频路径中的词条，一律清除。
4. **英文、中英混合与字母数字词表规范**：
   - `en_ext.dict.yaml`：由 `rules/en_additions.tsv` 管理现代开发/AI/硬件补充词；普通词全小写，专名保持规范大小写（如 `GitHub`、`ONNX`、`DeepSeek`、`Claude`）。
   - `en_dicts/cn_en*.txt`：严禁手工分改 7 份文件；统一在 `rules/cn_en_source.tsv` 维护增删改规则，经 `scripts/build_cn_en.py` 自动派生并同步全部 7 种布局（全拼 + 自然码/小鹤/智能 ABC/微软/搜狗/紫光）。
   - `rime_frost.dict.yaml` 字母数字词：统一在 `rules/alphanum_additions.txt` 维护，仅收高频短组合（长度 `<= 10`）。

---

## 6. 声明式规则架构（`rules/` SSOT）

所有新增与持续维护的词库覆写规则统一沉淀在 `rules/` 目录（纯文本 TSV/TXT，天然适配 `git diff` 与人工审查），由 `scripts/clean-dicts.py` 在清洗管线中确定性加载并执行：

```text
rules/
  README.md                 # 规则表字段说明与示例
  phonetics_fix.tsv         # 读音修正：target_file | word | old_py | new_py | reason | source
  word_fixes.tsv            # 词形修正：target_file | old_word | old_py | new_word | new_py | reason | source
  dual_readings.tsv         # 双读音双注释：word | py1 | w1 | note1 | py2 | w2 | note2 | target_file | source
  corrections.tsv           # 错音/错字纠错：word | wrong_py | weight | comment | category | source
  weights.tsv               # 权重覆盖：target_file | word | py | weight(N/<=N/>=N) | reason
  deletions.tsv             # 精确删除：target_file | word | py | reason
  additions.tsv             # 补录词条：target_file | word | py | weight | category | source
  en_additions.tsv          # 英文补充（en_ext）：word | code | weight | category
  en_fixes.tsv              # 英文修正/删除/调权：target_file | old_word | old_code | action | new_word | new_code | weight | reason
  cn_en_source.tsv          # 中英混合单一源（驱动 7 份 cn_en*.txt）：action | word | prefix_en | cn_syls | suffix_en | emit_lower | note
  alphanum_additions.txt    # 字母数字补充（rime_frost.dict.yaml）
  opencc_fixes.tsv          # OpenCC 文本修复：target_file | key | action | value | reason
scripts/
  clean-dicts.py            # 确定性、幂等词库清洗主引擎（依次执行结构清洗 + rules/ 覆写 + 全局去重）
  dict_rules.py             # rules/ 解析、应用、冲突校验与规则命中计数（stale_rules）模块
  build_cn_en.py            # cn_en_source.tsv -> 7 布局 en_dicts/cn_en*.txt 生成器
  dict_lint.py              # 独立静态门禁、幂等校验、同音碰撞预检与 CI 变更熔断脚本
```

### 规则引擎安全机制

- **静态冲突拦截**：同一 `(target_file, word, py)` 不得同时出现在 `deletions.tsv` 与 `additions.tsv`/`weights.tsv`；`phonetics_fix.tsv` 禁止形成链式二次改写循环；`dual_readings.tsv` 单点声明并同步生成主词库双音与 `corrections.dict.yaml` 双注释。
- **规则活性追踪（`stale_rules`）**：每次运行 `scripts/clean-dicts.py --manifest <path>` 记录各条外部规则命中次数；上游 `gaboolic/rime-frost` 自行修复导致连续 2 次同步零命中的历史规则，在季度审计时核实退场。

---

## 7. 维护节奏、防过拟合纪律与四级上线门禁

### 7.1 四种维护节奏

| 场景 | 频率 | 标准操作流（SOP） |
| :--- | :--- | :--- |
| **日常微调** | 按需 | 按第 3、4 节决策树定性 → 写入 `rules/*.tsv`（附 `reason` 与权威依据）→ 运行 `python scripts/clean-dicts.py` → 运行 `python scripts/dict_lint.py --strict --idempotent --check-collisions` → 补 1 条 `bench/accuracy-cases.json` 断言 → 本机部署验证。 |
| **上游周更** | 每周日（CI） | `.github/workflows/sync-upstream-dicts.yml` 拉取 `gaboolic/rime-frost` → 运行 `clean-dicts.py` → 运行 `dict_lint.py --strict --idempotent --diff-budget` → 全通过且在熔断阈值内则自动提交推送；**若校验失败，阻断推送并开/更 Issue 告警；若活跃词条 `|Δ| > 5,000` 或 `corrections` 变动 `> 50` 行，阻断直推 `main` 并自动提 PR 交人工复核**。 |
| **月度反馈复盘** | 每月一次 | 聚合分析本机 `%APPDATA%\Rime\neural\feedback.jsonl` 的高频翻页模式（仅提取脱敏词级频次，不保留原句），筛选稳定缺词或持续错排项按规范吸收进 `rules/`。 |
| **季度专题审计** | 每季度一次 | 脚本扫描 ＋ LLM 分片审计轮巡（Q1 审音与多音字 / Q2 现代新词与中英混输 / Q3 细胞词库长尾污染 / Q4 规则退场与权重漂移）；确定性上游真 Bug 按 `docs/upstream-issues/GUIDELINE.md` 打包回馈上游。 |

### 7.2 评测防过拟合铁律

1. **功能回归集**（`bench/accuracy-cases.json`）：验证确定性契约（收词、双读音注释、指定同音相对序、台繁双出、中英混输），可随规则新增同步扩充。
2. **公开参考基线集**（科技周刊 200 句、知乎热榜子集）：仅用于大改动前后的 **A/B 退化监控**，**严禁根据参考集错句反向特调特定词条或权重**。
3. **冻结盲测集**（跨领域新闻/小说/散文等未见语料）：严格只读，仅在季度审计或大幅调权后做整体验收。

### 7.3 四级上线门禁

| 门禁 | 执行命令 / 检查项 | 触发条件 | 通过标准 |
| :--- | :--- | :--- | :--- |
| **Gate 1：静态 Lint 与幂等** | `python scripts/dict_lint.py --strict --idempotent` | 每次改动 ＋ 每周 CI | 5 项不变量全 `0`、规则零冲突、`cn_en` 7 份一致、注释合规、二次执行 SHA-256 差异 = `0` |
| **Gate 2：引擎编译** | `WeaselDeployer /build` 或 `scripts/deploy-local.ps1` | 每次本地改动 | 退出码 `0`、Weasel 日志 0 error / 0 warning、`.table.bin` 体积变动可解释 |
| **Gate 3：功能回归** | `bench/accuracy-test.ps1 -WaitNeural` | 每次本地改动 | 100% 通过（0 failed），单实例 `WeaselServer.exe` 正常 |
| **Gate 4：盲测防退化** | `bench/eval-accuracy.py`（DP/FP × 统计/神经） | 涉及权重调整、批量删词或季度审计 | 字准与句准无退化；任何单句波动须查明根因 |
