#!/usr/bin/env python3
"""
Scientific sentence & character accuracy evaluator for rime-chth1z using Weasel's rime.dll.
Follows the exact sentence splitting, synonym normalization, and Levenshtein CER protocol
of gaboolic/rime-schema-compare, supporting both Natural Double Pinyin (ZRM) and Full Pinyin.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Dict, List, Optional, Tuple

from pypinyin import Style, lazy_pinyin

# --- Text splitting (matching gaboolic/rime-schema-compare/text_pipeline.py) ---
_OPEN_CQ = "\u201c"
_CLOSE_CQ = "\u201d"
_QUOTE_EDGE_RE = re.compile(r'^[\s\"“”‘’]+|[\s\"“”‘’]+$')
_DUNHAO_OR_SHUMINGHAO_RE = re.compile(r"[、]|《|》")
_HANZI_ONLY_RE = re.compile(r"^[\u4e00-\u9fff]+$")
MIN_EVAL_HANZI_CHARS = 5

ZRM_INITIALS = {"zh": "v", "ch": "i", "sh": "u"}
ZRM_FINALS = {
    "iu": "q", "ia": "w", "ua": "w", "uan": "r", "van": "r",
    "ue": "t", "ve": "t", "ing": "y", "uai": "y", "uo": "o",
    "un": "p", "vn": "p", "ong": "s", "iong": "s", "iang": "d",
    "uang": "d", "en": "f", "eng": "g", "ang": "h", "ian": "m",
    "an": "j", "iao": "c", "ao": "k", "ai": "l", "ei": "z",
    "ie": "x", "ui": "v", "ou": "b", "in": "n",
}


def syllable_to_zrm(syl: str) -> str:
    s = syl.lower().replace("ü", "v")
    if s in ("a", "o", "e"):
        return s + s
    if s in ("ai", "an", "ao", "ei", "en", "er", "ou"):
        return s
    if s == "ang":
        return "ah"
    if s == "eng":
        return "eg"
    if len(s) >= 2 and s[:2] in ZRM_INITIALS:
        ini = ZRM_INITIALS[s[:2]]
        fin = s[2:]
    else:
        ini = s[0]
        fin = s[1:]
    if ini in ("j", "q", "x", "y") and fin == "v":
        fin = "u"
    fin = ZRM_FINALS.get(fin, fin)
    return ini + fin


def sentence_to_keys(sentence: str, double_pinyin: bool) -> str:
    syls = lazy_pinyin(sentence, style=Style.NORMAL, v_to_u=False, errors="ignore")
    cleaned = [s.replace("ü", "v").lower() for s in syls if s and s.isalpha()]
    if double_pinyin:
        return "".join(syllable_to_zrm(s) for s in cleaned)
    return "".join(cleaned)


def split_corpus_sentences(text: str) -> List[str]:
    parts: List[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        n = len(s)
        start = 0
        depth = 0
        i = 0

        def emit_before(idx: int) -> None:
            nonlocal start
            seg = _QUOTE_EDGE_RE.sub("", s[start:idx].strip()).strip()
            if seg:
                parts.append(seg)
            start = idx + 1

        while i < n:
            c = s[i]
            if depth == 0 and c in "：:" and i + 1 < n and s[i + 1] == _OPEN_CQ:
                emit_before(i)
                j = i + 2
                while j < n and s[j].isspace():
                    j += 1
                start = j
                depth = 1
                i = j
                continue
            if c == _OPEN_CQ:
                if depth == 0:
                    emit_before(i)
                    depth = 1
                else:
                    depth += 1
                    start = i + 1
                i += 1
                continue
            if c == _CLOSE_CQ:
                emit_before(i)
                depth = max(0, depth - 1)
                i += 1
                continue
            if c in "，,。":
                emit_before(i)
            elif c == "." and not (i > 0 and i + 1 < n and s[i - 1].isdigit() and s[i + 1].isdigit()):
                emit_before(i)
            i += 1

        tail = _QUOTE_EDGE_RE.sub("", s[start:].strip()).strip()
        if tail:
            parts.append(tail)

    return [
        p for p in parts
        if not _DUNHAO_OR_SHUMINGHAO_RE.search(p)
        and _HANZI_ONLY_RE.fullmatch(p)
        and len(p) >= MIN_EVAL_HANZI_CHARS
    ]


def normalize_syn(s: str) -> str:
    t = s.strip().replace("其它", "其他")
    return t.translate(str.maketrans("她它地得", "他他的的"))


def levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + (0 if ca == cb else 1)))
        prev = cur
    return prev[-1]


# --- librime C API ctypes bindings ---
class RimeTraits(ctypes.Structure):
    _fields_ = [
        ("data_size", ctypes.c_int),
        ("shared_data_dir", ctypes.c_char_p),
        ("user_data_dir", ctypes.c_char_p),
        ("distribution_name", ctypes.c_char_p),
        ("distribution_code_name", ctypes.c_char_p),
        ("distribution_version", ctypes.c_char_p),
        ("app_name", ctypes.c_char_p),
        ("modules", ctypes.POINTER(ctypes.c_char_p)),
        ("min_log_level", ctypes.c_int),
        ("log_dir", ctypes.c_char_p),
        ("prebuilt_data_dir", ctypes.c_char_p),
        ("staging_dir", ctypes.c_char_p),
    ]


class RimeComposition(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_int),
        ("cursor_pos", ctypes.c_int),
        ("sel_start", ctypes.c_int),
        ("sel_end", ctypes.c_int),
        ("preedit", ctypes.c_char_p),
    ]


class RimeCandidate(ctypes.Structure):
    _fields_ = [
        ("text", ctypes.c_char_p),
        ("comment", ctypes.c_char_p),
        ("reserved", ctypes.c_void_p),
    ]


class RimeMenu(ctypes.Structure):
    _fields_ = [
        ("page_size", ctypes.c_int),
        ("page_no", ctypes.c_int),
        ("is_last_page", ctypes.c_int),
        ("highlighted_candidate_index", ctypes.c_int),
        ("num_candidates", ctypes.c_int),
        ("candidates", ctypes.POINTER(RimeCandidate)),
        ("select_keys", ctypes.c_char_p),
    ]


class RimeContext(ctypes.Structure):
    _fields_ = [
        ("data_size", ctypes.c_int),
        ("composition", RimeComposition),
        ("menu", RimeMenu),
        ("commit_text_preview", ctypes.c_char_p),
        ("select_labels", ctypes.POINTER(ctypes.c_char_p)),
    ]


class RimeCommit(ctypes.Structure):
    _fields_ = [
        ("data_size", ctypes.c_int),
        ("text", ctypes.c_char_p),
    ]


def find_weasel_dir() -> pathlib.Path:
    base = pathlib.Path(r"C:\Program Files\Rime")
    cands = sorted(base.glob("weasel-*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for d in cands:
        if (d / "rime.dll").is_file():
            return d
    raise FileNotFoundError("Could not find Weasel rime.dll under C:\\Program Files\\Rime")


class RimeEngine:
    _dll = None
    _setup_done = False

    def __init__(self, weasel_dir: pathlib.Path, user_dir: pathlib.Path, log_dir: pathlib.Path):
        if RimeEngine._dll is None:
            os.add_dll_directory(str(weasel_dir))
            dll = ctypes.CDLL(str(weasel_dir / "rime.dll"))
            dll.RimeSetup.argtypes = [ctypes.POINTER(RimeTraits)]
            dll.RimeInitialize.argtypes = [ctypes.POINTER(RimeTraits)]
            dll.RimeFinalize.argtypes = []
            dll.RimeCreateSession.restype = ctypes.c_size_t
            dll.RimeDestroySession.argtypes = [ctypes.c_size_t]
            dll.RimeDestroySession.restype = ctypes.c_bool
            dll.RimeSelectSchema.argtypes = [ctypes.c_size_t, ctypes.c_char_p]
            dll.RimeSelectSchema.restype = ctypes.c_bool
            dll.RimeProcessKey.argtypes = [ctypes.c_size_t, ctypes.c_int, ctypes.c_int]
            dll.RimeProcessKey.restype = ctypes.c_bool
            dll.RimeClearComposition.argtypes = [ctypes.c_size_t]
            dll.RimeGetContext.argtypes = [ctypes.c_size_t, ctypes.POINTER(RimeContext)]
            dll.RimeGetContext.restype = ctypes.c_bool
            dll.RimeFreeContext.argtypes = [ctypes.POINTER(RimeContext)]
            dll.RimeGetCommit.argtypes = [ctypes.c_size_t, ctypes.POINTER(RimeCommit)]
            dll.RimeGetCommit.restype = ctypes.c_bool
            dll.RimeFreeCommit.argtypes = [ctypes.POINTER(RimeCommit)]
            dll.RimeSetOption.argtypes = [ctypes.c_size_t, ctypes.c_char_p, ctypes.c_bool]
            RimeEngine._dll = dll

        self.dll = RimeEngine._dll
        self._keep = [
            str(weasel_dir / "data").encode("mbcs"),
            str(user_dir).encode("mbcs"),
            b"Chth1zEval",
            b"Chth1zEval",
            b"1.0",
            b"rime.eval",
            str(log_dir).encode("mbcs"),
        ]
        t = RimeTraits()
        t.data_size = ctypes.sizeof(RimeTraits) - ctypes.sizeof(ctypes.c_int)
        t.shared_data_dir = self._keep[0]
        t.user_data_dir = self._keep[1]
        t.distribution_name = self._keep[2]
        t.distribution_code_name = self._keep[3]
        t.distribution_version = self._keep[4]
        t.app_name = self._keep[5]
        t.min_log_level = 3
        t.log_dir = self._keep[6]
        self._traits = t

        if not RimeEngine._setup_done:
            self.dll.RimeSetup(ctypes.byref(t))
            RimeEngine._setup_done = True
        self.dll.RimeInitialize(ctypes.byref(t))
        self.sid = self.dll.RimeCreateSession()

    def select_schema(self, schema_id: str) -> None:
        if not self.dll.RimeSelectSchema(self.sid, schema_id.encode("utf-8")):
            raise RuntimeError(f"RimeSelectSchema failed: {schema_id}")
        self.dll.RimeSetOption(self.sid, b"traditionalization", False)

    def decode_sentence(self, keys: str) -> Tuple[str, float]:
        self.dll.RimeClearComposition(self.sid)
        t0 = time.perf_counter()
        committed = []
        for ch in keys:
            self.dll.RimeProcessKey(self.sid, ord(ch), 0)
            cm = RimeCommit()
            cm.data_size = ctypes.sizeof(RimeCommit) - ctypes.sizeof(ctypes.c_int)
            if self.dll.RimeGetCommit(self.sid, ctypes.byref(cm)):
                if cm.text:
                    committed.append(cm.text.decode("utf-8", errors="ignore"))
                self.dll.RimeFreeCommit(ctypes.byref(cm))

        # Select candidate 1 repeatedly until composition finishes (handles >max_sentence chunks cleanly)
        guard = 0
        while guard < 16:
            ctx = RimeContext()
            ctx.data_size = ctypes.sizeof(RimeContext) - ctypes.sizeof(ctypes.c_int)
            if not self.dll.RimeGetContext(self.sid, ctypes.byref(ctx)):
                break
            has_menu = ctx.menu.num_candidates > 0
            preview = ctx.commit_text_preview.decode("utf-8", errors="ignore") if ctx.commit_text_preview else ""
            top1 = ""
            if has_menu:
                c0 = ctx.menu.candidates[0]
                top1 = c0.text.decode("utf-8", errors="ignore") if c0.text else ""
            self.dll.RimeFreeContext(ctypes.byref(ctx))
            if not has_menu:
                if preview:
                    committed.append(preview)
                break
            # Press Space (0x20) to commit/confirm top1
            self.dll.RimeProcessKey(self.sid, 0x20, 0)
            cm = RimeCommit()
            cm.data_size = ctypes.sizeof(RimeCommit) - ctypes.sizeof(ctypes.c_int)
            if self.dll.RimeGetCommit(self.sid, ctypes.byref(cm)):
                if cm.text:
                    committed.append(cm.text.decode("utf-8", errors="ignore"))
                self.dll.RimeFreeCommit(ctypes.byref(cm))
                break
            guard += 1
        dt_ms = (time.perf_counter() - t0) * 1000.0
        return "".join(committed), dt_ms

    def close(self) -> None:
        self.dll.RimeDestroySession(self.sid)
        self.dll.RimeFinalize()


def create_isolated_env(rime_dir: pathlib.Path, schema_id: str, yaml_overrides: Optional[Dict[str, str]] = None) -> pathlib.Path:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="rime-eval-"))
    (tmp / "logs").mkdir()
    (tmp / "build").mkdir()
    for d in ("lua", "opencc", "cn_dicts", "cn_dicts_cell", "en_dicts"):
        src = rime_dir / d
        if src.exists():
            subprocess.run(["cmd", "/c", "mklink", "/J", str(tmp / d), str(src)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    for f in (rime_dir / "build").iterdir():
        if f.is_file():
            if f.suffix == ".bin":
                subprocess.run(["cmd", "/c", "mklink", "/H", str(tmp / "build" / f.name), str(f)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            else:
                shutil.copy2(f, tmp / "build" / f.name)
    for f in rime_dir.iterdir():
        if f.is_file() and f.suffix in (".yaml", ".lua", ".txt"):
            shutil.copy2(f, tmp / f.name)
        elif f.is_file() and f.suffix == ".gram":
            subprocess.run(["cmd", "/c", "mklink", "/H", str(tmp / f.name), str(f)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # Disable user_dict for clean reproducible evaluation & apply overrides in compiled build/<schema>.schema.yaml
    schema_path = tmp / "build" / f"{schema_id}.schema.yaml"
    raw = schema_path.read_text(encoding="utf-8")

    # Ensure enable_user_dict: false under translator:
    if re.search(r"(?m)^  enable_user_dict:", raw):
        raw = re.sub(r"(?m)^  enable_user_dict:.*$", "  enable_user_dict: false", raw)
    else:
        raw = re.sub(r"(?m)^translator:\r?\n", "translator:\n  enable_user_dict: false\n", raw, count=1)

    if yaml_overrides:
        for section_key, val in yaml_overrides.items():
            sec, key = section_key.split("/", 1)
            # Replace existing key inside section or insert right after section header
            sec_re = re.compile(rf"(?m)^{re.escape(sec)}:\r?\n((?:  .*\r?\n)*)")
            m = sec_re.search(raw)
            if m:
                body = m.group(1)
                key_re = re.compile(rf"(?m)^  {re.escape(key)}:.*$")
                if key_re.search(body):
                    new_body = key_re.sub(f"  {key}: {val}", body, count=1)
                else:
                    new_body = f"  {key}: {val}\n" + body
                raw = raw[:m.start(1)] + new_body + raw[m.end(1):]
            else:
                raw += f"\n{sec}:\n  {key}: {val}\n"

    schema_path.write_text(raw, encoding="utf-8")
    return tmp


def cleanup_isolated_env(tmp: pathlib.Path) -> None:
    for d in ("lua", "opencc", "cn_dicts", "cn_dicts_cell", "en_dicts"):
        p = tmp / d
        if p.exists():
            subprocess.run(["cmd", "/c", "rmdir", str(p)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.rmtree(tmp, ignore_errors=True)


def evaluate(
    rime_dir: pathlib.Path,
    schema_id: str,
    sentences: List[str],
    overrides: Optional[Dict[str, str]] = None,
    show_errors: int = 0,
) -> Dict[str, float]:
    weasel_dir = find_weasel_dir()
    double_pinyin = "double_pinyin" in schema_id
    pairs = [(s, sentence_to_keys(s, double_pinyin)) for s in sentences]
    pairs = [(s, k) for s, k in pairs if k]

    tmp = create_isolated_env(rime_dir, schema_id, overrides)
    try:
        eng = RimeEngine(weasel_dir, tmp, tmp / "logs")
        eng.select_schema(schema_id)
        # Warmup
        eng.decode_sentence("nihk" if double_pinyin else "nihao")

        exact = 0
        total_chars = 0
        total_ed = 0
        total_keys = 0
        total_ms = 0.0
        errors: List[Tuple[int, str, str, str]] = []

        for gold, keys in pairs:
            pred, ms = eng.decode_sentence(keys)
            ng, np = normalize_syn(gold), normalize_syn(pred)
            ed = levenshtein(np, ng)
            if np == ng:
                exact += 1
            else:
                errors.append((ed, gold, pred, keys))
            total_chars += len(ng)
            total_ed += ed
            total_keys += len(keys)
            total_ms += ms

        eng.close()
    finally:
        cleanup_isolated_env(tmp)

    n = len(pairs)
    sent_acc = exact / n * 100.0 if n else 0.0
    char_acc = (1.0 - total_ed / total_chars) * 100.0 if total_chars else 0.0
    ms_per_key = total_ms / total_keys if total_keys else 0.0

    if show_errors > 0:
        errors.sort(key=lambda x: -x[0])
        print(f"  Top {min(show_errors, len(errors))} mismatches (total {len(errors)}/{n}):")
        for ed, gold, pred, keys in errors[:show_errors]:
            print(f"    [ed={ed}] gold={gold} | pred={pred}")

    return {
        "n": n,
        "exact": exact,
        "sent_acc": sent_acc,
        "char_acc": char_acc,
        "ms_per_key": ms_per_key,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rime-dir", default=os.path.join(os.environ["APPDATA"], "Rime"))
    ap.add_argument("--schema", default="rime_frost_double_pinyin")
    ap.add_argument("--corpus", required=True, help="Path to corpus .txt file")
    ap.add_argument("--limit", type=int, default=0, help="Max sentences (0 = all)")
    ap.add_argument("--override", action="append", default=[], help="section/key=value")
    ap.add_argument("--show-errors", type=int, default=0)
    args = ap.parse_args()

    text = pathlib.Path(args.corpus).read_text(encoding="utf-8")
    sents = split_corpus_sentences(text)
    if args.limit > 0:
        sents = sents[:args.limit]

    overrides = {}
    for item in args.override:
        k, v = item.split("=", 1)
        overrides[k] = v

    res = evaluate(pathlib.Path(args.rime_dir), args.schema, sents, overrides, args.show_errors)
    print(
        f"[{args.schema}] n={res['n']} | sent_acc={res['sent_acc']:.2f}% ({res['exact']}/{res['n']}) "
        f"| char_acc={res['char_acc']:.2f}% | {res['ms_per_key']:.2f} ms/key"
    )


if __name__ == "__main__":
    main()
