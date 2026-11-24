<#
.SYNOPSIS
    Weekly updater for Chth1z/rime-chth1z + Chth1z/rime-neural (Release) + Wanxiang LTS gram + Weasel Nightly check.
.DESCRIPTION
    Self-contained updater (also copied standalone to <RimeUserDir>\auto_update\Update-RimeChth1z.ps1).
    Checks Chth1z/rime-chth1z (main), Chth1z/rime-neural (latest Release), and amzxyz/rime-wanxiang-data (LTS .gram).
    If a clean local git clone exists at $RepoDir on branch main, fast-forwards it via git pull --ff-only;
    otherwise downloads the immutable commit archive to a temp staging directory without touching dirty local edits.
    Preserves *.userdb, custom_phrase.txt, installation.yaml, user.yaml, neural/feedback.jsonl, and auto_update/.
#>
param(
    [switch]$Force,
    [switch]$ForceTheme,
    [switch]$InitOnly,
    [switch]$SkipGram,
    [string]$RepoDir = "",
    [string]$RimeDir = "",
    [string]$Theme   = "apple_graphite_dark"
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch {}

if (-not $RimeDir) {
    $regDir = (Get-ItemProperty -Path "HKCU:\SOFTWARE\Rime\Weasel" -Name "RimeUserDir" -ErrorAction SilentlyContinue).RimeUserDir
    $RimeDir = if ($regDir -and $regDir.Trim()) { $regDir.Trim() } else { Join-Path $env:APPDATA "Rime" }
}
if (-not $RepoDir -and $PSScriptRoot) {
    $candRepo = Split-Path $PSScriptRoot -Parent
    if ($candRepo -and (Test-Path -LiteralPath (Join-Path $candRepo ".git")) -and (Test-Path -LiteralPath (Join-Path $candRepo "rime_frost_double_pinyin.schema.yaml"))) {
        $RepoDir = $candRepo
    }
}
$rimeDir   = $RimeDir
$workDir   = Join-Path $rimeDir "auto_update"
$stateFile = Join-Path $workDir "state.json"
$logFile   = Join-Path $workDir "update.log"
$headers   = @{ "User-Agent" = "RimeChth1zWeeklyUpdater/1.4" }
$ghToken   = if ($env:GITHUB_TOKEN) { $env:GITHUB_TOKEN } elseif ($env:GH_TOKEN) { $env:GH_TOKEN } else { "" }
if ($ghToken) { $headers["Authorization"] = "Bearer $ghToken" }

New-Item -ItemType Directory -Force -Path $workDir | Out-Null

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

function Format-ShortSha([string]$Sha, [int]$Len = 8) {
    if (-not $Sha) { return "unknown" }
    if ($Sha.Length -le $Len) { return $Sha }
    return $Sha.Substring(0, $Len)
}

function Invoke-NativeSafe {
    param([scriptblock]$Action)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $global:LASTEXITCODE = 0
        $out = & $Action 2>&1
        $code = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
        return [pscustomobject]@{ ExitCode = $code; Output = @($out | ForEach-Object { [string]$_ }) }
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Write-Log([string]$Msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $Msg"
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Output $line
}

function Trim-Log {
    if (Test-Path -LiteralPath $logFile) {
        $all = @(Get-Content -LiteralPath $logFile -Encoding UTF8)
        if ($all.Count -gt 300) {
            Set-Content -LiteralPath $logFile -Value ($all | Select-Object -Last 300) -Encoding UTF8
        }
    }
}

function Get-WeaselDir {
    $proc = Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($proc) {
        try {
            if ($proc.Path) {
                $procDir = Split-Path $proc.Path -Parent
                if ($procDir -and (Test-Path -LiteralPath (Join-Path $procDir "WeaselDeployer.exe"))) {
                    return (Get-Item -LiteralPath $procDir).FullName
                }
            }
        } catch {}
    }
    foreach ($regPath in @("HKLM:\SOFTWARE\Rime\Weasel", "HKLM:\SOFTWARE\WOW6432Node\Rime\Weasel", "HKCU:\SOFTWARE\Rime\Weasel")) {
        $root = (Get-ItemProperty -Path $regPath -Name "WeaselRoot" -ErrorAction SilentlyContinue).WeaselRoot
        if ($root -and (Test-Path -LiteralPath (Join-Path $root "WeaselDeployer.exe"))) {
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
                Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "WeaselDeployer.exe") }
        }
    }
    $best = $candidates | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($best) { return $best.FullName }
    return $null
}

function Stop-WeaselCleanly([string]$ServerExe) {
    if (-not (Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue)) { return }
    if ($ServerExe -and (Test-Path -LiteralPath $ServerExe)) {
        [void](Invoke-NativeSafe { & $ServerExe /q })
    }
    for ($i = 0; $i -lt 20; $i++) {
        if (-not (Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 300
    }
    Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    for ($i = 0; $i -lt 10; $i++) {
        if (-not (Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 200
    }
}

function Start-WeaselDetached([string]$ServerExe) {
    if (-not $ServerExe -or -not (Test-Path -LiteralPath $ServerExe)) { return }
    try {
        $cim = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = "`"$ServerExe`"" }
        if ($null -eq $cim -or [int]$cim.ReturnValue -ne 0) {
            $rv = if ($null -eq $cim) { "null" } else { [string]$cim.ReturnValue }
            throw "Win32_Process.Create returned $rv"
        }
    } catch {
        Start-Process -FilePath $ServerExe
    }
}

function Invoke-CurlDownload([string]$Url, [string]$OutFile) {
    $res = Invoke-NativeSafe { & curl.exe -fsSL --retry 3 --connect-timeout 20 -o $OutFile $Url }
    if ($res.ExitCode -ne 0) {
        $tail = ($res.Output | Select-Object -Last 8) -join " | "
        throw "curl download failed (ExitCode=$($res.ExitCode)): $Url ($tail)"
    }
    if (-not (Test-Path -LiteralPath $OutFile) -or (Get-Item -LiteralPath $OutFile).Length -eq 0) {
        throw "Downloaded file missing or empty: $OutFile"
    }
}

function Sync-RepoToRime([string]$SourceRoot, [string]$TargetRimeDir, [string]$ThemeName, [bool]$OverwriteTheme = $false) {
    New-Item -ItemType Directory -Force -Path `
        (Join-Path $TargetRimeDir "cn_dicts"), `
        (Join-Path $TargetRimeDir "cn_dicts_cell"), `
        (Join-Path $TargetRimeDir "en_dicts"), `
        (Join-Path $TargetRimeDir "lua"), `
        (Join-Path $TargetRimeDir "opencc") | Out-Null

    Get-ChildItem -LiteralPath (Join-Path $SourceRoot "cn_dicts") -File | Where-Object { $_.Name -ne "tencent.dict.yaml" } | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $TargetRimeDir "cn_dicts\$($_.Name)") -Force
    }
    Copy-Item -Path (Join-Path $SourceRoot "cn_dicts_cell\*") -Destination (Join-Path $TargetRimeDir "cn_dicts_cell") -Force
    foreach ($ef in @("en.dict.yaml", "en_ext.dict.yaml", "cn_en.txt", "cn_en_double_pinyin.txt")) {
        $src = Join-Path $SourceRoot "en_dicts\$ef"
        if (Test-Path -LiteralPath $src) { Copy-Item -LiteralPath $src -Destination (Join-Path $TargetRimeDir "en_dicts\$ef") -Force }
    }
    Copy-Item -Path (Join-Path $SourceRoot "lua\*.lua") -Destination (Join-Path $TargetRimeDir "lua") -Force
    foreach ($of in @("s2tw.json","s2twp.json","STPhrases.ocd2","STCharacters.ocd2","TWPhrases.ocd2","TWVariants.ocd2","t2s.json","tw2sp.json","TSCharacters.ocd2","TSPhrases.ocd2","TWPhrasesRev.ocd2","TWVariantsRev.ocd2","TWVariantsRevPhrases.ocd2","emoji.json","emoji.txt","others.txt","chinese_english.json","chinese_english.txt","english_chinese.txt")) {
        $src = Join-Path $SourceRoot "opencc\$of"
        if (Test-Path -LiteralPath $src) { Copy-Item -LiteralPath $src -Destination (Join-Path $TargetRimeDir "opencc\$of") -Force }
    }
    $rootYamls = @(
        "default.yaml","key_bindings.yaml","punctuation.yaml","symbols.yaml","symbols_v.yaml",
        "rime_frost.dict.yaml","rime_frost.schema.yaml","rime_frost_double_pinyin.schema.yaml",
        "melt_eng.dict.yaml","melt_eng.schema.yaml","melt_eng_algebra.yaml","melt_eng_algebra_common.yaml"
    )
    foreach ($ry in $rootYamls) {
        $src = Join-Path $SourceRoot $ry
        if (Test-Path -LiteralPath $src) { Copy-Item -LiteralPath $src -Destination (Join-Path $TargetRimeDir $ry) -Force }
    }
    # Preserve existing user *.custom.yaml and customized non-GC rime.lua overrides
    Get-ChildItem -LiteralPath (Join-Path $SourceRoot "profiles") -File -ErrorAction SilentlyContinue | ForEach-Object {
        $dst = Join-Path $TargetRimeDir $_.Name
        $isCustomYaml = $_.Name.EndsWith(".custom.yaml")
        if ($isCustomYaml) {
            if (-not (Test-Path -LiteralPath $dst)) {
                Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
            }
        } elseif ($_.Name -eq "rime.lua") {
            $canOverwrite = -not (Test-Path -LiteralPath $dst)
            if (-not $canOverwrite) {
                $nonGcLines = @(Get-Content -LiteralPath $dst -Encoding UTF8 -ErrorAction SilentlyContinue |
                    Where-Object { $_ -notmatch '^\s*(--.*)?$' -and $_ -notmatch '^\s*collectgarbage\(' })
                $canOverwrite = ($nonGcLines.Count -eq 0)
            }
            if ($canOverwrite) {
                Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
            } else {
                Write-Log "Preserving customized rime.lua."
            }
        } else {
            Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
        }
    }
    $weaselCustomDst = Join-Path $TargetRimeDir "weasel.custom.yaml"
    if ($ThemeName -ne "keep" -and ($OverwriteTheme -or (-not (Test-Path -LiteralPath $weaselCustomDst)))) {
        $themeFile = Join-Path $SourceRoot "themes\$ThemeName.custom.yaml"
        if (Test-Path -LiteralPath $themeFile) {
            Copy-Item -LiteralPath $themeFile -Destination $weaselCustomDst -Force
        }
    }
    $selfUpdater = Join-Path $SourceRoot "scripts\update-local.ps1"
    if (Test-Path -LiteralPath $selfUpdater) {
        Copy-Item -LiteralPath $selfUpdater -Destination (Join-Path $TargetRimeDir "auto_update\Update-RimeChth1z.ps1") -Force
    }
    $obsolete = @(
        "radical_pinyin.dict.yaml","radical_pinyin.schema.yaml",
        "rime_frost_aux.dict.yaml","rime_frost_aux.schema.yaml",
        "lua\aux_lookup_filter.lua","lua\aux_code",
        "lua\autocap_filter.lua","lua\cn_en_spacer.lua","lua\corrector.lua",
        "lua\en_spacer.lua","lua\force_gc.lua","lua\is_in_user_dict.lua",
        "lua\long_word_filter.lua","lua\number_translator.lua","lua\pin_cand_filter.lua",
        "lua\reduce_english_filter.lua","lua\unicode.lua","lua\v_filter.lua",
        "lua\zhiyi_rerank_filter.lua"
    )
    foreach ($rel in $obsolete) {
        $obs = Join-Path $TargetRimeDir $rel
        if (Test-Path -LiteralPath $obs) { Remove-Item -LiteralPath $obs -Recurse -Force -ErrorAction SilentlyContinue }
    }
    $buildDir = Join-Path $TargetRimeDir "build"
    if (Test-Path -LiteralPath $buildDir) {
        foreach ($pat in @("radical_pinyin.*", "rime_frost_aux.*")) {
            Get-ChildItem -LiteralPath $buildDir -File -Filter $pat -ErrorAction SilentlyContinue | ForEach-Object {
                Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

$createdNew = $false
$mutex = New-Object System.Threading.Mutex($true, "Local\RimeChth1zWeeklyUpdate", [ref]$createdNew)
if (-not $createdNew) {
    Write-Log "[SKIP] Another RimeChth1zWeeklyUpdate instance is already running."
    exit 0
}

$wasRunning = $false
try {
    Write-Log "=== Weekly update check (rime-chth1z / rime-neural / Wanxiang LTS / Weasel Nightly) ==="

    $state = [ordered]@{
        repo_sha       = ""
        neural_tag     = ""
        gram_sha256    = ""
        gram_meta      = ""
        weasel_nightly = ""
        last_check     = ""
        last_update    = ""
    }
    if (Test-Path -LiteralPath $stateFile) {
        try {
            $loaded = Get-Content -LiteralPath $stateFile -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($k in @("repo_sha","neural_tag","gram_sha256","gram_meta","weasel_nightly","last_check","last_update")) {
                if ($loaded -and ($loaded.PSObject.Properties.Name -contains $k) -and $loaded.$k) {
                    $state[$k] = [string]$loaded.$k
                }
            }
        } catch {
            Write-Log "[WARN] Corrupt state.json detected ($($_.Exception.Message)); resetting baseline state."
        }
    }

    # 1. Query remote versions
    $repoCommit     = Invoke-RestMethod "https://api.github.com/repos/Chth1z/rime-chth1z/commits/main" -Headers $headers -TimeoutSec 20
    $remoteRepoSha  = [string]$repoCommit.sha
    $remoteRepoDate = [string]$repoCommit.commit.committer.date
    if ($remoteRepoSha -notmatch '^[0-9a-fA-F]{40}$') {
        throw "Invalid commit SHA returned for Chth1z/rime-chth1z main: '$remoteRepoSha'"
    }

    $neuralRel       = $null
    $neuralAsset     = $null
    $neuralSumAsset  = $null
    $remoteNeuralTag = ""
    try {
        $neuralRel       = Invoke-RestMethod "https://api.github.com/repos/Chth1z/rime-neural/releases/latest" -Headers $headers -TimeoutSec 20
        $remoteNeuralTag = [string]$neuralRel.tag_name
        $neuralAsset     = $neuralRel.assets | Where-Object { $_.name -match 'win-x64\.zip$' } | Select-Object -First 1
        $neuralSumAsset  = $neuralRel.assets | Where-Object { $_.name -eq 'SHA256SUMS.txt' } | Select-Object -First 1
    } catch {
        Write-Log "[WARN] Could not query Chth1z/rime-neural latest release: $_"
    }

    $gramAsset      = $null
    $remoteGramSha  = ""
    $remoteGramMeta = ""
    if (-not $SkipGram) {
        try {
            $wxRelease = Invoke-RestMethod "https://api.github.com/repos/amzxyz/rime-wanxiang-data/releases/tags/LTS" -Headers $headers -TimeoutSec 20
            $gramAsset = $wxRelease.assets | Where-Object { $_.name -eq "wanxiang-lts-zh-hans.gram" } | Select-Object -First 1
            if ($gramAsset) {
                $remoteGramMeta = "$($gramAsset.updated_at)|$($gramAsset.size)"
                if ($gramAsset.digest -match '^sha256:([0-9a-fA-F]{64})$') {
                    $remoteGramSha = $Matches[1].ToLowerInvariant()
                }
            }
        } catch {
            Write-Log "[WARN] Could not query amzxyz/rime-wanxiang-data LTS release (skipping .gram check): $_"
        }
    }

    $remoteWeaselName = ""
    try {
        $weaselRel   = Invoke-RestMethod "https://api.github.com/repos/rime/weasel/releases/tags/latest" -Headers $headers -TimeoutSec 20
        $weaselAsset = $weaselRel.assets | Where-Object { $_.name -match 'installer\.exe$' } | Select-Object -First 1
        if ($weaselAsset) { $remoteWeaselName = [string]$weaselAsset.name }
    } catch {
        Write-Log "[WARN] Could not query rime/weasel latest release (advisory only): $_"
    }

    $gramTag = if ($SkipGram) { "skipped" } elseif ($remoteGramSha) { (Format-ShortSha $remoteGramSha 12) + "..." } elseif ($remoteGramMeta) { $remoteGramMeta } else { "unavailable" }
    Write-Log ("Remote: Repo={0} ({1}) | Neural={2} | Gram={3} | Weasel={4}" -f (Format-ShortSha $remoteRepoSha 8), $remoteRepoDate, $remoteNeuralTag, $gramTag, $remoteWeaselName)

    $localGramPath = Join-Path $rimeDir "wanxiang-lts-zh-hans.gram"
    $localGramSha  = if (Test-Path -LiteralPath $localGramPath) {
        (Get-FileHash -LiteralPath $localGramPath -Algorithm SHA256).Hash.ToLowerInvariant()
    } else { "" }

    if ($InitOnly) {
        $state.repo_sha       = $remoteRepoSha
        $state.neural_tag     = $remoteNeuralTag
        $state.gram_sha256    = if ($localGramSha) { $localGramSha } else { $remoteGramSha }
        $state.gram_meta      = $remoteGramMeta
        $state.weasel_nightly = $remoteWeaselName
        $state.last_check     = (Get-Date -Format "o")
        Write-Utf8NoBom $stateFile ($state | ConvertTo-Json)
        Write-Log "Initialized state baseline (state.json)."
        Trim-Log
        exit 0
    }

    $neuralInstalled = Test-Path -LiteralPath (Join-Path $rimeDir "neural\rime_neural.dll")
    $needRepo   = $Force -or ($remoteRepoSha -ne $state.repo_sha)
    $needNeural = $neuralInstalled -and [bool]$neuralAsset -and ($Force -or ($remoteNeuralTag -ne $state.neural_tag))
    $needGram   = $false
    if (-not $SkipGram -and $gramAsset) {
        if ($Force) {
            $needGram = $true
        } elseif (Test-Path -LiteralPath $localGramPath) {
            if ($remoteGramSha) {
                $needGram = ($remoteGramSha -ne $localGramSha)
            } elseif ($remoteGramMeta) {
                $needGram = ($remoteGramMeta -ne $state.gram_meta)
            }
        }
    }

    if ($remoteWeaselName -and $state.weasel_nightly -and ($remoteWeaselName -ne $state.weasel_nightly)) {
        Write-Log "[NOTICE] New Weasel Nightly available: $remoteWeaselName (requires manual admin install)"
    }

    if (-not $needRepo -and -not $needNeural -and -not $needGram) {
        Write-Log "Repository, rime-neural, and Wanxiang LTS model are all up to date."
        $state.last_check  = (Get-Date -Format "o")
        $state.gram_sha256 = $localGramSha
        if ($remoteGramMeta) { $state.gram_meta = $remoteGramMeta }
        if (-not $state.weasel_nightly) { $state.weasel_nightly = $remoteWeaselName }
        Write-Utf8NoBom $stateFile ($state | ConvertTo-Json)
        Trim-Log
        exit 0
    }

    $stage = Join-Path $env:TEMP ("rime-chth1z-update-" + (Get-Date -Format "yyyyMMddHHmmss") + "-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
    New-Item -ItemType Directory -Force -Path $stage | Out-Null

    try {
        # 2. Prepare repo source
        $deploySource = $null
        if ($needRepo) {
            $usedLocalGit = $false
            if ($RepoDir -and (Test-Path -LiteralPath (Join-Path $RepoDir ".git")) -and (Get-Command git -ErrorAction SilentlyContinue)) {
                $branchRes = Invoke-NativeSafe { & git -C $RepoDir rev-parse --abbrev-ref HEAD }
                $branch = if ($branchRes.ExitCode -eq 0 -and $branchRes.Output.Count -gt 0) { ([string]$branchRes.Output[0]).Trim() } else { "" }
                $dirtyRes = Invoke-NativeSafe { & git -C $RepoDir status --porcelain }
                $dirty = @($dirtyRes.Output | Where-Object { [string]$_ -and ([string]$_).Trim() -ne "" })
                if ($branch -eq "main" -and $dirty.Count -eq 0) {
                    Write-Log "Fast-forwarding clean local repo at $RepoDir..."
                    $pullRes = Invoke-NativeSafe { & git -C $RepoDir pull --ff-only --quiet origin main }
                    if ($pullRes.ExitCode -eq 0) {
                        $headRes = Invoke-NativeSafe { & git -C $RepoDir rev-parse HEAD }
                        $headSha = if ($headRes.ExitCode -eq 0 -and $headRes.Output.Count -gt 0) { ([string]$headRes.Output[0]).Trim() } else { "" }
                        if ($headSha -eq $remoteRepoSha) {
                            $deploySource = $RepoDir
                            $usedLocalGit = $true
                            Write-Log "Local repo updated cleanly to $(Format-ShortSha $headSha 8)."
                        }
                    }
                } else {
                    Write-Log "Local repo has branch='$branch' or uncommitted changes; using isolated commit archive download."
                }
            }

            if (-not $usedLocalGit) {
                Write-Log "Downloading Chth1z/rime-chth1z (immutable commit $(Format-ShortSha $remoteRepoSha 8))..."
                $repoZip = Join-Path $stage "rime-chth1z.zip"
                Invoke-CurlDownload "https://github.com/Chth1z/rime-chth1z/archive/$remoteRepoSha.zip" $repoZip
                $repoEx = Join-Path $stage "repo"
                Expand-Archive -Path $repoZip -DestinationPath $repoEx -Force
                $deploySource = (Get-ChildItem -LiteralPath $repoEx -Directory | Select-Object -First 1).FullName
                if (-not $deploySource -or -not (Test-Path -LiteralPath (Join-Path $deploySource "rime_frost_double_pinyin.schema.yaml"))) {
                    throw "Downloaded archive structure invalid; aborting update."
                }
                Write-Log "Archive verified."
            }
        }

        # 2b. Prepare rime-neural official release bundle (fail-closed SHA-256 verification before Expand-Archive)
        $neuralStageDll = $null
        $neuralStageLua = $null
        if ($needNeural) {
            if (-not $neuralSumAsset) {
                throw "rime-neural release $remoteNeuralTag missing external SHA256SUMS.txt asset; refusing unverified binary."
            }
            Write-Log "Downloading Chth1z/rime-neural $remoteNeuralTag ($($neuralAsset.name))..."
            $nZip   = Join-Path $stage $neuralAsset.name
            $extSum = Join-Path $stage "SHA256SUMS.txt"
            Invoke-CurlDownload $neuralAsset.browser_download_url $nZip
            Invoke-CurlDownload $neuralSumAsset.browser_download_url $extSum

            $sumLines = @(Get-Content -LiteralPath $extSum -Encoding UTF8)
            $zipGot   = (Get-FileHash -LiteralPath $nZip -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($neuralAsset.digest -match '^sha256:([0-9a-fA-F]{64})$') {
                $apiDigest = $Matches[1].ToLowerInvariant()
                if ($zipGot -ne $apiDigest) {
                    throw "$($neuralAsset.name) SHA-256 mismatch against GitHub digest (got=$zipGot, expected=$apiDigest)"
                }
            }
            $zipPattern = '(?i)^([0-9a-f]{64})\s+\*?' + [regex]::Escape($neuralAsset.name) + '$'
            $zipMatch   = $sumLines | Where-Object { $_.Trim() -match $zipPattern } | Select-Object -First 1
            if ($zipMatch) {
                $zipExp = ($zipMatch.Trim() -split '\s+')[0].ToLowerInvariant()
                if ($zipGot -ne $zipExp) {
                    throw "$($neuralAsset.name) SHA-256 mismatch against SHA256SUMS.txt (got=$zipGot, expected=$zipExp)"
                }
            } else {
                throw "External SHA256SUMS.txt missing checksum entry for $($neuralAsset.name); refusing unverified archive."
            }

            $nEx = Join-Path $stage "neural"
            Expand-Archive -Path $nZip -DestinationPath $nEx -Force
            $dll = Join-Path $nEx "rime_neural.dll"
            $lua = Join-Path $nEx "rime_neural.lua"
            if (-not (Test-Path -LiteralPath $dll) -or -not (Test-Path -LiteralPath $lua)) {
                throw "rime-neural release bundle missing DLL or Lua script."
            }
            foreach ($pair in @(@{ Name = "rime_neural.dll"; Path = $dll }, @{ Name = "rime_neural.lua"; Path = $lua })) {
                $pattern   = '(?i)^([0-9a-f]{64})\s+\*?' + [regex]::Escape($pair.Name) + '$'
                $matchLine = $sumLines | Where-Object { $_.Trim() -match $pattern } | Select-Object -First 1
                if (-not $matchLine) {
                    throw "External SHA256SUMS.txt missing checksum entry for $($pair.Name)"
                }
                $expHash = ($matchLine.Trim() -split '\s+')[0].ToLowerInvariant()
                $gotHash = (Get-FileHash -LiteralPath $pair.Path -Algorithm SHA256).Hash.ToLowerInvariant()
                if ($gotHash -ne $expHash) {
                    throw "$($pair.Name) SHA-256 mismatch (got=$gotHash, expected=$expHash)"
                }
            }
            $neuralStageDll = $dll
            $neuralStageLua = $lua
            Write-Log "rime-neural $remoteNeuralTag verified against external SHA256SUMS.txt."
        }

        # 2c. Prepare Wanxiang LTS .gram (fail-closed SHA-256 verification)
        $newGramPath = $null
        $dlGramHash  = ""
        if ($needGram) {
            if (-not $remoteGramSha) {
                throw "Wanxiang LTS release asset missing SHA-256 digest; refusing unverified model."
            }
            Write-Log "Downloading Wanxiang LTS model ($($gramAsset.browser_download_url))..."
            $newGramPath = Join-Path $stage "wanxiang-lts-zh-hans.gram"
            Invoke-CurlDownload $gramAsset.browser_download_url $newGramPath
            $dlGramHash = (Get-FileHash -LiteralPath $newGramPath -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($dlGramHash -ne $remoteGramSha) {
                throw "Wanxiang model SHA-256 mismatch (got=$dlGramHash, expected=$remoteGramSha)"
            }
            Write-Log "Wanxiang LTS model SHA-256 verified ($(Format-ShortSha $dlGramHash 12)...)."
        }

        # 3. Stop WeaselServer cleanly
        $weaselDir = Get-WeaselDir
        if (-not $weaselDir) { throw "Weasel install directory not found." }
        $serverExe   = Join-Path $weaselDir "WeaselServer.exe"
        $deployerExe = Join-Path $weaselDir "WeaselDeployer.exe"

        $wasRunning = [bool](Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue)
        if ($wasRunning) {
            Stop-WeaselCleanly $serverExe
        }

        # 4. Apply updates
        if ($needRepo -and $deploySource) {
            Write-Log "Syncing files from $deploySource -> $rimeDir..."
            Sync-RepoToRime -SourceRoot $deploySource -TargetRimeDir $rimeDir -ThemeName $Theme -OverwriteTheme ([bool]$ForceTheme)
        }

        if ($needNeural -and $neuralStageDll -and $neuralStageLua) {
            Write-Log "Installing rime-neural $remoteNeuralTag..."
            Stop-WeaselCleanly $serverExe
            Copy-Item -LiteralPath $neuralStageDll -Destination (Join-Path $rimeDir "neural\rime_neural.dll") -Force
            Copy-Item -LiteralPath $neuralStageLua -Destination (Join-Path $rimeDir "lua\rime_neural.lua") -Force
        }

        if ($needGram -and $newGramPath) {
            Write-Log "Atomically replacing Wanxiang LTS model..."
            $tmpTarget = "$localGramPath.new"
            if (Test-Path -LiteralPath $tmpTarget) { Remove-Item -LiteralPath $tmpTarget -Force }
            $srcRoot = [System.IO.Path]::GetPathRoot($newGramPath)
            $dstRoot = [System.IO.Path]::GetPathRoot($tmpTarget)
            if ($srcRoot -and $dstRoot -and ($srcRoot.Equals($dstRoot, [System.StringComparison]::OrdinalIgnoreCase))) {
                [System.IO.File]::Move($newGramPath, $tmpTarget)
            } else {
                Copy-Item -LiteralPath $newGramPath -Destination $tmpTarget -Force
            }
            if (Test-Path -LiteralPath $localGramPath) {
                [System.IO.File]::Replace($tmpTarget, $localGramPath, $null)
            } else {
                [System.IO.File]::Move($tmpTarget, $localGramPath)
            }
        }

        # 5. Deploy & verify fresh WeaselDeployer logs + single detached WeaselServer
        Stop-WeaselCleanly $serverExe
        $weaselLogDir = Join-Path $env:TEMP "rime.weasel"
        $priorLogs = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
        if (Test-Path -LiteralPath $weaselLogDir) {
            Get-ChildItem -LiteralPath $weaselLogDir -File -ErrorAction SilentlyContinue | ForEach-Object {
                [void]$priorLogs.Add($_.Name)
            }
        }
        Write-Log "Running WeaselDeployer /deploy..."
        $deployStart = Get-Date
        $pDep = Start-Process -FilePath $deployerExe -ArgumentList "/deploy" -Wait -PassThru
        Write-Log "Deploy finished (ExitCode=$($pDep.ExitCode))"
        if ($pDep.ExitCode -ne 0) {
            throw "WeaselDeployer failed (ExitCode=$($pDep.ExitCode)); keeping previous state for retry."
        }
        if (Test-Path -LiteralPath $weaselLogDir) {
            $newLogs = @(Get-ChildItem -LiteralPath $weaselLogDir -Filter "rime.weasel*.INFO*" -File -ErrorAction SilentlyContinue |
                Where-Object { (-not $priorLogs.Contains($_.Name)) -or ($_.CreationTime -ge $deployStart.AddSeconds(-2)) } |
                Sort-Object CreationTime -Descending | Select-Object -First 4)
            $summaryLine = $null
            $badLog = $null
            foreach ($log in $newLogs) {
                $lines = Get-Content -LiteralPath $log.FullName -Encoding UTF8 -ErrorAction SilentlyContinue
                if (-not $summaryLine) {
                    $s = $lines | Where-Object { $_ -match 'finished updating schemas:' } | Select-Object -Last 1
                    if ($s) { $summaryLine = $s }
                }
                if (-not $badLog -and ($lines | Where-Object { $_ -match '^[EF]\d{4,8}\s' })) {
                    $badLog = $log.Name
                }
            }
            if (-not $summaryLine) {
                throw "No new WeaselDeployer INFO log containing 'finished updating schemas:' was found in $weaselLogDir."
            }
            Write-Log "Deploy summary: $summaryLine"
            if ($summaryLine -notmatch '0 failure') {
                throw "WeaselDeployer reported schema failures: $summaryLine"
            }
            if ($badLog) {
                throw "WeaselDeployer logged errors in $badLog"
            }
        }

        Start-Sleep -Milliseconds 400
        $procs = @(Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue)
        if ($wasRunning -and $procs.Count -eq 0) {
            Start-WeaselDetached $serverExe
            Write-Log "Restarted WeaselServer.exe."
        } elseif ($procs.Count -gt 1) {
            $procs | Sort-Object StartTime | Select-Object -Skip 1 | Stop-Process -Force -ErrorAction SilentlyContinue
            Write-Log "Reconciled duplicate WeaselServer.exe instances to a single process."
        }

        if ($needRepo)   { $state.repo_sha   = $remoteRepoSha }
        if ($needNeural) { $state.neural_tag = $remoteNeuralTag }
        if ($needGram) {
            $state.gram_sha256 = $dlGramHash
            $state.gram_meta   = $remoteGramMeta
        }
        $state.last_check     = (Get-Date -Format "o")
        $state.last_update    = (Get-Date -Format "o")
        $state.weasel_nightly = $remoteWeaselName
        Write-Utf8NoBom $stateFile ($state | ConvertTo-Json)
        Write-Log "=== Update completed ==="
    }
    finally {
        if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
        $leftoverTmp = "$localGramPath.new"
        if (Test-Path -LiteralPath $leftoverTmp) { Remove-Item -LiteralPath $leftoverTmp -Force -ErrorAction SilentlyContinue }
    }
}
catch {
    Write-Log "[ERROR] Update exception: $_"
    $weaselDir = Get-WeaselDir
    if ($wasRunning -and $weaselDir -and -not (Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue)) {
        Start-WeaselDetached (Join-Path $weaselDir "WeaselServer.exe")
    }
    Trim-Log
    exit 1
}
finally {
    if ($mutex) {
        try { $mutex.ReleaseMutex() } catch {}
        $mutex.Dispose()
    }
}

Trim-Log
exit 0
