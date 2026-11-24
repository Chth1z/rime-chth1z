-- 日期时间翻译器，可在方案中配置触发关键字。
-- 配置存放在 env（避免多方案并存时互相覆盖）；ISO 8601 优先使用 C99/UCRT `%z` 输出本地时区偏移。

local WEEK_TAB = { '日', '一', '二', '三', '四', '五', '六' }

local function yield_cand(seg, text)
    local cand = Candidate('', seg.start, seg._end, text, '')
    cand.quality = 100
    yield(cand)
end

local function format_iso_tz(current_time)
    -- Native C99/UCRT `%z` (`+0800`, `-0700`) is immune to mktime DST spring-forward gaps and boundary shifts
    local z = os.date('%z', current_time)
    if type(z) == 'string' then
        local sign, hh, mm = z:match('^([+-])(%d%d)(%d%d)$')
        if sign and hh and mm then
            if hh == '00' and mm == '00' then
                return 'Z'
            end
            return string.format('%s%s:%s', sign, hh, mm)
        end
    end

    -- Fallback for non-C99 runtimes
    local utc_tbl = os.date('!*t', current_time)
    local local_tbl = os.date('*t', current_time)
    utc_tbl.isdst = false
    local t_local = os.time(local_tbl)
    local t_utc = os.time(utc_tbl)
    if not t_local or not t_utc then
        return 'Z'
    end
    local diff = math.floor(os.difftime(t_local, t_utc) + 0.5) + (local_tbl.isdst and 3600 or 0)
    if diff == 0 then
        return 'Z'
    end
    local sign = diff >= 0 and '+' or '-'
    local abs_diff = math.abs(diff)
    local hours = math.floor(abs_diff / 3600)
    local mins = math.floor((abs_diff % 3600) / 60)
    return string.format('%s%02d:%02d', sign, hours, mins)
end

local M = {}

function M.init(env)
    local config = env.engine.schema.config
    local ns = env.name_space:gsub('^*', '')
    env.date = config:get_string(ns .. '/date') or 'rq'
    env.time = config:get_string(ns .. '/time') or 'sj'
    env.week = config:get_string(ns .. '/week') or 'xq'
    env.datetime = config:get_string(ns .. '/datetime') or 'dt'
    env.timestamp = config:get_string(ns .. '/timestamp') or 'ts'
end

function M.func(input, seg, env)
    if input == env.date then
        local current_time = os.time()
        yield_cand(seg, os.date('%Y-%m-%d', current_time))
        yield_cand(seg, os.date('%Y/%m/%d', current_time))
        yield_cand(seg, os.date('%Y.%m.%d', current_time))
        yield_cand(seg, os.date('%Y%m%d', current_time))
        yield_cand(seg, os.date('%Y年%m月%d日', current_time):gsub('年0', '年'):gsub('月0', '月'))

    elseif input == env.time then
        local current_time = os.time()
        yield_cand(seg, os.date('%H:%M', current_time))
        yield_cand(seg, os.date('%H:%M:%S', current_time))

    elseif input == env.week then
        local current_time = os.time()
        local text = WEEK_TAB[tonumber(os.date('%w', current_time)) + 1]
        yield_cand(seg, '星期' .. text)
        yield_cand(seg, '礼拜' .. text)
        yield_cand(seg, '周' .. text)

    elseif input == env.datetime then
        local current_time = os.time()
        yield_cand(seg, os.date('%Y-%m-%dT%H:%M:%S', current_time) .. format_iso_tz(current_time))
        yield_cand(seg, os.date('%Y-%m-%d %H:%M:%S', current_time))
        yield_cand(seg, os.date('%Y%m%d%H%M%S', current_time))

    elseif input == env.timestamp then
        local current_time = os.time()
        yield_cand(seg, string.format('%d', current_time))
    end
end

return M
