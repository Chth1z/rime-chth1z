# [Bug] `cn_en_{abc,ziguang}.txt` 双拼错码及 `opencc/others.txt` 化学式事实错误

## 环境与版本
- **上游版本**：`iDvel/rime-ice@927e1cf`（其中 `V怪客` 与 `opencc/others.txt` 同步影响 `gaboolic/rime-frost@ab64ecf`）
- **客户端与引擎**：Weasel `0.17.4` / `librime 1.17.0`
- **影响范围**：智能 ABC 双拼（`double_pinyin_abc`）、紫光双拼（`double_pinyin_ziguang`），以及开启 `emoji` 开关（加载 `opencc/emoji.json` → `others.txt`）的全部方案

## 实际影响
- **属于哪类问题**：词典编码错误导致候选不可达 / 化学式写法错误
- **实际影响说明**：
  1. `en_dicts/cn_en_abc.txt` 与 `en_dicts/cn_en_ziguang.txt` 存在双拼编码错误，按对应双拼规范键位无法命中「V怪客」与「T.S.艾略特」。
  2. `opencc/others.txt`（通过 `opencc/emoji.json` 在 `emoji` 开关启用时生效）存在 2 处化学式错误，直接向用户输出错误化学式候选。

## 复现步骤
1. 使用上游默认配置（未叠加个人 `*.custom.yaml`）。
2. 在智能 ABC 双拼下测试「V怪客」（智能 ABC 规则 `uai -> y`，`guai` 应为 `gy`）：
   - 输入 `Vgyke` / `vgyke`：**实际结果**无「V怪客」（`Vgyke` 走计算器报错 `gyke 解析失败`）；改输入错误编码 `Vgcke` / `vgcke` 才出现「V怪客」。
   - **预期结果**：输入 `Vgyke` / `vgyke` 命中「V怪客」。
3. 在 `iDvel/rime-ice@927e1cf` 的智能 ABC / 紫光双拼下检查「T.S.艾略特」（`double_pinyin_abc.schema.yaml:366` 规定 `ve -> m`、`lve -> lm`；`double_pinyin_ziguang.schema.yaml:363` 规定 `ve -> n`、`lve -> ln`）：
   - `en_dicts/cn_en_abc.txt:608-609` 误用自然码键位 `t` 写作 `TSollte` / `tsollte`（应为 `TSollmte` / `tsollmte`）。
   - `en_dicts/cn_en_ziguang.txt:608-609` 误用自然码键位 `t` 写作 `TSoplte` / `tsoplte`（应为 `TSoplnte` / `tsoplnte`）。
4. 开启 `emoji` 开关（`opencc/emoji.json`），输入 `yaliusuanna` / `lanfan`：
   - **实际结果**（实测干净上游）：
     - `yaliusuanna` → 候选出现 `亚硫酸钠` 后紧跟 **`NaSO₃`**（漏写下标 `₂`）
     - `lanfan` → 候选出现 `蓝矾` 后紧跟 **`CuSO₄·₅H₂O`**（结晶水系数 `5` 误用下标 `₅`）
   - **预期结果**：「亚硫酸钠」输出 `Na₂SO₃`；「蓝矾」输出 `CuSO₄·5H₂O`。

## 原因位置
- `en_dicts/cn_en_abc.txt:480-481`（`rime-frost@ab64ecf` 位于 `:458-459`）：`V怪客` 误编为 `Vgcke` / `vgcke`（智能 ABC 中 `c` 对应 `in`，`uai` 应为 `y`）。
- `en_dicts/cn_en_abc.txt:608-609`：`T.S.艾略特` 误编为 `TSollte` / `tsollte`（`lve` 应为 `lm`）。
- `en_dicts/cn_en_ziguang.txt:608-609`：`T.S.艾略特` 误编为 `TSoplte` / `tsoplte`（`lve` 应为 `ln`）。
- `opencc/others.txt:1096`（`rime-frost` 位于 `:1100`）：`亚硫酸钠\t亚硫酸钠 NaSO₃`。
- `opencc/others.txt:1123`（`rime-frost` 位于 `:1127`）：`蓝矾\t蓝矾 CuSO₄·₅H₂O`。
- （附带格式清理：`opencc/others.txt:661` `tab\ttab ⇥ \t` 行尾多出一个 `\t`；实测 OpenCC 运行时会自动忽略尾随空白、不影响候选，顺手清理即可。）

```tsv
# en_dicts/cn_en_abc.txt:480-481 & 608-609
V怪客	Vgcke
V怪客	vgcke
T.S.艾略特	TSollte
T.S.艾略特	tsollte

# en_dicts/cn_en_ziguang.txt:608-609
T.S.艾略特	TSoplte
T.S.艾略特	tsoplte

# opencc/others.txt
亚硫酸钠	亚硫酸钠 NaSO₃
蓝矾	蓝矾 CuSO₄·₅H₂O
```

## 修改建议
- 已逐条比对 `rime-ice@927e1cf` 全部 7 份 `en_dicts/cn_en*.txt`（各 1,011 行），除上述 3 处外其余 4 套双拼（自然码/小鹤/微软/搜狗）均无编码偏差：
  - `en_dicts/cn_en_abc.txt`：`Vgcke` / `vgcke` → `Vgyke` / `vgyke`；`TSollte` / `tsollte` → `TSollmte` / `tsollmte`
  - `en_dicts/cn_en_ziguang.txt`：`TSoplte` / `tsoplte` → `TSoplnte` / `tsoplnte`
- `opencc/others.txt`：
  - `亚硫酸钠\t亚硫酸钠 NaSO₃` → `亚硫酸钠\t亚硫酸钠 Na₂SO₃`
  - `蓝矾\t蓝矾 CuSO₄·₅H₂O` → `蓝矾\t蓝矾 CuSO₄·5H₂O`
  - 顺手移除 `tab\ttab ⇥ \t` 行尾多余制表符
