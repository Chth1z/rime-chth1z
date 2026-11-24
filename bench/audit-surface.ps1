<#
.SYNOPSIS
    Proactive full-surface live rime.dll audit across both Double Pinyin and Full Pinyin schemas.
.DESCRIPTION
    Runs an exhaustive, isolated runtime surface audit against Weasel's rime.dll without touching
    live *.userdb or neural/feedback.jsonl. Verifies:
      1. All 26 single-letter keys (a-z) and 100% of pin_cand_filter entries in DP & FP.
      2. 100% of cn_dicts/corrections.dict.yaml entries in DP & FP (reachability, exact comment
         attachment, and zero raw full-width pinyin bracket leaks).
      3. 100% of symbols_v.yaml keys in DP & FP (non-empty candidates).
      4. 100% of pure alphanum entries in rime_frost.dict.yaml in DP & FP.
      5. High-frequency EN-vs-CN anti-hijack checks (2-letter ZRM syllables, high-frequency FP
         abbreviations, and symbol-code anti-hijack guard keys).
      6. Calculator portable math + Lua boundary fuzzing + all-options-on smoke check + 0 log errors.
    Exits 0 iff all surface checks pass.
.PARAMETER RimeDir
    Source Rime user directory containing build/, lua/, opencc/, *.gram. Defaults to %APPDATA%\Rime.
#>
param(
    [string]$RimeDir = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if (-not $RimeDir) {
    $regDir = (Get-ItemProperty -Path "HKCU:\SOFTWARE\Rime\Weasel" -Name "RimeUserDir" -ErrorAction SilentlyContinue).RimeUserDir
    $RimeDir = if ($regDir -and $regDir.Trim()) { $regDir.Trim() } else { Join-Path $env:APPDATA "Rime" }
}

function Get-WeaselDir {
    $proc = Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($proc) {
        try {
            $procDir = Split-Path $proc.Path -Parent
            if ($procDir -and (Test-Path (Join-Path $procDir "rime.dll"))) { return $procDir }
        } catch {}
    }
    foreach ($regPath in @("HKLM:\SOFTWARE\Rime\Weasel", "HKLM:\SOFTWARE\WOW6432Node\Rime\Weasel", "HKCU:\SOFTWARE\Rime\Weasel")) {
        $root = (Get-ItemProperty -Path $regPath -Name "WeaselRoot" -ErrorAction SilentlyContinue).WeaselRoot
        if ($root -and (Test-Path (Join-Path $root "rime.dll"))) { return $root }
    }
    $cands = @()
    foreach ($base in @("C:\Program Files\Rime", "C:\Program Files (x86)\Rime")) {
        if (Test-Path $base) {
            $cands += Get-ChildItem $base -Directory -Filter "weasel-*" -ErrorAction SilentlyContinue |
                Where-Object { Test-Path (Join-Path $_.FullName "rime.dll") }
        }
    }
    $best = $cands | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($best) { return $best.FullName }
    return $null
}

function New-SafeHardlinkOrCopy([string]$Dst, [string]$Src) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $global:LASTEXITCODE = 0
        & cmd /c mklink /H "$Dst" "$Src" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Dst)) {
            Copy-Item -Path $Src -Destination $Dst -Force
        }
    } finally {
        $ErrorActionPreference = $prev
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$weaselDir = Get-WeaselDir
if (-not $weaselDir -or -not (Test-Path (Join-Path $weaselDir "rime.dll"))) {
    throw "Could not find Weasel rime.dll via registry or Program Files"
}

$benchDir = Join-Path $env:TEMP ("rime-surface-audit-" + (Get-Date -Format "yyyyMMddHHmmss") + "-" + [guid]::NewGuid().ToString("N").Substring(0, 6))
New-Item -ItemType Directory -Force -Path "$benchDir\logs" | Out-Null
$payloadPath = Join-Path $benchDir "surface_inputs.json"
$rimeInited = $false
$junctionDirs = @("build", "lua", "opencc", "cn_dicts", "cn_dicts_cell", "en_dicts")

try {
    # 1. Extract exact test inputs from repo SSOT via Python (zero duplication of ZRM tables)
    $pyExtract = @"
import json, pathlib, re, sys, yaml
root = pathlib.Path(r"$repoRoot")
sys.path.insert(0, str(root / "scripts"))
import build_cn_en

# Valid ZRM 2-letter syllables & high-freq EN collisions
valid_fp = set()
in_body = False
for l in (root / "cn_dicts/8105.dict.yaml").read_text(encoding="utf-8").splitlines():
    if l.strip() == "...": in_body = True; continue
    if not in_body or not l.strip() or l.startswith("#"): continue
    cols = l.split("\t")
    if len(cols) >= 2: valid_fp.add(cols[1].strip())

valid_zrm = {build_cn_en.syl_to_shuangpin(s, "double_pinyin") for s in valid_fp if s not in ("hm","hng","m","n","ng")}

en_codes = set()
for rel in ("en_dicts/en_ext.dict.yaml", "en_dicts/en.dict.yaml"):
    in_body = False
    for l in (root / rel).read_text(encoding="utf-8").splitlines():
        if l.strip() == "...": in_body = True; continue
        if not in_body or not l.strip() or l.startswith("#"): continue
        cols = l.split("\t")
        if len(cols) >= 2 and re.fullmatch(r"[a-zA-Z]+", cols[1]):
            en_codes.add(cols[1].lower())

zrm_2letter_en = sorted(c for c in en_codes if len(c) == 2 and c in valid_zrm)

fp_abbr_hi = set()
for rel in ("cn_dicts/base.dict.yaml", "cn_dicts/ext.dict.yaml"):
    in_body = False
    for l in (root / rel).read_text(encoding="utf-8").splitlines():
        if l.strip() == "...": in_body = True; continue
        if not in_body or not l.strip() or l.startswith("#"): continue
        cols = l.split("\t")
        if len(cols) >= 3 and cols[2].isdigit() and int(cols[2]) >= 5000:
            syls = cols[1].split()
            if len(syls) in (2, 3, 4):
                ab = "".join(s[0] for s in syls)
                if ab in en_codes:
                    fp_abbr_hi.add(ab)

# All corrections.dict.yaml entries
corrections = []
in_body = False
for idx, l in enumerate((root / "cn_dicts/corrections.dict.yaml").read_text(encoding="utf-8").splitlines(), 1):
    if l.strip() == "...": in_body = True; continue
    if not in_body or not l.strip() or l.startswith("#"): continue
    cols = l.split("\t")
    if len(cols) == 4:
        w, py, wt, cmt = cols
        corrections.append({
            "line": idx, "word": w, "py": py, "comment": cmt,
            "fp": "".join(py.split()),
            "dp": "".join(build_cn_en.syl_to_shuangpin(s, "double_pinyin") for s in py.split()),
        })

# All symbols_v.yaml keys
sym_doc = yaml.safe_load((root / "symbols_v.yaml").read_text(encoding="utf-8")) or {}
sym_keys = sorted(str(k) for k in (sym_doc.get("symbols") or {}).keys())

# All pin_cand_filter entries
dp_doc = yaml.safe_load((root / "rime_frost_double_pinyin.schema.yaml").read_text(encoding="utf-8")) or {}
fp_doc = yaml.safe_load((root / "rime_frost.schema.yaml").read_text(encoding="utf-8")) or {}

# Pure alphanum entries from rime_frost.dict.yaml (ASCII letters + digits only)
alphanum = []
in_body = False
for l in (root / "rime_frost.dict.yaml").read_text(encoding="utf-8").splitlines():
    if l.strip() == "...": in_body = True; continue
    if not in_body or not l.strip() or l.startswith("#"): continue
    s = l.strip()
    if "\t" not in s and re.fullmatch(r"[A-Z0-9]+", s) and re.search(r"[0-9]", s):
        alphanum.append(s)

payload = {
    "dp_pins": dp_doc.get("pin_cand_filter") or [],
    "fp_pins": fp_doc.get("pin_cand_filter") or [],
    "corrections": corrections,
    "sym_keys": sym_keys,
    "alphanum": alphanum,
    "zrm_2letter_en": zrm_2letter_en,
    "fp_abbr_hi": sorted(fp_abbr_hi),
}
pathlib.Path(r"$payloadPath").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
"@
    $pyExtract | python -
    if ($LASTEXITCODE -ne 0) { throw "Failed to extract surface audit inputs via Python." }

    # 2. Prepare isolated Rime sandbox (never touches live *.userdb or feedback.jsonl)
    foreach ($d in $junctionDirs) {
        $src = Join-Path $RimeDir $d
        if (Test-Path $src) { cmd /c mklink /J "$benchDir\$d" "$src" | Out-Null }
    }
    $neuralSrc = Join-Path $RimeDir "neural"
    if (Test-Path $neuralSrc) {
        $neuralDst = Join-Path $benchDir "neural"
        New-Item -ItemType Directory -Force -Path $neuralDst | Out-Null
        Get-ChildItem $neuralSrc -File | Where-Object { $_.Name -notmatch '^feedback\.jsonl(\.\d+)?$' } | ForEach-Object {
            New-SafeHardlinkOrCopy (Join-Path $neuralDst $_.Name) $_.FullName
        }
    }
    Get-ChildItem $RimeDir -File | Where-Object {
        $_.Extension -in @(".yaml", ".lua", ".txt") -and $_.Name -notin @("user.yaml", "installation.yaml")
    } | ForEach-Object { Copy-Item $_.FullName $benchDir }
    Get-ChildItem $RimeDir -File -Filter "*.gram" | ForEach-Object {
        New-SafeHardlinkOrCopy (Join-Path $benchDir $_.Name) $_.FullName
    }

    if (-not ("RimeSurfaceAuditor" -as [type])) {
        Add-Type -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public class SurfaceCand {
    public string Text;
    public string Comment;
}

public static class RimeSurfaceAuditor {
    [StructLayout(LayoutKind.Sequential)]
    public struct RimeTraits {
        public int data_size;
        public IntPtr shared_data_dir, user_data_dir, distribution_name, distribution_code_name, distribution_version, app_name, modules;
        public int min_log_level;
        public IntPtr log_dir, prebuilt_data_dir, staging_dir;
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct RimeComposition { public int length, cursor_pos, sel_start, sel_end; public IntPtr preedit; }
    [StructLayout(LayoutKind.Sequential)]
    public struct RimeCandidate { public IntPtr text, comment, reserved; }
    [StructLayout(LayoutKind.Sequential)]
    public struct RimeMenu { public int page_size, page_no, is_last_page, highlighted_candidate_index, num_candidates; public IntPtr candidates, select_keys; }
    [StructLayout(LayoutKind.Sequential)]
    public struct RimeContext { public int data_size; public RimeComposition composition; public RimeMenu menu; public IntPtr commit_text_preview, select_labels; }

    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern void RimeSetup(ref RimeTraits t);
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern void RimeInitialize(ref RimeTraits t);
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern void RimeFinalize();
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern UIntPtr RimeCreateSession();
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern bool RimeDestroySession(UIntPtr sid);
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern bool RimeSelectSchema(UIntPtr sid, string schema_id);
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern bool RimeProcessKey(UIntPtr sid, int keycode, int mask);
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern void RimeClearComposition(UIntPtr sid);
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern bool RimeGetContext(UIntPtr sid, ref RimeContext ctx);
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern bool RimeFreeContext(ref RimeContext ctx);
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern void RimeSetOption(UIntPtr sid, string opt, bool val);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] static extern bool SetDllDirectory(string lpPathName);

    static IntPtr Utf8(string s) { var b = Encoding.UTF8.GetBytes(s + "\0"); var p = Marshal.AllocHGlobal(b.Length); Marshal.Copy(b, 0, p, b.Length); return p; }
    static string FromUtf8(IntPtr p) { if (p == IntPtr.Zero) return ""; int len = 0; while (Marshal.ReadByte(p, len) != 0) len++; var b = new byte[len]; Marshal.Copy(p, b, 0, len); return Encoding.UTF8.GetString(b); }

    static UIntPtr _sid = UIntPtr.Zero;
    static string _curSchema = "";

    public static void Init(string dllDir, string sharedDir, string userDir, string logDir) {
        SetDllDirectory(dllDir);
        var t = new RimeTraits {
            data_size = Marshal.SizeOf(typeof(RimeTraits)) - 4,
            shared_data_dir = Utf8(sharedDir), user_data_dir = Utf8(userDir), log_dir = Utf8(logDir),
            distribution_name = Utf8("Weasel"), distribution_code_name = Utf8("Weasel"), distribution_version = Utf8("0.17"),
            app_name = Utf8("rime.surface"), min_log_level = 1
        };
        RimeSetup(ref t); RimeInitialize(ref t); _sid = RimeCreateSession();
    }
    public static void Close() {
        if (_sid != UIntPtr.Zero) { RimeDestroySession(_sid); _sid = UIntPtr.Zero; }
        RimeFinalize();
    }
    public static void SetSchema(string schema, bool trad, bool emoji, bool ce) {
        if (_curSchema != schema) { RimeSelectSchema(_sid, schema); _curSchema = schema; }
        RimeSetOption(_sid, "traditionalization", trad);
        RimeSetOption(_sid, "emoji", emoji);
        RimeSetOption(_sid, "chinese_english", ce);
        RimeSetOption(_sid, "neural_rerank", false);
    }
    public static List<SurfaceCand> Query(string input, int maxCands = 5) {
        RimeClearComposition(_sid);
        foreach (char ch in input) RimeProcessKey(_sid, (int)ch, 0);
        var list = new List<SurfaceCand>();
        int collected = 0;
        for (int page = 0; page < 4 && collected < maxCands; page++) {
            var ctx = new RimeContext { data_size = Marshal.SizeOf(typeof(RimeContext)) - 4 };
            if (!RimeGetContext(_sid, ref ctx)) break;
            int sz = Marshal.SizeOf(typeof(RimeCandidate));
            for (int i = 0; i < ctx.menu.num_candidates && collected < maxCands; i++) {
                var c = (RimeCandidate)Marshal.PtrToStructure(IntPtr.Add(ctx.menu.candidates, i * sz), typeof(RimeCandidate));
                list.Add(new SurfaceCand { Text = FromUtf8(c.text), Comment = FromUtf8(c.comment) });
                collected++;
            }
            bool isLast = ctx.menu.is_last_page != 0;
            RimeFreeContext(ref ctx);
            if (isLast || collected >= maxCands) break;
            RimeProcessKey(_sid, (int)'=', 0);
        }
        RimeClearComposition(_sid);
        return list;
    }
}
"@
    }

    $data = Get-Content $payloadPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $failures = [System.Collections.Generic.List[string]]::new()
    function Is-PureAscii([string]$s) { return $s -match '^[A-Za-z0-9\s\.\-\+\#/&''_@]+$' }

    [RimeSurfaceAuditor]::Init($weaselDir, (Join-Path $weaselDir "data"), $benchDir, "$benchDir\logs")
    $rimeInited = $true

    # Check 1: Single letters & pin_cand_filter (DP & FP)
    foreach ($pair in @(
        @("rime_frost_double_pinyin", $data.dp_pins, @()),
        @("rime_frost", $data.fp_pins, @("i", "u", "v"))
    )) {
        $sc = $pair[0]; $pins = $pair[1]; $allowAscii = $pair[2]
        [RimeSurfaceAuditor]::SetSchema($sc, $false, $false, $false)
        foreach ($b in 97..122) {
            $k = [string][char]$b
            if ($allowAscii -contains $k) { continue }
            $c = [RimeSurfaceAuditor]::Query($k, 3)
            if ($c.Count -eq 0 -or (Is-PureAscii $c[0].Text)) {
                $failures.Add("[$sc] single-letter '$k' hijacked/empty: $(($c | ForEach-Object {$_.Text}) -join '|')")
            }
        }
        foreach ($p in $pins) {
            $parts = ([string]$p).Split("`t")
            $k = $parts[0]; $exp = $parts[1]
            $c = [RimeSurfaceAuditor]::Query($k, 3)
            if ($c.Count -eq 0 -or $c[0].Text -ne $exp) {
                $failures.Add("[$sc] pin '$k' expected '$exp', got '$(if($c.Count -gt 0){$c[0].Text}else{''})'")
            }
        }
    }
    Write-Host ("[1/6] Single letters & pin_cand_filter: DP={0} FP={1} checked" -f $data.dp_pins.Count, $data.fp_pins.Count)

    # Check 2: 100% of corrections.dict.yaml (DP & FP)
    $corrTotal = $data.corrections.Count
    foreach ($pair in @(@("rime_frost_double_pinyin", "dp"), @("rime_frost", "fp"))) {
        $sc = $pair[0]; $field = $pair[1]
        [RimeSurfaceAuditor]::SetSchema($sc, $false, $false, $false)
        foreach ($cr in $data.corrections) {
            $code = [string]$cr.$field
            $cands = [RimeSurfaceAuditor]::Query($code, 15)
            $found = $null
            foreach ($cand in $cands) {
                if ($cand.Comment -match "［.*］") {
                    $failures.Add("[$sc] raw pinyin leak on '$($cr.word)' [$code]: '$($cand.Comment)'")
                }
                if ($cand.Text -eq $cr.word) { $found = $cand; break }
            }
            if ($null -eq $found) {
                $failures.Add("[$sc] correction missing in Top-15: L$($cr.line) '$($cr.word)' [$code]")
            } elseif ($found.Comment -ne $cr.comment) {
                $failures.Add("[$sc] correction comment mismatch: L$($cr.line) '$($cr.word)' [$code] got='$($found.Comment)' exp='$($cr.comment)'")
            }
        }
    }
    Write-Host ("[2/6] Corrections surface (DP & FP): {0} x 2 = {1} queries checked" -f $corrTotal, ($corrTotal * 2))

    # Check 3: 100% of symbols_v.yaml keys (DP & FP)
    foreach ($sc in @("rime_frost_double_pinyin", "rime_frost")) {
        [RimeSurfaceAuditor]::SetSchema($sc, $false, $false, $false)
        foreach ($sk in $data.sym_keys) {
            $c = [RimeSurfaceAuditor]::Query($sk, 2)
            if ($c.Count -eq 0) { $failures.Add("[$sc] symbol key '$sk' returned 0 candidates") }
        }
    }
    Write-Host ("[3/6] symbols_v.yaml reachability (DP & FP): {0} x 2 = {1} queries checked" -f $data.sym_keys.Count, ($data.sym_keys.Count * 2))

    # Check 4: Pure alphanum entries from rime_frost.dict.yaml (DP & FP)
    $digitFP = @{'0'='ling';'1'='yi';'2'='er';'3'='san';'4'='si';'5'='wu';'6'='liu';'7'='qi';'8'='ba';'9'='jiu'}
    $digitDP = @{'0'='ly';'1'='yi';'2'='er';'3'='sj';'4'='si';'5'='wu';'6'='lq';'7'='qi';'8'='ba';'9'='jq'}
    foreach ($sc in @("rime_frost_double_pinyin", "rime_frost")) {
        [RimeSurfaceAuditor]::SetSchema($sc, $false, $false, $false)
        $dmap = if ($sc -eq "rime_frost") { $digitFP } else { $digitDP }
        foreach ($w in $data.alphanum) {
            $code = ""
            foreach ($ch in $w.ToCharArray()) {
                $s = [string]$ch
                $code += if ($dmap.ContainsKey($s)) { $dmap[$s] } else { $s }
            }
            $c = [RimeSurfaceAuditor]::Query($code, 5)
            $texts = @($c | ForEach-Object { $_.Text })
            if ($texts -notcontains $w) {
                $failures.Add("[$sc] alphanum '$w' [$code] missing in Top-5: $($texts -join '|')")
            }
        }
    }
    Write-Host ("[4/6] Alphanum reachability (DP & FP): {0} x 2 checked" -f $data.alphanum.Count)

    # Check 5: High-frequency EN-vs-CN anti-hijack scan
    [RimeSurfaceAuditor]::SetSchema("rime_frost_double_pinyin", $false, $false, $false)
    foreach ($k in $data.zrm_2letter_en) {
        $c = [RimeSurfaceAuditor]::Query($k, 3)
        if ($c.Count -gt 0 -and (Is-PureAscii $c[0].Text)) {
            $failures.Add("[DP] 2-letter ZRM syllable '$k' hijacked by EN '$($c[0].Text)'")
        }
    }
    [RimeSurfaceAuditor]::SetSchema("rime_frost", $false, $false, $false)
    foreach ($k in $data.fp_abbr_hi) {
        $c = [RimeSurfaceAuditor]::Query($k, 3)
        if ($c.Count -gt 0 -and (Is-PureAscii $c[0].Text)) {
            $failures.Add("[FP] high-freq initial-abbrev '$k' hijacked by EN '$($c[0].Text)'")
        }
    }
    Write-Host ("[5/6] EN-vs-CN anti-hijack: DP 2-letter={0}, FP high-freq abbrev={1} checked" -f $data.zrm_2letter_en.Count, $data.fp_abbr_hi.Count)

    # Check 6: Calculator portability, Lua boundary fuzzing, and all-options-on smoke
    $calcExpect = @(
        @("/vslog10(100)", "^2(\.0)?$"),
        @("/vsatan2(1,1)", "^0\.785398"),
        @("/vssinh(1)", "^1\.175201"),
        @("/vscosh(1)", "^1\.543080"),
        @("/vstanh(1)", "^0\.761594"),
        @("/vstanh(100)", "^1(\.0)?$"),
        @("/vsldexp(2,3)", "^16(\.0)?$")
    )
    $fuzzBad = @("/vs1/0", "/vs0/0", "/vs1%0", "/vs2^1024", "/vs1000!", "/vs-1!", "/vssin", "/vsavg()", "/vsavg(fact(200),10)", "/vs(((", "/vsloge(0)", "/vslog10(-1)", "/vs(function()while(1)do;end;end)()")
    foreach ($sc in @("rime_frost_double_pinyin", "rime_frost")) {
        [RimeSurfaceAuditor]::SetSchema($sc, $true, $true, $true)
        foreach ($pair in $calcExpect) {
            $c = [RimeSurfaceAuditor]::Query($pair[0], 2)
            if ($c.Count -eq 0 -or $c[0].Text -notmatch $pair[1]) {
                $failures.Add("[$sc] calc '$($pair[0])' expected /$($pair[1])/, got '$(if($c.Count -gt 0){$c[0].Text}else{''})'")
            }
        }
        foreach ($fb in $fuzzBad) {
            $c = [RimeSurfaceAuditor]::Query($fb, 2)
            $joined = ($c | ForEach-Object { $_.Text }) -join "|"
            if ($joined -match "function:|userdata:|table:|inf|nan|attempt") {
                $failures.Add("[$sc] calc fuzz '$fb' leaked raw output: $joined")
            }
        }
        foreach ($selFuzz in @("http://[::1]:8080[", "a%b(c)[", "foo-bar.baz[", "ybhw", "miyt", "PDFwfjm")) {
            [void][RimeSurfaceAuditor]::Query($selFuzz, 3)
        }
    }

    [RimeSurfaceAuditor]::Close()
    $rimeInited = $false

    # Check Rime logs for any W/E/F errors (ignoring expected isolated-sandbox missing user.yaml)
    Get-ChildItem "$benchDir\logs" -File -ErrorAction SilentlyContinue | ForEach-Object {
        foreach ($line in Get-Content $_.FullName -ErrorAction SilentlyContinue) {
            if ($line -match "^[WEF]\d{8}\s" -and $line -notmatch "nonexistent config file '.*user\.yaml'") {
                $failures.Add("log($($_.Name)): $line")
            }
        }
    }
    Write-Host "[6/6] Calculator, Lua fuzzing, all-options-on & log cleanliness checked"

    Write-Host ""
    if ($failures.Count -eq 0) {
        Write-Host "=== Surface Audit Summary: PASS (0 failures across DP & FP) ===" -ForegroundColor Green
        exit 0
    } else {
        Write-Host "=== Surface Audit Summary: FAIL ($($failures.Count) failures) ===" -ForegroundColor Red
        $failures | Select-Object -First 30 | ForEach-Object { Write-Host "  [FAIL] $_" -ForegroundColor Red }
        exit 1
    }
}
finally {
    if ($rimeInited) {
        try { [RimeSurfaceAuditor]::Close() } catch {}
        $rimeInited = $false
    }
    foreach ($d in $junctionDirs) {
        $jp = Join-Path $benchDir $d
        if (Test-Path $jp) {
            try {
                if ((Get-Item $jp -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                    [System.IO.Directory]::Delete($jp, $false)
                }
            } catch {}
        }
    }
    Remove-Item -Recurse -Force $benchDir -ErrorAction SilentlyContinue
}
