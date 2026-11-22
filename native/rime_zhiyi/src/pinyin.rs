use std::collections::{HashMap, HashSet};

/// Convert a 2-letter Natural Double Pinyin (ZRM) pair into a standard full pinyin syllable
/// matching Zhiyi's `unified_vocab.json` (`f:<syllable>`).
pub fn zrm_pair_to_syllable(a: u8, b: u8) -> Option<String> {
    let a = a.to_ascii_lowercase();
    let b = b.to_ascii_lowercase();

    match (a, b) {
        (b'a', b'a') => return Some("a".into()),
        (b'o', b'o') => return Some("o".into()),
        (b'e', b'e') => return Some("e".into()),
        (b'a', b'i') => return Some("ai".into()),
        (b'a', b'n') => return Some("an".into()),
        (b'a', b'o') => return Some("ao".into()),
        (b'a', b'h') => return Some("ang".into()),
        (b'e', b'i') => return Some("ei".into()),
        (b'e', b'n') => return Some("en".into()),
        (b'e', b'r') => return Some("er".into()),
        (b'e', b'g') => return Some("eng".into()),
        (b'o', b'u') => return Some("ou".into()),
        _ => {}
    }

    let ini: &str = match a {
        b'v' => "zh",
        b'i' => "ch",
        b'u' => "sh",
        b'b' => "b",
        b'p' => "p",
        b'm' => "m",
        b'f' => "f",
        b'd' => "d",
        b't' => "t",
        b'n' => "n",
        b'l' => "l",
        b'g' => "g",
        b'k' => "k",
        b'h' => "h",
        b'j' => "j",
        b'q' => "q",
        b'x' => "x",
        b'r' => "r",
        b'z' => "z",
        b'c' => "c",
        b's' => "s",
        b'y' => "y",
        b'w' => "w",
        _ => return None,
    };

    let fin: &str = match b {
        b'a' => "a",
        b'e' => "e",
        b'i' => "i",
        b'u' => "u",
        b'o' => match a {
            b'b' | b'p' | b'm' | b'f' | b'w' | b'y' => "o",
            _ => "uo",
        },
        b'v' => match a {
            b'n' | b'l' => "v",
            b'j' | b'q' | b'x' | b'y' => "u",
            _ => "ui",
        },
        b'q' => "iu",
        b'w' => match a {
            b'g' | b'k' | b'h' | b'v' | b'i' | b'u' | b'r' => "ua",
            _ => "ia",
        },
        b'r' => "uan",
        b't' => match a {
            b'n' | b'l' => "ve",
            _ => "ue",
        },
        b'y' => match a {
            b'g' | b'k' | b'h' | b'v' | b'i' | b'u' => "uai",
            _ => "ing",
        },
        b'p' => "un",
        b's' => match a {
            b'j' | b'q' | b'x' => "iong",
            _ => "ong",
        },
        b'd' => match a {
            b'g' | b'k' | b'h' | b'v' | b'i' | b'u' => "uang",
            _ => "iang",
        },
        b'f' => "en",
        b'g' => "eng",
        b'h' => "ang",
        b'm' => "ian",
        b'j' => "an",
        b'c' => "iao",
        b'k' => "ao",
        b'l' => "ai",
        b'z' => "ei",
        b'x' => "ie",
        b'b' => "ou",
        b'n' => "in",
        _ => return None,
    };

    let mut out = String::with_capacity(ini.len() + fin.len());
    out.push_str(ini);
    out.push_str(fin);
    Some(out)
}

/// Parse Natural Double Pinyin input (ignoring delimiters `'`) into Zhiyi unit tags.
pub fn zrm_input_to_units(raw_input: &str) -> Vec<(&'static str, String)> {
    let letters: Vec<u8> = raw_input
        .bytes()
        .filter(|b| b.is_ascii_alphabetic())
        .map(|b| b.to_ascii_lowercase())
        .collect();
    let mut units = Vec::with_capacity((letters.len() + 1) / 2);
    let mut i = 0;
    while i + 1 < letters.len() {
        if let Some(syl) = zrm_pair_to_syllable(letters[i], letters[i + 1]) {
            units.push(("f", syl));
        }
        i += 2;
    }
    if i < letters.len() {
        let p = match letters[i] {
            b'v' => "zh".to_string(),
            b'i' => "ch".to_string(),
            b'u' => "sh".to_string(),
            c => (c as char).to_string(),
        };
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
            .split(|c: char| c == ' ' || c == '\'')
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
                let is_initial = k == 1
                    || (k == 2 && b[1] == b'h' && matches!(b[0], b'z' | b'c' | b's'));
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_zrm_edge_cases() {
        assert_eq!(zrm_pair_to_syllable(b'v', b'u').as_deref(), Some("zhu"));
        assert_eq!(zrm_pair_to_syllable(b'v', b'v').as_deref(), Some("zhui"));
        assert_eq!(zrm_pair_to_syllable(b'n', b'v').as_deref(), Some("nv"));
        assert_eq!(zrm_pair_to_syllable(b'l', b't').as_deref(), Some("lve"));
        assert_eq!(zrm_pair_to_syllable(b'j', b't').as_deref(), Some("jue"));
        assert_eq!(zrm_pair_to_syllable(b's', b'o').as_deref(), Some("suo"));
        assert_eq!(zrm_pair_to_syllable(b'b', b'o').as_deref(), Some("bo"));
        assert_eq!(zrm_pair_to_syllable(b'y', b'o').as_deref(), Some("yo"));
        assert_eq!(zrm_pair_to_syllable(b'r', b'w').as_deref(), Some("rua"));
        assert_eq!(zrm_pair_to_syllable(b'a', b'h').as_deref(), Some("ang"));
        assert_eq!(zrm_pair_to_syllable(b'e', b'g').as_deref(), Some("eng"));
    }
}
