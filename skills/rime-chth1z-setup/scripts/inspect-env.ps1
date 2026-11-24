<#
.SYNOPSIS
    Read-only environment audit for Chth1z/rime-chth1z full stack on Windows Weasel.
.DESCRIPTION
    Standalone script (directly downloadable via raw URL).
    Inspects OS architecture, admin elevation, Weasel install directory & PE32+ Lua 5.4 C API exports,
    RimeUserDir (registry-first, %APPDATA%\Rime fallback), existing Rime configs & user data,
    Wanxiang LTS .gram model, rime-neural binaries/model/vocab readiness, Noto Sans CJK TC font
    availability, weekly update scheduled task, local repo clone candidates, and CLI tool availability.
    Outputs structured UTF-8 JSON for agent consumption without modifying any files.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "SilentlyContinue"
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
            $candidates += Get-ChildItem -LiteralPath $base -Directory -Filter "weasel-*" |
                Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "rime.dll") }
        }
    }
    $best = $candidates | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($best) { return $best.FullName }
    return $null
}

function Get-RimeUserDir {
    $regDir = (Get-ItemProperty -Path "HKCU:\SOFTWARE\Rime\Weasel" -Name "RimeUserDir" -ErrorAction SilentlyContinue).RimeUserDir
    if ($regDir -and $regDir.Trim()) {
        return $regDir.Trim()
    }
    return (Join-Path $env:APPDATA "Rime")
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

function Test-IsAdmin {
    try {
        $id = [Security.Principal.WindowsIdentity]::GetCurrent()
        $pr = New-Object Security.Principal.WindowsPrincipal($id)
        return $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
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

$weaselDir     = Get-WeaselDir
$rimeDll       = if ($weaselDir) { Join-Path $weaselDir "rime.dll" } else { $null }
$weaselVersion = if ($weaselDir) { (Split-Path $weaselDir -Leaf) -replace '^weasel-', '' } else { $null }
$dllVerInfo    = if ($rimeDll -and (Test-Path -LiteralPath $rimeDll)) { (Get-Item -LiteralPath $rimeDll).VersionInfo.FileVersion } else { $null }
$luaExportsOk  = Test-RimeDllExportsLua54 -DllPath $rimeDll
$weaselProcs   = @(Get-Process -Name WeaselServer -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })

$userDir       = Get-RimeUserDir
$userDirExists = Test-Path -LiteralPath $userDir

$distVersion = ""
$installYaml = Join-Path $userDir "installation.yaml"
if (Test-Path -LiteralPath $installYaml) {
    $vm = Select-String -LiteralPath $installYaml -Pattern '^\s*distribution_version\s*:\s*"?([^"#]+)"?' | Select-Object -First 1
    if ($vm) { $distVersion = $vm.Matches[0].Groups[1].Value.Trim() }
}

# Detect active schema list (prefer compiled build\default.yaml; fallback to default.custom.yaml + default.yaml)
$parseSchemaList = {
    param([string]$filePath)
    $found = @()
    if (-not (Test-Path -LiteralPath $filePath)) { return $found }
    $lines = Get-Content -LiteralPath $filePath -Encoding UTF8
    $inList = $false
    foreach ($line in $lines) {
        if ($line -match '^\s*[''"]?schema_list(?:/\+)?[''"]?\s*:\s*(.*)$') {
            $rest = $Matches[1].Trim()
            if ($rest -match '^\[') {
                foreach ($m in [regex]::Matches($rest, 'schema\s*:\s*[''"]?([A-Za-z0-9_\-]+)[''"]?')) {
                    if ($found -notcontains $m.Groups[1].Value) { $found += $m.Groups[1].Value }
                }
                $inList = $false
            } else {
                $inList = $true
            }
            continue
        }
        if ($inList) {
            if ($line -match '^\s*-\s*(?:\{\s*)?schema\s*:\s*[''"]?([A-Za-z0-9_\-]+)[''"]?') {
                if ($found -notcontains $Matches[1]) { $found += $Matches[1] }
            } elseif ($line -match '^\s*[A-Za-z_''"]' -and $line -notmatch '^\s*#') {
                $inList = $false
            }
        }
    }
    return $found
}

$activeSchemas = & $parseSchemaList (Join-Path $userDir "build\default.yaml")
if ($activeSchemas.Count -eq 0) {
    $customSchemas = & $parseSchemaList (Join-Path $userDir "default.custom.yaml")
    $baseSchemas   = & $parseSchemaList (Join-Path $userDir "default.yaml")
    $customRaw = if (Test-Path -LiteralPath (Join-Path $userDir "default.custom.yaml")) {
        Get-Content -LiteralPath (Join-Path $userDir "default.custom.yaml") -Raw -Encoding UTF8
    } else { "" }
    if ($customRaw -match 'schema_list/\+') {
        $activeSchemas = @($baseSchemas + $customSchemas | Select-Object -Unique)
    } elseif ($customSchemas.Count -gt 0) {
        $activeSchemas = $customSchemas
    } else {
        $activeSchemas = $baseSchemas
    }
}

$selectedSchema = $null
$userYaml = Join-Path $userDir "user.yaml"
if (Test-Path -LiteralPath $userYaml) {
    $m = Select-String -LiteralPath $userYaml -Pattern 'previously_selected_schema\s*:\s*[''"]?([A-Za-z0-9_\-]+)[''"]?' | Select-Object -First 1
    if ($m) { $selectedSchema = $m.Matches[0].Groups[1].Value }
}

$existingRootYamls = @(if ($userDirExists) { Get-ChildItem -LiteralPath $userDir -File -Filter "*.yaml" | ForEach-Object { $_.Name } })
$existingUserDbs   = @(if ($userDirExists) { Get-ChildItem -LiteralPath $userDir -Directory -Filter "*.userdb" | ForEach-Object { $_.Name } })

$gramPath   = Join-Path $userDir "wanxiang-lts-zh-hans.gram"
$gramExists = Test-Path -LiteralPath $gramPath
$gramSizeMb = if ($gramExists) { [math]::Round((Get-Item -LiteralPath $gramPath).Length / 1MB, 2) } else { 0 }

$neuralDir   = Join-Path $userDir "neural"
$neuralFiles = [System.Collections.Generic.List[object]]::new()
if (Test-Path -LiteralPath $neuralDir) {
    foreach ($nf in (Get-ChildItem -LiteralPath $neuralDir -File)) {
        $neuralFiles.Add([ordered]@{
            name    = $nf.Name
            size_mb = [math]::Round($nf.Length / 1MB, 2)
        })
    }
}
$luaNeuralInstalled = Test-Path -LiteralPath (Join-Path $userDir "lua\rime_neural.lua")
$onnxCount = if (Test-Path -LiteralPath $neuralDir) {
    @(Get-ChildItem -LiteralPath $neuralDir -File -Filter "*.onnx" -ErrorAction SilentlyContinue).Count
} else { 0 }
$neuralReady = (Test-Path -LiteralPath (Join-Path $neuralDir "rime_neural.dll")) -and
               (Test-Path -LiteralPath (Join-Path $neuralDir "onnxruntime.dll")) -and
               (Test-Path -LiteralPath (Join-Path $neuralDir "tokenizer.json")) -and
               (Test-Path -LiteralPath (Join-Path $neuralDir "unified_vocab.json")) -and
               ($onnxCount -eq 1) -and
               $luaNeuralInstalled

$chth1zDeployed = (Test-Path -LiteralPath (Join-Path $userDir "lua\chth1z_pipeline_filter.lua")) -and
                  (Test-Path -LiteralPath (Join-Path $userDir "lua\tw_dual_filter.lua")) -and
                  (Test-Path -LiteralPath (Join-Path $userDir "cn_dicts\corrections.dict.yaml"))

$task = Get-ScheduledTask -TaskName "RimeChth1zWeeklyUpdate" -ErrorAction SilentlyContinue
$repoCandidates = @()
$scriptRepoCand = $null
if ($PSScriptRoot) {
    try { $scriptRepoCand = Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent } catch {}
}
foreach ($cand in @($scriptRepoCand, $PWD.Path, (Join-Path $env:USERPROFILE "rime-chth1z"))) {
    if ($cand -and (Test-Path -LiteralPath (Join-Path $cand "rime_frost_double_pinyin.schema.yaml")) -and (Test-Path -LiteralPath (Join-Path $cand "scripts\deploy-local.ps1"))) {
        $resolved = (Resolve-Path -LiteralPath $cand).Path
        if ($repoCandidates -notcontains $resolved) { $repoCandidates += $resolved }
    }
}

$result = [ordered]@{
    os_arch                   = $env:PROCESSOR_ARCHITECTURE
    is_64bit_os               = [Environment]::Is64BitOperatingSystem
    is_admin                  = (Test-IsAdmin)
    logical_processors        = [Environment]::ProcessorCount
    weasel_dir                = $weaselDir
    weasel_folder_version     = $weaselVersion
    weasel_dist_version       = $distVersion
    rime_dll_version          = $dllVerInfo
    rime_dll_lua54_exports    = $luaExportsOk
    weasel_server_pids        = $weaselProcs
    rime_user_dir             = $userDir
    rime_user_dir_exists      = $userDirExists
    existing_root_yaml_count  = $existingRootYamls.Count
    existing_userdbs          = $existingUserDbs
    has_custom_phrase         = (Test-Path -LiteralPath (Join-Path $userDir "custom_phrase.txt"))
    has_feedback_jsonl        = (Test-Path -LiteralPath (Join-Path $neuralDir "feedback.jsonl"))
    previously_selected       = $selectedSchema
    active_schema_list        = $activeSchemas
    rime_chth1z_deployed      = $chth1zDeployed
    wanxiang_gram_installed   = $gramExists
    wanxiang_gram_size_mb     = $gramSizeMb
    rime_neural_installed     = $neuralReady
    existing_neural_files     = $neuralFiles
    lua_neural_installed      = $luaNeuralInstalled
    noto_cjk_tc_installed     = (Test-NotoSansCjkInstalled)
    weekly_task_registered    = [bool]$task
    weekly_task_state         = if ($task) { [string]$task.State } else { $null }
    local_repo_candidates     = $repoCandidates
    has_git                   = [bool](Get-Command git -ErrorAction SilentlyContinue)
    has_curl                  = [bool](Get-Command curl.exe -ErrorAction SilentlyContinue)
    has_python                = [bool](Get-Command python -ErrorAction SilentlyContinue)
}

$result | ConvertTo-Json -Depth 5
