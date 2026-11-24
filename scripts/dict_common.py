#!/usr/bin/env python3
"""
Shared constants, dictionary entry parsing/formatting, syllable validation,
and atomic file-write primitives for rime-chth1z Python pipeline modules.
"""
from __future__ import annotations

import os
import pathlib
import re
import tempfile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Single authoritative ordering of the 26 active Chinese dictionaries
# (excluding corrections.dict.yaml and disabled luna.dict.yaml).
# Both clean-dicts.py cross-file deduplication and rime_frost.dict.yaml
# import_tables follow this exact order.
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

MANAGED_EN_DICTS: set[str] = {
    "en_dicts/en_ext.dict.yaml",
    "en_dicts/en.dict.yaml",
}

MANAGED_OPENCC_TXTS: set[str] = {
    "opencc/others.txt",
    "opencc/chinese_english.txt",
    "opencc/english_chinese.txt",
    "opencc/emoji.txt",
}

EXTRA_VALID_SYLS: frozenset[str] = frozenset({"hm", "hng", "m", "n", "ng"})
STRICT_SYL_RE = re.compile(r"^[a-z]+$")
LUE_NUE_RE = re.compile(r"\b[ln]ue\b")


def split_header_body(lines: list[str]) -> tuple[list[str], list[str]]:
    """Split a Rime .dict.yaml file into header (up to and including '...') and body."""
    for i, line in enumerate(lines):
        if line.strip() == "...":
            return lines[: i + 1], lines[i + 1 :]
    return [], lines


def split_header_body_with_lineno(lines: list[str]) -> tuple[list[str], list[str], int]:
    """Split a Rime .dict.yaml file into (header, body, 1-based starting line number of body)."""
    for i, line in enumerate(lines):
        if line.strip() == "...":
            return lines[: i + 1], lines[i + 1 :], i + 2
    return [], lines, 1


def parse_entry(line: str) -> tuple[str, str, str, list[str]] | None:
    """Return (word, py, weight, extra_cols) or None if comment/blank/non-tab line."""
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


def format_entry(w: str, py: str, wt: str, extra: list[str]) -> str:
    cols = [w, py]
    if wt != "" or extra:
        cols.append(wt)
    cols.extend(extra)
    return "\t".join(cols)


def w_int(wt: str) -> int:
    try:
        return int(wt)
    except (ValueError, TypeError):
        return 0


def normalize_lue_nue(py: str) -> str:
    return re.sub(r"\b([ln])ue\b", r"\1ve", py)


def extract_valid_syls_from_lines(
    lines: list[str],
    strict_errors: list[str] | None = None,
    source_label: str = "cn_dicts/8105.dict.yaml",
) -> set[str]:
    """Extract strictly validated lowercase ASCII pinyin syllables from 8105.dict.yaml lines."""
    valid: set[str] = set(EXTRA_VALID_SYLS)
    _, body, start_idx = split_header_body_with_lineno(lines)
    for idx, line in enumerate(body, start_idx):
        p = parse_entry(line)
        if not p:
            continue
        w, py, _, _ = p
        if not STRICT_SYL_RE.fullmatch(py) or LUE_NUE_RE.search(py):
            if strict_errors is not None:
                strict_errors.append(
                    f"{source_label}:{idx}: invalid syllable '{py}' for '{w}' in 8105 reference table"
                )
            continue
        valid.add(py)
    return valid


def load_valid_syls(
    root: pathlib.Path,
    strict_errors: list[str] | None = None,
) -> set[str]:
    """Load and validate the reference syllable set from cn_dicts/8105.dict.yaml + EXTRA_VALID_SYLS."""
    p = root / "cn_dicts/8105.dict.yaml"
    if not p.exists():
        if strict_errors is not None:
            strict_errors.append(f"missing reference syllable table: {p}")
        return set(EXTRA_VALID_SYLS)
    lines = p.read_text(encoding="utf-8").splitlines()
    return extract_valid_syls_from_lines(lines, strict_errors=strict_errors)


def atomic_write_text(path: pathlib.Path, text: str) -> bool:
    """
    Write UTF-8 LF text atomically via a sibling temp file and os.replace().
    Returns True if the file was written (created or content changed), False if unchanged.
    """
    data = text.encode("utf-8")
    if path.exists():
        try:
            if path.read_bytes() == data:
                return False
        except OSError:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as fh:
            tmp_path = fh.name
            fh.write(data)
            fh.flush()
        os.replace(tmp_path, path)
        tmp_path = None
        return True
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
