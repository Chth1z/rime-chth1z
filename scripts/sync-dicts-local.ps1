<#
.SYNOPSIS
    Pull dictionary and OpenCC text tables from upstream gaboolic/rime-frost and run clean-dicts.py.
#>
param(
    [switch]$Commit
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $repoRoot
try {
    git fetch upstream master --depth=1
    if ($LASTEXITCODE -ne 0) { throw "git fetch upstream failed" }
    $sha = (git rev-parse --short upstream/master).Trim()

    git checkout upstream/master -- `
        cn_dicts/ `
        cn_dicts_cell/ `
        en_dicts/ `
        opencc/chinese_english.txt `
        opencc/english_chinese.txt `
        opencc/emoji.txt `
        opencc/others.txt

    if ($LASTEXITCODE -ne 0) { throw "git checkout upstream dicts failed" }

    $cleaner = Join-Path $repoRoot "scripts\clean-dicts.py"
    if (Test-Path $cleaner) {
        python $cleaner
        if ($LASTEXITCODE -ne 0) { throw "clean-dicts.py failed" }
    }

    $status = git status --short
    if (-not $status) {
        Write-Output "Dictionaries already match cleaned upstream/master @ $sha."
        return
    }
    Write-Output "Updated files from upstream/master @ ${sha}:"
    $status | Write-Output

    if ($Commit) {
        git add cn_dicts/ cn_dicts_cell/ en_dicts/ opencc/ rime_frost.dict.yaml
        git commit -m "chore(dicts): sync upstream rime-frost @ $sha"
        Write-Output "Committed dictionary sync @ $sha."
    }
}
finally {
    Pop-Location
}
