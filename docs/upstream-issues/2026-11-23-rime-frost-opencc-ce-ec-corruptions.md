# [Bug] `opencc/english_chinese.txt`、`chinese_english.txt` 及 `others.txt` 存在批量格式损坏与释义错误

## 环境与版本
- **上游版本**：`gaboolic/rime-frost@ab64ecf`（`chinese_english.txt`、`english_chinese.txt` 及 `others.txt` 的 `V动物` 区块均为白霜独有）
- **客户端与引擎**：Weasel `0.17.4` / `librime 1.17.0`
- **影响范围**：启用英汉/汉英/符号 OpenCC 滤镜的全部白霜方案

## 实际影响
- **属于哪类问题**：OpenCC 词表格式损坏、候选截断拆分、不可达键及内容错误
- **实际影响说明**：
  1. `opencc/english_chinese.txt` 存在 **1,184 条**含空格多词键（单英文词 OpenCC 匹配不可达）、**314 条**行尾残留 `NUM NUM` 垃圾、**75 条**中文释义中间混入换行空格导致单个词被拆成两个候选、**4 条**残留 `^` 原始词典分隔符，以及 `bestrid`/`bestridden` 复制错释义。
  2. `opencc/chinese_english.txt` 存在全角空格 `U+3000` 不可达键、成语双错字（`百尺杆头更尽一步`）、地名错字（`格雷罗内洛罗`），以及高频词「小孩子」释义中残留陈旧种族歧视词 `pickaninny`。
  3. `opencc/others.txt` 的 `V动物` 键（`L1147`）包含 **54 个**重复 emoji（51 个完全重复 + 3 个 VS16 `U+FE0F` 视觉重复 `🕷`/`🐿`/`🕊`）。

## 复现步骤
1. 使用上游 `gaboolic/rime-frost@ab64ecf` 默认配置，开启 `english_chinese` / `chinese_english` 滤镜。
2. 在英文模式下输入 `cicely` / `electroluminescent` / `bestrid` / `cut`：
   - **实际结果**：`cicely` 候选末尾出现两个 `NUM`；`electroluminescent` 出现 `display^n.电场发光显示器`；`bestrid` 显示为 `vbl.撒布;布满`（错自上一行 `bestrewn`）；`cut` 的「切断」被拆成 `切` 与 `断` 两个候选。
   - **预期结果**：无 `NUM`/`^` 乱码、无中文字词断行拆分、`bestrid`/`bestridden` 释义为 `vbl.跨骑;跨坐;跨过`。
3. 在中文模式下输入「小孩子」（开启汉英注释）：候选释义出现 `pickaninny`；输入 `Vdongwu` 展开 `V动物` 出现大量重复动物 emoji。

## 原因位置
- `opencc/english_chinese.txt`（共 43,788 行）：
  - `L7009` `cicely` 等 **314 行**尾随 ` NUM NUM`
  - `L12690` `electroluminescent`、`L20498` `intercommunicating`、`L37995` `super-regenerative`、`L37996` `superregenerative`（后两条兼拼错 `eceiver`）含 `^` 分隔符损坏
  - `L3933` `bestrid`、`L3934` `bestridden` 误复制 `L3932` `bestrewn` 的 `vbl.撒布;布满`
  - `L3` `a/c` 含原始词典乱码串、`L5122` `bug` 含双空格与尾部重复 `n.错误`；另有 13 处 ` ;` 前多余空格与 75 处释义中间空格断词
- `opencc/chinese_english.txt`：
  - `L18107`：`小孩子\t小孩子 child kid pickaninny tad tike`
  - `L963`、`L1306`、`L24821`、`L36297`、`L36339`、`L41327`：键中含全角空格 `U+3000`
  - `L36297-36299`：`百尺杆头...更尽一步`（应为 `百尺竿头更进一步`）
  - `L28920`：`格雷罗内洛罗`（应为 `格雷罗内格罗`，Guerrero Negro）
- `opencc/others.txt:1147`：`V动物` 含 54 个重复 emoji（含 `🕷`/`🕷️`、`🐿`/`🐿️`、`🕊`/`🕊️`）。

## 修改建议
- `opencc/english_chinese.txt`：移除含空格键与行尾 `(?:\s+NUM)+$`，合并双空格与 ` ;`、拼接非词性标签起始的断行释义，并手工修正上述 4 条 `^` 条目、`a/c`、`bug` 与 `bestrid`/`bestridden`。
- `opencc/chinese_english.txt`：移除 `小孩子` 中的 `pickaninny`，删除 6 条 `U+3000` 与标点不可达键，修正 `百尺竿头更进一步` 与 `格雷罗内格罗`，清理前 3 行注释尾随空格。
- `opencc/others.txt`：对 `V动物` 按去掉 `U+FE0F` 后的基础码位去重（优先保留带 `U+FE0F` 的彩色 emoji 形式）。
