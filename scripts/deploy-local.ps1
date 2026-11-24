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
    [string]$RimeDir = "",
    [switch]$ForceCustom,
    [switch]$SkipDeploy,
    [switch]$RunBench,
    [switch]$Verify
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not $RimeDir) {
    $regDir = (Get-ItemProperty -Path "HKCU:\SOFTWARE\Rime\Weasel" -Name "RimeUserDir" -ErrorAction SilentlyContinue).RimeUserDir
    $RimeDir = if ($regDir -and $regDir.Trim()) { $regDir.Trim() } else { Join-Path $env:APPDATA "Rime" }
}
$rimeDir = $RimeDir

$weaselCandidates = @()
foreach ($regPath in @("HKLM:\SOFTWARE\Rime\Weasel", "HKLM:\SOFTWARE\WOW6432Node\Rime\Weasel", "HKCU:\SOFTWARE\Rime\Weasel")) {
    $root = (Get-ItemProperty -Path $regPath -Name "WeaselRoot" -ErrorAction SilentlyContinue).WeaselRoot
    if ($root -and (Test-Path (Join-Path $root "WeaselDeployer.exe"))) {
        $weaselCandidates += (Get-Item $root)
    }
}
foreach ($base in @("C:\Program Files\Rime", "C:\Program Files (x86)\Rime")) {
    if (Test-Path $base) {
        $weaselCandidates += Get-ChildItem $base -Directory -Filter "weasel-*" -ErrorAction SilentlyContinue |
            Where-Object { Test-Path (Join-Path $_.FullName "WeaselDeployer.exe") }
    }
}
$weaselItem = $weaselCandidates | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$weaselDir  = if ($weaselItem) { $weaselItem.FullName } else { $null }
if (-not $weaselDir) { throw "Weasel install directory not found." }

function Stop-WeaselServerClean([string]$ExePath) {
    if (-not (Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)) { return }
    & $ExePath /q 2>$null
    for ($i = 0; $i -lt 15; $i++) {
        if (-not (Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 250
    }
    Get-Process -Name WeaselServer -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

Write-Output "Deploying from $repoRoot -> $rimeDir (Theme=$Theme)"

# 1. Stop WeaselServer cleanly
$serverExe = Join-Path $weaselDir "WeaselServer.exe"
Stop-WeaselServerClean $serverExe

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
foreach ($of in @("s2tw.json","s2twp.json","STPhrases.ocd2","STCharacters.ocd2","TWPhrases.ocd2","TWVariants.ocd2","t2s.json","tw2sp.json","TSCharacters.ocd2","TSPhrases.ocd2","TWPhrasesRev.ocd2","TWVariantsRev.ocd2","TWVariantsRevPhrases.ocd2","emoji.json","emoji.txt","others.txt","chinese_english.json","chinese_english.txt","english_chinese.txt")) {
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

$customPhraseDst = Join-Path $rimeDir "custom_phrase.txt"
$customPhraseSrc = Join-Path $repoRoot "custom_phrase.txt"
if (-not (Test-Path $customPhraseDst) -and (Test-Path $customPhraseSrc)) {
    Copy-Item $customPhraseSrc $customPhraseDst -Force
}

# 3. Apply curated profiles & selected Weasel theme
# Always sync rime.lua (GC tuning); preserve existing user *.custom.yaml unless -ForceCustom is passed.
Get-ChildItem (Join-Path $repoRoot "profiles") -File | ForEach-Object {
    $dst = Join-Path $rimeDir $_.Name
    $isCustomYaml = $_.Name.EndsWith(".custom.yaml")
    if (-not $isCustomYaml -or $ForceCustom -or (-not (Test-Path $dst))) {
        Copy-Item $_.FullName $dst -Force
    }
}
if ($Theme -eq "keep") {
    Write-Output "Keeping existing weasel.custom.yaml (-Theme keep)"
} else {
    $themeFile = Join-Path $repoRoot "themes\$Theme.custom.yaml"
    if (Test-Path $themeFile) {
        Copy-Item $themeFile (Join-Path $rimeDir "weasel.custom.yaml") -Force
    } else {
        Write-Warning "Theme file not found: $themeFile (keeping existing weasel.custom.yaml)"
    }
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

if ($SkipDeploy) {
    Write-Output "Files synced to $rimeDir (-SkipDeploy)."
    return
}

# 4. Deploy & verify WeaselDeployer log + single WeaselServer
Stop-WeaselServerClean $serverExe
$deployStart = Get-Date
$p = Start-Process -FilePath (Join-Path $weaselDir "WeaselDeployer.exe") -ArgumentList "/deploy" -Wait -PassThru
Write-Output "WeaselDeployer ExitCode: $($p.ExitCode)"
if ($p.ExitCode -ne 0) { throw "WeaselDeployer failed with ExitCode=$($p.ExitCode)" }

$weaselLogDir = Join-Path $env:TEMP "rime.weasel"
if (Test-Path $weaselLogDir) {
    $infoLog = Get-ChildItem $weaselLogDir -Filter "rime.weasel*.INFO*" -File -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -ge $deployStart.AddSeconds(-2) } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($infoLog) {
        $infoLines = Get-Content $infoLog.FullName -Encoding UTF8 -ErrorAction SilentlyContinue
        $summaryLine = $infoLines | Where-Object { $_ -match 'finished updating schemas:' } | Select-Object -Last 1
        if ($summaryLine) {
            Write-Output "Deploy log: $summaryLine"
            if ($summaryLine -notmatch '0 failure') {
                throw "WeaselDeployer reported schema failures: $summaryLine"
            }
        }
        $badLines = $infoLines | Where-Object { $_ -match '^[EF]\d{8}\s' }
        if ($badLines) {
            throw "WeaselDeployer logged errors in $($infoLog.Name): $($badLines | Select-Object -First 3 | Out-String)"
        }
    }
}

Start-Sleep -Milliseconds 400
$procs = @(Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)
if ($procs.Count -eq 0) {
    try {
        Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = "`"$serverExe`"" } | Out-Null
    } catch {
        Start-Process -FilePath $serverExe
    }
    Start-Sleep -Milliseconds 600
    $procs = @(Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)
} elseif ($procs.Count -gt 1) {
    $procs | Sort-Object StartTime | Select-Object -Skip 1 | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 250
    $procs = @(Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)
}
Write-Output "WeaselServer running: count=$($procs.Count) PID=$($procs.Id -join ',')"
if ($procs.Count -ne 1) { throw "Expected exactly 1 WeaselServer instance, found $($procs.Count)" }

if ($Verify) {
    & (Join-Path $repoRoot "bench\accuracy-test.ps1") -WaitNeural
    if ($LASTEXITCODE -ne 0) { throw "accuracy-test.ps1 failed" }
}
if ($RunBench -or $Verify) {
    & (Join-Path $repoRoot "bench\bench-rime.ps1") -WaitNeural
}
