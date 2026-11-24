#!/usr/bin/env python3
"""
Deterministic unit test suite for rime-chth1z dictionary pipeline:
  - build_cn_en.py shuangpin encoding & rule conflict guards
  - dict_rules.py static conflict & validation guards
  - dict_lint.py negative defect-injection guards
  - clean-dicts.py zero ping-pong, span guardrails, precedence, OpenCC NBSP,
    weight-preserving dedup, and in-memory verification before atomic writes
"""
from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import unittest
from collections import Counter

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import build_cn_en  # noqa: E402
import dict_common  # noqa: E402
import dict_lint  # noqa: E402
import dict_rules  # noqa: E402


def _load_clean_dicts():
    spec = importlib.util.spec_from_file_location("clean_dicts_under_test", SCRIPTS_DIR / "clean-dicts.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


clean_dicts = _load_clean_dicts()


def _create_empty_rules_dir(rules_dir: pathlib.Path) -> None:
    rules_dir.mkdir(parents=True, exist_ok=True)
    for fname in (
        "phonetics_fix.tsv",
        "word_fixes.tsv",
        "dual_readings.tsv",
        "corrections.tsv",
        "weights.tsv",
        "deletions.tsv",
        "additions.tsv",
        "en_additions.tsv",
        "en_fixes.tsv",
        "cn_en_source.tsv",
        "alphanum_additions.txt",
        "opencc_fixes.tsv",
    ):
        (rules_dir / fname).write_text("# header\n", encoding="utf-8", newline="\n")


def _create_mini_repo(root: pathlib.Path) -> None:
    """Create a minimal valid repository layout with all 28 CN dicts, EN dicts, OpenCC, and rime_frost.dict.yaml."""
    _create_empty_rules_dir(root / "rules")
    (root / "cn_dicts").mkdir(parents=True, exist_ok=True)
    (root / "cn_dicts_cell").mkdir(parents=True, exist_ok=True)
    (root / "en_dicts").mkdir(parents=True, exist_ok=True)
    (root / "opencc").mkdir(parents=True, exist_ok=True)

    header_tpl = "---\nname: {name}\nversion: \"1\"\n...\n"
    for rel in dict_common.ALL_CN_DICTS:
        name = pathlib.Path(rel).name.replace(".dict.yaml", "")
        body = ""
        if rel == "cn_dicts/8105.dict.yaml":
            body = "于\tyu\t100\n传\tzhuan\t100\n传\tchuan\t100\n有\tyou\t100\n之\tzhi\t100\n词\tci\t100\n试\tshi\t100\n测\tce\t100\n"
        (root / rel).write_text(header_tpl.format(name=name) + body, encoding="utf-8", newline="\n")

    imp_lines = [f"  - {rel[:-len('.dict.yaml')]}" for rel in dict_common.ACTIVE_CN_DICTS]
    # Insert corrections right after others
    idx_others = imp_lines.index("  - cn_dicts/others")
    imp_lines.insert(idx_others + 1, "  - cn_dicts/corrections")
    rf_text = (
        "---\nname: rime_frost\nversion: \"1\"\nimport_tables:\n"
        + "\n".join(imp_lines)
        + "\n...\nM4A1\n# 加入词典，响应 opencc/others.txt\nV动物\n"
    )
    (root / "rime_frost.dict.yaml").write_text(rf_text, encoding="utf-8", newline="\n")

    for rel in ("en_dicts/en_ext.dict.yaml", "en_dicts/en.dict.yaml"):
        name = pathlib.Path(rel).name.replace(".dict.yaml", "")
        (root / rel).write_text(header_tpl.format(name=name), encoding="utf-8", newline="\n")
    for fname, _ in build_cn_en.CN_EN_FILES:
        (root / "en_dicts" / fname).write_text("# cn_en\n", encoding="utf-8", newline="\n")
    for rel in dict_common.MANAGED_OPENCC_TXTS:
        (root / rel).write_text("测试\t测试 test\n", encoding="utf-8", newline="\n")


class TestShuangpinEncoding(unittest.TestCase):
    def test_no_dead_er_in_fin_tables(self) -> None:
        for scheme, cfg in build_cn_en.SHUANGPIN_SCHEMES.items():
            self.assertNotIn("er", cfg["fin"], f"Dead shadowed 'er' found in {scheme} fin table")

    def test_all_8105_syllables_across_all_6_schemes(self) -> None:
        syl_errors: list[str] = []
        valid_syls = dict_common.load_valid_syls(REPO_ROOT, strict_errors=syl_errors)
        self.assertEqual(syl_errors, [])
        standard_syls = valid_syls - dict_common.EXTRA_VALID_SYLS
        self.assertGreaterEqual(len(standard_syls), 400)

        for scheme in build_cn_en.SHUANGPIN_SCHEMES:
            for syl in sorted(standard_syls):
                code = build_cn_en.syl_to_shuangpin(syl, scheme)
                self.assertEqual(
                    len(code), 2,
                    f"Expected 2-char shuangpin code for ({syl}, {scheme}), got {code!r}",
                )
                self.assertTrue(
                    all("a" <= ch <= "z" or ch == ";" for ch in code),
                    f"Unexpected char in shuangpin code {code!r} for ({syl}, {scheme})",
                )

    def test_critical_edge_syllables_match_rime_neural(self) -> None:
        expected = {
            # (syl, scheme): expected_code (cross-checked against rime-neural/src/pinyin.rs)
            ("nv", "double_pinyin"): "nv",
            ("lv", "double_pinyin"): "lv",
            ("nve", "double_pinyin"): "nt",
            ("lve", "double_pinyin"): "lt",
            ("er", "double_pinyin"): "er",
            ("nv", "flypy"): "nv",
            ("lv", "flypy"): "lv",
            ("nve", "flypy"): "nt",
            ("lve", "flypy"): "lt",
            ("er", "flypy"): "er",
            ("nv", "abc"): "nv",
            ("lv", "abc"): "lv",
            ("nve", "abc"): "nm",
            ("lve", "abc"): "lm",
            ("er", "abc"): "or",
            ("nv", "mspy"): "ny",
            ("lv", "mspy"): "ly",
            ("nve", "mspy"): "nv",
            ("lve", "mspy"): "lv",
            ("er", "mspy"): "or",
            ("jing", "mspy"): "j;",
            ("nv", "sogou"): "ny",
            ("lv", "sogou"): "ly",
            ("nve", "sogou"): "nt",
            ("lve", "sogou"): "lt",
            ("er", "sogou"): "or",
            ("jing", "sogou"): "j;",
            ("nv", "ziguang"): "nv",
            ("lv", "ziguang"): "lv",
            ("nve", "ziguang"): "nn",
            ("lve", "ziguang"): "ln",
            ("er", "ziguang"): "oj",
            ("jing", "ziguang"): "j;",
        }
        for (syl, scheme), want in expected.items():
            got = build_cn_en.syl_to_shuangpin(syl, scheme)
            self.assertEqual(got, want, f"Mismatch for ({syl}, {scheme}): got {got!r}, want {want!r}")

    def test_inverse_decoding_consistency(self) -> None:
        """Verify every standard syllable's shuangpin code maps back to the original initial+final."""
        valid_syls = dict_common.load_valid_syls(REPO_ROOT) - dict_common.EXTRA_VALID_SYLS
        for scheme, cfg in build_cn_en.SHUANGPIN_SCHEMES.items():
            inv_zero = {v: k for k, v in cfg["zero"].items()}
            inv_init: dict[str, set[str]] = {}
            for k, v in cfg["init"].items():
                inv_init.setdefault(v, set()).add(k)
            inv_fin: dict[str, set[str]] = {}
            for k, v in cfg["fin"].items():
                inv_fin.setdefault(v, set()).add(k)
            for ch in "aeiouv":
                if ch not in cfg["fin"]:
                    inv_fin.setdefault(ch, set()).add(ch)

            for syl in valid_syls:
                code = build_cn_en.syl_to_shuangpin(syl, scheme)
                if syl in cfg["zero"]:
                    self.assertEqual(inv_zero.get(code), syl)
                else:
                    ini_c, fin_c = code[0], code[1]
                    cand_inits = inv_init.get(ini_c, set()) | {ini_c}
                    cand_fins = inv_fin.get(fin_c, set()) | {fin_c}
                    reconstructed = {i + f for i in cand_inits for f in cand_fins}
                    self.assertIn(syl, reconstructed, f"Round-trip failed for ({syl}, {scheme}) -> {code}")


class TestStaticConflictGuards(unittest.TestCase):
    def test_weights_vs_dual_readings_exact_and_wild(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rdir = pathlib.Path(td)
            _create_empty_rules_dir(rdir)
            (rdir / "dual_readings.tsv").write_text(
                "测试\tce shi\t100\t规范 cè shì / 习惯 cè sì\tce si\t50\t习惯 cè sì / 规范 cè shì\tcn_dicts/base.dict.yaml\tsrc\n",
                encoding="utf-8",
                newline="\n",
            )
            (rdir / "weights.tsv").write_text(
                "cn_dicts/base.dict.yaml\t测试\tce shi\t100\tdup\n"
                "cn_dicts/base.dict.yaml\t测试\t*\t100\twild dup\n",
                encoding="utf-8",
                newline="\n",
            )
            rs = dict_rules.load_ruleset(rdir, valid_syls={"ce", "shi", "si"})
            self.assertTrue(any("weights.tsv:1" in e and "dual_readings.tsv" in e for e in rs.errors), rs.errors)
            self.assertTrue(any("weights.tsv:2" in e and "dual_readings.tsv" in e for e in rs.errors), rs.errors)

    def test_additions_vs_dual_and_cross_file_dup(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rdir = pathlib.Path(td)
            _create_empty_rules_dir(rdir)
            (rdir / "dual_readings.tsv").write_text(
                "测试\tce shi\t100\t规范 cè shì / 习惯 cè sì\tce si\t50\t习惯 cè sì / 规范 cè shì\tcn_dicts/base.dict.yaml\tsrc\n",
                encoding="utf-8",
                newline="\n",
            )
            (rdir / "additions.tsv").write_text(
                "cn_dicts/base.dict.yaml\t测试\tce shi\t100\tcommon\tsrc\n"
                "cn_dicts/base.dict.yaml\t词条\tci tiao\t50\tcommon\tsrc\n"
                "cn_dicts/ext.dict.yaml\t词条\tci tiao\t50\tcommon\tsrc\n",
                encoding="utf-8",
                newline="\n",
            )
            rs = dict_rules.load_ruleset(rdir, valid_syls={"ce", "shi", "si", "ci", "tiao"})
            self.assertTrue(any("additions.tsv:1" in e and "dual_readings.tsv" in e for e in rs.errors), rs.errors)
            self.assertTrue(any("additions.tsv:3" in e and "additions.tsv:2" in e for e in rs.errors), rs.errors)

    def test_word_fixes_to_phonetics_fix_chain(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rdir = pathlib.Path(td)
            _create_empty_rules_dir(rdir)
            (rdir / "word_fixes.tsv").write_text(
                "cn_dicts/base.dict.yaml\t旧词\t*\t新词\t*\treason\tsrc\n",
                encoding="utf-8",
                newline="\n",
            )
            (rdir / "phonetics_fix.tsv").write_text(
                "cn_dicts/base.dict.yaml\t新词\tjiu ci\txin ci\treason\tsrc\n",
                encoding="utf-8",
                newline="\n",
            )
            rs = dict_rules.load_ruleset(rdir, valid_syls={"jiu", "xin", "ci"})
            self.assertTrue(any("word_fixes.tsv:1" in e and "chains into phonetics_fix.tsv:1" in e for e in rs.errors), rs.errors)

    def test_en_fixes_and_opencc_fixes_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rdir = pathlib.Path(td)
            _create_empty_rules_dir(rdir)
            (rdir / "en_fixes.tsv").write_text(
                "en_dicts/en_ext.dict.yaml\tFoo\t*\tdelete\t\t\t\tdel\n"
                "en_dicts/en_ext.dict.yaml\tFoo\tFoo\treplace\tBar\tBar\t\trep\n"
                "en_dicts/en_ext.dict.yaml\tBaz\tBaz\treplace\tQux\tQux·1\t\tbad ascii\n"
                "en_dicts/en_ext.dict.yaml\tA\tA\treplace\tB\tB\t\tstep1\n"
                "en_dicts/en_ext.dict.yaml\tB\tB\treplace\tC\tC\t\tstep2\n",
                encoding="utf-8",
                newline="\n",
            )
            (rdir / "opencc_fixes.tsv").write_text(
                "opencc/others.txt\t甲\trename\t乙|乙 val\tcollide with key\n"
                "opencc/others.txt\t乙\treplace\t乙 val2\texisting rule\n",
                encoding="utf-8",
                newline="\n",
            )
            rs = dict_rules.load_ruleset(rdir, valid_syls=set())
            self.assertTrue(any("en_fixes.tsv:2" in e and "wildcard delete" in e for e in rs.errors), rs.errors)
            self.assertTrue(any("en_fixes.tsv:3" in e and "non-ASCII" in e for e in rs.errors), rs.errors)
            self.assertTrue(any("en_fixes.tsv:4" in e and "chained replace" in e for e in rs.errors), rs.errors)
            self.assertTrue(any("opencc_fixes.tsv:1" in e and "collides with another rule key" in e for e in rs.errors), rs.errors)

    def test_cn_en_source_conflicts_and_bom_crlf(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "cn_en_source.tsv"
            # BOM + CRLF + delete vs replace + delete vs case_fix + replace vs add + rename vs replace
            content = (
                "delete\t词A\t\t\t\t\tdel\r\n"
                "replace\t词A\tA\tci\t\ttrue\trep\r\n"
                "case_fix\t词A\tA\t\ta\t\tcf\r\n"
                "replace\t词B\tB\tci\t\ttrue\trep\r\n"
                "add\t词B\tB\tci\t\ttrue\tadd\r\n"
                "rename\t旧B\t词B\t\t\t\tren\r\n"
                "add\t词C\tC\tbadzz\t\ttrue\tbad syl\r\n"
            )
            p.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
            _, errs = build_cn_en.load_cn_en_rules(p, valid_syls={"ci"})
            self.assertTrue(any("UTF-8 BOM" in e for e in errs), errs)
            self.assertTrue(any("CRLF" in e for e in errs), errs)
            self.assertTrue(any("both deleted and replaced" in e for e in errs), errs)
            self.assertTrue(any("both deleted and case_fix" in e for e in errs), errs)
            self.assertTrue(any("both replace and add" in e for e in errs), errs)
            self.assertTrue(any("overlaps replace" in e for e in errs), errs)
            self.assertTrue(any("invalid syllable 'badzz'" in e for e in errs), errs)


class TestDictLintNegativeGuards(unittest.TestCase):
    def test_8105_corrupted_syllable_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "cn_dicts").mkdir()
            (root / "cn_dicts/8105.dict.yaml").write_text(
                "---\nname: 8105\n...\n好\thao\t10\n坏\tbad123\t10\n略\tlue\t10\n",
                encoding="utf-8",
                newline="\n",
            )
            errs: list[str] = []
            vs = dict_common.load_valid_syls(root, strict_errors=errs)
            self.assertIn("hao", vs)
            self.assertNotIn("bad123", vs)
            self.assertNotIn("lue", vs)
            self.assertEqual(len(errs), 2, errs)

    def test_hygiene_and_cn_invariant_negative_cases(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _create_mini_repo(root)
            # Inject hygiene errors into base.dict.yaml: empty col, double space in py, trailing space in wt, \t\t, C0 char, negative weight
            base = root / "cn_dicts/base.dict.yaml"
            base.write_text(
                "---\nname: base\n...\n"
                "\tce\t1\n"
                "测试\tce  shi\t1\n"
                "测试\tce shi\t1 \n"
                "测试\tce shi\t\t1\n"
                "测试\tce shi\t-5\n"
                "测\x07试\tce shi\t1\n",
                encoding="utf-8",
                newline="\n",
            )
            # Inject BOM + CRLF on melt_eng.schema.yaml and opencc/test.json
            (root / "melt_eng.schema.yaml").write_bytes(b"\xef\xbb\xbfschema:\r\n  id: melt_eng\r\n")
            (root / "opencc/test.json").write_bytes(b"{\"name\": \"t\"}\r\n")

            hyg_errs: list[str] = []
            dict_lint.check_hygiene(root, hyg_errs)
            self.assertTrue(any("empty text or code column" in e for e in hyg_errs), hyg_errs)
            self.assertTrue(any("double space inside code column" in e for e in hyg_errs), hyg_errs)
            self.assertTrue(any("trailing whitespace in column 3" in e for e in hyg_errs), hyg_errs)
            self.assertTrue(any("consecutive tabs" in e for e in hyg_errs), hyg_errs)
            self.assertTrue(any("C0/C1 control character" in e for e in hyg_errs), hyg_errs)
            self.assertTrue(any("melt_eng.schema.yaml: UTF-8 BOM" in e for e in hyg_errs), hyg_errs)
            self.assertTrue(any("opencc/test.json: CRLF" in e for e in hyg_errs), hyg_errs)

            # Check negative weight & cross-dict reading conflict in check_cn_invariants
            (root / "cn_dicts_cell/literature.dict.yaml").write_text(
                "---\nname: literature\n...\n测试\tce shi\t10\n",
                encoding="utf-8",
                newline="\n",
            )
            (root / "cn_dicts_cell/idiom.dict.yaml").write_text(
                "---\nname: idiom\n...\n测试\tce ci\t10\n",
                encoding="utf-8",
                newline="\n",
            )
            valid_syls = dict_common.load_valid_syls(root)
            rs = dict_rules.load_ruleset(root / "rules", valid_syls=valid_syls)
            cn_errs: list[str] = []
            cn_warns: list[str] = []
            dict_lint.check_cn_invariants(root, valid_syls, rs, cn_errs, cn_warns)
            self.assertTrue(any("negative weight -5" in e for e in cn_errs), cn_errs)
            self.assertTrue(any("cross-dict reading conflict for '测试'" in e for e in cn_errs), cn_errs)

    def test_opencc_symbols_v_and_import_tables_negative_cases(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _create_mini_repo(root)
            # 1. Corrupt opencc files
            (root / "opencc/chinese_english.txt").write_text("骂\t骂 ****\n", encoding="utf-8", newline="\n")
            (root / "opencc/english_chinese.txt").write_text(
                "foo\tfoo bar:n.glued\n"
                "baz\tbaz v.ok vbl.\n",
                encoding="utf-8",
                newline="\n",
            )
            (root / "opencc/emoji.txt").write_text("右上\t右上 ↗️ ↗\n", encoding="utf-8", newline="\n")
            (root / "opencc/broken.json").write_text(
                '{"segmentation": {"type": "mmseg", "dict": {"type": "text", "file": "does_not_exist.txt"}}}\n',
                encoding="utf-8",
                newline="\n",
            )
            # 2. Duplicate YAML key & /vs collision in symbols_v.yaml
            (root / "symbols_v.yaml").write_text(
                "symbols:\n  '/a': ['α']\n  '/a': ['β']\n  '/vsx': ['x']\n",
                encoding="utf-8",
                newline="\n",
            )
            # 3. Swap two import_tables in rime_frost.dict.yaml
            rf_txt = (root / "rime_frost.dict.yaml").read_text(encoding="utf-8")
            rf_txt = rf_txt.replace(
                "  - cn_dicts_cell/literature\n  - cn_dicts_cell/idiom",
                "  - cn_dicts_cell/idiom\n  - cn_dicts_cell/literature",
            )
            (root / "rime_frost.dict.yaml").write_text(rf_txt, encoding="utf-8", newline="\n")

            errs: list[str] = []
            warns: list[str] = []
            dict_lint.check_schema_and_opencc(root, errs, warns, strict=True)
            self.assertTrue(any("censored '****'" in e for e in errs), errs)
            self.assertTrue(any("glued entry/POS token" in e for e in errs), errs)
            self.assertTrue(any("trailing empty POS tag" in e for e in errs), errs)
            self.assertTrue(any("duplicate VS16/non-VS16" in e for e in errs), errs)
            self.assertTrue(any("does_not_exist.txt" in e for e in errs), errs)
            self.assertTrue(any("duplicate YAML key '/a'" in e for e in errs), errs)
            self.assertTrue(any("collides with calculator prefix '/vs'" in e for e in errs), errs)
            self.assertTrue(any("import_tables order differs" in e for e in errs), errs)

    def test_diff_budget_catches_zero_net_delta_swap_and_non_primary_cn_en(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _create_mini_repo(root)
            base = root / "cn_dicts/base.dict.yaml"
            base.write_text(
                "---\nname: base\n...\n" + "".join(f"词{i}\tci\t10\n" for i in range(5)),
                encoding="utf-8",
                newline="\n",
            )
            subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
            subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=str(root), check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(root), check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=str(root), check=True)
            subprocess.run(["git", "add", "."], cwd=str(root), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(root), check=True)

            # Replace 5 entries with 5 DIFFERENT entries -> net delta is 0, symdiff is 10!
            base.write_text(
                "---\nname: base\n...\n" + "".join(f"新{i}\txin\t10\n" for i in range(5)),
                encoding="utf-8",
                newline="\n",
            )
            # Mutate ONLY cn_en_mspy.txt (leave cn_en.txt untouched!)
            (root / "en_dicts/cn_en_mspy.txt").write_text(
                "# cn_en\n" + "".join(f"AI词{i}\tAIci\n" for i in range(4)),
                encoding="utf-8",
                newline="\n",
            )
            res = dict_lint.check_diff_budget(
                root, max_active_delta=5, max_corrections_delta=50, max_cn_en_delta=2
            )
            self.assertEqual(res["active_cn_net_delta"], 0)
            self.assertEqual(res["active_cn_symdiff"], 10)
            self.assertEqual(res["cn_en_changed_entries"], 4)
            self.assertTrue(res["needs_review"])
            self.assertTrue(any("active_cn_symdiff=10" in r for r in res["reasons"]), res["reasons"])
            self.assertTrue(any("cn_en_max_file_symdiff=4" in r for r in res["reasons"]), res["reasons"])


class TestCleanerHardeningAndZeroPingPong(unittest.TestCase):
    def test_clean_ext_and_industry_product_zero_ping_pong(self) -> None:
        st_ext: Counter = Counter()
        out_ext = clean_dicts.clean_ext(
            ["---", "name: ext", "...", "大咯血\tda ka xue\t25", "大咯血\tda ka xie\t25"],
            st_ext,
        )
        self.assertEqual(st_ext["reweighted"], 0)
        self.assertIn("大咯血\tda ka xie\t25", out_ext)

        st_ind: Counter = Counter()
        wl_lines = ["---", "name: industry_product", "..."] + [
            f"{w}\tce shi\t10" for w in sorted(clean_dicts.INDUSTRY_PRODUCT_WHITELIST)
        ]
        out_ind = clean_dicts.clean_industry_product(wl_lines, st_ind)
        self.assertEqual(st_ind["deleted_boilerplate_or_spam"], 0)
        self.assertEqual(len(out_ind), len(wl_lines))

    def test_build_cn_en_replace_pass2_fixed_zero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "en_dicts").mkdir()
            (root / "rules").mkdir()
            rules_p = root / "rules/cn_en_source.tsv"
            rules_p.write_text(
                "replace\tAV女优\tAV\tnv you\t\ttrue\tfix mspy/sogou\n",
                encoding="utf-8",
                newline="\n",
            )
            for fname, _ in build_cn_en.CN_EN_FILES:
                (root / "en_dicts" / fname).write_text("AV女优\tAVold\n", encoding="utf-8", newline="\n")

            m1: dict = {"files": {}}
            build_cn_en.apply_cn_en_rules(root, root, rules_p, manifest=m1, valid_syls={"nv", "you"})
            for rel, st in m1["files"].items():
                self.assertGreater(st["fixed"], 0, f"Pass 1 should fix {rel}")

            m2: dict = {"files": {}}
            _, changed2 = build_cn_en.apply_cn_en_rules(root, root, rules_p, manifest=m2, valid_syls={"nv", "you"})
            self.assertEqual(changed2, [])
            for rel, st in m2["files"].items():
                self.assertEqual(st["fixed"], 0, f"Pass 2 ping-pong in {rel}: {st}")

    def test_find_entry_span_max_span_len_guardrail(self) -> None:
        body = ["开始\tkai shi\t0"] + [f"正词{i}\tzheng ci\t10" for i in range(50)] + ["结束\tjie shu\t0"]
        st: Counter = Counter()
        self.assertIsNone(
            clean_dicts.find_entry_span(body, ("开始", "kai shi"), ("结束", "jie shu"), max_span_len=20, stats=st)
        )
        self.assertEqual(st["span_guard_aborted"], 1)
        self.assertEqual(
            clean_dicts.find_entry_span(body, ("开始", "kai shi"), ("结束", "jie shu"), max_span_len=60, stats=st),
            (0, 51),
        )

    def test_opencc_english_chinese_nbsp_join(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _create_mini_repo(root)
            (root / "opencc/english_chinese.txt").write_text(
                "irc\tirc n.Internet Relay Chat\n",
                encoding="utf-8",
                newline="\n",
            )
            _, buffers = clean_dicts.run_pipeline(root, root, root / "rules", write=False)
            self.assertEqual(
                buffers["opencc/english_chinese.txt"],
                "irc\tirc n.Internet\u00a0Relay\u00a0Chat\n",
            )

    def test_precedence_and_weight_preserving_dedup_and_atomic_abort(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _create_mini_repo(root)
            # Precedence: literature has pre-simplified '於传有之' and rule targets normalized '于传有之'
            (root / "cn_dicts_cell/literature.dict.yaml").write_text(
                "---\nname: literature\n...\n於传有之\tyu chuan you zhi\t5\n测试\tce shi\t0\n",
                encoding="utf-8",
                newline="\n",
            )
            # Step-2 weight-preserving dedup: composite has higher weight 500 for same (测试, ce shi)
            (root / "cn_dicts_cell/composite.dict.yaml").write_text(
                "---\nname: composite\n...\n测试\tce shi\t500\n",
                encoding="utf-8",
                newline="\n",
            )
            (root / "rules/phonetics_fix.tsv").write_text(
                "cn_dicts_cell/literature.dict.yaml\t于传有之\tyu chuan you zhi\tyu zhuan you zhi\tfix\tsrc\n",
                encoding="utf-8",
                newline="\n",
            )
            manifest, buffers = clean_dicts.run_pipeline(root, root, root / "rules", write=True)
            lit_out = buffers["cn_dicts_cell/literature.dict.yaml"]
            comp_out = buffers["cn_dicts_cell/composite.dict.yaml"]
            self.assertIn("于传有之\tyu zhuan you zhi\t5", lit_out)
            self.assertIn("测试\tce shi\t500", lit_out)
            self.assertNotIn("测试\tce shi", comp_out)
            self.assertEqual(manifest["files"]["cn_dicts_cell/literature.dict.yaml"]["dedup_weight_promoted"], 1)

            # Atomic abort: inject an invalid syllable into base.dict.yaml; literature.dict.yaml must remain untouched on disk
            lit_before = (root / "cn_dicts_cell/literature.dict.yaml").read_bytes()
            (root / "cn_dicts/base.dict.yaml").write_text(
                "---\nname: base\n...\n测试\tce badzz\t10\n",
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaises(RuntimeError):
                clean_dicts.run_pipeline(root, root, root / "rules", write=True)
            self.assertEqual((root / "cn_dicts_cell/literature.dict.yaml").read_bytes(), lit_before)

    def test_clean_chess2_strips_obsolete_bao_cannon(self) -> None:
        lines = [
            "---",
            "name: chess2",
            "...",
            "前包进一\tqian bao jin yi\t0",
            "后包平五\thou bao ping wu\t1",
            "前炮进一\tqian pao jin yi\t0",
            "炮二平五\tpao er ping wu\t5",
        ]
        st: Counter = Counter()
        out = clean_dicts.clean_chess2(lines, st)
        joined = "\n".join(out)
        self.assertNotIn("前包进一", joined)
        self.assertNotIn("后包平五", joined)
        self.assertIn("前炮进一\tqian pao jin yi\t0", joined)
        self.assertIn("炮二平五\tpao er ping wu\t5", joined)
        self.assertEqual(st["deleted_trad_piece"], 2)

    def test_post_normalize_medication_can_allowlist_and_shi(self) -> None:
        lines = [
            "---",
            "name: medication",
            "...",
            "蚕参健脾颗粒\tcan can jian pi ke li\t0",
            "参苓白术丸\tcan ling bai zhu wan\t18",
            "医学参考值\tyi xue can kao zhi\t1",
            "仆参穴\tpu can xue\t0",
            "人迎趺阳三部不参\tren ying fu yang san bu bu can\t0",
            "参德力糖浆\tcan de li tang jiang\t0",
            "奥罗普什热\tao luo pu shen re\t0",
        ]
        st: Counter = Counter()
        out = clean_dicts.post_normalize_medication(lines, st)
        joined = "\n".join(out)
        self.assertIn("蚕参健脾颗粒\tcan shen jian pi ke li\t0", joined)
        self.assertIn("参苓白术丸\tshen ling bai zhu wan\t18", joined)
        self.assertIn("医学参考值\tyi xue can kao zhi\t1", joined)
        self.assertIn("仆参穴\tpu can xue\t0", joined)
        self.assertIn("人迎趺阳三部不参\tren ying fu yang san bu bu can\t0", joined)
        self.assertIn("参德力糖浆\tcan de li tang jiang\t0", joined)
        self.assertIn("奥罗普什热\tao luo pu shi re\t0", joined)
        self.assertEqual(st["fixed_py"], 3)

        sh_lines = ["---", "name: shulihua", "...", "福科什引理\tfu ke shen yin li\t0"]
        sh_st: Counter = Counter()
        sh_out = "\n".join(clean_dicts.post_normalize_shulihua(sh_lines, sh_st))
        self.assertIn("福科什引理\tfu ke shi yin li\t0", sh_out)
        self.assertEqual(sh_st["fixed_py"], 1)

    def test_clean_composite_normalizes_si_and_zhui(self) -> None:
        lines = [
            "---",
            "name: composite",
            "...",
            "追忆似水年华\tzhui yi shi shui nian hua\t174",
            "飞也似地\tfei ye shi di\t5",
            "似的大喊\tshi de da han\t3",
            "颈椎按摩仪\tjing chui an mo yi\t62",
            "椎心泣血\tchui xin qi xue\t2",
        ]
        st: Counter = Counter()
        out = "\n".join(clean_dicts.clean_composite(lines, st))
        self.assertIn("追忆似水年华\tzhui yi si shui nian hua\t174", out)
        self.assertIn("飞也似地\tfei ye shi di\t5", out)
        self.assertIn("似的大喊\tshi de da han\t3", out)
        self.assertIn("颈椎按摩仪\tjing zhui an mo yi\t62", out)
        self.assertIn("椎心泣血\tchui xin qi xue\t2", out)
        self.assertEqual(st["fixed_py"], 2)

    def test_cross_dict_shadow_fix_propagation_and_dual_protection(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _create_mini_repo(root)
            # literature fixes (测试, ce ci) -> (测试, ce shi) and (旧词 -> 新词);
            # lower-priority idiom still has raw upstream duplicates of both!
            (root / "cn_dicts/8105.dict.yaml").write_text(
                "---\nname: 8105\n...\n测\tce\t10\n试\tshi\t10\n词\tci\t10\n旧\tjiu\t10\n新\txin\t10\n双\tshuang\t10\n读\tdu\t10\n",
                encoding="utf-8",
                newline="\n",
            )
            (root / "cn_dicts_cell/literature.dict.yaml").write_text(
                "---\nname: literature\n...\n测试\tce ci\t5\n旧词\tjiu ci\t3\n",
                encoding="utf-8",
                newline="\n",
            )
            (root / "cn_dicts_cell/idiom.dict.yaml").write_text(
                "---\nname: idiom\n...\n测试\tce ci\t20\n旧词\tjiu ci\t12\n",
                encoding="utf-8",
                newline="\n",
            )
            (root / "rules/phonetics_fix.tsv").write_text(
                "cn_dicts_cell/literature.dict.yaml\t测试\tce ci\tce shi\tfix\tsrc\n",
                encoding="utf-8",
                newline="\n",
            )
            (root / "rules/word_fixes.tsv").write_text(
                "cn_dicts_cell/literature.dict.yaml\t旧词\tjiu ci\t新词\txin ci\twf\tsrc\n",
                encoding="utf-8",
                newline="\n",
            )
            manifest, buffers = clean_dicts.run_pipeline(root, root, root / "rules", write=False)
            lit_out = buffers["cn_dicts_cell/literature.dict.yaml"]
            idiom_out = buffers["cn_dicts_cell/idiom.dict.yaml"]
            # Literature inherits max weight via Step 2 dedup, idiom has 0 shadow conflicts/resurrections
            self.assertIn("测试\tce shi\t20", lit_out)
            self.assertIn("新词\txin ci\t12", lit_out)
            self.assertNotIn("测试\tce ci", idiom_out)
            self.assertNotIn("旧词\tjiu ci", idiom_out)
            self.assertEqual(manifest["files"]["cn_dicts_cell/idiom.dict.yaml"]["propagated_py_shadow"], 1)
            self.assertEqual(manifest["files"]["cn_dicts_cell/idiom.dict.yaml"]["propagated_wf_shadow"], 1)


if __name__ == "__main__":
    unittest.main()
