<#
.SYNOPSIS
    Pull only dictionary & OpenCC data files from upstream gaboolic/rime-frost without merge conflicts.
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
        opencc/STCharacters.ocd2 `
        opencc/STPhrases.ocd2 `
        opencc/TWPhrases.ocd2 `
        opencc/TWVariants.ocd2 `
        opencc/chinese_english.txt `
        opencc/english_chinese.txt `
        opencc/emoji.txt `
        opencc/others.txt

    if ($LASTEXITCODE -ne 0) { throw "git checkout upstream dicts failed" }

    $status = git status --short
    if (-not $status) {
        Write-Output "Dictionaries already match upstream/master @ $sha."
        return
    }
    Write-Output "Updated files from upstream/master @ ${sha}:"
    $status | Write-Output

    if ($Commit) {
        git add cn_dicts/ cn_dicts_cell/ en_dicts/ opencc/
        git commit -m "chore(dicts): sync upstream rime-frost @ $sha"
        Write-Output "Committed dictionary sync @ $sha."
    }
}
finally {
    Pop-Location
}
