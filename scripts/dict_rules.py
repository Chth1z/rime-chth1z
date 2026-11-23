#!/usr/bin/env python3
"""
Declarative dictionary rule loader, validator, conflict detector, and applier
for Chth1z/rime-chth1z (see docs/DICTIONARY_SPEC.md).
"""
from __future__ import annotations

import pathlib
import re
from collections import Counter
from dataclasses import dataclass, field

import build_cn_en

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

ACTIVE_CN_DICTS: tuple[str, ...] = (
    "cn_dicts/8105.dict.yaml",
    "cn_dicts/base.dict.yaml",
    "cn_dicts/ext.dict.yaml",
    "cn_dicts/others.dict.yaml",
    "cn_dicts_cell/literature.dict.yaml",
    "cn_dicts_cell/idiom.dict.yaml",
    "cn_dicts_cell/history.dict.yaml",
    "cn_dicts_cell/geography.dict.yaml",
    "cn_dicts_cell/place.dict.yaml",
    "cn_dicts_cell/shulihua.dict.yaml",
    "cn_dicts_cell/medication.dict.yaml",
    "cn_dicts_cell/industry_product.dict.yaml",
    "cn_dicts_cell/sport.dict.yaml",
    "cn_dicts_cell/animal.dict.yaml",
    "cn_dicts_cell/chess.dict.yaml",
    "cn_dicts_cell/chess2.dict.yaml",
    "cn_dicts_cell/music.dict.yaml",
    "cn_dicts_cell/computer.dict.yaml",
    "cn_dicts_cell/media.dict.yaml",
    "cn_dicts_cell/inputmethod.dict.yaml",
    "cn_dicts_cell/food.dict.yaml",
    "cn_dicts_cell/game.dict.yaml",
    "cn_dicts_cell/name.dict.yaml",
    "cn_dicts_cell/name2.dict.yaml",
    "cn_dicts_cell/exthot.dict.yaml",
    "cn_dicts_cell/composite.dict.yaml",
)

ALL_CN_DICTS: set[str] = set(ACTIVE_CN_DICTS) | {
    "cn_dicts/corrections.dict.yaml",
    "cn_dicts_cell/luna.dict.yaml",
}

MANAGED_OPENCC_TXTS: set[str] = {
    "opencc/others.txt",
    "opencc/chinese_english.txt",
    "opencc/english_chinese.txt",
    "opencc/emoji.txt",
}

CORRECTION_CATEGORIES: set[str] = {"A", "B", "C", "E1"}
ADDITION_CATEGORIES: set[str] = {"A", "E1", "modern", "tech", "domain", "brand"}
EN_CATEGORIES: set[str] = {"hardware", "ai", "dev", "consumer"}
OPENCC_ACTIONS: set[str] = {"replace", "delete", "add"}
COMMENT_HARD_MAX_LEN = 40
COMMENT_WARN_MAX_LEN = 32
E1_MAX_WEIGHT = 30
ALPHANUM_MAX_LEN = 10


@dataclass(frozen=True)
class PhoneticFixRule:
    line_no: int
    target_file: str
    word: str
    old_py: str
    new_py: str
    reason: str
    source: str

    @property
    def rule_id(self) -> str:
        return f"phonetics_fix.tsv:{self.line_no}:{self.target_file}:{self.word}:{self.old_py}->{self.new_py}"


@dataclass(frozen=True)
class DualReadingRule:
    line_no: int
    word: str
    py1: str
    w1: int
    note1: str
    py2: str
    w2: int
    note2: str
    target_file: str
    source: str

    @property
    def rule_id(self) -> str:
        return f"dual_readings.tsv:{self.line_no}:{self.word}:{self.py1}|{self.py2}"


@dataclass(frozen=True)
class CorrectionRule:
    line_no: int
    word: str
    wrong_py: str
    weight: int
    comment: str
    category: str
    source: str

    @property
    def rule_id(self) -> str:
        return f"corrections.tsv:{self.line_no}:{self.word}:{self.wrong_py}"


@dataclass(frozen=True)
class WeightRule:
    line_no: int
    target_file: str
    word: str
    py: str
    weight: int
    reason: str

    @property
    def rule_id(self) -> str:
        return f"weights.tsv:{self.line_no}:{self.target_file}:{self.word}:{self.py}={self.weight}"


@dataclass(frozen=True)
class DeletionRule:
    line_no: int
    target_file: str
    word: str
    py: str  # concrete pinyin or "*"
    reason: str

    @property
    def rule_id(self) -> str:
        return f"deletions.tsv:{self.line_no}:{self.target_file}:{self.word}:{self.py}"


@dataclass(frozen=True)
class AdditionRule:
    line_no: int
    target_file: str
    word: str
    py: str
    weight: int
    category: str
    source: str

    @property
    def rule_id(self) -> str:
        return f"additions.tsv:{self.line_no}:{self.target_file}:{self.word}:{self.py}"


@dataclass(frozen=True)
class EnAdditionRule:
    line_no: int
    word: str
    code: str
    weight: str
    category: str

    @property
    def rule_id(self) -> str:
        return f"en_additions.tsv:{self.line_no}:{self.word}:{self.code}"


@dataclass(frozen=True)
class OpenCCFixRule:
    line_no: int
    target_file: str
    key: str
    action: str
    value: str
    reason: str

    @property
    def rule_id(self) -> str:
        return f"opencc_fixes.tsv:{self.line_no}:{self.target_file}:{self.action}:{self.key}"


@dataclass
class RuleSet:
    rules_dir: pathlib.Path
    phonetics_fix: list[PhoneticFixRule] = field(default_factory=list)
    dual_readings: list[DualReadingRule] = field(default_factory=list)
    corrections: list[CorrectionRule] = field(default_factory=list)
    weights: list[WeightRule] = field(default_factory=list)
    deletions: list[DeletionRule] = field(default_factory=list)
    additions: list[AdditionRule] = field(default_factory=list)
    en_additions: list[EnAdditionRule] = field(default_factory=list)
    cn_en_rules: list[build_cn_en.CnEnRule] = field(default_factory=list)
    alphanum_additions: list[str] = field(default_factory=list)
    opencc_fixes: list[OpenCCFixRule] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def all_rule_ids(self) -> list[str]:
        ids: list[str] = []
        for group in (
            self.phonetics_fix,
            self.dual_readings,
            self.corrections,
            self.weights,
            self.deletions,
            self.additions,
            self.en_additions,
            self.cn_en_rules,
            self.opencc_fixes,
        ):
            ids.extend(r.rule_id for r in group)
        for tok in self.alphanum_additions:
            ids.append(f"alphanum_additions.txt:{tok}")
        return ids


def _iter_tsv(path: pathlib.Path, expected_cols: int, errors: list[str]) -> list[tuple[int, list[str]]]:
    rows: list[tuple[int, list[str]]] = []
    if not path.exists():
        errors.append(f"Missing required rule file: {path}")
        return rows
    raw_bytes = path.read_bytes()
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        errors.append(f"{path.name}: UTF-8 BOM is forbidden")
    if b"\r\n" in raw_bytes:
        errors.append(f"{path.name}: CRLF line endings found (must be LF)")
    for idx, line in enumerate(raw_bytes.decode("utf-8").splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) != expected_cols:
            errors.append(f"{path.name}:{idx}: expected {expected_cols} tab-separated columns, got {len(cols)}")
            continue
        rows.append((idx, cols))
    return rows


def _validate_pinyin(
    fname: str,
    idx: int,
    word: str,
    py: str,
    valid_syls: set[str] | None,
    errors: list[str],
    check_len: bool = True,
) -> None:
    if not py or py != py.strip():
        errors.append(f"{fname}:{idx}: malformed pinyin '{py}' for '{word}'")
        return
    if re.search(r"\b[ln]ue\b", py):
        errors.append(f"{fname}:{idx}: forbidden lue/nue spelling '{py}' for '{word}'")
    syls = py.split()
    if check_len:
        w_nodot = word.replace("·", "")
        if len(syls) != len(w_nodot):
            errors.append(f"{fname}:{idx}: syllable count ({len(syls)}) != word length ({len(w_nodot)}) for '{word}' '{py}'")
    if valid_syls is not None:
        for sy in syls:
            if sy not in valid_syls:
                errors.append(f"{fname}:{idx}: invalid syllable '{sy}' in '{word}' '{py}'")


def _parse_nonneg_int(fname: str, idx: int, raw: str, field_name: str, errors: list[str]) -> int | None:
    try:
        v = int(raw)
    except ValueError:
        errors.append(f"{fname}:{idx}: {field_name} must be integer, got '{raw}'")
        return None
    if v < 0:
        errors.append(f"{fname}:{idx}: {field_name} must be >= 0, got {v}")
        return None
    return v


def load_ruleset(rules_dir: pathlib.Path, valid_syls: set[str] | None = None) -> RuleSet:
    rs = RuleSet(rules_dir=rules_dir)

    # 1. phonetics_fix.tsv
    pf_seen: set[tuple[str, str, str]] = set()
    for idx, cols in _iter_tsv(rules_dir / "phonetics_fix.tsv", 6, rs.errors):
        target, word, old_py, new_py, reason, source = cols
        if target not in ALL_CN_DICTS or target == "cn_dicts/corrections.dict.yaml":
            rs.errors.append(f"phonetics_fix.tsv:{idx}: invalid target_file '{target}'")
            continue
        if not word or not reason or not source:
            rs.errors.append(f"phonetics_fix.tsv:{idx}: word, reason, and source are required")
            continue
        _validate_pinyin("phonetics_fix.tsv", idx, word, new_py, valid_syls, rs.errors, check_len=True)
        if old_py == new_py:
            rs.errors.append(f"phonetics_fix.tsv:{idx}: no-op rule '{word}' '{old_py}' == '{new_py}'")
            continue
        k = (target, word, old_py)
        if k in pf_seen:
            rs.errors.append(f"phonetics_fix.tsv:{idx}: duplicate key {k}")
            continue
        pf_seen.add(k)
        rs.phonetics_fix.append(PhoneticFixRule(idx, target, word, old_py, new_py, reason, source))

    # Detect chained/cyclic phonetics_fix rules on the same (target, word)
    pf_by_tw: dict[tuple[str, str], list[PhoneticFixRule]] = {}
    for r in rs.phonetics_fix:
        pf_by_tw.setdefault((r.target_file, r.word), []).append(r)
    for tw, group in pf_by_tw.items():
        old_set = {r.old_py for r in group}
        for r in group:
            if r.new_py in old_set:
                rs.errors.append(
                    f"phonetics_fix.tsv:{r.line_no}: non-idempotent chain on {tw}: '{r.old_py}' -> '{r.new_py}' feeds another rule"
                )

    # 2. dual_readings.tsv
    dr_seen: set[tuple[str, str, str]] = set()
    for idx, cols in _iter_tsv(rules_dir / "dual_readings.tsv", 9, rs.errors):
        word, py1, w1_s, note1, py2, w2_s, note2, target, source = cols
        if target not in ACTIVE_CN_DICTS:
            rs.errors.append(f"dual_readings.tsv:{idx}: target_file must be an active CN dict, got '{target}'")
            continue
        if not word or not note1 or not note2 or not source:
            rs.errors.append(f"dual_readings.tsv:{idx}: word, note1, note2, and source are required")
            continue
        if py1 == py2:
            rs.errors.append(f"dual_readings.tsv:{idx}: py1 and py2 must differ for '{word}'")
            continue
        w1 = _parse_nonneg_int("dual_readings.tsv", idx, w1_s, "w1", rs.errors)
        w2 = _parse_nonneg_int("dual_readings.tsv", idx, w2_s, "w2", rs.errors)
        if w1 is None or w2 is None:
            continue
        _validate_pinyin("dual_readings.tsv", idx, word, py1, valid_syls, rs.errors, check_len=True)
        _validate_pinyin("dual_readings.tsv", idx, word, py2, valid_syls, rs.errors, check_len=True)
        for label, note in (("note1", note1), ("note2", note2)):
            if len(note) > COMMENT_HARD_MAX_LEN:
                rs.errors.append(f"dual_readings.tsv:{idx}: {label} length {len(note)} > {COMMENT_HARD_MAX_LEN}")
            elif len(note) > COMMENT_WARN_MAX_LEN:
                rs.warnings.append(f"dual_readings.tsv:{idx}: {label} length {len(note)} > {COMMENT_WARN_MAX_LEN} ('{note}')")
        dk = (word, min(py1, py2), max(py1, py2))
        if dk in dr_seen:
            rs.errors.append(f"dual_readings.tsv:{idx}: duplicate dual reading entry for '{word}'")
            continue
        dr_seen.add(dk)
        rs.dual_readings.append(DualReadingRule(idx, word, py1, w1, note1, py2, w2, note2, target, source))

    # 3. corrections.tsv
    corr_seen: set[tuple[str, str]] = set()
    for idx, cols in _iter_tsv(rules_dir / "corrections.tsv", 6, rs.errors):
        word, wrong_py, wt_s, comment, category, source = cols
        if not word or not comment or not source:
            rs.errors.append(f"corrections.tsv:{idx}: word, comment, and source are required")
            continue
        if category not in CORRECTION_CATEGORIES:
            rs.errors.append(f"corrections.tsv:{idx}: invalid category '{category}' (allowed: {sorted(CORRECTION_CATEGORIES)})")
            continue
        wt = _parse_nonneg_int("corrections.tsv", idx, wt_s, "weight", rs.errors)
        if wt is None:
            continue
        if category == "E1" and wt > E1_MAX_WEIGHT:
            rs.errors.append(f"corrections.tsv:{idx}: E1 typo '{word}' weight {wt} > {E1_MAX_WEIGHT}")
        if len(comment) > COMMENT_HARD_MAX_LEN:
            rs.errors.append(f"corrections.tsv:{idx}: comment length {len(comment)} > {COMMENT_HARD_MAX_LEN}")
        elif len(comment) > COMMENT_WARN_MAX_LEN:
            rs.warnings.append(f"corrections.tsv:{idx}: comment length {len(comment)} > {COMMENT_WARN_MAX_LEN} ('{comment}')")
        _validate_pinyin("corrections.tsv", idx, word, wrong_py, valid_syls, rs.errors, check_len=False)
        ck = (word, wrong_py)
        if ck in corr_seen:
            rs.errors.append(f"corrections.tsv:{idx}: duplicate key {ck}")
            continue
        corr_seen.add(ck)
        rs.corrections.append(CorrectionRule(idx, word, wrong_py, wt, comment, category, source))

    # 4. weights.tsv
    wt_seen: set[tuple[str, str, str]] = set()
    for idx, cols in _iter_tsv(rules_dir / "weights.tsv", 5, rs.errors):
        target, word, py, wt_s, reason = cols
        if target not in ALL_CN_DICTS or target == "cn_dicts/corrections.dict.yaml":
            rs.errors.append(f"weights.tsv:{idx}: invalid target_file '{target}'")
            continue
        if not word or not reason:
            rs.errors.append(f"weights.tsv:{idx}: word and reason are required")
            continue
        wt = _parse_nonneg_int("weights.tsv", idx, wt_s, "weight", rs.errors)
        if wt is None:
            continue
        _validate_pinyin("weights.tsv", idx, word, py, valid_syls, rs.errors, check_len=True)
        wk = (target, word, py)
        if wk in wt_seen:
            rs.errors.append(f"weights.tsv:{idx}: duplicate key {wk}")
            continue
        wt_seen.add(wk)
        rs.weights.append(WeightRule(idx, target, word, py, wt, reason))

    # 5. deletions.tsv
    del_seen: set[tuple[str, str, str]] = set()
    for idx, cols in _iter_tsv(rules_dir / "deletions.tsv", 4, rs.errors):
        target, word, py, reason = cols
        if target not in ALL_CN_DICTS:
            rs.errors.append(f"deletions.tsv:{idx}: invalid target_file '{target}'")
            continue
        if not word or not py or not reason:
            rs.errors.append(f"deletions.tsv:{idx}: word, py (or '*'), and reason are required")
            continue
        if py != "*":
            _validate_pinyin("deletions.tsv", idx, word, py, valid_syls, rs.errors, check_len=False)
        dk = (target, word, py)
        if dk in del_seen:
            rs.errors.append(f"deletions.tsv:{idx}: duplicate key {dk}")
            continue
        del_seen.add(dk)
        rs.deletions.append(DeletionRule(idx, target, word, py, reason))

    # 6. additions.tsv
    add_seen: set[tuple[str, str, str]] = set()
    for idx, cols in _iter_tsv(rules_dir / "additions.tsv", 6, rs.errors):
        target, word, py, wt_s, category, source = cols
        if target not in ACTIVE_CN_DICTS:
            rs.errors.append(f"additions.tsv:{idx}: target_file must be an active CN dict, got '{target}'")
            continue
        if not word or not source:
            rs.errors.append(f"additions.tsv:{idx}: word and source are required")
            continue
        if category not in ADDITION_CATEGORIES:
            rs.errors.append(f"additions.tsv:{idx}: invalid category '{category}' (allowed: {sorted(ADDITION_CATEGORIES)})")
            continue
        wt = _parse_nonneg_int("additions.tsv", idx, wt_s, "weight", rs.errors)
        if wt is None:
            continue
        if category == "E1" and wt > E1_MAX_WEIGHT:
            rs.errors.append(f"additions.tsv:{idx}: E1 typo '{word}' weight {wt} > {E1_MAX_WEIGHT}")
        _validate_pinyin("additions.tsv", idx, word, py, valid_syls, rs.errors, check_len=True)
        ak = (target, word, py)
        if ak in add_seen:
            rs.errors.append(f"additions.tsv:{idx}: duplicate key {ak}")
            continue
        add_seen.add(ak)
        rs.additions.append(AdditionRule(idx, target, word, py, wt, category, source))

    # 7. en_additions.tsv
    en_seen: set[tuple[str, str]] = set()
    for idx, cols in _iter_tsv(rules_dir / "en_additions.tsv", 4, rs.errors):
        word, code, wt_s, category = cols
        if not word or not code:
            rs.errors.append(f"en_additions.tsv:{idx}: word and code are required")
            continue
        if wt_s != "":
            _parse_nonneg_int("en_additions.tsv", idx, wt_s, "weight", rs.errors)
        if category not in EN_CATEGORIES:
            rs.errors.append(f"en_additions.tsv:{idx}: invalid category '{category}' (allowed: {sorted(EN_CATEGORIES)})")
            continue
        ek = (word, code)
        if ek in en_seen:
            rs.errors.append(f"en_additions.tsv:{idx}: duplicate key {ek}")
            continue
        en_seen.add(ek)
        rs.en_additions.append(EnAdditionRule(idx, word, code, wt_s, category))

    # 8. cn_en_source.tsv
    cn_en_rules, cn_en_errors = build_cn_en.load_cn_en_rules(rules_dir / "cn_en_source.tsv", valid_syls=valid_syls)
    rs.cn_en_rules = cn_en_rules
    rs.errors.extend(cn_en_errors)

    # 9. alphanum_additions.txt
    alpha_path = rules_dir / "alphanum_additions.txt"
    if not alpha_path.exists():
        rs.errors.append(f"Missing required rule file: {alpha_path}")
    else:
        raw_bytes = alpha_path.read_bytes()
        if raw_bytes.startswith(b"\xef\xbb\xbf"):
            rs.errors.append("alphanum_additions.txt: UTF-8 BOM is forbidden")
        if b"\r\n" in raw_bytes:
            rs.errors.append("alphanum_additions.txt: CRLF line endings found (must be LF)")
        seen_toks: set[str] = set()
        for idx, line in enumerate(raw_bytes.decode("utf-8").splitlines(), 1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "\t" in s or " " in s:
                rs.errors.append(f"alphanum_additions.txt:{idx}: whitespace forbidden in token '{s}'")
                continue
            if len(s) > ALPHANUM_MAX_LEN:
                rs.errors.append(f"alphanum_additions.txt:{idx}: token '{s}' length {len(s)} > {ALPHANUM_MAX_LEN}")
                continue
            if s in seen_toks:
                rs.errors.append(f"alphanum_additions.txt:{idx}: duplicate token '{s}'")
                continue
            seen_toks.add(s)
            rs.alphanum_additions.append(s)

    # 10. opencc_fixes.tsv
    occ_seen: set[tuple[str, str]] = set()
    for idx, cols in _iter_tsv(rules_dir / "opencc_fixes.tsv", 5, rs.errors):
        target, key, action, value, reason = cols
        if target not in MANAGED_OPENCC_TXTS:
            rs.errors.append(f"opencc_fixes.tsv:{idx}: invalid target_file '{target}'")
            continue
        if action not in OPENCC_ACTIONS:
            rs.errors.append(f"opencc_fixes.tsv:{idx}: invalid action '{action}' (allowed: {sorted(OPENCC_ACTIONS)})")
            continue
        if not key or not reason:
            rs.errors.append(f"opencc_fixes.tsv:{idx}: key and reason are required")
            continue
        if action in {"replace", "add"} and not value:
            rs.errors.append(f"opencc_fixes.tsv:{idx}: action '{action}' requires non-empty value")
            continue
        ok = (target, key)
        if ok in occ_seen:
            rs.errors.append(f"opencc_fixes.tsv:{idx}: duplicate key {ok}")
            continue
        occ_seen.add(ok)
        rs.opencc_fixes.append(OpenCCFixRule(idx, target, key, action, value, reason))

    # Cross-table conflict detection
    def _is_deleted(target: str, word: str, py: str) -> bool:
        return (target, word, py) in del_seen or (target, word, "*") in del_seen

    for r in rs.additions:
        if _is_deleted(r.target_file, r.word, r.py):
            rs.errors.append(f"conflict: additions.tsv:{r.line_no} ({r.target_file}, {r.word}, {r.py}) is also in deletions.tsv")

    for r in rs.weights:
        if _is_deleted(r.target_file, r.word, r.py):
            rs.errors.append(f"conflict: weights.tsv:{r.line_no} ({r.target_file}, {r.word}, {r.py}) is also in deletions.tsv")

    for r in rs.phonetics_fix:
        if _is_deleted(r.target_file, r.word, r.new_py):
            rs.errors.append(
                f"conflict: phonetics_fix.tsv:{r.line_no} target ({r.target_file}, {r.word}, {r.new_py}) is deleted in deletions.tsv"
            )

    for r in rs.dual_readings:
        for py in (r.py1, r.py2):
            if _is_deleted(r.target_file, r.word, py):
                rs.errors.append(
                    f"conflict: dual_readings.tsv:{r.line_no} ({r.target_file}, {r.word}, {py}) is deleted in deletions.tsv"
                )
        for py in (r.py1, r.py2):
            if (r.word, py) in corr_seen:
                rs.errors.append(
                    f"conflict: dual_readings.tsv:{r.line_no} ({r.word}, {py}) is also defined in corrections.tsv (keep single source)"
                )

    for r in rs.corrections:
        if _is_deleted("cn_dicts/corrections.dict.yaml", r.word, r.wrong_py):
            rs.errors.append(
                f"conflict: corrections.tsv:{r.line_no} ({r.word}, {r.wrong_py}) is also deleted in deletions.tsv"
            )

    return rs


def _split_header_body(lines: list[str]) -> tuple[list[str], list[str]]:
    for i, line in enumerate(lines):
        if line.strip() == "...":
            return lines[: i + 1], lines[i + 1 :]
    return [], lines


def _parse_entry(line: str) -> tuple[str, str, str, list[str]] | None:
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    parts = line.rstrip("\r\n").split("\t")
    if len(parts) < 2:
        return None
    w = parts[0]
    py = parts[1]
    wt = parts[2] if len(parts) >= 3 else ""
    extra = parts[3:] if len(parts) > 3 else []
    return w, py, wt, extra


def _format_entry(w: str, py: str, wt: str, extra: list[str]) -> str:
    cols = [w, py]
    if wt != "" or extra:
        cols.append(wt)
    cols.extend(extra)
    return "\t".join(cols)


def apply_cn_overlay(
    rel: str,
    lines: list[str],
    ruleset: RuleSet,
    hits: dict[str, int],
    stats: Counter,
) -> list[str]:
    """Apply declarative rules/ overrides for a single non-corrections CN dictionary."""
    pf_map = {(r.word, r.old_py): r for r in ruleset.phonetics_fix if r.target_file == rel}
    del_exact = {(r.word, r.py): r for r in ruleset.deletions if r.target_file == rel and r.py != "*"}
    del_wild = {r.word: r for r in ruleset.deletions if r.target_file == rel and r.py == "*"}
    wt_map = {(r.word, r.py): r for r in ruleset.weights if r.target_file == rel}
    adds = [r for r in ruleset.additions if r.target_file == rel]
    duals = [r for r in ruleset.dual_readings if r.target_file == rel]

    if not (pf_map or del_exact or del_wild or wt_map or adds or duals):
        return lines

    hdr, body = _split_header_body(lines)
    out_body: list[str] = []
    seen: set[tuple[str, str]] = set()

    for line in body:
        p = _parse_entry(line)
        if not p:
            out_body.append(line)
            continue
        w, py, wt, extra = p

        pf = pf_map.get((w, py))
        if pf is not None:
            py = pf.new_py
            hits[pf.rule_id] += 1
            stats["rules_py_fixed"] += 1

        dr = del_exact.get((w, py)) or del_wild.get(w)
        if dr is not None:
            hits[dr.rule_id] += 1
            stats["rules_deleted"] += 1
            continue

        wr = wt_map.get((w, py))
        if wr is not None:
            hits[wr.rule_id] += 1
            if wt != str(wr.weight):
                wt = str(wr.weight)
                stats["rules_reweighted"] += 1

        seen.add((w, py))
        out_body.append(_format_entry(w, py, wt, extra))

    for ar in adds:
        if (ar.word, ar.py) in seen:
            hits[ar.rule_id] += 1
        else:
            seen.add((ar.word, ar.py))
            out_body.append(_format_entry(ar.word, ar.py, str(ar.weight), []))
            hits[ar.rule_id] += 1
            stats["rules_added"] += 1

    for dr in duals:
        for py, wt_val in ((dr.py1, dr.w1), (dr.py2, dr.w2)):
            if (dr.word, py) in seen:
                hits[dr.rule_id] += 1
            else:
                seen.add((dr.word, py))
                out_body.append(_format_entry(dr.word, py, str(wt_val), []))
                hits[dr.rule_id] += 1
                stats["rules_added"] += 1

    return hdr + out_body


def apply_corrections_overlay(
    lines: list[str],
    ruleset: RuleSet,
    active_keys: set[tuple[str, str]],
    hits: dict[str, int],
    stats: Counter,
) -> list[str]:
    """Apply rules/corrections.tsv, rules/dual_readings.tsv, and deletions targeting corrections.dict.yaml."""
    rel = "cn_dicts/corrections.dict.yaml"
    del_exact = {(r.word, r.py): r for r in ruleset.deletions if r.target_file == rel and r.py != "*"}
    del_wild = {r.word: r for r in ruleset.deletions if r.target_file == rel and r.py == "*"}

    # Build unified desired correction overlay: (word, py) -> (weight, comment, rule_id)
    desired: dict[tuple[str, str], tuple[int, str, str]] = {}
    for cr in ruleset.corrections:
        desired[(cr.word, cr.wrong_py)] = (cr.weight, cr.comment, cr.rule_id)
    for dr in ruleset.dual_readings:
        for py, wt_val, note in ((dr.py1, dr.w1, dr.note1), (dr.py2, dr.w2, dr.note2)):
            eff_wt = 0 if (dr.word, py) in active_keys else wt_val
            desired[(dr.word, py)] = (eff_wt, note, dr.rule_id)

    if not (del_exact or del_wild or desired):
        return lines

    hdr, body = _split_header_body(lines)
    out_body: list[str] = []
    emitted: set[tuple[str, str]] = set()

    for line in body:
        p = _parse_entry(line)
        if not p:
            out_body.append(line)
            continue
        w, py, wt, extra = p

        dr = del_exact.get((w, py)) or del_wild.get(w)
        if dr is not None:
            hits[dr.rule_id] += 1
            stats["rules_deleted"] += 1
            continue

        ov = desired.get((w, py))
        if ov is not None:
            new_wt, new_cmt, rid = ov
            hits[rid] += 1
            old_cmt = extra[0] if extra else ""
            if wt != str(new_wt) or old_cmt != new_cmt:
                stats["rules_corr_updated"] += 1
            out_body.append(_format_entry(w, py, str(new_wt), [new_cmt]))
            emitted.add((w, py))
            continue

        emitted.add((w, py))
        out_body.append(line)

    for (w, py), (new_wt, new_cmt, rid) in desired.items():
        if (w, py) not in emitted:
            out_body.append(_format_entry(w, py, str(new_wt), [new_cmt]))
            emitted.add((w, py))
            hits[rid] += 1
            stats["rules_corr_added"] += 1

    return hdr + out_body


def apply_opencc_overlay(
    rel: str,
    lines: list[str],
    ruleset: RuleSet,
    hits: dict[str, int],
) -> tuple[list[str], int]:
    """Apply rules/opencc_fixes.tsv overrides for an OpenCC text file."""
    fixes = [r for r in ruleset.opencc_fixes if r.target_file == rel]
    if not fixes:
        return lines, 0

    by_key = {r.key: r for r in fixes}
    out: list[str] = []
    seen_keys: set[str] = set()
    changed = 0

    for line in lines:
        if "\t" not in line:
            out.append(line)
            continue
        k, _ = line.split("\t", 1)
        r = by_key.get(k)
        if r is None:
            seen_keys.add(k)
            out.append(line)
            continue
        if r.action == "delete":
            hits[r.rule_id] += 1
            changed += 1
            continue
        if r.action == "replace":
            hits[r.rule_id] += 1
            new_line = f"{k}\t{r.value}"
            if new_line != line:
                changed += 1
            seen_keys.add(k)
            out.append(new_line)
            continue
        seen_keys.add(k)
        out.append(line)

    for r in fixes:
        if r.action == "add":
            if r.key in seen_keys:
                hits[r.rule_id] += 1
            else:
                out.append(f"{r.key}\t{r.value}")
                seen_keys.add(r.key)
                hits[r.rule_id] += 1
                changed += 1

    return out, changed


def summarize_rule_hits(ruleset: RuleSet, hits: dict[str, int]) -> dict:
    all_ids = ruleset.all_rule_ids()
    zero_hit = [rid for rid in all_ids if hits.get(rid, 0) == 0]
    return {
        "total_rules": len(all_ids),
        "matched_rules": len(all_ids) - len(zero_hit),
        "zero_hit_count": len(zero_hit),
        "stale_rules": zero_hit,
    }
