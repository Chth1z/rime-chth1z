<#
.SYNOPSIS
    Install or upgrade official Chth1z/rime-neural release into Rime user directory.
.DESCRIPTION
    Downloads the official GitHub Release bundle (rime_neural.dll + lua/rime_neural.lua + SHA-256),
    verifies hashes, ensures the Apache-2.0 ONNX model (ML-pumpkin-1103 or zhen-feather) and
    onnxruntime.dll are installed in <RimeUserDir>\neural\, and restarts WeaselServer cleanly.
#>
param(
    [string]$RimeDir = "",
    [ValidateSet("pumpkin", "feather")]
    [string]$Model = "pumpkin",
    [string]$ReleaseTag = "",
    [string]$LocalModelArchive = "",
    [switch]$ForceDownload
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch {}

. (Join-Path $PSScriptRoot "_common.ps1")

if (-not $RimeDir) {
    $RimeDir = Get-RimeUserDir
}

$repoRoot       = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$localInstaller = Join-Path (Split-Path $repoRoot -Parent) "rime-neural\scripts\install.ps1"

$params = @{
    RimeDir  = $RimeDir
    Model    = $Model
    Prebuilt = $true
}
if ($ReleaseTag)        { $params.ReleaseTag        = $ReleaseTag }
if ($LocalModelArchive) { $params.LocalModelArchive = $LocalModelArchive }
if ($ForceDownload)     { $params.ForceDownload     = $true }

if (Test-Path -LiteralPath $localInstaller) {
    Write-Output "[INFO] Using local sibling rime-neural installer: $localInstaller"
    $global:LASTEXITCODE = 0
    & $localInstaller @params
    $rc = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
    exit $rc
}

$tmpScript = Join-Path $env:TEMP ("rime-neural-install-" + (Get-Date -Format "yyyyMMddHHmmss") + "-" + ([guid]::NewGuid().ToString("N").Substring(0, 8)) + ".ps1")
$rc = 0
try {
    # Always fetch the latest hardened installer from main; -ReleaseTag selects the target release asset.
    $url = "https://raw.githubusercontent.com/Chth1z/rime-neural/main/scripts/install.ps1"
    Write-Output "Downloading official rime-neural installer from $url..."
    $dl = Invoke-NativeSafe { & curl.exe -fsSL --retry 3 --connect-timeout 20 -o $tmpScript $url }
    if ($dl.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $tmpScript) -or (Get-Item -LiteralPath $tmpScript).Length -eq 0) {
        $tail = ($dl.Output | Select-Object -Last 8) -join " | "
        throw "Failed to download rime-neural installer (ExitCode=$($dl.ExitCode)): $tail"
    }
    $global:LASTEXITCODE = 0
    & $tmpScript @params
    $rc = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
}
finally {
    if (Test-Path -LiteralPath $tmpScript) { Remove-Item -LiteralPath $tmpScript -Force -ErrorAction SilentlyContinue }
}
exit $rc
