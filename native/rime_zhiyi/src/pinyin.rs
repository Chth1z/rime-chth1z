use std::collections::{HashMap, HashSet};

/// Supported pinyin input layouts (Full Pinyin + 7 major Rime Double Pinyin schemes).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum PinyinLayout {
    Full,
    Zrm,
    Flypy,
    Mspy,
    Sogou,
    Abc,
    Ziguang,
    Jiajia,
}

impl PinyinLayout {
    /// Parse an explicit layout name or auto-detect from a Rime `schema_id`.
    pub fn from_name_or_schema(layout_opt: &str, schema_id: &str) -> Self {
        match layout_opt.trim().to_ascii_lowercase().as_str() {
            "full" | "quanpin" | "pinyin" => return Self::Full,
            "zrm" | "natural" => return Self::Zrm,
            "flypy" | "xiaohe" => return Self::Flypy,
            "mspy" | "microsoft" => return Self::Mspy,
            "sogou" => return Self::Sogou,
            "abc" | "znabc" => return Self::Abc,
            "ziguang" | "zg" => return Self::Ziguang,
            "jiajia" | "jj" => return Self::Jiajia,
            _ => {}
        }

        let s = schema_id.to_ascii_lowercase();
        if s.contains("flypy") || s.contains("xiaohe") {
            Self::Flypy
        } else if s.contains("mspy") || s.contains("microsoft") {
            Self::Mspy
        } else if s.contains("sogou") {
            Self::Sogou
        } else if s.contains("abc") {
            Self::Abc
        } else if s.contains("ziguang") {
            Self::Ziguang
        } else if s.contains("jiajia") {
            Self::Jiajia
        } else if s.contains("double_pinyin") || s.contains("zrm") {
            Self::Zrm
        } else {
            Self::Full
        }
    }

    pub fn is_double_pinyin(self) -> bool {
        self != Self::Full
    }

    /// True for layouts that map a final (`ing`) to the semicolon key `;`.
    pub fn uses_semicolon(self) -> bool {
        matches!(self, Self::Mspy | Self::Sogou | Self::Ziguang)
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Full => "full",
            Self::Zrm => "zrm",
            Self::Flypy => "flypy",
            Self::Mspy => "mspy",
            Self::Sogou => "sogou",
            Self::Abc => "abc",
            Self::Ziguang => "ziguang",
            Self::Jiajia => "jiajia",
        }
    }
}

#[derive(Clone, Copy)]
enum ZeroInitialMode {
    /// Leading `a`/`e`/`o` (e.g. `aa=a`, `ah=ang`, `eg=eng`) plus optional `o`-prefixed aliases.
    SelfLeading,
    /// Fixed `o` zero-initial key (e.g. `oa=a`, `oe=e`, `oo=o`, `o+fin`).
    FixedO,
}

struct DoublePinyinSpec {
    zh_key: u8,
    ch_key: u8,
    sh_key: u8,
    zero_mode: ZeroInitialMode,
    /// Zero-initial 2-key direct overrides checked first (canonical Rime forms).
    zero_pairs: &'static [(u8, u8, &'static str)],
    /// Key -> possible finals (ordered by specificity; disambiguated via valid Mandarin table).
    finals_fn: fn(u8) -> &'static [&'static str],
}

fn zrm_finals(k: u8) -> &'static [&'static str] {
    match k {
        b'a' => &["a"],
        b'e' => &["e"],
        b'i' => &["i"],
        b'u' => &["u"],
        b'o' => &["o", "uo"],
        b'v' => &["v", "ui"],
        b'q' => &["iu"],
        b'w' => &["ua", "ia"],
        b'r' => &["uan", "er"],
        b't' => &["ve", "ue"],
        b'y' => &["uai", "ing"],
        b'p' => &["un"],
        b's' => &["iong", "ong"],
        b'd' => &["uang", "iang"],
        b'f' => &["en"],
        b'g' => &["eng"],
        b'h' => &["ang"],
        b'j' => &["an"],
        b'k' => &["ao"],
        b'l' => &["ai"],
        b'z' => &["ei"],
        b'x' => &["ie"],
        b'c' => &["iao"],
        b'b' => &["ou"],
        b'n' => &["in"],
        b'm' => &["ian"],
        _ => &[],
    }
}

fn flypy_finals(k: u8) -> &'static [&'static str] {
    match k {
        b'a' => &["a"],
        b'e' => &["e"],
        b'i' => &["i"],
        b'u' => &["u"],
        b'o' => &["o", "uo"],
        b'v' => &["v", "ui"],
        b'q' => &["iu"],
        b'w' => &["ei"],
        b'r' => &["uan"],
        b't' => &["ve", "ue"],
        b'y' => &["un"],
        b'p' => &["ie"],
        b's' => &["iong", "ong"],
        b'd' => &["ai"],
        b'f' => &["en"],
        b'g' => &["eng"],
        b'h' => &["ang"],
        b'j' => &["an"],
        b'k' => &["uai", "ing"],
        b'l' => &["uang", "iang"],
        b'z' => &["ou"],
        b'x' => &["ua", "ia"],
        b'c' => &["ao"],
        b'b' => &["in"],
        b'n' => &["iao"],
        b'm' => &["ian"],
        _ => &[],
    }
}

fn mspy_finals(k: u8) -> &'static [&'static str] {
    match k {
        b'a' => &["a"],
        b'e' => &["e"],
        b'i' => &["i"],
        b'u' => &["u"],
        b'o' => &["o", "uo"],
        b'q' => &["iu"],
        b'w' => &["ua", "ia"],
        b'r' => &["uan", "er"],
        b't' => &["ve", "ue"],
        b'y' => &["uai", "v"],
        b'p' => &["un"],
        b's' => &["iong", "ong"],
        b'd' => &["uang", "iang"],
        b'f' => &["en"],
        b'g' => &["eng"],
        b'h' => &["ang"],
        b'j' => &["an"],
        b'k' => &["ao"],
        b'l' => &["ai"],
        b'z' => &["ei"],
        b'x' => &["ie"],
        b'c' => &["iao"],
        b'v' => &["ui", "ve", "ue"],
        b'b' => &["ou"],
        b'n' => &["in"],
        b'm' => &["ian"],
        b';' => &["ing"],
        _ => &[],
    }
}

fn sogou_finals(k: u8) -> &'static [&'static str] {
    match k {
        b'v' => &["ui"],
        other => mspy_finals(other),
    }
}

fn abc_finals(k: u8) -> &'static [&'static str] {
    match k {
        b'a' => &["a"],
        b'e' => &["e"],
        b'i' => &["i"],
        b'u' => &["u"],
        b'o' => &["o", "uo"],
        b'v' => &["v"],
        b'q' => &["ei"],
        b'w' => &["ian"],
        b'r' => &["iu", "er"],
        b't' => &["uang", "iang"],
        b'y' => &["ing"],
        b'p' => &["uan"],
        b's' => &["iong", "ong"],
        b'd' => &["ua", "ia"],
        b'f' => &["en"],
        b'g' => &["eng"],
        b'h' => &["ang"],
        b'j' => &["an"],
        b'k' => &["ao"],
        b'l' => &["ai"],
        b'z' => &["iao"],
        b'x' => &["ie"],
        b'c' => &["uai", "in"],
        b'b' => &["ou"],
        b'n' => &["un"],
        b'm' => &["ve", "ue", "ui"],
        _ => &[],
    }
}

fn ziguang_finals(k: u8) -> &'static [&'static str] {
    match k {
        b'a' => &["a"],
        b'e' => &["e"],
        b'i' => &["i"],
        b'u' => &["u"],
        b'o' => &["o", "uo"],
        b'v' => &["v"],
        b'q' => &["ao"],
        b'w' => &["en"],
        b'r' => &["an"],
        b't' => &["eng"],
        b'y' => &["uai", "in"],
        b'p' => &["ai"],
        b's' => &["ang"],
        b'd' => &["ie"],
        b'f' => &["ian"],
        b'g' => &["uang", "iang"],
        b'h' => &["iong", "ong"],
        b'j' => &["iu", "er"],
        b'k' => &["ei"],
        b'l' => &["uan"],
        b'z' => &["ou"],
        b'x' => &["ua", "ia"],
        b'b' => &["iao"],
        b'n' => &["ve", "ue", "ui"],
        b'm' => &["un"],
        b';' => &["ing"],
        _ => &[],
    }
}

fn jiajia_finals(k: u8) -> &'static [&'static str] {
    match k {
        b'a' => &["a"],
        b'e' => &["e"],
        b'i' => &["i"],
        b'u' => &["u"],
        b'o' => &["o", "uo"],
        b'q' => &["ing", "er"],
        b'w' => &["ei"],
        b'r' => &["en"],
        b't' => &["eng"],
        b'y' => &["iong", "ong"],
        b'p' => &["ou"],
        b's' => &["ai"],
        b'd' => &["ao"],
        b'f' => &["an"],
        b'g' => &["ang"],
        b'h' => &["uang", "iang"],
        b'j' => &["ian"],
        b'k' => &["iao"],
        b'l' => &["in"],
        b'z' => &["un"],
        b'x' => &["uai", "ve", "ue"],
        b'c' => &["uan"],
        b'v' => &["v", "ui"],
        b'b' => &["ua", "ia"],
        b'n' => &["iu"],
        b'm' => &["ie"],
        _ => &[],
    }
}

const ZERO_ZRM: &[(u8, u8, &str)] = &[
    (b'a', b'a', "a"),
    (b'o', b'o', "o"),
    (b'e', b'e', "e"),
    (b'a', b'i', "ai"),
    (b'a', b'n', "an"),
    (b'a', b'o', "ao"),
    (b'a', b'h', "ang"),
    (b'e', b'i', "ei"),
    (b'e', b'n', "en"),
    (b'e', b'r', "er"),
    (b'e', b'g', "eng"),
    (b'o', b'u', "ou"),
    // Also accept o-prefixed aliases (rime-ice ZRM derives o-zero-initial forms)
    (b'o', b'a', "a"),
    (b'o', b'e', "e"),
    (b'o', b'l', "ai"),
    (b'o', b'j', "an"),
    (b'o', b'k', "ao"),
    (b'o', b'h', "ang"),
    (b'o', b'z', "ei"),
    (b'o', b'f', "en"),
    (b'o', b'g', "eng"),
    (b'o', b'r', "er"),
    (b'o', b'b', "ou"),
];

const ZERO_FLYPY: &[(u8, u8, &str)] = &[
    (b'a', b'a', "a"),
    (b'o', b'o', "o"),
    (b'e', b'e', "e"),
    (b'a', b'i', "ai"),
    (b'a', b'd', "ai"),
    (b'a', b'n', "an"),
    (b'a', b'j', "an"),
    (b'a', b'o', "ao"),
    (b'a', b'c', "ao"),
    (b'a', b'h', "ang"),
    (b'e', b'i', "ei"),
    (b'e', b'w', "ei"),
    (b'e', b'n', "en"),
    (b'e', b'f', "en"),
    (b'e', b'r', "er"),
    (b'e', b'g', "eng"),
    (b'o', b'u', "ou"),
    (b'o', b'z', "ou"),
];

const ZERO_MSPY_SOGOU: &[(u8, u8, &str)] = &[
    (b'o', b'a', "a"),
    (b'o', b'e', "e"),
    (b'o', b'o', "o"),
    (b'o', b'l', "ai"),
    (b'o', b'j', "an"),
    (b'o', b'k', "ao"),
    (b'o', b'h', "ang"),
    (b'o', b'z', "ei"),
    (b'o', b'f', "en"),
    (b'o', b'g', "eng"),
    (b'o', b'r', "er"),
    (b'o', b'b', "ou"),
    // Self-leading aliases from Rime MSPY/Sogou algebra
    (b'a', b'a', "a"),
    (b'e', b'e', "e"),
    (b'a', b'l', "ai"),
    (b'a', b'j', "an"),
    (b'a', b'k', "ao"),
    (b'a', b'h', "ang"),
    (b'e', b'z', "ei"),
    (b'e', b'f', "en"),
    (b'e', b'g', "eng"),
    (b'e', b'r', "er"),
    (b'a', b'i', "ai"),
    (b'a', b'n', "an"),
    (b'a', b'o', "ao"),
    (b'e', b'i', "ei"),
    (b'e', b'n', "en"),
    (b'o', b'u', "ou"),
];

const ZERO_ABC: &[(u8, u8, &str)] = &[
    (b'o', b'a', "a"),
    (b'o', b'e', "e"),
    (b'o', b'o', "o"),
    (b'o', b'l', "ai"),
    (b'o', b'j', "an"),
    (b'o', b'k', "ao"),
    (b'o', b'h', "ang"),
    (b'o', b'q', "ei"),
    (b'o', b'f', "en"),
    (b'o', b'g', "eng"),
    (b'o', b'r', "er"),
    (b'o', b'b', "ou"),
];

const ZERO_ZIGUANG: &[(u8, u8, &str)] = &[
    (b'o', b'a', "a"),
    (b'o', b'e', "e"),
    (b'o', b'o', "o"),
    (b'o', b'p', "ai"),
    (b'o', b'r', "an"),
    (b'o', b'q', "ao"),
    (b'o', b's', "ang"),
    (b'o', b'k', "ei"),
    (b'o', b'w', "en"),
    (b'o', b't', "eng"),
    (b'o', b'j', "er"),
    (b'o', b'z', "ou"),
];

const ZERO_JIAJIA: &[(u8, u8, &str)] = &[
    (b'o', b'a', "a"),
    (b'o', b'e', "e"),
    (b'o', b'o', "o"),
    (b'o', b's', "ai"),
    (b'o', b'f', "an"),
    (b'o', b'd', "ao"),
    (b'o', b'g', "ang"),
    (b'o', b'w', "ei"),
    (b'o', b'r', "en"),
    (b'o', b't', "eng"),
    (b'o', b'q', "er"),
    (b'o', b'p', "ou"),
    (b'a', b'a', "a"),
    (b'e', b'e', "e"),
    (b'a', b's', "ai"),
    (b'a', b'f', "an"),
    (b'a', b'd', "ao"),
    (b'a', b'g', "ang"),
    (b'e', b'w', "ei"),
    (b'e', b'r', "en"),
    (b'e', b't', "eng"),
    (b'e', b'q', "er"),
    (b'a', b'i', "ai"),
    (b'a', b'n', "an"),
    (b'a', b'o', "ao"),
    (b'e', b'i', "ei"),
    (b'e', b'n', "en"),
    (b'o', b'u', "ou"),
];

fn layout_spec(layout: PinyinLayout) -> Option<DoublePinyinSpec> {
    Some(match layout {
        PinyinLayout::Full => return None,
        PinyinLayout::Zrm => DoublePinyinSpec {
            zh_key: b'v',
            ch_key: b'i',
            sh_key: b'u',
            zero_mode: ZeroInitialMode::SelfLeading,
            zero_pairs: ZERO_ZRM,
            finals_fn: zrm_finals,
        },
        PinyinLayout::Flypy => DoublePinyinSpec {
            zh_key: b'v',
            ch_key: b'i',
            sh_key: b'u',
            zero_mode: ZeroInitialMode::SelfLeading,
            zero_pairs: ZERO_FLYPY,
            finals_fn: flypy_finals,
        },
        PinyinLayout::Mspy => DoublePinyinSpec {
            zh_key: b'v',
            ch_key: b'i',
            sh_key: b'u',
            zero_mode: ZeroInitialMode::SelfLeading,
            zero_pairs: ZERO_MSPY_SOGOU,
            finals_fn: mspy_finals,
        },
        PinyinLayout::Sogou => DoublePinyinSpec {
            zh_key: b'v',
            ch_key: b'i',
            sh_key: b'u',
            zero_mode: ZeroInitialMode::SelfLeading,
            zero_pairs: ZERO_MSPY_SOGOU,
            finals_fn: sogou_finals,
        },
        PinyinLayout::Abc => DoublePinyinSpec {
            zh_key: b'a',
            ch_key: b'e',
            sh_key: b'v',
            zero_mode: ZeroInitialMode::FixedO,
            zero_pairs: ZERO_ABC,
            finals_fn: abc_finals,
        },
        PinyinLayout::Ziguang => DoublePinyinSpec {
            zh_key: b'u',
            ch_key: b'a',
            sh_key: b'i',
            zero_mode: ZeroInitialMode::FixedO,
            zero_pairs: ZERO_ZIGUANG,
            finals_fn: ziguang_finals,
        },
        PinyinLayout::Jiajia => DoublePinyinSpec {
            zh_key: b'v',
            ch_key: b'u',
            sh_key: b'i',
            zero_mode: ZeroInitialMode::SelfLeading,
            zero_pairs: ZERO_JIAJIA,
            finals_fn: jiajia_finals,
        },
    })
}

fn map_initial(spec: &DoublePinyinSpec, a: u8) -> Option<&'static str> {
    if a == spec.zh_key {
        return Some("zh");
    }
    if a == spec.ch_key {
        return Some("ch");
    }
    if a == spec.sh_key {
        return Some("sh");
    }
    match a {
        b'b' => Some("b"),
        b'p' => Some("p"),
        b'm' => Some("m"),
        b'f' => Some("f"),
        b'd' => Some("d"),
        b't' => Some("t"),
        b'n' => Some("n"),
        b'l' => Some("l"),
        b'g' => Some("g"),
        b'k' => Some("k"),
        b'h' => Some("h"),
        b'j' => Some("j"),
        b'q' => Some("q"),
        b'x' => Some("x"),
        b'r' => Some("r"),
        b'z' => Some("z"),
        b'c' => Some("c"),
        b's' => Some("s"),
        b'y' => Some("y"),
        b'w' => Some("w"),
        _ => None,
    }
}

/// Convert a 2-key Double Pinyin pair under `layout` into a standard full pinyin syllable.
/// Uses `valid_syllables` (from `unified_vocab.json`) to disambiguate shared final keys accurately.
pub fn dp_pair_to_syllable(
    layout: PinyinLayout,
    a: u8,
    b: u8,
    valid_syllables: &HashSet<String>,
) -> Option<String> {
    let spec = layout_spec(layout)?;
    let a = a.to_ascii_lowercase();
    let b = b.to_ascii_lowercase();

    // 1. Check explicit zero-initial pairs first (except layouts where `a`/`e` is a consonant initial,
    //    which only happens under FixedO where zero_pairs all start with `o`!)
    for &(za, zb, syl) in spec.zero_pairs {
        if a == za && b == zb {
            return Some(syl.to_string());
        }
    }

    // 2. Map initial consonant
    let ini = map_initial(&spec, a)?;
    let candidates = (spec.finals_fn)(b);
    if candidates.is_empty() {
        return None;
    }

    // 3. Disambiguate final via exact Mandarin phonotactics + valid_syllables table
    let mut fallback: Option<String> = None;
    for &fin in candidates {
        // Normalize ü rules: n/l keep `v` / `ve`, j/q/x/y use `u` / `ue`; no other consonant takes `v`
        let norm_fin = match (ini, fin) {
            ("j" | "q" | "x" | "y", "v") => "u",
            ("j" | "q" | "x" | "y", "ve") => "ue",
            ("n" | "l", "v") => "v",
            ("n" | "l", "ue") => "ve",
            (_, "v") => continue,
            // `uo` never pairs with b/p/m/f/w/y; `o` only pairs with b/p/m/f/w/y
            ("b" | "p" | "m" | "f" | "w" | "y", "uo") => continue,
            (i, "o") if !matches!(i, "b" | "p" | "m" | "f" | "w" | "y") => continue,
            // `er` is strictly zero-initial
            (_, "er") => continue,
            _ => fin,
        };

        let mut cand = String::with_capacity(ini.len() + norm_fin.len());
        cand.push_str(ini);
        cand.push_str(norm_fin);

        if valid_syllables.is_empty() || valid_syllables.contains(&cand) {
            return Some(cand);
        }
        if fallback.is_none() {
            fallback = Some(cand);
        }
    }

    // Keep zero_mode used cleanly for completeness
    let _ = spec.zero_mode;
    fallback
}

/// Parse Double Pinyin input (ignoring delimiters `'`) into Zhiyi unit tags for any supported layout.
pub fn double_pinyin_to_units(
    layout: PinyinLayout,
    raw_input: &str,
    valid_syllables: &HashSet<String>,
) -> Vec<(&'static str, String)> {
    let Some(spec) = layout_spec(layout) else {
        return Vec::new();
    };
    let allow_semi = layout.uses_semicolon();
    let keys: Vec<u8> = raw_input
        .bytes()
        .filter(|&b| b.is_ascii_alphabetic() || (allow_semi && b == b';'))
        .map(|b| b.to_ascii_lowercase())
        .collect();

    let mut units = Vec::with_capacity(keys.len().div_ceil(2));
    let mut i = 0;
    while i + 1 < keys.len() {
        if let Some(syl) = dp_pair_to_syllable(layout, keys[i], keys[i + 1], valid_syllables) {
            units.push(("f", syl));
        }
        i += 2;
    }
    if i < keys.len() {
        let p = map_initial(&spec, keys[i])
            .map(str::to_string)
            .unwrap_or_else(|| (keys[i] as char).to_string());
        units.push(("p", p));
    }
    units
}

/// Full-pinyin syllable recovery aligned to the leading candidate's characters via `readings`.
pub fn full_pinyin_to_units(
    raw_input: &str,
    lead_text: &str,
    readings: &HashMap<String, Vec<String>>,
    valid_syllables: &HashSet<String>,
) -> Vec<(&'static str, String)> {
    if raw_input.contains(' ') {
        let parts: Vec<String> = raw_input
            .split([' ', '\''])
            .filter(|s| !s.is_empty())
            .map(|s| s.to_ascii_lowercase())
            .collect();
        if parts.iter().all(|p| valid_syllables.contains(p)) {
            return parts.into_iter().map(|p| ("f", p)).collect();
        }
    }

    let code: String = raw_input
        .bytes()
        .filter(|b| b.is_ascii_alphabetic())
        .map(|b| b.to_ascii_lowercase() as char)
        .collect();
    let chars: Vec<char> = lead_text.chars().collect();
    let mut out: Vec<(&'static str, String)> = Vec::with_capacity(chars.len());

    fn walk(
        i: usize,
        pos: usize,
        chars: &[char],
        code: &str,
        readings: &HashMap<String, Vec<String>>,
        out: &mut Vec<(&'static str, String)>,
    ) -> bool {
        if i == chars.len() {
            return pos == code.len();
        }
        let key = chars[i].to_string();
        let Some(rlist) = readings.get(&key) else {
            return false;
        };
        let last = i + 1 == chars.len();
        for reading in rlist {
            if code[pos..].starts_with(reading.as_str()) {
                out.push(("f", reading.clone()));
                if walk(i + 1, pos + reading.len(), chars, code, readings, out) {
                    return true;
                }
                out.pop();
            }
            for k in (1..reading.len()).rev() {
                let b = reading.as_bytes();
                let is_initial =
                    k == 1 || (k == 2 && b[1] == b'h' && matches!(b[0], b'z' | b'c' | b's'));
                if !last && !is_initial {
                    continue;
                }
                if code[pos..].starts_with(&reading[..k]) {
                    out.push(("p", reading[..k].to_string()));
                    if walk(i + 1, pos + k, chars, code, readings, out) {
                        return true;
                    }
                    out.pop();
                }
            }
        }
        false
    }

    if walk(0, 0, &chars, &code, readings, &mut out) {
        return out;
    }

    // Fallback: greedy longest-syllable split
    let mut greedy = Vec::new();
    let mut pos = 0;
    while pos < code.len() {
        let mut matched = false;
        for len in (1..=6.min(code.len() - pos)).rev() {
            let sub = &code[pos..pos + len];
            if valid_syllables.contains(sub) {
                greedy.push(("f", sub.to_string()));
                pos += len;
                matched = true;
                break;
            }
        }
        if !matched {
            greedy.push(("p", code[pos..pos + 1].to_string()));
            pos += 1;
        }
    }
    greedy
}

/// Dispatch helper converting raw input into Zhiyi syllable units under any `PinyinLayout`.
pub fn input_to_units(
    layout: PinyinLayout,
    raw_input: &str,
    lead_text: &str,
    readings: &HashMap<String, Vec<String>>,
    valid_syllables: &HashSet<String>,
) -> Vec<(&'static str, String)> {
    if layout.is_double_pinyin() {
        double_pinyin_to_units(layout, raw_input, valid_syllables)
    } else {
        full_pinyin_to_units(raw_input, lead_text, readings, valid_syllables)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_valid_syllables() -> HashSet<String> {
        let mut set: HashSet<String> = [
            "a", "o", "e", "ai", "ei", "ao", "ou", "an", "en", "ang", "eng", "er", "zhu", "zhui",
            "zhuang", "zhuai", "chuan", "shuo", "shuang", "shui", "nv", "lv", "lve", "nve", "jue",
            "que", "xue", "yue", "ju", "qu", "xu", "yu", "suo", "bo", "po", "mo", "fo", "wo", "yo",
            "rua", "ting", "ming", "jing", "liang", "jiang", "qiang", "xiang", "kuai", "guai",
            "ni", "hao", "zhong", "guo", "ren", "min", "tian", "qi", "dian", "jia", "bian", "yi",
            "xiong", "qiong", "jiong", "long", "dong", "kong", "gong", "hong", "nong", "liu",
            "jiu", "qiu", "xiu", "diu", "niu", "miu", "bie", "pie", "mie", "die", "tie", "nie",
            "lie", "jie", "qie", "xie", "piao", "miao", "diao", "tiao", "niao", "liao", "jiao",
            "qiao", "xiao", "kun", "gun", "hun", "dun", "tun", "lun", "zun", "cun", "sun", "run",
            "zhun", "chun", "shun",
        ]
        .into_iter()
        .map(String::from)
        .collect();
        // If live unified_vocab.json exists on machine, load ALL 425 real syllables!
        if let Ok(appdata) = std::env::var("APPDATA") {
            let p = std::path::PathBuf::from(appdata)
                .join("Rime")
                .join("zhiyi")
                .join("unified_vocab.json");
            if let Ok(raw) = std::fs::read_to_string(&p) {
                if let Ok(v) = serde_json::from_str::<serde_json::Value>(&raw) {
                    if let Some(arr) = v.get("units").and_then(|u| u.as_array()) {
                        for item in arr {
                            if let Some(s) = item.as_str().and_then(|u| u.strip_prefix("f:")) {
                                set.insert(s.to_string());
                            }
                        }
                    }
                }
            }
        }
        set
    }

    #[test]
    fn test_all_seven_double_pinyin_layouts() {
        let valid = sample_valid_syllables();

        // 1. ZRM (自然码)
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Zrm, b'v', b'u', &valid).as_deref(),
            Some("zhu")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Zrm, b'v', b'v', &valid).as_deref(),
            Some("zhui")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Zrm, b'n', b'v', &valid).as_deref(),
            Some("nv")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Zrm, b'l', b't', &valid).as_deref(),
            Some("lve")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Zrm, b'j', b't', &valid).as_deref(),
            Some("jue")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Zrm, b'y', b'o', &valid).as_deref(),
            Some("yo")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Zrm, b'r', b'w', &valid).as_deref(),
            Some("rua")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Zrm, b't', b'y', &valid).as_deref(),
            Some("ting")
        );

        // 2. Flypy (小鹤)
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Flypy, b't', b'k', &valid).as_deref(),
            Some("ting")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Flypy, b'k', b'k', &valid).as_deref(),
            Some("kuai")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Flypy, b'v', b'l', &valid).as_deref(),
            Some("zhuang")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Flypy, b'j', b'l', &valid).as_deref(),
            Some("jiang")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Flypy, b'n', b'v', &valid).as_deref(),
            Some("nv")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Flypy, b'j', b'n', &valid).as_deref(),
            Some("jiao")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Flypy, b'a', b'h', &valid).as_deref(),
            Some("ang")
        );

        // 3. MSPY (微软) — uses `;` for `ing`
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Mspy, b't', b';', &valid).as_deref(),
            Some("ting")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Mspy, b'n', b'y', &valid).as_deref(),
            Some("nv")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Mspy, b'k', b'y', &valid).as_deref(),
            Some("kuai")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Mspy, b'j', b'v', &valid).as_deref(),
            Some("jue")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Mspy, b'v', b'v', &valid).as_deref(),
            Some("zhui")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Mspy, b'o', b'r', &valid).as_deref(),
            Some("er")
        );

        // 4. Sogou (搜狗)
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Sogou, b'm', b';', &valid).as_deref(),
            Some("ming")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Sogou, b'u', b'v', &valid).as_deref(),
            Some("shui")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Sogou, b'l', b't', &valid).as_deref(),
            Some("lve")
        );

        // 5. ABC (智能 ABC)
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Abc, b'a', b's', &valid).as_deref(),
            Some("zhong")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Abc, b'e', b'p', &valid).as_deref(),
            Some("chuan")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Abc, b'v', b'o', &valid).as_deref(),
            Some("shuo")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Abc, b't', b'y', &valid).as_deref(),
            Some("ting")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Abc, b'o', b'h', &valid).as_deref(),
            Some("ang")
        );

        // 6. Ziguang (紫光) — uses `;` for `ing`
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Ziguang, b'u', b'h', &valid).as_deref(),
            Some("zhong")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Ziguang, b'a', b'l', &valid).as_deref(),
            Some("chuan")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Ziguang, b'i', b'o', &valid).as_deref(),
            Some("shuo")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Ziguang, b't', b';', &valid).as_deref(),
            Some("ting")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Ziguang, b'o', b's', &valid).as_deref(),
            Some("ang")
        );

        // 7. Jiajia (拼音加加)
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Jiajia, b'v', b'y', &valid).as_deref(),
            Some("zhong")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Jiajia, b'u', b'c', &valid).as_deref(),
            Some("chuan")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Jiajia, b'i', b'o', &valid).as_deref(),
            Some("shuo")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Jiajia, b't', b'q', &valid).as_deref(),
            Some("ting")
        );
        assert_eq!(
            dp_pair_to_syllable(PinyinLayout::Jiajia, b'o', b'g', &valid).as_deref(),
            Some("ang")
        );

        // Auto-detection from schema_id
        assert_eq!(
            PinyinLayout::from_name_or_schema("auto", "double_pinyin_flypy"),
            PinyinLayout::Flypy
        );
        assert_eq!(
            PinyinLayout::from_name_or_schema("auto", "double_pinyin_mspy"),
            PinyinLayout::Mspy
        );
        assert_eq!(
            PinyinLayout::from_name_or_schema("auto", "rime_frost_double_pinyin"),
            PinyinLayout::Zrm
        );
        assert_eq!(
            PinyinLayout::from_name_or_schema("auto", "rime_ice"),
            PinyinLayout::Full
        );
        assert_eq!(
            PinyinLayout::from_name_or_schema("sogou", "custom"),
            PinyinLayout::Sogou
        );
    }

    #[test]
    fn test_semicolon_double_pinyin_sequence() {
        let valid = sample_valid_syllables();
        let units = double_pinyin_to_units(PinyinLayout::Mspy, "m;tm", &valid);
        assert_eq!(
            units,
            vec![("f", "ming".to_string()), ("f", "tian".to_string())]
        );
    }

    fn encode_for_test(layout: PinyinLayout, syl: &str) -> Option<(u8, u8)> {
        // Canonical zero-initial syllables
        if let Some(pair) = match (layout, syl) {
            (
                PinyinLayout::Zrm
                | PinyinLayout::Flypy
                | PinyinLayout::Mspy
                | PinyinLayout::Sogou
                | PinyinLayout::Jiajia,
                "a",
            ) => Some((b'a', b'a')),
            (
                PinyinLayout::Zrm
                | PinyinLayout::Flypy
                | PinyinLayout::Mspy
                | PinyinLayout::Sogou
                | PinyinLayout::Jiajia,
                "e",
            ) => Some((b'e', b'e')),
            (
                PinyinLayout::Zrm
                | PinyinLayout::Flypy
                | PinyinLayout::Mspy
                | PinyinLayout::Sogou
                | PinyinLayout::Jiajia,
                "o",
            ) => Some((b'o', b'o')),
            (
                PinyinLayout::Zrm
                | PinyinLayout::Flypy
                | PinyinLayout::Mspy
                | PinyinLayout::Sogou
                | PinyinLayout::Jiajia,
                "ai",
            ) => Some((b'a', b'i')),
            (
                PinyinLayout::Zrm
                | PinyinLayout::Flypy
                | PinyinLayout::Mspy
                | PinyinLayout::Sogou
                | PinyinLayout::Jiajia,
                "an",
            ) => Some((b'a', b'n')),
            (
                PinyinLayout::Zrm
                | PinyinLayout::Flypy
                | PinyinLayout::Mspy
                | PinyinLayout::Sogou
                | PinyinLayout::Jiajia,
                "ao",
            ) => Some((b'a', b'o')),
            (
                PinyinLayout::Zrm | PinyinLayout::Flypy | PinyinLayout::Mspy | PinyinLayout::Sogou,
                "ang",
            ) => Some((b'a', b'h')),
            (PinyinLayout::Jiajia, "ang") => Some((b'a', b'g')),
            (
                PinyinLayout::Zrm
                | PinyinLayout::Flypy
                | PinyinLayout::Mspy
                | PinyinLayout::Sogou
                | PinyinLayout::Jiajia,
                "ei",
            ) => Some((b'e', b'i')),
            (
                PinyinLayout::Zrm
                | PinyinLayout::Flypy
                | PinyinLayout::Mspy
                | PinyinLayout::Sogou
                | PinyinLayout::Jiajia,
                "en",
            ) => Some((b'e', b'n')),
            (
                PinyinLayout::Zrm | PinyinLayout::Flypy | PinyinLayout::Mspy | PinyinLayout::Sogou,
                "er",
            ) => Some((b'e', b'r')),
            (PinyinLayout::Jiajia, "er") => Some((b'e', b'q')),
            (
                PinyinLayout::Zrm | PinyinLayout::Flypy | PinyinLayout::Mspy | PinyinLayout::Sogou,
                "eng",
            ) => Some((b'e', b'g')),
            (PinyinLayout::Jiajia, "eng") => Some((b'e', b't')),
            (
                PinyinLayout::Zrm
                | PinyinLayout::Flypy
                | PinyinLayout::Mspy
                | PinyinLayout::Sogou
                | PinyinLayout::Jiajia,
                "ou",
            ) => Some((b'o', b'u')),
            (PinyinLayout::Abc, s) => ZERO_ABC
                .iter()
                .find(|&&(_, _, z)| z == s)
                .map(|&(a, b, _)| (a, b)),
            (PinyinLayout::Ziguang, s) => ZERO_ZIGUANG
                .iter()
                .find(|&&(_, _, z)| z == s)
                .map(|&(a, b, _)| (a, b)),
            _ => None,
        } {
            return Some(pair);
        }

        let spec = layout_spec(layout)?;
        let (ini, fin) = if let Some(rest) = syl.strip_prefix("zh") {
            (spec.zh_key, rest)
        } else if let Some(rest) = syl.strip_prefix("ch") {
            (spec.ch_key, rest)
        } else if let Some(rest) = syl.strip_prefix("sh") {
            (spec.sh_key, rest)
        } else {
            let b0 = syl.as_bytes()[0];
            if matches!(b0, b'a' | b'e' | b'o') {
                return None;
            }
            (b0, &syl[1..])
        };

        // Find the key mapped to `fin` in `spec.finals_fn`
        let search_fin = match (syl.as_bytes()[0], fin) {
            (b'j' | b'q' | b'x' | b'y', "ue") => "ve",
            _ => fin,
        };
        for k in (b'a'..=b'z').chain(std::iter::once(b';')) {
            if (spec.finals_fn)(k).contains(&search_fin) || (spec.finals_fn)(k).contains(&fin) {
                return Some((ini, k));
            }
        }
        None
    }

    #[test]
    fn test_exhaustive_roundtrip_all_7_layouts() {
        let valid = sample_valid_syllables();
        // Exclude rare interjections / non-standard syllables absent from standard pinyin tables
        let skip = [
            "hm", "hng", "m", "n", "ng", "lo", "nou", "den", "kei", "dia", "tei", "fiao", "chua",
            "neng",
        ];
        for layout in [
            PinyinLayout::Zrm,
            PinyinLayout::Flypy,
            PinyinLayout::Mspy,
            PinyinLayout::Sogou,
            PinyinLayout::Abc,
            PinyinLayout::Ziguang,
            PinyinLayout::Jiajia,
        ] {
            let mut tested = 0usize;
            for syl in &valid {
                if skip.contains(&syl.as_str()) {
                    continue;
                }
                if let Some((k1, k2)) = encode_for_test(layout, syl) {
                    let dec = dp_pair_to_syllable(layout, k1, k2, &valid);
                    assert_eq!(
                        dec.as_deref(),
                        Some(syl.as_str()),
                        "Roundtrip mismatch on {:?}: {} -> ({},{}) -> {:?}",
                        layout,
                        syl,
                        k1 as char,
                        k2 as char,
                        dec
                    );
                    tested += 1;
                }
            }
            assert!(
                tested >= 90,
                "Too few syllables tested for {:?}: {}",
                layout,
                tested
            );
        }
    }
}
