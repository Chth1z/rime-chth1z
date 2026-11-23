#!/usr/bin/env python3
"""
Single-source CN-EN dictionary builder for rime-chth1z.
Reads rules/cn_en_source.tsv and deterministically synchronizes en_dicts/cn_en.txt
and all 6 Rime shuangpin variants (double_pinyin, flypy, abc, mspy, sogou, ziguang).
"""
from __future__ import annotations

import argparse
import pathlib
from dataclasses import dataclass

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Rime double-pinyin schemes for syncing all 7 cn_en*.txt tables identically
SHUANGPIN_SCHEMES: dict[str, dict[str, dict[str, str]]] = {
    "double_pinyin": {  # 自然码
        "init": {"zh": "v", "ch": "i", "sh": "u"},
        "fin": {
            "iu": "q", "ia": "w", "ua": "w", "uan": "r", "ue": "t", "ve": "t",
            "uai": "y", "ing": "y", "uo": "o", "un": "p", "iong": "s", "ong": "s",
            "iang": "d", "uang": "d", "en": "f", "eng": "g", "ang": "h", "an": "j",
            "ao": "k", "ai": "l", "ei": "z", "ie": "x", "iao": "c", "ui": "v",
            "ou": "b", "in": "n", "ian": "m",
        },
        "zero": {
            "a": "aa", "o": "oo", "e": "ee", "ai": "ai", "ei": "ei", "ao": "ao",
            "ou": "ou", "an": "an", "en": "en", "ang": "ah", "eng": "eg", "er": "er",
        },
    },
    "flypy": {  # 小鹤
        "init": {"zh": "v", "ch": "i", "sh": "u"},
        "fin": {
            "iu": "q", "ei": "w", "uan": "r", "ue": "t", "ve": "t", "un": "y",
            "uo": "o", "ie": "p", "iong": "s", "ong": "s", "ai": "d", "en": "f",
            "eng": "g", "ang": "h", "an": "j", "uai": "k", "ing": "k", "iang": "l",
            "uang": "l", "ou": "z", "ia": "x", "ua": "x", "ao": "c", "ui": "v",
            "in": "b", "iao": "n", "ian": "m",
        },
        "zero": {
            "a": "aa", "o": "oo", "e": "ee", "ai": "ai", "ei": "ei", "ao": "ao",
            "ou": "ou", "an": "an", "en": "en", "ang": "ah", "eng": "eg", "er": "er",
        },
    },
    "abc": {  # 智能ABC
        "init": {"zh": "a", "ch": "e", "sh": "v"},
        "fin": {
            "ei": "q", "ian": "w", "iu": "r", "er": "r", "iang": "t", "uang": "t",
            "ing": "y", "uai": "y", "uo": "o", "uan": "p", "ong": "s", "iong": "s",
            "ia": "d", "ua": "d", "en": "f", "eng": "g", "ang": "h", "an": "j",
            "ao": "k", "ai": "l", "iao": "z", "ie": "x", "in": "c", "ou": "b",
            "un": "n", "ue": "m", "ve": "m", "ui": "m",
        },
        "zero": {
            "a": "oa", "o": "oo", "e": "oe", "ai": "ol", "ei": "oq", "ao": "ok",
            "ou": "ob", "an": "oj", "en": "of", "ang": "oh", "eng": "og", "er": "or",
        },
    },
    "mspy": {  # 微软双拼
        "init": {"zh": "v", "ch": "i", "sh": "u"},
        "fin": {
            "iu": "q", "ia": "w", "ua": "w", "er": "r", "uan": "r", "ue": "t",
            "uai": "y", "uo": "o", "un": "p", "ong": "s", "iong": "s", "uang": "d",
            "iang": "d", "en": "f", "eng": "g", "ang": "h", "an": "j", "ao": "k",
            "ai": "l", "ing": ";", "ei": "z", "ie": "x", "iao": "c", "ui": "v",
            "ve": "v", "ou": "b", "in": "n", "ian": "m",
        },
        "zero": {
            "a": "oa", "o": "oo", "e": "oe", "ai": "ol", "ei": "oz", "ao": "ok",
            "ou": "ob", "an": "oj", "en": "of", "ang": "oh", "eng": "og", "er": "or",
        },
    },
    "sogou": {  # 搜狗双拼
        "init": {"zh": "v", "ch": "i", "sh": "u"},
        "fin": {
            "iu": "q", "ia": "w", "ua": "w", "er": "r", "uan": "r", "ue": "t",
            "ve": "t", "uai": "y", "uo": "o", "un": "p", "ong": "s", "iong": "s",
            "uang": "d", "iang": "d", "en": "f", "eng": "g", "ang": "h", "an": "j",
            "ao": "k", "ai": "l", "ing": ";", "ei": "z", "ie": "x", "iao": "c",
            "ui": "v", "ou": "b", "in": "n", "ian": "m",
        },
        "zero": {
            "a": "oa", "o": "oo", "e": "oe", "ai": "ol", "ei": "oz", "ao": "ok",
            "ou": "ob", "an": "oj", "en": "of", "ang": "oh", "eng": "og", "er": "or",
        },
    },
    "ziguang": {  # 紫光双拼
        "init": {"zh": "u", "ch": "a", "sh": "i"},
        "fin": {
            "ao": "q", "en": "w", "an": "r", "eng": "t", "in": "y", "uo": "o",
            "ai": "p", "ang": "s", "ie": "d", "ian": "f", "iang": "g", "uang": "g",
            "ong": "h", "iong": "h", "er": "j", "iu": "j", "ei": "k", "uan": "l",
            "ing": ";", "ou": "z", "ia": "x", "ua": "x", "iao": "b", "ui": "n",
            "ue": "n", "ve": "n", "un": "m", "uai": "y",
        },
        "zero": {
            "a": "oa", "o": "oo", "e": "oe", "ai": "op", "ei": "ok", "ao": "oq",
            "ou": "oz", "an": "or", "en": "ow", "ang": "os", "eng": "ot", "er": "oj",
        },
    },
}

CN_EN_FILES: tuple[tuple[str, str | None], ...] = (
    ("cn_en.txt", None),
    ("cn_en_double_pinyin.txt", "double_pinyin"),
    ("cn_en_flypy.txt", "flypy"),
    ("cn_en_abc.txt", "abc"),
    ("cn_en_mspy.txt", "mspy"),
    ("cn_en_sogou.txt", "sogou"),
    ("cn_en_ziguang.txt", "ziguang"),
)


@dataclass(frozen=True)
class CnEnRule:
    line_no: int
    action: str
    word: str
    prefix_en: str
    cn_syls: tuple[str, ...]
    suffix_en: str
    emit_lower: bool
    note: str

    @property
    def rule_id(self) -> str:
        syl_str = " ".join(self.cn_syls)
        return f"cn_en_source.tsv:{self.line_no}:{self.action}:{self.word}:{syl_str}"


def syl_to_shuangpin(syl: str, scheme: str) -> str:
    sc = SHUANGPIN_SCHEMES[scheme]
    s = syl.lower()
    if s in sc["zero"]:
        return sc["zero"][s]
    if s[:2] in ("zh", "ch", "sh"):
        ini = sc["init"][s[:2]]
        fin = s[2:]
    else:
        ini = s[0]
        fin = s[1:]
    if fin == "v":
        fcode = "v"
    elif fin in sc["fin"]:
        fcode = sc["fin"][fin]
    else:
        fcode = fin
    return ini + fcode


def encode_cn_en_codes(
    prefix_en: str,
    cn_syls: tuple[str, ...],
    suffix_en: str,
    emit_lower: bool,
    scheme: str | None,
) -> list[str]:
    if scheme is None:
        cn_part = "".join(cn_syls)
    else:
        cn_part = "".join(syl_to_shuangpin(s, scheme) for s in cn_syls)
    primary = f"{prefix_en}{cn_part}{suffix_en}"
    codes = [primary]
    if emit_lower:
        lower = f"{prefix_en.lower()}{cn_part}{suffix_en.lower()}"
        if lower != primary:
            codes.append(lower)
    return codes


def load_cn_en_rules(
    source_path: pathlib.Path,
    valid_syls: set[str] | None = None,
) -> tuple[list[CnEnRule], list[str]]:
    rules: list[CnEnRule] = []
    errors: list[str] = []
    if not source_path.exists():
        errors.append(f"Missing CN-EN source file: {source_path}")
        return rules, errors

    seen_keys: set[tuple[str, str, tuple[str, ...], str, str]] = set()
    for idx, raw in enumerate(source_path.read_text(encoding="utf-8").splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        cols = raw.split("\t")
        if len(cols) != 7:
            errors.append(f"{source_path.name}:{idx}: expected 7 tab-separated columns, got {len(cols)}")
            continue
        action, word, prefix_en, cn_syls_raw, suffix_en, emit_lower_raw, note = cols
        if action not in {"delete", "rename", "case_fix", "add", "replace"}:
            errors.append(f"{source_path.name}:{idx}: invalid action '{action}'")
            continue
        if not word:
            errors.append(f"{source_path.name}:{idx}: empty word")
            continue
        syls = tuple(cn_syls_raw.split()) if cn_syls_raw else ()
        emit_lower = False
        if action == "rename" and not prefix_en:
            errors.append(f"{source_path.name}:{idx}: rename requires new word in prefix_en column")
            continue
        if action == "case_fix" and (not prefix_en or not suffix_en):
            errors.append(f"{source_path.name}:{idx}: case_fix requires old prefix in prefix_en and new prefix in suffix_en")
            continue
        if action in {"add", "replace"}:
            if not syls:
                errors.append(f"{source_path.name}:{idx}: {action} requires cn_syls")
                continue
            if emit_lower_raw not in {"true", "false"}:
                errors.append(f"{source_path.name}:{idx}: emit_lower must be 'true' or 'false', got '{emit_lower_raw}'")
                continue
            emit_lower = emit_lower_raw == "true"
            if valid_syls is not None:
                for sy in syls:
                    if sy not in valid_syls:
                        errors.append(f"{source_path.name}:{idx}: invalid syllable '{sy}' in '{word}'")
        key = (action, word, syls, prefix_en, suffix_en)
        if key in seen_keys:
            errors.append(f"{source_path.name}:{idx}: duplicate rule for {key}")
            continue
        seen_keys.add(key)
        rules.append(CnEnRule(idx, action, word, prefix_en, syls, suffix_en, emit_lower, note))

    # Cross-action conflicts: cannot delete and add/rename the same word
    deleted_words = {r.word for r in rules if r.action == "delete"}
    for r in rules:
        if r.action == "add" and r.word in deleted_words:
            errors.append(f"{source_path.name}:{r.line_no}: conflict: '{r.word}' is both deleted and added")
        if r.action == "rename" and (r.word in deleted_words or r.prefix_en in deleted_words):
            errors.append(f"{source_path.name}:{r.line_no}: conflict: rename '{r.word}' -> '{r.prefix_en}' overlaps delete")

    return rules, errors


def apply_cn_en_rules(
    src_root: pathlib.Path,
    dst_root: pathlib.Path,
    rules_path: pathlib.Path,
    manifest: dict | None = None,
    rule_hits: dict[str, int] | None = None,
    dry_run: bool = False,
) -> tuple[list[CnEnRule], list[str]]:
    rules, errors = load_cn_en_rules(rules_path)
    if errors:
        raise ValueError("Invalid cn_en_source.tsv:\n  " + "\n  ".join(errors))

    deletes = {r.word: r for r in rules if r.action == "delete"}
    renames = {r.word: r for r in rules if r.action == "rename"}
    replaces = {r.word: r for r in rules if r.action == "replace"}
    case_fixes = [r for r in rules if r.action == "case_fix"]
    additions = [r for r in rules if r.action == "add"]

    if rule_hits is not None:
        for r in rules:
            rule_hits.setdefault(r.rule_id, 0)

    en_dir = dst_root / "en_dicts"
    if not dry_run:
        en_dir.mkdir(parents=True, exist_ok=True)

    changed_files: list[str] = []
    for fname, scheme in CN_EN_FILES:
        src_path = src_root / "en_dicts" / fname
        if not src_path.exists():
            continue
        raw_text = src_path.read_text(encoding="utf-8")
        raw_lines = raw_text.splitlines()
        out_lines: list[str] = []
        seen: set[tuple[str, str]] = set()
        del_cnt = 0
        fix_cnt = 0
        add_cnt = 0

        for line in raw_lines:
            if not line.strip() or line.strip().startswith("#"):
                out_lines.append(line)
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                out_lines.append(line)
                continue
            w, code = parts[0], parts[1]
            if w in deletes:
                del_cnt += 1
                if rule_hits is not None:
                    rule_hits[deletes[w].rule_id] += 1
                continue
            if w in renames:
                r = renames[w]
                w = r.prefix_en
                fix_cnt += 1
                if rule_hits is not None:
                    rule_hits[r.rule_id] += 1
            if w in replaces:
                r = replaces[w]
                for rep_code in encode_cn_en_codes(r.prefix_en, r.cn_syls, r.suffix_en, r.emit_lower, scheme):
                    if (w, rep_code) not in seen:
                        seen.add((w, rep_code))
                        out_lines.append(f"{w}\t{rep_code}")
                        if rep_code != code:
                            fix_cnt += 1
                if rule_hits is not None:
                    rule_hits[r.rule_id] += 1
                continue
            for r in case_fixes:
                if w == r.word and code.startswith(r.prefix_en):
                    code = r.suffix_en + code[len(r.prefix_en):]
                    fix_cnt += 1
                    if rule_hits is not None:
                        rule_hits[r.rule_id] += 1
            if (w, code) in seen:
                continue
            seen.add((w, code))
            out_lines.append(f"{w}\t{code}")

        for r in additions:
            for code in encode_cn_en_codes(r.prefix_en, r.cn_syls, r.suffix_en, r.emit_lower, scheme):
                if (r.word, code) not in seen:
                    seen.add((r.word, code))
                    out_lines.append(f"{r.word}\t{code}")
                    add_cnt += 1
                    if rule_hits is not None:
                        rule_hits[r.rule_id] += 1
                else:
                    # Already present (idempotent pass) still counts as active presence
                    if rule_hits is not None:
                        rule_hits[r.rule_id] += 1

        new_text = "\n".join(out_lines) + "\n"
        if new_text != raw_text:
            changed_files.append(f"en_dicts/{fname}")
        if not dry_run:
            (en_dir / fname).write_text(new_text, encoding="utf-8", newline="\n")
        if manifest is not None:
            manifest["files"][f"en_dicts/{fname}"] = {
                "before": len(raw_lines),
                "after": len(out_lines),
                "fixed": fix_cnt,
                "deleted": del_cnt,
                "added": add_cnt,
            }

    return rules, changed_files


def main() -> None:
    ap = argparse.ArgumentParser(description="Build/sync all 7 en_dicts/cn_en*.txt tables from rules/cn_en_source.tsv.")
    ap.add_argument("--src-dir", type=pathlib.Path, default=REPO_ROOT)
    ap.add_argument("--out-dir", type=pathlib.Path, default=None)
    ap.add_argument("--rules-dir", type=pathlib.Path, default=REPO_ROOT / "rules")
    ap.add_argument("--check", action="store_true", help="Check whether all 7 files are already up to date (no write)")
    args = ap.parse_args()

    src_root = args.src_dir.resolve()
    dst_root = (args.out_dir or args.src_dir).resolve()
    rules_path = args.rules_dir.resolve() / "cn_en_source.tsv"
    manifest: dict = {"files": {}}
    rules, changed = apply_cn_en_rules(src_root, dst_root, rules_path, manifest=manifest, dry_run=args.check)
    if args.check:
        if changed:
            raise SystemExit(f"cn_en tables out of sync with {rules_path}: {changed}")
        print(f"OK: all 7 cn_en*.txt tables match {rules_path.name} ({len(rules)} rules).")
    else:
        print(f"Synced 7 cn_en*.txt tables using {len(rules)} rules ({len(changed)} files updated).")
        for rel, st in manifest["files"].items():
            print(f"  {rel:34s}: {st}")


if __name__ == "__main__":
    main()
