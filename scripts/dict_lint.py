#!/usr/bin/env python3
"""
Standalone dictionary linter, rules SSOT validator, idempotency verifier,
homophone collision advisor, and CI diff-budget circuit breaker for rime-chth1z.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import re
import subprocess

import build_cn_en
import dict_common
import dict_rules

REPO_ROOT = dict_common.REPO_ROOT

EXTRA_VALID_SYLS = dict_common.EXTRA_VALID_SYLS
ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
ZERO_WIDTH_NO_ZWJ_RE = re.compile(r"[\u200b\u200c\ufeff]")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
LUE_NUE_RE = dict_common.LUE_NUE_RE
CENSORED_STARS_RE = re.compile(r"\*{4,}")
GLUED_COLON_POS_RE = re.compile(
    r"[a-zA-Z0-9]:(?:vbl|n|v|vt|vi|a|adj|ad|adv|prep|conj|pron|num|int|art)\."
)
TRAILING_EMPTY_POS_RE = re.compile(
    r"(?:^|\s)(?:vbl|n|v|vt|vi|a|adj|ad|adv|prep|conj|pron|num|int|art)\.$"
)

MANAGED_EN_FILES = (
    "en_dicts/en.dict.yaml",
    "en_dicts/en_ext.dict.yaml",
    *(f"en_dicts/{fname}" for fname, _ in build_cn_en.CN_EN_FILES),
)

MANAGED_OPENCC_FILES = (
    "opencc/chinese_english.txt",
    "opencc/english_chinese.txt",
    "opencc/emoji.txt",
    "opencc/others.txt",
)

ALL_MANAGED_FILES: tuple[str, ...] = (
    *dict_common.ACTIVE_CN_DICTS,
    "cn_dicts/corrections.dict.yaml",
    "cn_dicts_cell/luna.dict.yaml",
    "rime_frost.dict.yaml",
    *MANAGED_EN_FILES,
    *MANAGED_OPENCC_FILES,
)

EXTRA_HYGIENE_FILES: tuple[str, ...] = (
    "melt_eng.schema.yaml",
    "melt_eng.dict.yaml",
    "custom_phrase.txt",
)

DISABLED_UPSTREAM_DICTS: set[str] = {
    "cn_dicts/41448.dict.yaml",
    "cn_dicts/GB18030-2022.dict.yaml",
    "cn_dicts/tencent.dict.yaml",
}

ALLOW_A_CLASS_HIGH_W2: set[tuple[str, str]] = {
    ("公钥", "gong yao"),
    ("密钥", "mi yao"),
    ("介壳虫", "jie ke chong"),
    ("卡死", "ka si"),
}

# Genuine cross-domain homographs whose readings legitimately differ across active CN dicts
CROSS_DICT_HOMOGRAPH_ALLOWLIST: frozenset[str] = frozenset({
    "起着", "闲着", "停着", "应着",  # base (着 zhe) vs chess2 (棋着 zhao)
    "重炮",                          # base (heavy artillery zhong) vs chess (double cannon chong)
    "民乐",                          # base (folk music yue) vs place (Minle County/Station le)
    "两行",                          # base (two lines hang) vs literature (two columns/marching xing)
    "测度",                          # base (conjecture duo) vs shulihua (measure theory du)
    "得治",                          # base (must treat dei) vs medication (be cured de)
    "千石",                          # base (1000 dan salary) vs name2 (Japanese surname Sengoku shi)
    "乐友",                          # base (music lover yue) vs medication (brand/term le)
    "正角",                          # base (opera lead role jue) vs shulihua (positive angle jiao)
    "阳夏",                          # geography (Qin/Han county yang jia) vs history (1911 Battle of Yangxia yang xia)
})

_split_header_body = dict_common.split_header_body_with_lineno


def _sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def _sha256(path: pathlib.Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _load_valid_syls(root: pathlib.Path, errors: list[str] | None = None) -> set[str]:
    return dict_common.load_valid_syls(root, strict_errors=errors)


def _check_file_hygiene(root: pathlib.Path, rel: str, errors: list[str], require_entry_checks: bool) -> None:
    p = root / rel
    if not p.exists():
        errors.append(f"missing managed file: {rel}")
        return
    raw = p.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        errors.append(f"{rel}: UTF-8 BOM is forbidden")
    if b"\r\n" in raw:
        errors.append(f"{rel}: CRLF line endings detected (must be LF)")
    if rel.endswith(".json") and raw and not raw.endswith(b"\n"):
        errors.append(f"{rel}: missing trailing LF newline")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        errors.append(f"{rel}: invalid UTF-8 ({exc})")
        return

    if not require_entry_checks:
        return

    is_dict = rel.endswith(".dict.yaml")
    is_cn_en = rel.startswith("en_dicts/cn_en")
    allows_emoji_zwj = rel in ("opencc/emoji.txt", "opencc/others.txt")
    lines = text.splitlines()
    start_idx = 1
    if is_dict:
        _, lines, start_idx = _split_header_body(lines)

    for idx, line in enumerate(lines, start_idx):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if CONTROL_CHAR_RE.search(line):
            errors.append(f"{rel}:{idx}: C0/C1 control character in entry")
        if "\u3000" in line:
            errors.append(f"{rel}:{idx}: full-width space U+3000 in entry")
        if allows_emoji_zwj:
            key_part = line.split("\t", 1)[0]
            if ZERO_WIDTH_RE.search(key_part) or ZERO_WIDTH_NO_ZWJ_RE.search(line):
                errors.append(f"{rel}:{idx}: zero-width character in entry")
        elif ZERO_WIDTH_RE.search(line):
            errors.append(f"{rel}:{idx}: zero-width character in entry")
        if is_dict or is_cn_en:
            if "\t\t" in line:
                errors.append(f"{rel}:{idx}: consecutive tabs (empty column) in entry")
            cols = line.split("\t")
            if len(cols) < 2 and rel != "rime_frost.dict.yaml":
                errors.append(f"{rel}:{idx}: missing tab delimiter")
                continue
            if len(cols) >= 2:
                if not cols[0] or not cols[1]:
                    errors.append(f"{rel}:{idx}: empty text or code column")
                if any(c != c.strip() for c in cols[:2]):
                    errors.append(f"{rel}:{idx}: leading/trailing whitespace in text or code")
                if "  " in cols[1]:
                    errors.append(f"{rel}:{idx}: double space inside code column '{cols[1]}'")
                for col_i in range(2, len(cols)):
                    if cols[col_i] != cols[col_i].rstrip(" "):
                        errors.append(f"{rel}:{idx}: trailing whitespace in column {col_i + 1}")
                    if col_i == 2 and cols[2] != cols[2].strip():
                        errors.append(f"{rel}:{idx}: leading/trailing whitespace in weight column")


def check_hygiene(root: pathlib.Path, errors: list[str]) -> None:
    """Check UTF-8 no BOM, LF line endings, and clean whitespace on all managed + owned config files."""
    for rel in ALL_MANAGED_FILES:
        _check_file_hygiene(root, rel, errors, require_entry_checks=True)
    for rel in EXTRA_HYGIENE_FILES:
        if (root / rel).exists():
            _check_file_hygiene(root, rel, errors, require_entry_checks=False)
    occ_dir = root / "opencc"
    if occ_dir.exists():
        for jf in sorted(occ_dir.glob("*.json")):
            _check_file_hygiene(root, f"opencc/{jf.name}", errors, require_entry_checks=False)


def _is_allowed_cross_dict_variant(
    word: str,
    pys: set[str],
    dual_reading_words: set[str],
) -> bool:
    if len(word) < 2 or word in dual_reading_words or word in CROSS_DICT_HOMOGRAPH_ALLOWLIST:
        return True
    py_list = [p.split() for p in pys]
    w_nodot = word.replace("·", "")
    if any(len(s) != len(w_nodot) for s in py_list):
        return False
    ref = py_list[0]
    for other in py_list[1:]:
        for ch, s1, s2 in zip(w_nodot, ref, other):
            if s1 == s2:
                continue
            pair = {s1, s2}
            if ch == "谁" and pair == {"shei", "shui"}:
                continue
            if ch == "血" and pair == {"xue", "xie"}:
                continue
            return False
    return True


def check_cn_invariants(
    root: pathlib.Path,
    valid_syls: set[str],
    ruleset: dict_rules.RuleSet,
    errors: list[str],
    warnings: list[str],
) -> tuple[dict, set[tuple[str, str]], dict[str, list[tuple[str, int, str]]]]:
    """Verify the CN invariants, cross-dict phonetic consistency, and corrections.dict.yaml contract."""
    invalid_syls: list[tuple] = []
    len_mismatches: list[tuple] = []
    lue_nue: list[tuple] = []
    within_dups = 0
    cross_dups = 0
    active_keys: set[tuple[str, str]] = set()
    code_index: dict[str, list[tuple[str, int, str]]] = {}
    word_readings_active: dict[str, list[tuple[str, str, int]]] = {}
    active_entry_count = 0

    cn_files = (*dict_common.ACTIVE_CN_DICTS, "cn_dicts/corrections.dict.yaml", "cn_dicts_cell/luna.dict.yaml")
    for rel in cn_files:
        p = root / rel
        if not p.exists():
            continue
        is_corr = rel == "cn_dicts/corrections.dict.yaml"
        is_luna = rel == "cn_dicts_cell/luna.dict.yaml"
        _, body, start_idx = _split_header_body(p.read_text(encoding="utf-8").splitlines())
        local_seen: set[tuple[str, str]] = set()

        for idx, line in enumerate(body, start_idx):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) < 2:
                continue
            w, py = cols[0], cols[1]
            wt_s = cols[2] if len(cols) >= 3 else ""

            if LUE_NUE_RE.search(py):
                lue_nue.append((rel, idx, w, py))
            syls = py.split()
            w_nodot = w.replace("·", "")
            if not w_nodot or not syls:
                errors.append(f"{rel}:{idx}: empty word or pinyin ('{w}', '{py}')")
            for sy in syls:
                if sy not in valid_syls:
                    invalid_syls.append((rel, idx, w, py, sy))
            if not is_corr and len(syls) != len(w_nodot):
                len_mismatches.append((rel, idx, w, py))

            k = (w, py)
            if k in local_seen:
                within_dups += 1
            local_seen.add(k)

            if not is_corr and not is_luna:
                active_entry_count += 1
                if k in active_keys:
                    cross_dups += 1
                active_keys.add(k)
                try:
                    wt_val = int(wt_s) if wt_s else 0
                except ValueError:
                    errors.append(f"{rel}:{idx}: non-integer weight '{wt_s}'")
                    wt_val = 0
                if wt_val < 0:
                    errors.append(f"{rel}:{idx}: negative weight {wt_val} for ({w}, {py})")
                code_index.setdefault(py, []).append((w, wt_val, rel))
                if rel not in ("cn_dicts/8105.dict.yaml", "cn_dicts/others.dict.yaml"):
                    word_readings_active.setdefault(w, []).append((rel, py, wt_val))

    # Cross-dict same-word reading-conflict check (catches idiom/literature or cell drift)
    dual_reading_words = {dr.word for dr in ruleset.dual_readings}
    cross_reading_conflicts = 0
    for w, items in word_readings_active.items():
        files = {r for r, _, _ in items}
        pys = {py for _, py, _ in items}
        if len(files) > 1 and len(pys) > 1:
            if not _is_allowed_cross_dict_variant(w, pys, dual_reading_words):
                cross_reading_conflicts += 1
                short = [(r.split("/")[-1], py, wt) for r, py, wt in items]
                errors.append(f"cross-dict reading conflict for '{w}': {short}")

    # Spec limit: E1 whitelist total <= 10
    e1_count = sum(1 for r in ruleset.corrections if r.category == "E1") + sum(
        1 for r in ruleset.additions if r.category == "E1"
    )
    if e1_count > dict_rules.E1_MAX_COUNT:
        errors.append(f"E1 whitelist count {e1_count} exceeds limit {dict_rules.E1_MAX_COUNT}")

    # Dedicated corrections.dict.yaml contract + SSOT coverage check (runs after active_keys is fully built)
    managed_corr_keys: set[tuple[str, str]] = {
        (cr.word, cr.wrong_py) for cr in ruleset.corrections
    } | {
        (dr.word, py) for dr in ruleset.dual_readings for py in (dr.py1, dr.py2)
    }
    corr_p = root / "cn_dicts/corrections.dict.yaml"
    corr_entries = 0
    corr_overlap_nonzero = 0
    corr_unmanaged = 0
    if corr_p.exists():
        _, body, start_idx = _split_header_body(corr_p.read_text(encoding="utf-8").splitlines())
        for idx, line in enumerate(body, start_idx):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            cols = line.split("\t")
            corr_entries += 1
            if len(cols) != 4:
                errors.append(f"cn_dicts/corrections.dict.yaml:{idx}: expected 4 columns, got {len(cols)}")
                continue
            w, py, wt_s, cmt = cols
            if (w, py) not in managed_corr_keys:
                corr_unmanaged += 1
                errors.append(
                    f"cn_dicts/corrections.dict.yaml:{idx}: unmanaged entry ({w}, {py}) not declared in rules/corrections.tsv or rules/dual_readings.tsv"
                )
            try:
                wt_val = int(wt_s)
            except ValueError:
                errors.append(f"cn_dicts/corrections.dict.yaml:{idx}: non-integer weight '{wt_s}'")
                continue
            if wt_val < 0:
                errors.append(f"cn_dicts/corrections.dict.yaml:{idx}: negative weight {wt_val}")
            if not cmt.strip():
                errors.append(f"cn_dicts/corrections.dict.yaml:{idx}: empty comment")
            elif len(cmt) > dict_rules.COMMENT_HARD_MAX_LEN:
                errors.append(
                    f"cn_dicts/corrections.dict.yaml:{idx}: comment length {len(cmt)} > {dict_rules.COMMENT_HARD_MAX_LEN} ('{cmt}')"
                )
            elif len(cmt) > dict_rules.COMMENT_WARN_MAX_LEN:
                warnings.append(
                    f"cn_dicts/corrections.dict.yaml:{idx}: comment length {len(cmt)} > {dict_rules.COMMENT_WARN_MAX_LEN} ('{cmt}')"
                )
            if (w, py) in active_keys and wt_val != 0:
                corr_overlap_nonzero += 1
                errors.append(
                    f"cn_dicts/corrections.dict.yaml:{idx}: active overlap ({w}, {py}) must use weight=0, got {wt_val}"
                )

    # Verify dual_readings.tsv declared weights match actual active CN dict weights
    actual_by_file_key: dict[tuple[str, str, str], int] = {}
    for py, entries in code_index.items():
        for w, wt_val, rel in entries:
            actual_by_file_key[(rel, w, py)] = wt_val
    for dr in ruleset.dual_readings:
        for py, decl_w in ((dr.py1, dr.w1), (dr.py2, dr.w2)):
            act = actual_by_file_key.get((dr.target_file, dr.word, py))
            if act is None:
                errors.append(f"{dr.rule_id}: missing ({dr.word}, {py}) in {dr.target_file}")
            elif act != decl_w:
                errors.append(
                    f"{dr.rule_id}: declared weight {decl_w} != actual weight {act} in {dr.target_file} for ({dr.word}, {py})"
                )

    if invalid_syls:
        errors.append(f"invalid_syllables={len(invalid_syls)} (samples: {invalid_syls[:5]})")
    if len_mismatches:
        errors.append(f"len_mismatches={len(len_mismatches)} (samples: {len_mismatches[:5]})")
    if lue_nue:
        errors.append(f"remaining_lue_nue={len(lue_nue)} (samples: {lue_nue[:5]})")
    if within_dups:
        errors.append(f"within_file_dups={within_dups}")
    if cross_dups:
        errors.append(f"cross_file_dups_active_26={cross_dups}")

    stats = {
        "active_cn_entries_excl_corr_luna": active_entry_count,
        "corrections_entries": corr_entries,
        "active_cn_entries_incl_corr": active_entry_count + corr_entries,
        "invalid_syllables": len(invalid_syls),
        "len_mismatches": len(len_mismatches),
        "remaining_lue_nue": len(lue_nue),
        "within_file_dups": within_dups,
        "cross_file_dups_active_26": cross_dups,
        "cross_dict_reading_conflicts": cross_reading_conflicts,
        "corrections_overlap_nonzero": corr_overlap_nonzero,
        "corrections_unmanaged": corr_unmanaged,
        "e1_count": e1_count,
    }
    return stats, active_keys, code_index


def check_en_and_cn_en(
    root: pathlib.Path,
    rules_dir: pathlib.Path,
    errors: list[str],
    valid_syls: set[str] | None = None,
) -> dict:
    """Verify en_dicts/ integrity and 100% parity across all 7 cn_en*.txt layouts."""
    word_seqs: dict[str, list[str]] = {}
    counts: dict[str, int] = {}

    for fname, _ in build_cn_en.CN_EN_FILES:
        rel = f"en_dicts/{fname}"
        p = root / rel
        if not p.exists():
            errors.append(f"missing {rel}")
            continue
        seen: set[tuple[str, str]] = set()
        words: list[str] = []
        for idx, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) < 2:
                errors.append(f"{rel}:{idx}: invalid cn_en entry")
                continue
            w, code = cols[0], cols[1]
            if (w, code) in seen:
                errors.append(f"{rel}:{idx}: duplicate ({w}, {code})")
            seen.add((w, code))
            words.append(w)
        word_seqs[rel] = words
        counts[rel] = len(words)

    if word_seqs:
        ref_rel = "en_dicts/cn_en.txt"
        ref_words = word_seqs.get(ref_rel, [])
        for rel, words in word_seqs.items():
            if rel == ref_rel:
                continue
            if len(words) != len(ref_words):
                errors.append(f"cn_en parity mismatch: {rel} has {len(words)} entries vs {ref_rel} {len(ref_words)}")
            elif words != ref_words:
                for i, (a, b) in enumerate(zip(ref_words, words), 1):
                    if a != b:
                        errors.append(f"cn_en word-order mismatch at entry #{i}: {ref_rel}='{a}' vs {rel}='{b}'")
                        break

    # Verify dry-run of build_cn_en produces 0 changes against rules/cn_en_source.tsv
    cn_en_src = rules_dir / "cn_en_source.tsv"
    if cn_en_src.exists():
        try:
            _, changed = build_cn_en.apply_cn_en_rules(
                root, root, cn_en_src, dry_run=True, valid_syls=valid_syls
            )
            if changed:
                errors.append(f"cn_en tables out of sync with rules/cn_en_source.tsv: {changed}")
        except ValueError as exc:
            errors.append(str(exc))

    # Check en_ext & en no within-file/cross-file duplicates, valid weights, and symbol-code anti-hijack guards
    protected_en_codes: dict[str, set[str]] = {}
    leading_sym_entries: list[tuple[str, int, str, str, str]] = []
    global_en_seen: dict[tuple[str, str], str] = {}
    for rel in ("en_dicts/en_ext.dict.yaml", "en_dicts/en.dict.yaml"):
        p = root / rel
        if not p.exists():
            continue
        _, body, start_idx = _split_header_body(p.read_text(encoding="utf-8").splitlines())
        seen_en: set[tuple[str, str]] = set()
        dup_cnt = 0
        cross_dup_cnt = 0
        for idx, line in enumerate(body, start_idx):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) >= 2:
                w, code = cols[0], cols[1]
                k = (w, code)
                if k in seen_en:
                    dup_cnt += 1
                seen_en.add(k)
                if k in global_en_seen and global_en_seen[k] != rel:
                    cross_dup_cnt += 1
                else:
                    global_en_seen[k] = rel
                if len(cols) >= 3 and cols[2] != "":
                    try:
                        en_wt = int(cols[2])
                        if en_wt < 0:
                            errors.append(f"{rel}:{idx}: negative weight {en_wt} for '{w}'")
                    except ValueError:
                        errors.append(f"{rel}:{idx}: non-integer weight '{cols[2]}' for '{w}'")
                if re.search(r"[^\x21-\x7e]", code):
                    errors.append(
                        f"{rel}:{idx}: non-ASCII or whitespace char in EN code '{code}' for '{w}' "
                        f"(untypeable under ASCII speller/alphabet)"
                    )
                if re.search(r"[^a-zA-Z0-9]", code):
                    stripped = re.sub(r"[^a-zA-Z0-9]", "", code)
                    if len(stripped) <= 1:
                        errors.append(
                            f"{rel}:{idx}: symbol code '{code}' for '{w}' collapses to <=1 alnum char "
                            f"('{stripped}') under melt_eng algebra; use safe ASCII code in en_ext + "
                            f"rules/cn_en_source.tsv (emit_lower=false)"
                        )
                    elif re.match(r"^[^a-zA-Z0-9]", code):
                        leading_sym_entries.append((rel, idx, w, code, stripped.lower()))
                else:
                    is_base = rel == "en_dicts/en.dict.yaml"
                    is_weighted = len(cols) >= 3 and cols[2].isdigit() and int(cols[2]) > 1
                    if is_base or is_weighted:
                        protected_en_codes.setdefault(code.lower(), set()).add(w)
        if dup_cnt:
            errors.append(f"{rel}: {dup_cnt} within-file duplicates")
        if cross_dup_cnt:
            errors.append(f"{rel}: {cross_dup_cnt} cross-file duplicates with en_ext.dict.yaml")

    for rel, idx, w, code, stripped_lower in leading_sym_entries:
        colliding_words = protected_en_codes.get(stripped_lower, set()) - {w}
        if colliding_words:
            errors.append(
                f"{rel}:{idx}: leading-symbol code '{code}' for '{w}' strips to '{stripped_lower}' "
                f"which collides with protected EN word(s) {sorted(colliding_words)} and hijacks via librime "
                f"per-key weight normalization; keep plain code/weight or route Chinese phonetic via rules/cn_en_source.tsv"
            )

    # Guard MSPY/Sogou ü(v) -> y mapping consistency in build_cn_en.py
    for sch in ("mspy", "sogou"):
        if build_cn_en.syl_to_shuangpin("nv", sch) != "ny" or build_cn_en.syl_to_shuangpin("lv", sch) != "ly":
            errors.append(f"build_cn_en.py: {sch} must map nv/lv -> ny/ly (ü -> y)")

    return {"cn_en_entry_counts": counts}


def _collect_opencc_json_files(obj) -> list[str]:
    files: list[str] = []
    if isinstance(obj, dict):
        if "file" in obj and isinstance(obj["file"], str):
            files.append(obj["file"])
        for v in obj.values():
            files.extend(_collect_opencc_json_files(v))
    elif isinstance(obj, list):
        for x in obj:
            files.extend(_collect_opencc_json_files(x))
    return files


def _load_yaml_unique_keys(yaml_mod, text: str, label: str, errors: list[str]):
    """Load YAML with SafeLoader while flagging any duplicate mapping keys."""

    class _UniqueKeyLoader(yaml_mod.SafeLoader):
        pass

    def _construct_mapping(loader, node, deep=False):
        seen: set = set()
        for key_node, _ in node.value:
            k = loader.construct_object(key_node, deep=deep)
            if k in seen:
                line_no = getattr(key_node.start_mark, "line", 0) + 1
                errors.append(f"{label}:{line_no}: duplicate YAML key {k!r}")
            seen.add(k)
        return loader.construct_mapping(node, deep=deep)

    _UniqueKeyLoader.add_constructor(
        yaml_mod.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
    )
    return yaml_mod.load(text, Loader=_UniqueKeyLoader)


def check_schema_and_opencc(
    root: pathlib.Path,
    errors: list[str],
    warnings: list[str],
    strict: bool = False,
) -> None:
    """Verify rime_frost.dict.yaml import_tables parity, OpenCC JSON/TXT quality, and YAML schemas."""
    rf = root / "rime_frost.dict.yaml"
    disabled_tables = (
        "- cn_dicts/41448",
        "- cn_dicts/GB18030-2022",
        "- cn_dicts/tencent",
        "- cn_dicts_cell/luna",
    )
    if rf.exists():
        for idx, line in enumerate(rf.read_text(encoding="utf-8").splitlines(), 1):
            s = line.strip()
            for pref in disabled_tables:
                if s == pref or s.startswith(pref + " ") or s.startswith(pref + "\t"):
                    errors.append(f"rime_frost.dict.yaml:{idx}: {pref[2:]} must remain disabled")

    occ_dir = root / "opencc"
    if occ_dir.exists():
        for jf in sorted(occ_dir.glob("*.json")):
            try:
                doc = json.loads(jf.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"opencc/{jf.name}: invalid JSON ({exc})")
                continue
            for ref_file in _collect_opencc_json_files(doc):
                if not (occ_dir / ref_file).exists():
                    errors.append(f"opencc/{jf.name}: referenced dictionary file 'opencc/{ref_file}' does not exist")
            stack = [doc]
            while stack:
                node = stack.pop()
                if isinstance(node, dict):
                    if node.get("type") == "group":
                        mp = node.get("match_policy")
                        if mp not in ("short_circuit", "union"):
                            errors.append(
                                f"opencc/{jf.name}: group dict missing valid 'match_policy' (expected 'short_circuit' or 'union')"
                            )
                    stack.extend(node.values())
                elif isinstance(node, list):
                    stack.extend(node)

        for rel in MANAGED_OPENCC_FILES:
            p = root / rel
            if not p.exists():
                continue
            seen_keys: set[str] = set()
            is_ec = rel == "opencc/english_chinese.txt"
            is_emoji_like = rel in ("opencc/emoji.txt", "opencc/others.txt")
            check_first_tok = rel in (
                "opencc/chinese_english.txt",
                "opencc/english_chinese.txt",
                "opencc/emoji.txt",
            )
            for idx, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                if "\t" not in line:
                    errors.append(f"{rel}:{idx}: missing tab separator in OpenCC table")
                    continue
                if line != line.rstrip(" "):
                    errors.append(f"{rel}:{idx}: trailing space in OpenCC entry")
                k, v = line.split("\t", 1)
                if not k or not v.strip():
                    errors.append(f"{rel}:{idx}: empty key or value in OpenCC entry")
                if k in seen_keys:
                    errors.append(f"{rel}:{idx}: duplicate key '{k}'")
                seen_keys.add(k)
                if "  " in v:
                    errors.append(f"{rel}:{idx}: double space in value for '{k}'")
                if CENSORED_STARS_RE.search(v):
                    errors.append(f"{rel}:{idx}: censored '****' token in value for '{k}'")
                toks = v.split(" ")
                if check_first_tok and not k.startswith("----------") and toks and toks[0] != k:
                    errors.append(f"{rel}:{idx}: first value token '{toks[0]}' != key '{k}'")
                if is_ec:
                    if " " in k:
                        errors.append(f"{rel}:{idx}: whitespace in english_chinese key '{k}'")
                    if re.search(r"\sNUM$", v):
                        errors.append(f"{rel}:{idx}: stray trailing NUM in value for '{k}'")
                    if "计算机]" in v:
                        errors.append(f"{rel}:{idx}: corrupted '计算机]' tag in value for '{k}'")
                    if GLUED_COLON_POS_RE.search(v):
                        errors.append(f"{rel}:{idx}: glued entry/POS token in value for '{k}'")
                    if TRAILING_EMPTY_POS_RE.search(v):
                        errors.append(f"{rel}:{idx}: trailing empty POS tag in value for '{k}'")
                if is_emoji_like and not k.startswith("----------"):
                    seen_toks: set[str] = set()
                    seen_vs16_base: dict[str, str] = {}
                    for t in toks:
                        if t in seen_toks:
                            errors.append(f"{rel}:{idx}: duplicate token '{t}' for '{k}'")
                        seen_toks.add(t)
                        # Detect VS16 vs bare duplicate pairs (allowing intentional VS16 vs VS15 \ufe0e pairs)
                        if "\ufe0e" not in t:
                            base = t.replace("\ufe0f", "")
                            prev = seen_vs16_base.get(base)
                            if prev is not None and prev != t:
                                errors.append(
                                    f"{rel}:{idx}: duplicate VS16/non-VS16 token pair ('{prev}', '{t}') for '{k}'"
                                )
                            seen_vs16_base[base] = t

    # Guard against unmanaged new upstream dictionary files
    known_dict_files = set(ALL_MANAGED_FILES) | DISABLED_UPSTREAM_DICTS
    for sub, pat in (("cn_dicts", "*.dict.yaml"), ("cn_dicts_cell", "*.dict.yaml"), ("en_dicts", "*.dict.yaml"), ("en_dicts", "cn_en*.txt")):
        sub_dir = root / sub
        if not sub_dir.exists():
            continue
        for f in sorted(sub_dir.glob(pat)):
            rel = f"{sub}/{f.name}"
            if rel not in known_dict_files:
                errors.append(f"unmanaged dictionary file detected: {rel} (must be added to clean-dicts.py & dict_lint.py or explicitly excluded)")

    # PyYAML syntax & schema invariant verification for root, profile, and theme YAML files
    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None
    if yaml is None:
        msg = "PyYAML is not installed; cannot run YAML syntax, rime_frost import_tables, melt_eng order, spelling_hints, and symbols_v guards (install pyyaml)"
        if strict:
            errors.append(msg)
        else:
            warnings.append(msg)
    if yaml is not None:
        # Verify rime_frost.dict.yaml import_tables exact parity (set + order) with ACTIVE_CN_DICTS and disk existence
        if rf.exists():
            rf_hdr, _, _ = _split_header_body(rf.read_text(encoding="utf-8").splitlines())
            try:
                rf_doc = yaml.safe_load("\n".join(rf_hdr)) or {}
            except Exception as exc:
                errors.append(f"rime_frost.dict.yaml: invalid YAML header ({exc})")
                rf_doc = {}
            imp = rf_doc.get("import_tables") or []
            if not isinstance(imp, list):
                errors.append("rime_frost.dict.yaml: import_tables must be a list")
            else:
                imp_files = [f"{t}.dict.yaml" for t in imp]
                for rel_t in imp_files:
                    if not (root / rel_t).exists():
                        errors.append(f"rime_frost.dict.yaml: imported table '{rel_t}' does not exist on disk")
                if "cn_dicts/corrections.dict.yaml" not in imp_files:
                    errors.append("rime_frost.dict.yaml: cn_dicts/corrections must be enabled in import_tables")
                active_imp = [f for f in imp_files if f != "cn_dicts/corrections.dict.yaml"]
                expected_active = list(dict_common.ACTIVE_CN_DICTS)
                if active_imp != expected_active:
                    if set(active_imp) != set(expected_active):
                        missing = sorted(set(expected_active) - set(active_imp))
                        extra = sorted(set(active_imp) - set(expected_active))
                        errors.append(
                            f"rime_frost.dict.yaml: import_tables set mismatch vs ACTIVE_CN_DICTS (missing={missing}, extra={extra})"
                        )
                    else:
                        errors.append(
                            "rime_frost.dict.yaml: import_tables order differs from dict_common.ACTIVE_CN_DICTS"
                        )

        yaml_files = (
            [p for p in sorted(root.glob("*.yaml")) if not p.name.endswith(".dict.yaml")]
            + sorted((root / "profiles").glob("*.yaml"))
            + sorted((root / "themes").glob("*.yaml"))
        )
        for yf in yaml_files:
            rel_y = yf.relative_to(root).as_posix()
            raw_y = yf.read_bytes()
            if raw_y.startswith(b"\xef\xbb\xbf"):
                errors.append(f"{rel_y}: UTF-8 BOM is forbidden")
            try:
                yaml.safe_load(raw_y.decode("utf-8"))
            except Exception as exc:
                errors.append(f"{rel_y}: invalid YAML ({exc})")

        # Guard melt_eng FP+ZRM parity and algebra pipeline order (pre -> CN -> post)
        me_schema = root / "melt_eng.schema.yaml"
        me_common = root / "melt_eng_algebra_common.yaml"
        if me_schema.exists():
            me_doc = yaml.safe_load(me_schema.read_text(encoding="utf-8")) or {}
            alg_ref = (me_doc.get("speller") or {}).get("algebra", {})
            inc = alg_ref.get("__include") if isinstance(alg_ref, dict) else None
            if inc != "melt_eng_algebra:/algebra_fp_zrm":
                errors.append(
                    f"melt_eng.schema.yaml: speller/algebra/__include must be 'melt_eng_algebra:/algebra_fp_zrm' "
                    f"(got {inc!r}) so Full Pinyin and Natural Double Pinyin remain equal first-class schemas"
                )
        if me_common.exists():
            mc_doc = yaml.safe_load(me_common.read_text(encoding="utf-8")) or {}
            pre_rules = mc_doc.get("algebra_common_pre") or []
            post_rules = mc_doc.get("algebra_common_post") or []
            erase_rules = {"erase/^[^a-zA-Z0-9].+$/", "erase/[^a-zA-Z]/"}
            bad_pre = [r for r in pre_rules if r in erase_rules]
            if bad_pre:
                errors.append(
                    f"melt_eng_algebra_common.yaml: {bad_pre[0]} must not be in algebra_common_pre "
                    "(breaks Chinese phonetic derivation for leading-symbol entries like .gitignore/.DS_Store)"
                )
            if not any(r in post_rules for r in erase_rules):
                errors.append(
                    "melt_eng_algebra_common.yaml: algebra_common_post must contain erase/[^a-zA-Z]/ (or erase/^[^a-zA-Z0-9].+$/)"
                )
            for k, v in mc_doc.items():
                if isinstance(v, dict) and "__include" in v and ":" not in str(v["__include"]):
                    errors.append(
                        f"melt_eng_algebra_common.yaml: key '{k}' has self-file __include '{v['__include']}' "
                        "(triggers librime circular-dependency warnings)"
                    )
        me_alg = root / "melt_eng_algebra.yaml"
        if me_alg.exists():
            ma_doc = yaml.safe_load(me_alg.read_text(encoding="utf-8")) or {}
            for k, v in ma_doc.items():
                if isinstance(v, dict) and "__include" in v and ":" not in str(v["__include"]):
                    errors.append(
                        f"melt_eng_algebra.yaml: key '{k}' has self-file __include '{v['__include']}' "
                        "(triggers librime circular-dependency warnings)"
                    )

        # Guard translator/spelling_hints >= max syllable length in cn_dicts/corrections.dict.yaml
        corr_p = root / "cn_dicts/corrections.dict.yaml"
        max_corr_syls = 0
        max_corr_sample = ""
        if corr_p.exists():
            _, corr_body, _ = _split_header_body(corr_p.read_text(encoding="utf-8").splitlines())
            for line in corr_body:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                cols = line.split("\t")
                if len(cols) >= 4:
                    n_syl = len(cols[1].split())
                    if n_syl > max_corr_syls:
                        max_corr_syls = n_syl
                        max_corr_sample = cols[0]
        if max_corr_syls > 0:
            for sc_rel in ("rime_frost.schema.yaml", "rime_frost_double_pinyin.schema.yaml"):
                sc_p = root / sc_rel
                if not sc_p.exists():
                    continue
                sc_doc = yaml.safe_load(sc_p.read_text(encoding="utf-8")) or {}
                sh = (sc_doc.get("translator") or {}).get("spelling_hints")
                if not isinstance(sh, int) or sh < max_corr_syls:
                    errors.append(
                        f"{sc_rel}: translator/spelling_hints={sh!r} < max corrections syllable count "
                        f"{max_corr_syls} ('{max_corr_sample}'); comments on longer corrections will be dropped"
                    )

        # Guard symbols_v.yaml: unique YAML keys, /vs calculator-prefix guard, punct regex reachability, no dup items
        sym_p = root / "symbols_v.yaml"
        if sym_p.exists():
            try:
                sym_doc = _load_yaml_unique_keys(yaml, sym_p.read_text(encoding="utf-8"), "symbols_v.yaml", errors) or {}
            except Exception as exc:
                errors.append(f"symbols_v.yaml: failed to parse YAML ({exc})")
                sym_doc = {}
            sym_map = sym_doc.get("symbols") or {}
            punct_pats = []
            for sc_rel in ("rime_frost.schema.yaml", "rime_frost_double_pinyin.schema.yaml"):
                sc_p = root / sc_rel
                if sc_p.exists():
                    sc_doc = yaml.safe_load(sc_p.read_text(encoding="utf-8")) or {}
                    pat = ((sc_doc.get("recognizer") or {}).get("patterns") or {}).get("punct")
                    if pat:
                        punct_pats.append((sc_rel, re.compile(pat)))
            for sk, vals in sym_map.items():
                sk_s = str(sk)
                if sk_s.startswith("/vs"):
                    errors.append(
                        f"symbols_v.yaml: key '{sk_s}' collides with calculator prefix '/vs'"
                    )
                for sc_rel, pat_re in punct_pats:
                    if not pat_re.match(sk_s):
                        errors.append(
                            f"symbols_v.yaml: key '{sk_s}' does not match {sc_rel} recognizer/patterns/punct "
                            f"'{pat_re.pattern}' (unreachable)"
                        )
                if isinstance(vals, list):
                    seen_v: set[str] = set()
                    for v in vals:
                        vs = str(v)
                        if vs in seen_v:
                            errors.append(f"symbols_v.yaml: duplicate item '{vs}' under key '{sk_s}'")
                        seen_v.add(vs)


def _load_clean_dicts_module(root: pathlib.Path):
    cleaner_path = root / "scripts/clean-dicts.py"
    if not cleaner_path.exists():
        cleaner_path = REPO_ROOT / "scripts/clean-dicts.py"
    spec = importlib.util.spec_from_file_location("_rime_clean_dicts_idemp", cleaner_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load cleaner module from {cleaner_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_idempotency(root: pathlib.Path, rules_dir: pathlib.Path, errors: list[str]) -> dict:
    """Run clean-dicts.py in-memory (no disk writes) and assert 0 SHA-256 diffs and 0 pass-2 churn."""
    try:
        cleaner_mod = _load_clean_dicts_module(root)
        manifest, out_buffers = cleaner_mod.run_pipeline(root, root, rules_dir, write=False)
    except Exception as exc:
        errors.append(f"idempotency clean-dicts.py failed: {exc}")
        return {"checked_files": 0, "diffs": ["<cleaner failed>"]}

    diffs: list[str] = []
    checked = 0
    for rel in ALL_MANAGED_FILES:
        src = root / rel
        if not src.exists():
            continue
        checked += 1
        h_before = _sha256(src)
        buf = out_buffers.get(rel)
        if buf is None:
            errors.append(f"idempotency: cleaner did not emit buffer for managed file '{rel}'")
            diffs.append(rel)
            continue
        h_after = _sha256_bytes(buf.encode("utf-8"))
        if h_after != h_before:
            diffs.append(rel)
    if diffs:
        errors.append(f"idempotency failed: {len(diffs)} file(s) changed on pass 2: {diffs}")

    # Assert zero pass-2 ping-pong churn counters across managed files
    churn_keys = (
        "reweighted", "fixed_py", "fixed_word_or_trad", "deleted_boilerplate_or_spam",
        "deleted_noise_or_typo", "deleted_wrong_py", "added",
        "rules_deleted", "rules_word_fixed", "rules_py_fixed", "rules_reweighted", "rules_added",
        "rules_corr_updated", "rules_corr_added", "dedup_within_file", "dedup_cross_file",
        "dedup_weight_promoted", "fixed", "deleted", "normalized", "overlay_fixed",
    )
    churn_hits: dict[str, dict[str, int]] = {}
    for rel, st in manifest.get("files", {}).items():
        nonzero = {k: st[k] for k in churn_keys if st.get(k, 0)}
        if nonzero:
            churn_hits[rel] = nonzero
    if churn_hits:
        errors.append(f"idempotency pass-2 ping-pong detected (non-zero churn counters): {churn_hits}")

    return {
        "checked_files": checked,
        "diffs": diffs,
        "churn": churn_hits,
        "rules_manifest": manifest.get("rules", {}),
    }


def check_collisions(
    ruleset: dict_rules.RuleSet,
    code_index: dict[str, list[tuple[str, int, str]]],
    errors: list[str],
    warnings: list[str],
) -> list[dict]:
    """Inspect top-5 homophones for every rule in rules/ affecting Chinese codes."""
    report: list[dict] = []

    def _top5(py: str) -> list[tuple[str, int, str]]:
        return sorted(code_index.get(py, []), key=lambda x: -x[1])[:5]

    COMMON_HOMOPHONE_THRESHOLD = 50

    for cr in ruleset.corrections:
        top = _top5(cr.wrong_py)
        top_non_self = [x for x in top if x[0] != cr.word]
        entry = {
            "source": cr.rule_id,
            "category": cr.category,
            "word": cr.word,
            "code": cr.wrong_py,
            "weight": cr.weight,
            "top5_active": [[w, wt] for w, wt, _ in top],
        }
        report.append(entry)
        if (
            cr.category in {"B", "C"}
            and top_non_self
            and top_non_self[0][1] >= COMMON_HOMOPHONE_THRESHOLD
            and cr.weight >= top_non_self[0][1]
            and cr.weight > 0
        ):
            errors.append(
                f"collision guard: {cr.rule_id} weight {cr.weight} >= top common active homophone '{top_non_self[0][0]}' ({top_non_self[0][1]})"
            )
        if cr.category == "E1" and top_non_self and cr.weight > max(1, top_non_self[0][1] // 20):
            warnings.append(
                f"collision guard: E1 {cr.rule_id} weight {cr.weight} > top1/20 ({top_non_self[0][0]}={top_non_self[0][1]})"
            )

    for ar in ruleset.additions:
        top = _top5(ar.py)
        top_non_self = [x for x in top if x[0] != ar.word]
        report.append(
            {
                "source": ar.rule_id,
                "category": ar.category,
                "word": ar.word,
                "code": ar.py,
                "weight": ar.weight,
                "top5_active": [[w, wt] for w, wt, _ in top],
            }
        )
        if ar.category == "E1" and top_non_self and ar.weight > max(1, top_non_self[0][1] // 20):
            warnings.append(
                f"collision guard: E1 {ar.rule_id} weight {ar.weight} > top1/20 ({top_non_self[0][0]}={top_non_self[0][1]})"
            )

    for wr in ruleset.weights:
        top = _top5(wr.py)
        report.append(
            {
                "source": wr.rule_id,
                "category": "weight",
                "word": wr.word,
                "code": wr.py,
                "weight": wr.weight,
                "top5_active": [[w, wt] for w, wt, _ in top],
            }
        )

    for dr in ruleset.dual_readings:
        for idx_py, (py, wt) in enumerate(((dr.py1, dr.w1), (dr.py2, dr.w2))):
            top = _top5(py)
            top_non_self = [x for x in top if x[0] != dr.word]
            report.append(
                {
                    "source": dr.rule_id,
                    "category": "A",
                    "word": dr.word,
                    "code": py,
                    "weight": wt,
                    "top5_active": [[w, wt_v] for w, wt_v, _ in top],
                }
            )
            if (
                idx_py == 1
                and top_non_self
                and top_non_self[0][1] >= COMMON_HOMOPHONE_THRESHOLD
                and wt >= top_non_self[0][1]
                and (dr.word, py) not in ALLOW_A_CLASS_HIGH_W2
            ):
                msg = (
                    f"collision guard: A-class py2 {dr.rule_id} weight {wt} >= top common active homophone "
                    f"'{top_non_self[0][0]}' ({top_non_self[0][1]})"
                )
                if wt >= 500:
                    errors.append(msg)
                else:
                    warnings.append(msg)

    return report


def _git_show_lines(root: pathlib.Path, rel: str) -> list[str] | None:
    proc = subprocess.run(
        ["git", "show", f"HEAD:{rel}"],
        cwd=str(root),
        capture_output=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="replace").splitlines()


def _entry_set(lines: list[str], is_dict: bool = True) -> set[str]:
    body = _split_header_body(lines)[1] if is_dict else lines
    return {l for l in body if l.strip() and not l.strip().startswith("#") and "\t" in l}


def check_diff_budget(
    root: pathlib.Path,
    max_active_delta: int,
    max_corrections_delta: int,
    max_cn_en_delta: int,
) -> dict:
    """Compare current working tree vs HEAD using symmetric differences for CI circuit-breaker decisions."""
    active_before = 0
    active_after = 0
    active_symdiff = 0
    for rel in (*dict_common.ACTIVE_CN_DICTS, "cn_dicts/corrections.dict.yaml"):
        head_lines = _git_show_lines(root, rel) or []
        cur_p = root / rel
        cur_lines = cur_p.read_text(encoding="utf-8").splitlines() if cur_p.exists() else []
        head_set = _entry_set(head_lines, True)
        cur_set = _entry_set(cur_lines, True)
        active_before += len(head_set)
        active_after += len(cur_set)
        active_symdiff += len(head_set ^ cur_set)
    active_delta = active_after - active_before

    corr_head = _git_show_lines(root, "cn_dicts/corrections.dict.yaml") or []
    corr_cur = (root / "cn_dicts/corrections.dict.yaml").read_text(encoding="utf-8").splitlines()
    corr_changed = len(_entry_set(corr_head, True) ^ _entry_set(corr_cur, True))

    cn_en_per_file: dict[str, int] = {}
    for fname, _ in build_cn_en.CN_EN_FILES:
        rel = f"en_dicts/{fname}"
        ce_head = _git_show_lines(root, rel) or []
        ce_p = root / rel
        ce_cur = ce_p.read_text(encoding="utf-8").splitlines() if ce_p.exists() else []
        cn_en_per_file[rel] = len(_entry_set(ce_head, False) ^ _entry_set(ce_cur, False))
    cn_en_changed = max(cn_en_per_file.values()) if cn_en_per_file else 0
    cn_en_total_symdiff = sum(cn_en_per_file.values())

    reasons: list[str] = []
    if active_symdiff > max_active_delta:
        reasons.append(f"active_cn_symdiff={active_symdiff} exceeds {max_active_delta} (net={active_delta:+d})")
    if corr_changed > max_corrections_delta:
        reasons.append(f"corrections_changed_entries={corr_changed} exceeds {max_corrections_delta}")
    if cn_en_changed > max_cn_en_delta:
        reasons.append(
            f"cn_en_max_file_symdiff={cn_en_changed} exceeds {max_cn_en_delta} (all_7_total={cn_en_total_symdiff})"
        )

    needs_review = len(reasons) > 0
    summary = (
        f"active_cn={active_before:,}->{active_after:,} (net={active_delta:+,}, symdiff={active_symdiff:,}), "
        f"corrections_symdiff={corr_changed}, cn_en_max_symdiff={cn_en_changed} (all7={cn_en_total_symdiff})"
    )
    return {
        "active_cn_before": active_before,
        "active_cn_after": active_after,
        "active_cn_net_delta": active_delta,
        "active_cn_symdiff": active_symdiff,
        "corrections_changed_entries": corr_changed,
        "cn_en_changed_entries": cn_en_changed,
        "cn_en_total_symdiff": cn_en_total_symdiff,
        "cn_en_per_file_symdiff": cn_en_per_file,
        "needs_review": needs_review,
        "reasons": reasons,
        "summary": summary,
    }


def _write_github_output(path: pathlib.Path, kv: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for k, v in kv.items():
            safe_v = str(v).replace("\r", " ").replace("\n", " ")
            fh.write(f"{k}={safe_v}\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Lint rime-chth1z dictionaries, rules/ SSOT, idempotency, and CI diff budget.")
    ap.add_argument("--root", type=pathlib.Path, default=REPO_ROOT)
    ap.add_argument("--rules-dir", type=pathlib.Path, default=None)
    ap.add_argument("--strict", action="store_true", help="Run all hygiene, invariant, parity, and rules SSOT checks")
    ap.add_argument("--idempotent", action="store_true", help="Run pass-2 in-memory SHA-256 idempotency verification")
    ap.add_argument("--check-collisions", action="store_true", help="Audit top-5 homophone collisions for rules/ entries")
    ap.add_argument("--diff-budget", action="store_true", help="Compute working-tree vs HEAD diff budget for CI circuit breaker")
    ap.add_argument("--max-active-delta", type=int, default=5000)
    ap.add_argument("--max-corrections-delta", type=int, default=50)
    ap.add_argument("--max-cn-en-delta", type=int, default=200)
    ap.add_argument("--github-output", type=pathlib.Path, default=None)
    ap.add_argument("--json", dest="json_out", type=pathlib.Path, default=None)
    args = ap.parse_args()

    root = args.root.resolve()
    rules_dir = (args.rules_dir or (root / "rules")).resolve()

    errors: list[str] = []
    warnings: list[str] = []

    valid_syls = _load_valid_syls(root, errors=errors)
    ruleset = dict_rules.load_ruleset(rules_dir, valid_syls=valid_syls)
    errors.extend(ruleset.errors)
    warnings.extend(ruleset.warnings)

    check_hygiene(root, errors)
    cn_stats, _, code_index = check_cn_invariants(root, valid_syls, ruleset, errors, warnings)
    en_stats = check_en_and_cn_en(root, rules_dir, errors, valid_syls=valid_syls)
    check_schema_and_opencc(root, errors, warnings, strict=args.strict)

    idemp_stats = None
    if args.idempotent:
        idemp_stats = check_idempotency(root, rules_dir, errors)

    collision_report = None
    if args.check_collisions:
        collision_report = check_collisions(ruleset, code_index, errors, warnings)

    if args.strict and warnings:
        errors.extend(f"strict-mode warning: {w}" for w in warnings)

    diff_stats = None
    if args.diff_budget:
        diff_stats = check_diff_budget(
            root,
            max_active_delta=args.max_active_delta,
            max_corrections_delta=args.max_corrections_delta,
            max_cn_en_delta=args.max_cn_en_delta,
        )

    report = {
        "ok": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "cn": cn_stats,
        "en": en_stats,
        "rules_total": len(ruleset.all_rule_ids()),
        "idempotency": idemp_stats,
        "collisions": collision_report,
        "diff_budget": diff_stats,
    }

    if args.json_out:
        dict_common.atomic_write_text(
            args.json_out, json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )

    if args.github_output:
        gh_kv = {
            "lint_ok": "true" if report["ok"] else "false",
            "error_count": str(len(errors)),
            "warning_count": str(len(warnings)),
        }
        if diff_stats is not None:
            gh_kv["needs_review"] = "true" if diff_stats["needs_review"] else "false"
            gh_kv["diff_summary"] = diff_stats["summary"]
            gh_kv["review_reasons"] = "; ".join(diff_stats["reasons"])
        _write_github_output(args.github_output, gh_kv)

    print("=== DICT LINT SUMMARY ===")
    print(f"Status:       {'PASS' if report['ok'] else 'FAIL'} (errors={len(errors)}, warnings={len(warnings)})")
    print(f"Active CN:    {cn_stats['active_cn_entries_incl_corr']:,} (base+cell={cn_stats['active_cn_entries_excl_corr_luna']:,}, corrections={cn_stats['corrections_entries']:,})")
    print(f"Rules SSOT:   {report['rules_total']} declarative rules loaded")
    if idemp_stats is not None:
        print(f"Idempotency:  {idemp_stats['checked_files']} files checked, {len(idemp_stats['diffs'])} diffs")
    if diff_stats is not None:
        print(f"Diff budget:  {diff_stats['summary']} (needs_review={diff_stats['needs_review']})")
    if collision_report is not None:
        print(f"Collisions:   {len(collision_report)} rule entries audited (see --json for full table)")
    if warnings:
        print("\n=== WARNINGS ===")
        for w in warnings:
            print(f"  [WARN] {w}")
    if errors:
        print("\n=== ERRORS ===")
        for e in errors:
            print(f"  [ERR]  {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
