<#
.SYNOPSIS
    Check latest updates across all 4 upstreams: rime-frost, rime-ice (lua), Weasel Nightly, and Wanxiang LTS gram.
#>
$ErrorActionPreference = "Stop"
$headers = @{ "User-Agent" = "rime-chth1z-checker/1.0" }

Write-Output "=== 1. gaboolic/rime-frost (latest 5 commits) ==="
$frost = Invoke-RestMethod "https://api.github.com/repos/gaboolic/rime-frost/commits?per_page=5" -Headers $headers -TimeoutSec 20
$frost | ForEach-Object {
    "{0}  {1}  {2}" -f $_.commit.committer.date.Substring(0,10), $_.sha.Substring(0,8), ($_.commit.message -split "`n")[0]
}

Write-Output "`n=== 2. iDvel/rime-ice (latest 5 lua/ commits) ==="
$ice = Invoke-RestMethod "https://api.github.com/repos/iDvel/rime-ice/commits?path=lua&per_page=5" -Headers $headers -TimeoutSec 20
$ice | ForEach-Object {
    "{0}  {1}  {2}" -f $_.commit.committer.date.Substring(0,10), $_.sha.Substring(0,8), ($_.commit.message -split "`n")[0]
}

Write-Output "`n=== 3. rime/weasel Nightly (latest) ==="
$weasel = Invoke-RestMethod "https://api.github.com/repos/rime/weasel/releases/tags/latest" -Headers $headers -TimeoutSec 20
$inst = $weasel.assets | Where-Object { $_.name -match 'installer\.exe$' } | Select-Object -First 1
if ($inst) {
    Write-Output ("Remote : {0} (updated {1})" -f $inst.name, $inst.updated_at.Substring(0,10))
}
$localVer = (Select-String -Path (Join-Path $env:APPDATA "Rime\installation.yaml") -Pattern 'distribution_version:' -ErrorAction SilentlyContinue).Line
if ($localVer) { Write-Output "Local  : $($localVer.Trim())" }

Write-Output "`n=== 4. amzxyz/rime-wanxiang-data LTS (.gram) ==="
$wx = Invoke-RestMethod "https://api.github.com/repos/amzxyz/rime-wanxiang-data/releases/tags/LTS" -Headers $headers -TimeoutSec 20
$gram = $wx.assets | Where-Object { $_.name -eq "wanxiang-lts-zh-hans.gram" } | Select-Object -First 1
if ($gram) {
    Write-Output ("Remote : {0} ({1:N2} MB, updated {2}, {3})" -f $gram.name, ($gram.size/1MB), $gram.updated_at.Substring(0,10), $gram.digest)
}
$localGram = Join-Path $env:APPDATA "Rime\wanxiang-lts-zh-hans.gram"
if (Test-Path $localGram) {
    $lh = (Get-FileHash $localGram -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Output ("Local  : {0:N2} MB, sha256:{1}" -f ((Get-Item $localGram).Length/1MB), $lh)
}
