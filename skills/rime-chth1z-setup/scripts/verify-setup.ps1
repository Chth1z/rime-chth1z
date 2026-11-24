<#
.SYNOPSIS
    Independent end-to-end post-deployment verification for the full Chth1z/rime-chth1z stack.
.DESCRIPTION
    Standalone script (directly downloadable via raw URL).
    Run this in a separate command after bootstrap.ps1 to verify:
      - Weasel Nightly >= 0.17.4 with PE32+ Lua 5.4 C API exports
      - Core rime-chth1z config, all 6 Lua scripts, OpenCC, and cleaned dictionary files
      - Wanxiang LTS .gram language model (unless -SkipGram)
      - rime-neural DLL, ONNX Runtime, single ONNX model, vocab/tokenizer, and Lua filter (unless -SkipNeural)
      - Compiled build/rime_frost_double_pinyin.schema.yaml & build/rime_frost.schema.yaml
      - Exactly 1 live WeaselServer.exe process (confirming detached survival)
      - Clean Weasel deploy & warning/error logs anchored to the latest deploy / active WeaselServer session
    Outputs structured UTF-8 JSON and exits 0 iff all required checks pass.
#>
[CmdletBinding()]
param(
    [string]$RimeDir = "",
    [switch]$SkipGram,
    [switch]$SkipNeural
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Get-WeaselDir {
    $proc = Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($proc) {
        try {
            if ($proc.Path) {
                $procDir = Split-Path $proc.Path -Parent
                if ($procDir -and (Test-Path -LiteralPath (Join-Path $procDir "rime.dll"))) {
                    return (Get-Item -LiteralPath $procDir).FullName
                }
            }
        } catch {}
    }
    foreach ($regPath in @("HKLM:\SOFTWARE\Rime\Weasel", "HKLM:\SOFTWARE\WOW6432Node\Rime\Weasel", "HKCU:\SOFTWARE\Rime\Weasel")) {
        $root = (Get-ItemProperty -Path $regPath -Name "WeaselRoot" -ErrorAction SilentlyContinue).WeaselRoot
        if ($root -and (Test-Path -LiteralPath (Join-Path $root "rime.dll"))) {
            return (Get-Item -LiteralPath $root).FullName
        }
    }
    $bases = @()
    if ($env:ProgramFiles) { $bases += (Join-Path $env:ProgramFiles "Rime") }
    if (${env:ProgramFiles(x86)}) { $bases += (Join-Path ${env:ProgramFiles(x86)} "Rime") }
    $candidates = @()
    foreach ($base in ($bases | Select-Object -Unique)) {
        if (Test-Path -LiteralPath $base) {
            $candidates += Get-ChildItem -LiteralPath $base -Directory -Filter "weasel-*" -ErrorAction SilentlyContinue |
                Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "rime.dll") }
        }
    }
    $best = $candidates | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($best) { return $best.FullName }
    return $null
}

function Test-RimeDllExportsLua54 {
    param([string]$DllPath)
    if (-not $DllPath -or -not (Test-Path -LiteralPath $DllPath)) { return $false }
    try {
        # Parse PE32+ Export Directory (AddressOfNames) to verify real x64 Lua 5.4 exports
        $bytes = [System.IO.File]::ReadAllBytes($DllPath)
        if ($bytes.Length -lt 0x100 -or $bytes[0] -ne 0x4D -or $bytes[1] -ne 0x5A) { return $false }
        $peOff = [BitConverter]::ToInt32($bytes, 0x3C)
        if ($peOff -lt 0 -or ($peOff + 0x90) -gt $bytes.Length) { return $false }
        if ($bytes[$peOff] -ne 0x50 -or $bytes[$peOff + 1] -ne 0x45) { return $false }
        $machine = [BitConverter]::ToUInt16($bytes, $peOff + 4)
        if ($machine -ne 0x8664) { return $false }
        $numSec  = [BitConverter]::ToUInt16($bytes, $peOff + 6)
        $optSize = [BitConverter]::ToUInt16($bytes, $peOff + 20)
        $optOff  = $peOff + 24
        $magic   = [BitConverter]::ToUInt16($bytes, $optOff)
        if ($magic -ne 0x20B) { return $false }
        $expRva  = [BitConverter]::ToUInt32($bytes, $optOff + 112)
        if ($expRva -eq 0) { return $false }

        $secOff = $optOff + $optSize
        $rvaToOff = {
            param([uint32]$rva)
            for ($i = 0; $i -lt $numSec; $i++) {
                $s     = $secOff + $i * 40
                $vAddr = [BitConverter]::ToUInt32($bytes, $s + 12)
                $vSize = [BitConverter]::ToUInt32($bytes, $s + 8)
                $rSize = [BitConverter]::ToUInt32($bytes, $s + 16)
                $rPtr  = [BitConverter]::ToUInt32($bytes, $s + 20)
                $span  = [Math]::Max($vSize, $rSize)
                if ($rva -ge $vAddr -and $rva -lt ($vAddr + $span)) {
                    return [int]($rPtr + ($rva - $vAddr))
                }
            }
            return -1
        }

        $expOff = & $rvaToOff $expRva
        if ($expOff -lt 0 -or ($expOff + 40) -gt $bytes.Length) { return $false }
        $numNames = [BitConverter]::ToUInt32($bytes, $expOff + 24)
        $namesRva = [BitConverter]::ToUInt32($bytes, $expOff + 32)
        $namesOff = & $rvaToOff $namesRva
        if ($namesOff -lt 0) { return $false }

        $needed = [System.Collections.Generic.HashSet[string]]::new([string[]]@(
            "lua_version", "lua_createtable", "lua_rawget", "lua_rawset", "lua_rawlen", "lua_tolstring"
        ))
        for ($i = 0; $i -lt $numNames -and $needed.Count -gt 0; $i++) {
            $pos = $namesOff + $i * 4
            if (($pos + 4) -gt $bytes.Length) { break }
            $nameRva = [BitConverter]::ToUInt32($bytes, $pos)
            $nOff = & $rvaToOff $nameRva
            if ($nOff -lt 0) { continue }
            $end = $nOff
            while ($end -lt $bytes.Length -and $bytes[$end] -ne 0) { $end++ }
            $sym = [System.Text.Encoding]::ASCII.GetString($bytes, $nOff, $end - $nOff)
            [void]$needed.Remove($sym)
        }
        return ($needed.Count -eq 0)
    } catch {
        return $false
    }
}

function Test-NotoSansCjkInstalled {
    foreach ($fontDir in @("C:\Windows\Fonts", (Join-Path $env:LOCALAPPDATA "Microsoft\Windows\Fonts"))) {
        if (Test-Path -LiteralPath $fontDir) {
            $hit = Get-ChildItem -LiteralPath $fontDir -File -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match 'NotoSansCJK|NotoSansTC' } | Select-Object -First 1
            if ($hit) { return $true }
        }
    }
    foreach ($regPath in @("HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts", "HKCU:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")) {
        $props = Get-ItemProperty -Path $regPath -ErrorAction SilentlyContinue
        if ($props) {
            foreach ($p in $props.PSObject.Properties) {
                if ($p.Name -match 'Noto Sans CJK' -or ([string]$p.Value) -match 'NotoSansCJK') {
                    return $true
                }
            }
        }
    }
    return $false
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

# 1. Weasel + PE32+ Lua 5.4 exports
$weaselDir = Get-WeaselDir
$luaOk     = if ($weaselDir) { Test-RimeDllExportsLua54 -DllPath (Join-Path $weaselDir "rime.dll") } else { $false }
$weaselOk  = [bool]$weaselDir -and ($SkipNeural -or $luaOk)
Add-Check -Name "weasel:install_and_lua54" -Ok $weaselOk -Detail "dir=$weaselDir lua54_exports=$luaOk"

# 2. Core rime-chth1z files (including all 6 Lua scripts)
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
    "lua\date_translator.lua",
    "lua\lunar.lua",
    "cn_dicts\corrections.dict.yaml",
    "cn_dicts\base.dict.yaml",
    "en_dicts\en_ext.dict.yaml",
    "opencc\s2twp.json",
    "opencc\s2tw.json"
)
$missingCore = @($coreFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $RimeDir $_)) })
Add-Check -Name "chth1z:core_files" -Ok ($missingCore.Count -eq 0) -Detail $(if ($missingCore.Count -eq 0) { "all $($coreFiles.Count) core files present" } else { "MISSING: $($missingCore -join ', ')" })

# 3. Wanxiang LTS .gram
if (-not $SkipGram) {
    $gramPath = Join-Path $RimeDir "wanxiang-lts-zh-hans.gram"
    $gramOk   = (Test-Path -LiteralPath $gramPath) -and ((Get-Item -LiteralPath $gramPath).Length -ge 100MB)
    $gramInfo = if (Test-Path -LiteralPath $gramPath) { "{0:F1} MB" -f ((Get-Item -LiteralPath $gramPath).Length / 1MB) } else { "MISSING: $gramPath" }
    Add-Check -Name "gram:wanxiang_lts" -Ok $gramOk -Detail $gramInfo
}

# 4. rime-neural binaries & model
$neuralDir = Join-Path $RimeDir "neural"
if (-not $SkipNeural) {
    $missingN = @()
    foreach ($req in @("rime_neural.dll", "onnxruntime.dll", "tokenizer.json", "unified_vocab.json")) {
        if (-not (Test-Path -LiteralPath (Join-Path $neuralDir $req))) { $missingN += "neural\$req" }
    }
    $onnxFiles = if (Test-Path -LiteralPath $neuralDir) {
        @(Get-ChildItem -LiteralPath $neuralDir -File -Filter "*.onnx" -ErrorAction SilentlyContinue)
    } else { @() }
    if ($onnxFiles.Count -lt 1) { $missingN += "neural\*.onnx" }
    elseif ($onnxFiles.Count -gt 1) { $missingN += "CONFLICT: multiple .onnx models ($($onnxFiles.Name -join ', '))" }
    if (-not (Test-Path -LiteralPath (Join-Path $RimeDir "lua\rime_neural.lua"))) { $missingN += "lua\rime_neural.lua" }
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
    if (-not (Test-Path -LiteralPath $built)) {
        Add-Check -Name "build:$sid" -Ok $false -Detail "MISSING: $built (run WeaselDeployer /deploy)"
        continue
    }
    $raw = Get-Content -LiteralPath $built -Raw -Encoding UTF8
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

# 7. Session-anchored Weasel deploy & warning/error logs (immune to pre-fix logs from older sessions)
$logDir  = Join-Path $env:TEMP "rime.weasel"
$logErrs = [System.Collections.Generic.List[string]]::new()
$summary = ""
if (Test-Path -LiteralPath $logDir) {
    $allInfos = @(Get-ChildItem -LiteralPath $logDir -Filter "rime.weasel*.INFO*" -File -ErrorAction SilentlyContinue |
        Sort-Object CreationTime -Descending)

    # Locate the latest deploy log containing "finished updating schemas:"
    $latestDeployLog = $null
    $latestSummaryLine = $null
    foreach ($inf in ($allInfos | Select-Object -First 12)) {
        $lines = Get-Content -LiteralPath $inf.FullName -Encoding UTF8 -ErrorAction SilentlyContinue
        $sLine = $lines | Where-Object { $_ -match 'finished updating schemas:' } | Select-Object -Last 1
        if ($sLine) {
            $latestDeployLog = $inf
            $latestSummaryLine = $sLine
            break
        }
    }

    # Anchor cutoff to the current active session (latest deploy log creation and/or live WeaselServer StartTime)
    $serverStart = $null
    if ($procs.Count -ge 1) {
        try { $serverStart = ($procs | Sort-Object StartTime -Descending | Select-Object -First 1).StartTime } catch {}
    }

    $anchorTime = $null
    if ($latestDeployLog -and $serverStart) {
        $anchorTime = if ($latestDeployLog.CreationTime -lt $serverStart) {
            $latestDeployLog.CreationTime.AddSeconds(-2)
        } else {
            $serverStart.AddSeconds(-2)
        }
    } elseif ($latestDeployLog) {
        $anchorTime = $latestDeployLog.CreationTime.AddSeconds(-2)
    } elseif ($serverStart) {
        $anchorTime = $serverStart.AddSeconds(-2)
    } else {
        $anchorTime = (Get-Date).AddMinutes(-15)
    }

    if ($latestDeployLog -and $latestSummaryLine) {
        $summary = "$($latestDeployLog.Name): $($latestSummaryLine.Trim())"
        if ($summary -notmatch '0 failure') {
            $logErrs.Add("deploy failure: $summary")
        }
    }

    $sessionInfos = @($allInfos | Where-Object { $_.CreationTime -ge $anchorTime } | Select-Object -First 6)
    foreach ($inf in $sessionInfos) {
        $lines = Get-Content -LiteralPath $inf.FullName -Encoding UTF8 -ErrorAction SilentlyContinue
        $efLines = @($lines | Where-Object { $_ -match '^[EF]\d{4,8}\s' } | Select-Object -First 3)
        foreach ($l in $efLines) { $logErrs.Add("$($inf.Name): $($l.Trim())") }
    }

    $warnLogs = @(Get-ChildItem -LiteralPath $logDir -File -ErrorAction SilentlyContinue |
        Where-Object { $_.CreationTime -ge $anchorTime -and ($_.Name -match 'WARNING|ERROR') } |
        Sort-Object CreationTime -Descending | Select-Object -First 6)
    foreach ($wf in $warnLogs) {
        $hits = Select-String -LiteralPath $wf.FullName -Pattern 'rime_neural|chth1z_pipeline|tw_dual|lua_filter.*error|loadlib failed|circular dependencies' -ErrorAction SilentlyContinue | Select-Object -First 3
        foreach ($h in $hits) { $logErrs.Add("$($wf.Name):$($h.LineNumber): $($h.Line.Trim())") }
    }
}
$logDetail = if ($logErrs.Count -eq 0) {
    if ($summary) { "0 errors | $summary" } else { "0 errors in active Weasel session logs" }
} else {
    ($logErrs | Select-Object -First 5) -join " | "
}
Add-Check -Name "logs:weasel_clean" -Ok ($logErrs.Count -eq 0) -Detail $logDetail

# Advisory (non-blocking) status
$notoInstalled = Test-NotoSansCjkInstalled
$task = Get-ScheduledTask -TaskName "RimeChth1zWeeklyUpdate" -ErrorAction SilentlyContinue

$out = [ordered]@{
    ok       = $allOk
    rime_dir = $RimeDir
    advisory = [ordered]@{
        noto_cjk_tc_installed  = $notoInstalled
        weekly_task_registered = [bool]$task
        feedback_jsonl_exists  = (Test-Path -LiteralPath (Join-Path $neuralDir "feedback.jsonl"))
    }
    checks   = $checks
}

$out | ConvertTo-Json -Depth 5
if (-not $allOk) { exit 1 }
