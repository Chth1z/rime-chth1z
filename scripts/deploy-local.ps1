<#
.SYNOPSIS
    Deploy rime-chth1z + profiles/ + themes/ to %APPDATA%\Rime safely.
.DESCRIPTION
    Preserves *.userdb, wanxiang-lts-zh-hans.gram, custom_phrase.txt, installation.yaml, user.yaml,
    and auto_update/. Runs WeaselDeployer /deploy, verifies ExitCode=0, restarts single WeaselServer,
    and optionally runs bench/bench-rime.ps1.
#>
param(
    [string]$Theme = "apple_graphite_dark",
    [switch]$RunBench,
    [switch]$Verify
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$rimeDir  = Join-Path $env:APPDATA "Rime"
$weaselDir = (Get-ChildItem "C:\Program Files\Rime" -Directory -Filter "weasel-*" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
if (-not $weaselDir) { throw "Weasel install directory not found." }

Write-Output "Deploying from $repoRoot -> $rimeDir (Theme=$Theme)"

# 1. Stop WeaselServer cleanly
$serverExe = Join-Path $weaselDir "WeaselServer.exe"
$wasRunning = [bool](Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)
if ($wasRunning) {
    & $serverExe /q 2>$null
    for ($i = 0; $i -lt 15; $i++) {
        if (-not (Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 250
    }
    Get-Process -Name WeaselServer -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

# 2. Sync dicts (excluding tencent), en_dicts, lua, opencc, root schemas
New-Item -ItemType Directory -Force -Path `
    (Join-Path $rimeDir "cn_dicts"), `
    (Join-Path $rimeDir "cn_dicts_cell"), `
    (Join-Path $rimeDir "en_dicts"), `
    (Join-Path $rimeDir "lua"), `
    (Join-Path $rimeDir "opencc") | Out-Null

Get-ChildItem (Join-Path $repoRoot "cn_dicts") -File | Where-Object { $_.Name -ne "tencent.dict.yaml" } | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $rimeDir "cn_dicts\$($_.Name)") -Force
}
Copy-Item (Join-Path $repoRoot "cn_dicts_cell\*") (Join-Path $rimeDir "cn_dicts_cell") -Force
foreach ($ef in @("en.dict.yaml", "en_ext.dict.yaml", "cn_en.txt", "cn_en_double_pinyin.txt")) {
    $src = Join-Path $repoRoot "en_dicts\$ef"
    if (Test-Path $src) { Copy-Item $src (Join-Path $rimeDir "en_dicts\$ef") -Force }
}
Copy-Item (Join-Path $repoRoot "lua\*.lua") (Join-Path $rimeDir "lua") -Force
foreach ($of in @("s2tw.json","s2twp.json","STPhrases.ocd2","STCharacters.ocd2","TWPhrases.ocd2","TWVariants.ocd2","t2s.json","TSCharacters.ocd2","TSPhrases.ocd2","emoji.json","emoji.txt","others.txt","chinese_english.json","chinese_english.txt","english_chinese.txt")) {
    $src = Join-Path $repoRoot "opencc\$of"
    if (Test-Path $src) { Copy-Item $src (Join-Path $rimeDir "opencc\$of") -Force }
}
$rootYamls = @(
    "default.yaml","key_bindings.yaml","punctuation.yaml","symbols.yaml","symbols_v.yaml",
    "rime_frost.dict.yaml","rime_frost.schema.yaml","rime_frost_double_pinyin.schema.yaml",
    "melt_eng.dict.yaml","melt_eng.schema.yaml","melt_eng_algebra.yaml","melt_eng_algebra_common.yaml"
)
foreach ($ry in $rootYamls) {
    $src = Join-Path $repoRoot $ry
    if (Test-Path $src) { Copy-Item $src (Join-Path $rimeDir $ry) -Force }
}

# 3. Apply curated profiles & selected Weasel theme
Get-ChildItem (Join-Path $repoRoot "profiles") -File | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $rimeDir $_.Name) -Force
}
$themeFile = Join-Path $repoRoot "themes\$Theme.custom.yaml"
if (Test-Path $themeFile) {
    Copy-Item $themeFile (Join-Path $rimeDir "weasel.custom.yaml") -Force
} else {
    Write-Warning "Theme file not found: $themeFile (keeping existing weasel.custom.yaml)"
}
$updaterSrc = Join-Path $repoRoot "scripts\update-local.ps1"
if (Test-Path $updaterSrc) {
    $autoDir = Join-Path $rimeDir "auto_update"
    New-Item -ItemType Directory -Force -Path $autoDir | Out-Null
    Copy-Item $updaterSrc (Join-Path $autoDir "Update-RimeChth1z.ps1") -Force
}

# 3b. Remove known obsolete upstream files no longer referenced by schemas
$obsoleteRelPaths = @(
    "radical_pinyin.dict.yaml",
    "radical_pinyin.schema.yaml",
    "rime_frost_aux.dict.yaml",
    "rime_frost_aux.schema.yaml",
    "lua\aux_lookup_filter.lua",
    "lua\aux_code",
    "lua\autocap_filter.lua",
    "lua\cn_en_spacer.lua",
    "lua\corrector.lua",
    "lua\en_spacer.lua",
    "lua\force_gc.lua",
    "lua\is_in_user_dict.lua",
    "lua\long_word_filter.lua",
    "lua\number_translator.lua",
    "lua\pin_cand_filter.lua",
    "lua\reduce_english_filter.lua",
    "lua\unicode.lua",
    "lua\v_filter.lua",
    "lua\zhiyi_rerank_filter.lua"
)
foreach ($rel in $obsoleteRelPaths) {
    $obs = Join-Path $rimeDir $rel
    if (Test-Path $obs) {
        Remove-Item $obs -Recurse -Force -ErrorAction SilentlyContinue
        Write-Output "Removed obsolete file: $rel"
    }
}

# 4. Deploy & restart single WeaselServer
$p = Start-Process -FilePath (Join-Path $weaselDir "WeaselDeployer.exe") -ArgumentList "/deploy" -Wait -PassThru
Write-Output "WeaselDeployer ExitCode: $($p.ExitCode)"
if ($p.ExitCode -ne 0) { throw "WeaselDeployer failed with ExitCode=$($p.ExitCode)" }

Start-Sleep -Milliseconds 400
if (-not (Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)) {
    try {
        Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = "`"$serverExe`"" } | Out-Null
    } catch {
        Start-Process -FilePath $serverExe
    }
    Start-Sleep -Milliseconds 600
}
$procs = Get-Process -Name WeaselServer -ErrorAction SilentlyContinue
Write-Output "WeaselServer running: count=$($procs.Count) PID=$($procs.Id)"

if ($Verify) {
    & (Join-Path $repoRoot "bench\accuracy-test.ps1")
    if ($LASTEXITCODE -ne 0) { throw "accuracy-test.ps1 failed" }
}
if ($RunBench -or $Verify) {
    & (Join-Path $repoRoot "bench\bench-rime.ps1")
}
