mod feedback;
mod gram;
mod lua_api;
mod pinyin;
mod zhiyi;

use std::ffi::{c_char, c_int};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::path::{Path, PathBuf};

use lua_api::{get_api, pop, push_str, read_str, LuaInteger, LuaState};
use zhiyi::FusionWeights;

unsafe fn read_str_array(api: &lua_api::LuaApi, l: LuaState, idx: c_int) -> Vec<String> {
    let n = (api.rawlen)(l, idx);
    let mut out = Vec::with_capacity(n);
    for i in 1..=(n as LuaInteger) {
        (api.rawgeti)(l, idx, i);
        if let Some(s) = read_str(api, l, -1) {
            out.push(s);
        }
        pop(api, l, 1);
    }
    out
}

unsafe fn read_f32_array(api: &lua_api::LuaApi, l: LuaState, idx: c_int) -> Vec<f32> {
    let n = (api.rawlen)(l, idx);
    let mut out = Vec::with_capacity(n);
    for i in 1..=(n as LuaInteger) {
        (api.rawgeti)(l, idx, i);
        let mut isnum: c_int = 0;
        let v = (api.tonumberx)(l, -1, &mut isnum);
        out.push(if isnum != 0 { v as f32 } else { 0.0 });
        pop(api, l, 1);
    }
    out
}

unsafe fn push_f32_array(api: &lua_api::LuaApi, l: LuaState, vals: &[f32]) {
    (api.createtable)(l, vals.len() as c_int, 0);
    for (i, &v) in vals.iter().enumerate() {
        (api.pushnumber)(l, v as f64);
        (api.rawseti)(l, -2, (i + 1) as LuaInteger);
    }
}

unsafe fn read_weights(api: &lua_api::LuaApi, l: LuaState, idx: c_int) -> FusionWeights {
    let mut w = FusionWeights::default();
    let n = (api.rawlen)(l, idx);
    if n == 0 {
        // Fallback: allow scalar rank_penalty for backwards compatibility
        let mut isnum: c_int = 0;
        let rp = (api.tonumberx)(l, idx, &mut isnum);
        if isnum != 0 {
            w.w_logit = 1.0;
            w.w_rank = -rp.abs();
            w.w_gram = 0.0;
            w.w_char_lp = 0.0;
            w.w_ctx_lp = 0.0;
        }
        return w;
    }
    let vals = read_f32_array(api, l, idx);
    if vals.len() >= 1 { w.w_logit = vals[0] as f64; }
    if vals.len() >= 2 { w.w_rank = vals[1] as f64; }
    if vals.len() >= 3 { w.w_gram = vals[2] as f64; }
    if vals.len() >= 4 { w.w_char_lp = vals[3] as f64; }
    if vals.len() >= 5 { w.w_ctx_lp = vals[4] as f64; }
    w
}

/// init(model_dir, ort_dll, threads, [gram_path])
unsafe extern "C" fn lua_init(l: LuaState) -> c_int {
    let Ok(api) = get_api() else { return 0; };
    let res = catch_unwind(AssertUnwindSafe(|| -> Result<(), String> {
        let model_dir = read_str(api, l, 1).ok_or("missing arg 1: model_dir")?;
        let ort_dll = read_str(api, l, 2).ok_or("missing arg 2: ort_dll")?;
        let mut isnum: c_int = 0;
        let threads_raw = (api.tointegerx)(l, 3, &mut isnum);
        let threads = if isnum != 0 && threads_raw > 0 { threads_raw as usize } else { 8 };
        let gram_path = read_str(api, l, 4).filter(|s| !s.is_empty());
        zhiyi::init_engine(
            Path::new(&model_dir),
            Path::new(&ort_dll),
            gram_path.as_deref().map(Path::new),
            threads,
        )
    }));
    match res {
        Ok(Ok(())) => {
            (api.pushboolean)(l, 1);
            (api.pushnil)(l);
            2
        }
        Ok(Err(e)) => {
            (api.pushboolean)(l, 0);
            push_str(api, l, &e);
            2
        }
        Err(_) => {
            (api.pushboolean)(l, 0);
            push_str(api, l, "panic in rime_zhiyi.init");
            2
        }
    }
}

/// init_async(model_dir, ort_dll, threads, [gram_path])
unsafe extern "C" fn lua_init_async(l: LuaState) -> c_int {
    let Ok(api) = get_api() else { return 0; };
    let res = catch_unwind(AssertUnwindSafe(|| -> Result<(), String> {
        let model_dir = read_str(api, l, 1).ok_or("missing arg 1: model_dir")?;
        let ort_dll = read_str(api, l, 2).ok_or("missing arg 2: ort_dll")?;
        let mut isnum: c_int = 0;
        let threads_raw = (api.tointegerx)(l, 3, &mut isnum);
        let threads = if isnum != 0 && threads_raw > 0 { threads_raw as usize } else { 8 };
        let gram_path = read_str(api, l, 4).filter(|s| !s.is_empty()).map(PathBuf::from);
        zhiyi::init_engine_async(PathBuf::from(model_dir), PathBuf::from(ort_dll), gram_path, threads);
        Ok(())
    }));
    (api.pushboolean)(l, if matches!(res, Ok(Ok(()))) { 1 } else { 0 });
    1
}

unsafe extern "C" fn lua_is_ready(l: LuaState) -> c_int {
    let Ok(api) = get_api() else { return 0; };
    (api.pushboolean)(l, if zhiyi::is_ready() { 1 } else { 0 });
    1
}

/// rerank(context, raw_input, is_dp, cands_tbl, weights_tbl_or_alpha, [p2c_top1_th], [p2c_top2_th])
/// Returns { order={...}, p2c_text=str|nil, p2c_pos=0|1|2, logits={...}, gram_deltas={...}, char_lps={...} }
unsafe extern "C" fn lua_rerank(l: LuaState) -> c_int {
    let Ok(api) = get_api() else { return 0; };
    let res = catch_unwind(AssertUnwindSafe(|| -> Result<zhiyi::RerankResult, String> {
        if !zhiyi::is_ready() {
            return Err("not ready".to_string());
        }
        let ctx = read_str(api, l, 1).unwrap_or_default();
        let raw_input = read_str(api, l, 2).unwrap_or_default();
        let is_dp = (api.toboolean)(l, 3) != 0;
        let cands = read_str_array(api, l, 4);
        let weights = read_weights(api, l, 5);

        let mut isnum: c_int = 0;
        let t1 = (api.tonumberx)(l, 6, &mut isnum);
        let p2c_top1_th = if isnum != 0 { t1 as f32 } else { 1.0 };
        isnum = 0;
        let t2 = (api.tonumberx)(l, 7, &mut isnum);
        let p2c_top2_th = if isnum != 0 { t2 as f32 } else { 0.45 };

        zhiyi::rerank(&ctx, &raw_input, is_dp, &cands, weights, p2c_top1_th, p2c_top2_th)
    }));

    match res {
        Ok(Ok(rr)) => {
            (api.createtable)(l, 0, 6);

            (api.createtable)(l, rr.order.len() as c_int, 0);
            for (i, idx) in rr.order.into_iter().enumerate() {
                (api.pushinteger)(l, idx as LuaInteger);
                (api.rawseti)(l, -2, (i + 1) as LuaInteger);
            }
            (api.setfield)(l, -2, b"order\0".as_ptr() as *const c_char);

            if let Some(ref txt) = rr.p2c_text {
                push_str(api, l, txt);
            } else {
                (api.pushnil)(l);
            }
            (api.setfield)(l, -2, b"p2c_text\0".as_ptr() as *const c_char);

            (api.pushinteger)(l, rr.p2c_pos as LuaInteger);
            (api.setfield)(l, -2, b"p2c_pos\0".as_ptr() as *const c_char);

            push_f32_array(api, l, &rr.logits);
            (api.setfield)(l, -2, b"logits\0".as_ptr() as *const c_char);

            push_f32_array(api, l, &rr.gram_deltas);
            (api.setfield)(l, -2, b"gram_deltas\0".as_ptr() as *const c_char);

            push_f32_array(api, l, &rr.char_lps);
            (api.setfield)(l, -2, b"char_lps\0".as_ptr() as *const c_char);

            1
        }
        _ => {
            (api.pushnil)(l);
            1
        }
    }
}

/// log_feedback(schema, raw_input, context, cands_tbl, logits_tbl, gram_tbl, char_tbl, p2c_cand_or_nil, shown_top1, chosen_text, chosen_rank, reverted)
unsafe extern "C" fn lua_log_feedback(l: LuaState) -> c_int {
    let Ok(api) = get_api() else { return 0; };
    let res = catch_unwind(AssertUnwindSafe(|| -> Result<(), String> {
        let mdir = zhiyi::model_dir_path().ok_or("engine not ready")?;
        let schema = read_str(api, l, 1).unwrap_or_default();
        let raw_input = read_str(api, l, 2).unwrap_or_default();
        let ctx = read_str(api, l, 3).unwrap_or_default();
        let cands = read_str_array(api, l, 4);
        let logits = read_f32_array(api, l, 5);
        let gram_deltas = read_f32_array(api, l, 6);
        let char_lps = read_f32_array(api, l, 7);
        let p2c_cand = read_str(api, l, 8).filter(|s| !s.is_empty());
        let shown_top1 = read_str(api, l, 9).unwrap_or_default();
        let chosen_text = read_str(api, l, 10).unwrap_or_default();
        let mut isnum: c_int = 0;
        let chosen_rank = (api.tointegerx)(l, 11, &mut isnum) as i32;
        let reverted = (api.toboolean)(l, 12) != 0;

        let rec = feedback::FeedbackRecord {
            ts: feedback::now_unix_secs(),
            schema: &schema,
            raw_input: &raw_input,
            context: feedback::sanitize_for_log(&ctx),
            cands: &cands,
            logits: &logits,
            gram_deltas: &gram_deltas,
            char_lps: &char_lps,
            p2c_cand: p2c_cand.as_deref(),
            shown_top1: &shown_top1,
            chosen_text: &chosen_text,
            chosen_rank,
            reverted,
        };
        feedback::append_feedback(&mdir.join("feedback.jsonl"), &rec)
    }));
    (api.pushboolean)(l, if matches!(res, Ok(Ok(()))) { 1 } else { 0 });
    1
}

unsafe extern "C" fn lua_stats(l: LuaState) -> c_int {
    let Ok(api) = get_api() else { return 0; };
    let (ready, calls, hits, kv_hits, avg_ms, fused_kv, has_gram) = zhiyi::get_stats();
    (api.createtable)(l, 0, 7);
    (api.pushboolean)(l, if ready { 1 } else { 0 });
    (api.setfield)(l, -2, b"ready\0".as_ptr() as *const c_char);
    (api.pushinteger)(l, calls as LuaInteger);
    (api.setfield)(l, -2, b"calls\0".as_ptr() as *const c_char);
    (api.pushinteger)(l, hits as LuaInteger);
    (api.setfield)(l, -2, b"cache_hits\0".as_ptr() as *const c_char);
    (api.pushinteger)(l, kv_hits as LuaInteger);
    (api.setfield)(l, -2, b"kv_hits\0".as_ptr() as *const c_char);
    (api.pushnumber)(l, avg_ms);
    (api.setfield)(l, -2, b"avg_ms\0".as_ptr() as *const c_char);
    (api.pushboolean)(l, if fused_kv { 1 } else { 0 });
    (api.setfield)(l, -2, b"fused_kv\0".as_ptr() as *const c_char);
    (api.pushboolean)(l, if has_gram { 1 } else { 0 });
    (api.setfield)(l, -2, b"has_gram\0".as_ptr() as *const c_char);
    1
}

#[no_mangle]
pub unsafe extern "C" fn luaopen_rime_zhiyi(l: LuaState) -> c_int {
    lua_api::pin_self_module(luaopen_rime_zhiyi as *const std::ffi::c_void);
    let Ok(api) = get_api() else { return 0; };
    (api.createtable)(l, 0, 6);
    (api.pushcclosure)(l, lua_init, 0);
    (api.setfield)(l, -2, b"init\0".as_ptr() as *const c_char);
    (api.pushcclosure)(l, lua_init_async, 0);
    (api.setfield)(l, -2, b"init_async\0".as_ptr() as *const c_char);
    (api.pushcclosure)(l, lua_is_ready, 0);
    (api.setfield)(l, -2, b"is_ready\0".as_ptr() as *const c_char);
    (api.pushcclosure)(l, lua_rerank, 0);
    (api.setfield)(l, -2, b"rerank\0".as_ptr() as *const c_char);
    (api.pushcclosure)(l, lua_log_feedback, 0);
    (api.setfield)(l, -2, b"log_feedback\0".as_ptr() as *const c_char);
    (api.pushcclosure)(l, lua_stats, 0);
    (api.setfield)(l, -2, b"stats\0".as_ptr() as *const c_char);
    1
}
