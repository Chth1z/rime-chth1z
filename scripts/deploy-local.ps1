<#
.SYNOPSIS
    Deploy rime-chth1z + profiles/ + themes/ to %APPDATA%\Rime safely.
.DESCRIPTION
    Preserves *.userdb, wanxiang-lts-zh-hans.gram, custom_phrase.txt, installation.yaml, user.yaml,
    and auto_update/. Runs WeaselDeployer /deploy, verifies ExitCode=0 and fresh deploy INFO logs,
    restarts a single detached WeaselServer, and optionally runs isolated child-process verification
    (bench/accuracy-test.ps1 and bench/bench-rime.ps1).
#>
param(
    [string]$Theme = "apple_graphite_dark",
    [string]$RimeDir = "",
    [switch]$ForceCustom,
    [switch]$SkipDeploy,
    [switch]$RunBench,
    [switch]$Verify
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}

. (Join-Path $PSScriptRoot "_common.ps1")

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not $RimeDir) {
    $RimeDir = Get-RimeUserDir
}
$rimeDir = $RimeDir

$weaselDir = Get-WeaselDir -RequireFile "WeaselDeployer.exe"
if (-not $weaselDir) { throw "Weasel install directory not found." }

Write-Output "Deploying from $repoRoot -> $rimeDir (Theme=$Theme)"

# 1. Stop WeaselServer cleanly
$serverExe = Join-Path $weaselDir "WeaselServer.exe"
Stop-WeaselServerClean -ServerExe $serverExe

# 2. Sync dicts (excluding tencent), en_dicts, lua, opencc, root schemas
New-Item -ItemType Directory -Force -Path `
    (Join-Path $rimeDir "cn_dicts"), `
    (Join-Path $rimeDir "cn_dicts_cell"), `
    (Join-Path $rimeDir "en_dicts"), `
    (Join-Path $rimeDir "lua"), `
    (Join-Path $rimeDir "opencc") | Out-Null

Get-ChildItem -LiteralPath (Join-Path $repoRoot "cn_dicts") -File | Where-Object { $_.Name -ne "tencent.dict.yaml" } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $rimeDir "cn_dicts\$($_.Name)") -Force
}
Copy-Item -Path (Join-Path $repoRoot "cn_dicts_cell\*") -Destination (Join-Path $rimeDir "cn_dicts_cell") -Force
foreach ($ef in @("en.dict.yaml", "en_ext.dict.yaml", "cn_en.txt", "cn_en_double_pinyin.txt")) {
    $src = Join-Path $repoRoot "en_dicts\$ef"
    if (Test-Path -LiteralPath $src) { Copy-Item -LiteralPath $src -Destination (Join-Path $rimeDir "en_dicts\$ef") -Force }
}
Copy-Item -Path (Join-Path $repoRoot "lua\*.lua") -Destination (Join-Path $rimeDir "lua") -Force
foreach ($of in @("s2tw.json","s2twp.json","STPhrases.ocd2","STCharacters.ocd2","TWPhrases.ocd2","TWVariants.ocd2","t2s.json","tw2sp.json","TSCharacters.ocd2","TSPhrases.ocd2","TWPhrasesRev.ocd2","TWVariantsRev.ocd2","TWVariantsRevPhrases.ocd2","emoji.json","emoji.txt","others.txt","chinese_english.json","chinese_english.txt","english_chinese.txt")) {
    $src = Join-Path $repoRoot "opencc\$of"
    if (Test-Path -LiteralPath $src) { Copy-Item -LiteralPath $src -Destination (Join-Path $rimeDir "opencc\$of") -Force }
}
$rootYamls = @(
    "default.yaml","key_bindings.yaml","punctuation.yaml","symbols.yaml","symbols_v.yaml",
    "rime_frost.dict.yaml","rime_frost.schema.yaml","rime_frost_double_pinyin.schema.yaml",
    "melt_eng.dict.yaml","melt_eng.schema.yaml","melt_eng_algebra.yaml","melt_eng_algebra_common.yaml"
)
foreach ($ry in $rootYamls) {
    $src = Join-Path $repoRoot $ry
    if (Test-Path -LiteralPath $src) { Copy-Item -LiteralPath $src -Destination (Join-Path $rimeDir $ry) -Force }
}

$customPhraseDst = Join-Path $rimeDir "custom_phrase.txt"
$customPhraseSrc = Join-Path $repoRoot "custom_phrase.txt"
if (-not (Test-Path -LiteralPath $customPhraseDst) -and (Test-Path -LiteralPath $customPhraseSrc)) {
    Copy-Item -LiteralPath $customPhraseSrc -Destination $customPhraseDst -Force
}

# 3. Apply curated profiles & selected Weasel theme
# Preserve existing user *.custom.yaml (and custom non-GC rime.lua) unless -ForceCustom is passed.
Get-ChildItem -LiteralPath (Join-Path $repoRoot "profiles") -File | ForEach-Object {
    $dst = Join-Path $rimeDir $_.Name
    $isCustomYaml = $_.Name.EndsWith(".custom.yaml")
    if ($isCustomYaml) {
        if ($ForceCustom -or (-not (Test-Path -LiteralPath $dst))) {
            Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
        }
    } elseif ($_.Name -eq "rime.lua") {
        $canOverwrite = $ForceCustom -or (-not (Test-Path -LiteralPath $dst))
        if (-not $canOverwrite) {
            $nonGcLines = @(Get-Content -LiteralPath $dst -Encoding UTF8 -ErrorAction SilentlyContinue |
                Where-Object { $_ -notmatch '^\s*(--.*)?$' -and $_ -notmatch '^\s*collectgarbage\(' })
            $canOverwrite = ($nonGcLines.Count -eq 0)
        }
        if ($canOverwrite) {
            Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
        } else {
            Write-Output "Preserving customized rime.lua (pass -ForceCustom to overwrite)."
        }
    } else {
        Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
    }
}
if ($Theme -eq "keep") {
    Write-Output "Keeping existing weasel.custom.yaml (-Theme keep)"
} else {
    $themeFile = Join-Path $repoRoot "themes\$Theme.custom.yaml"
    if (Test-Path -LiteralPath $themeFile) {
        Copy-Item -LiteralPath $themeFile -Destination (Join-Path $rimeDir "weasel.custom.yaml") -Force
    } else {
        Write-Warning "Theme file not found: $themeFile (keeping existing weasel.custom.yaml)"
    }
}
$updaterSrc = Join-Path $repoRoot "scripts\update-local.ps1"
if (Test-Path -LiteralPath $updaterSrc) {
    $autoDir = Join-Path $rimeDir "auto_update"
    New-Item -ItemType Directory -Force -Path $autoDir | Out-Null
    Copy-Item -LiteralPath $updaterSrc -Destination (Join-Path $autoDir "Update-RimeChth1z.ps1") -Force
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
    if (Test-Path -LiteralPath $obs) {
        Remove-Item -LiteralPath $obs -Recurse -Force -ErrorAction SilentlyContinue
        Write-Output "Removed obsolete file: $rel"
    }
}
$buildDir = Join-Path $rimeDir "build"
if (Test-Path -LiteralPath $buildDir) {
    foreach ($pat in @("radical_pinyin.*", "rime_frost_aux.*")) {
        Get-ChildItem -LiteralPath $buildDir -File -Filter $pat -ErrorAction SilentlyContinue | ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
            Write-Output "Removed obsolete build artifact: build\$($_.Name)"
        }
    }
}

if ($SkipDeploy) {
    Write-Output "Files synced to $rimeDir (-SkipDeploy)."
    exit 0
}

# 4. Deploy & verify fresh WeaselDeployer log + single detached WeaselServer
Stop-WeaselServerClean -ServerExe $serverExe
$weaselLogDir = Join-Path $env:TEMP "rime.weasel"
$priorLogs = Get-WeaselLogSnapshot -LogDir $weaselLogDir
$deployStart = Get-Date
$p = Start-Process -FilePath (Join-Path $weaselDir "WeaselDeployer.exe") -ArgumentList "/deploy" -Wait -PassThru
Write-Output "WeaselDeployer ExitCode: $($p.ExitCode)"
if ($p.ExitCode -ne 0) { throw "WeaselDeployer failed with ExitCode=$($p.ExitCode)" }

Assert-WeaselDeployLogs -DeployStart $deployStart -PriorLogNames $priorLogs -LogDir $weaselLogDir -OnSummary {
    param($logName, $summaryLine)
    Write-Output "Deploy log ($logName): $summaryLine"
}

Start-Sleep -Milliseconds 400
$procs = @(Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)
if ($procs.Count -eq 0) {
    Start-WeaselDetached -ServerExe $serverExe
    Start-Sleep -Milliseconds 600
    $procs = @(Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)
} elseif ($procs.Count -gt 1) {
    $procs | Sort-Object StartTime | Select-Object -Skip 1 | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 250
    $procs = @(Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)
}
Write-Output "WeaselServer running: count=$($procs.Count) PID=$($procs.Id -join ',')"
if ($procs.Count -ne 1) { throw "Expected exactly 1 WeaselServer instance, found $($procs.Count)" }

# 5. Run optional post-deploy verification in isolated child PowerShell processes (zero rime.dll/glog cross-contamination)
if ($Verify) {
    $accScript = Join-Path $repoRoot "bench\accuracy-test.ps1"
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $global:LASTEXITCODE = 0
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $accScript -RimeDir $rimeDir -WaitNeural
        $rc = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
    } finally {
        $ErrorActionPreference = $prevEap
    }
    if ($rc -ne 0) { throw "accuracy-test.ps1 failed (ExitCode=$rc)" }
}
if ($RunBench -or $Verify) {
    $benchScript = Join-Path $repoRoot "bench\bench-rime.ps1"
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $global:LASTEXITCODE = 0
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $benchScript -RimeDir $rimeDir -WaitNeural
        $rc = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
    } finally {
        $ErrorActionPreference = $prevEap
    }
    if ($rc -ne 0) { throw "bench-rime.ps1 failed (ExitCode=$rc)" }
}
exit 0
