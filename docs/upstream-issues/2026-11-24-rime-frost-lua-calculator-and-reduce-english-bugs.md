# [Bug] `lua/calculator.lua` 阶乘溢出与函数指针泄漏，及 `reduce_english_filter.lua` 吞英文候选

## 环境与版本
- **上游版本**：`gaboolic/rime-frost@c982966`（已确认最新 `master` 仍可复现；`calculator.lua` 为白霜独有，`reduce_english_filter.lua` 雾凇已修但白霜未同步）
- **客户端与引擎**：Weasel `0.17.4` / `librime 1.17.0` / `Lua 5.4.8`
- **影响范围**：全拼与 6 套双拼方案（其中 `reduce_english_filter.lua` 问题在双拼方案下极易复现）

## 实际影响
- **属于哪类问题**：计算结果错误（整数溢出）/ 内部内存地址泄漏 / 正常英文候选被静默吞掉
- **实际影响说明**：
  1. `lua/calculator.lua` 在 Lua 5.4 下用整数累乘阶乘，`21!` 即触发 64 位有符号整数溢出为负数，`66!` 溢成 `0`；且未校验求值结果类型和无穷大/NaN，输入 `Vsin` / `Vcos` 直接将 Lua 函数对象内存地址 `function: 0000...` 作为候选输出，输入 `V1/0` / `V0/0` 输出 `inf` / `-nan(ind)`。
  2. `lua/reduce_english_filter.lua` 将 `pending_cands` 的输出循环错写在 `if index >= M.idx + #pending_cands - 1` 分支内：当输入编码命中 `words` 列表（如双拼下输入 `bench`、`benz`）且无足够中文候选时，循环结束即退出，**全部英文候选被静默吞掉，候选栏完全为空**（`iDvel/rime-ice` 已将该循环移至外部修复，白霜尚未同步）。
  3. 附带：`lua/select_character.lua:22` 同样存在 `is_composing() or has_menu()` 导致无候选菜单的 URL 态按 `[`（如 `http://[`）被吞并上屏单字母 `h` 的问题（母库 `rime-ice` 已另行反馈）。

## 复现步骤
1. 使用干净的 `gaboolic/rime-frost@c982966` 默认配置（未叠加个人 `*.custom.yaml`）部署。
2. **`lua/calculator.lua`（默认全拼 `rime_frost` 实测）**：
   - 输入 `V21!` → 候选为 `['-4249290049419214848', '21!=-4249290049419214848']`
   - 输入 `V66!` → 候选为 `['0', '66!=0']`
   - 输入 `Vsin` → 候选出现 `['...', 'function: 0000021D387DCE00', 'sin=function: 0000021D387DCE00']`（`Vcos` 同理）
   - 输入 `V1/0` → 候选为 `['inf', '1/0=inf']`；输入 `V0/0` → 候选为 `['-nan(ind)', '0/0=-nan(ind)']`
   - **预期结果**：`V21!` 输出 `5.1090942171709e+19`、`V66!` 输出 `5.4434493907744e+92`；`Vsin`、`V1/0`、`V0/0` 不输出函数指针地址或 `inf`/`nan`。
3. **`lua/reduce_english_filter.lua`（默认自然码双拼 `rime_frost_double_pinyin` 实测）**：
   - 输入 `bench` → **实际结果**：`pre='bench'`, **`cands=[]`**（候选栏完全空白，英文词 `bench` / `benchmark` 全部丢失）
   - 输入 `benz` → **实际结果**：`pre='benz'`, **`cands=[]`**（英文词 `benz` 丢失）
   - **预期结果**：无中文候选时，`bench`、`benz` 等英文候选正常输出。
4. **`lua/select_character.lua`（默认全拼 `rime_frost` 实测）**：
   - 输入 `http://[` → **实际结果**：`pre=''`, `commit='h'`（整段 `http://` 与 `[` 被吞）。

## 原因位置
- `lua/calculator.lua:207-217`：`local result = 1` 在 Lua 5.4 中为 64 位整数，乘至 `21!` 溢出回绕；
- `lua/calculator.lua:251-255`：`if success and result ~= nil then` 未检查 `type(result) == "number"` 及 `math.huge` / `NaN`；
- `lua/reduce_english_filter.lua:99-106`：`pending_cands` 输出循环位于 `if index >= M.idx + #pending_cands - 1` 内部；
- `lua/select_character.lua:22`：未要求 `context:has_menu()`。

```lua
-- lua/calculator.lua:212-217 & 251-255
local result = 1
for i = 1, x do
  result = result * i
end
...
local success, result = pcall(load("return " .. code, "calculate", "t", calcPlugin))
if success and result ~= nil then
  result = tostring(result)

-- lua/reduce_english_filter.lua:99-106
if index >= M.idx + #pending_cands - 1 then
    for _, cand in ipairs(pending_cands) do
        yield(cand)
    end
    break
end
```

## 修改建议
以下改法均兼容 Lua 5.1 / LuaJIT / Lua 5.4 / Lua 5.5：

1. **`lua/calculator.lua`**：
   - 阶乘增加非整数与上界校验（`x > 170` 避免浮点溢出与大数循环卡顿）并改用浮点累乘避免 Lua 5.4 int64 溢出：
     ```lua
     if x < 0 or x > 170 or math.floor(x) ~= x then return nil end
     if x == 0 or x == 1 then return 1 end
     local result = 1.0
     for i = 2, x do
       result = result * i
     end
     ```
   - 求值结果校验类型与有限性，整数值格式化去除 `.0`：
     ```lua
     if success and type(result) == "number" and result == result
        and result ~= math.huge and result ~= -math.huge then
       local out
       if math.floor(result) == result and math.abs(result) < 1e15 then
         out = string.format("%.0f", result)
       else
         out = tostring(result)
       end
       yield(Candidate(input, seg.start, seg._end, out, ""))
       yield(Candidate(input, seg.start, seg._end, express .. "=" .. out, ""))
     ```
2. **`lua/reduce_english_filter.lua`**：同步 `iDvel/rime-ice` 修复，将 `pending_cands` 输出移出 `for cand in input:iter()` 循环：
   ```lua
   if index >= M.idx + #pending_cands - 1 then
       break
   end
   end
   for _, cand in ipairs(pending_cands) do
       yield(cand)
   end
   ```
3. **`lua/select_character.lua`**：将 `L22` 的 `(context:is_composing() or context:has_menu())` 改为 `context:has_menu()`，并在无选中候选时直接返回 `2`。
