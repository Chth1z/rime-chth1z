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
    [string]$RimeDir  = (Join-Path $env:APPDATA "Rime"),
    [string]$SchemaId = "rime_frost_double_pinyin",
    [switch]$WaitNeural
)

$ErrorActionPreference = "Stop"

$weaselDir = (Get-ChildItem "C:\Program Files\Rime" -Directory -Filter "weasel-*" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
if (-not $weaselDir -or -not (Test-Path (Join-Path $weaselDir "rime.dll"))) {
    throw "Could not find Weasel rime.dll under C:\Program Files\Rime"
}

# Report power & CPU context so Battery vs AC comparisons stay apples-to-apples
$bat = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$pwr = if (-not $bat) { "Desktop/AC" } elseif ($bat.BatteryStatus -eq 2) { "AC ($($bat.EstimatedChargeRemaining)%)" } else { "Battery ($($bat.EstimatedChargeRemaining)%)" }
Write-Output ("=== Environment: {0} | Power: {1} | Schema: {2} ===" -f $cpu.Name.Trim(), $pwr, $SchemaId)

$benchDir = Join-Path $env:TEMP ("rime-frost-bench-" + (Get-Date -Format "yyyyMMddHHmmss"))
New-Item -ItemType Directory -Force -Path "$benchDir\logs" | Out-Null

try {
    foreach ($d in @("build", "lua", "opencc", "cn_dicts", "cn_dicts_cell", "en_dicts", "zhiyi")) {
        $src = Join-Path $RimeDir $d
        if (Test-Path $src) { cmd /c mklink /J "$benchDir\$d" "$src" | Out-Null }
    }
    Get-ChildItem $RimeDir -File | Where-Object { $_.Extension -in @(".yaml", ".lua", ".txt") } |
        ForEach-Object { Copy-Item $_.FullName $benchDir }
    Get-ChildItem $RimeDir -File -Filter "*.gram" | ForEach-Object {
        cmd /c mklink /H "$benchDir\$($_.Name)" "$($_.FullName)" | Out-Null
    }

    if (-not ("RimeFrostBench" -as [type])) {
        Add-Type -TypeDefinition @"
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;

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

    public static void Run(string weaselDir, string userDir, string logDir, string schemaId, int waitNeuralMs) {
        SetDllDirectory(weaselDir);
        var t = new RimeTraits();
        t.data_size = Marshal.SizeOf(typeof(RimeTraits)) - sizeof(int);
        t.shared_data_dir = Marshal.StringToHGlobalAnsi(weaselDir + @"\data");
        t.user_data_dir = Marshal.StringToHGlobalAnsi(userDir);
        t.distribution_name = Marshal.StringToHGlobalAnsi("FrostBench");
        t.distribution_code_name = Marshal.StringToHGlobalAnsi("FrostBench");
        t.distribution_version = Marshal.StringToHGlobalAnsi("1.0");
        t.app_name = Marshal.StringToHGlobalAnsi("rime.bench");
        t.min_log_level = 3;
        t.log_dir = Marshal.StringToHGlobalAnsi(logDir);

        RimeSetup(ref t);
        var swInit = Stopwatch.StartNew();
        RimeInitialize(ref t);
        var sid = RimeCreateSession();
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

        RimeDestroySession(sid);
        RimeFinalize();
    }
}
"@
    }

    $waitMs = if ($WaitNeural) { 2000 } else { 0 }
    [RimeFrostBench]::Run($weaselDir, $benchDir, "$benchDir\logs", $SchemaId, $waitMs)
}
finally {
    foreach ($d in @("build", "lua", "opencc", "cn_dicts", "cn_dicts_cell", "en_dicts", "zhiyi")) {
        if (Test-Path "$benchDir\$d") { cmd /c rmdir "$benchDir\$d" 2>$null | Out-Null }
    }
    Remove-Item $benchDir -Recurse -Force -ErrorAction SilentlyContinue
}
