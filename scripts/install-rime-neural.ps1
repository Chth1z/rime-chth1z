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
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

if (-not $RimeDir) {
    $regDir = (Get-ItemProperty -Path "HKCU:\SOFTWARE\Rime\Weasel" -Name "RimeUserDir" -ErrorAction SilentlyContinue).RimeUserDir
    $RimeDir = if ($regDir -and $regDir.Trim()) { $regDir.Trim() } else { Join-Path $env:APPDATA "Rime" }
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

if (Test-Path $localInstaller) {
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
    & curl.exe -fSL --retry 3 --connect-timeout 20 -o $tmpScript $url
    if ($LASTEXITCODE -ne 0) { throw "Failed to download rime-neural installer." }
    $global:LASTEXITCODE = 0
    & $tmpScript @params
    $rc = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
}
finally {
    if (Test-Path $tmpScript) { Remove-Item $tmpScript -Force -ErrorAction SilentlyContinue }
}
exit $rc
