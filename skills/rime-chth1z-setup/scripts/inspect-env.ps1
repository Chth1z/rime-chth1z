<#
.SYNOPSIS
    Read-only environment audit for Chth1z/rime-chth1z full stack on Windows Weasel.
.DESCRIPTION
    Inspects OS architecture, admin elevation, Weasel install directory & Lua 5.4 C API exports,
    RimeUserDir (registry-first, %APPDATA%\Rime fallback), existing Rime configs & user data,
    Wanxiang LTS .gram model, rime-neural binaries/model, Noto Sans CJK TC font availability,
    weekly update scheduled task, local repo clone candidates, and CLI tool availability.
    Outputs structured JSON for agent consumption without modifying any files.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "SilentlyContinue"

function Get-WeaselDir {
    $candidates = @()
    foreach ($regPath in @("HKLM:\SOFTWARE\Rime\Weasel", "HKLM:\SOFTWARE\WOW6432Node\Rime\Weasel", "HKCU:\SOFTWARE\Rime\Weasel")) {
        $root = (Get-ItemProperty -Path $regPath -Name "WeaselRoot" -ErrorAction SilentlyContinue).WeaselRoot
        if ($root -and (Test-Path (Join-Path $root "rime.dll"))) {
            $candidates += (Get-Item $root)
        }
    }
    foreach ($base in @("C:\Program Files\Rime", "C:\Program Files (x86)\Rime")) {
        if (Test-Path $base) {
            $candidates += Get-ChildItem $base -Directory -Filter "weasel-*" |
                Where-Object { Test-Path (Join-Path $_.FullName "rime.dll") }
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
    if (-not $DllPath -or -not (Test-Path $DllPath)) { return $false }
    try {
        $bytes = [System.IO.File]::ReadAllBytes($DllPath)
        $ascii = [System.Text.Encoding]::ASCII.GetString($bytes)
        return ($ascii.Contains("lua_pcallk") -and $ascii.Contains("lua_tolstring") -and $ascii.Contains("lua_createtable"))
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
        if (Test-Path $fontDir) {
            $hit = Get-ChildItem $fontDir -File -ErrorAction SilentlyContinue |
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
$dllVerInfo    = if ($rimeDll -and (Test-Path $rimeDll)) { (Get-Item $rimeDll).VersionInfo.FileVersion } else { $null }
$luaExportsOk  = Test-RimeDllExportsLua54 -DllPath $rimeDll
$weaselProcs   = @(Get-Process -Name WeaselServer -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })

$userDir       = Get-RimeUserDir
$userDirExists = Test-Path $userDir

$activeSchemas = @()
foreach ($cfgFile in @("default.custom.yaml", "default.yaml")) {
    $p = Join-Path $userDir $cfgFile
    if (Test-Path $p) {
        $lines = Get-Content $p -Encoding UTF8
        $inList = $false
        foreach ($line in $lines) {
            if ($line -match '^\s*schema_list\s*:') { $inList = $true; continue }
            if ($inList) {
                if ($line -match '^\s*-\s*schema\s*:\s*([A-Za-z0-9_\-]+)') {
                    if ($activeSchemas -notcontains $Matches[1]) { $activeSchemas += $Matches[1] }
                } elseif ($line -match '^\s*[A-Za-z_]' -and $line -notmatch '^\s*#') {
                    $inList = $false
                }
            }
        }
        if ($activeSchemas.Count -gt 0) { break }
    }
}

$selectedSchema = $null
$userYaml = Join-Path $userDir "user.yaml"
if (Test-Path $userYaml) {
    $m = Select-String -Path $userYaml -Pattern 'previously_selected_schema\s*:\s*"?([A-Za-z0-9_\-]+)"?' | Select-Object -First 1
    if ($m) { $selectedSchema = $m.Matches[0].Groups[1].Value }
}

$existingRootYamls = @(if ($userDirExists) { Get-ChildItem $userDir -File -Filter "*.yaml" | ForEach-Object { $_.Name } })
$existingUserDbs   = @(if ($userDirExists) { Get-ChildItem $userDir -Directory -Filter "*.userdb" | ForEach-Object { $_.Name } })

$gramPath    = Join-Path $userDir "wanxiang-lts-zh-hans.gram"
$gramExists  = Test-Path $gramPath
$gramSizeMb  = if ($gramExists) { [math]::Round((Get-Item $gramPath).Length / 1MB, 2) } else { 0 }

$neuralDir   = Join-Path $userDir "neural"
$neuralFiles = [System.Collections.Generic.List[object]]::new()
if (Test-Path $neuralDir) {
    foreach ($nf in (Get-ChildItem $neuralDir -File)) {
        $neuralFiles.Add([ordered]@{
            name    = $nf.Name
            size_mb = [math]::Round($nf.Length / 1MB, 2)
        })
    }
}
$luaNeuralInstalled = Test-Path (Join-Path $userDir "lua\rime_neural.lua")
$neuralReady = (Test-Path (Join-Path $neuralDir "rime_neural.dll")) -and
               (Test-Path (Join-Path $neuralDir "onnxruntime.dll")) -and
               (@(Get-ChildItem $neuralDir -Filter "*.onnx" -ErrorAction SilentlyContinue).Count -ge 1) -and
               $luaNeuralInstalled

$chth1zDeployed = (Test-Path (Join-Path $userDir "lua\chth1z_pipeline_filter.lua")) -and
                  (Test-Path (Join-Path $userDir "lua\tw_dual_filter.lua")) -and
                  (Test-Path (Join-Path $userDir "cn_dicts\corrections.dict.yaml"))

$task = Get-ScheduledTask -TaskName "RimeChth1zWeeklyUpdate" -ErrorAction SilentlyContinue
$repoCandidates = @()
foreach ($cand in @($PWD.Path, (Join-Path $env:USERPROFILE "rime-chth1z"), "D:\Github\rime-chth1z")) {
    if ($cand -and (Test-Path (Join-Path $cand "rime_frost_double_pinyin.schema.yaml")) -and (Test-Path (Join-Path $cand "scripts\deploy-local.ps1"))) {
        $resolved = (Resolve-Path $cand).Path
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
    rime_dll_version          = $dllVerInfo
    rime_dll_lua54_exports    = $luaExportsOk
    weasel_server_pids        = $weaselProcs
    rime_user_dir             = $userDir
    rime_user_dir_exists      = $userDirExists
    existing_root_yaml_count  = $existingRootYamls.Count
    existing_userdbs          = $existingUserDbs
    has_custom_phrase         = (Test-Path (Join-Path $userDir "custom_phrase.txt"))
    has_feedback_jsonl        = (Test-Path (Join-Path $neuralDir "feedback.jsonl"))
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
