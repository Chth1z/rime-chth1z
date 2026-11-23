-- Taiwan Traditional dual-candidate filter (s2twp + s2tw):
-- When traditionalization is enabled:
--   * Multi-character candidates:
--       1st candidate: full Taiwan usage (s2twp.json), e.g. 程序优化 -> 程式最佳化
--       2nd candidate (only when s2twp differs from s2tw): Taiwan Traditional glyphs keeping
--         original wording (s2tw.json), e.g. 程序优化 -> 程序優化
--   * Single-character Hanzi candidates:
--       Expands all 1-to-many Traditional variants via convert_word() (e.g. 发 -> 發/髮,
--       面 -> 面/麵, 钟 -> 鐘/鍾, 只 -> 只/隻) with deduplication.
--   * Non-Hanzi candidates (ASCII, pure Emoji, symbols): passthrough untouched.
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

local function is_hanzi_cp(cp)
    return (cp >= 0x4E00 and cp <= 0x9FFF)
        or (cp >= 0x3400 and cp <= 0x4DBF)
        or (cp >= 0xF900 and cp <= 0xFAFF)
        or (cp >= 0x20000 and cp <= 0x323AF)
end

local function analyze_text(s)
    -- Returns (has_hanzi, is_single_hanzi)
    if not s:find("[\128-\255]") then
        return false, false
    end
    local count = 0
    local found_hanzi = false
    for _, cp in utf8.codes(s) do
        count = count + 1
        if is_hanzi_cp(cp) then
            found_hanzi = true
            if count > 1 then
                return true, false
            end
        elseif count > 1 and found_hanzi then
            return true, false
        end
    end
    return found_hanzi, (found_hanzi and count == 1)
end

local function emit_variant(cand, src, text, seen)
    if not text or text == "" or seen[text] then
        return
    end
    seen[text] = true
    if text == src then
        yield(cand)
    else
        yield(cand:to_shadow_candidate(cand.type, text, cand.comment))
    end
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
        local has_hz, is_single = analyze_text(src)
        if not has_hz then
            yield(cand)
        elseif is_single then
            local words_twp = conv_twp:convert_word(src)
            local words_tw = conv_tw and conv_tw:convert_word(src) or nil
            if (words_twp and #words_twp > 0) or (words_tw and #words_tw > 0) then
                local seen = {}
                if words_twp then
                    for i = 1, #words_twp do
                        emit_variant(cand, src, words_twp[i], seen)
                    end
                end
                if words_tw then
                    for i = 1, #words_tw do
                        emit_variant(cand, src, words_tw[i], seen)
                    end
                end
            else
                yield(cand)
            end
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
