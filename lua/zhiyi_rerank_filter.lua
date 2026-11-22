-- Native ONNX neural sentence reranker filter (Zhiyi 1.4V2-Long-L12, Apache-2.0).
-- Loads `zhiyi/rime_zhiyi.dll` in-process via Weasel's official Lua 5.4 C API.
-- Features:
--   * Zero custom rime.dll required; works on official unmodified Weasel (librime >= 1.17.0).
--   * Non-blocking background initialization (`init_async`) -> 0 ms Weasel startup delay.
--   * Strict dictionary protection: only reranks `sentence` candidates, never overrides exact
--     dictionary/userdb hits (`phrase`, `user_phrase`, `table`, `completion`, etc.).
--   * Traditional-to-Simplified context normalization (`t2s.json`) for Taiwan Traditional mode.
--   * Graceful zero-cost pass-through if DLL/model is absent or `neural_rerank` option is off.

local M = {}

local native_mod = nil
local native_loaded = false
local native_attempted = false

local function join_path(a, b)
    if a:sub(-1) == "\\" or a:sub(-1) == "/" then
        return a .. b
    end
    return a .. "\\" .. b
end

local function file_exists(path)
    local f = io.open(path, "rb")
    if f then
        f:close()
        return true
    end
    return false
end

local function ensure_native(user_dir, threads, sync_init)
    if native_attempted then
        if native_loaded and sync_init and native_mod and not native_mod.is_ready() then
            local zdir = join_path(user_dir, "zhiyi")
            native_mod.init(zdir, join_path(zdir, "onnxruntime.dll"), threads)
        end
        return native_loaded
    end
    native_attempted = true

    local zdir = join_path(user_dir, "zhiyi")
    local dll_path = join_path(zdir, "rime_zhiyi.dll")
    local ort_path = join_path(zdir, "onnxruntime.dll")
    local onnx_path = join_path(zdir, "laya.int8g.onnx")

    if not (file_exists(dll_path) and file_exists(ort_path) and file_exists(onnx_path)) then
        return false
    end

    local loader, err = package.loadlib(dll_path, "luaopen_rime_zhiyi")
    if not loader then
        if log and log.warning then
            log.warning("zhiyi_rerank: loadlib failed: " .. tostring(err))
        end
        return false
    end

    local ok_mod, mod = pcall(loader)
    if not ok_mod or type(mod) ~= "table" or type(mod.rerank) ~= "function" then
        if log and log.warning then
            log.warning("zhiyi_rerank: luaopen_rime_zhiyi failed: " .. tostring(mod))
        end
        return false
    end

    if sync_init then
        local ok_init, init_err = mod.init(zdir, ort_path, threads)
        if not ok_init then
            if log and log.warning then
                log.warning("zhiyi_rerank: init failed: " .. tostring(init_err))
            end
            return false
        end
    else
        mod.init_async(zdir, ort_path, threads)
    end

    native_mod = mod
    native_loaded = true
    return true
end

local function get_preceding_context(context, segment_start, t2s)
    local parts = {}
    local hist = context.commit_history
    if hist then
        if type(hist.to_table) == "function" then
            local tbl = hist:to_table()
            if type(tbl) == "table" and #tbl > 0 then
                local start_i = math.max(1, #tbl - 5)
                for i = start_i, #tbl do
                    local rec = tbl[i]
                    if rec and rec.text and #rec.text > 0 then
                        parts[#parts + 1] = rec.text
                    end
                end
            end
        elseif type(hist.latest_text) == "function" then
            local lt = hist:latest_text()
            if lt and #lt > 0 then
                parts[#parts + 1] = lt
            end
        elseif type(hist.back) == "function" then
            local rec = hist:back()
            if rec and rec.text and #rec.text > 0 then
                parts[#parts + 1] = rec.text
            end
        end
    end

    if segment_start > 0 and context.composition then
        local comp = context.composition
        if type(comp.toSegmentation) == "function" then
            local segs = comp:toSegmentation()
            if segs then
                for i = 0, segs.size - 1 do
                    local seg = segs:get_at(i)
                    if seg and seg._end <= segment_start then
                        local cand = seg:get_selected_candidate()
                        if cand and cand.text and #cand.text > 0 then
                            parts[#parts + 1] = cand.text
                        end
                    end
                end
            end
        end
    end

    if #parts == 0 then
        return ""
    end
    local text = table.concat(parts)
    if #text > 384 then
        local cut = #text - 384 + 1
        while cut <= #text and (string.byte(text, cut) >= 0x80 and string.byte(text, cut) < 0xC0) do
            cut = cut + 1
        end
        text = string.sub(text, cut)
    end
    if t2s then
        local ok, conv = pcall(t2s.convert, t2s, text)
        if ok and conv then
            text = conv
        end
    end
    return text
end

function M.init(env)
    local cfg = env.engine.schema.config
    local ns = "zhiyi_rerank"
    env.option_name = cfg:get_string(ns .. "/option_name") or "neural_rerank"
    env.max_candidates = cfg:get_int(ns .. "/max_candidates") or 8
    env.rank_penalty = cfg:get_double(ns .. "/rank_penalty") or 1.4
    env.threads = cfg:get_int(ns .. "/threads") or 6
    env.min_input_len = cfg:get_int(ns .. "/min_input_len") or 4
    local sync_init = cfg:get_bool(ns .. "/sync_init")
    env.sync_init = (sync_init == true)

    env.is_double_pinyin = cfg:get_bool(ns .. "/double_pinyin")
    if env.is_double_pinyin == nil then
        env.is_double_pinyin = (env.engine.schema.schema_id:find("double_pinyin", 1, true) ~= nil)
    end

    local user_dir = rime_api.get_user_data_dir()
    env.ready = ensure_native(user_dir, env.threads, env.sync_init)

    local ok_occ, occ = pcall(Opencc, "t2s.json")
    env.t2s = (ok_occ and occ) or nil
end

function M.func(input, env)
    local ctx = env.engine.context
    if not env.ready or not native_mod or not ctx:get_option(env.option_name) or not native_mod.is_ready() then
        for cand in input:iter() do
            yield(cand)
        end
        return
    end

    local max_k = env.max_candidates
    local is_first = true
    local passthrough = false
    local flushed = false
    local seg_start = 0
    local seg_end = 0
    local raw_seg = ""
    local sent_cands = nil
    local sent_texts = nil
    local seen_texts = nil

    local function flush_sentences()
        flushed = true
        if not sent_cands then
            return
        end
        if #sent_cands >= 2 then
            local pre_ctx = get_preceding_context(ctx, seg_start, env.t2s)
            local order = native_mod.rerank(pre_ctx, raw_seg, env.is_double_pinyin, sent_texts, env.rank_penalty)
            if type(order) == "table" and #order == #sent_cands then
                for i = 1, #order do
                    local idx = order[i]
                    if sent_cands[idx] then
                        yield(sent_cands[idx])
                    end
                end
                return
            end
        end
        for i = 1, #sent_cands do
            yield(sent_cands[i])
        end
    end

    for cand in input:iter() do
        if passthrough or flushed then
            yield(cand)
        elseif is_first then
            is_first = false
            local g0 = cand:get_genuine()
            if not g0 or g0.type ~= "sentence" then
                passthrough = true
                yield(cand)
            else
                seg_start = cand.start
                seg_end = cand._end
                raw_seg = string.sub(ctx.input or "", seg_start + 1, seg_end)
                local letter_cnt = 0
                for i = 1, #raw_seg do
                    local b = string.byte(raw_seg, i)
                    if (b >= 65 and b <= 90) or (b >= 97 and b <= 122) then
                        letter_cnt = letter_cnt + 1
                    end
                end
                if letter_cnt < env.min_input_len or (env.is_double_pinyin and (letter_cnt % 2) == 1) then
                    passthrough = true
                    yield(cand)
                else
                    sent_cands = { cand }
                    sent_texts = { cand.text }
                    seen_texts = { [cand.text] = true }
                end
            end
        else
            local g = cand:get_genuine()
            if #sent_cands < max_k
                and g and g.type == "sentence"
                and cand.start == seg_start and cand._end == seg_end
            then
                if not seen_texts[cand.text] then
                    seen_texts[cand.text] = true
                    sent_cands[#sent_cands + 1] = cand
                    sent_texts[#sent_texts + 1] = cand.text
                end
            else
                flush_sentences()
                yield(cand)
            end
        end
    end

    if not passthrough and not flushed and sent_cands then
        flush_sentences()
    end
end

function M.fini(env)
    env.t2s = nil
end

return M
