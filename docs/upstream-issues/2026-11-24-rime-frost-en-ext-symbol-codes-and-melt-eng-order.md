# [Bug] `en_ext.dict.yaml` 中 `C++`/`C#`/`01.AI` 编码缺失符号及 `melt_eng_algebra_common.yaml` 派生顺序导致谐音失效

## 环境与版本
- **上游版本**：`gaboolic/rime-frost@c982966`（已确认最新 `master` 仍可复现；其中 `C++`/`C#` 与 `01.AI` 为白霜独有改动/词条，`melt_eng_algebra_common.yaml` 顺序问题承自 `iDvel/rime-ice@927e1cf`）
- **客户端与引擎**：Weasel `0.17.4` / `librime 1.17.0`
- **影响范围**：使用 `melt_eng` 的全拼与全部 6 套双拼方案

## 实际影响
- **属于哪类问题**：词条编码与拼写派生规则脱节，导致常见技术词的英文/中文谐音全部失效
- **实际影响说明**：
  1. **`C++`、`C#` 历史绕过（`fd2f491`）导致全部中文谐音及 `Cplusplus` 断链**：已核对提交历史，`fd2f491`（2025-02-04「去掉置顶词」）注释掉 `pin_cand_filter` 中的 `c → 才 从` 后，因 `C++`/`C#` 经 `derive/[^a-zA-Z0-9]//` 会折叠为单字母 `c` 抢占首位，当时将 `en_dicts/en_ext.dict.yaml:997-998` 改为 `C++\tCpp` 与 `C#\tCsharp` 作为规避。但该改法的副作用是导致 `melt_eng_algebra_common.yaml` 的 `derive/\+/plus/` 及 `melt_eng_algebra.yaml` 全部 7 套方案的 `derive/\+/jia|jw|jx|jd/`、`derive/#/jing|jy|jk|j;/` 全部失效（全拼 `Cjiajia`/`Cplusplus`/`Cjing` 与双拼 `Cjwjw`/`Cjy` 均无候选）。母库 `iDvel/rime-ice#1465`（`7232b17`，2026-01-30）一年后遇到完全相同的 `c` 键抢占问题，也证实直接改词编码会破坏双拼派生，最终采用在 `melt_eng` 末尾追加 `- erase/^[a-z]$/` 的方式无副作用解决。
  2. **`01.AI` 编码遗漏句点 `.`**：白霜独有词条 `en_dicts/en_ext.dict.yaml:2277` 将 `01.AI` 的编码写为 `01AI`（与相邻 `L2278: 01AI\t01AI` 相同），导致 `dot`/`dian`/`dm` 派生无法触发，`lingyidianAI`、`lyyidmai`、`zeroonedotAI` 均无法命中 `01.AI`。
  3. **`melt_eng_algebra_common.yaml` 管线顺序截断前导符号词条与全大写中文谐音**：`L48: erase/^[^a-zA-Z0-9].+$/` 与 `L50-64` 大小写派生位于 `melt_eng_algebra.yaml` 的 `__append` 之前，导致 `.gitignore`（`L2148`）、`.DS_Store`（`L15`）、`.npmrc`（`L1985`）的中文点号谐音（`diangitignore`/`dmgitignore` 等）以及 `NOTEPADJIAJIA`、`NOTEPADJWJW`、`NODEDIANJS` 等全大写中文谐音全部无候选。

## 复现步骤
1. 使用干净的 `gaboolic/rime-frost@c982966` 默认配置（`melt_eng.schema.yaml` 默认 `algebra_rime_frost`）编译部署，在 `rime.dll` 隔离会话下实测：
   - **`Cjiajia` → 无候选**；**`Cplusplus` → 无候选**（仅 `Cpp` 出 `C++`）
   - **`Cjing` → 无候选**（仅 `Csharp` 出 `C#`）
   - **`lingyidianAI` → 无候选**；**`zeroonedotAI` → 无候选**（仅 `lingyiAI` 出 `01.AI | 01AI`）
   - `dotgitignore` → `.gitignore`；**`diangitignore` → 无候选**
   - `dotDSStore` → `.DS_Store`；**`dianDSStore` → 无候选**
   - `dotnpmrc` → `.npmrc`；**`diannpmrc` → 无候选**
   - `Notepadjiajia` → `Notepad++`；**`NOTEPADJIAJIA` → 无候选**
   - `Nodedianjs` → `Node.js`；**`NODEDIANJS` → 无候选**
2. **预期结果**：全拼与双拼下 `Cjiajia`/`Cjwjw`/`Cplusplus` 正常命中 `C++`、`Cjing`/`Cjy` 正常命中 `C#`（且小写单键 `c` 与 `cjiajia`/`cjwjw`/`cjy` 不被英文劫持）；`lingyidianAI`/`lyyidmai`/`zeroonedotAI` 命中 `01.AI`；`diangitignore`/`dmgitignore`、`NOTEPADJIAJIA`/`NODEDIANJS` 均正常命中。

## 原因位置
- `en_dicts/en_ext.dict.yaml:997-998`：

```tsv
C++	Cpp
C#	Csharp
```

- `en_dicts/en_ext.dict.yaml:2277-2278`：

```tsv
01.AI	01AI
01AI	01AI
```

- `melt_eng_algebra_common.yaml:47-64`（`erase` 与大小写派生均在 `melt_eng_algebra.yaml` 的 `__append` 之前）：

```yaml
  # 禁用非英文、数字开头的编码
  - erase/^[^a-zA-Z0-9].+$/
  # 全小写
  - derive/^.+$/\L$0/
  # 全大写
  - derive/^.+$/\U$0/
  # 首字母大写
  - derive/^./\U$0/
  # 前 2~10 个字母大写
  ...
```

## 修改建议
1. **`01.AI`（直接改编码）**：将 `en_dicts/en_ext.dict.yaml:2277` 改为 `01.AI\t01.AI`。`derive/[.]//` 仍会保留 `01AI` 编码（原有 `lingyiAI`/`lyyiAI` 不受影响），同时恢复 `lingyidianAI`/`lyyidmai`/`zeroonedotAI`。
2. **`melt_eng_algebra_common.yaml` + `melt_eng_algebra.yaml`（调整管线顺序）**：将 `algebra_common` 拆为 `algebra_common_pre`（`L5-38` 英文数字/符号派生）与 `algebra_common_post`（`L39-64` 去符号、`erase/^[^a-zA-Z0-9].+$/`、大小写派生），在 `melt_eng_algebra.yaml` 各方案中按 `pre → 中文数字/符号谐音 → post` 顺序拼接，并保留 `algebra_common` 兼容外部直接引用。
3. **`C++` / `C#`（替代 `fd2f491` 的旧规避方案，在不污染小写单键 `c` 的前提下恢复 7 方案谐音派生）**：
   - **方案 A（推荐，直接对齐母库 `iDvel/rime-ice#1465` / `7232b17`）**：在 `algebra_common_post` 末尾补回 `- erase/^[a-z]$/`（并将全小写派生限制为 `derive/^.{4,}$/\L$0/` 或依赖 `erase/^[a-z]$/` 清除单字母小写），同时 `en_ext` 恢复 `C++\tC++`（保留 `C++\tCpp`）与 `C#\tC#`；
   - **方案 B（若希望继续避免 `en_ext` 出现单字母折叠编码）**：保留 `C++\tCpp` / `C#\tCsharp`，在 `en_ext` 补 `C++\tCplusplus`，并将 `C++`/`C#` 的大写中文谐音编码（全拼 `Cjiajia`/`Cjing`、自然码 `Cjwjw`/`Cjy`、小鹤 `Cjxjx`/`Cjk` 等，不生成小写）同步写入 7 份 `en_dicts/cn_en*.txt`。

> 附注：`.NET`（`en_ext:138-139` 为 `net 1` + `dotnet`）切忌直接将编码改为 `.NET`——因 `librime` 按编码键独立归一化权重且 `.` 的 ASCII 序小于字母，会导致输入 `net` 时 `.NET` 反超 `net 2`；如需支持 `dianNET`/`dmNET`，建议同样走 `cn_en*.txt`。
