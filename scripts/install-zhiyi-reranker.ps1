<#
.SYNOPSIS
    Build and install the native Rust + ONNX Runtime Zhiyi ML-pumpkin-1103 neural reranker
    into %APPDATA%\Rime\zhiyi\.
.DESCRIPTION
    1. Downloads Zhiyi ML-pumpkin-1103 int8 fused KV-cache ONNX model (Apache-2.0) from
       dd1000001000/zhiyi_models and verifies exact SHA-256 of laya.one.fused.int8g.onnx.
    2. Locates onnxruntime.dll (from -OrtDllPath, existing %APPDATA%\Rime\zhiyi\, local Python
       onnxruntime package, or official Microsoft.ML.OnnxRuntime NuGet package).
    3. Builds native\rime_zhiyi (Rust cdylib Lua 5.4 module) via `cargo build --release`.
    4. Stops WeaselServer cleanly, copies DLLs and model files into %APPDATA%\Rime\zhiyi\,
       and restarts WeaselServer.
#>
param(
    [string]$RimeDir = (Join-Path $env:APPDATA "Rime"),
    [string]$OrtDllPath = "",
    [string]$LocalArchive = "",
    [string]$PrebuiltDll = "",
    [switch]$ForceDownload,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$zhiyiDir = Join-Path $RimeDir "zhiyi"
$crateDir = Join-Path $repoRoot "native\rime_zhiyi"

$modelUrl    = "https://github.com/dd1000001000/zhiyi_models/releases/download/model-ml-pumpkin-1103/laya-ml-pumpkin-1103-int8g.zip"
$fusedSha256 = "c273b2cfc46179e9df2a94aaa381bb6fb1d55862fe8834b4631950180d521ca5"

New-Item -ItemType Directory -Force -Path $zhiyiDir | Out-Null

# 1. Ensure ML-pumpkin-1103 fused KV-cache model files exist (Apache-2.0)
$fusedTarget = Join-Path $zhiyiDir "laya.one.fused.int8g.onnx"
$needModel = $ForceDownload -or `
    -not (Test-Path $fusedTarget) -or `
    -not (Test-Path (Join-Path $zhiyiDir "tokenizer.json")) -or `
    -not (Test-Path (Join-Path $zhiyiDir "unified_vocab.json"))

if (-not $needModel) {
    $curHash = (Get-FileHash $fusedTarget -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($curHash -ne $fusedSha256) {
        Write-Output "Existing laya.one.fused.int8g.onnx hash differs; refreshing..."
        $needModel = $true
    }
}

if ($needModel) {
    $stage = Join-Path $env:TEMP ("rime-zhiyi-dl-" + (Get-Date -Format "yyyyMMddHHmmss"))
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    try {
        if ($LocalArchive -and (Test-Path $LocalArchive)) {
            $archive = (Resolve-Path $LocalArchive).Path
            Write-Output "Using local model archive: $archive"
        } else {
            $archive = Join-Path $stage "ml-pumpkin-1103.zip"
            Write-Output "Downloading Zhiyi ML-pumpkin-1103 ONNX package (~199 MB, Apache-2.0)..."
            & curl.exe -fSL --retry 3 --connect-timeout 20 -o $archive $modelUrl
            if ($LASTEXITCODE -ne 0) { throw "Model download failed (ExitCode=$LASTEXITCODE)" }
        }

        $extDir = Join-Path $stage "extracted"
        New-Item -ItemType Directory -Force -Path $extDir | Out-Null
        Expand-Archive -Path $archive -DestinationPath $extDir -Force

        $fusedSrc = (Get-ChildItem $extDir -Recurse -Filter "laya.one.fused.int8g.onnx" | Select-Object -First 1)
        if (-not $fusedSrc) { throw "laya.one.fused.int8g.onnx not found in archive." }
        $actualHash = (Get-FileHash $fusedSrc.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $fusedSha256) {
            throw "SHA-256 mismatch on laya.one.fused.int8g.onnx! Expected=$fusedSha256 Got=$actualHash"
        }
        Write-Output "Verified laya.one.fused.int8g.onnx (SHA-256: $($actualHash.Substring(0,12))...)."

        $srcModelDir = $fusedSrc.DirectoryName
        foreach ($f in @("laya.one.fused.int8g.onnx", "tokenizer.json", "unified_vocab.json", "rl_agent_config.json", "LICENSE")) {
            $src = Join-Path $srcModelDir $f
            if (Test-Path $src) {
                Copy-Item $src (Join-Path $zhiyiDir $f) -Force
            }
        }
        # Clean up superseded whole-graph file if present so disk stays tidy (~84 MB saved)
        foreach ($old in @("laya.int8g.onnx", "laya.one.int8g.onnx")) {
            $op = Join-Path $zhiyiDir $old
            if (Test-Path $op) { Remove-Item $op -Force -ErrorAction SilentlyContinue }
        }
        Write-Output "Installed Zhiyi ML-pumpkin-1103 fused KV-cache model to $zhiyiDir."
    }
    finally {
        Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Output "Zhiyi ML-pumpkin-1103 model already verified in $zhiyiDir."
}

# 2. Resolve onnxruntime.dll
$targetOrt = Join-Path $zhiyiDir "onnxruntime.dll"
if (-not (Test-Path $targetOrt) -or $OrtDllPath) {
    $resolvedOrt = ""
    if ($OrtDllPath -and (Test-Path $OrtDllPath)) {
        $resolvedOrt = (Resolve-Path $OrtDllPath).Path
    }
    if (-not $resolvedOrt -and (Get-Command python -ErrorAction SilentlyContinue)) {
        $pyOrt = (& python -c "import onnxruntime, pathlib; p=pathlib.Path(onnxruntime.__file__).parent/'capi'/'onnxruntime.dll'; print(p if p.is_file() else '')" 2>$null)
        if ($pyOrt -and (Test-Path $pyOrt.Trim())) {
            $resolvedOrt = $pyOrt.Trim()
        }
    }
    if (-not $resolvedOrt) {
        $stageOrt = Join-Path $env:TEMP ("rime-ort-dl-" + (Get-Date -Format "yyyyMMddHHmmss"))
        New-Item -ItemType Directory -Force -Path $stageOrt | Out-Null
        try {
            $nupkg = Join-Path $stageOrt "ort.zip"
            Write-Output "Downloading official Microsoft.ML.OnnxRuntime (win-x64) from NuGet..."
            & curl.exe -fSL --retry 3 --connect-timeout 20 -o $nupkg "https://www.nuget.org/api/v2/package/Microsoft.ML.OnnxRuntime"
            if ($LASTEXITCODE -ne 0) { throw "ONNX Runtime download failed." }
            $ortEx = Join-Path $stageOrt "ex"
            Expand-Archive -Path $nupkg -DestinationPath $ortEx -Force
            $dll = Join-Path $ortEx "runtimes\win-x64\native\onnxruntime.dll"
            if (-not (Test-Path $dll)) { throw "onnxruntime.dll not found inside NuGet package." }
            Copy-Item $dll $targetOrt -Force
            Write-Output "Installed onnxruntime.dll from NuGet."
        }
        finally {
            Remove-Item $stageOrt -Recurse -Force -ErrorAction SilentlyContinue
        }
    } else {
        Copy-Item $resolvedOrt $targetOrt -Force
        Write-Output "Copied onnxruntime.dll from $resolvedOrt."
    }
} else {
    Write-Output "onnxruntime.dll already present in $zhiyiDir."
}

# 3. Resolve or build native Rust Lua 5.4 module
$builtDll = if ($PrebuiltDll -and (Test-Path $PrebuiltDll)) {
    (Resolve-Path $PrebuiltDll).Path
} else {
    Join-Path $crateDir "target\release\rime_zhiyi.dll"
}
if (-not $PrebuiltDll -and (-not $SkipBuild -or -not (Test-Path $builtDll))) {
    if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
        throw "cargo not found. Pass -PrebuiltDll <path> from Releases or install Rust (https://rustup.rs)."
    }
    Write-Output "Building native\rime_zhiyi (release)..."
    & cargo build --release --manifest-path (Join-Path $crateDir "Cargo.toml")
    if ($LASTEXITCODE -ne 0) { throw "cargo build failed (ExitCode=$LASTEXITCODE)" }
}
if (-not (Test-Path $builtDll)) { throw "Native DLL missing: $builtDll" }

# 4. Stop WeaselServer cleanly (so DLL is not locked), copy rime_zhiyi.dll, restart
$weaselDir = (Get-ChildItem "C:\Program Files\Rime" -Directory -Filter "weasel-*" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
$serverExe = if ($weaselDir) { Join-Path $weaselDir "WeaselServer.exe" } else { $null }
$wasRunning = [bool](Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)

if ($wasRunning -and $serverExe) {
    & $serverExe /q 2>$null
    for ($i = 0; $i -lt 15; $i++) {
        if (-not (Get-Process -Name WeaselServer -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 250
    }
}

Copy-Item $builtDll (Join-Path $zhiyiDir "rime_zhiyi.dll") -Force
Write-Output ("Installed rime_zhiyi.dll ({0:F2} MB) -> {1}" -f ((Get-Item $builtDll).Length / 1MB), $zhiyiDir)

if ($wasRunning -and $serverExe) {
    Start-Process -FilePath $serverExe
    Start-Sleep -Milliseconds 500
    $procs = Get-Process -Name WeaselServer -ErrorAction SilentlyContinue
    Write-Output "Restarted WeaselServer (count=$($procs.Count) PID=$($procs.Id))."
}
Write-Output "Done! Run scripts\deploy-local.ps1 -Verify to deploy updated schemas and verify."
