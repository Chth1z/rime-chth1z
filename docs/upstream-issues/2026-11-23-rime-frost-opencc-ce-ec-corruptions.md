# [Bug] `opencc/{english_chinese,chinese_english,emoji,others}.txt` 存在格式损坏、释义错贴与键遮蔽

## 环境与版本
- **上游版本**：`gaboolic/rime-frost@c982966`（已确认最新 `master` 仍可复现；以下问题均为白霜独有或白霜未同步雾凇修复的词表问题）
- **客户端与引擎**：Weasel `0.17.4` / `librime 1.17.0`
- **影响范围**：开启 `chinese_english` 开关（加载 `opencc/chinese_english.json`，含 `chinese_english.txt` 与 `english_chinese.txt`）或 `emoji` 开关（加载 `opencc/emoji.json`，含 `emoji.txt` 与 `others.txt`）的全部白霜方案

## 实际影响
- **属于哪类问题**：OpenCC 词表格式损坏、候选截断拆分、同键遮蔽、不可达键及内容错误
- **实际影响说明**：
  1. `opencc/english_chinese.txt` 存在 **314 条**行尾残留 `NUM NUM` 垃圾（单英文词 310 条）、**79 条**中文释义中间混入换行空格、**13 条** `;` 前多空格、**7 条**双空格、**1,184 条**含空格多词键（单英文词匹配不可达），以及 4 条 `^` 原始分隔符损坏与 `bestrid`/`bestridden` 复制错释义；在开启 `chinese_english` 开关输入常用英文词时，**直接向用户弹出字面量 `NUM` 候选、被腰斩的半个中文词以及 `;` 开头的破碎候选**。
  2. `opencc/chinese_english.txt` 在高频日常词「小孩子」中残留陈旧种族歧视词 `pickaninny`（开启 `chinese_english` 直接排第 4 候选），另存在 6 条全角空格 `U+3000` 不可达键、成语双错字（`百尺杆头更尽一步`）与地名错字（`格雷罗内洛罗`）。
  3. `opencc/emoji.txt`（白霜独有差异）与 `opencc/others.txt` 存在同键遮蔽及多处错字键：`emoji.txt:2078` `食盐 🧂` 在 `emoji.json` 转换链中位于 `others.txt` 之前，直接**完全遮蔽**了白霜独有的 `others.txt:1033` `食盐 NaCl`；另含 4 条错别字键（`手指捏和`/`狐狸偷`/`盘绕是炸鱼饼`/`鞠躬勋章`）、2 条含短破折号 `U+2013` 不可达键（`特里斯坦–达库尼亚*`），以及 4 条扑克红桃 `♥️ (U+2665)` 未同步 `rime-ice` 改为规范红心 `❤️ (U+2764)`。
  4. `opencc/others.txt:1147` 的 `V动物` 含 54 个冗余重复 emoji（其中 51 个完全重复虽会被 `librime` 运行时去重，但 `🕷`/`🕷️`、`🕊`/`🕊️`、`🐿`/`🐿️` 3 组因 `U+FE0F` 差异在运行时仍重复出现 2 遍）。

## 复现步骤
1. 使用干净的 `gaboolic/rime-frost@c982966` 默认配置（未叠加个人 `*.custom.yaml`）部署。
2. 开启 `chinese_english` 开关（加载 `opencc/chinese_english.json`），在默认全拼 `rime_frost` 下输入以下常见英文词与中文词，实测候选结果：
   - 输入 `crime` → `[crime, n.犯罪;罪行;罪恶, NUM, ...]`（**字面量 `NUM` 直接出现在第 3 候选**；`clerk`、`condition` 同样在第 4 候选弹出 `NUM`）
   - 输入 `world` → `[world, n.世界;...;社会生, 活;大量, ...]`（「社会生活」被空格腰斩为两个独立候选）
   - 输入 `strike` → `[strike, ..., vt....;发, 现;划燃, ...]`（「发现」被腰斩）
   - 输入 `warm` → `[warm, ..., a....;色, 情的, ...]`（「色情的」被腰斩）
   - 输入 `draw` → `[draw, ..., vt....;制订, ;草拟;吸引, ...]`（出现以 `;` 开头的破碎候选；`wind` 同现 `;使弯曲;使迂回`）
   - 输入 `xiaohaizi` → `[小孩子, child, kid, pickaninny, tad, tike, ...]`（第 4 候选直接输出 `pickaninny`）
3. 开启 `emoji` 开关（加载 `opencc/emoji.json`），输入 `shiyan`：
   - **实际结果**：`[实验, 试验, 饰演, 食盐, 🧂, 誓言, 时延, 食言]`——`others.txt:1033` 定义的 `NaCl` 被 `emoji.txt:2078` 遮蔽，完全不会出现。
   - **预期结果**：无 `NUM` 垃圾候选、无中文释义断词与 `;` 碎片、移除 `pickaninny`，且 `食盐` 同时输出 `🧂` 与 `NaCl`。

## 原因位置

以下行号与条数均在 `gaboolic/rime-frost@c982966` 原始文件上逐行核实：

- `opencc/english_chinese.txt`（共 43,788 行）：
  - **314 行**尾随 ` NUM NUM`（单英文词 310 行，含 `L7275` `clerk`、`L8163` `condition`、`L9288` `crime` 等常用词）
  - **79 行**释义中间混入换行空格（含 `L4792` `bound`、`L4961` `break`、`L9678` `cut`、`L18342` `high`、`L22492` `light`、`L35916` `smooth`、`L37451` `strike`、`L42646` `warm`、`L43422` `world` 等常用词）
  - **13 行**分号前多空格（含 `L12005` `draw`、`L14285` `fall`、`L22578` `line`、`L38416` `tab`、`L43168` `wind` 等）
  - **7 行**双空格（`L5248` `bug` 兼尾部重复 `n.错误`、`L22578` `line`、`L23633` `marker`、`L32426` `remit`、`L33544` `rule`、`L42774` `way`、`L43168` `wind`）
  - **1,184 行**键中含空格的多词短语（单英文词 OpenCC 匹配不可达）
  - 其余源文件释义损坏（当前词条未在 `en.dict.yaml` 收录，但词表文本已损坏）：`L3` `a/c` 原始释义串乱码、`L12690` `electroluminescent` / `L20498` `intercommunicating` / `L37995` `super-regenerative` / `L37996` `superregenerative`（后两条兼拼错 `eceiver`）含 `^` 分隔符损坏、`L3933` `bestrid` / `L3934` `bestridden` 误复制 `L3932` `bestrewn` 的 `vbl.撒布;布满`（实为 `bestride` 过去式/分词）
- `opencc/chinese_english.txt`：
  - `L18107`：`小孩子\t小孩子 child kid pickaninny tad tike`
  - `L963`、`L1306`、`L24821`、`L36297`、`L36339`、`L41327`：键中含全角空格 `U+3000`
  - `L36297-36299`：`百尺杆头...更尽一步`（应为 `百尺竿头更进一步`）
  - `L28920`：`格雷罗内洛罗`（应为 `格雷罗内格罗`，Guerrero Negro）
  - `L1-L3`：文件头注释行尾随空格
- `opencc/emoji.txt`（白霜独有部分；与雾凇共有的黑白方块反转、`拇指向上`/`红发男` 已另行向 `iDvel/rime-ice` 反馈）：
  - `L2078`：`食盐\t食盐 🧂` 遮蔽 `opencc/others.txt:1033` `食盐\t食盐 NaCl`
  - `L685` `手指捏和`（应为 `手指捏合`）、`L1552` `狐狸偷`（应为 `狐狸头`）、`L2122` `盘绕是炸鱼饼`（应为 `盘绕式炸鱼饼`）、`L2817` `鞠躬勋章`（应为 `军功勋章`）
  - `L4624-4625`：`特里斯坦–达库尼亚群岛` / `特里斯坦–达库尼亚`（含 `U+2013` 短破折号不可达）
  - `L68` `喜欢`、`L535` `爱心`、`L542` `love`、`L548` `心形`：使用扑克红桃 `♥️ (U+2665)`（`rime-ice` 已统一为规范红心 `❤️ (U+2764)`）
- `opencc/others.txt:1147`：`V动物` 含 51 个完全重复 token 及 3 组 `U+FE0F` 视觉重复对（`🕷`/`🕷️`、`🕊`/`🕊️`、`🐿`/`🐿️`）。

## 修改建议
- `opencc/english_chinese.txt`：移除含空格键与行尾 `(?:\s+NUM)+$`，合并双空格与 ` ;`，将非词性标签起始的断行续接段拼回前项，并修复上述 `a/c`、`bug`、4 条 `^` 条目与 `bestrid`/`bestridden`。
- `opencc/chinese_english.txt`：移除 `小孩子` 中的 `pickaninny`，删除 6 条 `U+3000` 及标点不可达键，修正 `百尺竿头更进一步` 与 `格雷罗内格罗`，去除前 3 行尾随空格。
- `opencc/emoji.txt` & `opencc/others.txt`：将 `emoji.txt:2078` 合并为 `食盐\t食盐 🧂 NaCl`（并移除 `others.txt:1033` 冗余项）、修正上述 4 条错别字键与 2 条破折号键、将 4 处 `♥️` 同步为 `❤️`；对 `others.txt:1147` `V动物` 按去除 `U+FE0F` 后的基础码位去重（优先保留带 `U+FE0F` 彩色形式）。
