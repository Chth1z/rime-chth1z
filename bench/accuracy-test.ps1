<#
.SYNOPSIS
    Automated functional regression test suite against Weasel's rime.dll.
.DESCRIPTION
    Runs isolated test cases from bench/accuracy-cases.json without touching live *.userdb.
    Verifies candidates, comments, pins, corrector hints, autocap, reduce_english, s2twp,
    date/lunar/calculator, select_character, and checks Rime logs for any Lua runtime errors.
.PARAMETER RimeDir
    Source Rime user directory containing build/, lua/, opencc/, *.gram.
    Defaults to %APPDATA%\Rime.
.PARAMETER CasesPath
    Path to JSON test cases file. Defaults to bench/accuracy-cases.json.
#>
param(
    [string]$RimeDir   = (Join-Path $env:APPDATA "Rime"),
    [string]$CasesPath = (Join-Path $PSScriptRoot "accuracy-cases.json"),
    [switch]$WaitNeural
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$weaselDir = (Get-ChildItem "C:\Program Files\Rime" -Directory -Filter "weasel-*" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
if (-not $weaselDir -or -not (Test-Path (Join-Path $weaselDir "rime.dll"))) {
    throw "Could not find Weasel rime.dll under C:\Program Files\Rime"
}

$casesJson = [System.IO.File]::ReadAllText($CasesPath, [System.Text.Encoding]::UTF8)
$suite = $casesJson | ConvertFrom-Json

$benchDir = Join-Path $env:TEMP ("rime-accuracy-" + (Get-Date -Format "yyyyMMddHHmmss"))
New-Item -ItemType Directory -Force -Path "$benchDir\logs" | Out-Null

try {
    foreach ($d in @("build", "lua", "opencc", "cn_dicts", "cn_dicts_cell", "en_dicts", "zhiyi")) {
        $src = Join-Path $RimeDir $d
        if (Test-Path $src) { cmd /c mklink /J "$benchDir\$d" "$src" | Out-Null }
    }
    Get-ChildItem $RimeDir -File | Where-Object {
        $_.Extension -in @(".yaml", ".lua", ".txt") -and $_.Name -notin @("user.yaml", "installation.yaml")
    } | ForEach-Object { Copy-Item $_.FullName $benchDir }
    Get-ChildItem $RimeDir -File -Filter "*.gram" | ForEach-Object {
        cmd /c mklink /H "$benchDir\$($_.Name)" "$($_.FullName)" | Out-Null
    }

    if (-not ("RimeAccuracyRunner" -as [type])) {
        Add-Type -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public class RimeCandInfo {
    public string Text;
    public string Comment;
}

public class RimeQueryResult {
    public string Preedit;
    public string Commit;
    public List<RimeCandInfo> Candidates = new List<RimeCandInfo>();
}

public static class RimeAccuracyRunner {
    [StructLayout(LayoutKind.Sequential)]
    public struct RimeTraits {
        public int data_size;
        public IntPtr shared_data_dir, user_data_dir, distribution_name, distribution_code_name, distribution_version, app_name, modules;
        public int min_log_level;
        public IntPtr log_dir, prebuilt_data_dir, staging_dir;
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct RimeComposition {
        public int length, cursor_pos, sel_start, sel_end;
        public IntPtr preedit;
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct RimeCandidate {
        public IntPtr text, comment, reserved;
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct RimeMenu {
        public int page_size, page_no, is_last_page, highlighted_candidate_index, num_candidates;
        public IntPtr candidates, select_keys;
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct RimeContext {
        public int data_size;
        public RimeComposition composition;
        public RimeMenu menu;
        public IntPtr commit_text_preview, select_labels;
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct RimeCommit {
        public int data_size;
        public IntPtr text;
    }

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
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern bool RimeGetCommit(UIntPtr sid, ref RimeCommit commit);
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern bool RimeFreeCommit(ref RimeCommit commit);
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern void RimeSetOption(UIntPtr sid, string opt, bool val);
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern bool RimeGetOption(UIntPtr sid, string opt);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] static extern bool SetDllDirectory(string lpPathName);

    private static UIntPtr _sid = UIntPtr.Zero;
    private static string _currentSchema = "";

    private static readonly Dictionary<string, int> SpecialKeys = new Dictionary<string, int> {
        { "BackSpace", 0xff08 }, { "Tab", 0xff09 }, { "Return", 0xff0d },
        { "Escape", 0xff1b }, { "Home", 0xff50 }, { "Left", 0xff51 },
        { "Up", 0xff52 }, { "Right", 0xff53 }, { "Down", 0xff54 },
        { "Page_Up", 0xff55 }, { "Page_Down", 0xff56 }, { "End", 0xff57 },
        { "Delete", 0xffff }, { "Space", 0x0020 }
    };

    static string PtrToUtf8(IntPtr p) {
        if (p == IntPtr.Zero) return "";
        int len = 0;
        while (Marshal.ReadByte(p, len) != 0) len++;
        if (len == 0) return "";
        byte[] buf = new byte[len];
        Marshal.Copy(p, buf, 0, len);
        return Encoding.UTF8.GetString(buf);
    }

    public static void Init(string weaselDir, string userDir, string logDir) {
        SetDllDirectory(weaselDir);
        var t = new RimeTraits {
            data_size = Marshal.SizeOf(typeof(RimeTraits)) - sizeof(int),
            shared_data_dir = Marshal.StringToHGlobalAnsi(weaselDir + @"\data"),
            user_data_dir = Marshal.StringToHGlobalAnsi(userDir),
            distribution_name = Marshal.StringToHGlobalAnsi("AccuracyTest"),
            distribution_code_name = Marshal.StringToHGlobalAnsi("AccuracyTest"),
            distribution_version = Marshal.StringToHGlobalAnsi("1.0"),
            app_name = Marshal.StringToHGlobalAnsi("rime.accuracy"),
            min_log_level = 1,
            log_dir = Marshal.StringToHGlobalAnsi(logDir)
        };
        RimeSetup(ref t);
        RimeInitialize(ref t);
        _sid = RimeCreateSession();
        _currentSchema = "";
    }

    public static void Shutdown() {
        if (_sid != UIntPtr.Zero) {
            RimeDestroySession(_sid);
            _sid = UIntPtr.Zero;
        }
        RimeFinalize();
    }

    public static void EnsureSchema(string schemaId) {
        if (_currentSchema != schemaId) {
            if (!RimeSelectSchema(_sid, schemaId)) {
                throw new Exception("RimeSelectSchema failed: " + schemaId);
            }
            _currentSchema = schemaId;
        }
    }

    public static bool GetOption(string name) { return RimeGetOption(_sid, name); }
    public static void SetOption(string name, bool val) { RimeSetOption(_sid, name, val); }

    public static RimeQueryResult RunKeys(string keys) {
        RimeClearComposition(_sid);
        var res = new RimeQueryResult { Preedit = "", Commit = "" };
        int i = 0;
        while (i < keys.Length) {
            int keycode;
            int mask = 0;
            if (keys[i] == '{') {
                int end = keys.IndexOf('}', i + 1);
                if (end > i) {
                    string tok = keys.Substring(i + 1, end - i - 1);
                    if (tok.StartsWith("Shift+")) { mask |= 1; tok = tok.Substring(6); }
                    if (tok.StartsWith("Control+")) { mask |= 4; tok = tok.Substring(8); }
                    if (SpecialKeys.ContainsKey(tok)) {
                        keycode = SpecialKeys[tok];
                    } else if (tok.Length == 1) {
                        keycode = (int)tok[0];
                    } else {
                        throw new Exception("Unknown key token: " + tok);
                    }
                    i = end + 1;
                } else {
                    keycode = (int)keys[i++];
                }
            } else {
                keycode = (int)keys[i++];
            }

            RimeProcessKey(_sid, keycode, mask);
            var cm = new RimeCommit { data_size = Marshal.SizeOf(typeof(RimeCommit)) - sizeof(int) };
            if (RimeGetCommit(_sid, ref cm)) {
                res.Commit += PtrToUtf8(cm.text);
                RimeFreeCommit(ref cm);
            }
        }

        var ctx = new RimeContext { data_size = Marshal.SizeOf(typeof(RimeContext)) - sizeof(int) };
        if (RimeGetContext(_sid, ref ctx)) {
            res.Preedit = PtrToUtf8(ctx.composition.preedit);
            int sz = Marshal.SizeOf(typeof(RimeCandidate));
            for (int k = 0; k < ctx.menu.num_candidates; k++) {
                IntPtr cp = new IntPtr(ctx.menu.candidates.ToInt64() + k * sz);
                var c = (RimeCandidate)Marshal.PtrToStructure(cp, typeof(RimeCandidate));
                res.Candidates.Add(new RimeCandInfo {
                    Text = PtrToUtf8(c.text),
                    Comment = PtrToUtf8(c.comment)
                });
            }
            RimeFreeContext(ref ctx);
        }
        return res;
    }
}
"@
    }

    [RimeAccuracyRunner]::Init($weaselDir, $benchDir, "$benchDir\logs")
    if ($WaitNeural) {
        [RimeAccuracyRunner]::EnsureSchema("rime_frost_double_pinyin")
        Start-Sleep -Milliseconds 4500
    }

    $passed = 0
    $failed = 0
    $failures = New-Object System.Collections.Generic.List[string]

    foreach ($tc in $suite.cases) {
        [RimeAccuracyRunner]::EnsureSchema($tc.schema)
        # Deterministic baseline for regression suite regardless of user.yaml toggle state
        [RimeAccuracyRunner]::SetOption("traditionalization", $true)

        $savedOpts = @{}
        if ($tc.PSObject.Properties.Name -contains "options" -and $tc.options) {
            foreach ($prop in $tc.options.PSObject.Properties) {
                $savedOpts[$prop.Name] = [RimeAccuracyRunner]::GetOption($prop.Name)
                [RimeAccuracyRunner]::SetOption($prop.Name, [bool]$prop.Value)
            }
        }

        $res = [RimeAccuracyRunner]::RunKeys($tc.keys)

        foreach ($k in $savedOpts.Keys) {
            [RimeAccuracyRunner]::SetOption($k, [bool]$savedOpts[$k])
        }

        $errs = New-Object System.Collections.Generic.List[string]
        $cands = $res.Candidates
        $firstText = if ($cands.Count -gt 0) { $cands[0].Text } else { "<none>" }
        $secondText = if ($cands.Count -gt 1) { $cands[1].Text } else { "<none>" }
        $firstComment = if ($cands.Count -gt 0) { $cands[0].Comment } else { "" }

        if ($tc.PSObject.Properties.Name -contains "first_text") {
            if ($firstText -ne $tc.first_text) {
                $errs.Add("first_text expected '$($tc.first_text)' got '$firstText'")
            }
        }
        if ($tc.PSObject.Properties.Name -contains "second_text") {
            if ($secondText -ne $tc.second_text) {
                $errs.Add("second_text expected '$($tc.second_text)' got '$secondText'")
            }
        }
        if ($tc.PSObject.Properties.Name -contains "no_first_text") {
            if ($firstText -eq $tc.no_first_text) {
                $errs.Add("first_text must not be '$($tc.no_first_text)'")
            }
        }
        if ($tc.PSObject.Properties.Name -contains "first_text_regex") {
            if ($firstText -notmatch $tc.first_text_regex) {
                $errs.Add("first_text '$firstText' did not match /$($tc.first_text_regex)/")
            }
        }
        if ($tc.PSObject.Properties.Name -contains "first_comment") {
            if ($firstComment -ne $tc.first_comment) {
                $errs.Add("first_comment expected '$($tc.first_comment)' got '$firstComment'")
            }
        }
        if ($tc.PSObject.Properties.Name -contains "first_comment_empty" -and $tc.first_comment_empty) {
            if ($firstComment -ne "") {
                $errs.Add("first_comment expected empty got '$firstComment'")
            }
        }
        if ($tc.PSObject.Properties.Name -contains "no_raw_pinyin_comment" -and $tc.no_raw_pinyin_comment) {
            foreach ($c in $cands) {
                if ($c.Comment -match '^\uFF3B.+\uFF3D$') {
                    $errs.Add("leaked raw pinyin comment '$($c.Comment)' on '$($c.Text)'")
                }
            }
        }
        if ($tc.PSObject.Properties.Name -contains "any_text") {
            $found = $false
            foreach ($c in $cands) { if ($c.Text -eq $tc.any_text) { $found = $true; break } }
            if (-not $found) { $errs.Add("any_text '$($tc.any_text)' not found") }
        }
        if ($tc.PSObject.Properties.Name -contains "any_text_with_comment") {
            $found = $false
            foreach ($c in $cands) {
                if ($c.Text -eq $tc.any_text_with_comment.text -and $c.Comment -eq $tc.any_text_with_comment.comment) {
                    $found = $true; break
                }
            }
            if (-not $found) {
                $errs.Add("candidate '$($tc.any_text_with_comment.text)[$($tc.any_text_with_comment.comment)]' not found")
            }
        }
        if ($tc.PSObject.Properties.Name -contains "text_before") {
            $a = $tc.text_before[0]; $b = $tc.text_before[1]
            $ia = -1; $ib = -1
            for ($idx = 0; $idx -lt $cands.Count; $idx++) {
                if ($ia -lt 0 -and $cands[$idx].Text -eq $a) { $ia = $idx }
                if ($ib -lt 0 -and $cands[$idx].Text -eq $b) { $ib = $idx }
            }
            if ($ia -lt 0 -or $ib -lt 0 -or $ia -ge $ib) {
                $errs.Add("expected '$a' (idx=$ia) before '$b' (idx=$ib)")
            }
        }
        if ($tc.PSObject.Properties.Name -contains "no_text_regex") {
            foreach ($c in $cands) {
                if ($c.Text -match $tc.no_text_regex) {
                    $errs.Add("forbidden text '$($c.Text)' matched /$($tc.no_text_regex)/")
                }
            }
        }
        if ($tc.PSObject.Properties.Name -contains "commit") {
            if ($res.Commit -ne $tc.commit) {
                $errs.Add("commit expected '$($tc.commit)' got '$($res.Commit)'")
            }
        }
        if ($tc.PSObject.Properties.Name -contains "preedit") {
            if ($res.Preedit -ne $tc.preedit) {
                $errs.Add("preedit expected '$($tc.preedit)' got '$($res.Preedit)'")
            }
        }

        if ($errs.Count -eq 0) {
            $passed++
        } else {
            $failed++
            $candDump = ($cands | ForEach-Object { if ($_.Comment) { "$($_.Text)[$($_.Comment)]" } else { $_.Text } }) -join " | "
            $msg = "[FAIL] $($tc.name) ($($tc.schema) '$($tc.keys)'): $($errs -join '; ') | got cands=[$candDump] commit='$($res.Commit)' pre='$($res.Preedit)'"
            $failures.Add($msg)
            Write-Output $msg
        }
    }

    [RimeAccuracyRunner]::Shutdown()

    # Check logs for Lua runtime errors
    $luaErrs = @()
    Get-ChildItem "$benchDir\logs" -File -ErrorAction SilentlyContinue | ForEach-Object {
        $hits = Select-String -Path $_.FullName -Pattern "error running|attempt to|stack traceback|syntax error" -ErrorAction SilentlyContinue
        if ($hits) { $luaErrs += $hits }
    }
    if ($luaErrs.Count -gt 0) {
        $failed++
        Write-Output "[FAIL] Lua runtime errors detected in logs:"
        $luaErrs | ForEach-Object { Write-Output "  $($_.Line)" }
    }

    Write-Output ("=== Accuracy Test Summary: {0} passed, {1} failed (total {2} cases) ===" -f $passed, $failed, $suite.cases.Count)
    if ($failed -gt 0) { exit 1 }
}
finally {
    foreach ($d in @("build", "lua", "opencc", "cn_dicts", "cn_dicts_cell", "en_dicts", "zhiyi")) {
        if (Test-Path "$benchDir\$d") { cmd /c rmdir "$benchDir\$d" 2>$null | Out-Null }
    }
    Remove-Item $benchDir -Recurse -Force -ErrorAction SilentlyContinue
}
