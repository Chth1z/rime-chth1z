#!/usr/bin/env python3
"""
Standalone dictionary linter, rules SSOT validator, idempotency verifier,
homophone collision advisor, and CI diff-budget circuit breaker for rime-chth1z.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import build_cn_en
import dict_rules

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

EXTRA_VALID_SYLS = {"hm", "hng", "m", "n", "ng"}
ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
ZERO_WIDTH_NO_ZWJ_RE = re.compile(r"[\u200b\u200c\ufeff]")
LUE_NUE_RE = re.compile(r"\b[ln]ue\b")

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
    *dict_rules.ACTIVE_CN_DICTS,
    "cn_dicts/corrections.dict.yaml",
    "cn_dicts_cell/luna.dict.yaml",
    "rime_frost.dict.yaml",
    *MANAGED_EN_FILES,
    *MANAGED_OPENCC_FILES,
)


def _split_header_body(lines: list[str]) -> tuple[list[str], list[str], int]:
    for i, line in enumerate(lines):
        if line.strip() == "...":
            return lines[: i + 1], lines[i + 1 :], i + 2
    return [], lines, 1


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _load_valid_syls(root: pathlib.Path) -> set[str]:
    valid: set[str] = set(EXTRA_VALID_SYLS)
    p = root / "cn_dicts/8105.dict.yaml"
    if not p.exists():
        return valid
    _, body, _ = _split_header_body(p.read_text(encoding="utf-8").splitlines())
    for line in body:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) >= 2:
            valid.add(cols[1])
    return valid


def check_hygiene(root: pathlib.Path, errors: list[str]) -> None:
    """Check UTF-8 no BOM, LF line endings, and clean whitespace on all managed files."""
    for rel in ALL_MANAGED_FILES:
        p = root / rel
        if not p.exists():
            errors.append(f"missing managed file: {rel}")
            continue
        raw = p.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            errors.append(f"{rel}: UTF-8 BOM is forbidden")
        if b"\r\n" in raw:
            errors.append(f"{rel}: CRLF line endings detected (must be LF)")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"{rel}: invalid UTF-8 ({exc})")
            continue

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
            if (is_dict or is_cn_en) and "\u3000" in line:
                errors.append(f"{rel}:{idx}: full-width space U+3000 in entry")
            if allows_emoji_zwj:
                key_part = line.split("\t", 1)[0]
                if ZERO_WIDTH_RE.search(key_part) or ZERO_WIDTH_NO_ZWJ_RE.search(line):
                    errors.append(f"{rel}:{idx}: zero-width character in entry")
            elif ZERO_WIDTH_RE.search(line):
                errors.append(f"{rel}:{idx}: zero-width character in entry")
            if is_dict or is_cn_en:
                cols = line.split("\t")
                if len(cols) < 2 and rel != "rime_frost.dict.yaml":
                    errors.append(f"{rel}:{idx}: missing tab delimiter")
                    continue
                if any(c != c.strip() for c in cols[:2]):
                    errors.append(f"{rel}:{idx}: leading/trailing whitespace in text or code")


def check_cn_invariants(
    root: pathlib.Path,
    valid_syls: set[str],
    errors: list[str],
    warnings: list[str],
) -> tuple[dict, set[tuple[str, str]], dict[str, list[tuple[str, int, str]]]]:
    """Verify the 5 CN invariants + corrections.dict.yaml contract."""
    invalid_syls: list[tuple] = []
    len_mismatches: list[tuple] = []
    lue_nue: list[tuple] = []
    within_dups = 0
    cross_dups = 0
    active_keys: set[tuple[str, str]] = set()
    code_index: dict[str, list[tuple[str, int, str]]] = {}
    active_entry_count = 0

    cn_files = (*dict_rules.ACTIVE_CN_DICTS, "cn_dicts/corrections.dict.yaml", "cn_dicts_cell/luna.dict.yaml")
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
            for sy in syls:
                if sy not in valid_syls:
                    invalid_syls.append((rel, idx, w, py, sy))
            if not is_corr:
                w_nodot = w.replace("·", "")
                if len(syls) != len(w_nodot):
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
                code_index.setdefault(py, []).append((w, wt_val, rel))

    # Dedicated corrections.dict.yaml contract check (runs after active_keys is fully built)
    corr_p = root / "cn_dicts/corrections.dict.yaml"
    corr_entries = 0
    corr_overlap_nonzero = 0
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

    if invalid_syls:
        errors.append(f"invalid_syllables={len(invalid_syls)} (samples: {invalid_syls[:5]})")
    if len_mismatches:
        errors.append(f"len_mismatches={len(len_mismatches)} (samples: {len_mismatches[:5]})")
    if lue_nue:
        errors.append(f"remaining_lue_nue={len(lue_nue)} (samples: {lue_nue[:5]})")
    if within_dups:
        errors.append(f"within_file_dups={within_dups}")
    if cross_dups:
        errors.append(f"cross_file_dups_active_27={cross_dups}")

    stats = {
        "active_cn_entries_excl_corr_luna": active_entry_count,
        "corrections_entries": corr_entries,
        "active_cn_entries_incl_corr": active_entry_count + corr_entries,
        "invalid_syllables": len(invalid_syls),
        "len_mismatches": len(len_mismatches),
        "remaining_lue_nue": len(lue_nue),
        "within_file_dups": within_dups,
        "cross_file_dups_active_27": cross_dups,
        "corrections_overlap_nonzero": corr_overlap_nonzero,
    }
    return stats, active_keys, code_index


def check_en_and_cn_en(root: pathlib.Path, rules_dir: pathlib.Path, errors: list[str]) -> dict:
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
            _, changed = build_cn_en.apply_cn_en_rules(root, root, cn_en_src, dry_run=True)
            if changed:
                errors.append(f"cn_en tables out of sync with rules/cn_en_source.tsv: {changed}")
        except ValueError as exc:
            errors.append(str(exc))

    # Check en_ext & en no within-file duplicates
    for rel in ("en_dicts/en_ext.dict.yaml", "en_dicts/en.dict.yaml"):
        p = root / rel
        if not p.exists():
            continue
        _, body, start_idx = _split_header_body(p.read_text(encoding="utf-8").splitlines())
        seen_en: set[tuple[str, str]] = set()
        dup_cnt = 0
        for line in body:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) >= 2:
                k = (cols[0], cols[1])
                if k in seen_en:
                    dup_cnt += 1
                seen_en.add(k)
        if dup_cnt:
            errors.append(f"{rel}: {dup_cnt} within-file duplicates")

    return {"cn_en_entry_counts": counts}


def check_schema_and_opencc(root: pathlib.Path, errors: list[str]) -> None:
    """Verify rime_frost.dict.yaml locks luna off and OpenCC JSON/TXT files are valid."""
    rf = root / "rime_frost.dict.yaml"
    if rf.exists():
        for idx, line in enumerate(rf.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip() == "- cn_dicts_cell/luna":
                errors.append(f"rime_frost.dict.yaml:{idx}: cn_dicts_cell/luna must remain disabled")

    occ_dir = root / "opencc"
    if occ_dir.exists():
        for jf in sorted(occ_dir.glob("*.json")):
            try:
                json.loads(jf.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"opencc/{jf.name}: invalid JSON ({exc})")
        for rel in MANAGED_OPENCC_FILES:
            p = root / rel
            if not p.exists():
                continue
            for idx, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                if "\t" not in line:
                    errors.append(f"{rel}:{idx}: missing tab separator in OpenCC table")


def check_idempotency(root: pathlib.Path, rules_dir: pathlib.Path, errors: list[str]) -> dict:
    """Copy all managed files to a tempdir, run clean-dicts.py, and assert 0 SHA-256 diffs."""
    with tempfile.TemporaryDirectory(prefix="rime-lint-idemp-") as tmp:
        tmp_root = pathlib.Path(tmp)
        before_hashes: dict[str, str] = {}
        for rel in ALL_MANAGED_FILES:
            src = root / rel
            if not src.exists():
                continue
            dst = tmp_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            before_hashes[rel] = _sha256(dst)

        cleaner = root / "scripts/clean-dicts.py"
        manifest_path = tmp_root / "manifest.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(cleaner),
                "--src-dir",
                str(tmp_root),
                "--out-dir",
                str(tmp_root),
                "--rules-dir",
                str(rules_dir),
                "--manifest",
                str(manifest_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            errors.append(f"idempotency clean-dicts.py failed (rc={proc.returncode}): {proc.stderr or proc.stdout}")
            return {"checked_files": len(before_hashes), "diffs": ["<cleaner failed>"]}

        diffs: list[str] = []
        for rel, h_before in before_hashes.items():
            h_after = _sha256(tmp_root / rel)
            if h_after != h_before:
                diffs.append(rel)
        if diffs:
            errors.append(f"idempotency failed: {len(diffs)} file(s) changed on pass 2: {diffs}")

        rules_summary = {}
        if manifest_path.exists():
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
            rules_summary = m.get("rules", {})
        return {"checked_files": len(before_hashes), "diffs": diffs, "rules_manifest": rules_summary}


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
        if cr.category in {"B", "C"} and top_non_self and cr.weight >= top_non_self[0][1] and cr.weight > 0:
            errors.append(
                f"collision guard: {cr.rule_id} weight {cr.weight} >= top active homophone '{top_non_self[0][0]}' ({top_non_self[0][1]})"
            )
        if cr.category == "E1" and top_non_self and cr.weight > max(1, top_non_self[0][1] // 20):
            warnings.append(
                f"collision guard: E1 {cr.rule_id} weight {cr.weight} > top1/20 ({top_non_self[0][0]}={top_non_self[0][1]})"
            )

    for ar in ruleset.additions:
        top = _top5(ar.py)
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
        for py, wt in ((dr.py1, dr.w1), (dr.py2, dr.w2)):
            top = _top5(py)
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


def _count_dict_entries(lines: list[str]) -> int:
    _, body, _ = _split_header_body(lines)
    return sum(1 for l in body if l.strip() and not l.strip().startswith("#") and "\t" in l)


def _entry_set(lines: list[str], is_dict: bool = True) -> set[str]:
    body = _split_header_body(lines)[1] if is_dict else lines
    return {l for l in body if l.strip() and not l.strip().startswith("#") and "\t" in l}


def check_diff_budget(
    root: pathlib.Path,
    max_active_delta: int,
    max_corrections_delta: int,
    max_cn_en_delta: int,
) -> dict:
    """Compare current working tree vs HEAD to drive CI circuit-breaker decisions."""
    active_before = 0
    active_after = 0
    for rel in (*dict_rules.ACTIVE_CN_DICTS, "cn_dicts/corrections.dict.yaml"):
        head_lines = _git_show_lines(root, rel)
        cur_p = root / rel
        if head_lines is not None:
            active_before += _count_dict_entries(head_lines)
        if cur_p.exists():
            active_after += _count_dict_entries(cur_p.read_text(encoding="utf-8").splitlines())
    active_delta = active_after - active_before

    corr_head = _git_show_lines(root, "cn_dicts/corrections.dict.yaml") or []
    corr_cur = (root / "cn_dicts/corrections.dict.yaml").read_text(encoding="utf-8").splitlines()
    corr_changed = len(_entry_set(corr_head, True) ^ _entry_set(corr_cur, True))

    cn_en_head = _git_show_lines(root, "en_dicts/cn_en.txt") or []
    cn_en_cur = (root / "en_dicts/cn_en.txt").read_text(encoding="utf-8").splitlines()
    cn_en_changed = len(_entry_set(cn_en_head, False) ^ _entry_set(cn_en_cur, False))

    reasons: list[str] = []
    if abs(active_delta) > max_active_delta:
        reasons.append(f"active_cn_net_delta={active_delta:+d} exceeds ±{max_active_delta}")
    if corr_changed > max_corrections_delta:
        reasons.append(f"corrections_changed_entries={corr_changed} exceeds {max_corrections_delta}")
    if cn_en_changed > max_cn_en_delta:
        reasons.append(f"cn_en_changed_entries={cn_en_changed} exceeds {max_cn_en_delta}")

    needs_review = len(reasons) > 0
    summary = (
        f"active_cn={active_before:,}->{active_after:,} ({active_delta:+,}), "
        f"corrections_symdiff={corr_changed}, cn_en_symdiff={cn_en_changed}"
    )
    return {
        "active_cn_before": active_before,
        "active_cn_after": active_after,
        "active_cn_net_delta": active_delta,
        "corrections_changed_entries": corr_changed,
        "cn_en_changed_entries": cn_en_changed,
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
    ap.add_argument("--idempotent", action="store_true", help="Run pass-2 SHA-256 idempotency verification in tempdir")
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

    valid_syls = _load_valid_syls(root)
    ruleset = dict_rules.load_ruleset(rules_dir, valid_syls=valid_syls)
    errors.extend(ruleset.errors)
    warnings.extend(ruleset.warnings)

    check_hygiene(root, errors)
    cn_stats, _, code_index = check_cn_invariants(root, valid_syls, errors, warnings)
    en_stats = check_en_and_cn_en(root, rules_dir, errors)
    check_schema_and_opencc(root, errors)

    idemp_stats = None
    if args.idempotent:
        idemp_stats = check_idempotency(root, rules_dir, errors)

    collision_report = None
    if args.check_collisions:
        collision_report = check_collisions(ruleset, code_index, errors, warnings)

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
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

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
        print(f"Collisions:   {len(collision_report)} rule entries audited")
        for item in collision_report:
            print(f"  {item['source']} -> top5={item['top5_active']}")
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
