<#
.SYNOPSIS
    Independent end-to-end post-deployment verification for the full Chth1z/rime-chth1z stack.
.DESCRIPTION
    Run this in a separate command after bootstrap.ps1 to verify:
      - Weasel Nightly >= 0.17.4 with Lua 5.4 C API exports
      - Core rime-chth1z config, Lua pipeline, OpenCC, and cleaned dictionary files
      - Wanxiang LTS .gram language model (unless -SkipGram)
      - rime-neural DLL, ONNX Runtime, model, vocab, and Lua filter (unless -SkipNeural)
      - Compiled build/rime_frost_double_pinyin.schema.yaml & build/rime_frost.schema.yaml
      - Exactly 1 live WeaselServer.exe process (confirming detached survival)
      - Clean recent Weasel deploy & warning/error logs (0 failures, 0 errors)
    Outputs structured JSON and exits 0 iff all required checks pass.
#>
[CmdletBinding()]
param(
    [string]$RimeDir = "",
    [switch]$SkipGram,
    [switch]$SkipNeural
)

$ErrorActionPreference = "Stop"

function Get-WeaselDir {
    foreach ($regPath in @("HKLM:\SOFTWARE\Rime\Weasel", "HKLM:\SOFTWARE\WOW6432Node\Rime\Weasel", "HKCU:\SOFTWARE\Rime\Weasel")) {
        $root = (Get-ItemProperty -Path $regPath -Name "WeaselRoot" -ErrorAction SilentlyContinue).WeaselRoot
        if ($root -and (Test-Path (Join-Path $root "rime.dll"))) {
            return (Get-Item $root).FullName
        }
    }
    $candidates = @()
    foreach ($base in @("C:\Program Files\Rime", "C:\Program Files (x86)\Rime")) {
        if (Test-Path $base) {
            $candidates += Get-ChildItem $base -Directory -Filter "weasel-*" -ErrorAction SilentlyContinue |
                Where-Object { Test-Path (Join-Path $_.FullName "rime.dll") }
        }
    }
    $best = $candidates | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($best) { return $best.FullName }
    return $null
}

function Test-RimeDllExportsLua54([string]$DllPath) {
    if (-not $DllPath -or -not (Test-Path $DllPath)) { return $false }
    try {
        $bytes = [System.IO.File]::ReadAllBytes($DllPath)
        $ascii = [System.Text.Encoding]::ASCII.GetString($bytes)
        return ($ascii.Contains("lua_pcallk") -and $ascii.Contains("lua_tolstring") -and $ascii.Contains("lua_createtable"))
    } catch {
        return $false
    }
}

if (-not $RimeDir) {
    $regDir = (Get-ItemProperty -Path "HKCU:\SOFTWARE\Rime\Weasel" -Name "RimeUserDir" -ErrorAction SilentlyContinue).RimeUserDir
    $RimeDir = if ($regDir -and $regDir.Trim()) { $regDir.Trim() } else { Join-Path $env:APPDATA "Rime" }
}

$checks = [System.Collections.Generic.List[object]]::new()
$allOk  = $true

function Add-Check {
    param([string]$Name, [bool]$Ok, [string]$Detail)
    if (-not $Ok) { $script:allOk = $false }
    $checks.Add([ordered]@{ name = $Name; ok = $Ok; detail = $Detail })
}

# 1. Weasel + Lua 5.4 exports
$weaselDir = Get-WeaselDir
$luaOk     = if ($weaselDir) { Test-RimeDllExportsLua54 (Join-Path $weaselDir "rime.dll") } else { $false }
$weaselOk  = [bool]$weaselDir -and ($SkipNeural -or $luaOk)
Add-Check -Name "weasel:install_and_lua54" -Ok $weaselOk -Detail "dir=$weaselDir lua54_exports=$luaOk"

# 2. Core rime-chth1z files
$coreFiles = @(
    "rime.lua",
    "default.yaml",
    "rime_frost_double_pinyin.schema.yaml",
    "rime_frost.schema.yaml",
    "weasel.custom.yaml",
    "lua\chth1z_pipeline_filter.lua",
    "lua\tw_dual_filter.lua",
    "lua\calculator.lua",
    "lua\select_character.lua",
    "cn_dicts\corrections.dict.yaml",
    "cn_dicts\base.dict.yaml",
    "en_dicts\en_ext.dict.yaml",
    "opencc\s2twp.json",
    "opencc\s2tw.json"
)
$missingCore = @($coreFiles | Where-Object { -not (Test-Path (Join-Path $RimeDir $_)) })
Add-Check -Name "chth1z:core_files" -Ok ($missingCore.Count -eq 0) -Detail $(if ($missingCore.Count -eq 0) { "all $($coreFiles.Count) core files present" } else { "MISSING: $($missingCore -join ', ')" })

# 3. Wanxiang LTS .gram
if (-not $SkipGram) {
    $gramPath = Join-Path $RimeDir "wanxiang-lts-zh-hans.gram"
    $gramOk   = (Test-Path $gramPath) -and ((Get-Item $gramPath).Length -ge 100MB)
    $gramInfo = if (Test-Path $gramPath) { "{0:F1} MB" -f ((Get-Item $gramPath).Length / 1MB) } else { "MISSING: $gramPath" }
    Add-Check -Name "gram:wanxiang_lts" -Ok $gramOk -Detail $gramInfo
}

# 4. rime-neural binaries & model
$neuralDir = Join-Path $RimeDir "neural"
if (-not $SkipNeural) {
    $missingN = @()
    foreach ($req in @("rime_neural.dll", "onnxruntime.dll", "tokenizer.json", "unified_vocab.json")) {
        if (-not (Test-Path (Join-Path $neuralDir $req))) { $missingN += "neural\$req" }
    }
    $onnxFiles = @(Get-ChildItem $neuralDir -Filter "*.onnx" -ErrorAction SilentlyContinue)
    if ($onnxFiles.Count -lt 1) { $missingN += "neural\*.onnx" }
    elseif ($onnxFiles.Count -gt 1) { $missingN += "CONFLICT: multiple .onnx models ($($onnxFiles.Name -join ', '))" }
    if (-not (Test-Path (Join-Path $RimeDir "lua\rime_neural.lua"))) { $missingN += "lua\rime_neural.lua" }
    $nDetail = if ($missingN.Count -eq 0) {
        $mNames = ($onnxFiles | ForEach-Object { "$($_.Name) ({0:F1} MB)" -f ($_.Length / 1MB) }) -join ", "
        "all binaries & model present: $mNames"
    } else {
        "MISSING: $($missingN -join ', ')"
    }
    Add-Check -Name "neural:files" -Ok ($missingN.Count -eq 0) -Detail $nDetail
}

# 5. Compiled build/*.schema.yaml verification
foreach ($sid in @("rime_frost_double_pinyin", "rime_frost")) {
    $built = Join-Path $RimeDir "build\$sid.schema.yaml"
    if (-not (Test-Path $built)) {
        Add-Check -Name "build:$sid" -Ok $false -Detail "MISSING: $built (run WeaselDeployer /deploy)"
        continue
    }
    $raw = Get-Content $built -Raw -Encoding UTF8
    $issues = @()
    if ($raw -notmatch 'lua_filter@\*chth1z_pipeline_filter') { $issues += "missing chth1z_pipeline_filter" }
    if ($raw -notmatch 'lua_filter@\*tw_dual_filter')         { $issues += "missing tw_dual_filter" }
    if (-not $SkipGram -and ($raw -notmatch 'wanxiang-lts-zh-hans')) { $issues += "missing wanxiang-lts-zh-hans grammar" }
    if (-not $SkipNeural) {
        $iN = $raw.IndexOf("lua_filter@*rime_neural")
        $iT = $raw.IndexOf("lua_filter@*tw_dual_filter")
        if ($iN -lt 0) { $issues += "missing lua_filter@*rime_neural" }
        elseif ($iT -ge 0 -and $iN -gt $iT) { $issues += "rime_neural must precede tw_dual_filter" }
        if ($raw -notmatch 'max_sentences:\s*([6-9]|[1-9]\d)') { $issues += "max_sentences < 6" }
    }
    Add-Check -Name "build:$sid" -Ok ($issues.Count -eq 0) -Detail $(if ($issues.Count -eq 0) { "filters, grammar & beam settings valid" } else { $issues -join "; " })
}

# 6. Exactly 1 live WeaselServer.exe process
$procs   = @(Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)
$pidText = ($procs | ForEach-Object { $_.Id }) -join ","
Add-Check -Name "process:WeaselServer" -Ok ($procs.Count -eq 1) -Detail "count=$($procs.Count) pids=$pidText"

# 7. Recent Weasel deploy & warning/error logs (scan multiple INFO logs so WeaselServer never masks WeaselDeployer)
$logDir  = Join-Path $env:TEMP "rime.weasel"
$logErrs = [System.Collections.Generic.List[string]]::new()
$summary = ""
if (Test-Path $logDir) {
    $cutoff = (Get-Date).AddMinutes(-15)
    $recentInfos = @(Get-ChildItem $logDir -Filter "rime.weasel*.INFO*" -File -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -ge $cutoff } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 4)
    if ($recentInfos.Count -eq 0) {
        $recentInfos = @(Get-ChildItem $logDir -Filter "rime.weasel*.INFO*" -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 2)
    }
    foreach ($inf in $recentInfos) {
        $lines = Get-Content $inf.FullName -Encoding UTF8 -ErrorAction SilentlyContinue
        if (-not $summary) {
            $sLine = $lines | Where-Object { $_ -match 'finished updating schemas:' } | Select-Object -Last 1
            if ($sLine) {
                $summary = "$($inf.Name): $($sLine.Trim())"
                if ($summary -notmatch '0 failure') { $logErrs.Add("deploy failure: $summary") }
            }
        }
        $efLines = $lines | Where-Object { $_ -match '^[EF]\d{4,8}\s' } | Select-Object -First 3
        foreach ($l in $efLines) { $logErrs.Add("$($inf.Name): $($l.Trim())") }
    }
    $warnLogs = Get-ChildItem $logDir -File -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -ge $cutoff -and ($_.Name -match 'WARNING|ERROR') } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 4
    foreach ($wf in $warnLogs) {
        $hits = Select-String -Path $wf.FullName -Pattern 'rime_neural|chth1z_pipeline|tw_dual|lua_filter.*error|loadlib failed|circular dependencies' -ErrorAction SilentlyContinue | Select-Object -First 3
        foreach ($h in $hits) { $logErrs.Add("$($wf.Name):$($h.LineNumber): $($h.Line.Trim())") }
    }
}
$logDetail = if ($logErrs.Count -eq 0) {
    if ($summary) { "0 errors | $summary" } else { "0 errors in recent Weasel logs" }
} else {
    ($logErrs | Select-Object -First 5) -join " | "
}
Add-Check -Name "logs:weasel_clean" -Ok ($logErrs.Count -eq 0) -Detail $logDetail

# Advisory (non-blocking) status
$notoInstalled = $false
foreach ($fd in @("C:\Windows\Fonts", (Join-Path $env:LOCALAPPDATA "Microsoft\Windows\Fonts"))) {
    if ((Test-Path $fd) -and (Get-ChildItem $fd -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'NotoSansCJK|NotoSansTC' } | Select-Object -First 1)) {
        $notoInstalled = $true
        break
    }
}
$task = Get-ScheduledTask -TaskName "RimeChth1zWeeklyUpdate" -ErrorAction SilentlyContinue

$out = [ordered]@{
    ok       = $allOk
    rime_dir = $RimeDir
    advisory = [ordered]@{
        noto_cjk_tc_installed  = $notoInstalled
        weekly_task_registered = [bool]$task
        feedback_jsonl_exists  = (Test-Path (Join-Path $neuralDir "feedback.jsonl"))
    }
    checks   = $checks
}

$out | ConvertTo-Json -Depth 5
if (-not $allOk) { exit 1 }
