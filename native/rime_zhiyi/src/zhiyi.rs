use std::collections::{HashMap, HashSet, VecDeque};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Mutex, OnceLock};
use std::time::Instant;

use ort::environment::Environment;
use ort::session::{builder::GraphOptimizationLevel, Session};
use ort::value::Tensor;
use serde::Deserialize;
use tokenizers::Tokenizer;

use crate::pinyin::{full_pinyin_to_units, zrm_input_to_units};

const CONTEXT_CHARS: usize = 128;
const LRU_CAPACITY: usize = 256;

#[derive(Deserialize)]
struct UnifiedVocabFile {
    units: Vec<String>,
    readings: HashMap<String, Vec<String>>,
    #[serde(default = "default_max_slots")]
    max_slots: usize,
    #[serde(default = "default_ctx_tokens")]
    choice_context_tokens: usize,
    #[serde(default = "default_cand_tokens")]
    choice_candidate_tokens: usize,
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

#[derive(Hash, PartialEq, Eq, Clone)]
struct CacheKey {
    ctx_tail: String,
    raw_input: String,
    is_dp: bool,
    cands: Vec<String>,
}

pub struct ZhiyiStats {
    pub calls: u64,
    pub cache_hits: u64,
    pub total_infer_ms: f64,
}

pub struct ZhiyiEngine {
    model_dir: PathBuf,
    session: Session,
    tokenizer: Tokenizer,
    unit_ids: HashMap<String, i64>,
    readings: HashMap<String, Vec<String>>,
    valid_syllables: HashSet<String>,
    max_slots: usize,
    context_tokens: usize,
    candidate_tokens: usize,
    cls_id: i64,
    sep_id: i64,
    mask_id: i64,
    lru_map: HashMap<CacheKey, Vec<f32>>,
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

pub fn init_engine(model_dir: &Path, ort_dll: &Path, threads: usize) -> Result<(), String> {
    if let Some(m) = ENGINE.get() {
        let g = m.lock().map_err(|_| "engine mutex poisoned".to_string())?;
        if g.model_dir == model_dir {
            return Ok(());
        }
        return Ok(());
    }

    let ort_env = ensure_ort_env(ort_dll)?;

    let onnx_path = model_dir.join("laya.int8g.onnx");
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

    let mut engine = ZhiyiEngine {
        model_dir: model_dir.to_path_buf(),
        session,
        tokenizer,
        unit_ids,
        readings: uv.readings,
        valid_syllables,
        max_slots: uv.max_slots,
        context_tokens: uv.choice_context_tokens,
        candidate_tokens: uv.choice_candidate_tokens,
        cls_id,
        sep_id,
        mask_id,
        lru_map: HashMap::with_capacity(LRU_CAPACITY + 16),
        lru_order: VecDeque::with_capacity(LRU_CAPACITY + 16),
        stats: ZhiyiStats {
            calls: 0,
            cache_hits: 0,
            total_infer_ms: 0.0,
        },
    };

    // Single untimed warmup pass so kernels are paged in before the user's first sentence
    let warmup_cands = vec!["你好".to_string(), "拟好".to_string()];
    let _ = engine.score_candidates("", "nihk", true, &warmup_cands);
    engine.lru_map.clear();
    engine.lru_order.clear();
    engine.stats = ZhiyiStats {
        calls: 0,
        cache_hits: 0,
        total_infer_ms: 0.0,
    };

    let _ = ENGINE.set(Mutex::new(engine));
    Ok(())
}

/// Non-blocking background initialization for WeaselServer startup (returns in <0.1 ms).
/// Until the background thread finishes (~1.2s), `rerank_indices` returns Err("not ready")
/// immediately so typing is never stalled.
pub fn init_engine_async(model_dir: PathBuf, ort_dll: PathBuf, threads: usize) {
    if ENGINE.get().is_some() {
        return;
    }
    if ASYNC_STARTED.swap(true, Ordering::AcqRel) {
        return;
    }
    let _ = std::thread::Builder::new()
        .name("rime-zhiyi-init".to_string())
        .spawn(move || {
            if init_engine(&model_dir, &ort_dll, threads).is_err() {
                ASYNC_STARTED.store(false, Ordering::Release);
            }
        });
}

pub fn is_ready() -> bool {
    ENGINE.get().is_some()
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

    pub fn score_candidates(
        &mut self,
        context: &str,
        raw_input: &str,
        is_double_pinyin: bool,
        cands: &[String],
    ) -> Result<Vec<f32>, String> {
        self.stats.calls += 1;
        let ctx_tail = utf8_tail(context, CONTEXT_CHARS);
        let key = CacheKey {
            ctx_tail: ctx_tail.to_string(),
            raw_input: raw_input.to_string(),
            is_dp: is_double_pinyin,
            cands: cands.to_vec(),
        };
        if let Some(cached) = self.lru_map.get(&key) {
            self.stats.cache_hits += 1;
            return Ok(cached.clone());
        }

        let mut units = if is_double_pinyin {
            zrm_input_to_units(raw_input)
        } else {
            full_pinyin_to_units(raw_input, &cands[0], &self.readings, &self.valid_syllables)
        };

        // Pre-encode candidates; only shift LCP on ultra-long (>16 token) sentences
        // where candidate_tokens truncation would clip the differing tail.
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
        if cand_toks.iter().any(|t| t.len() > self.candidate_tokens) {
            let lcp = common_prefix_chars(cands);
            if lcp > 0 {
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

        let mut ids: Vec<i64> = Vec::with_capacity(256);
        ids.push(self.cls_id);
        let ctx_final = utf8_tail(&eff_ctx, CONTEXT_CHARS);
        if !ctx_final.is_empty() {
            let cids = self.encode_ids(ctx_final);
            let start = cids.len().saturating_sub(self.context_tokens);
            ids.extend_from_slice(&cids[start..]);
        }
        ids.push(self.sep_id);

        let mut unit_ids: Vec<i64> = vec![0; ids.len()];
        let mut slots: Vec<i64> = Vec::with_capacity(self.max_slots);
        for (kind, text) in units.iter().take(self.max_slots) {
            slots.push(ids.len() as i64);
            ids.push(self.mask_id);
            let k = format!("{}:{}", kind, text);
            unit_ids.push(*self.unit_ids.get(&k).unwrap_or(&0));
        }
        ids.push(self.sep_id);
        unit_ids.push(0);

        let mut markers: Vec<i64> = Vec::with_capacity(cand_toks.len());
        for ctok in &cand_toks {
            markers.push(ids.len() as i64);
            ids.push(self.mask_id);
            let take = ctok.len().min(self.candidate_tokens);
            ids.extend_from_slice(&ctok[..take]);
        }
        ids.push(self.sep_id);
        unit_ids.resize(ids.len(), 0);

        let seq_len = ids.len();
        let n_markers = markers.len();
        if slots.is_empty() {
            slots.push(0);
        }
        let n_slots = slots.len();

        let attention_mask: Vec<i64> = vec![1; seq_len];
        let marker_mask: Vec<bool> = vec![true; n_markers];

        let t_ids = Tensor::from_array(([1usize, seq_len], ids))
            .map_err(|e| format!("tensor input_ids: {}", e))?;
        let t_att = Tensor::from_array(([1usize, seq_len], attention_mask))
            .map_err(|e| format!("tensor attention_mask: {}", e))?;
        let t_uid = Tensor::from_array(([1usize, seq_len], unit_ids))
            .map_err(|e| format!("tensor unit_ids: {}", e))?;
        let t_mpos = Tensor::from_array(([1usize, n_markers], markers))
            .map_err(|e| format!("tensor marker_pos: {}", e))?;
        let t_mmask = Tensor::from_array(([1usize, n_markers], marker_mask))
            .map_err(|e| format!("tensor marker_mask: {}", e))?;
        let t_spos = Tensor::from_array(([1usize, n_slots], slots))
            .map_err(|e| format!("tensor slot_pos: {}", e))?;

        let t0 = Instant::now();
        let outputs = self
            .session
            .run(ort::inputs![
                "input_ids" => t_ids,
                "attention_mask" => t_att,
                "unit_ids" => t_uid,
                "marker_pos" => t_mpos,
                "marker_mask" => t_mmask,
                "slot_pos" => t_spos,
            ])
            .map_err(|e| format!("session run: {}", e))?;
        self.stats.total_infer_ms += t0.elapsed().as_secs_f64() * 1000.0;

        let (_, slice) = outputs["logits"]
            .try_extract_tensor::<f32>()
            .map_err(|e| format!("extract logits: {}", e))?;
        let logits: Vec<f32> = slice.iter().take(n_markers).copied().collect();

        if self.lru_map.len() >= LRU_CAPACITY {
            if let Some(old) = self.lru_order.pop_front() {
                self.lru_map.remove(&old);
            }
        }
        self.lru_order.push_back(key.clone());
        self.lru_map.insert(key, logits.clone());
        Ok(logits)
    }
}

pub fn rerank_indices(
    context: &str,
    raw_input: &str,
    is_double_pinyin: bool,
    cands: &[String],
    rank_penalty: f64,
) -> Result<Vec<usize>, String> {
    if cands.len() < 2 {
        return Ok((1..=cands.len()).collect());
    }
    let mutex = ENGINE.get().ok_or_else(|| "engine not ready".to_string())?;
    let mut eng = mutex.lock().map_err(|_| "engine mutex poisoned".to_string())?;
    let logits = eng.score_candidates(context, raw_input, is_double_pinyin, cands)?;

    let max_l = logits.iter().copied().fold(f32::NEG_INFINITY, f32::max) as f64;
    let sum_exp: f64 = logits.iter().map(|&x| ((x as f64) - max_l).exp()).sum();
    let lse = max_l + sum_exp.ln();

    let mut order: Vec<(usize, f64)> = logits
        .iter()
        .enumerate()
        .map(|(i, &x)| {
            let lp = (x as f64) - lse;
            let score = lp - rank_penalty * ((i as f64) + 1.0).ln();
            (i + 1, score)
        })
        .collect();
    order.sort_by(|a, b| b.1.total_cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    Ok(order.into_iter().map(|(idx, _)| idx).collect())
}

pub fn get_stats() -> (bool, u64, u64, f64) {
    let Some(mutex) = ENGINE.get() else {
        return (false, 0, 0, 0.0);
    };
    let Ok(eng) = mutex.lock() else {
        return (false, 0, 0, 0.0);
    };
    let infer_calls = eng.stats.calls.saturating_sub(eng.stats.cache_hits);
    let avg = if infer_calls > 0 {
        eng.stats.total_infer_ms / (infer_calls as f64)
    } else {
        0.0
    };
    (true, eng.stats.calls, eng.stats.cache_hits, avg)
}
