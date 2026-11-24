<#
.SYNOPSIS
    Check latest updates across all upstreams: rime-frost, rime-ice (lua), rime-neural, Weasel Nightly, and Wanxiang LTS gram.
#>
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
$headers = @{ "User-Agent" = "rime-chth1z-checker/1.2" }
$ghToken = if ($env:GITHUB_TOKEN) { $env:GITHUB_TOKEN } elseif ($env:GH_TOKEN) { $env:GH_TOKEN } else { "" }
if ($ghToken) { $headers["Authorization"] = "Bearer $ghToken" }

function Format-IsoDate($Val) {
    if ($null -eq $Val) { return "unknown" }
    if ($Val -is [datetime]) { return $Val.ToString("yyyy-MM-dd") }
    $s = [string]$Val
    if ($s.Length -ge 10) { return $s.Substring(0, 10) }
    return $s
}

$regRime = (Get-ItemProperty -Path "HKCU:\SOFTWARE\Rime\Weasel" -Name "RimeUserDir" -ErrorAction SilentlyContinue).RimeUserDir
$rimeDir = if ($regRime -and $regRime.Trim()) { $regRime.Trim() } else { Join-Path $env:APPDATA "Rime" }

Write-Output "=== 1. gaboolic/rime-frost (latest 5 commits) ==="
$frost = Invoke-RestMethod "https://api.github.com/repos/gaboolic/rime-frost/commits?per_page=5" -Headers $headers -TimeoutSec 20
$frost | ForEach-Object {
    "{0}  {1}  {2}" -f (Format-IsoDate $_.commit.committer.date), $_.sha.Substring(0,8), ($_.commit.message -split "`n")[0]
}

Write-Output "`n=== 2. iDvel/rime-ice (latest 5 lua/ commits) ==="
$ice = Invoke-RestMethod "https://api.github.com/repos/iDvel/rime-ice/commits?path=lua&per_page=5" -Headers $headers -TimeoutSec 20
$ice | ForEach-Object {
    "{0}  {1}  {2}" -f (Format-IsoDate $_.commit.committer.date), $_.sha.Substring(0,8), ($_.commit.message -split "`n")[0]
}

Write-Output "`n=== 3. Chth1z/rime-neural (latest Release) ==="
try {
    $nr = Invoke-RestMethod "https://api.github.com/repos/Chth1z/rime-neural/releases/latest" -Headers $headers -TimeoutSec 20
    Write-Output ("Remote : {0} (published {1})" -f $nr.tag_name, (Format-IsoDate $nr.published_at))
} catch {
    Write-Output "Remote : (not yet published)"
}
$localDll = Join-Path $rimeDir "neural\rime_neural.dll"
if (Test-Path $localDll) {
    $lh = (Get-FileHash $localDll -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Output ("Local  : {0:N2} MB, sha256:{1}" -f ((Get-Item $localDll).Length/1MB), $lh.Substring(0,16))
}

Write-Output "`n=== 4. rime/weasel Nightly (latest) ==="
$weasel = Invoke-RestMethod "https://api.github.com/repos/rime/weasel/releases/tags/latest" -Headers $headers -TimeoutSec 20
$inst = $weasel.assets | Where-Object { $_.name -match 'installer\.exe$' } | Select-Object -First 1
if ($inst) {
    Write-Output ("Remote : {0} (updated {1})" -f $inst.name, (Format-IsoDate $inst.updated_at))
}
$localVer = (Select-String -Path (Join-Path $rimeDir "installation.yaml") -Pattern 'distribution_version:' -ErrorAction SilentlyContinue).Line
if ($localVer) { Write-Output "Local  : $($localVer.Trim())" }

Write-Output "`n=== 5. amzxyz/rime-wanxiang-data LTS (.gram) ==="
$wx = Invoke-RestMethod "https://api.github.com/repos/amzxyz/rime-wanxiang-data/releases/tags/LTS" -Headers $headers -TimeoutSec 20
$gram = $wx.assets | Where-Object { $_.name -eq "wanxiang-lts-zh-hans.gram" } | Select-Object -First 1
if ($gram) {
    Write-Output ("Remote : {0} ({1:N2} MB, updated {2}, {3})" -f $gram.name, ($gram.size/1MB), (Format-IsoDate $gram.updated_at), $gram.digest)
}
$localGram = Join-Path $rimeDir "wanxiang-lts-zh-hans.gram"
if (Test-Path $localGram) {
    $lh = (Get-FileHash $localGram -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Output ("Local  : {0:N2} MB, sha256:{1}" -f ((Get-Item $localGram).Length/1MB), $lh)
}
