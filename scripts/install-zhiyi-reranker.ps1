<#
.SYNOPSIS
    Build and install the native Rust + ONNX Runtime Zhiyi neural reranker into %APPDATA%\Rime\zhiyi\.
.DESCRIPTION
    1. Downloads Zhiyi 1.4V2-Long-L12 int8 ONNX model (Apache-2.0) from qingjian-team/qingjian-models
       with SHA-256 verification (reuses existing files unless -ForceDownload is set).
    2. Locates onnxruntime.dll (from -OrtDllPath, existing %APPDATA%\Rime\zhiyi\, local Python
       onnxruntime package, or official Microsoft.ML.OnnxRuntime NuGet package).
    3. Builds native\rime_zhiyi (Rust cdylib Lua 5.4 module) via `cargo build --release`.
    4. Stops WeaselServer cleanly, copies DLLs and model files into %APPDATA%\Rime\zhiyi\,
       and restarts WeaselServer.
#>
param(
    [string]$RimeDir = (Join-Path $env:APPDATA "Rime"),
    [string]$OrtDllPath = "",
    [switch]$ForceDownload,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$zhiyiDir = Join-Path $RimeDir "zhiyi"
$crateDir = Join-Path $repoRoot "native\rime_zhiyi"

$modelUrl    = "https://github.com/qingjian-team/qingjian-models/releases/download/zhiyi-onnx-v1.0.0/zhiyi-onnx-v1.0.0.tar.gz.part1"
$modelSha256 = "d693c2a262613888202e2de73b9bfce9f6421db3db2e1b7e1109aac9a296d5f3"

New-Item -ItemType Directory -Force -Path $zhiyiDir | Out-Null

# 1. Ensure Zhiyi ONNX model files exist (Apache-2.0)
$needModel = $ForceDownload -or `
    -not (Test-Path (Join-Path $zhiyiDir "laya.int8g.onnx")) -or `
    -not (Test-Path (Join-Path $zhiyiDir "tokenizer.json")) -or `
    -not (Test-Path (Join-Path $zhiyiDir "unified_vocab.json"))

if ($needModel) {
    $stage = Join-Path $env:TEMP ("rime-zhiyi-dl-" + (Get-Date -Format "yyyyMMddHHmmss"))
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    try {
        $archive = Join-Path $stage "zhiyi-onnx.tar.gz"
        Write-Output "Downloading Zhiyi 1.4V2-Long-L12 ONNX model (~70 MB, Apache-2.0)..."
        & curl.exe -fSL --retry 3 --connect-timeout 20 -o $archive $modelUrl
        if ($LASTEXITCODE -ne 0) { throw "Model download failed (ExitCode=$LASTEXITCODE)" }

        $actualHash = (Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $modelSha256) {
            throw "SHA-256 mismatch! Expected=$modelSha256 Got=$actualHash"
        }
        Write-Output "Model archive verified (SHA-256: $($actualHash.Substring(0,12))...)."

        $extDir = Join-Path $stage "extracted"
        New-Item -ItemType Directory -Force -Path $extDir | Out-Null
        & tar.exe -xzf $archive -C $extDir
        if ($LASTEXITCODE -ne 0) { throw "tar extraction failed (ExitCode=$LASTEXITCODE)" }

        $srcModelDir = (Get-ChildItem $extDir -Recurse -Filter "laya.int8g.onnx" | Select-Object -First 1).DirectoryName
        if (-not $srcModelDir) { throw "laya.int8g.onnx not found in extracted archive." }

        foreach ($f in @("laya.int8g.onnx", "tokenizer.json", "unified_vocab.json", "LICENSE")) {
            $src = Join-Path $srcModelDir $f
            if (Test-Path $src) {
                Copy-Item $src (Join-Path $zhiyiDir $f) -Force
            }
        }
        Write-Output "Installed Zhiyi ONNX model files to $zhiyiDir."
    }
    finally {
        Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Output "Zhiyi ONNX model files already present in $zhiyiDir."
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
            & curl.exe -fSL --retry 3 --connect-timeout 20 -o $nupkg "https://www.nuget.org/api/v2/package/Microsoft.ML.OnnxRuntime/1.20.1"
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

# 3. Build native Rust Lua 5.4 module
$builtDll = Join-Path $crateDir "target\release\rime_zhiyi.dll"
if (-not $SkipBuild -or -not (Test-Path $builtDll)) {
    if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
        throw "cargo not found. Install Rust toolchain (https://rustup.rs) to build native\rime_zhiyi."
    }
    Write-Output "Building native\rime_zhiyi (release)..."
    & cargo build --release --manifest-path (Join-Path $crateDir "Cargo.toml")
    if ($LASTEXITCODE -ne 0) { throw "cargo build failed (ExitCode=$LASTEXITCODE)" }
}
if (-not (Test-Path $builtDll)) { throw "Built DLL missing: $builtDll" }

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
