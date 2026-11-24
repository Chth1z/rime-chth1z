<#
.SYNOPSIS
    Internal shared helper functions for repo-internal scripts (scripts/ and bench/).
.DESCRIPTION
    Dot-sourced by repo-internal PowerShell scripts only.
    Standalone scripts (scripts/update-local.ps1 and skills/rime-chth1z-setup/scripts/*.ps1)
    remain self-contained so they can execute independently outside the repository.
#>

function Get-RimeUserDir {
    $regDir = (Get-ItemProperty -Path "HKCU:\SOFTWARE\Rime\Weasel" -Name "RimeUserDir" -ErrorAction SilentlyContinue).RimeUserDir
    if ($regDir -and $regDir.Trim()) {
        return $regDir.Trim()
    }
    return (Join-Path $env:APPDATA "Rime")
}

function Get-WeaselDir {
    param(
        [string]$RequireFile = "rime.dll"
    )
    $proc = Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($proc) {
        try {
            if ($proc.Path) {
                $procDir = Split-Path $proc.Path -Parent
                if ($procDir -and (Test-Path -LiteralPath (Join-Path $procDir $RequireFile))) {
                    return (Get-Item -LiteralPath $procDir).FullName
                }
            }
        } catch {}
    }
    foreach ($regPath in @("HKLM:\SOFTWARE\Rime\Weasel", "HKLM:\SOFTWARE\WOW6432Node\Rime\Weasel", "HKCU:\SOFTWARE\Rime\Weasel")) {
        $root = (Get-ItemProperty -Path $regPath -Name "WeaselRoot" -ErrorAction SilentlyContinue).WeaselRoot
        if ($root -and (Test-Path -LiteralPath (Join-Path $root $RequireFile))) {
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
                Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName $RequireFile) }
        }
    }
    $best = $candidates | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($best) { return $best.FullName }
    return $null
}

function Invoke-NativeSafe {
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $global:LASTEXITCODE = 0
        $out = & $Action 2>&1
        $code = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
        return [pscustomobject]@{
            ExitCode = $code
            Output   = @($out | ForEach-Object { [string]$_ })
        }
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Stop-WeaselServerClean {
    param(
        [string]$ServerExe
    )
    if (-not (Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue)) { return }
    if ($ServerExe -and (Test-Path -LiteralPath $ServerExe)) {
        [void](Invoke-NativeSafe { & $ServerExe /q })
    }
    for ($i = 0; $i -lt 20; $i++) {
        if (-not (Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue)) { return }
        Start-Sleep -Milliseconds 250
    }
    Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    for ($i = 0; $i -lt 15; $i++) {
        if (-not (Get-Process -Name "WeaselServer" -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 200
    }
}

function Start-WeaselDetached {
    param(
        [string]$ServerExe
    )
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

function New-SafeHardlinkOrCopy {
    param(
        [Parameter(Mandatory = $true)][string]$Dst,
        [Parameter(Mandatory = $true)][string]$Src
    )
    try {
        New-Item -ItemType HardLink -Path $Dst -Target $Src -ErrorAction Stop | Out-Null
    } catch {
        Copy-Item -LiteralPath $Src -Destination $Dst -Force
    }
}

function Enable-SandboxNeuralSyncInit {
    param(
        [Parameter(Mandatory = $true)][string]$BuildDir
    )
    if (-not (Test-Path -LiteralPath $BuildDir)) { return }
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $secRe = [regex]'(?m)^rime_neural:\r?\n((?:  [^\r\n]*(?:\r?\n|$))*)'
    $keyRe = [regex]'(?m)^  sync_init:[^\r\n]*'
    Get-ChildItem -LiteralPath $BuildDir -File -Filter "*.schema.yaml" -ErrorAction SilentlyContinue | ForEach-Object {
        $raw = [System.IO.File]::ReadAllText($_.FullName, [System.Text.Encoding]::UTF8)
        $m = $secRe.Match($raw)
        if ($m.Success) {
            $body = $m.Groups[1].Value
            if ($keyRe.IsMatch($body)) {
                $newBody = $keyRe.Replace($body, "  sync_init: true", 1)
            } else {
                $newBody = "  sync_init: true`n" + $body
            }
            $updated = $raw.Substring(0, $m.Groups[1].Index) + $newBody + $raw.Substring($m.Groups[1].Index + $m.Groups[1].Length)
            [System.IO.File]::WriteAllText($_.FullName, $updated, $utf8NoBom)
        }
    }
}

function New-BenchSandbox {
    param(
        [Parameter(Mandatory = $true)][string]$Prefix,
        [Parameter(Mandatory = $true)][string]$RimeDir,
        [switch]$CopyBuildYamls,
        [switch]$EnableNeuralSyncInit
    )
    $benchDir = Join-Path $env:TEMP ("$Prefix-" + (Get-Date -Format "yyyyMMddHHmmss") + "-" + [guid]::NewGuid().ToString("N").Substring(0, 6))
    try {
        New-Item -ItemType Directory -Force -Path (Join-Path $benchDir "logs") | Out-Null

        $junctionDirs = if ($CopyBuildYamls) {
            @("lua", "opencc", "cn_dicts", "cn_dicts_cell", "en_dicts")
        } else {
            @("build", "lua", "opencc", "cn_dicts", "cn_dicts_cell", "en_dicts")
        }

        foreach ($d in $junctionDirs) {
            $src = Join-Path $RimeDir $d
            if (Test-Path -LiteralPath $src) {
                New-Item -ItemType Junction -Path (Join-Path $benchDir $d) -Target $src | Out-Null
            }
        }

        if ($CopyBuildYamls) {
            $buildSrc = Join-Path $RimeDir "build"
            if (Test-Path -LiteralPath $buildSrc) {
                $buildDst = Join-Path $benchDir "build"
                New-Item -ItemType Directory -Force -Path $buildDst | Out-Null
                Get-ChildItem -LiteralPath $buildSrc -File | ForEach-Object {
                    $dstFile = Join-Path $buildDst $_.Name
                    if ($_.Extension -eq ".bin") {
                        New-SafeHardlinkOrCopy -Dst $dstFile -Src $_.FullName
                    } else {
                        Copy-Item -LiteralPath $_.FullName -Destination $dstFile -Force
                    }
                }
                if ($EnableNeuralSyncInit) {
                    Enable-SandboxNeuralSyncInit -BuildDir $buildDst
                }
            }
        }

        $neuralSrc = Join-Path $RimeDir "neural"
        if (Test-Path -LiteralPath $neuralSrc) {
            $neuralDst = Join-Path $benchDir "neural"
            New-Item -ItemType Directory -Force -Path $neuralDst | Out-Null
            Get-ChildItem -LiteralPath $neuralSrc -File | Where-Object { $_.Name -notmatch '^feedback\.jsonl(\.\d+)?$' } | ForEach-Object {
                New-SafeHardlinkOrCopy -Dst (Join-Path $neuralDst $_.Name) -Src $_.FullName
            }
        }

        Get-ChildItem -LiteralPath $RimeDir -File | Where-Object {
            $_.Extension -in @(".yaml", ".lua", ".txt") -and $_.Name -notin @("user.yaml", "installation.yaml")
        } | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $benchDir $_.Name) -Force
        }

        Get-ChildItem -LiteralPath $RimeDir -File -Filter "*.gram" | ForEach-Object {
            New-SafeHardlinkOrCopy -Dst (Join-Path $benchDir $_.Name) -Src $_.FullName
        }

        return $benchDir
    } catch {
        Remove-BenchSandbox -BenchDir $benchDir -IgnoreMissing -Quiet
        throw
    }
}

function Remove-ReparsePointsRecursive {
    param(
        [Parameter(Mandatory = $true)][string]$RootDir
    )
    if (-not (Test-Path -LiteralPath $RootDir)) { return }
    $items = @(Get-ChildItem -LiteralPath $RootDir -Force -ErrorAction SilentlyContinue)
    foreach ($item in $items) {
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            if (($item.Attributes -band [System.IO.FileAttributes]::Directory) -ne 0) {
                [System.IO.Directory]::Delete($item.FullName, $false)
            } else {
                [System.IO.File]::Delete($item.FullName)
            }
        } elseif (($item.Attributes -band [System.IO.FileAttributes]::Directory) -ne 0) {
            Remove-ReparsePointsRecursive -RootDir $item.FullName
        }
    }
}

function Remove-BenchSandbox {
    param(
        [string]$BenchDir,
        [switch]$IgnoreMissing,
        [switch]$Quiet
    )
    if (-not $BenchDir -or -not (Test-Path -LiteralPath $BenchDir)) {
        return
    }
    Remove-ReparsePointsRecursive -RootDir $BenchDir
    Remove-Item -LiteralPath $BenchDir -Recurse -Force
    if (Test-Path -LiteralPath $BenchDir) {
        $msg = "Failed to remove bench sandbox (leaked files remain): $BenchDir"
        if ($Quiet) {
            Write-Warning $msg
        } else {
            throw $msg
        }
    }
}

function Get-WeaselLogSnapshot {
    param(
        [string]$LogDir = (Join-Path $env:TEMP "rime.weasel")
    )
    $names = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    if ($LogDir -and (Test-Path -LiteralPath $LogDir)) {
        Get-ChildItem -LiteralPath $LogDir -File -ErrorAction SilentlyContinue | ForEach-Object {
            [void]$names.Add($_.Name)
        }
    }
    return ,$names
}

function Assert-WeaselDeployLogs {
    param(
        [Parameter(Mandatory = $true)][datetime]$DeployStart,
        [System.Collections.Generic.HashSet[string]]$PriorLogNames,
        [string]$LogDir = (Join-Path $env:TEMP "rime.weasel"),
        [scriptblock]$OnSummary
    )
    if (-not (Test-Path -LiteralPath $LogDir)) {
        Write-Warning "Weasel log directory not found ($LogDir); unable to inspect deploy logs."
        return
    }
    $newInfos = @(Get-ChildItem -LiteralPath $LogDir -Filter "rime.weasel*.INFO*" -File -ErrorAction SilentlyContinue |
        Where-Object {
            ($null -eq $PriorLogNames -or (-not $PriorLogNames.Contains($_.Name))) -or
            ($_.CreationTime -ge $DeployStart.AddSeconds(-2))
        } |
        Sort-Object CreationTime -Descending | Select-Object -First 4)

    $foundSummary = $null
    foreach ($infoLog in $newInfos) {
        $infoLines = Get-Content -LiteralPath $infoLog.FullName -Encoding UTF8 -ErrorAction SilentlyContinue
        $summaryLine = $infoLines | Where-Object { $_ -match 'finished updating schemas:' } | Select-Object -Last 1
        if ($summaryLine) {
            $foundSummary = $summaryLine
            if ($OnSummary) {
                & $OnSummary $infoLog.Name $summaryLine
            }
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
        throw "No new WeaselDeployer INFO log containing 'finished updating schemas:' was found in $LogDir after deploy."
    }
}
