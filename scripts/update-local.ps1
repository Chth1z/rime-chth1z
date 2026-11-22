<#
.SYNOPSIS
    Weekly updater for Chth1z/rime-chth1z + Chth1z/rime-neural (Release) + Wanxiang LTS gram + Weasel Nightly check.
.DESCRIPTION
    Checks Chth1z/rime-chth1z (main), Chth1z/rime-neural (latest Release), and amzxyz/rime-wanxiang-data (LTS .gram).
    If a clean local git clone exists at $RepoDir on branch main, fast-forwards it via git pull --ff-only;
    otherwise downloads the GitHub zip archive to a temp staging directory without touching dirty local edits.
    Preserves *.userdb, custom_phrase.txt, installation.yaml, user.yaml, neural/feedback.jsonl, and auto_update/.
#>
param(
    [switch]$Force,
    [switch]$InitOnly,
    [string]$RepoDir = "D:\Github\rime-chth1z",
    [string]$Theme   = "apple_graphite_dark"
)

$ErrorActionPreference = "Stop"
$rimeDir   = Join-Path $env:APPDATA "Rime"
$workDir   = Join-Path $rimeDir "auto_update"
$stateFile = Join-Path $workDir "state.json"
$logFile   = Join-Path $workDir "update.log"
$headers   = @{ "User-Agent" = "RimeChth1zWeeklyUpdater/1.1" }

New-Item -ItemType Directory -Force -Path $workDir | Out-Null

function Write-Log([string]$Msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $Msg"
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Output $line
}

function Trim-Log {
    if (Test-Path $logFile) {
        $all = Get-Content $logFile -Encoding UTF8
        if ($all.Count -gt 300) {
            Set-Content -Path $logFile -Value ($all | Select-Object -Last 300) -Encoding UTF8
        }
    }
}

function Get-WeaselDir {
    $d = Get-ChildItem "C:\Program Files\Rime" -Directory -Filter "weasel-*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($d) { return $d.FullName }
    return $null
}

function Invoke-CurlDownload([string]$Url, [string]$OutFile) {
    & curl.exe -fSL --retry 3 --connect-timeout 20 -o $OutFile $Url
    if ($LASTEXITCODE -ne 0) {
        throw "curl download failed (ExitCode=$LASTEXITCODE): $Url"
    }
    if (-not (Test-Path $OutFile) -or (Get-Item $OutFile).Length -eq 0) {
        throw "Downloaded file missing or empty: $OutFile"
    }
}

function Sync-RepoToRime([string]$SourceRoot, [string]$TargetRimeDir, [string]$ThemeName) {
    New-Item -ItemType Directory -Force -Path `
        (Join-Path $TargetRimeDir "cn_dicts"), `
        (Join-Path $TargetRimeDir "cn_dicts_cell"), `
        (Join-Path $TargetRimeDir "en_dicts"), `
        (Join-Path $TargetRimeDir "lua"), `
        (Join-Path $TargetRimeDir "opencc") | Out-Null

    Get-ChildItem (Join-Path $SourceRoot "cn_dicts") -File | Where-Object { $_.Name -ne "tencent.dict.yaml" } | ForEach-Object {
        Copy-Item $_.FullName (Join-Path $TargetRimeDir "cn_dicts\$($_.Name)") -Force
    }
    Copy-Item (Join-Path $SourceRoot "cn_dicts_cell\*") (Join-Path $TargetRimeDir "cn_dicts_cell") -Force
    foreach ($ef in @("en.dict.yaml", "en_ext.dict.yaml", "cn_en.txt", "cn_en_double_pinyin.txt")) {
        $src = Join-Path $SourceRoot "en_dicts\$ef"
        if (Test-Path $src) { Copy-Item $src (Join-Path $TargetRimeDir "en_dicts\$ef") -Force }
    }
    Copy-Item (Join-Path $SourceRoot "lua\*.lua") (Join-Path $TargetRimeDir "lua") -Force
    foreach ($of in @("s2tw.json","s2twp.json","STPhrases.ocd2","STCharacters.ocd2","TWPhrases.ocd2","TWVariants.ocd2","t2s.json","TSCharacters.ocd2","TSPhrases.ocd2","emoji.json","emoji.txt","others.txt","chinese_english.json","chinese_english.txt","english_chinese.txt")) {
        $src = Join-Path $SourceRoot "opencc\$of"
        if (Test-Path $src) { Copy-Item $src (Join-Path $TargetRimeDir "opencc\$of") -Force }
    }
    $rootYamls = @(
        "default.yaml","key_bindings.yaml","punctuation.yaml","symbols.yaml","symbols_v.yaml",
        "rime_frost.dict.yaml","rime_frost.schema.yaml","rime_frost_double_pinyin.schema.yaml",
        "melt_eng.dict.yaml","melt_eng.schema.yaml","melt_eng_algebra.yaml","melt_eng_algebra_common.yaml"
    )
    foreach ($ry in $rootYamls) {
        $src = Join-Path $SourceRoot $ry
        if (Test-Path $src) { Copy-Item $src (Join-Path $TargetRimeDir $ry) -Force }
    }
    Get-ChildItem (Join-Path $SourceRoot "profiles") -File -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item $_.FullName (Join-Path $TargetRimeDir $_.Name) -Force
    }
    $themeFile = Join-Path $SourceRoot "themes\$ThemeName.custom.yaml"
    if (Test-Path $themeFile) {
        Copy-Item $themeFile (Join-Path $TargetRimeDir "weasel.custom.yaml") -Force
    }
    $selfUpdater = Join-Path $SourceRoot "scripts\update-local.ps1"
    if (Test-Path $selfUpdater) {
        Copy-Item $selfUpdater (Join-Path $TargetRimeDir "auto_update\Update-RimeChth1z.ps1") -Force
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
        if (Test-Path $obs) { Remove-Item $obs -Recurse -Force -ErrorAction SilentlyContinue }
    }
}

$createdNew = $false
$mutex = New-Object System.Threading.Mutex($true, "Local\RimeChth1zWeeklyUpdate", [ref]$createdNew)
if (-not $createdNew) {
    Write-Log "[SKIP] Another RimeChth1zWeeklyUpdate instance is already running."
    exit 0
}

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
    if (Test-Path $stateFile) {
        $loaded = Get-Content $stateFile -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($k in @("repo_sha","neural_tag","gram_sha256","gram_meta","weasel_nightly","last_check","last_update")) {
            if ($loaded.PSObject.Properties.Name -contains $k -and $loaded.$k) {
                $state[$k] = [string]$loaded.$k
            }
        }
    }

    # 1. Query remote versions
    $repoCommit     = Invoke-RestMethod "https://api.github.com/repos/Chth1z/rime-chth1z/commits/main" -Headers $headers -TimeoutSec 20
    $remoteRepoSha  = [string]$repoCommit.sha
    $remoteRepoDate = [string]$repoCommit.commit.committer.date

    $neuralRel      = $null
    $neuralAsset    = $null
    $remoteNeuralTag = ""
    try {
        $neuralRel = Invoke-RestMethod "https://api.github.com/repos/Chth1z/rime-neural/releases/latest" -Headers $headers -TimeoutSec 20
        $remoteNeuralTag = [string]$neuralRel.tag_name
        $neuralAsset = $neuralRel.assets | Where-Object { $_.name -match 'win-x64\.zip$' } | Select-Object -First 1
    } catch {
        Write-Log "[WARN] Could not query Chth1z/rime-neural latest release: $_"
    }

    $wxRelease = Invoke-RestMethod "https://api.github.com/repos/amzxyz/rime-wanxiang-data/releases/tags/LTS" -Headers $headers -TimeoutSec 20
    $gramAsset = $wxRelease.assets | Where-Object { $_.name -eq "wanxiang-lts-zh-hans.gram" } | Select-Object -First 1
    $remoteGramSha  = ""
    $remoteGramMeta = ""
    if ($gramAsset) {
        $remoteGramMeta = "$($gramAsset.updated_at)|$($gramAsset.size)"
        if ($gramAsset.digest -match '^sha256:([0-9a-fA-F]{64})$') {
            $remoteGramSha = $Matches[1].ToLowerInvariant()
        }
    }

    $weaselRel        = Invoke-RestMethod "https://api.github.com/repos/rime/weasel/releases/tags/latest" -Headers $headers -TimeoutSec 20
    $weaselAsset      = $weaselRel.assets | Where-Object { $_.name -match 'installer\.exe$' } | Select-Object -First 1
    $remoteWeaselName = if ($weaselAsset) { [string]$weaselAsset.name } else { "" }

    $gramTag = if ($remoteGramSha) { $remoteGramSha.Substring(0, 12) + "..." } else { $remoteGramMeta }
    Write-Log "Remote: Repo=$($remoteRepoSha.Substring(0,8)) ($remoteRepoDate) | Neural=$remoteNeuralTag | Gram=$gramTag | Weasel=$remoteWeaselName"

    $localGramPath = Join-Path $rimeDir "wanxiang-lts-zh-hans.gram"
    $localGramSha  = if (Test-Path $localGramPath) {
        (Get-FileHash $localGramPath -Algorithm SHA256).Hash.ToLowerInvariant()
    } else { "" }

    if ($InitOnly) {
        $state.repo_sha       = $remoteRepoSha
        $state.neural_tag     = $remoteNeuralTag
        $state.gram_sha256    = if ($localGramSha) { $localGramSha } else { $remoteGramSha }
        $state.gram_meta      = $remoteGramMeta
        $state.weasel_nightly = $remoteWeaselName
        $state.last_check     = (Get-Date -Format "o")
        $state | ConvertTo-Json | Set-Content -Path $stateFile -Encoding UTF8
        Write-Log "Initialized state baseline (state.json)."
        Trim-Log
        exit 0
    }

    $neuralInstalled = Test-Path (Join-Path $rimeDir "neural")
    $needRepo   = $Force -or ($remoteRepoSha -ne $state.repo_sha)
    $needNeural = $neuralInstalled -and [bool]$neuralAsset -and ($Force -or ($remoteNeuralTag -ne $state.neural_tag))
    $needGram   = $false
    if ($Force) {
        $needGram = [bool]$gramAsset
    } elseif ($remoteGramSha) {
        $needGram = ($remoteGramSha -ne $localGramSha)
    } elseif ($remoteGramMeta) {
        $needGram = ($remoteGramMeta -ne $state.gram_meta)
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
        $state | ConvertTo-Json | Set-Content -Path $stateFile -Encoding UTF8
        Trim-Log
        exit 0
    }

    $stage = Join-Path $env:TEMP ("rime-chth1z-update-" + (Get-Date -Format "yyyyMMddHHmmss"))
    New-Item -ItemType Directory -Force -Path $stage | Out-Null

    try {
        # 2. Prepare repo source
        $deploySource = $null
        if ($needRepo) {
            $usedLocalGit = $false
            if ((Test-Path (Join-Path $RepoDir ".git")) -and (Get-Command git -ErrorAction SilentlyContinue)) {
                $branch = (& git -C $RepoDir rev-parse --abbrev-ref HEAD 2>$null).Trim()
                $dirty  = (& git -C $RepoDir status --porcelain 2>$null)
                if ($branch -eq "main" -and -not $dirty) {
                    Write-Log "Fast-forwarding clean local repo at $RepoDir..."
                    & git -C $RepoDir pull --ff-only origin main 2>&1 | Out-Null
                    if ($LASTEXITCODE -eq 0) {
                        $headSha = (& git -C $RepoDir rev-parse HEAD 2>$null).Trim()
                        if ($headSha -eq $remoteRepoSha) {
                            $deploySource = $RepoDir
                            $usedLocalGit = $true
                            Write-Log "Local repo updated cleanly to $($headSha.Substring(0,8))."
                        }
                    }
                } else {
                    Write-Log "Local repo has branch='$branch' or uncommitted changes; using isolated zip download."
                }
            }

            if (-not $usedLocalGit) {
                Write-Log "Downloading Chth1z/rime-chth1z (main @ $($remoteRepoSha.Substring(0,8)))..."
                $repoZip = Join-Path $stage "rime-chth1z.zip"
                Invoke-CurlDownload "https://github.com/Chth1z/rime-chth1z/archive/refs/heads/main.zip" $repoZip
                $repoEx = Join-Path $stage "repo"
                Expand-Archive -Path $repoZip -DestinationPath $repoEx -Force
                $deploySource = (Get-ChildItem $repoEx -Directory | Select-Object -First 1).FullName
                if (-not $deploySource -or -not (Test-Path (Join-Path $deploySource "rime_frost_double_pinyin.schema.yaml"))) {
                    throw "Downloaded archive structure invalid; aborting update."
                }
                Write-Log "Archive verified."
            }
        }

        # 2b. Prepare rime-neural official release bundle (DLL + Lua + SHA-256)
        $neuralStageDll = $null
        $neuralStageLua = $null
        if ($needNeural) {
            Write-Log "Downloading Chth1z/rime-neural $remoteNeuralTag ($($neuralAsset.name))..."
            $nZip = Join-Path $stage $neuralAsset.name
            Invoke-CurlDownload $neuralAsset.browser_download_url $nZip
            $nEx = Join-Path $stage "neural"
            Expand-Archive -Path $nZip -DestinationPath $nEx -Force
            $dll = Join-Path $nEx "rime_neural.dll"
            $lua = Join-Path $nEx "rime_neural.lua"
            $sum = Join-Path $nEx "SHA256SUMS.txt"
            if (-not (Test-Path $dll) -or -not (Test-Path $lua)) {
                throw "rime-neural release bundle missing DLL or Lua script."
            }
            if (Test-Path $sum) {
                $expDll = (Get-Content $sum | Where-Object { $_ -match 'rime_neural\.dll$' } | Select-Object -First 1) -split '\s+' | Select-Object -First 1
                if ($expDll) {
                    $gotDll = (Get-FileHash $dll -Algorithm SHA256).Hash.ToLowerInvariant()
                    if ($gotDll -ne $expDll.ToLowerInvariant()) {
                        throw "rime_neural.dll SHA-256 mismatch (got=$gotDll, expected=$expDll)"
                    }
                }
            }
            $neuralStageDll = $dll
            $neuralStageLua = $lua
            Write-Log "rime-neural $remoteNeuralTag verified."
        }

        # 2c. Prepare Wanxiang LTS .gram
        $newGramPath = $null
        $dlGramHash  = ""
        if ($needGram) {
            Write-Log "Downloading Wanxiang LTS model ($($gramAsset.browser_download_url))..."
            $newGramPath = Join-Path $stage "wanxiang-lts-zh-hans.gram"
            Invoke-CurlDownload $gramAsset.browser_download_url $newGramPath
            $dlGramHash = (Get-FileHash $newGramPath -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($remoteGramSha -and ($dlGramHash -ne $remoteGramSha)) {
                throw "Wanxiang model SHA-256 mismatch (got=$dlGramHash, expected=$remoteGramSha)"
            }
            Write-Log "Wanxiang LTS model verified ($($dlGramHash.Substring(0,12))...)."
        }

        # 3. Stop WeaselServer cleanly
        $weaselDir = Get-WeaselDir
        if (-not $weaselDir) { throw "Weasel install directory not found." }
        $serverExe   = Join-Path $weaselDir "WeaselServer.exe"
        $deployerExe = Join-Path $weaselDir "WeaselDeployer.exe"

        $wasRunning = [bool](Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue)
        if ($wasRunning) {
            & $serverExe /q 2>$null
            for ($i = 0; $i -lt 20; $i++) {
                if (-not (Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue)) { break }
                Start-Sleep -Milliseconds 300
            }
            Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        }

        # 4. Apply updates
        if ($needRepo -and $deploySource) {
            Write-Log "Syncing files from $deploySource -> $rimeDir..."
            Sync-RepoToRime -SourceRoot $deploySource -TargetRimeDir $rimeDir -ThemeName $Theme
        }

        if ($needNeural -and $neuralStageDll -and $neuralStageLua) {
            Write-Log "Installing rime-neural $remoteNeuralTag..."
            Copy-Item $neuralStageDll (Join-Path $rimeDir "neural\rime_neural.dll") -Force
            Copy-Item $neuralStageLua (Join-Path $rimeDir "lua\rime_neural.lua") -Force
        }

        if ($needGram -and $newGramPath) {
            Write-Log "Atomically replacing Wanxiang LTS model..."
            $tmpTarget = "$localGramPath.new"
            Copy-Item -Path $newGramPath -Destination $tmpTarget -Force
            Move-Item -Path $tmpTarget -Destination $localGramPath -Force
        }

        # 5. Deploy & ensure single WeaselServer
        Write-Log "Running WeaselDeployer /deploy..."
        $pDep = Start-Process -FilePath $deployerExe -ArgumentList "/deploy" -Wait -PassThru
        Write-Log "Deploy finished (ExitCode=$($pDep.ExitCode))"
        if ($pDep.ExitCode -ne 0) {
            throw "WeaselDeployer failed (ExitCode=$($pDep.ExitCode)); keeping previous state for retry."
        }

        Start-Sleep -Milliseconds 400
        if ($wasRunning -and -not (Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue)) {
            Start-Process -FilePath $serverExe
            Write-Log "Restarted WeaselServer.exe."
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
        $state | ConvertTo-Json | Set-Content -Path $stateFile -Encoding UTF8
        Write-Log "=== Update completed ==="
    }
    finally {
        if (Test-Path $stage) { Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue }
        $leftoverTmp = "$localGramPath.new"
        if (Test-Path $leftoverTmp) { Remove-Item $leftoverTmp -Force -ErrorAction SilentlyContinue }
    }
}
catch {
    Write-Log "[ERROR] Update exception: $_"
    $weaselDir = Get-WeaselDir
    if ($weaselDir -and -not (Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue)) {
        Start-Process -FilePath (Join-Path $weaselDir "WeaselServer.exe")
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
