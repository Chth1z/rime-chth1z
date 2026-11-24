<#
.SYNOPSIS
    End-to-end installer and configurator for the full Chth1z/rime-chth1z stack on Windows Weasel.
.DESCRIPTION
    Standalone script (directly downloadable via raw URL). Orchestrates:
      1. Optional official Weasel Nightly (>= 0.17.4, librime >= 1.17.0 with PE32+ Lua 5.4 exports) install
         with fail-closed SHA-256 verification before UAC elevation.
      2. Timestamped backup of pre-existing Rime user YAML/Lua files (always preserving *.userdb,
         custom_phrase.txt, installation.yaml, user.yaml, and neural/feedback.jsonl).
      3. Syncing Chth1z/rime-chth1z (local clone, fresh git clone, or GitHub zip archive).
      4. Downloading and fail-closed SHA-256-verifying wanxiang-lts-zh-hans.gram (~373 MB) from amzxyz/rime-wanxiang-data.
      5. Installing official Chth1z/rime-neural Release + ONNX Runtime + verified Apache-2.0 model (or pure stat mode).
      6. Optional Noto Sans CJK TC Super OTC font install (or Microsoft YaHei UI font fallback).
      7. Optional weekly auto-update Windows Scheduled Task (RimeChth1zWeeklyUpdate).
      8. Full WeaselDeployer /deploy, fresh deploy log verification, and WMI-detached single WeaselServer launch.
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
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch {}

$headers = @{ "User-Agent" = "RimeChth1zSetup/1.2" }
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
        $global:LASTEXITCODE = 0
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
    $proc = Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($proc) {
        try {
            if ($proc.Path) {
                $pdir = Split-Path $proc.Path -Parent
                if ($pdir -and (Test-Path -LiteralPath (Join-Path $pdir "rime.dll"))) {
                    return (Get-Item -LiteralPath $pdir).FullName
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

function Stop-WeaselServerClean([string]$WeaselDirPath) {
    if (-not (Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)) { return }
    if ($WeaselDirPath) {
        $exe = Join-Path $WeaselDirPath "WeaselServer.exe"
        if (Test-Path -LiteralPath $exe) { [void](Invoke-NativeSafe -FilePath $exe -ArgumentList @("/q")) }
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
    $res = Invoke-NativeSafe -FilePath "curl.exe" -ArgumentList @("-fsSL", "--retry", "3", "--connect-timeout", "25", "-o", $OutFile, $Url)
    if ($res.ExitCode -ne 0) {
        $tail = ($res.Output | Select-Object -Last 8) -join " | "
        throw "Download failed (ExitCode=$($res.ExitCode)): $Url ($tail)"
    }
    if (-not (Test-Path -LiteralPath $OutFile) -or (Get-Item -LiteralPath $OutFile).Length -eq 0) {
        throw "Downloaded file missing or empty: $OutFile"
    }
}

function Backup-CustomYamlIfUserOwned([string]$TargetPath) {
    if (-not (Test-Path -LiteralPath $TargetPath)) { return }
    $existing = [System.IO.File]::ReadAllText($TargetPath, [System.Text.Encoding]::UTF8)
    if (-not $existing.StartsWith("# Generated by rime-chth1z-setup")) {
        $bak = "$TargetPath.pre-bootstrap-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".bak"
        Copy-Item -LiteralPath $TargetPath -Destination $bak -Force
        Write-Warning "Preserved pre-existing user custom file at $bak before writing bootstrap patch to $TargetPath."
    }
}

if (-not [Environment]::Is64BitOperatingSystem) {
    throw "Windows 64-bit (x64) is required."
}

$stage = Join-Path $env:TEMP ("rime-chth1z-bootstrap-" + (Get-Date -Format "yyyyMMddHHmmss") + "-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force -Path $stage | Out-Null

try {
    # 1. Verify or install official Weasel Nightly (>= 0.17.4 with PE32+ Lua 5.4 exports)
    $weaselDir = Get-WeaselDir
    $luaOk     = if ($weaselDir) { Test-RimeDllExportsLua54 (Join-Path $weaselDir "rime.dll") } else { $false }

    if ($InstallWeasel -and ((-not $weaselDir) -or (-not $luaOk))) {
        Write-Output "[1/7] Fetching latest official Weasel Nightly installer (rime/weasel releases/tags/latest)..."
        $wRel = Invoke-RestMethod "https://api.github.com/repos/rime/weasel/releases/tags/latest" -Headers $headers -TimeoutSec 25
        $wAsset = $wRel.assets | Where-Object { $_.name -match 'installer\.exe$' } | Select-Object -First 1
        if (-not $wAsset) { throw "Could not locate Weasel Nightly installer asset." }
        if (-not ($wAsset.digest -match '^sha256:([0-9a-fA-F]{64})$')) {
            throw "Weasel Nightly release asset '$($wAsset.name)' missing GitHub SHA-256 digest; refusing unverified admin installer."
        }
        $expWeaselSha = $Matches[1].ToLowerInvariant()
        $installerExe = Join-Path $stage $wAsset.name
        Invoke-CurlDownload $wAsset.browser_download_url $installerExe
        $gotWeaselSha = (Get-FileHash -LiteralPath $installerExe -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($gotWeaselSha -ne $expWeaselSha) {
            throw "Weasel installer SHA-256 mismatch (got=$gotWeaselSha, expected=$expWeaselSha); aborting before elevation."
        }
        Write-Output "Weasel installer SHA-256 verified ($($gotWeaselSha.Substring(0,12))...)."
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
        $existingFiles = @(Get-ChildItem -LiteralPath $RimeDir -File -Filter "*.yaml" -ErrorAction SilentlyContinue)
        $existingLua   = Test-Path -LiteralPath (Join-Path $RimeDir "lua")
        if ($existingFiles.Count -gt 0 -or $existingLua) {
            $backupDir = Join-Path $RimeDir ("backup-pre-rime-chth1z-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
            New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
            foreach ($f in $existingFiles) {
                Copy-Item -LiteralPath $f.FullName -Destination (Join-Path $backupDir $f.Name) -Force
            }
            $rl = Join-Path $RimeDir "rime.lua"
            if (Test-Path -LiteralPath $rl) { Copy-Item -LiteralPath $rl -Destination (Join-Path $backupDir "rime.lua") -Force }
            if ($existingLua) {
                Copy-Item -LiteralPath (Join-Path $RimeDir "lua") -Destination (Join-Path $backupDir "lua") -Recurse -Force
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
    if ($RepoDir -and (Test-Path -LiteralPath (Join-Path $RepoDir "rime_frost_double_pinyin.schema.yaml"))) {
        $sourceRoot = (Resolve-Path -LiteralPath $RepoDir).Path
        $isGitClone = Test-Path -LiteralPath (Join-Path $sourceRoot ".git")
        Write-Output "[3/7] Using existing local rime-chth1z checkout: $sourceRoot"
    } elseif ((-not $NoGitClone) -and (Get-Command git -ErrorAction SilentlyContinue)) {
        $targetRepo = if ($RepoDir) { $RepoDir } else { Join-Path $env:USERPROFILE "rime-chth1z" }
        if (Test-Path -LiteralPath (Join-Path $targetRepo ".git")) {
            $sourceRoot = (Resolve-Path -LiteralPath $targetRepo).Path
            $isGitClone = $true
            $branchRes = Invoke-NativeSafe -FilePath "git" -ArgumentList @("-C", $sourceRoot, "rev-parse", "--abbrev-ref", "HEAD")
            $curBranch = if ($branchRes.ExitCode -eq 0 -and $branchRes.Output.Count -gt 0) { $branchRes.Output[0].Trim() } else { "" }
            $dirtyRes  = Invoke-NativeSafe -FilePath "git" -ArgumentList @("-C", $sourceRoot, "status", "--porcelain")
            $dirtyLines = @($dirtyRes.Output | Where-Object { $_ -and $_.Trim() -ne "" })
            if ($curBranch -eq "main" -and $dirtyRes.ExitCode -eq 0 -and $dirtyLines.Count -eq 0) {
                Write-Output "[3/7] Updating clean git checkout (branch=main) at $sourceRoot..."
                $pullRes = Invoke-NativeSafe -FilePath "git" -ArgumentList @("-C", $sourceRoot, "pull", "--ff-only", "--quiet", "origin", "main")
                if ($pullRes.ExitCode -ne 0) {
                    Write-Warning "git pull skipped/failed (ExitCode=$($pullRes.ExitCode)); continuing with existing checkout."
                }
            } else {
                Write-Output "[3/7] Using existing git checkout at $sourceRoot (branch='$curBranch', dirty=$($dirtyLines.Count); skipping pull)."
            }
        } else {
            Write-Output "[3/7] Cloning Chth1z/rime-chth1z -> $targetRepo..."
            $repoParent = Split-Path $targetRepo -Parent
            if ($repoParent) {
                New-Item -ItemType Directory -Force -Path $repoParent | Out-Null
            }
            $cloneRes = Invoke-NativeSafe -FilePath "git" -ArgumentList @("clone", "--depth", "1", "https://github.com/Chth1z/rime-chth1z.git", $targetRepo)
            if ($cloneRes.ExitCode -ne 0) {
                $tail = ($cloneRes.Output | Select-Object -Last 8) -join " | "
                throw "git clone failed for Chth1z/rime-chth1z (ExitCode=$($cloneRes.ExitCode)): $tail"
            }
            $sourceRoot = (Resolve-Path -LiteralPath $targetRepo).Path
            $isGitClone = $true
        }
    } else {
        Write-Output "[3/7] Downloading Chth1z/rime-chth1z main archive..."
        $zipPath = Join-Path $stage "rime-chth1z.zip"
        Invoke-CurlDownload "https://github.com/Chth1z/rime-chth1z/archive/refs/heads/main.zip" $zipPath
        $exDir = Join-Path $stage "repo"
        Expand-Archive -Path $zipPath -DestinationPath $exDir -Force
        $sourceRoot = (Get-ChildItem -LiteralPath $exDir -Directory | Select-Object -First 1).FullName
        if (-not $sourceRoot -or -not (Test-Path -LiteralPath (Join-Path $sourceRoot "rime_frost_double_pinyin.schema.yaml"))) {
            throw "Downloaded rime-chth1z archive structure invalid."
        }
    }

    # 4. Download & fail-closed SHA-256 verify wanxiang-lts-zh-hans.gram (~373 MB)
    $gramPath = Join-Path $RimeDir "wanxiang-lts-zh-hans.gram"
    if ($SkipGram) {
        Write-Output "[4/7] Wanxiang LTS .gram skipped (-SkipGram)."
    } else {
        $needGram = $ForceRedownload -or (-not (Test-Path -LiteralPath $gramPath)) -or ((Get-Item -LiteralPath $gramPath).Length -lt 100MB)
        if ($needGram) {
            Write-Output "[4/7] Downloading wanxiang-lts-zh-hans.gram from amzxyz/rime-wanxiang-data (LTS)..."
            $wxRel   = Invoke-RestMethod "https://api.github.com/repos/amzxyz/rime-wanxiang-data/releases/tags/LTS" -Headers $headers -TimeoutSec 25
            $wxAsset = $wxRel.assets | Where-Object { $_.name -eq "wanxiang-lts-zh-hans.gram" } | Select-Object -First 1
            if (-not $wxAsset) { throw "wanxiang-lts-zh-hans.gram asset not found in LTS release." }
            if (-not ($wxAsset.digest -match '^sha256:([0-9a-fA-F]{64})$')) {
                throw "wanxiang-lts-zh-hans.gram release asset missing SHA-256 digest; refusing unverified model."
            }
            $expSha = $Matches[1].ToLowerInvariant()
            $dlGram = Join-Path $stage "wanxiang-lts-zh-hans.gram"
            Invoke-CurlDownload $wxAsset.browser_download_url $dlGram
            $gotSha = (Get-FileHash -LiteralPath $dlGram -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($gotSha -ne $expSha) {
                throw "wanxiang-lts-zh-hans.gram SHA-256 mismatch (got=$gotSha, expected=$expSha)"
            }
            Write-Output "Wanxiang .gram SHA-256 verified ($($gotSha.Substring(0,12))...)."
            Stop-WeaselServerClean $weaselDir
            $tmpGram = "$gramPath.new"
            if (Test-Path -LiteralPath $tmpGram) { Remove-Item -LiteralPath $tmpGram -Force }
            $srcRoot = [System.IO.Path]::GetPathRoot($dlGram)
            $dstRoot = [System.IO.Path]::GetPathRoot($tmpGram)
            if ($srcRoot -and $dstRoot -and ($srcRoot.Equals($dstRoot, [System.StringComparison]::OrdinalIgnoreCase))) {
                [System.IO.File]::Move($dlGram, $tmpGram)
            } else {
                Copy-Item -LiteralPath $dlGram -Destination $tmpGram -Force
            }
            if (Test-Path -LiteralPath $gramPath) {
                [System.IO.File]::Replace($tmpGram, $gramPath, $null)
            } else {
                [System.IO.File]::Move($tmpGram, $gramPath)
            }
        } else {
            Write-Output "[4/7] Wanxiang LTS .gram already present ($([math]::Round((Get-Item -LiteralPath $gramPath).Length / 1MB, 1)) MB)."
        }
    }

    # 5. Install Chth1z/rime-neural (verified release + ONNX Runtime + model)
    if ($NeuralModel -eq "none") {
        Write-Output "[5/7] rime-neural skipped (-NeuralModel none)."
    } else {
        Write-Output "[5/7] Installing Chth1z/rime-neural (Model=$NeuralModel)..."
        Stop-WeaselServerClean $weaselDir
        $installNeural = Join-Path $sourceRoot "scripts\install-rime-neural.ps1"
        if (Test-Path -LiteralPath $installNeural) {
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

    # 6. Optional Noto Sans CJK TC font installation (verify GitHub digest when published, else exact asset size)
    if ($InstallNotoFont) {
        Write-Output "[6/7] Installing Google Noto Sans CJK Super OTC font..."
        $notoUrl          = "https://github.com/notofonts/noto-cjk/releases/download/Sans2.004/00_NotoSansCJK.ttc.zip"
        $notoExpectedSha  = ""
        $notoExpectedSize = 95183504L
        try {
            $nRels = Invoke-RestMethod "https://api.github.com/repos/notofonts/noto-cjk/releases?per_page=8" -Headers $headers -TimeoutSec 20
            $sansRel = $nRels | Where-Object { $_.tag_name -match '^Sans' } | Select-Object -First 1
            if ($sansRel) {
                $a = $sansRel.assets | Where-Object { $_.name -eq "00_NotoSansCJK.ttc.zip" } | Select-Object -First 1
                if ($a) {
                    $notoUrl = $a.browser_download_url
                    if ($a.size) { $notoExpectedSize = [int64]$a.size }
                    if ($a.digest -match '^sha256:([0-9a-fA-F]{64})$') {
                        $notoExpectedSha = $Matches[1].ToLowerInvariant()
                    }
                }
            }
        } catch {
            Write-Warning "Could not query notofonts/noto-cjk releases API ($($_.Exception.Message)); falling back to Sans2.004."
        }
        $notoZip = Join-Path $stage "NotoSansCJK.zip"
        Invoke-CurlDownload $notoUrl $notoZip
        $actualNotoSize = (Get-Item -LiteralPath $notoZip).Length
        if ($notoExpectedSha) {
            $gotNotoSha = (Get-FileHash -LiteralPath $notoZip -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($gotNotoSha -ne $notoExpectedSha) {
                throw "NotoSansCJK archive SHA-256 mismatch (got=$gotNotoSha, expected=$notoExpectedSha)"
            }
            Write-Output "NotoSansCJK archive SHA-256 verified ($($gotNotoSha.Substring(0,12))...)."
        } else {
            if ($notoExpectedSize -gt 0 -and $actualNotoSize -ne $notoExpectedSize) {
                throw "NotoSansCJK archive size mismatch (got=$actualNotoSize, expected=$notoExpectedSize)"
            }
            Write-Warning "GitHub release for $notoUrl does not publish a SHA-256 digest; verified exact byte size ($actualNotoSize bytes)."
        }
        $notoEx = Join-Path $stage "noto"
        Expand-Archive -Path $notoZip -DestinationPath $notoEx -Force
        $ttc = Get-ChildItem -LiteralPath $notoEx -Recurse -Filter "NotoSansCJK*.ttc" | Select-Object -First 1
        if (-not $ttc) { throw "NotoSansCJK.ttc not found inside downloaded archive." }

        if (Test-IsAdmin) {
            $dstFont = "C:\Windows\Fonts\NotoSansCJK.ttc"
            Copy-Item -LiteralPath $ttc.FullName -Destination $dstFont -Force
            Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts" -Name "Noto Sans CJK (TrueType)" -Value "NotoSansCJK.ttc"
        } else {
            $userFontDir = Join-Path $env:LOCALAPPDATA "Microsoft\Windows\Fonts"
            New-Item -ItemType Directory -Force -Path $userFontDir | Out-Null
            $dstFont = Join-Path $userFontDir "NotoSansCJK.ttc"
            Copy-Item -LiteralPath $ttc.FullName -Destination $dstFont -Force
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

    # Primary layout override (preserve non-generated user default.custom.yaml via .bak before overwriting)
    $defaultCustomPath = Join-Path $RimeDir "default.custom.yaml"
    if ($PrimaryLayout -eq "full") {
        Backup-CustomYamlIfUserOwned $defaultCustomPath
        $fullDefaultPatch = @(
            "# Generated by rime-chth1z-setup (-PrimaryLayout full): Full Pinyin first, Natural Double Pinyin second",
            "patch:",
            "  schema_list:",
            "    - schema: rime_frost",
            "    - schema: rime_frost_double_pinyin"
        ) -join "`n"
        [System.IO.File]::WriteAllText($defaultCustomPath, $fullDefaultPatch + "`n", $utf8NoBom)
    } elseif (Test-Path -LiteralPath $defaultCustomPath) {
        $prevDef = [System.IO.File]::ReadAllText($defaultCustomPath, [System.Text.Encoding]::UTF8)
        if ($prevDef.StartsWith("# Generated by rime-chth1z-setup")) {
            [System.IO.File]::WriteAllText($defaultCustomPath, "# Generated by rime-chth1z-setup (-PrimaryLayout zrm)`npatch: {}`n", $utf8NoBom)
        }
    }

    # Merge schema-level optional patches (-NeuralModel none and/or -SkipGram) into *.custom.yaml
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
            Backup-CustomYamlIfUserOwned $scPath
            $patchText = ($schemaPatchLines -join "`n") + "`n"
            [System.IO.File]::WriteAllText($scPath, $patchText, $utf8NoBom)
        } elseif (Test-Path -LiteralPath $scPath) {
            $prevSc = [System.IO.File]::ReadAllText($scPath, [System.Text.Encoding]::UTF8)
            if ($prevSc.StartsWith("# Generated by rime-chth1z-setup")) {
                [System.IO.File]::WriteAllText($scPath, "# Generated by rime-chth1z-setup (defaults active)`npatch: {}`n", $utf8NoBom)
            }
        }
    }

    # If user requested fallback font (without Noto Sans CJK TC)
    if ($UseFallbackFont -and ($Theme -ne "keep")) {
        $weaselCustom = Join-Path $RimeDir "weasel.custom.yaml"
        if (Test-Path -LiteralPath $weaselCustom) {
            $raw = [System.IO.File]::ReadAllText($weaselCustom, [System.Text.Encoding]::UTF8)
            $raw = $raw -replace 'Noto Sans CJK TC:medium', 'Microsoft YaHei UI'
            $raw = $raw -replace 'Noto Sans CJK TC', 'Microsoft YaHei UI'
            [System.IO.File]::WriteAllText($weaselCustom, $raw, $utf8NoBom)
        }
    }

    # Run a single clean WeaselDeployer /deploy and verify fresh deploy log + detached single WeaselServer
    Stop-WeaselServerClean $weaselDir
    $weaselLogDir = Join-Path $env:TEMP "rime.weasel"
    $priorLogs = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    if (Test-Path -LiteralPath $weaselLogDir) {
        Get-ChildItem -LiteralPath $weaselLogDir -File -ErrorAction SilentlyContinue | ForEach-Object {
            [void]$priorLogs.Add($_.Name)
        }
    }
    $deployStart = Get-Date
    $pDep = Start-Process -FilePath (Join-Path $weaselDir "WeaselDeployer.exe") -ArgumentList "/deploy" -Wait -PassThru
    Write-Output "WeaselDeployer ExitCode: $($pDep.ExitCode)"
    if ($pDep.ExitCode -ne 0) { throw "WeaselDeployer /deploy failed (ExitCode=$($pDep.ExitCode))" }

    if (Test-Path -LiteralPath $weaselLogDir) {
        $newInfos = @(Get-ChildItem -LiteralPath $weaselLogDir -Filter "rime.weasel*.INFO*" -File -ErrorAction SilentlyContinue |
            Where-Object { (-not $priorLogs.Contains($_.Name)) -or ($_.CreationTime -ge $deployStart.AddSeconds(-2)) } |
            Sort-Object CreationTime -Descending | Select-Object -First 4)
        $foundSummary = $null
        foreach ($infoLog in $newInfos) {
            $infoLines = Get-Content -LiteralPath $infoLog.FullName -Encoding UTF8 -ErrorAction SilentlyContinue
            $summaryLine = $infoLines | Where-Object { $_ -match 'finished updating schemas:' } | Select-Object -Last 1
            if ($summaryLine) {
                $foundSummary = $summaryLine
                Write-Output "Deploy log ($($infoLog.Name)): $summaryLine"
                if ($summaryLine -notmatch '0 failure') {
                    throw "WeaselDeployer reported schema failures: $summaryLine"
                }
            }
            $badLines = @($infoLines | Where-Object { $_ -match '^[EF]\d{4,8}\s' })
            if ($badLines.Count -gt 0) {
                throw "WeaselDeployer logged errors in $($infoLog.Name): $(($badLines | Select-Object -First 3) -join ' | ')"
            }
        }
        if (-not $foundSummary) {
            throw "No new WeaselDeployer INFO log containing 'finished updating schemas:' was found in $weaselLogDir."
        }
    }

    Start-Sleep -Milliseconds 400
    $procs = @(Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)
    if ($procs.Count -eq 0) {
        Start-WeaselDetached (Join-Path $weaselDir "WeaselServer.exe")
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
        if (Test-Path -LiteralPath $updaterPath) {
            $cleanRimeDir = $RimeDir.TrimEnd('\')
            $cleanSrcRoot = $sourceRoot.TrimEnd('\')
            $cleanUpdater = $updaterPath.TrimEnd('\')

            $initArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $cleanUpdater, "-InitOnly", "-RimeDir", $cleanRimeDir)
            if ($isGitClone) { $initArgs += @("-RepoDir", $cleanSrcRoot) }
            if ($SkipGram)   { $initArgs += "-SkipGram" }
            $initRes = Invoke-NativeSafe -FilePath "powershell.exe" -ArgumentList $initArgs
            if ($initRes.ExitCode -ne 0) {
                $tail = ($initRes.Output | Select-Object -Last 5) -join " | "
                Write-Warning "InitOnly state seed failed (ExitCode=$($initRes.ExitCode)): $tail"
            }

            $argParts = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", "`"$cleanUpdater`"", "-RimeDir", "`"$cleanRimeDir`"")
            if ($isGitClone) { $argParts += @("-RepoDir", "`"$cleanSrcRoot`"") }
            if ($Theme -eq "keep" -or $UseFallbackFont) { $argParts += @("-Theme", "keep") }
            if ($SkipGram) { $argParts += @("-SkipGram") }
            $action   = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ($argParts -join " ")
            $trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "03:30"
            $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
            Register-ScheduledTask -TaskName "RimeChth1zWeeklyUpdate" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
            Write-Output "Registered weekly scheduled task: RimeChth1zWeeklyUpdate (Sundays 03:30)."
        }
    }

    if ($RunAccuracyTest -and (Test-Path -LiteralPath (Join-Path $sourceRoot "bench\accuracy-test.ps1"))) {
        Write-Output "Running regression suite (bench\accuracy-test.ps1)..."
        $accScript = Join-Path $sourceRoot "bench\accuracy-test.ps1"
        $accArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $accScript, "-RimeDir", $RimeDir)
        if ($NeuralModel -ne "none") { $accArgs += "-WaitNeural" }
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $global:LASTEXITCODE = 0
            & powershell.exe @accArgs
            $accRc = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
        } finally {
            $ErrorActionPreference = $prevEap
        }
        if ($accRc -ne 0) { throw "bench\accuracy-test.ps1 failed (ExitCode=$accRc)" }
    }

    Write-Output "=== BOOTSTRAP COMPLETE ==="
    Write-Output ("Summary: RimeDir={0} | Source={1} | Neural={2} | Gram={3} | Backup={4}" -f `
        $RimeDir, $sourceRoot, $NeuralModel, (-not $SkipGram), $(if ($backupDir) { $backupDir } else { "none" }))
}
finally {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
    if ($RimeDir) {
        $leftoverTmp = Join-Path $RimeDir "wanxiang-lts-zh-hans.gram.new"
        if (Test-Path -LiteralPath $leftoverTmp) { Remove-Item -LiteralPath $leftoverTmp -Force -ErrorAction SilentlyContinue }
    }
}
exit 0
