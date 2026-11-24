# [Bug] `lua/select_character.lua` 吞 IPv6 `[` 与模式字符报错，及 `lua/number_translator.lua` 漏判 tag 误劫持邮箱

## 环境与版本
- **上游版本**：`iDvel/rime-ice@927e1cf`（已确认最新 `main` 仍可复现；两处问题均同步影响下游 `gaboolic/rime-frost@c982966`）
- **客户端与引擎**：Weasel `0.17.4` / `librime 1.17.0` / `Lua 5.4.8`
- **影响范围**：默认启用 `lua_processor@*select_character`（`default.yaml:208` 绑定 `[` / `]`）与 `lua_translator@*number_translator` 的全部方案

## 实际影响
- **属于哪类问题**：误拦截正常输入、触发 Lua 运行时报错、违背 `recognizer/patterns/number` 正则约束
- **实际影响说明**：
  1. `lua/select_character.lua` 未要求 `context:has_menu()`（仅判断 `is_composing() or has_menu()`），且 `commit_text:find(selected_candidate)` 未关闭正则模式、未判 `nil`：用户在中文态输入 IPv6 地址（如 `http://[::1]`）按 `[` 时，整段 `http://` 会被吃掉并上屏单字母 `h`；若 URL 中包含 `-`（Lua 模式元字符），按 `[` 直接抛出 Lua 运行时错误。
  2. `lua/number_translator.lua` 未校验 `seg:has_tag("number")`，仅看首字母是否为 `R`：输入以 `R` 开头且带数字的邮箱或域名（如 `R123@a.com`、`R100.com`）时，虽然并未命中 `recognizer/patterns/number`，仍会被强行翻译成中文大写金额；此外若用户在 `*.custom.yaml` 置空 `recognizer/patterns/number`，`:sub(2, 2)` 会对 `nil` 取索引报错。

## 复现步骤
1. 使用干净的 `iDvel/rime-ice@927e1cf` 默认配置（未叠加个人 `*.custom.yaml`）部署，切至 `rime_ice`。
2. **`select_character.lua` 吞 `[` 与报错**：
   - 输入 `http://[`（URL 识别态、无候选菜单）：
     - **实际结果**：预编辑清空，直接上屏单字母 `h`（`pre='' commit='h'`）。
     - **预期结果**：无候选菜单时放行 `[`，保留 `http://[` 以继续输入 IPv6 地址。
   - 输入 `http://my-site.com[`：
     - **实际结果**：Weasel `ERROR` 日志抛出 Lua 运行时报错：
       `LuaProcessor::ProcessKeyEvent of *select_character error(2): ...\lua\select_character.lua:45: attempt to perform arithmetic on a nil value (local 'end_pos')`
     - **预期结果**：无候选菜单时放行 `[`，不产生 Lua 错误。
3. **`number_translator.lua` 误劫持邮箱 / 域名**：
   - 输入 `R123@a.com`（命中 `recognizer/patterns/email`，未命中 `number`）：
     - **实际结果**：候选被劫持为 `['一百二十三[〔数字小写〕]', '壹佰贰拾叁[〔数字大写〕]', '一百二十三元整[〔金额小写〕]', '壹佰贰拾叁元整[〔金额大写〕]']`。
   - 输入 `R100.com`：
     - **实际结果**：预编辑变为 `一百点co m`。
   - **预期结果**：仅在 `seg:has_tag("number")` 时触发大写数字转换，邮箱与域名原样保留。

## 原因位置
- `lua/select_character.lua:24, 41-45`：
  - `L24`：`context:is_composing()` 在 URL 识别态（无候选菜单）也为 `true`，导致 `selected_candidate` 回退到原始 `input`；
  - `L41`：`commit_text:find(selected_candidate)` 缺少第 4 参数 `true`（纯文本匹配），`-`、`.`、`+`、`%` 等被按 Lua 模式解析，`find` 返回 `nil` 后 `L45` 算术运算报错；
  - `L44`：`gsub(selected_candidate, selected_char)` 同样存在模式元字符风险。
- `lua/number_translator.lua:147-151`：
  - 未判断 `seg:has_tag("number")`；
  - `env.engine.schema.config:get_string('recognizer/patterns/number'):sub(2, 2)` 未对 `get_string` 返回 `nil` 做兜底。

```lua
-- lua/select_character.lua:22-45
if
    not key:release()
    and (context:is_composing() or context:has_menu())
    and (env.first_key or env.last_key)
then
    ...
    local _, end_pos = commit_text:find(selected_candidate)
    local part1 = commit_text:sub(1, end_pos):gsub(selected_candidate, selected_char)
    local part2 = commit_text:sub(end_pos + 1)

-- lua/number_translator.lua:146-151
local function number_translator(input, seg, env)
    env.number_keyword = env.number_keyword or
        env.engine.schema.config:get_string('recognizer/patterns/number'):sub(2, 2)
    if env.number_keyword ~= '' and input:sub(1, 1) == env.number_keyword then
```

## 修改建议
以下改法均兼容 Lua 5.1 / LuaJIT / Lua 5.4 / Lua 5.5：

1. **`lua/select_character.lua`**：要求存在活跃候选菜单（`context:has_menu()` 且有选中候选），并用纯文本匹配 + 下标切片替代 `gsub`：

```lua
if
    not key:release()
    and context:has_menu()
    and (env.first_key or env.last_key)
then
    local cand = context:get_selected_candidate()
    if not cand then return 2 end
    local selected_candidate = cand.text
    ...
    local start_pos, end_pos = commit_text:find(selected_candidate, 1, true)
    if not end_pos then return 2 end
    local part1 = commit_text:sub(1, start_pos - 1) .. selected_char
    local part2 = commit_text:sub(end_pos + 1)
```

2. **`lua/number_translator.lua`**：前置 `seg:has_tag("number")` 校验并为 `get_string` 增加空串兜底：

```lua
local function number_translator(input, seg, env)
    if not seg:has_tag("number") then return end
    if env.number_keyword == nil then
        local pat = env.engine.schema.config:get_string('recognizer/patterns/number') or ''
        env.number_keyword = pat:sub(2, 2)
    end
    if env.number_keyword ~= '' and input:sub(1, 1) == env.number_keyword then
        ...
```
