-- Taiwan Traditional dual-candidate filter (s2twp + s2tw):
-- When traditionalization is enabled:
--   1st candidate: full Taiwan usage (s2twp.json), e.g. 程序优化 -> 程式最佳化
--   2nd candidate (only when s2twp differs from s2tw): Taiwan Traditional glyphs keeping
--     original wording (s2tw.json), e.g. 程序优化 -> 程序優化
-- When traditionalization is disabled: passthrough untouched (Simplified Chinese).

local M = {}

local converter_cache = {}

local function get_converter(cfg_name)
    local conv = converter_cache[cfg_name]
    if conv == nil then
        conv = Opencc(cfg_name) or false
        converter_cache[cfg_name] = conv
    end
    return conv
end

function M.init(env)
    local config = env.engine.schema.config
    local ns = env.name_space:gsub("^*", "")

    env.option_name = config:get_string(ns .. "/option_name") or "traditionalization"
    local twp_cfg = config:get_string(ns .. "/twp_config") or "s2twp.json"
    local tw_cfg = config:get_string(ns .. "/tw_config") or "s2tw.json"
    env.conv_twp = get_converter(twp_cfg)
    env.conv_tw = get_converter(tw_cfg)

    local tags = {}
    local tag_list = config:get_list(ns .. "/tags")
    if tag_list and tag_list.size > 0 then
        for i = 0, tag_list.size - 1 do
            tags[#tags + 1] = tag_list:get_value_at(i).value
        end
    else
        tags = { "abc", "number", "gregorian_to_lunar" }
    end
    env.tags = tags
end

function M.func(input, env)
    local context = env.engine.context
    local conv_twp = env.conv_twp
    local conv_tw = env.conv_tw

    if not conv_twp or not context:get_option(env.option_name) then
        for cand in input:iter() do
            yield(cand)
        end
        return
    end

    local comp = context.composition
    local seg = (comp and not comp:empty()) and comp:back() or nil
    if seg then
        local allowed = false
        local tags = env.tags
        for i = 1, #tags do
            if seg:has_tag(tags[i]) then
                allowed = true
                break
            end
        end
        if not allowed then
            for cand in input:iter() do
                yield(cand)
            end
            return
        end
    end

    for cand in input:iter() do
        local src = cand.text
        -- Fast-skip pure ASCII candidates (English, numbers, dates, timestamps)
        if not src:find("[\128-\255]") then
            yield(cand)
        else
            local twp = conv_twp:convert(src)
            local tw = conv_tw and conv_tw:convert(src) or twp

            if twp == tw then
                if twp == src then
                    yield(cand)
                else
                    yield(cand:to_shadow_candidate(cand.type, twp, cand.comment))
                end
            else
                if twp == src then
                    yield(cand)
                else
                    yield(cand:to_shadow_candidate(cand.type, twp, cand.comment))
                end
                if tw == src then
                    yield(cand)
                else
                    yield(cand:to_shadow_candidate(cand.type, tw, cand.comment))
                end
            end
        end
    end
end

return M
