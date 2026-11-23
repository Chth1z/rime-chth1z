# [Bug] `cn_en_abc.txt` 中「V怪客」智能 ABC 编码错误及 `opencc/others.txt` 化学式与符号格式错误

## 环境与版本
- **上游版本**：`iDvel/rime-ice@927e1cf`（同步影响 `gaboolic/rime-frost@ab64ecf`）
- **客户端与引擎**：Weasel `0.17.4` / `librime 1.17.0`
- **影响范围**：智能 ABC 双拼方案（`double_pinyin_abc`），以及启用 `opencc/others.txt` 滤镜的全部方案

## 实际影响
- **属于哪类问题**：编码错误导致候选不可达 / 词表事实错误与格式损坏
- **实际影响说明**：
  1. 智能 ABC 双拼下按规范键位 `Vgyke`（`guai -> gy`）无法打出「V怪客」，字典中误写为 `Vgcke`（智能 ABC 中 `c` 为 `in`，`gc` 非合法音节）。
  2. `opencc/others.txt` 中存在化学式事实错误与多余制表符，影响日常输入化学式与键盘符号。

## 复现步骤
1. 使用上游默认配置（未叠加个人 `*.custom.yaml`）。
2. 在智能 ABC 双拼下输入 `Vgyke`：未出现「V怪客」，改为输入错误编码 `Vgcke` 才会出现。
3. 在任意启用 `others` OpenCC 滤镜的方案下输入 `eryanghuaqing` / `yaliusuanna` / `lanfan`：
   - **实际结果**：「二氧化氢」附带 `H₂O₂`（实为过氧化氢，二氧化氢为 `HO₂`）；「亚硫酸钠」附带 `NaSO₃`（缺下标 `₂`）；「蓝矾」附带 `CuSO₄·₅H₂O`（结晶水系数误用下标 `₅`）；`tab` 行尾多出一个 `\t`。
   - **预期结果**：智能 ABC「V怪客」编码为 `Vgyke` / `vgyke`；删除错误的「二氧化氢 → `H₂O₂`」条目；「亚硫酸钠」修正为 `Na₂SO₃`；「蓝矾」修正为 `CuSO₄·5H₂O`；移除 `tab` 行尾多余制表符。

## 原因位置
- `en_dicts/cn_en_abc.txt:480-481`（`rime-frost` 位于 `:458-459`）：`uai` 韵母在智能 ABC 中对应 `y`，误编码为 `c`。
- `opencc/others.txt:661`（`rime-frost` 位于 `:663`）：`tab\ttab ⇥ \t` 尾部多出一个制表符。
- `opencc/others.txt:1020`（`rime-frost` 位于 `:1022`）：`二氧化氢\t二氧化氢 H₂O₂` 化学式事实错误（同文件已收正确词条 `过氧化氢\t过氧化氢 H₂O₂`）。
- `opencc/others.txt:1096`（`rime-frost` 位于 `:1100`）：`亚硫酸钠\t亚硫酸钠 NaSO₃` 漏写下标 `₂`。
- `opencc/others.txt:1123`（`rime-frost` 位于 `:1127`）：`蓝矾\t蓝矾 CuSO₄·₅H₂O` 化学计量数 `5` 误用下标 `₅`。

```tsv
# en_dicts/cn_en_abc.txt:480-481
V怪客	Vgcke
V怪客	vgcke

# opencc/others.txt
tab	tab ⇥ 	
二氧化氢	二氧化氢 H₂O₂
亚硫酸钠	亚硫酸钠 NaSO₃
蓝矾	蓝矾 CuSO₄·₅H₂O
```

## 修改建议
- `en_dicts/cn_en_abc.txt` 将 `V怪客` 的 `Vgcke` / `vgcke` 修正为 `Vgyke` / `vgyke`（全拼及其他 5 套双拼经逐条校验均正确）。
- `opencc/others.txt`：
  - `tab\ttab ⇥ \t` → `tab\ttab ⇥`
  - 删除 `二氧化氢\t二氧化氢 H₂O₂`
  - `亚硫酸钠\t亚硫酸钠 NaSO₃` → `亚硫酸钠\t亚硫酸钠 Na₂SO₃`
  - `蓝矾\t蓝矾 CuSO₄·₅H₂O` → `蓝矾\t蓝矾 CuSO₄·5H₂O`
