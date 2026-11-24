# [Bug] `melt_eng.schema.yaml` 派生顺序导致前导符号词条与全大写中文谐音失效，及搜狗双拼 `#` 键位误写

## 环境与版本
- **上游版本**：`iDvel/rime-ice@927e1cf`（已确认最新 `main` 仍可复现；其中第 1 项规则顺序问题同步影响下游 `gaboolic/rime-frost@c982966`）
- **客户端与引擎**：Weasel `0.17.4` / `librime 1.17.0`
- **影响范围**：
  1. `algebra_common` 顺序问题影响全拼（`algebra_rime_ice` / `algebra_pinyin`）与全部 7 套双拼的 `melt_eng` 英文拼写派生。
  2. `#` 键位误写影响搜狗双拼（`algebra_double_pinyin_sogou`）。

## 实际影响
- **属于哪类问题**：违背声明行为（`melt_eng` 拼写派生规则被前置规则提前截断 / 双拼键位表错配）
- **实际影响说明**：
  1. **前导符号词条中文谐音全部失效**：`melt_eng.schema.yaml:120` 的 `erase/^[^a-zA-Z0-9].+$/` 位于 `algebra_common` 中，在各方案通过 `__append` 追加中文 `.` 谐音（`derive/\./dian/`、`dm`、`dw`、`df`、`dj`）**之前**执行。`en_ext.dict.yaml` 中的 `.gitignore`（`L2321`）、`.DS_Store`（`L18`）、`.npmrc`（`L2135`）虽可通过英文 `dot` 派生（因 `L101: derive/\./dot/` 在 `L120` 之前），但在进入中文 `dian`/`dm` 规则前就已被擦除，导致 `diangitignore`/`dmgitignore`、`dianDSStore`/`dmDSStore`、`diannpmrc`/`dmnpmrc` 均无候选。
  2. **全大写中文谐音派生全部失效**：`melt_eng.schema.yaml:122-136` 的大小写派生（含 `L124: derive/^.+$/\U$0/`）同样在各方案 `__append` 之前执行。以 `Notepad++`、`Node.js`、`C++`、`C#` 为例，`L124` 先产生 `NOTEPAD++`、`NODE.JS`、`C++`、`C#`，随后 `__append` 再将符号替换为小写拼音，最终得到的是无法正常输入的大小写混排编码（如 `NOTEPADjiajia`、`NODEdianJS`），而用户按 CapsLock 或按住 Shift 输入 `NOTEPADJIAJIA`、`NOTEPADJWJW`、`NODEDIANJS`、`CJIAJIA`、`CJING` 均无候选（对比英文 `NOTEPADPLUSPLUS` 可正常出 `Notepad++`）。
  3. **搜狗双拼 `#` 键位误写**：`double_pinyin_sogou.schema.yaml:371` 定义 `ing → ;`，同块 `melt_eng.schema.yaml:277` 已正确写作 `derive/0/l;/`，但 `L290` 误写为 `derive/#/jy/`（自然码键位），导致搜狗双拼下按规范输入 `Cj;` 无法打出 `C#`，反向输入非搜狗键位 `Cjy` 才命中。

## 复现步骤
1. 使用干净的 `iDvel/rime-ice@927e1cf` 默认配置（`melt_eng.schema.yaml` 默认 `algebra_rime_ice`）编译部署，在 `rime.dll` 隔离会话下实测：
   - `dotgitignore` → `.gitignore`；**`diangitignore` → 无候选**
   - `dotDSStore` → `.DS_Store`；**`dianDSStore` → 无候选**
   - `dotnpmrc` → `.npmrc`；**`diannpmrc` → 无候选**
   - `Notepadjiajia` → `Notepad++`、`NOTEPADPLUSPLUS` → `Notepad++`；**`NOTEPADJIAJIA` → 无候选**
   - `Nodedianjs` → `Node.js`；**`NODEDIANJS` → 无候选**
   - `Cjiajia` → `C++`、`Cjing` → `C#`；**`CJIAJIA` / `CJING` → 无候选**
2. 切换至搜狗双拼 `algebra_double_pinyin_sogou`（并在 `speller/alphabet` 允许 `;`，与 `double_pinyin_sogou.schema.yaml:337` 一致）实测：
   - **`Cj;` → 无候选**
   - **`Cjy` → `C#`**（键位错配为自然码 `jy`）
   - `dotgitignore` → `.gitignore`；**`dmgitignore` / `NOTEPADJWJW` → 无候选**
3. **预期结果**：前导符号词条支持中文点号谐音（`diangitignore`/`dmgitignore` → `.gitignore` 等）；全大写中文谐音（`NOTEPADJIAJIA`/`NOTEPADJWJW`/`NODEDIANJS`/`CJIAJIA`/`CJING`）正常命中；搜狗双拼下 `Cj;` 命中 `C#`。

## 原因位置
- `melt_eng.schema.yaml:120-138`（`algebra_common` 尾部，位于所有 `algebra_*` 的 `__append` 之前）：

```yaml
  # 禁用非英文、数字开头的编码
  - erase/^[^a-zA-Z0-9].+$/
  # 四个字母以上派生全小写，以避免在低版本 Rime 和简拼重码
  - derive/^.{4,}$/\L$0/
  # 全大写
  - derive/^.+$/\U$0/
  # 首字母大写
  - derive/^./\U$0/
  # 前 2~10 个字母大写
  ...
  # 禁用小写单编码
  - erase/^[a-z]$/
```

- `melt_eng.schema.yaml:266-290`（`algebra_double_pinyin_sogou`）：

```yaml
  __append:
    ...
    - derive/0/l;/   # L277：ing 已正确写作 ;
    ...
    - derive/\+/jw/
    - derive/#/jy/   # L290：误写为 jy，应为 j;（参照 double_pinyin_sogou.schema.yaml:371 与 mspy L264 / ziguang L342）
```

## 修改建议
1. 将 `melt_eng.schema.yaml:290` 的 `- derive/#/jy/` 修正为 `- derive/#/j;/`。
2. 将 `algebra_common` 拆分为 `algebra_common_pre`（英文数字与符号派生，`L77-110`）和 `algebra_common_post`（去特殊字符、`erase/^[^a-zA-Z0-9].+$/`、大小写派生与 `erase/^[a-z]$/`，`L111-138`），各方案按 `pre → 中文数字/符号谐音 → post` 顺序拼接，并保留 `algebra_common` 兼容外部直接引用：

```yaml
algebra_common:
  __include: algebra_common_pre
  __append:
    __include: algebra_common_post

_pre_rime_ice:
  __include: algebra_common_pre
  __append:
    # 全拼数字与符号中文谐音
    - derive/(?<!\d)1([1-9])(?!\d)/shi$1/
    ...
    - derive/#/jing/

algebra_rime_ice:
  __include: _pre_rime_ice
  __append:
    __include: algebra_common_post
```

> 边界说明：实测在下游配置将 `erase` 与大小写派生后置后，`melt_eng.prism.bin` 仅增加约 `0.15 MB`（对 2 万余条纯英文无影响，仅作用于约 160 条含符号/数字词条）；若下游或用户未修改 `en_ext` 中 `.NET` 的写法（当前为 `net 1` + `dotnet`，无前导 `.NET`），也不会影响 `net` 与 `.NET` 的原有排序。
