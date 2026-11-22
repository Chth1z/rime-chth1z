mod lua_api;
mod pinyin;
mod zhiyi;

use std::ffi::{c_char, c_int};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::path::{Path, PathBuf};

use lua_api::{get_api, pop, push_str, read_str, LuaInteger, LuaState};

unsafe extern "C" fn lua_init(l: LuaState) -> c_int {
    let Ok(api) = get_api() else {
        return 0;
    };
    let res = catch_unwind(AssertUnwindSafe(|| -> Result<(), String> {
        let model_dir = read_str(api, l, 1).ok_or("missing arg 1: model_dir")?;
        let ort_dll = read_str(api, l, 2).ok_or("missing arg 2: ort_dll")?;
        let mut isnum: c_int = 0;
        let threads_raw = (api.tointegerx)(l, 3, &mut isnum);
        let threads = if isnum != 0 && threads_raw > 0 {
            threads_raw as usize
        } else {
            6
        };
        zhiyi::init_engine(Path::new(&model_dir), Path::new(&ort_dll), threads)
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

unsafe extern "C" fn lua_init_async(l: LuaState) -> c_int {
    let Ok(api) = get_api() else {
        return 0;
    };
    let res = catch_unwind(AssertUnwindSafe(|| -> Result<(), String> {
        let model_dir = read_str(api, l, 1).ok_or("missing arg 1: model_dir")?;
        let ort_dll = read_str(api, l, 2).ok_or("missing arg 2: ort_dll")?;
        let mut isnum: c_int = 0;
        let threads_raw = (api.tointegerx)(l, 3, &mut isnum);
        let threads = if isnum != 0 && threads_raw > 0 {
            threads_raw as usize
        } else {
            6
        };
        zhiyi::init_engine_async(PathBuf::from(model_dir), PathBuf::from(ort_dll), threads);
        Ok(())
    }));
    match res {
        Ok(Ok(())) => {
            (api.pushboolean)(l, 1);
            1
        }
        _ => {
            (api.pushboolean)(l, 0);
            1
        }
    }
}

unsafe extern "C" fn lua_is_ready(l: LuaState) -> c_int {
    let Ok(api) = get_api() else {
        return 0;
    };
    (api.pushboolean)(l, if zhiyi::is_ready() { 1 } else { 0 });
    1
}

unsafe extern "C" fn lua_rerank(l: LuaState) -> c_int {
    let Ok(api) = get_api() else {
        return 0;
    };
    let res = catch_unwind(AssertUnwindSafe(|| -> Result<Vec<usize>, String> {
        if !zhiyi::is_ready() {
            return Err("not ready".to_string());
        }
        let ctx = read_str(api, l, 1).unwrap_or_default();
        let raw_input = read_str(api, l, 2).unwrap_or_default();
        let is_dp = (api.toboolean)(l, 3) != 0;

        let n = (api.rawlen)(l, 4);
        let mut cands = Vec::with_capacity(n);
        for i in 1..=(n as LuaInteger) {
            (api.rawgeti)(l, 4, i);
            if let Some(s) = read_str(api, l, -1) {
                cands.push(s);
            }
            pop(api, l, 1);
        }

        let mut isnum: c_int = 0;
        let rp = (api.tonumberx)(l, 5, &mut isnum);
        let rank_penalty = if isnum != 0 { rp } else { 1.4 };

        zhiyi::rerank_indices(&ctx, &raw_input, is_dp, &cands, rank_penalty)
    }));

    match res {
        Ok(Ok(order)) => {
            (api.createtable)(l, order.len() as c_int, 0);
            for (i, idx) in order.into_iter().enumerate() {
                (api.pushinteger)(l, idx as LuaInteger);
                (api.rawseti)(l, -2, (i + 1) as LuaInteger);
            }
            1
        }
        _ => {
            (api.pushnil)(l);
            1
        }
    }
}

unsafe extern "C" fn lua_stats(l: LuaState) -> c_int {
    let Ok(api) = get_api() else {
        return 0;
    };
    let (ready, calls, hits, avg_ms) = zhiyi::get_stats();
    (api.createtable)(l, 0, 4);
    (api.pushboolean)(l, if ready { 1 } else { 0 });
    (api.setfield)(l, -2, b"ready\0".as_ptr() as *const c_char);
    (api.pushinteger)(l, calls as LuaInteger);
    (api.setfield)(l, -2, b"calls\0".as_ptr() as *const c_char);
    (api.pushinteger)(l, hits as LuaInteger);
    (api.setfield)(l, -2, b"cache_hits\0".as_ptr() as *const c_char);
    (api.pushnumber)(l, avg_ms);
    (api.setfield)(l, -2, b"avg_ms\0".as_ptr() as *const c_char);
    1
}

#[no_mangle]
pub unsafe extern "C" fn luaopen_rime_zhiyi(l: LuaState) -> c_int {
    lua_api::pin_self_module(luaopen_rime_zhiyi as *const std::ffi::c_void);
    let Ok(api) = get_api() else {
        return 0;
    };
    (api.createtable)(l, 0, 5);
    (api.pushcclosure)(l, lua_init, 0);
    (api.setfield)(l, -2, b"init\0".as_ptr() as *const c_char);
    (api.pushcclosure)(l, lua_init_async, 0);
    (api.setfield)(l, -2, b"init_async\0".as_ptr() as *const c_char);
    (api.pushcclosure)(l, lua_is_ready, 0);
    (api.setfield)(l, -2, b"is_ready\0".as_ptr() as *const c_char);
    (api.pushcclosure)(l, lua_rerank, 0);
    (api.setfield)(l, -2, b"rerank\0".as_ptr() as *const c_char);
    (api.pushcclosure)(l, lua_stats, 0);
    (api.setfield)(l, -2, b"stats\0".as_ptr() as *const c_char);
    1
}
