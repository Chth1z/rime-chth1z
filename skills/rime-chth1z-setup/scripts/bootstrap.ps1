<#
.SYNOPSIS
    End-to-end installer and configurator for the full Chth1z/rime-chth1z stack on Windows Weasel.
.DESCRIPTION
    Orchestrates:
      1. Optional official Weasel Nightly (>= 0.17.4, librime >= 1.17.0 with Lua 5.4 exports) install.
      2. Timestamped backup of pre-existing Rime user YAML/Lua files (always preserving *.userdb,
         custom_phrase.txt, installation.yaml, user.yaml, and neural/feedback.jsonl).
      3. Syncing Chth1z/rime-chth1z (local clone, fresh git clone, or GitHub zip archive).
      4. Downloading and SHA-256-verifying wanxiang-lts-zh-hans.gram (~373 MB) from amzxyz/rime-wanxiang-data.
      5. Installing official Chth1z/rime-neural Release + ONNX Runtime + verified Apache-2.0 model (or pure stat mode).
      6. Optional Noto Sans CJK TC Super OTC font install (or Microsoft YaHei UI font fallback).
      7. Optional weekly auto-update Windows Scheduled Task (RimeChth1zWeeklyUpdate).
      8. Full WeaselDeployer /deploy, deploy log verification, and WMI-detached single WeaselServer launch.
#>
[CmdletBinding()]
param(
    [string]$RimeDir = "",
    [string]$RepoDir = "",
    [switch]$NoGitClone,
    [ValidateSet("pumpkin", "feather", "none")]
    [string]$NeuralModel = "pumpkin",
    [ValidateSet("zrm", "full")]
    [string]$PrimaryLayout = "zrm",
    [switch]$SkipGram,
    [switch]$InstallWeasel,
    [ValidateSet("apple_graphite_dark", "keep")]
    [string]$Theme = "apple_graphite_dark",
    [switch]$InstallNotoFont,
    [switch]$UseFallbackFont,
    [switch]$RegisterWeeklyTask,
    [switch]$SkipBackup,
    [switch]$ForceRedownload,
    [switch]$RunAccuracyTest
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
$headers = @{ "User-Agent" = "RimeChth1zSetup/1.1" }
$ghToken = if ($env:GITHUB_TOKEN) { $env:GITHUB_TOKEN } elseif ($env:GH_TOKEN) { $env:GH_TOKEN } else { "" }
if ($ghToken) { $headers["Authorization"] = "Bearer $ghToken" }

function Invoke-NativeSafe {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgumentList = @()
    )
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $FilePath @ArgumentList 2>&1
        $code = $LASTEXITCODE
        return [pscustomobject]@{
            ExitCode = if ($null -eq $code) { 0 } else { [int]$code }
            Output   = @($output | ForEach-Object { [string]$_ })
        }
    }
    finally {
        $ErrorActionPreference = $prev
    }
}

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

function Get-RimeUserDir {
    $regDir = (Get-ItemProperty -Path "HKCU:\SOFTWARE\Rime\Weasel" -Name "RimeUserDir" -ErrorAction SilentlyContinue).RimeUserDir
    if ($regDir -and $regDir.Trim()) {
        return $regDir.Trim()
    }
    return (Join-Path $env:APPDATA "Rime")
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

function Test-IsAdmin {
    try {
        $id = [Security.Principal.WindowsIdentity]::GetCurrent()
        $pr = New-Object Security.Principal.WindowsPrincipal($id)
        return $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch {
        return $false
    }
}

function Stop-WeaselServerClean([string]$WeaselDirPath) {
    if (-not (Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)) { return }
    if ($WeaselDirPath) {
        $exe = Join-Path $WeaselDirPath "WeaselServer.exe"
        if (Test-Path $exe) { [void](Invoke-NativeSafe -FilePath $exe -ArgumentList @("/q")) }
    }
    for ($i = 0; $i -lt 20; $i++) {
        if (-not (Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)) { return }
        Start-Sleep -Milliseconds 250
    }
    Get-Process -Name WeaselServer -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    for ($i = 0; $i -lt 15; $i++) {
        if (-not (Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 200
    }
}

function Invoke-CurlDownload([string]$Url, [string]$OutFile) {
    & curl.exe -fSL --retry 3 --connect-timeout 25 -o $OutFile $Url
    if ($LASTEXITCODE -ne 0) { throw "Download failed (ExitCode=$LASTEXITCODE): $Url" }
    if (-not (Test-Path $OutFile) -or (Get-Item $OutFile).Length -eq 0) {
        throw "Downloaded file missing or empty: $OutFile"
    }
}

if (-not [Environment]::Is64BitOperatingSystem) {
    throw "Windows 64-bit (x64) is required."
}

$stage = Join-Path $env:TEMP ("rime-chth1z-bootstrap-" + (Get-Date -Format "yyyyMMddHHmmss"))
New-Item -ItemType Directory -Force -Path $stage | Out-Null

try {
    # 1. Verify or install official Weasel Nightly (>= 0.17.4 with Lua 5.4 exports)
    $weaselDir = Get-WeaselDir
    $luaOk     = if ($weaselDir) { Test-RimeDllExportsLua54 (Join-Path $weaselDir "rime.dll") } else { $false }

    if ($InstallWeasel -and ((-not $weaselDir) -or (-not $luaOk))) {
        Write-Output "[1/7] Fetching latest official Weasel Nightly installer (rime/weasel releases/tags/latest)..."
        $wRel = Invoke-RestMethod "https://api.github.com/repos/rime/weasel/releases/tags/latest" -Headers $headers -TimeoutSec 25
        $wAsset = $wRel.assets | Where-Object { $_.name -match 'installer\.exe$' } | Select-Object -First 1
        if (-not $wAsset) { throw "Could not locate Weasel Nightly installer asset." }
        $installerExe = Join-Path $stage $wAsset.name
        Invoke-CurlDownload $wAsset.browser_download_url $installerExe
        Stop-WeaselServerClean $weaselDir
        Write-Output "Running $($wAsset.name) (approve UAC prompt if requested)..."
        if (Test-IsAdmin) {
            $pW = Start-Process -FilePath $installerExe -ArgumentList "/S" -Wait -PassThru
        } else {
            $pW = Start-Process -FilePath $installerExe -ArgumentList "/S" -Verb RunAs -Wait -PassThru
        }
        if ($pW.ExitCode -ne 0) { throw "Weasel installer exited with code $($pW.ExitCode)." }
        Start-Sleep -Seconds 1
        $weaselDir = Get-WeaselDir
        $luaOk     = if ($weaselDir) { Test-RimeDllExportsLua54 (Join-Path $weaselDir "rime.dll") } else { $false }
    }

    if (-not $weaselDir) {
        throw "Weasel is not installed. Re-run with -InstallWeasel or install official Weasel Nightly 0.17.4+ from https://github.com/rime/weasel/releases."
    }
    if (($NeuralModel -ne "none") -and (-not $luaOk)) {
        throw "Installed Weasel ($weaselDir) does not export Lua 5.4 C API (requires official Weasel Nightly >= 0.17.4). Re-run with -InstallWeasel or upgrade Weasel first."
    }
    Write-Output "[1/7] Weasel verified: $weaselDir (Lua54Exports=$luaOk)"

    # 2. Resolve RimeUserDir & back up pre-existing config safely
    if (-not $RimeDir) { $RimeDir = Get-RimeUserDir }
    New-Item -ItemType Directory -Force -Path $RimeDir | Out-Null

    $backupDir = $null
    if (-not $SkipBackup) {
        $existingFiles = @(Get-ChildItem $RimeDir -File -Filter "*.yaml" -ErrorAction SilentlyContinue)
        $existingLua   = Test-Path (Join-Path $RimeDir "lua")
        if ($existingFiles.Count -gt 0 -or $existingLua) {
            $backupDir = Join-Path $RimeDir ("backup-pre-rime-chth1z-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
            New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
            foreach ($f in $existingFiles) {
                Copy-Item $f.FullName (Join-Path $backupDir $f.Name) -Force
            }
            $rl = Join-Path $RimeDir "rime.lua"
            if (Test-Path $rl) { Copy-Item $rl (Join-Path $backupDir "rime.lua") -Force }
            if ($existingLua) {
                Copy-Item (Join-Path $RimeDir "lua") (Join-Path $backupDir "lua") -Recurse -Force
            }
            Write-Output "[2/7] Backed up existing Rime YAML/Lua files to: $backupDir"
        } else {
            Write-Output "[2/7] Fresh RimeUserDir ($RimeDir); no backup needed."
        }
    } else {
        Write-Output "[2/7] Backup skipped (-SkipBackup)."
    }

    # 3. Acquire or locate Chth1z/rime-chth1z source tree
    $sourceRoot = $null
    $isGitClone = $false
    if ($RepoDir -and (Test-Path (Join-Path $RepoDir "rime_frost_double_pinyin.schema.yaml"))) {
        $sourceRoot = (Resolve-Path $RepoDir).Path
        $isGitClone = Test-Path (Join-Path $sourceRoot ".git")
        Write-Output "[3/7] Using existing local rime-chth1z checkout: $sourceRoot"
    } elseif ((-not $NoGitClone) -and (Get-Command git -ErrorAction SilentlyContinue)) {
        $targetRepo = if ($RepoDir) { $RepoDir } else { Join-Path $env:USERPROFILE "rime-chth1z" }
        if (Test-Path (Join-Path $targetRepo ".git")) {
            $sourceRoot = (Resolve-Path $targetRepo).Path
            $isGitClone = $true
            $dirtyRes = Invoke-NativeSafe -FilePath "git" -ArgumentList @("-C", $sourceRoot, "status", "--porcelain")
            if ($dirtyRes.ExitCode -eq 0 -and $dirtyRes.Output.Count -eq 0) {
                Write-Output "[3/7] Updating clean git checkout at $sourceRoot..."
                $pullRes = Invoke-NativeSafe -FilePath "git" -ArgumentList @("-C", $sourceRoot, "pull", "--ff-only", "--quiet", "origin", "main")
                if ($pullRes.ExitCode -ne 0) {
                    Write-Warning "git pull skipped/failed (ExitCode=$($pullRes.ExitCode)); continuing with existing checkout."
                }
            } else {
                Write-Output "[3/7] Using existing dirty git checkout at $sourceRoot (skipping pull)."
            }
        } else {
            Write-Output "[3/7] Cloning Chth1z/rime-chth1z -> $targetRepo..."
            New-Item -ItemType Directory -Force -Path (Split-Path $targetRepo -Parent) | Out-Null
            & git clone --depth 1 "https://github.com/Chth1z/rime-chth1z.git" $targetRepo
            if ($LASTEXITCODE -ne 0) { throw "git clone failed for Chth1z/rime-chth1z." }
            $sourceRoot = (Resolve-Path $targetRepo).Path
            $isGitClone = $true
        }
    } else {
        Write-Output "[3/7] Downloading Chth1z/rime-chth1z main archive..."
        $zipPath = Join-Path $stage "rime-chth1z.zip"
        Invoke-CurlDownload "https://github.com/Chth1z/rime-chth1z/archive/refs/heads/main.zip" $zipPath
        $exDir = Join-Path $stage "repo"
        Expand-Archive -Path $zipPath -DestinationPath $exDir -Force
        $sourceRoot = (Get-ChildItem $exDir -Directory | Select-Object -First 1).FullName
        if (-not $sourceRoot -or -not (Test-Path (Join-Path $sourceRoot "rime_frost_double_pinyin.schema.yaml"))) {
            throw "Downloaded rime-chth1z archive structure invalid."
        }
    }

    # 4. Download & SHA-256 verify wanxiang-lts-zh-hans.gram (~373 MB)
    $gramPath = Join-Path $RimeDir "wanxiang-lts-zh-hans.gram"
    if ($SkipGram) {
        Write-Output "[4/7] Wanxiang LTS .gram skipped (-SkipGram)."
    } else {
        $needGram = $ForceRedownload -or (-not (Test-Path $gramPath)) -or ((Get-Item $gramPath).Length -lt 100MB)
        if ($needGram) {
            Write-Output "[4/7] Downloading wanxiang-lts-zh-hans.gram from amzxyz/rime-wanxiang-data (LTS)..."
            $wxRel   = Invoke-RestMethod "https://api.github.com/repos/amzxyz/rime-wanxiang-data/releases/tags/LTS" -Headers $headers -TimeoutSec 25
            $wxAsset = $wxRel.assets | Where-Object { $_.name -eq "wanxiang-lts-zh-hans.gram" } | Select-Object -First 1
            if (-not $wxAsset) { throw "wanxiang-lts-zh-hans.gram asset not found in LTS release." }
            $dlGram  = Join-Path $stage "wanxiang-lts-zh-hans.gram"
            Invoke-CurlDownload $wxAsset.browser_download_url $dlGram
            if ($wxAsset.digest -match '^sha256:([0-9a-fA-F]{64})$') {
                $expSha = $Matches[1].ToLowerInvariant()
                $gotSha = (Get-FileHash $dlGram -Algorithm SHA256).Hash.ToLowerInvariant()
                if ($gotSha -ne $expSha) {
                    throw "wanxiang-lts-zh-hans.gram SHA-256 mismatch (got=$gotSha, expected=$expSha)"
                }
                Write-Output "Wanxiang .gram SHA-256 verified ($($gotSha.Substring(0,12))...)."
            }
            Stop-WeaselServerClean $weaselDir
            Move-Item -Path $dlGram -Destination $gramPath -Force
        } else {
            Write-Output "[4/7] Wanxiang LTS .gram already present ($([math]::Round((Get-Item $gramPath).Length / 1MB, 1)) MB)."
        }
    }

    # 5. Install Chth1z/rime-neural (verified release + ONNX Runtime + model)
    if ($NeuralModel -eq "none") {
        Write-Output "[5/7] rime-neural skipped (-NeuralModel none)."
    } else {
        Write-Output "[5/7] Installing Chth1z/rime-neural (Model=$NeuralModel)..."
        Stop-WeaselServerClean $weaselDir
        $installNeural = Join-Path $sourceRoot "scripts\install-rime-neural.ps1"
        if (Test-Path $installNeural) {
            $nParams = @{ RimeDir = $RimeDir; Model = $NeuralModel }
            if ($ForceRedownload) { $nParams.ForceDownload = $true }
            $global:LASTEXITCODE = 0
            & $installNeural @nParams
            if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "install-rime-neural.ps1 failed (ExitCode=$LASTEXITCODE)" }
        } else {
            $tmpN = Join-Path $stage "install-rime-neural-upstream.ps1"
            Invoke-CurlDownload "https://raw.githubusercontent.com/Chth1z/rime-neural/main/scripts/install.ps1" $tmpN
            $nParams = @{ RimeDir = $RimeDir; Model = $NeuralModel; Prebuilt = $true }
            if ($ForceRedownload) { $nParams.ForceDownload = $true }
            $global:LASTEXITCODE = 0
            & $tmpN @nParams
            if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "rime-neural install.ps1 failed (ExitCode=$LASTEXITCODE)" }
        }
    }

    # 6. Optional Noto Sans CJK TC font installation
    if ($InstallNotoFont) {
        Write-Output "[6/7] Installing Google Noto Sans CJK Super OTC font..."
        $notoUrl = "https://github.com/notofonts/noto-cjk/releases/download/Sans2.004/00_NotoSansCJK.ttc.zip"
        try {
            $nRels = Invoke-RestMethod "https://api.github.com/repos/notofonts/noto-cjk/releases?per_page=8" -Headers $headers -TimeoutSec 20
            $sansRel = $nRels | Where-Object { $_.tag_name -match '^Sans' } | Select-Object -First 1
            if ($sansRel) {
                $a = $sansRel.assets | Where-Object { $_.name -eq "00_NotoSansCJK.ttc.zip" } | Select-Object -First 1
                if ($a) { $notoUrl = $a.browser_download_url }
            }
        } catch {}
        $notoZip = Join-Path $stage "NotoSansCJK.zip"
        Invoke-CurlDownload $notoUrl $notoZip
        $notoEx = Join-Path $stage "noto"
        Expand-Archive -Path $notoZip -DestinationPath $notoEx -Force
        $ttc = Get-ChildItem $notoEx -Recurse -Filter "NotoSansCJK*.ttc" | Select-Object -First 1
        if (-not $ttc) { throw "NotoSansCJK.ttc not found inside downloaded archive." }

        if (Test-IsAdmin) {
            $dstFont = "C:\Windows\Fonts\NotoSansCJK.ttc"
            Copy-Item $ttc.FullName $dstFont -Force
            Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts" -Name "Noto Sans CJK (TrueType)" -Value "NotoSansCJK.ttc"
        } else {
            $userFontDir = Join-Path $env:LOCALAPPDATA "Microsoft\Windows\Fonts"
            New-Item -ItemType Directory -Force -Path $userFontDir | Out-Null
            $dstFont = Join-Path $userFontDir "NotoSansCJK.ttc"
            Copy-Item $ttc.FullName $dstFont -Force
            $regFonts = "HKCU:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
            if (-not (Test-Path $regFonts)) { New-Item -Path $regFonts -Force | Out-Null }
            Set-ItemProperty -Path $regFonts -Name "Noto Sans CJK (TrueType)" -Value $dstFont
        }
        try {
            Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class Win32FontNotify {
    [DllImport("gdi32.dll", CharSet = CharSet.Unicode)]
    public static extern int AddFontResourceW(string lpszFilename);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr SendMessageTimeoutW(IntPtr hWnd, uint Msg, UIntPtr wParam, IntPtr lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);
}
"@ -ErrorAction SilentlyContinue
            [void][Win32FontNotify]::AddFontResourceW($dstFont)
            $res = [UIntPtr]::Zero
            [void][Win32FontNotify]::SendMessageTimeoutW([IntPtr]0xFFFF, 0x001D, [UIntPtr]::Zero, [IntPtr]::Zero, 2, 1000, [ref]$res)
        } catch {}
        Write-Output "Installed Noto Sans CJK font -> $dstFont"
    } else {
        Write-Output "[6/7] Noto Sans CJK font download not requested."
    }

    # 7. Sync rime-chth1z files, apply optional overrides (UTF-8 no-BOM), build schemas & restart detached WeaselServer
    Write-Output "[7/7] Deploying rime-chth1z to $RimeDir..."
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $deployScript = Join-Path $sourceRoot "scripts\deploy-local.ps1"
    $global:LASTEXITCODE = 0
    & $deployScript -Theme $Theme -RimeDir $RimeDir -SkipDeploy
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "deploy-local.ps1 file sync failed (ExitCode=$LASTEXITCODE)" }

    # Primary layout override (reset previously generated default.custom.yaml when switching back to zrm)
    $defaultCustomPath = Join-Path $RimeDir "default.custom.yaml"
    if ($PrimaryLayout -eq "full") {
        $fullDefaultPatch = @(
            "# Generated by rime-chth1z-setup (-PrimaryLayout full): Full Pinyin first, Natural Double Pinyin second",
            "patch:",
            "  schema_list:",
            "    - schema: rime_frost",
            "    - schema: rime_frost_double_pinyin"
        ) -join "`n"
        [System.IO.File]::WriteAllText($defaultCustomPath, $fullDefaultPatch + "`n", $utf8NoBom)
    } elseif (Test-Path $defaultCustomPath) {
        $prevDef = [System.IO.File]::ReadAllText($defaultCustomPath, [System.Text.Encoding]::UTF8)
        if ($prevDef.StartsWith("# Generated by rime-chth1z-setup")) {
            [System.IO.File]::WriteAllText($defaultCustomPath, "# Generated by rime-chth1z-setup (-PrimaryLayout zrm)`npatch: {}`n", $utf8NoBom)
        }
    }

    # Merge schema-level optional patches (-NeuralModel none and/or -SkipGram) into *.custom.yaml
    # Also reset stale bootstrap-generated *.custom.yaml when re-enabling neural/.gram defaults.
    $schemaPatchLines = [System.Collections.Generic.List[string]]::new()
    $schemaPatchLines.Add("# Generated by rime-chth1z-setup")
    $schemaPatchLines.Add("patch:")
    $hasSchemaPatch = $false
    if ($NeuralModel -eq "none") {
        $hasSchemaPatch = $true
        $schemaPatchLines.Add("  engine/filters:")
        $schemaPatchLines.Add("    - lua_filter@*chth1z_pipeline_filter")
        $schemaPatchLines.Add("    - simplifier@emoji")
        $schemaPatchLines.Add("    - simplifier@chinese_english")
        $schemaPatchLines.Add("    - lua_filter@*tw_dual_filter")
        $schemaPatchLines.Add("    - uniquifier")
    }
    if ($SkipGram) {
        $hasSchemaPatch = $true
        $schemaPatchLines.Add("  grammar: {}")
    }
    foreach ($scName in @("rime_frost.custom.yaml", "rime_frost_double_pinyin.custom.yaml")) {
        $scPath = Join-Path $RimeDir $scName
        if ($hasSchemaPatch) {
            $patchText = ($schemaPatchLines -join "`n") + "`n"
            [System.IO.File]::WriteAllText($scPath, $patchText, $utf8NoBom)
        } elseif (Test-Path $scPath) {
            $prevSc = [System.IO.File]::ReadAllText($scPath, [System.Text.Encoding]::UTF8)
            if ($prevSc.StartsWith("# Generated by rime-chth1z-setup")) {
                [System.IO.File]::WriteAllText($scPath, "# Generated by rime-chth1z-setup (defaults active)`npatch: {}`n", $utf8NoBom)
            }
        }
    }

    # If user requested fallback font (without Noto Sans CJK TC)
    if ($UseFallbackFont -and ($Theme -ne "keep")) {
        $weaselCustom = Join-Path $RimeDir "weasel.custom.yaml"
        if (Test-Path $weaselCustom) {
            $raw = [System.IO.File]::ReadAllText($weaselCustom, [System.Text.Encoding]::UTF8)
            $raw = $raw -replace 'Noto Sans CJK TC:medium', 'Microsoft YaHei UI'
            $raw = $raw -replace 'Noto Sans CJK TC', 'Microsoft YaHei UI'
            [System.IO.File]::WriteAllText($weaselCustom, $raw, $utf8NoBom)
        }
    }

    # Run a single clean WeaselDeployer /deploy and verify deploy log + detached single WeaselServer
    Stop-WeaselServerClean $weaselDir
    $deployStart = Get-Date
    $pDep = Start-Process -FilePath (Join-Path $weaselDir "WeaselDeployer.exe") -ArgumentList "/deploy" -Wait -PassThru
    Write-Output "WeaselDeployer ExitCode: $($pDep.ExitCode)"
    if ($pDep.ExitCode -ne 0) { throw "WeaselDeployer /deploy failed (ExitCode=$($pDep.ExitCode))" }

    $weaselLogDir = Join-Path $env:TEMP "rime.weasel"
    if (Test-Path $weaselLogDir) {
        $recentInfos = @(Get-ChildItem $weaselLogDir -Filter "rime.weasel*.INFO*" -File -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -ge $deployStart.AddSeconds(-2) } |
            Sort-Object LastWriteTime -Descending | Select-Object -First 4)
        foreach ($infoLog in $recentInfos) {
            $infoLines = Get-Content $infoLog.FullName -Encoding UTF8 -ErrorAction SilentlyContinue
            $summaryLine = $infoLines | Where-Object { $_ -match 'finished updating schemas:' } | Select-Object -Last 1
            if ($summaryLine) {
                Write-Output "Deploy log ($($infoLog.Name)): $summaryLine"
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
            Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = "`"$(Join-Path $weaselDir 'WeaselServer.exe')`"" } | Out-Null
        } catch {
            Start-Process -FilePath (Join-Path $weaselDir "WeaselServer.exe")
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

    # Optional: register weekly auto-update Scheduled Task (no admin required)
    if ($RegisterWeeklyTask) {
        $updaterPath = Join-Path $RimeDir "auto_update\Update-RimeChth1z.ps1"
        if (Test-Path $updaterPath) {
            $initParams = @{ InitOnly = $true; RimeDir = $RimeDir }
            if ($isGitClone) { $initParams.RepoDir = $sourceRoot }
            try { & $updaterPath @initParams | Out-Null } catch { Write-Warning "InitOnly state seed warning: $_" }

            $argParts = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", "`"$updaterPath`"", "-RimeDir", "`"$RimeDir`"")
            if ($isGitClone) { $argParts += @("-RepoDir", "`"$sourceRoot`"") }
            if ($Theme -eq "keep" -or $UseFallbackFont) { $argParts += @("-Theme", "keep") }
            if ($SkipGram) { $argParts += @("-SkipGram") }
            $action   = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ($argParts -join " ")
            $trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "03:30"
            $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
            Register-ScheduledTask -TaskName "RimeChth1zWeeklyUpdate" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
            Write-Output "Registered weekly scheduled task: RimeChth1zWeeklyUpdate (Sundays 03:30)."
        }
    }

    if ($RunAccuracyTest -and (Test-Path (Join-Path $sourceRoot "bench\accuracy-test.ps1"))) {
        Write-Output "Running regression suite (bench\accuracy-test.ps1)..."
        $global:LASTEXITCODE = 0
        if ($NeuralModel -ne "none") {
            & (Join-Path $sourceRoot "bench\accuracy-test.ps1") -RimeDir $RimeDir -WaitNeural
        } else {
            & (Join-Path $sourceRoot "bench\accuracy-test.ps1") -RimeDir $RimeDir
        }
        if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "bench\accuracy-test.ps1 failed (ExitCode=$LASTEXITCODE)" }
    }

    Write-Output "=== BOOTSTRAP COMPLETE ==="
    Write-Output ("Summary: RimeDir={0} | Source={1} | Neural={2} | Gram={3} | Backup={4}" -f `
        $RimeDir, $sourceRoot, $NeuralModel, (-not $SkipGram), $(if ($backupDir) { $backupDir } else { "none" }))
}
finally {
    if (Test-Path $stage) { Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue }
}
exit 0
