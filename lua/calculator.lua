-- Pure-Lua recursive-descent calculator translator for rime-chth1z.
-- Evaluates arithmetic expressions directly without `load()` / VM code execution,
-- preventing sandbox escapes, OOM, and ReDoS while supporting full scientific functions,
-- postfix factorials (`(2+3)!`, `3!!`), overflow-safe hyperbolic/statistical ops, and clean formatting.

local M = {}

local MAX_EXPR_LEN = 160
local MAX_TOKENS = 128
local MAX_DEPTH = 48
local LN2 = math.log(2)

local function is_finite(x)
    return type(x) == "number" and x == x and x ~= math.huge and x ~= -math.huge
end

local CONSTANTS = {
    e = math.exp(1),
    pi = math.pi,
}

local function fn_sinh(x)
    if not is_finite(x) then return nil end
    local ax = math.abs(x)
    if ax < 1e-5 then
        local x2 = x * x
        return x * (1.0 + x2 / 6.0 + x2 * x2 / 120.0)
    end
    if ax > 709.78 then
        -- Avoid premature overflow in exp(x) for 709.78 < |x| <= 710.47
        local half = math.exp(ax - LN2)
        return x < 0 and -half or half
    end
    return (math.exp(x) - math.exp(-x)) * 0.5
end

local function fn_cosh(x)
    if not is_finite(x) then return nil end
    local ax = math.abs(x)
    if ax > 709.78 then
        return math.exp(ax - LN2)
    end
    return (math.exp(x) + math.exp(-x)) * 0.5
end

local function fn_tanh(x)
    if not is_finite(x) then return nil end
    if x > 20 then return 1.0 end
    if x < -20 then return -1.0 end
    local e2x = math.exp(2 * x)
    return (e2x - 1) / (e2x + 1)
end

local function fn_atan2(y, x)
    if not is_finite(y) or not is_finite(x) then return nil end
    if math.atan2 then return math.atan2(y, x) end
    return math.atan(y, x)
end

local function fn_ldexp(x, y)
    if not is_finite(x) or not is_finite(y) or y ~= math.floor(y) then return nil end
    if math.ldexp then return math.ldexp(x, y) end
    -- Scale in two halves to avoid overflow/underflow of 2^y at exponent limits
    if y >= 1024 then
        local half = math.floor(y / 2)
        return (x * (2.0 ^ half)) * (2.0 ^ (y - half))
    elseif y <= -1022 then
        local half = math.floor(y / 2)
        return (x * (2.0 ^ half)) * (2.0 ^ (y - half))
    end
    return x * (2.0 ^ y)
end

local function fn_log(base, x)
    if not is_finite(base) or not is_finite(x) or base <= 0 or base == 1 or x <= 0 then
        return nil
    end
    return math.log(x) / math.log(base)
end

local function fn_loge(x)
    if not is_finite(x) or x <= 0 then return nil end
    return math.log(x)
end

local function fn_log10(x)
    if not is_finite(x) or x <= 0 then return nil end
    return math.log(x) / math.log(10)
end

local function fn_avg(args)
    local n = #args
    if n == 0 then return nil end
    -- Welford running mean avoids overflow on large operands (e.g. avg(1e308, 1e308))
    local mean = 0.0
    for i = 1, n do
        local v = args[i]
        if not is_finite(v) then return nil end
        mean = mean + (v - mean) / i
    end
    return mean
end

local function fn_var(args)
    local n = #args
    if n == 0 then return nil end
    -- Welford one-pass numerically stable population variance
    local mean = 0.0
    local m2 = 0.0
    for i = 1, n do
        local v = args[i]
        if not is_finite(v) then return nil end
        local delta = v - mean
        mean = mean + delta / i
        m2 = m2 + delta * (v - mean)
    end
    return m2 / n
end

local function fn_fact(x)
    if not is_finite(x) or x < 0 or x > 170 or x ~= math.floor(x) then
        return nil
    end
    local n = math.floor(x)
    if n <= 1 then return 1.0 end
    local res = 1.0
    for i = 2, n do
        res = res * i
    end
    return res
end

local function fn_comb(n, k)
    if not is_finite(n) or not is_finite(k) or n < 0 or k < 0 or k > n
        or n ~= math.floor(n) or k ~= math.floor(k) or n > 1000
    then
        return nil
    end
    k = math.min(k, n - k)
    local res = 1.0
    for i = 1, k do
        res = res * (n - k + i) / i
    end
    return res
end

local function fn_perm(n, k)
    if not is_finite(n) or not is_finite(k) or n < 0 or k < 0 or k > n
        or n ~= math.floor(n) or k ~= math.floor(k) or n > 1000
    then
        return nil
    end
    local res = 1.0
    for i = 0, k - 1 do
        res = res * (n - i)
    end
    return res
end

local function unary_fn(f)
    return function(args)
        if #args ~= 1 or not is_finite(args[1]) then return nil end
        return f(args[1])
    end
end

local function binary_fn(f)
    return function(args)
        if #args ~= 2 or not is_finite(args[1]) or not is_finite(args[2]) then return nil end
        return f(args[1], args[2])
    end
end

local FUNCTIONS = {
    rdm = function(args)
        if #args == 0 then
            return math.random()
        elseif #args == 1 then
            local m = args[1]
            if not is_finite(m) or m < 1 or m ~= math.floor(m) then return nil end
            return math.random(math.floor(m))
        elseif #args == 2 then
            local m, n = args[1], args[2]
            if not is_finite(m) or not is_finite(n) or m ~= math.floor(m) or n ~= math.floor(n) or m > n then
                return nil
            end
            return math.random(math.floor(m), math.floor(n))
        end
        return nil
    end,
    sin = unary_fn(math.sin),
    sinh = unary_fn(fn_sinh),
    asin = unary_fn(math.asin),
    cos = unary_fn(math.cos),
    cosh = unary_fn(fn_cosh),
    acos = unary_fn(math.acos),
    tan = unary_fn(math.tan),
    tanh = unary_fn(fn_tanh),
    atan = unary_fn(math.atan),
    atan2 = binary_fn(fn_atan2),
    deg = unary_fn(math.deg),
    rad = unary_fn(math.rad),
    ldexp = binary_fn(fn_ldexp),
    exp = unary_fn(math.exp),
    sqrt = unary_fn(function(x) return x >= 0 and math.sqrt(x) or nil end),
    cbrt = unary_fn(function(x) return x < 0 and -((-x) ^ (1 / 3)) or (x ^ (1 / 3)) end),
    abs = unary_fn(math.abs),
    floor = unary_fn(math.floor),
    ceil = unary_fn(math.ceil),
    round = unary_fn(function(x) return x >= 0 and math.floor(x + 0.5) or math.ceil(x - 0.5) end),
    log = binary_fn(fn_log),
    loge = unary_fn(fn_loge),
    log10 = unary_fn(fn_log10),
    pow = binary_fn(function(a, b) return a ^ b end),
    fact = unary_fn(fn_fact),
    comb = binary_fn(fn_comb),
    perm = binary_fn(fn_perm),
    avg = fn_avg,
    var = fn_var,
    min = function(args)
        if #args == 0 then return nil end
        local best = args[1]
        for i = 2, #args do
            if args[i] < best then best = args[i] end
        end
        return best
    end,
    max = function(args)
        if #args == 0 then return nil end
        local best = args[1]
        for i = 2, #args do
            if args[i] > best then best = args[i] end
        end
        return best
    end,
}

local function tokenize(expr)
    if #expr > MAX_EXPR_LEN then
        return nil
    end
    local tokens = {}
    local i = 1
    local n = #expr

    while i <= n do
        local b = expr:byte(i)
        if b == 32 or b == 9 or b == 10 or b == 13 then
            i = i + 1
        elseif (b >= 48 and b <= 57) or (b == 46 and i < n and expr:byte(i + 1) >= 48 and expr:byte(i + 1) <= 57) then
            -- Parse decimal/scientific number (`123`, `3.14`, `.5`, `1e-5`, `2.5E+3`)
            local start_i = i
            local saw_dot = false
            while i <= n do
                local c = expr:byte(i)
                if c >= 48 and c <= 57 then
                    i = i + 1
                elseif c == 46 and not saw_dot then
                    saw_dot = true
                    i = i + 1
                else
                    break
                end
            end
            if i <= n and (expr:byte(i) == 101 or expr:byte(i) == 69) then
                local exp_i = i + 1
                if exp_i <= n and (expr:byte(exp_i) == 43 or expr:byte(exp_i) == 45) then
                    exp_i = exp_i + 1
                end
                if exp_i <= n and expr:byte(exp_i) >= 48 and expr:byte(exp_i) <= 57 then
                    i = exp_i
                    while i <= n and expr:byte(i) >= 48 and expr:byte(i) <= 57 do
                        i = i + 1
                    end
                else
                    return nil
                end
            end
            -- Reject trailing `.` or immediate identifier/digit splice (e.g. `2.5.1` or `12abc`)
            if i <= n then
                local nb = expr:byte(i)
                if nb == 46 or (nb >= 65 and nb <= 90) or (nb >= 97 and nb <= 122) or nb == 95 then
                    return nil
                end
            end
            local num = tonumber(expr:sub(start_i, i - 1))
            if not is_finite(num) then
                return nil
            end
            tokens[#tokens + 1] = { kind = "num", val = num + 0.0 }
        elseif (b >= 65 and b <= 90) or (b >= 97 and b <= 122) or b == 95 then
            local start_i = i
            i = i + 1
            while i <= n do
                local c = expr:byte(i)
                if (c >= 65 and c <= 90) or (c >= 97 and c <= 122) or (c >= 48 and c <= 57) or c == 95 then
                    i = i + 1
                else
                    break
                end
            end
            local ident = expr:sub(start_i, i - 1)
            if not CONSTANTS[ident] and not FUNCTIONS[ident] then
                return nil
            end
            tokens[#tokens + 1] = { kind = "ident", val = ident }
        else
            local ch = expr:sub(i, i)
            if ch == "+" or ch == "-" or ch == "*" or ch == "/" or ch == "%"
                or ch == "^" or ch == "(" or ch == ")" or ch == "," or ch == "!"
            then
                tokens[#tokens + 1] = { kind = ch, val = ch }
                i = i + 1
            else
                return nil
            end
        end

        if #tokens > MAX_TOKENS then
            return nil
        end
    end

    return tokens
end

local function eval_expression(expr)
    local tokens = tokenize(expr)
    if not tokens or #tokens == 0 then
        return nil
    end

    local pos = 1
    local depth = 0
    local ntok = #tokens

    local parse_expr, parse_unary, parse_power, parse_postfix, parse_primary

    local function enter()
        depth = depth + 1
        return depth <= MAX_DEPTH
    end

    local function leave()
        depth = depth - 1
    end

    parse_primary = function()
        if not enter() then return nil end
        local tok = tokens[pos]
        if not tok then
            leave()
            return nil
        end
        if tok.kind == "num" then
            pos = pos + 1
            leave()
            return tok.val
        elseif tok.kind == "ident" then
            local name = tok.val
            pos = pos + 1
            if tokens[pos] and tokens[pos].kind == "(" then
                local fn = FUNCTIONS[name]
                if not fn then
                    leave()
                    return nil
                end
                pos = pos + 1 -- consume '('
                local args = {}
                if not (tokens[pos] and tokens[pos].kind == ")") then
                    while true do
                        local arg = parse_expr()
                        if arg == nil then
                            leave()
                            return nil
                        end
                        args[#args + 1] = arg
                        if tokens[pos] and tokens[pos].kind == "," then
                            pos = pos + 1
                        else
                            break
                        end
                    end
                end
                if not (tokens[pos] and tokens[pos].kind == ")") then
                    leave()
                    return nil
                end
                pos = pos + 1 -- consume ')'
                local res = fn(args)
                leave()
                if not is_finite(res) then return nil end
                return res + 0.0
            else
                local cval = CONSTANTS[name]
                leave()
                return cval
            end
        elseif tok.kind == "(" then
            pos = pos + 1
            local val = parse_expr()
            if val == nil or not (tokens[pos] and tokens[pos].kind == ")") then
                leave()
                return nil
            end
            pos = pos + 1
            leave()
            return val
        end
        leave()
        return nil
    end

    parse_postfix = function()
        local val = parse_primary()
        if val == nil then return nil end
        while tokens[pos] and tokens[pos].kind == "!" do
            pos = pos + 1
            val = fn_fact(val)
            if not is_finite(val) then return nil end
        end
        return val
    end

    parse_power = function()
        if not enter() then return nil end
        local base = parse_postfix()
        if base == nil then
            leave()
            return nil
        end
        if tokens[pos] and tokens[pos].kind == "^" then
            pos = pos + 1
            local exp = parse_unary()
            if exp == nil then
                leave()
                return nil
            end
            local res = base ^ exp
            leave()
            if not is_finite(res) then return nil end
            return res
        end
        leave()
        return base
    end

    parse_unary = function()
        if not enter() then return nil end
        local tok = tokens[pos]
        if tok and tok.kind == "+" then
            pos = pos + 1
            local v = parse_unary()
            leave()
            return v
        elseif tok and tok.kind == "-" then
            pos = pos + 1
            local v = parse_unary()
            leave()
            if v == nil then return nil end
            return -v
        end
        local v = parse_power()
        leave()
        return v
    end

    local function parse_mul()
        local lhs = parse_unary()
        if lhs == nil then return nil end
        while tokens[pos] do
            local k = tokens[pos].kind
            if k ~= "*" and k ~= "/" and k ~= "%" then
                break
            end
            pos = pos + 1
            local rhs = parse_unary()
            if rhs == nil then return nil end
            if k == "*" then
                lhs = lhs * rhs
            elseif k == "/" then
                if rhs == 0 then return nil end
                lhs = lhs / rhs
            else
                if rhs == 0 then return nil end
                lhs = lhs % rhs
            end
            if not is_finite(lhs) then return nil end
        end
        return lhs
    end

    parse_expr = function()
        if not enter() then return nil end
        local lhs = parse_mul()
        if lhs == nil then
            leave()
            return nil
        end
        while tokens[pos] do
            local k = tokens[pos].kind
            if k ~= "+" and k ~= "-" then
                break
            end
            pos = pos + 1
            local rhs = parse_mul()
            if rhs == nil then
                leave()
                return nil
            end
            lhs = (k == "+") and (lhs + rhs) or (lhs - rhs)
            if not is_finite(lhs) then
                leave()
                return nil
            end
        end
        leave()
        return lhs
    end

    local val = parse_expr()
    if val == nil or pos ~= ntok + 1 or not is_finite(val) then
        return nil
    end
    return val
end

local function format_result(val)
    -- Eliminate negative zero (`-0.0`)
    if val == 0 then
        return "0"
    end
    -- Render exact IEEE-754 integers cleanly without trailing `.0`
    if math.abs(val) <= 9007199254740992 and val == math.floor(val) then
        return string.format("%.0f", val)
    end
    return string.format("%.14g", val)
end

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

function M.func(input, seg, env)
    if not seg:has_tag('calculator') then return end
    local prefix = nil
    for _, candidatePrefix in ipairs(env.prefixes) do
        if startsWith(input, candidatePrefix) then
            prefix = candidatePrefix
            break
        end
    end
    if not prefix then return end

    local express = string.sub(input, #prefix + 1)
    if #express < 2 then return end

    local result = eval_expression(express)
    if result ~= nil then
        local out = format_result(result)
        yield(Candidate("calculator", seg.start, seg._end, out, ""))
        yield(Candidate("calculator", seg.start, seg._end, express .. "=" .. out, ""))
    else
        yield(Candidate("calculator", seg.start, seg._end, express, "解析失败"))
    end
end

return M
