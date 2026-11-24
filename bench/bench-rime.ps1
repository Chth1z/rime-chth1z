<#
.SYNOPSIS
    Reproducible millisecond keystroke latency benchmark for librime (rime.dll).
.DESCRIPTION
    Runs an isolated, read-only session against Weasel's rime.dll without touching
    live *.userdb files. Measures init time, all 26 single-letter first-keystroke
    latencies (a-z), and short/medium/20-char sentence keystroke latencies.
.PARAMETER RimeDir
    Source Rime user directory containing build/, lua/, opencc/, *.gram.
    Defaults to %APPDATA%\Rime.
.PARAMETER SchemaId
    Rime schema_id to benchmark. Defaults to rime_frost_double_pinyin.
#>
param(
    [string]$RimeDir  = "",
    [string]$SchemaId = "rime_frost_double_pinyin",
    [switch]$WaitNeural
)

$ErrorActionPreference = "Stop"

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

$weaselDir = Get-WeaselDir
if (-not $weaselDir -or -not (Test-Path (Join-Path $weaselDir "rime.dll"))) {
    throw "Could not find Weasel rime.dll via registry or Program Files"
}

# Report power & CPU context so Battery vs AC comparisons stay apples-to-apples
$bat = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$pwr = if (-not $bat) { "Desktop/AC" } elseif ($bat.BatteryStatus -eq 2) { "AC ($($bat.EstimatedChargeRemaining)%)" } else { "Battery ($($bat.EstimatedChargeRemaining)%)" }
Write-Output ("=== Environment: {0} | Power: {1} | Schema: {2} ===" -f $cpu.Name.Trim(), $pwr, $SchemaId)

$benchDir = Join-Path $env:TEMP ("rime-frost-bench-" + (Get-Date -Format "yyyyMMddHHmmss") + "-" + [guid]::NewGuid().ToString("N").Substring(0, 6))
New-Item -ItemType Directory -Force -Path "$benchDir\logs" | Out-Null
$junctionDirs = @("build", "lua", "opencc", "cn_dicts", "cn_dicts_cell", "en_dicts")

try {
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

    if (-not ("RimeFrostBench" -as [type])) {
        Add-Type -TypeDefinition @"
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

public static class RimeFrostBench {
    [StructLayout(LayoutKind.Sequential)]
    public struct RimeTraits {
        public int data_size;
        public IntPtr shared_data_dir, user_data_dir, distribution_name, distribution_code_name, distribution_version, app_name, modules;
        public int min_log_level;
        public IntPtr log_dir, prebuilt_data_dir, staging_dir;
    }
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern void RimeSetup(ref RimeTraits t);
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern void RimeInitialize(ref RimeTraits t);
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern void RimeFinalize();
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern UIntPtr RimeCreateSession();
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern bool RimeDestroySession(UIntPtr sid);
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern bool RimeSelectSchema(UIntPtr sid, string schema_id);
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern bool RimeProcessKey(UIntPtr sid, int keycode, int mask);
    [DllImport("rime.dll", CallingConvention=CallingConvention.Cdecl)] static extern void RimeClearComposition(UIntPtr sid);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] static extern bool SetDllDirectory(string lpPathName);

    static IntPtr Utf8(string s) {
        var b = Encoding.UTF8.GetBytes(s + "\0");
        var p = Marshal.AllocHGlobal(b.Length);
        Marshal.Copy(b, 0, p, b.Length);
        return p;
    }

    public static void Run(string weaselDir, string userDir, string logDir, string schemaId, int waitNeuralMs) {
        SetDllDirectory(weaselDir);
        var t = new RimeTraits();
        t.data_size = Marshal.SizeOf(typeof(RimeTraits)) - sizeof(int);
        t.shared_data_dir = Utf8(weaselDir + @"\data");
        t.user_data_dir = Utf8(userDir);
        t.distribution_name = Utf8("FrostBench");
        t.distribution_code_name = Utf8("FrostBench");
        t.distribution_version = Utf8("1.0");
        t.app_name = Utf8("rime.bench");
        t.min_log_level = 3;
        t.log_dir = Utf8(logDir);

        RimeSetup(ref t);
        var swInit = Stopwatch.StartNew();
        RimeInitialize(ref t);
        UIntPtr sid = UIntPtr.Zero;
        try {
            sid = RimeCreateSession();
            RimeSelectSchema(sid, schemaId);
            swInit.Stop();
            Console.WriteLine("Init + SelectSchema : {0:F1} ms", swInit.Elapsed.TotalMilliseconds);
            if (waitNeuralMs > 0) {
                System.Threading.Thread.Sleep(waitNeuralMs);
            }

            // Warmup
            foreach (char ch in "nihk") RimeProcessKey(sid, (int)ch, 0);
            RimeClearComposition(sid);

            // 1. All 26 single-letter first-keystroke benchmark
            double azSum = 0, azMax = 0; char azMaxCh = ' ';
            string slowKeys = "";
            for (char c = 'a'; c <= 'z'; c++) {
                RimeClearComposition(sid);
                var sw = Stopwatch.StartNew();
                RimeProcessKey(sid, (int)c, 0);
                sw.Stop();
                double ms = sw.Elapsed.TotalMilliseconds;
                azSum += ms;
                if (ms > azMax) { azMax = ms; azMaxCh = c; }
                if (ms > 15.0) slowKeys += string.Format("{0}:{1:F1}ms ", c, ms);
            }
            Console.WriteLine("All 26 1st-keys a-z : avg={0:F1} ms | max={1:F1} ms ('{2}') | slow(>15ms)={3}",
                azSum / 26.0, azMax, azMaxCh, string.IsNullOrEmpty(slowKeys) ? "none" : slowKeys.Trim());

            // 2. Sentence benchmark (valid Natural Double Pinyin & Full Pinyin sentences)
            string[] inputs = schemaId.Contains("double_pinyin")
                ? new string[] {
                    "nihk",                          // ni hao (4 keys)
                    "womfjntmzfmeyh",                // wo men jin tian zen me yang (14 keys)
                    "xmzlysxwllhlybyixxyjii",        // xian zai yong xia lai hai you yi xie yan chi (22 keys)
                    "jntmtmqivfdehfhkwoxdqugsyrwj"   // jin tian tian qi zhen de hen hao wo xiang qu gong yuan wan (28 keys)
                }
                : new string[] {
                    "nihao",
                    "womenjintianzenmeyang",
                    "xianzaiyongxialaihaiyouyixieyanchi"
                };

            double fSum = 0, rSum = 0, sMax = 0; int rCnt = 0;
            foreach (var inp in inputs) {
                RimeClearComposition(sid);
                double tot = 0, mx = 0;
                for (int i = 0; i < inp.Length; i++) {
                    var sw = Stopwatch.StartNew();
                    RimeProcessKey(sid, (int)inp[i], 0);
                    sw.Stop();
                    double ms = sw.Elapsed.TotalMilliseconds;
                    tot += ms;
                    if (ms > mx) mx = ms;
                    if (ms > sMax) sMax = ms;
                    if (i == 0) fSum += ms; else { rSum += ms; rCnt++; }
                }
                Console.WriteLine("  '{0,-22}' ({1,2} keys): total={2,5:F1}ms  avg={3,4:F1}ms  max={4,5:F1}ms",
                    inp.Length > 22 ? inp.Substring(0, 22) : inp, inp.Length, tot, tot / inp.Length, mx);
            }
            Console.WriteLine("Sentence summary    : 1st-key avg={0:F1} ms | rest avg={1:F1} ms | peak={2:F1} ms",
                fSum / inputs.Length, rSum / Math.Max(1, rCnt), sMax);
        } finally {
            if (sid != UIntPtr.Zero) RimeDestroySession(sid);
            RimeFinalize();
        }
    }
}
"@
    }

    # Background ORT init takes ~0.8s on AC and ~2.7s on battery
    $waitMs = if ($WaitNeural) { 4500 } else { 0 }
    [RimeFrostBench]::Run($weaselDir, $benchDir, "$benchDir\logs", $SchemaId, $waitMs)
}
finally {
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
    Remove-Item $benchDir -Recurse -Force -ErrorAction SilentlyContinue
}
