<#
.SYNOPSIS
    Pull dictionary and OpenCC text tables from upstream gaboolic/rime-frost and run clean-dicts.py.
#>
param(
    [switch]$Commit
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}

. (Join-Path $PSScriptRoot "_common.ps1")

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$lintReport = Join-Path $env:TEMP ("rime-chth1z-sync-lint-" + [guid]::NewGuid().ToString("N").Substring(0, 8) + ".json")

$managedUpstreamPaths = @(
    "cn_dicts/",
    "cn_dicts_cell/",
    "en_dicts/",
    "opencc/chinese_english.txt",
    "opencc/english_chinese.txt",
    "opencc/emoji.txt",
    "opencc/others.txt"
)
$managedCheckPaths = $managedUpstreamPaths + @("rime_frost.dict.yaml")
$managedCommitPaths = @("cn_dicts/", "cn_dicts_cell/", "en_dicts/", "opencc/", "rime_frost.dict.yaml")

Push-Location $repoRoot
try {
    # Guard against clobbering uncommitted local edits in managed dictionary paths
    $preDirty = Invoke-NativeSafe { & git status --porcelain -- @managedCheckPaths }
    if ($preDirty.ExitCode -ne 0) {
        throw "git status failed (ExitCode=$($preDirty.ExitCode)): $($preDirty.Output -join ' | ')"
    }
    $dirtyLines = @($preDirty.Output | Where-Object { $_ -and $_.Trim() -ne "" })
    if ($dirtyLines.Count -gt 0) {
        throw ("Managed dictionary paths have uncommitted local changes; commit or stash them first:`n" + ($dirtyLines -join "`n"))
    }

    $fetchRes = Invoke-NativeSafe { & git fetch upstream master --depth=1 }
    if ($fetchRes.ExitCode -ne 0) {
        $tail = ($fetchRes.Output | Select-Object -Last 8) -join " | "
        throw "git fetch upstream failed (ExitCode=$($fetchRes.ExitCode)): $tail"
    }

    $shaRes = Invoke-NativeSafe { & git rev-parse --short upstream/master }
    if ($shaRes.ExitCode -ne 0 -or $shaRes.Output.Count -eq 0) {
        throw "git rev-parse upstream/master failed (ExitCode=$($shaRes.ExitCode))"
    }
    $sha = ([string]$shaRes.Output[0]).Trim()
    if (-not $sha) { throw "Empty SHA resolved for upstream/master" }

    $coRes = Invoke-NativeSafe { & git checkout upstream/master -- @managedUpstreamPaths }
    if ($coRes.ExitCode -ne 0) {
        $tail = ($coRes.Output | Select-Object -Last 8) -join " | "
        throw "git checkout upstream dicts failed (ExitCode=$($coRes.ExitCode)): $tail"
    }

    $cleaner = Join-Path $repoRoot "scripts\clean-dicts.py"
    if (Test-Path -LiteralPath $cleaner) {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $global:LASTEXITCODE = 0
            & python $cleaner
            $cleanRc = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
        } finally {
            $ErrorActionPreference = $prevEap
        }
        if ($cleanRc -ne 0) { throw "clean-dicts.py failed (ExitCode=$cleanRc)" }
    }

    $linter = Join-Path $repoRoot "scripts\dict_lint.py"
    if (Test-Path -LiteralPath $linter) {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $global:LASTEXITCODE = 0
            & python $linter --strict --idempotent --check-collisions --diff-budget --json $lintReport
            $lintRc = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
        } finally {
            $ErrorActionPreference = $prevEap
        }
        if ($lintRc -ne 0) { throw "dict_lint.py failed (ExitCode=$lintRc)" }
    }

    $stRes = Invoke-NativeSafe { & git status --short -- @managedCommitPaths }
    if ($stRes.ExitCode -ne 0) {
        throw "git status failed (ExitCode=$($stRes.ExitCode))"
    }
    $status = @($stRes.Output | Where-Object { $_ -and $_.Trim() -ne "" })
    if ($status.Count -eq 0) {
        Write-Output "Dictionaries already match cleaned upstream/master @ $sha."
        return
    }
    Write-Output "Updated files from upstream/master @ ${sha}:"
    $status | Write-Output

    if ($Commit) {
        if (Test-Path -LiteralPath $lintReport) {
            $report = Get-Content -LiteralPath $lintReport -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($report.diff_budget -and $report.diff_budget.needs_review) {
                throw "Diff budget exceeded ($($report.diff_budget.reasons -join '; ')); inspect changes before committing manually."
            }
        }
        $addRes = Invoke-NativeSafe { & git add -- @managedCommitPaths }
        if ($addRes.ExitCode -ne 0) {
            throw "git add failed (ExitCode=$($addRes.ExitCode)): $($addRes.Output -join ' | ')"
        }
        # Commit --only on managed dict paths so unrelated already-staged files are never swept in
        $commitRes = Invoke-NativeSafe { & git commit --only -m "chore(dicts): sync upstream rime-frost @ $sha" -- @managedCommitPaths }
        if ($commitRes.ExitCode -ne 0) {
            throw "git commit failed (ExitCode=$($commitRes.ExitCode)): $($commitRes.Output -join ' | ')"
        }
        Write-Output "Committed dictionary sync @ $sha."
    }
}
finally {
    Pop-Location
    if (Test-Path -LiteralPath $lintReport) {
        Remove-Item -LiteralPath $lintReport -Force -ErrorAction SilentlyContinue
    }
}
