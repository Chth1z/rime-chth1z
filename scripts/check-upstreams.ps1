<#
.SYNOPSIS
    Check latest updates across all upstreams: rime-frost, rime-ice (lua), rime-neural, Weasel Nightly, and Wanxiang LTS gram.
#>
$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch {}

. (Join-Path $PSScriptRoot "_common.ps1")

$headers = @{ "User-Agent" = "rime-chth1z-checker/1.3" }
$ghToken = if ($env:GITHUB_TOKEN) { $env:GITHUB_TOKEN } elseif ($env:GH_TOKEN) { $env:GH_TOKEN } else { "" }
if ($ghToken) { $headers["Authorization"] = "Bearer $ghToken" }

function Format-IsoDate($Val) {
    if ($null -eq $Val) { return "unknown" }
    if ($Val -is [datetime]) { return $Val.ToString("yyyy-MM-dd") }
    $s = [string]$Val
    if ($s.Length -ge 10) { return $s.Substring(0, 10) }
    return $s
}

function Format-ErrorDetail($ErrRecord) {
    $msg = if ($ErrRecord.Exception -and $ErrRecord.Exception.Message) { $ErrRecord.Exception.Message } else { [string]$ErrRecord }
    try {
        if ($ErrRecord.Exception.Response -and $ErrRecord.Exception.Response.StatusCode) {
            $code = [int]$ErrRecord.Exception.Response.StatusCode
            return "HTTP $code ($msg)"
        }
    } catch {}
    return $msg
}

$rimeDir = Get-RimeUserDir
$failedCount = 0

Write-Output "=== 1. gaboolic/rime-frost (latest 5 commits) ==="
try {
    $frost = Invoke-RestMethod "https://api.github.com/repos/gaboolic/rime-frost/commits?per_page=5" -Headers $headers -TimeoutSec 20
    $frost | ForEach-Object {
        $firstLine = if ($_.commit.message) { ($_.commit.message -split "`r?`n")[0] } else { "" }
        $sha = if ($_.sha -and $_.sha.Length -ge 8) { $_.sha.Substring(0, 8) } else { [string]$_.sha }
        "{0}  {1}  {2}" -f (Format-IsoDate $_.commit.committer.date), $sha, $firstLine
    }
} catch {
    $failedCount++
    Write-Output ("Remote : [ERROR] {0}" -f (Format-ErrorDetail $_))
}

Write-Output "`n=== 2. iDvel/rime-ice (latest 5 lua/ commits) ==="
try {
    $ice = Invoke-RestMethod "https://api.github.com/repos/iDvel/rime-ice/commits?path=lua&per_page=5" -Headers $headers -TimeoutSec 20
    $ice | ForEach-Object {
        $firstLine = if ($_.commit.message) { ($_.commit.message -split "`r?`n")[0] } else { "" }
        $sha = if ($_.sha -and $_.sha.Length -ge 8) { $_.sha.Substring(0, 8) } else { [string]$_.sha }
        "{0}  {1}  {2}" -f (Format-IsoDate $_.commit.committer.date), $sha, $firstLine
    }
} catch {
    $failedCount++
    Write-Output ("Remote : [ERROR] {0}" -f (Format-ErrorDetail $_))
}

Write-Output "`n=== 3. Chth1z/rime-neural (latest Release) ==="
try {
    $nr = Invoke-RestMethod "https://api.github.com/repos/Chth1z/rime-neural/releases/latest" -Headers $headers -TimeoutSec 20
    Write-Output ("Remote : {0} (published {1})" -f $nr.tag_name, (Format-IsoDate $nr.published_at))
} catch {
    $failedCount++
    Write-Output ("Remote : [ERROR] {0}" -f (Format-ErrorDetail $_))
}
$localDll = Join-Path $rimeDir "neural\rime_neural.dll"
if (Test-Path -LiteralPath $localDll) {
    $lh = (Get-FileHash -LiteralPath $localDll -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Output ("Local  : {0:N2} MB, sha256:{1}" -f ((Get-Item -LiteralPath $localDll).Length / 1MB), $lh.Substring(0, 16))
}

Write-Output "`n=== 4. rime/weasel Nightly (latest) ==="
try {
    $weasel = Invoke-RestMethod "https://api.github.com/repos/rime/weasel/releases/tags/latest" -Headers $headers -TimeoutSec 20
    $inst = $weasel.assets | Where-Object { $_.name -match 'installer\.exe$' } | Select-Object -First 1
    if ($inst) {
        Write-Output ("Remote : {0} (updated {1})" -f $inst.name, (Format-IsoDate $inst.updated_at))
    } else {
        Write-Output "Remote : (installer asset not found)"
    }
} catch {
    $failedCount++
    Write-Output ("Remote : [ERROR] {0}" -f (Format-ErrorDetail $_))
}
$installYaml = Join-Path $rimeDir "installation.yaml"
if (Test-Path -LiteralPath $installYaml) {
    $verMatch = Select-String -LiteralPath $installYaml -Pattern 'distribution_version:' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($verMatch -and $verMatch.Line) { Write-Output "Local  : $($verMatch.Line.Trim())" }
}

Write-Output "`n=== 5. amzxyz/rime-wanxiang-data LTS (.gram) ==="
try {
    $wx = Invoke-RestMethod "https://api.github.com/repos/amzxyz/rime-wanxiang-data/releases/tags/LTS" -Headers $headers -TimeoutSec 20
    $gram = $wx.assets | Where-Object { $_.name -eq "wanxiang-lts-zh-hans.gram" } | Select-Object -First 1
    if ($gram) {
        Write-Output ("Remote : {0} ({1:N2} MB, updated {2}, {3})" -f $gram.name, ($gram.size / 1MB), (Format-IsoDate $gram.updated_at), $gram.digest)
    } else {
        Write-Output "Remote : (wanxiang-lts-zh-hans.gram asset not found)"
    }
} catch {
    $failedCount++
    Write-Output ("Remote : [ERROR] {0}" -f (Format-ErrorDetail $_))
}
$localGram = Join-Path $rimeDir "wanxiang-lts-zh-hans.gram"
if (Test-Path -LiteralPath $localGram) {
    $lh = (Get-FileHash -LiteralPath $localGram -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Output ("Local  : {0:N2} MB, sha256:{1}" -f ((Get-Item -LiteralPath $localGram).Length / 1MB), $lh)
}

if ($failedCount -eq 5) {
    exit 1
}
exit 0
