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
$headers = @{ "User-Agent" = "RimeChth1zSetup/1.0" }

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
        if (Test-Path $exe) { & $exe /q 2>$null }
    }
    for ($i = 0; $i -lt 20; $i++) {
        if (-not (Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 250
    }
    Get-Process -Name WeaselServer -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
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
            $dirty = & git -C $sourceRoot status --porcelain 2>$null
            if (-not $dirty) {
                Write-Output "[3/7] Updating clean git checkout at $sourceRoot..."
                & git -C $sourceRoot pull --ff-only origin main 2>&1 | Out-Null
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
            & $installNeural @nParams
            if ($LASTEXITCODE -ne 0) { throw "install-rime-neural.ps1 failed (ExitCode=$LASTEXITCODE)" }
        } else {
            $tmpN = Join-Path $stage "install-rime-neural-upstream.ps1"
            Invoke-CurlDownload "https://raw.githubusercontent.com/Chth1z/rime-neural/main/scripts/install.ps1" $tmpN
            $nParams = @{ RimeDir = $RimeDir; Model = $NeuralModel; Prebuilt = $true }
            if ($ForceRedownload) { $nParams.ForceDownload = $true }
            & $tmpN @nParams
            if ($LASTEXITCODE -ne 0) { throw "rime-neural install.ps1 failed (ExitCode=$LASTEXITCODE)" }
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

    # 7. Deploy rime-chth1z files, apply optional overrides, build schemas & restart detached WeaselServer
    Write-Output "[7/7] Deploying rime-chth1z to $RimeDir..."
    $deployScript = Join-Path $sourceRoot "scripts\deploy-local.ps1"
    $deployTheme  = if ($Theme -eq "keep") { "__keep_existing__" } else { $Theme }
    & $deployScript -Theme $deployTheme -RimeDir $RimeDir
    if ($LASTEXITCODE -ne 0) { throw "deploy-local.ps1 failed (ExitCode=$LASTEXITCODE)" }

    $needRedeploy = $false

    # If user chose pure statistical mode (-NeuralModel none), disable lua_filter@*rime_neural cleanly via *.custom.yaml
    if ($NeuralModel -eq "none") {
        $statPatch = @"
# Generated by rime-chth1z-setup (-NeuralModel none): pure statistical mode without lua_filter@*rime_neural
patch:
  engine/filters:
    - lua_filter@*chth1z_pipeline_filter
    - simplifier@emoji
    - simplifier@chinese_english
    - lua_filter@*tw_dual_filter
    - uniquifier
"@
        Set-Content -Path (Join-Path $RimeDir "rime_frost.custom.yaml") -Value $statPatch -Encoding UTF8
        Set-Content -Path (Join-Path $RimeDir "rime_frost_double_pinyin.custom.yaml") -Value $statPatch -Encoding UTF8
        $needRedeploy = $true
    }

    # If user requested fallback font (without Noto Sans CJK TC)
    if ($UseFallbackFont -and ($Theme -ne "keep")) {
        $weaselCustom = Join-Path $RimeDir "weasel.custom.yaml"
        if (Test-Path $weaselCustom) {
            $raw = Get-Content $weaselCustom -Raw -Encoding UTF8
            $raw = $raw -replace 'Noto Sans CJK TC:medium', 'Microsoft YaHei UI'
            $raw = $raw -replace 'Noto Sans CJK TC', 'Microsoft YaHei UI'
            Set-Content -Path $weaselCustom -Value $raw -Encoding UTF8
            $needRedeploy = $true
        }
    }

    if ($needRedeploy) {
        Stop-WeaselServerClean $weaselDir
        $pRe = Start-Process -FilePath (Join-Path $weaselDir "WeaselDeployer.exe") -ArgumentList "/deploy" -Wait -PassThru
        if ($pRe.ExitCode -ne 0) { throw "Secondary WeaselDeployer /deploy failed (ExitCode=$($pRe.ExitCode))" }
        Start-Sleep -Milliseconds 400
        if (-not (Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)) {
            Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = "`"$(Join-Path $weaselDir 'WeaselServer.exe')`"" } | Out-Null
            Start-Sleep -Milliseconds 600
        }
    }

    # Optional: register weekly auto-update Scheduled Task (no admin required)
    if ($RegisterWeeklyTask) {
        $updaterPath = Join-Path $RimeDir "auto_update\Update-RimeChth1z.ps1"
        if (Test-Path $updaterPath) {
            $initParams = @{ InitOnly = $true; RimeDir = $RimeDir }
            if ($isGitClone) { $initParams.RepoDir = $sourceRoot }
            try { & $updaterPath @initParams | Out-Null } catch { Write-Warning "InitOnly state seed warning: $_" }

            $argParts = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", "`"$updaterPath`"", "-RimeDir", "`"$RimeDir`"")
            if ($isGitClone) { $argParts += @("-RepoDir", "`"$sourceRoot`"") }
            $action   = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ($argParts -join " ")
            $trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "03:30"
            $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
            Register-ScheduledTask -TaskName "RimeChth1zWeeklyUpdate" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
            Write-Output "Registered weekly scheduled task: RimeChth1zWeeklyUpdate (Sundays 03:30)."
        }
    }

    if ($RunAccuracyTest -and (Test-Path (Join-Path $sourceRoot "bench\accuracy-test.ps1"))) {
        Write-Output "Running regression suite (bench\accuracy-test.ps1)..."
        if ($NeuralModel -ne "none") {
            & (Join-Path $sourceRoot "bench\accuracy-test.ps1") -WaitNeural
        } else {
            & (Join-Path $sourceRoot "bench\accuracy-test.ps1")
        }
        if ($LASTEXITCODE -ne 0) { throw "bench\accuracy-test.ps1 failed (ExitCode=$LASTEXITCODE)" }
    }

    Write-Output "=== BOOTSTRAP COMPLETE ==="
    Write-Output ("Summary: RimeDir={0} | Source={1} | Neural={2} | Gram={3} | Backup={4}" -f `
        $RimeDir, $sourceRoot, $NeuralModel, (-not $SkipGram), $(if ($backupDir) { $backupDir } else { "none" }))
}
finally {
    if (Test-Path $stage) { Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue }
}
