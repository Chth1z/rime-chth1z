use std::collections::{HashMap, HashSet, VecDeque};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Mutex, OnceLock};
use std::time::Instant;

use ort::environment::Environment;
use ort::session::{builder::GraphOptimizationLevel, Session};
use ort::value::{Tensor, TensorRef};
use serde::Deserialize;
use tokenizers::Tokenizer;

use crate::gram::WanxiangGram;
use crate::pinyin::{input_to_units, PinyinLayout};

const CONTEXT_CHARS: usize = 128;
const LRU_CAPACITY: usize = 256;
const KV_CACHE_CAPACITY: usize = 16;

#[derive(Deserialize)]
struct MlSubConfig {
    #[serde(default = "default_old_chars")]
    old_chars: usize,
    #[serde(default)]
    pinyin: HashMap<String, Vec<String>>,
}

fn default_old_chars() -> usize {
    6163
}

#[derive(Deserialize)]
struct UnifiedVocabFile {
    units: Vec<String>,
    #[serde(default)]
    chars: Vec<String>,
    readings: HashMap<String, Vec<String>>,
    #[serde(default = "default_max_slots")]
    max_slots: usize,
    #[serde(default = "default_ctx_tokens")]
    choice_context_tokens: usize,
    #[serde(default = "default_cand_tokens")]
    choice_candidate_tokens: usize,
    #[serde(default)]
    ml: Option<MlSubConfig>,
}

fn default_max_slots() -> usize {
    24
}
fn default_ctx_tokens() -> usize {
    128
}
fn default_cand_tokens() -> usize {
    16
}

#[derive(Clone, Copy)]
pub struct FusionWeights {
    pub w_logit: f64,
    pub w_rank: f64,
    pub w_gram: f64,
    pub w_char_lp: f64,
    pub w_ctx_lp: f64,
}

impl Default for FusionWeights {
    fn default() -> Self {
        Self {
            w_logit: 1.0,
            w_rank: -1.4,
            w_gram: 0.05,
            w_char_lp: 0.15,
            w_ctx_lp: 0.0,
        }
    }
}

#[derive(Clone, Copy)]
pub struct P2cConfig {
    /// Minimum Pass-1 `char_logits` margin to trigger KV-cached Pass-2 cross-encoder check (<= 0 disables Pass-2).
    pub verify_margin: f32,
    /// Minimum Pass-2 cross-encoder logit lead over Rime's best candidate to promote P2C to #1.
    pub top1_logit_diff: f32,
    /// Minimum Wanxiang `.gram` per-char score delta floor to allow #1 promotion.
    pub top1_min_gram_diff: f32,
    /// Minimum Pass-2 cross-encoder logit lead to insert P2C safely at #2.
    pub top2_logit_diff: f32,
    /// Legacy Pass-1-only fallback margins (used only when running non-KV graph or Pass-2 disabled).
    pub legacy_top1_margin: f32,
    pub legacy_top2_margin: f32,
}

impl Default for P2cConfig {
    fn default() -> Self {
        Self {
            verify_margin: 0.20,
            top1_logit_diff: 2.0,
            top1_min_gram_diff: -2.0,
            top2_logit_diff: 0.5,
            legacy_top1_margin: 1.0,
            legacy_top2_margin: 0.45,
        }
    }
}

#[derive(Clone)]
pub struct RerankResult {
    pub order: Vec<usize>,
    pub p2c_text: Option<String>,
    pub p2c_pos: u8, // 0 = none, 1 = top-1, 2 = top-2
    pub logits: Vec<f32>,
    pub gram_deltas: Vec<f32>,
    pub char_lps: Vec<f32>,
}

#[derive(Clone)]
struct CachedEval {
    logits: Vec<f32>,
    gram_deltas: Vec<f32>,
    char_lps: Vec<f32>,
    p2c_text: Option<String>,
    p2c_margin: f32,
    p2c_verified: Option<(f32, f32)>,
}

#[derive(Hash, PartialEq, Eq, Clone)]
struct CacheKey {
    ctx_tail: String,
    raw_input: String,
    layout: PinyinLayout,
    cands: Vec<String>,
}

struct ContextKv {
    p: usize,
    enc_k: Vec<f32>,
    enc_v: Vec<f32>,
    choice_k: Vec<f32>,
    choice_v: Vec<f32>,
    mask: Vec<bool>,
}

pub struct ZhiyiStats {
    pub calls: u64,
    pub cache_hits: u64,
    pub kv_hits: u64,
    pub p2c_pass2_calls: u64,
    pub total_infer_ms: f64,
    pub fused_kv: bool,
    pub has_gram: bool,
}

pub struct ZhiyiEngine {
    model_dir: PathBuf,
    session: Session,
    use_fused_kv: bool,
    tokenizer: Tokenizer,
    unit_ids: HashMap<String, i64>,
    chars: Vec<String>,
    char_to_id: HashMap<char, usize>,
    syl_to_cids: HashMap<String, Vec<usize>>,
    old_chars: usize,
    readings: HashMap<String, Vec<String>>,
    valid_syllables: HashSet<String>,
    max_slots: usize,
    context_tokens: usize,
    candidate_tokens: usize,
    cls_id: i64,
    sep_id: i64,
    mask_id: i64,
    gram: Option<WanxiangGram>,
    kv_cache: VecDeque<(String, ContextKv)>,
    lru_map: HashMap<CacheKey, CachedEval>,
    lru_order: VecDeque<CacheKey>,
    pub stats: ZhiyiStats,
}

static ORT_ENV: OnceLock<Result<Environment, String>> = OnceLock::new();
static ENGINE: OnceLock<Mutex<ZhiyiEngine>> = OnceLock::new();
static ASYNC_STARTED: AtomicBool = AtomicBool::new(false);

fn ensure_ort_env(ort_dll: &Path) -> Result<&'static Environment, String> {
    ORT_ENV
        .get_or_init(|| {
            ort::init_from(ort_dll)
                .map_err(|e| format!("ort::init_from({}) failed: {}", ort_dll.display(), e))?
                .with_name("rime_zhiyi")
                .with_telemetry(false)
                .build()
                .map_err(|e| format!("ort env build failed: {}", e))
        })
        .as_ref()
        .map_err(|e| e.clone())
}

pub fn init_engine(
    model_dir: &Path,
    ort_dll: &Path,
    gram_path: Option<&Path>,
    threads: usize,
) -> Result<(), String> {
    if let Some(m) = ENGINE.get() {
        let g = m.lock().map_err(|_| "engine mutex poisoned".to_string())?;
        if g.model_dir == model_dir {
            return Ok(());
        }
        return Ok(());
    }

    let ort_env = ensure_ort_env(ort_dll)?;

    // Prefer fused KV-cache graph (ML-pumpkin-1103) when present; fallback to whole graph
    let fused_path = model_dir.join("laya.one.fused.int8g.onnx");
    let kv_path = model_dir.join("laya.one.int8g.onnx");
    let whole_path = model_dir.join("laya.int8g.onnx");
    let (onnx_path, use_fused_kv) = if fused_path.is_file() {
        (fused_path, true)
    } else if kv_path.is_file() {
        (kv_path, true)
    } else {
        (whole_path, false)
    };

    let tok_path = model_dir.join("tokenizer.json");
    let vocab_path = model_dir.join("unified_vocab.json");

    let vocab_raw = std::fs::read_to_string(&vocab_path)
        .map_err(|e| format!("read {}: {}", vocab_path.display(), e))?;
    let uv: UnifiedVocabFile = serde_json::from_str(&vocab_raw)
        .map_err(|e| format!("parse {}: {}", vocab_path.display(), e))?;

    let mut unit_ids = HashMap::with_capacity(uv.units.len());
    let mut valid_syllables = HashSet::new();
    for (idx, name) in uv.units.into_iter().enumerate() {
        if let Some(syl) = name.strip_prefix("f:") {
            valid_syllables.insert(syl.to_string());
        }
        unit_ids.insert(name, idx as i64);
    }

    let mut char_to_id: HashMap<char, usize> = HashMap::with_capacity(uv.chars.len());
    for (idx, s) in uv.chars.iter().enumerate() {
        if let Some(ch) = s.chars().next() {
            if s.chars().count() == 1 {
                char_to_id.insert(ch, idx);
            }
        }
    }

    let old_chars = uv
        .ml
        .as_ref()
        .map(|m| m.old_chars)
        .unwrap_or(uv.chars.len())
        .min(uv.chars.len());
    let pinyin_src = uv
        .ml
        .as_ref()
        .filter(|m| !m.pinyin.is_empty())
        .map(|m| &m.pinyin)
        .unwrap_or(&uv.readings);

    let mut syl_to_cids: HashMap<String, Vec<usize>> = HashMap::with_capacity(450);
    for (ch_str, rlist) in pinyin_src {
        if let Some(ch) = ch_str.chars().next() {
            if let Some(&cid) = char_to_id.get(&ch) {
                if cid < old_chars {
                    for syl in rlist {
                        syl_to_cids.entry(syl.clone()).or_default().push(cid);
                    }
                }
            }
        }
    }

    let tokenizer = Tokenizer::from_file(&tok_path)
        .map_err(|e| format!("load {}: {}", tok_path.display(), e))?;
    let cls_id = tokenizer
        .token_to_id("<bos>")
        .ok_or_else(|| "missing <bos> token".to_string())? as i64;
    let sep_id = tokenizer
        .token_to_id("<eos>")
        .ok_or_else(|| "missing <eos> token".to_string())? as i64;
    let mask_id = tokenizer
        .token_to_id("<mask>")
        .ok_or_else(|| "missing <mask> token".to_string())? as i64;

    let threads = threads.clamp(1, 16);
    let session = Session::builder(ort_env)
        .map_err(|e| format!("session builder: {}", e))?
        .with_optimization_level(GraphOptimizationLevel::Level3)
        .map_err(|e| format!("opt level: {}", e))?
        .with_intra_threads(threads)
        .map_err(|e| format!("intra threads: {}", e))?
        .with_inter_threads(1)
        .map_err(|e| format!("inter threads: {}", e))?
        .commit_from_file(&onnx_path)
        .map_err(|e| format!("load {}: {}", onnx_path.display(), e))?;

    let gram = gram_path.and_then(|gp| {
        if gp.is_file() {
            WanxiangGram::open(gp, -15.5, -4.0).ok()
        } else {
            None
        }
    });
    let has_gram = gram.is_some();

    let mut engine = ZhiyiEngine {
        model_dir: model_dir.to_path_buf(),
        session,
        use_fused_kv,
        tokenizer,
        unit_ids,
        chars: uv.chars,
        char_to_id,
        syl_to_cids,
        old_chars,
        readings: uv.readings,
        valid_syllables,
        max_slots: uv.max_slots,
        context_tokens: uv.choice_context_tokens,
        candidate_tokens: uv.choice_candidate_tokens,
        cls_id,
        sep_id,
        mask_id,
        gram,
        kv_cache: VecDeque::with_capacity(KV_CACHE_CAPACITY + 2),
        lru_map: HashMap::with_capacity(LRU_CAPACITY + 16),
        lru_order: VecDeque::with_capacity(LRU_CAPACITY + 16),
        stats: ZhiyiStats {
            calls: 0,
            cache_hits: 0,
            kv_hits: 0,
            p2c_pass2_calls: 0,
            total_infer_ms: 0.0,
            fused_kv: use_fused_kv,
            has_gram,
        },
    };

    // Single untimed warmup pass (also pre-populates empty-context KV cache!)
    let warmup_cands = vec!["你好".to_string(), "拟好".to_string()];
    let _ = engine.evaluate(
        "",
        "nihk",
        PinyinLayout::Zrm,
        &warmup_cands,
        FusionWeights::default(),
        0.0,
    );
    engine.lru_map.clear();
    engine.lru_order.clear();
    engine.stats.calls = 0;
    engine.stats.cache_hits = 0;
    engine.stats.kv_hits = 0;
    engine.stats.p2c_pass2_calls = 0;
    engine.stats.total_infer_ms = 0.0;

    let _ = ENGINE.set(Mutex::new(engine));
    Ok(())
}

pub fn init_engine_async(
    model_dir: PathBuf,
    ort_dll: PathBuf,
    gram_path: Option<PathBuf>,
    threads: usize,
) {
    if ENGINE.get().is_some() {
        return;
    }
    if ASYNC_STARTED.swap(true, Ordering::AcqRel) {
        return;
    }
    let _ = std::thread::Builder::new()
        .name("rime-zhiyi-init".to_string())
        .spawn(move || {
            if init_engine(&model_dir, &ort_dll, gram_path.as_deref(), threads).is_err() {
                ASYNC_STARTED.store(false, Ordering::Release);
            }
        });
}

pub fn is_ready() -> bool {
    ENGINE.get().is_some()
}

pub fn model_dir_path() -> Option<PathBuf> {
    let mutex = ENGINE.get()?;
    let eng = mutex.lock().ok()?;
    Some(eng.model_dir.clone())
}

fn utf8_tail(s: &str, max_chars: usize) -> &str {
    let total = s.chars().count();
    if total <= max_chars {
        return s;
    }
    let skip = total - max_chars;
    match s.char_indices().nth(skip) {
        Some((byte_idx, _)) => &s[byte_idx..],
        None => s,
    }
}

fn common_prefix_chars(cands: &[String]) -> usize {
    if cands.is_empty() {
        return 0;
    }
    let first: Vec<char> = cands[0].chars().collect();
    let mut lcp = first.len();
    for c in &cands[1..] {
        let mut matched = 0;
        for (a, b) in first.iter().zip(c.chars()) {
            if *a == b {
                matched += 1;
            } else {
                break;
            }
        }
        lcp = lcp.min(matched);
        if lcp == 0 {
            break;
        }
    }
    let min_len = cands.iter().map(|s| s.chars().count()).min().unwrap_or(0);
    if lcp >= min_len {
        0
    } else {
        lcp
    }
}

fn rank_order_from_features(
    logits: &[f32],
    gram_deltas: &[f32],
    char_lps: &[f32],
    has_ctx: f64,
    weights: FusionWeights,
) -> Vec<usize> {
    let max_l = logits.iter().copied().fold(f32::NEG_INFINITY, f32::max) as f64;
    let sum_exp: f64 = logits.iter().map(|&x| ((x as f64) - max_l).exp()).sum();
    let lse = max_l + sum_exp.ln();

    let mut scored: Vec<(usize, f64)> = logits
        .iter()
        .enumerate()
        .map(|(i, &x)| {
            let lp = (x as f64) - lse;
            let score = weights.w_logit * lp
                + weights.w_rank * ((i as f64) + 1.0).ln()
                + weights.w_gram * (gram_deltas[i] as f64)
                + weights.w_char_lp * (char_lps[i] as f64)
                + weights.w_ctx_lp * lp * has_ctx;
            (i, score)
        })
        .collect();
    scored.sort_by(|a, b| b.1.total_cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    scored.into_iter().map(|(idx, _)| idx).collect()
}

impl ZhiyiEngine {
    fn encode_ids(&self, text: &str) -> Vec<i64> {
        let cleaned = if text.contains("<mask>") {
            text.replace("<mask>", " ")
        } else {
            text.to_string()
        };
        match self.tokenizer.encode(cleaned, false) {
            Ok(enc) => enc.get_ids().iter().map(|&x| x as i64).collect(),
            Err(_) => Vec::new(),
        }
    }

    fn compute_context_kv(&mut self, ctx_final: &str) -> Result<ContextKv, String> {
        let mut ids: Vec<i64> = Vec::with_capacity(self.context_tokens + 2);
        ids.push(self.cls_id);
        if !ctx_final.is_empty() {
            let cids = self.encode_ids(ctx_final);
            let start = cids.len().saturating_sub(self.context_tokens);
            ids.extend_from_slice(&cids[start..]);
        }
        ids.push(self.sep_id);
        let p = ids.len();
        let uids = vec![0i64; p];

        let z_enc = vec![0.0f32; 12 * 6 * 64];
        let z_ch = vec![0.0f32; 2 * 6 * 64];

        let t_ids =
            Tensor::from_array(([1usize, p], ids)).map_err(|e| format!("ctx ids: {}", e))?;
        let t_uid =
            Tensor::from_array(([1usize, p], uids)).map_err(|e| format!("ctx uid: {}", e))?;
        let t_ek = TensorRef::from_array_view(([12usize, 1, 6, 1, 64], z_enc.as_slice()))
            .map_err(|e| format!("ek: {}", e))?;
        let t_ev = TensorRef::from_array_view(([12usize, 1, 6, 1, 64], z_enc.as_slice()))
            .map_err(|e| format!("ev: {}", e))?;
        let t_ck = TensorRef::from_array_view(([2usize, 1, 6, 1, 64], z_ch.as_slice()))
            .map_err(|e| format!("ck: {}", e))?;
        let t_cv = TensorRef::from_array_view(([2usize, 1, 6, 1, 64], z_ch.as_slice()))
            .map_err(|e| format!("cv: {}", e))?;
        let t_pm =
            Tensor::from_array(([1usize, 1], vec![false])).map_err(|e| format!("pm: {}", e))?;
        let t_mp =
            Tensor::from_array(([1usize, 1], vec![0i64])).map_err(|e| format!("mp: {}", e))?;
        let t_sp =
            Tensor::from_array(([1usize, 1], vec![0i64])).map_err(|e| format!("sp: {}", e))?;

        let t0 = Instant::now();
        let outputs = self
            .session
            .run(ort::inputs![
                "input_ids" => t_ids,
                "unit_ids" => t_uid,
                "past_enc_k" => t_ek,
                "past_enc_v" => t_ev,
                "past_choice_k" => t_ck,
                "past_choice_v" => t_cv,
                "past_mask" => t_pm,
                "marker_pos" => t_mp,
                "slot_pos" => t_sp,
            ])
            .map_err(|e| format!("ctx run: {}", e))?;
        self.stats.total_infer_ms += t0.elapsed().as_secs_f64() * 1000.0;

        let (_, ek) = outputs["present_enc_k"]
            .try_extract_tensor::<f32>()
            .map_err(|e| format!("out ek: {}", e))?;
        let (_, ev) = outputs["present_enc_v"]
            .try_extract_tensor::<f32>()
            .map_err(|e| format!("out ev: {}", e))?;
        let (_, ck) = outputs["present_choice_k"]
            .try_extract_tensor::<f32>()
            .map_err(|e| format!("out ck: {}", e))?;
        let (_, cv) = outputs["present_choice_v"]
            .try_extract_tensor::<f32>()
            .map_err(|e| format!("out cv: {}", e))?;

        Ok(ContextKv {
            p,
            enc_k: ek.to_vec(),
            enc_v: ev.to_vec(),
            choice_k: ck.to_vec(),
            choice_v: cv.to_vec(),
            mask: vec![true; p],
        })
    }

    fn get_or_compute_kv_index(&mut self, ctx_final: &str) -> Result<usize, String> {
        if let Some(pos) = self.kv_cache.iter().position(|(k, _)| k == ctx_final) {
            self.stats.kv_hits += 1;
            return Ok(pos);
        }
        let kv = self.compute_context_kv(ctx_final)?;
        if self.kv_cache.len() >= KV_CACHE_CAPACITY {
            // Keep empty context pinned if it's at front; evict oldest non-empty
            if let Some(evict) = self.kv_cache.iter().position(|(k, _)| !k.is_empty()) {
                self.kv_cache.remove(evict);
            } else {
                self.kv_cache.pop_front();
            }
        }
        self.kv_cache.push_back((ctx_final.to_string(), kv));
        Ok(self.kv_cache.len() - 1)
    }

    fn evaluate(
        &mut self,
        context: &str,
        raw_input: &str,
        layout: PinyinLayout,
        cands: &[String],
        weights: FusionWeights,
        p2c_verify_margin: f32,
    ) -> Result<CachedEval, String> {
        self.stats.calls += 1;
        let ctx_tail = utf8_tail(context, CONTEXT_CHARS);
        let key = CacheKey {
            ctx_tail: ctx_tail.to_string(),
            raw_input: raw_input.to_string(),
            layout,
            cands: cands.to_vec(),
        };
        if let Some(cached) = self.lru_map.get(&key) {
            self.stats.cache_hits += 1;
            return Ok(cached.clone());
        }

        let mut units = input_to_units(
            layout,
            raw_input,
            &cands[0],
            &self.readings,
            &self.valid_syllables,
        );
        let orig_units_len = units.len();

        let mut cand_toks: Vec<Vec<i64>> = cands
            .iter()
            .map(|c| {
                let mut s = String::with_capacity(c.len() + 1);
                s.push(' ');
                s.push_str(c);
                self.encode_ids(&s)
            })
            .collect();

        let mut eff_ctx = ctx_tail.to_string();
        let mut shifted_lcp = false;
        if cand_toks.iter().any(|t| t.len() > self.candidate_tokens) {
            let lcp = common_prefix_chars(cands);
            if lcp > 0 {
                shifted_lcp = true;
                let prefix_str: String = cands[0].chars().take(lcp).collect();
                eff_ctx.push_str(&prefix_str);
                cand_toks = cands
                    .iter()
                    .map(|c| {
                        let tail: String = c.chars().skip(lcp).collect();
                        let mut s = String::with_capacity(tail.len() + 1);
                        s.push(' ');
                        s.push_str(&tail);
                        self.encode_ids(&s)
                    })
                    .collect();
                if lcp < units.len() {
                    units = units.split_off(lcp);
                }
            }
        }

        let ctx_final = utf8_tail(&eff_ctx, CONTEXT_CHARS).to_string();
        let (logits, char_logits, n_slots, vocab_chars) = if self.use_fused_kv {
            self.run_fused_kv(&ctx_final, &units, &cand_toks)?
        } else {
            self.run_whole_graph(&ctx_final, &units, &cand_toks)?
        };

        // Compute exact Wanxiang .gram deltas (0.01 ms, 0 MB extra RAM)
        let gram_deltas: Vec<f32> = if let Some(ref g) = self.gram {
            let raw_g: Vec<f64> = cands.iter().map(|c| g.score_sentence_per_char(c)).collect();
            let g0 = raw_g.first().copied().unwrap_or(0.0);
            raw_g.into_iter().map(|x| (x - g0) as f32).collect()
        } else {
            vec![0.0f32; cands.len()]
        };

        // Decode char_logits head (0.00 ms extra inference!) for both candidate scoring & P2C synthesis
        let mut char_lps = vec![0.0f32; cands.len()];
        let mut p2c_text: Option<String> = None;
        let mut p2c_margin: f32 = -100.0;

        let can_decode_p2c = !shifted_lcp
            && orig_units_len > 0
            && orig_units_len <= self.max_slots
            && n_slots == orig_units_len
            && vocab_chars >= self.old_chars
            && !self.chars.is_empty();

        if can_decode_p2c {
            let mut gen_chars: Vec<char> = Vec::with_capacity(n_slots);
            let mut slot_lps: Vec<HashMap<usize, f32>> = Vec::with_capacity(n_slots);
            let mut gen_sum = 0.0f32;
            let mut all_full = true;

            for (j, (kind, syl)) in units.iter().enumerate() {
                if *kind != "f" {
                    all_full = false;
                }
                let row = &char_logits[j * vocab_chars..(j + 1) * vocab_chars];
                if let Some(allowed) = self.syl_to_cids.get(syl) {
                    let mut max_v = f32::NEG_INFINITY;
                    let mut best_cid = allowed[0];
                    for &cid in allowed {
                        let v = row[cid];
                        if v > max_v {
                            max_v = v;
                            best_cid = cid;
                        }
                    }
                    let sum_e: f32 = allowed.iter().map(|&cid| (row[cid] - max_v).exp()).sum();
                    let lse = max_v + sum_e.ln();
                    let mut map = HashMap::with_capacity(allowed.len());
                    for &cid in allowed {
                        map.insert(cid, row[cid] - lse);
                    }
                    gen_sum += max_v - lse;
                    if let Some(ch) = self.chars[best_cid].chars().next() {
                        gen_chars.push(ch);
                    }
                    slot_lps.push(map);
                } else {
                    all_full = false;
                    slot_lps.push(HashMap::new());
                }
            }

            if all_full && gen_chars.len() == n_slots {
                let mut raw_clp = Vec::with_capacity(cands.len());
                for c in cands {
                    let mut s = 0.0f32;
                    let mut cnt = 0usize;
                    for (j, ch) in c.chars().take(n_slots).enumerate() {
                        cnt += 1;
                        let lp = self
                            .char_to_id
                            .get(&ch)
                            .and_then(|cid| slot_lps[j].get(cid))
                            .copied()
                            .unwrap_or(-15.0);
                        s += lp;
                    }
                    if cnt < n_slots {
                        s += -15.0 * ((n_slots - cnt) as f32);
                    }
                    raw_clp.push(s / (n_slots as f32));
                }
                let c0 = raw_clp[0];
                let max_cand_clp = raw_clp.iter().copied().fold(f32::NEG_INFINITY, f32::max);
                for (i, &v) in raw_clp.iter().enumerate() {
                    char_lps[i] = v - c0;
                }
                let gen_str: String = gen_chars.into_iter().collect();
                let gen_mean = gen_sum / (n_slots as f32);
                if !cands.iter().any(|c| c == &gen_str) {
                    p2c_margin = gen_mean - max_cand_clp;
                    p2c_text = Some(gen_str);
                }
            }
        }

        // Optional KV-cached Pass-2 Cross-Encoder + .gram verification of promising novel P2C candidates
        // Triggers on only ~6-7% of sentences; reuses warm prefix KV-cache (~4-5 ms on AC, ~0.3 ms amortized).
        let mut p2c_verified: Option<(f32, f32)> = None;
        if self.use_fused_kv && p2c_verify_margin > 0.0 && p2c_margin > p2c_verify_margin {
            if let Some(ref p2c_str) = p2c_text {
                let has_ctx_f = if context.trim().chars().count() >= 2 {
                    1.0
                } else {
                    0.0
                };
                let rank0 =
                    rank_order_from_features(&logits, &gram_deltas, &char_lps, has_ctx_f, weights);
                let best_idx = rank0[0];
                let mut probe_cands: Vec<&str> = Vec::with_capacity(3);
                probe_cands.push(cands[best_idx].as_str());
                if rank0.len() >= 2 {
                    probe_cands.push(cands[rank0[1]].as_str());
                }
                probe_cands.push(p2c_str.as_str());
                let probe_toks: Vec<Vec<i64>> = probe_cands
                    .iter()
                    .map(|c| {
                        let mut s = String::with_capacity(c.len() + 1);
                        s.push(' ');
                        s.push_str(c);
                        self.encode_ids(&s)
                    })
                    .collect();

                if let Ok((l2, _, _, _)) = self.run_fused_kv(&ctx_final, &units, &probe_toks) {
                    if let (Some(&l_best), Some(&l_p2c)) = (l2.first(), l2.last()) {
                        self.stats.p2c_pass2_calls += 1;
                        let gdiff = if let Some(ref g) = self.gram {
                            (g.score_sentence_per_char(p2c_str)
                                - g.score_sentence_per_char(&cands[best_idx]))
                                as f32
                        } else {
                            0.0
                        };
                        p2c_verified = Some((l_p2c - l_best, gdiff));
                    }
                }
            }
        }

        let res = CachedEval {
            logits,
            gram_deltas,
            char_lps,
            p2c_text,
            p2c_margin,
            p2c_verified,
        };

        if self.lru_map.len() >= LRU_CAPACITY {
            if let Some(old) = self.lru_order.pop_front() {
                self.lru_map.remove(&old);
            }
        }
        self.lru_order.push_back(key.clone());
        self.lru_map.insert(key, res.clone());
        Ok(res)
    }

    fn run_fused_kv(
        &mut self,
        ctx_final: &str,
        units: &[(&'static str, String)],
        cand_toks: &[Vec<i64>],
    ) -> Result<(Vec<f32>, Vec<f32>, usize, usize), String> {
        let kv_idx = self.get_or_compute_kv_index(ctx_final)?;

        let mut ids: Vec<i64> = Vec::with_capacity(192);
        let mut uids: Vec<i64> = Vec::with_capacity(192);
        let mut slots: Vec<i64> = Vec::with_capacity(self.max_slots);
        for (kind, text) in units.iter().take(self.max_slots) {
            slots.push(ids.len() as i64);
            ids.push(self.mask_id);
            let k = format!("{}:{}", kind, text);
            uids.push(*self.unit_ids.get(&k).unwrap_or(&0));
        }
        ids.push(self.sep_id);
        uids.push(0);

        let mut markers: Vec<i64> = Vec::with_capacity(cand_toks.len());
        for ctok in cand_toks {
            markers.push(ids.len() as i64);
            ids.push(self.mask_id);
            uids.push(0);
            let take = ctok.len().min(self.candidate_tokens);
            ids.extend_from_slice(&ctok[..take]);
            uids.resize(ids.len(), 0);
        }
        ids.push(self.sep_id);
        uids.push(0);

        let seq_len = ids.len();
        let n_markers = markers.len();
        let real_slots = slots.len();
        if slots.is_empty() {
            slots.push(0);
        }
        let n_slots_in = slots.len();

        let kv = &self.kv_cache[kv_idx].1;
        let t_ids =
            Tensor::from_array(([1usize, seq_len], ids)).map_err(|e| format!("ids: {}", e))?;
        let t_uid =
            Tensor::from_array(([1usize, seq_len], uids)).map_err(|e| format!("uid: {}", e))?;
        let t_ek = TensorRef::from_array_view(([12usize, 1, 6, kv.p, 64], kv.enc_k.as_slice()))
            .map_err(|e| format!("ek: {}", e))?;
        let t_ev = TensorRef::from_array_view(([12usize, 1, 6, kv.p, 64], kv.enc_v.as_slice()))
            .map_err(|e| format!("ev: {}", e))?;
        let t_ck = TensorRef::from_array_view(([2usize, 1, 6, kv.p, 64], kv.choice_k.as_slice()))
            .map_err(|e| format!("ck: {}", e))?;
        let t_cv = TensorRef::from_array_view(([2usize, 1, 6, kv.p, 64], kv.choice_v.as_slice()))
            .map_err(|e| format!("cv: {}", e))?;
        let t_pm = TensorRef::from_array_view(([1usize, kv.p], kv.mask.as_slice()))
            .map_err(|e| format!("pm: {}", e))?;
        let t_mp =
            Tensor::from_array(([1usize, n_markers], markers)).map_err(|e| format!("mp: {}", e))?;
        let t_sp =
            Tensor::from_array(([1usize, n_slots_in], slots)).map_err(|e| format!("sp: {}", e))?;

        let t0 = Instant::now();
        let outputs = self
            .session
            .run(ort::inputs![
                "input_ids" => t_ids,
                "unit_ids" => t_uid,
                "past_enc_k" => t_ek,
                "past_enc_v" => t_ev,
                "past_choice_k" => t_ck,
                "past_choice_v" => t_cv,
                "past_mask" => t_pm,
                "marker_pos" => t_mp,
                "slot_pos" => t_sp,
            ])
            .map_err(|e| format!("key run: {}", e))?;
        self.stats.total_infer_ms += t0.elapsed().as_secs_f64() * 1000.0;

        let (_, l_slice) = outputs["logits"]
            .try_extract_tensor::<f32>()
            .map_err(|e| format!("logits: {}", e))?;
        let logits: Vec<f32> = l_slice.iter().take(n_markers).copied().collect();

        let (c_shape, c_slice) = outputs["char_logits"]
            .try_extract_tensor::<f32>()
            .map_err(|e| format!("char_logits: {}", e))?;
        let vocab_chars = c_shape.last().copied().unwrap_or(0) as usize;
        let cl = c_slice
            .iter()
            .take(real_slots * vocab_chars)
            .copied()
            .collect();
        Ok((logits, cl, real_slots, vocab_chars))
    }

    fn run_whole_graph(
        &mut self,
        ctx_final: &str,
        units: &[(&'static str, String)],
        cand_toks: &[Vec<i64>],
    ) -> Result<(Vec<f32>, Vec<f32>, usize, usize), String> {
        let mut ids: Vec<i64> = Vec::with_capacity(256);
        ids.push(self.cls_id);
        if !ctx_final.is_empty() {
            let cids = self.encode_ids(ctx_final);
            let start = cids.len().saturating_sub(self.context_tokens);
            ids.extend_from_slice(&cids[start..]);
        }
        ids.push(self.sep_id);

        let mut uids: Vec<i64> = vec![0; ids.len()];
        let mut slots: Vec<i64> = Vec::with_capacity(self.max_slots);
        for (kind, text) in units.iter().take(self.max_slots) {
            slots.push(ids.len() as i64);
            ids.push(self.mask_id);
            let k = format!("{}:{}", kind, text);
            uids.push(*self.unit_ids.get(&k).unwrap_or(&0));
        }
        ids.push(self.sep_id);
        uids.push(0);

        let mut markers: Vec<i64> = Vec::with_capacity(cand_toks.len());
        for ctok in cand_toks {
            markers.push(ids.len() as i64);
            ids.push(self.mask_id);
            let take = ctok.len().min(self.candidate_tokens);
            ids.extend_from_slice(&ctok[..take]);
        }
        ids.push(self.sep_id);
        uids.resize(ids.len(), 0);

        let seq_len = ids.len();
        let n_markers = markers.len();
        let real_slots = slots.len();
        if slots.is_empty() {
            slots.push(0);
        }
        let n_slots_in = slots.len();

        let t_ids =
            Tensor::from_array(([1usize, seq_len], ids)).map_err(|e| format!("ids: {}", e))?;
        let t_att = Tensor::from_array(([1usize, seq_len], vec![1i64; seq_len]))
            .map_err(|e| format!("att: {}", e))?;
        let t_uid =
            Tensor::from_array(([1usize, seq_len], uids)).map_err(|e| format!("uid: {}", e))?;
        let t_mp =
            Tensor::from_array(([1usize, n_markers], markers)).map_err(|e| format!("mp: {}", e))?;
        let t_mm = Tensor::from_array(([1usize, n_markers], vec![true; n_markers]))
            .map_err(|e| format!("mm: {}", e))?;
        let t_sp =
            Tensor::from_array(([1usize, n_slots_in], slots)).map_err(|e| format!("sp: {}", e))?;

        let t0 = Instant::now();
        let outputs = self
            .session
            .run(ort::inputs![
                "input_ids" => t_ids,
                "attention_mask" => t_att,
                "unit_ids" => t_uid,
                "marker_pos" => t_mp,
                "marker_mask" => t_mm,
                "slot_pos" => t_sp,
            ])
            .map_err(|e| format!("whole run: {}", e))?;
        self.stats.total_infer_ms += t0.elapsed().as_secs_f64() * 1000.0;

        let (_, l_slice) = outputs["logits"]
            .try_extract_tensor::<f32>()
            .map_err(|e| format!("logits: {}", e))?;
        let logits: Vec<f32> = l_slice.iter().take(n_markers).copied().collect();

        let (c_shape, c_slice) = outputs["char_logits"]
            .try_extract_tensor::<f32>()
            .map_err(|e| format!("char_logits: {}", e))?;
        let vocab_chars = c_shape.last().copied().unwrap_or(0) as usize;
        let cl = c_slice
            .iter()
            .take(real_slots * vocab_chars)
            .copied()
            .collect();
        Ok((logits, cl, real_slots, vocab_chars))
    }
}

pub fn rerank(
    context: &str,
    raw_input: &str,
    layout: PinyinLayout,
    cands: &[String],
    weights: FusionWeights,
    p2c_cfg: P2cConfig,
) -> Result<RerankResult, String> {
    if cands.len() < 2 {
        return Ok(RerankResult {
            order: (1..=cands.len()).collect(),
            p2c_text: None,
            p2c_pos: 0,
            logits: vec![0.0; cands.len()],
            gram_deltas: vec![0.0; cands.len()],
            char_lps: vec![0.0; cands.len()],
        });
    }
    let mutex = ENGINE.get().ok_or_else(|| "engine not ready".to_string())?;
    let mut eng = mutex
        .lock()
        .map_err(|_| "engine mutex poisoned".to_string())?;
    let eval = eng.evaluate(
        context,
        raw_input,
        layout,
        cands,
        weights,
        p2c_cfg.verify_margin,
    )?;

    let has_ctx = if context.trim().chars().count() >= 2 {
        1.0
    } else {
        0.0
    };
    let order0 = rank_order_from_features(
        &eval.logits,
        &eval.gram_deltas,
        &eval.char_lps,
        has_ctx,
        weights,
    );

    // P2C synthesis gating:
    //   1. Preferred path: KV-cached Pass-2 Cross-Encoder + .gram verification (works with & without context)
    //   2. Fallback path (non-KV graph or Pass-2 disabled): context-gated Pass-1 char_logits margin
    let (p2c_text, p2c_pos) = if let Some(ref txt) = eval.p2c_text {
        if let Some((ldiff, gdiff)) = eval.p2c_verified {
            if p2c_cfg.top1_logit_diff > 0.0
                && ldiff > p2c_cfg.top1_logit_diff
                && gdiff > p2c_cfg.top1_min_gram_diff
            {
                (Some(txt.clone()), 1u8)
            } else if p2c_cfg.top2_logit_diff > 0.0
                && ldiff > p2c_cfg.top2_logit_diff
                && gdiff > (p2c_cfg.top1_min_gram_diff - 1.5)
            {
                (Some(txt.clone()), 2u8)
            } else {
                (None, 0u8)
            }
        } else if has_ctx > 0.5 {
            if p2c_cfg.legacy_top1_margin > 0.0 && eval.p2c_margin > p2c_cfg.legacy_top1_margin {
                (Some(txt.clone()), 1u8)
            } else if p2c_cfg.legacy_top2_margin > 0.0
                && eval.p2c_margin > p2c_cfg.legacy_top2_margin
            {
                (Some(txt.clone()), 2u8)
            } else {
                (None, 0u8)
            }
        } else {
            (None, 0u8)
        }
    } else {
        (None, 0u8)
    };

    Ok(RerankResult {
        order: order0.into_iter().map(|idx| idx + 1).collect(),
        p2c_text,
        p2c_pos,
        logits: eval.logits,
        gram_deltas: eval.gram_deltas,
        char_lps: eval.char_lps,
    })
}

pub fn get_stats() -> (bool, u64, u64, u64, u64, f64, bool, bool) {
    let Some(mutex) = ENGINE.get() else {
        return (false, 0, 0, 0, 0, 0.0, false, false);
    };
    let Ok(eng) = mutex.lock() else {
        return (false, 0, 0, 0, 0, 0.0, false, false);
    };
    let infer_calls = eng.stats.calls.saturating_sub(eng.stats.cache_hits);
    let avg = if infer_calls > 0 {
        eng.stats.total_infer_ms / (infer_calls as f64)
    } else {
        0.0
    };
    (
        true,
        eng.stats.calls,
        eng.stats.cache_hits,
        eng.stats.kv_hits,
        eng.stats.p2c_pass2_calls,
        avg,
        eng.stats.fused_kv,
        eng.stats.has_gram,
    )
}
