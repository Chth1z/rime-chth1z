-- Universal ONNX neural sentence reranker filter for Rime / Weasel (v0.3.0).
-- Loads `zhiyi/rime_zhiyi.dll` in-process via official Weasel's Lua 5.4 C API.
-- Features:
--   * Zero custom rime.dll required; works on official unmodified Weasel (librime >= 1.17.0).
--   * Universal layout auto-detection: Full Pinyin + 7 Double Pinyin layouts
--     (ZRM, Flypy, MSPY, Sogou, ABC, Ziguang, Jiajia) across rime-ice / rime-frost / rime-wanxiang.
--   * Non-blocking background initialization (`init_async`) -> 0 ms Weasel startup delay.
--   * Fused prefix KV-cache (`laya.one.fused.int8g.onnx`) + direct mmap `.gram` score fusion
--     + KV-cached Pass-2 cross-encoder verified `char_logits` P2C OOV candidate synthesis.
--   * Non-blocking background Windows UIA preceding-text context (zero keystroke freeze,
--     window-isolated to prevent cross-app contamination, hard password-field blocking).
--   * Strict dictionary protection: only reranks `sentence` candidates, never overrides exact
--     dictionary/userdb hits (`phrase`, `user_phrase`, `table`, `completion`, etc.).
--   * Traditional-to-Simplified context normalization (`t2s.json`) for Traditional schemas.
--   * Optional privacy-first local feedback logger (`commit_notifier` -> `zhiyi/feedback.jsonl`).
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

local function ensure_native(user_dir, threads, gram_file, sync_init)
    local zdir = join_path(user_dir, "zhiyi")
    local ort_path = join_path(zdir, "onnxruntime.dll")
    local gram_path = ""
    if gram_file and #gram_file > 0 then
        local gp = join_path(user_dir, gram_file)
        if file_exists(gp) then
            gram_path = gp
        end
    end

    if native_attempted then
        if native_loaded and sync_init and native_mod and not native_mod.is_ready() then
            native_mod.init(zdir, ort_path, threads, gram_path)
        end
        return native_loaded
    end
    native_attempted = true

    local dll_path = join_path(zdir, "rime_zhiyi.dll")
    local has_model = file_exists(join_path(zdir, "laya.one.fused.int8g.onnx"))
        or file_exists(join_path(zdir, "laya.one.int8g.onnx"))
        or file_exists(join_path(zdir, "laya.int8g.onnx"))

    if not (file_exists(dll_path) and file_exists(ort_path) and has_model) then
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
        local ok_init, init_err = mod.init(zdir, ort_path, threads, gram_path)
        if not ok_init then
            if log and log.warning then
                log.warning("zhiyi_rerank: init failed: " .. tostring(init_err))
            end
            return false
        end
    else
        mod.init_async(zdir, ort_path, threads, gram_path)
    end

    native_mod = mod
    native_loaded = true
    return true
end

local function append_composition_prefix(parts, context, segment_start)
    if segment_start <= 0 or not context.composition then
        return
    end
    local comp = context.composition
    if type(comp.toSegmentation) ~= "function" then
        return
    end
    local segs = comp:toSegmentation()
    if not segs then
        return
    end
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

local function append_commit_history(parts, context)
    local hist = context.commit_history
    if not hist then
        return
    end
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

--- Resolve preceding context with strict cross-app isolation & password protection.
--- Returns `(normalized_ctx_str, is_password_blocked)`.
local function get_preceding_context(context, segment_start, live_preedit, raw_seg, env)
    local parts = {}

    if env.enable_uia and native_mod and type(native_mod.query_uia_context) == "function" then
        local status, uia_text = native_mod.query_uia_context(live_preedit or "", raw_seg or "")
        if status == "blocked" then
            -- Password control or password manager -> force empty context & suppress feedback logging
            return "", true
        elseif status == "text" then
            -- Authoritative before-caret text from the active control (may be "" for fresh boxes -> zero bleed!)
            if uia_text and #uia_text > 0 then
                parts[#parts + 1] = uia_text
            end
            append_composition_prefix(parts, context, segment_start)
        elseif status == "window_changed" then
            -- Just switched foreground window -> discard stale commit_history from previous app
            append_composition_prefix(parts, context, segment_start)
        else
            -- Same window, control lacks UIA -> safe to fall back to same-window commit_history
            append_commit_history(parts, context)
            append_composition_prefix(parts, context, segment_start)
        end
    else
        append_commit_history(parts, context)
        append_composition_prefix(parts, context, segment_start)
    end

    if #parts == 0 then
        return "", false
    end
    local text = table.concat(parts)
    if #text > 384 then
        local cut = #text - 384 + 1
        while cut <= #text and (string.byte(text, cut) >= 0x80 and string.byte(text, cut) < 0xC0) do
            cut = cut + 1
        end
        text = string.sub(text, cut)
    end
    if env.t2s then
        local ok, conv = pcall(env.t2s.convert, env.t2s, text)
        if ok and conv then
            text = conv
        end
    end
    return text, false
end

local function load_fusion_weights(cfg, ns)
    local defaults = { 0.91, -1.26, 0.05, 0.40, -0.39 }
    local list = cfg:get_list(ns .. "/fusion_weights")
    if list and list.size >= 5 then
        local out = {}
        for i = 0, 4 do
            local v = list:get_value_at(i)
            local num = v and v:get_double()
            out[i + 1] = num or defaults[i + 1]
        end
        return out
    end
    return defaults
end

local function load_p2c_cfg(cfg, ns)
    return {
        verify_margin = cfg:get_double(ns .. "/p2c_verify_margin") or 0.20,
        top1_logit_diff = cfg:get_double(ns .. "/p2c_top1_logit_diff") or 2.0,
        top1_min_gram_diff = cfg:get_double(ns .. "/p2c_top1_min_gram_diff") or -2.0,
        top2_logit_diff = cfg:get_double(ns .. "/p2c_top2_logit_diff") or 0.5,
        legacy_top1_margin = cfg:get_double(ns .. "/p2c_top1_threshold") or 1.0,
        legacy_top2_margin = cfg:get_double(ns .. "/p2c_top2_threshold") or 0.45,
    }
end

function M.init(env)
    local cfg = env.engine.schema.config
    local ns = "zhiyi_rerank"
    env.schema_id = env.engine.schema.schema_id
    env.option_name = cfg:get_string(ns .. "/option_name") or "neural_rerank"
    env.max_candidates = cfg:get_int(ns .. "/max_candidates") or 8
    env.fusion_weights = load_fusion_weights(cfg, ns)
    env.p2c_cfg = load_p2c_cfg(cfg, ns)
    env.threads = cfg:get_int(ns .. "/threads") or 8
    env.sync_init = (cfg:get_bool(ns .. "/sync_init") == true)

    local user_dir = rime_api.get_user_data_dir()
    local in_temp = (user_dir:lower():find("\\temp\\", 1, true) ~= nil)

    local allow_temp_log = (cfg:get_bool(ns .. "/log_feedback_in_temp") == true)
    env.log_feedback = (cfg:get_bool(ns .. "/log_feedback") == true) and (not in_temp or allow_temp_log)
    env.feedback_path = join_path(join_path(user_dir, "zhiyi"), "feedback.jsonl")

    local uia_opt = cfg:get_bool(ns .. "/enable_uia_context")
    if uia_opt == nil then
        uia_opt = true
    end
    local allow_temp_uia = (cfg:get_bool(ns .. "/enable_uia_in_temp") == true)
    env.enable_uia = uia_opt and (not in_temp or allow_temp_uia)

    env.feedback_sample_n = 0
    env.last_rerank = nil

    local gram_lang = cfg:get_string("grammar/language")
    local gram_file = (gram_lang and #gram_lang > 0) and (gram_lang .. ".gram") or ""

    env.ready = ensure_native(user_dir, env.threads, gram_file, env.sync_init)

    -- Resolve pinyin layout universally (auto-detects Full + 7 Double Pinyin schemes)
    local layout_opt = cfg:get_string(ns .. "/pinyin_layout") or "auto"
    if layout_opt == "auto" then
        local dp_legacy = cfg:get_bool(ns .. "/double_pinyin")
        if dp_legacy == false then
            layout_opt = "full"
        end
    end
    if env.ready and native_mod and type(native_mod.resolve_layout) == "function" then
        env.layout, env.is_double_pinyin, env.uses_semicolon = native_mod.resolve_layout(layout_opt, env.schema_id)
    else
        env.is_double_pinyin = (env.schema_id:find("double_pinyin", 1, true) ~= nil)
        env.layout = env.is_double_pinyin and "zrm" or "full"
        env.uses_semicolon = false
    end

    env.min_input_len = cfg:get_int(ns .. "/min_input_len") or (env.is_double_pinyin and 4 or 6)

    if env.ready and native_mod and type(native_mod.set_uia_enabled) == "function" then
        native_mod.set_uia_enabled(env.enable_uia)
    end

    local ok_occ, occ = pcall(Opencc, "t2s.json")
    env.t2s = (ok_occ and occ) or nil

    -- Connect commit_notifier once for UIA post-commit refresh + optional local feedback capture
    if (env.log_feedback or env.enable_uia) and env.engine.context and env.engine.context.commit_notifier then
        env.commit_conn = env.engine.context.commit_notifier:connect(function(ctx)
            if env.enable_uia and native_mod and type(native_mod.kick_uia_refresh) == "function" then
                native_mod.kick_uia_refresh()
            end

            if not env.log_feedback then
                return
            end
            local snap = env.last_rerank
            env.last_rerank = nil
            if not snap or snap.blocked or not native_mod or type(native_mod.log_feedback) ~= "function" then
                return
            end
            if ctx:get_option("ascii_mode") then
                return
            end
            local committed = ctx:get_commit_text() or ""
            if #committed < 6 then
                return
            end
            local norm_commit = committed
            if env.t2s then
                local ok_c, conv = pcall(env.t2s.convert, env.t2s, committed)
                if ok_c and conv then
                    norm_commit = conv
                end
            end

            local chosen_rank = 0
            for i = 1, #snap.shown do
                if snap.shown[i] == norm_commit then
                    chosen_rank = i
                    break
                end
            end
            if chosen_rank == 0 then
                local top1 = snap.shown[1] or ""
                if math.abs(#norm_commit - #top1) > 6 then
                    return
                end
            end

            -- Log ALL corrections (rank >= 2 or custom edit) + 10% sample of accepted top-1
            local should_log = (chosen_rank ~= 1)
            if not should_log then
                env.feedback_sample_n = env.feedback_sample_n + 1
                if (env.feedback_sample_n % 10) == 0 then
                    should_log = true
                end
            end
            if should_log then
                native_mod.log_feedback(
                    env.schema_id,
                    snap.raw_seg,
                    snap.pre_ctx,
                    snap.cands,
                    snap.logits,
                    snap.gram_deltas,
                    snap.char_lps,
                    snap.p2c_text or "",
                    snap.shown[1] or "",
                    norm_commit,
                    chosen_rank,
                    false,
                    env.feedback_path
                )
            end
        end)
    end
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
    local first_preedit = ""
    local sent_cands = nil
    local sent_texts = nil
    local seen_texts = nil

    local function flush_sentences()
        flushed = true
        if not sent_cands then
            return
        end
        if #sent_cands >= 2 then
            local pre_ctx, is_blocked = get_preceding_context(ctx, seg_start, first_preedit, raw_seg, env)
            local res = native_mod.rerank(
                pre_ctx,
                raw_seg,
                env.layout,
                sent_texts,
                env.fusion_weights,
                env.p2c_cfg
            )
            if type(res) == "table" and type(res.order) == "table" and #res.order == #sent_cands then
                local p2c_cand = nil
                if type(res.p2c_text) == "string" and #res.p2c_text > 0 and (res.p2c_pos == 1 or res.p2c_pos == 2) then
                    p2c_cand = Candidate("sentence", seg_start, seg_end, res.p2c_text, "")
                    p2c_cand.preedit = first_preedit
                end

                local emit_list = {}
                local shown_texts = {}
                if p2c_cand and res.p2c_pos == 1 then
                    emit_list[#emit_list + 1] = p2c_cand
                    shown_texts[#shown_texts + 1] = res.p2c_text
                end
                for i = 1, #res.order do
                    local idx = res.order[i]
                    local c = sent_cands[idx]
                    if c then
                        emit_list[#emit_list + 1] = c
                        shown_texts[#shown_texts + 1] = c.text
                        if #emit_list == 1 and p2c_cand and res.p2c_pos == 2 then
                            emit_list[#emit_list + 1] = p2c_cand
                            shown_texts[#shown_texts + 1] = res.p2c_text
                        end
                    end
                end

                -- Record snapshot BEFORE yielding (Rime Menu is lazy and may pause coroutine after page 1)
                if env.log_feedback then
                    env.last_rerank = {
                        full_input = ctx.input or "",
                        raw_seg = raw_seg,
                        pre_ctx = pre_ctx,
                        cands = sent_texts,
                        logits = res.logits or {},
                        gram_deltas = res.gram_deltas or {},
                        char_lps = res.char_lps or {},
                        p2c_text = res.p2c_text,
                        shown = shown_texts,
                        blocked = is_blocked,
                    }
                end

                for i = 1, #emit_list do
                    yield(emit_list[i])
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
                if env.last_rerank and (ctx.input or "") ~= env.last_rerank.full_input then
                    env.last_rerank = nil
                end
                passthrough = true
                yield(cand)
            else
                seg_start = cand.start
                seg_end = cand._end
                first_preedit = cand.preedit or ""
                raw_seg = string.sub(ctx.input or "", seg_start + 1, seg_end)
                local key_cnt = 0
                local allow_semi = env.uses_semicolon
                for i = 1, #raw_seg do
                    local b = string.byte(raw_seg, i)
                    if (b >= 65 and b <= 90) or (b >= 97 and b <= 122) or (allow_semi and b == 59) then
                        key_cnt = key_cnt + 1
                    end
                end
                if key_cnt < env.min_input_len or (env.is_double_pinyin and (key_cnt % 2) == 1) then
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
    if env.commit_conn then
        pcall(function() env.commit_conn:disconnect() end)
        env.commit_conn = nil
    end
    env.last_rerank = nil
    env.t2s = nil
end

return M
