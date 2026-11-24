-- author: https://github.com/ChaosAlphard
-- 说明 https://github.com/gaboolic/rime-shuangpin-fuzhuma/pull/41
local M = {}

function M.init(env)
  local config = env.engine.schema.config
  local namespace = env.name_space:gsub('^%*', '')
  local prefix = config:get_string(namespace .. '/trigger') or 'V'
  env.prefixes = { prefix }
  local lowerPrefix = prefix:lower()
  if lowerPrefix ~= prefix then
    table.insert(env.prefixes, lowerPrefix)
  end
end

local function startsWith(str, start)
  return string.sub(str, 1, string.len(start)) == start
end

local function truncateFromStart(str, truncateStr)
  return string.sub(str, string.len(truncateStr) + 1)
end

-- 函数表
local calcPlugin = {
  -- e, exp(1) = e^1 = e
  e = math.exp(1),
  -- π
  pi = math.pi
}

-- random([m [,n ]]) 返回m-n之间的随机数, n为空则返回1-m之间, 都为空则返回0-1之间的小数
local function random(...)
  return math.random(...)
end
-- 注册到函数表中
calcPlugin["rdm"] = random

-- 正弦
local function sin(x)
  return math.sin(x)
end
calcPlugin["sin"] = sin

-- 双曲正弦（兼容 LuaJIT / Lua 5.4 / 5.5）
local function sinh(x)
  return (math.exp(x) - math.exp(-x)) * 0.5
end
calcPlugin["sinh"] = sinh

-- 反正弦
local function asin(x)
  return math.asin(x)
end
calcPlugin["asin"] = asin

-- 余弦
local function cos(x)
  return math.cos(x)
end
calcPlugin["cos"] = cos

-- 双曲余弦（兼容 LuaJIT / Lua 5.4 / 5.5）
local function cosh(x)
  return (math.exp(x) + math.exp(-x)) * 0.5
end
calcPlugin["cosh"] = cosh

-- 反余弦
local function acos(x)
  return math.acos(x)
end
calcPlugin["acos"] = acos

-- 正切
local function tan(x)
  return math.tan(x)
end
calcPlugin["tan"] = tan

-- 双曲正切（兼容 LuaJIT / Lua 5.4 / 5.5，避免大参数下 exp 溢出产生 NaN）
local function tanh(x)
  if x > 20 then return 1.0 end
  if x < -20 then return -1.0 end
  local e2x = math.exp(2 * x)
  return (e2x - 1) / (e2x + 1)
end
calcPlugin["tanh"] = tanh

-- 反正切
local function atan(x)
  return math.atan(x)
end
calcPlugin["atan"] = atan

-- 返回以弧度为单位的点(x,y)相对于x轴的逆时针角度。y是点的纵坐标，x是点的横坐标
-- 返回范围从−π到π （以弧度为单位），其中负角度表示向下旋转，正角度表示向上旋转
-- 它与传统的 math.atan(y/x) 函数相比，具有更好的数学定义，因为它能够正确处理边界情况（例如x=0）
local function atan2(y, x)
  if math.atan2 then return math.atan2(y, x) end
  return math.atan(y, x)
end
calcPlugin["atan2"] = atan2

-- 将角度从弧度转换为度 e.g. deg(π) = 180
local function deg(x)
  return math.deg(x)
end
calcPlugin["deg"] = deg

-- 将角度从度转换为弧度 e.g. rad(180) = π
local function rad(x)
  return math.rad(x)
end
calcPlugin["rad"] = rad

-- 返回两个值, 无法参与运算后续
-- 返回m,e 使得x = m*2^e
-- local function frexp(x)
--   return math.frexp(x)
-- end
-- calcPlugin["frexp"] = frexp

-- 返回 x*2^y（兼容 LuaJIT / Lua 5.4 / 5.5）
local function ldexp(x, y)
  if math.ldexp then return math.ldexp(x, y) end
  return x * (2.0 ^ y)
end
calcPlugin["ldexp"] = ldexp

-- 返回 e^x
local function exp(x)
  return math.exp(x)
end
calcPlugin["exp"] = exp

-- 返回x的平方根 e.g. sqrt(x) = x^0.5
local function sqrt(x)
  return math.sqrt(x)
end
calcPlugin["sqrt"] = sqrt

-- x为底的对数, log(10, 100) = log(100) / log(10) = 2
local function log(x, y)
  -- 底数不能 <= 0 或等于 1，真数不能 <= 0
  if type(x) ~= "number" or type(y) ~= "number" or x <= 0 or x == 1 or y <= 0 then return nil end

  return math.log(y) / math.log(x)
end
calcPlugin["log"] = log

-- 自然数e为底的对数
local function loge(x)
  -- 不能为负数或0
  if type(x) ~= "number" or x <= 0 then return nil end

  return math.log(x)
end
calcPlugin["loge"] = loge

-- 10为底的对数（兼容 LuaJIT / Lua 5.4 / 5.5）
local function log10(x)
  -- 不能为负数或0
  if type(x) ~= "number" or x <= 0 then return nil end

  return math.log(x) / math.log(10)
end
calcPlugin["log10"] = log10

-- 平均值（任一参数非有效有限数字时返回 nil，避免 ipairs 在 nil 处截断产生错值）
local function avg(...)
  local data = {...}
  local n = select("#", ...)
  if n == 0 then return nil end

  local sum = 0
  for i = 1, n do
    local value = data[i]
    if type(value) ~= "number" or value ~= value or value == math.huge or value == -math.huge then
      return nil
    end
    sum = sum + value
  end

  return sum / n
end
calcPlugin["avg"] = avg

-- 方差（任一参数非有效有限数字时返回 nil）
local function variance(...)
  local data = {...}
  local n = select("#", ...)
  if n == 0 then return nil end

  local sum = 0
  for i = 1, n do
    local value = data[i]
    if type(value) ~= "number" or value ~= value or value == math.huge or value == -math.huge then
      return nil
    end
    sum = sum + value
  end
  local mean = sum / n

  local sum_squared_diff = 0
  for i = 1, n do
    sum_squared_diff = sum_squared_diff + (data[i] - mean)^2
  end

  return sum_squared_diff / n
end
calcPlugin["var"] = variance

-- 阶乘（限制 n <= 170 且为非负整数；n <= 20 保持 64 位精确整数，21..170 自动切换 IEEE 754 浮点）
local function factorial(x)
  if type(x) ~= "number" or x < 0 or x > 170 or x ~= math.floor(x) then return nil end
  if x == 0 or x == 1 then return 1 end

  local result = x <= 20 and 1 or 1.0
  for i = 2, x do
    result = result * i
  end

  return result
end
calcPlugin["fact"] = factorial

-- 实现阶乘计算(!)
local function replaceToFactorial(str)
  -- 替换[0-9]!字符为fact([0-9])以实现阶乘
  return str:gsub("([0-9]+)!", "fact(%1)")
end

-- 只读沙箱代理，阻止表达式写入污染 calcPlugin 全局函数或常量（如 pi/e）
local calcEnv = setmetatable({}, {
  __index = calcPlugin,
  __newindex = function() error("read-only calculator environment") end,
  __metatable = false,
})

local FORBIDDEN_KEYWORDS = {
  ["function"] = true, ["while"] = true, ["for"] = true, ["repeat"] = true,
  ["until"] = true, ["do"] = true, ["end"] = true, ["goto"] = true,
  ["local"] = true, ["return"] = true, ["if"] = true, ["then"] = true,
  ["else"] = true, ["elseif"] = true, ["break"] = true, ["in"] = true,
}

local function isSafeExpression(expr)
  if #expr > 160 then return false end
  -- 仅允许字母数字、空白与算术/括号/逗号/小数点/阶乘符号（禁止引号、冒号、方括号、花括号、分号、等号）
  if not expr:match("^[%w%s%+%-%*/%%%^%(%)%.,!]+$") then
    return false
  end
  for ident in expr:gmatch("[%a_][%w_]*") do
    if FORBIDDEN_KEYWORDS[ident] then
      return false
    end
  end
  return true
end

-- 简单计算器
function M.func(input, seg, env)
  -- 以方案的识别规则为准，避免把双拼的 v 声母当成计算器前缀。
  if not seg:has_tag('calculator') then return end
  local prefix = nil
  for _, candidatePrefix in ipairs(env.prefixes) do
    if startsWith(input, candidatePrefix) then
      prefix = candidatePrefix
      break
    end
  end
  if not prefix then return end
  -- 提取算式
  local express = truncateFromStart(input, prefix)
  -- 算式长度 < 2 直接终止(没有计算意义)
  if (string.len(express) < 2) then return end
  local code = replaceToFactorial(express)

  local success, result = false, nil
  if isSafeExpression(express) then
    local fn = load("return " .. code, "calculate", "t", calcEnv)
    if fn then
      success, result = pcall(fn)
    end
  end
  if success and type(result) == "number" and result == result and result ~= math.huge and result ~= -math.huge then
    result = tostring(result)
    yield(Candidate("calculator", seg.start, seg._end, result, ""))
    yield(Candidate("calculator", seg.start, seg._end, express .. "=" .. result, ""))
  else
    yield(Candidate("calculator", seg.start, seg._end, express, "解析失败"))
    yield(Candidate("calculator", seg.start, seg._end, code, "入参"))
    -- TODO: 错误信息记录到日志中
    -- print("express: " .. express)
    -- print("code: " .. code)
    -- print("result: " .. result)
  end
end

return M
