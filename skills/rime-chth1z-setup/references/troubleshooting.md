# Troubleshooting & Rollback Reference (`rime-chth1z`)

## 1. Weasel Too Old (`rime_dll_lua54_exports: false`) or `winget` Installed `0.16.x`

- **Symptom**: `inspect-env.ps1` reports `rime_dll_lua54_exports: false`, or Weasel logs show `rime_neural: init failed` / missing Lua symbols.
- **Cause**: Official stable Weasel `0.16.x` (including default `winget` packages) does not export Lua 5.4 C API symbols from `rime.dll`.
- **Fix**: Re-run `bootstrap.ps1 -InstallWeasel` (or manually download the official Nightly `installer.exe` from <https://github.com/rime/weasel/releases/tag/latest>), approve UAC, then re-run `inspect-env.ps1` to confirm `rime_dll_lua54_exports: true`.

## 2. UAC Required When Installing Weasel

- **Symptom**: `bootstrap.ps1 -InstallWeasel` fails or hangs waiting for elevation in a non-interactive terminal.
- **Fix**: Download the latest `weasel-*-installer.exe` from <https://github.com/rime/weasel/releases/tag/latest> to `%TEMP%`, open it for the user to approve the Windows UAC dialog, wait for completion, then run `bootstrap.ps1` without `-InstallWeasel`.

## 3. `rime_neural.dll` Locked During Upgrade / Redeploy

- **Symptom**: `Copy-Item` fails with `The process cannot access the file because it is being used by another process`.
- **Cause**: `rime_neural.dll` pins itself in `WeaselServer.exe` (`GET_MODULE_HANDLE_EX_FLAG_PIN`) so Rime redeploys never crash or reload ONNX Runtime.
- **Fix**: Stop `WeaselServer.exe` cleanly first:
  ```powershell
  & "<weasel_dir>\WeaselServer.exe" /q 2>$null
  Start-Sleep -Milliseconds 600
  Get-Process -Name WeaselServer -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  ```

## 4. `WeaselServer.exe` Dies Right After Agent Shell Exits

- **Symptom**: `verify-setup.ps1` reports `process:WeaselServer` `count=0` even though deploy succeeded in the previous command.
- **Cause**: Agent terminal runners often wrap commands in a Windows Job Object (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`) that kills child processes on command exit.
- **Fix**: Start `WeaselServer.exe` detached via WMI/CIM and verify in a subsequent command:
  ```powershell
  Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = "`"<weasel_dir>\WeaselServer.exe`"" } | Out-Null
  ```

## 5. GitHub Download Timeouts or Proxy Issues

- **Symptom**: `curl.exe` fails to download `wanxiang-lts-zh-hans.gram`, `rime-neural`, or `NotoSansCJK.zip`.
- **Fix**: Ensure the user's proxy environment variable (`HTTPS_PROXY` / `HTTP_PROXY`) is set in the shell before calling `bootstrap.ps1`, or re-run `bootstrap.ps1` (already-downloaded components such as `.gram` and `rime-neural` are automatically reused unless `-ForceRedownload` is passed).

## 6. `Noto Sans CJK TC` Font Not Picking Up Immediately

- **Symptom**: Candidate window still falls back to Microsoft YaHei after `-InstallNotoFont`.
- **Fix**: Restart `WeaselServer.exe` (`/q` then detached launch) so DirectWrite reloads the newly registered user font cache, or sign out and sign back in if installing per-user on older Windows 10 builds.

## 7. Clean Rollback / Uninstall

1. Stop `WeaselServer.exe` cleanly (`/q`).
2. Restore files from `<rime_user_dir>\backup-pre-rime-chth1z-<timestamp>\` back into `<rime_user_dir>\`.
3. Optionally remove `<rime_user_dir>\neural\` (keep `feedback.jsonl` if desired), `<rime_user_dir>\lua\rime_neural.lua`, and `<rime_user_dir>\wanxiang-lts-zh-hans.gram`.
4. If the weekly updater task was registered, remove it:
   ```powershell
   Unregister-ScheduledTask -TaskName "RimeChth1zWeeklyUpdate" -Confirm:$false -ErrorAction SilentlyContinue
   ```
5. Run `"<weasel_dir>\WeaselDeployer.exe" /deploy` and restart `WeaselServer.exe` detached.
