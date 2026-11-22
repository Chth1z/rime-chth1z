<#
.SYNOPSIS
    Install or upgrade official Chth1z/rime-neural release into %APPDATA%\Rime.
.DESCRIPTION
    Downloads the official GitHub Release bundle (rime_neural.dll + lua/rime_neural.lua + SHA-256),
    verifies hashes, ensures the Apache-2.0 ONNX model (ML-pumpkin-1103 or zhen-feather) and
    onnxruntime.dll are installed in %APPDATA%\Rime\neural\, and restarts WeaselServer cleanly.
#>
param(
    [string]$RimeDir = (Join-Path $env:APPDATA "Rime"),
    [ValidateSet("pumpkin", "feather")]
    [string]$Model = "pumpkin",
    [string]$ReleaseTag = "",
    [string]$LocalModelArchive = "",
    [switch]$ForceDownload
)

$ErrorActionPreference = "Stop"
$localInstaller = "D:\Github\rime-neural\scripts\install.ps1"

if (Test-Path $localInstaller) {
    $params = @{
        RimeDir  = $RimeDir
        Model    = $Model
        Prebuilt = $true
    }
    if ($ReleaseTag)        { $params.ReleaseTag        = $ReleaseTag }
    if ($LocalModelArchive) { $params.LocalModelArchive = $LocalModelArchive }
    if ($ForceDownload)     { $params.ForceDownload     = $true }
    & $localInstaller @params
    exit $LASTEXITCODE
}

$tmpScript = Join-Path $env:TEMP ("rime-neural-install-" + (Get-Date -Format "yyyyMMddHHmmss") + ".ps1")
try {
    $ref = if ($ReleaseTag) { $ReleaseTag } else { "main" }
    $url = "https://raw.githubusercontent.com/Chth1z/rime-neural/$ref/scripts/install.ps1"
    Write-Output "Downloading official rime-neural installer from $url..."
    & curl.exe -fSL --retry 3 --connect-timeout 20 -o $tmpScript $url
    if ($LASTEXITCODE -ne 0) { throw "Failed to download rime-neural installer." }
    $params = @{
        RimeDir  = $RimeDir
        Model    = $Model
        Prebuilt = $true
    }
    if ($ReleaseTag)        { $params.ReleaseTag        = $ReleaseTag }
    if ($LocalModelArchive) { $params.LocalModelArchive = $LocalModelArchive }
    if ($ForceDownload)     { $params.ForceDownload     = $true }
    & $tmpScript @params
}
finally {
    if (Test-Path $tmpScript) { Remove-Item $tmpScript -Force -ErrorAction SilentlyContinue }
}
