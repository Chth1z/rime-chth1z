-- Unified single-pass Lua filter for rime-chth1z:
-- Combines pin_cand + corrector + autocap + reduce_english + throttled incremental GC step
-- into a single C++ <-> Lua traversal while preserving standard schema config keys
-- (pin_cand_filter, corrector, reduce_english_filter).

local M = {}

local CORRECTIONS_REL = "cn_dicts/corrections.dict.yaml"
local cached_corrections = nil
local cached_has_single = false
local logged_corrections_warn = false
local gc_tick = 0

local function open_corrections_file()
    local candidates = {}
    if rime_api and type(rime_api.get_user_data_dir) == "function" then
        local ud = rime_api.get_user_data_dir()
        if type(ud) == "string" and #ud > 0 then
            candidates[#candidates + 1] = ud .. "/" .. CORRECTIONS_REL
        end
    end
    -- Relative fallback works when Weasel CWD is user_data_dir even under non-ASCII Windows profiles
    candidates[#candidates + 1] = CORRECTIONS_REL
    if rime_api and type(rime_api.get_shared_data_dir) == "function" then
        local ok_s, sd = pcall(rime_api.get_shared_data_dir)
        if ok_s and type(sd) == "string" and #sd > 0 then
            candidates[#candidates + 1] = sd .. "/" .. CORRECTIONS_REL
        end
    end
    for i = 1, #candidates do
        local f = io.open(candidates[i], "r")
        if f then
            return f
        end
    end
    return nil
end

local function load_corrections()
    if cached_corrections ~= nil then
        return cached_corrections, cached_has_single
    end

    local file = open_corrections_file()
    if not file then
        if not logged_corrections_warn and log and log.warning then
            logged_corrections_warn = true
            log.warning("chth1z_pipeline_filter: unable to open " .. CORRECTIONS_REL .. " (check non-ASCII user path or deployment)")
        end
        return {}, false
    end

    local corrections = {}
    local has_single = false
    for line in file:lines() do
        line = line:gsub("\r$", "")
        local text, code, comment = line:match("^([^\t#][^\t]*)\t([^\t]+)\t[^\t]*\t(.+)$")
        if text and code and comment then
            if not has_single and not code:find(" ", 1, true) then
                has_single = true
            end
            local items = corrections[code]
            local item = { text = text, comment = comment }
            if items then
                items[#items + 1] = item
            else
                corrections[code] = { item }
            end
        end
    end
    file:close()

    cached_corrections = corrections
    cached_has_single = has_single
    return corrections, has_single
end

local function load_pin_cands(config)
    local list = config:get_list("pin_cand_filter")
    if not list or list.size == 0 then
        return nil
    end

    local explicit = {}
    for i = 0, list.size - 1 do
        local item = list:get_value_at(i)
        local raw = item and item.value
        if type(raw) == "string" then
            local preedit, texts = raw:match("([^\t]+)\t(.+)")
            if preedit and texts and #preedit > 0 and #texts > 0 then
                explicit[preedit:gsub(" ", "")] = true
            end
        end
    end

    local pin_cands = {}
    local auto_seen = {}
    local sep = "\x1f"
    for i = 0, list.size - 1 do
        local item = list:get_value_at(i)
        local raw = item and item.value
        local preedit, texts = nil, nil
        if type(raw) == "string" then
            preedit, texts = raw:match("([^\t]+)\t(.+)")
        end
        if preedit and texts and #preedit > 0 and #texts > 0 then
            if texts:find(" > ", 1, true) then
                texts = texts:gsub(" > ", sep)
            else
                texts = texts:gsub(" ", sep)
            end

            local preedit_no_spaces = preedit:gsub(" ", "")
            local entries = {}
            local seen_entry = {}
            for text in texts:gmatch("[^" .. sep .. "]+") do
                if not seen_entry[text] then
                    seen_entry[text] = true
                    entries[#entries + 1] = text
                end
            end
            pin_cands[preedit_no_spaces] = entries

            if preedit:find(" ", 1, true) then
                local preceding_part, last_part = preedit:match("^(.+)%s(%S+)$")
                if preceding_part and last_part then
                    local prefix = preceding_part:gsub(" ", "")
                    local p1 = prefix .. last_part:sub(1, 1)
                    local p2 = last_part:match("^[zcs]h") and (prefix .. last_part:sub(1, 2)) or ""
                    for _, p in ipairs({ p1, p2 }) do
                        if p ~= "" and not explicit[p] then
                            local target = pin_cands[p]
                            local seen = auto_seen[p]
                            if not target then
                                target = {}
                                seen = {}
                                pin_cands[p] = target
                                auto_seen[p] = seen
                            end
                            for j = 1, #entries do
                                local text = entries[j]
                                if not seen[text] then
                                    seen[text] = true
                                    target[#target + 1] = text
                                end
                            end
                        end
                    end
                end
            end
        end
    end

    return next(pin_cands) ~= nil and pin_cands or nil
end

local BUILTIN_REDUCE_WORDS = {
    "aid", "aim", "air", "and", "ann", "ant", "any", "bad", "bag", "bail", "bait", "bam", "ban", "band",
    "bang", "bank", "bans", "bar", "bat", "bay", "bend", "benq", "bent", "benz", "bib", "bid", "bien", "big", "bin",
    "bind", "bit", "biz", "bob", "boc", "bop", "bos", "bot", "bow", "box", "boy", "bud", "buf", "bug", "bus",
    "but", "buy", "cab", "cad", "cain", "cam", "can", "cans", "cant", "cap", "car", "cat", "cef", "cen",
    "cent", "chad", "chan", "chap", "char", "chat", "chef", "chen", "cher", "chew", "chic", "chin", "chip", "chit",
    "coup", "cum", "cunt", "cup", "cur", "cut", "dab", "dad", "dag", "dal", "dam", "day", "def", "del", "den",
    "dent", "deny", "der", "dew", "dial", "did", "died", "dies", "diet", "dig", "dim", "din", "dip", "dir", "dis",
    "dit", "diy", "doug", "dub", "dug", "dun", "dunn", "don", "end", "err", "fab", "fan", "fans", "faq", "far", "fat",
    "fax", "fob", "fog", "for", "foul", "four", "fox", "fun", "fur", "gag", "gail", "gain", "gal", "gam", "gan",
    "gang", "gank", "gaol", "gap", "gas", "gay", "ged", "gel", "gem", "gen", "ger", "get", "guam", "guid", "gum",
    "gun", "guns", "gus", "gut", "guy", "had", "hail", "hair", "ham", "han", "hand", "hang", "hank", "hans", "has",
    "hat", "hay", "heil", "heir", "hem", "hen", "hep", "her", "hex", "hey", "hour", "hub", "hud", "hug", "huh",
    "hum", "hung", "hunk", "hunt", "hut", "jim", "jug", "junk", "kat", "kent", "key", "lab", "lad", "lag", "laid",
    "lam", "lan", "land", "lang", "laos", "lap", "lat", "law", "lax", "lay", "led", "leg", "len", "let", "lex",
    "liam", "liar", "lib", "lid", "lied", "lien", "lies", "ling", "link", "linn", "lip", "lit", "liz", "lob", "log",
    "lol", "lot", "loud", "low", "lug", "lund", "lung", "lux", "mac", "mad", "mag", "maid", "mail", "main", "man",
    "mann", "many", "map", "mar", "mat", "max", "may", "med", "mel", "men", "mend", "mens", "ment", "met", "mic",
    "mid", "mil", "min", "mind", "ming", "mins", "mint", "mit", "mix", "mob", "moc", "mod", "mom", "mop", "mos",
    "mot", "mud", "mug", "mum", "nad", "nail", "nan", "nap", "nas", "nat", "nay", "neil", "net", "new", "nib", "nil",
    "nip", "noun", "nous", "nun", "nut", "nvm", "our", "out", "pac", "pad", "paid", "pail", "pain", "pair", "pak", "pal",
    "pam", "pan", "pans", "pant", "pap", "par", "pat", "paw", "pax", "pay", "pens", "pic", "pier", "pies", "pig",
    "pin", "ping", "pink", "pins", "pint", "pit", "pix", "pod", "pop", "por", "pos", "pot", "pour", "pow", "pub",
    "put", "rand", "rang", "rank", "rant", "red", "rent", "rep", "res", "ret", "rex", "rib", "rid", "rig", "rim",
    "rip", "rub", "rug", "ruin", "rum", "run", "runc", "runs", "sac", "sad", "said", "sail", "sal", "sam", "san",
    "sand", "sang", "sans", "sap", "sat", "saw", "sax", "say", "sec", "send", "sent", "set", "sew", "sex", "sham",
    "shaw", "shed", "shin", "ship", "shit", "shut", "sig", "sim", "sin", "sip", "sir", "sis", "sit", "six", "soul",
    "soup", "sour", "sub", "suit", "sum", "sun", "sung", "suns", "sup", "sur", "sus", "tab", "tad", "tag", "tail",
    "taj", "tan", "tang", "tank", "tap", "tar", "tax", "tec", "ted", "tel", "ten", "ter", "tex", "tic", "tied",
    "tier", "ties", "tim", "tin", "tip", "tit", "tour", "tout", "tum", "wag", "wait", "wail", "wan", "wand", "womens",
    "want", "wap", "war", "was", "wax", "way", "weir", "went", "won", "wow", "yan", "yang", "yen", "yep", "yes",
    "yet", "yin", "your", "yum", "zen", "zip",
    "bach", "bash", "bench", "bush", "cash", "couch", "dash", "dish", "hash", "hush", "lash", "loch", "lunch",
    "lush", "mesh", "much", "nash", "pinch", "pouch", "push", "ranch", "rich", "rush", "such", "tech", "touch",
    "wash", "zach",
    "eg", "my", "mt", "dj", "as", "js", "cs", "ak", "ps", "cd", "cn", "hk", "bt", "pk", "ml"
}

local function load_reduce_english(config)
    local idx = config:get_int("reduce_english_filter/idx") or 2
    local mode = config:get_string("reduce_english_filter/mode")
    local map = {}

    if mode == "none" then
        return idx, map
    end

    if mode ~= "custom" then
        for i = 1, #BUILTIN_REDUCE_WORDS do
            map[BUILTIN_REDUCE_WORDS[i]] = true
        end
    end

    local list = config:get_list("reduce_english_filter/words")
    if list then
        for i = 0, list.size - 1 do
            local item = list:get_value_at(i)
            if item and type(item.value) == "string" then
                map[item.value] = true
            end
        end
    end

    return idx, map
end

--- Extract the active unconfirmed segment slice from `context.input` so multi-segment input
--- (e.g. confirmed Chinese seg 1 + English seg 2) drives `autocap` and `reduce_english` accurately.
local function active_segment_code(context)
    local full = context.input or ""
    local comp = context.composition
    if comp and not comp:empty() then
        local seg = comp:back()
        if seg and seg.start and seg._end and seg._end > seg.start then
            return full:sub(seg.start + 1, seg._end)
        end
    end
    return full
end

function M.init(env)
    local config = env.engine.schema.config

    -- 1. pin_cand config
    env.pin_cands = load_pin_cands(config)
    env.pin_max_scan = config:get_int("chth1z_pipeline/pin_max_scan") or 40

    -- 2. corrector config
    env.keep_comment = config:get_bool("translator/keep_comments") or false
    local delimiter = config:get_string("speller/delimiter")
    if delimiter and #delimiter > 0 and delimiter:sub(1, 1) ~= " " then
        env.delimiter = delimiter:sub(1, 1):gsub("([%^%$%(%)%%%.%[%]%*%+%-%?])", "%%%1")
    else
        env.delimiter = nil
    end
    local style = config:get_string("corrector") or "{comment}"
    env.corrector_style = style
    env.corrector_plain = (style == "{comment}")
    env.corrections, env.corrections_has_single = load_corrections()

    -- 3. reduce_english config
    env.reduce_idx, env.reduce_map = load_reduce_english(config)

    -- 4. GC step interval (0 disables internal GC stepping)
    local gc_interval = config:get_int("chth1z_pipeline/gc_interval")
    env.gc_interval = gc_interval ~= nil and gc_interval or 16
end

function M.func(input, env)
    local gc_interval = env.gc_interval
    if gc_interval > 0 then
        gc_tick = gc_tick + 1
        if gc_tick >= gc_interval then
            gc_tick = 0
            collectgarbage("step", 0)
        end
    end

    local context = env.engine.context
    local code = active_segment_code(context)
    local codeLen = #code

    -- Autocap mode: 0 = off, 1 = Title, 2 = ALL UPPER
    local cap_mode = 0
    local pureCodeLower
    if codeLen > 1 then
        local b1 = code:byte(1)
        if b1 >= 65 and b1 <= 90 then
            local b2 = code:byte(2)
            if b2 >= 65 and b2 <= 90 then
                cap_mode = 2
            else
                cap_mode = 1
            end
            pureCodeLower = code:gsub("[%s%p]", ""):lower()
        end
    end

    -- Localize hot-path upvalues
    local corrections = env.corrections
    local has_single = env.corrections_has_single
    local env_delimiter = env.delimiter
    local keep_comment = env.keep_comment
    local corrector_style = env.corrector_style
    local corrector_plain = env.corrector_plain

    local reduce_active = env.reduce_map[code] == true
    local reduce_idx = env.reduce_idx
    local reduce_seen = 0
    local reduce_done = false
    local pending = reduce_active and {} or nil

    local function emit(cand)
        -- Stage 2: corrector (parse full-width bracketed pinyin comment ［...］)
        local comment = cand.comment
        if #comment >= 6 and comment:byte(1) == 0xEF
            and comment:sub(1, 3) == "\239\188\187" and comment:sub(-3) == "\239\188\189" then
            local pinyin = comment:sub(4, -4)
            local correction_comment
            if #pinyin > 0 and (has_single or env_delimiter or pinyin:find(" ", 1, true)) then
                local key = env_delimiter and pinyin:gsub(env_delimiter, " ") or pinyin
                local items = corrections[key]
                if items then
                    local ctext = cand.text
                    for i = #items, 1, -1 do
                        local item = items[i]
                        if ctext == item.text then
                            correction_comment = item.comment
                            break
                        end
                    end
                end
            end
            if correction_comment then
                cand:get_genuine().comment = corrector_plain and correction_comment
                    or corrector_style:gsub("{comment}", function() return correction_comment end)
            elseif keep_comment and #pinyin > 0 then
                cand:get_genuine().comment = corrector_plain and pinyin
                    or corrector_style:gsub("{comment}", function() return pinyin end)
            else
                cand:get_genuine().comment = ""
            end
        end

        -- Stage 3: autocap (only active when active segment length > 1 and starts with A-Z)
        if cap_mode ~= 0 then
            local text = cand.text
            if not text:find("[^%w%p%s]") and not text:find("%s") then
                local pureText = text:gsub("[%s%p]", "")
                if pureText:sub(1, codeLen) ~= code
                    and (cand.type == "completion" or pureCodeLower == pureText:lower()) then
                    if cap_mode == 2 then
                        -- Preserve intentional CamelCase brand words (uppercase after pos 1 + lowercase, e.g. `VSCode`, `iPhone`, `GitHub`, `jQuery`)
                        if not (text:find("%u", 2) and text:find("%l")) then
                            text = text:upper()
                            cand = cand:to_shadow_candidate(cand.type, text, cand.comment)
                        end
                    else
                        text = text:gsub("^%a", string.upper)
                        cand = cand:to_shadow_candidate(cand.type, text, cand.comment)
                    end
                end
            end
        end

        -- Stage 4: reduce_english (only active when active segment is in reduce_map)
        if not reduce_active or reduce_done then
            yield(cand)
            return
        end

        reduce_seen = reduce_seen + 1
        if cand.preedit:find(" ", 1, true) or not cand.text:find("[a-zA-Z]") or cand.type == "user_table" then
            yield(cand)
        else
            pending[#pending + 1] = cand
        end
        if reduce_seen >= reduce_idx + #pending - 1 then
            for i = 1, #pending do
                yield(pending[i])
            end
            pending = {}
            reduce_done = true
        end
    end

    -- Stage 1: pin_cand
    local pin_cands = env.pin_cands
    if pin_cands and context:get_option("pin_cand") then
        local target_pe, target_texts
        local pined, others
        local pined_count, target_len, others_len = 0, 0, 0
        local pin_max_scan = env.pin_max_scan

        for cand in input:iter() do
            local pe = cand.preedit or ""
            if pe:find(" ", 1, true) then
                pe = pe:gsub(" ", "")
            end

            if not target_texts then
                -- Skip empty-preedit translator hits (date/lunar) without aborting pinning for pinyin candidates
                if pe == "" then
                    emit(cand)
                else
                    local texts = pin_cands[pe]
                    if not texts then
                        emit(cand)
                        break
                    end
                    target_pe = pe
                    target_texts = texts
                    target_len = #texts
                    pined = {}
                    for i = 1, target_len do pined[i] = false end
                    others = {}
                end
            elseif pe ~= target_pe then
                others_len = others_len + 1
                others[others_len] = cand
                break
            end

            if target_texts then
                local ctext = cand.text
                local matched_idx = 0
                for i = 1, target_len do
                    if target_texts[i] == ctext then
                        matched_idx = i
                        break
                    end
                end

                if matched_idx ~= 0 and not pined[matched_idx] then
                    pined[matched_idx] = cand
                    pined_count = pined_count + 1
                else
                    others_len = others_len + 1
                    others[others_len] = cand
                end

                if pined_count == target_len or others_len >= pin_max_scan then
                    break
                end
            end
        end

        if pined then
            for i = 1, target_len do
                local c = pined[i]
                if c then emit(c) end
            end
            for i = 1, others_len do
                emit(others[i])
            end
        end
    end

    -- Stream remaining candidates
    for cand in input:iter() do
        emit(cand)
    end

    -- Flush any buffered English candidates when total candidates < reduce_idx + #pending - 1
    if reduce_active and not reduce_done and #pending > 0 then
        for i = 1, #pending do
            yield(pending[i])
        end
    end
end

return M
