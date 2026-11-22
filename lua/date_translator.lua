-- 日期时间，可在方案中配置触发关键字。
-- 改进：配置存放在 env（避免多方案并存时模块表 M 互相覆盖）；ISO 8601 动态计算本地时区偏移。

local function yield_cand(seg, text)
    local cand = Candidate('', seg.start, seg._end, text, '')
    cand.quality = 100
    yield(cand)
end

local function format_iso_tz(current_time)
    local utc_tbl = os.date('!*t', current_time)
    local local_tbl = os.date('*t', current_time)
    utc_tbl.isdst = local_tbl.isdst
    local diff = math.floor(os.difftime(os.time(local_tbl), os.time(utc_tbl)) + 0.5)
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
        local week_tab = {'日', '一', '二', '三', '四', '五', '六'}
        local text = week_tab[tonumber(os.date('%w', current_time)) + 1]
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
