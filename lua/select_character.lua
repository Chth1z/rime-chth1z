-- 以词定字
-- 原脚本 https://github.com/BlindingDark/rime-lua-select-character
-- 支持单字/词组/长句定字、光标不在句尾及长句部分选词后保留剩余编码，
-- 使用 cand._end 与 plain 匹配，修复光标在句首重复回填与特殊字符/重复词误替换问题。

local select = {}

function select.init(env)
    local config = env.engine.schema.config
    env.first_key = config:get_string('key_binder/select_first_character')
    env.last_key = config:get_string('key_binder/select_last_character')
end

function select.func(key, env)
    local engine = env.engine
    local context = engine.context

    if
        not key:release()
        and (context:is_composing() or context:has_menu())
        and (env.first_key or env.last_key)
    then
        local repr = key:repr()
        local is_first = (repr == env.first_key)
        local is_last = (repr == env.last_key)
        if not is_first and not is_last then
            return 2
        end

        local input = context.input
        local cand = context:get_selected_candidate()
        local selected_text = cand and cand.text or input
        if selected_text == '' then
            return 2
        end

        local selected_char
        if is_first then
            local second = utf8.offset(selected_text, 2)
            selected_char = second and selected_text:sub(1, second - 1) or selected_text
        else
            local last = utf8.offset(selected_text, -1)
            selected_char = last and selected_text:sub(last) or selected_text
        end

        -- 获取当前段之前的已确认文本（若存在）
        local commit_text = context:get_commit_text()
        local preedit = context:get_preedit()
        local sel_start = (preedit and preedit.sel_start and preedit.sel_start > 0) and preedit.sel_start or 0
        local confirmed_prefix = ''
        if sel_start > 0 then
            local pos = commit_text:find(selected_text, sel_start + 1, true)
            if pos then
                confirmed_prefix = commit_text:sub(1, pos - 1)
            else
                -- 兼容 preedit 与 commit_text 之间可能存在的空格差异
                pos = commit_text:find(selected_text, 1, true)
                if pos then
                    confirmed_prefix = commit_text:sub(1, pos - 1)
                end
            end
        end

        -- 精确计算当前候选之后尚未消费的原始编码
        local consumed_end
        if cand and cand._end and cand._end > 0 then
            consumed_end = cand._end
        else
            local caret_pos = context.caret_pos
            consumed_end = (caret_pos and caret_pos > 0) and caret_pos or #input
        end
        local remaining_input = consumed_end < #input and input:sub(consumed_end + 1) or ''

        engine:commit_text(confirmed_prefix .. selected_char)
        context:clear()
        if remaining_input ~= '' then
            context:push_input(remaining_input)
        end
        return 1
    end
    return 2
end

return select
