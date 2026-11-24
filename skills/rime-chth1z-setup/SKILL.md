---
name: rime-chth1z-setup
description: >-
  Install, configure, upgrade, or troubleshoot the complete Chth1z/rime-chth1z
  Windows Rime / Weasel (小狼毫) input stack in one workflow: official Weasel
  Nightly (>= 0.17.4), cleaned rime-chth1z dictionaries and schemas (Natural
  Double Pinyin + Full Pinyin + TW dual-output + Lua pipeline), Wanxiang LTS
  grammar model (wanxiang-lts-zh-hans.gram), Chth1z/rime-neural ONNX neural
  reranker, apple_graphite_dark theme, optional Noto Sans CJK TC font, and
  optional weekly auto-updater task. Use when the user asks to install or
  replicate the Chth1z Rime / Weasel setup on Windows.
---

# `rime-chth1z` Full-Stack Installation & Configuration Skill

Installs and configures the complete [`Chth1z/rime-chth1z`](https://github.com/Chth1z/rime-chth1z) Windows Weasel stack end-to-end while backing up pre-existing configs and preserving `*.userdb`, `custom_phrase.txt`, `installation.yaml`, `user.yaml`, and `neural/feedback.jsonl`.

## Stack Components

- **Input Engine**: Official Windows Weasel Nightly `>= 0.17.4` (`librime >= 1.17.0` with Lua 5.4 C API exports).
- **Schemas & Cleaned Dictionaries (`Chth1z/rime-chth1z`)**: Natural Double Pinyin (`rime_frost_double_pinyin`, default) + Full Pinyin (`rime_frost`), 27 active cleaned CN dicts (`1.66M` entries, `rules/` SSOT `9,989` rules), EN / CN-EN / OpenCC tables, 6 Lua scripts (`chth1z_pipeline_filter`, `tw_dual_filter`, `calculator`, `date_translator`, `lunar`, `select_character`), Lua 5.4 GC tuning (`rime.lua`), and `apple_graphite_dark` theme (`weasel.custom.yaml`, with `claude.exe` / `claude-desktop.exe` defaulting to 臺繁).
- **Grammar Model**: `wanxiang-lts-zh-hans.gram` (~373 MB, SHA-256 verified from `amzxyz/rime-wanxiang-data` LTS release).
- **Neural Reranker**: Official [`Chth1z/rime-neural`](https://github.com/Chth1z/rime-neural) release (`rime_neural.dll` + `onnxruntime.dll` + `ML-pumpkin-1103` 82 MB or `zhen-feather` 38 MB, SHA-256 verified).
- **Optional Extras**: Google `Noto Sans CJK` Super OTC font (~91 MB zip, or `Microsoft YaHei UI` fallback) and Windows Scheduled Task `RimeChth1zWeeklyUpdate` (Sundays 03:30, no admin required).

## Workflow

### Step 1: Audit the Environment (Read-Only)

Run [`scripts/inspect-env.ps1`](./scripts/inspect-env.ps1) first before modifying any file. If reading this `SKILL.md` from a raw URL without a local checkout, fetch the script to `%TEMP%` first:

```powershell
# Local skill checkout:
powershell -ExecutionPolicy Bypass -File "<skill_dir>\scripts\inspect-env.ps1"

# Remote URL (no local checkout yet):
$s = Join-Path $env:TEMP "rime-chth1z-inspect-env.ps1"
& curl.exe -fSL -o $s "https://raw.githubusercontent.com/Chth1z/rime-chth1z/main/skills/rime-chth1z-setup/scripts/inspect-env.ps1"
powershell -ExecutionPolicy Bypass -File $s
```

Inspect the JSON output carefully:
- **OS**: Must be Windows x64 (`is_64bit_os: true`). Stop and inform the user if running on macOS/Linux.
- **Weasel readiness**: Check `weasel_dir` and `rime_dll_lua54_exports`.
  - **Important**: Do **not** install Weasel via `winget` — the stable `0.16.x` package does not export Lua 5.4 C API symbols needed by `rime-neural`. Always use official **Weasel Nightly `0.17.4+`** (`rime/weasel/releases/tags/latest`).
- **Real User Dir**: Always use `rime_user_dir` from the audit (honors `HKCU\Software\Rime\Weasel\RimeUserDir`).
- **Existing Data**: Note `existing_userdbs`, `has_custom_phrase`, `has_feedback_jsonl`, `local_repo_candidates`, `noto_cjk_tc_installed`, and `weekly_task_registered`.

### Step 2: Confirm Preferences (Single Brief Prompt)

If the user explicitly asked for **"全套默认安装 / 按你的完整配置安装 / recommended defaults"**, skip redundant questions and proceed directly with recommended defaults (still mention UAC if Weasel needs installing/upgrading).

Otherwise, briefly summarize the audit and confirm:
1. **Weasel Nightly** (*only if `weasel_dir` is null or `rime_dll_lua54_exports` is false*): confirm downloading and running the official Weasel Nightly installer (`-InstallWeasel`, triggers UAC if not elevated).
2. **Primary Layout**:
   - `zrm` (default): **自然码双拼为主 + 全拼并列**（`-PrimaryLayout zrm`）。
   - `full`: **全拼为主 + 自然码双拼并列**（`-PrimaryLayout full`）。（`melt_eng` 已内置同时支持全拼与自然码数字/符号谐音派生，两个方案均完整可用。）
3. **Neural Model**:
   - `pumpkin` (default, recommended): `ML-pumpkin-1103` (12L, ~82 MB, highest accuracy).
   - `feather`: `zhen-feather` (8L, ~38 MB, lighter for battery/RAM-constrained laptops).
   - `none`: pure statistical mode (Wanxiang `.gram` only, skips `rime-neural`).
4. **Font for `apple_graphite_dark`** (*only if `noto_cjk_tc_installed: false`*):
   - Install Google official `NotoSansCJK.ttc` (~91 MB zip, full CJK TC glyphs, `-InstallNotoFont`), OR
   - Keep `apple_graphite_dark` with Windows built-in `Microsoft YaHei UI` fallback (`-UseFallbackFont`, zero download).
5. **Weekly Auto-Updater**: Register user-level Scheduled Task `RimeChth1zWeeklyUpdate` (`-RegisterWeeklyTask`, default: yes) to sync repo, `rime-neural`, and Wanxiang `.gram` every Sunday at 03:30.

### Step 3: Run End-to-End Bootstrap

Fetch or invoke [`scripts/bootstrap.ps1`](./scripts/bootstrap.ps1). It safely backs up existing YAML/Lua files, syncs `Chth1z/rime-chth1z`, downloads and SHA-256-verifies `wanxiang-lts-zh-hans.gram`, installs official `Chth1z/rime-neural`, applies optional font/theme overrides, deploys via `WeaselDeployer /deploy`, and starts a single detached `WeaselServer.exe`.

```powershell
# Local skill checkout:
$bootstrap = "<skill_dir>\scripts\bootstrap.ps1"

# Or remote URL (no local checkout yet):
$bootstrap = Join-Path $env:TEMP "rime-chth1z-bootstrap.ps1"
& curl.exe -fSL -o $bootstrap "https://raw.githubusercontent.com/Chth1z/rime-chth1z/main/skills/rime-chth1z-setup/scripts/bootstrap.ps1"

# Example: full recommended stack on a fresh or existing Windows PC
powershell -ExecutionPolicy Bypass -File $bootstrap `
  -RimeDir "<rime_user_dir>" `
  -NeuralModel pumpkin `
  -RegisterWeeklyTask
```

Common optional flags for `bootstrap.ps1`:
- `-InstallWeasel`: install or upgrade to official Weasel Nightly (`tags/latest`) when missing or `< 0.17.4`.
- `-RepoDir "<path>"`: reuse an existing local clone (or specify where `git clone` should place `rime-chth1z`; default `%USERPROFILE%\rime-chth1z`). Pass `-NoGitClone` to use a temporary zip archive instead.
- `-PrimaryLayout zrm | full`: choose Natural Double Pinyin (`zrm`, default) or Full Pinyin (`full`) as the primary default schema.
- `-NeuralModel pumpkin | feather | none`
- `-SkipGram`: skip downloading the ~373 MB Wanxiang `.gram` model.
- `-Theme apple_graphite_dark | keep`: use `keep` to preserve the user's existing `weasel.custom.yaml`.
- `-InstallNotoFont` / `-UseFallbackFont`: install `NotoSansCJK.ttc` or patch `weasel.custom.yaml` to `Microsoft YaHei UI`.
- `-RunAccuracyTest`: also run the 242-case `bench\accuracy-test.ps1` suite after deployment (requires local checkout).

### Step 4: Apply Optional Customizations

If the user requested overrides beyond the default stack (e.g., Full Pinyin as default, removing `claude.exe` 臺繁 `app_options`, disabling UIA context or feedback logging, or reusing only the dictionaries), read [`references/customization.md`](./references/customization.md) (raw URL: `https://raw.githubusercontent.com/Chth1z/rime-chth1z/main/skills/rime-chth1z-setup/references/customization.md`), apply the minimal patch to `*.custom.yaml`, and redeploy + restart `WeaselServer.exe` detached.

### Step 5: Verify End-to-End (Separate Command)

Always run [`scripts/verify-setup.ps1`](./scripts/verify-setup.ps1) in a **separate shell command** after `bootstrap.ps1` finishes — this verifies all installed files, compiled schemas, clean Weasel logs, **and** proves `WeaselServer.exe` survived shell exit:

```powershell
# Local skill checkout:
powershell -ExecutionPolicy Bypass -File "<skill_dir>\scripts\verify-setup.ps1" -RimeDir "<rime_user_dir>"

# Or remote URL:
$v = Join-Path $env:TEMP "rime-chth1z-verify-setup.ps1"
& curl.exe -fSL -o $v "https://raw.githubusercontent.com/Chth1z/rime-chth1z/main/skills/rime-chth1z-setup/scripts/verify-setup.ps1"
powershell -ExecutionPolicy Bypass -File $v -RimeDir "<rime_user_dir>"
```

(Pass `-SkipNeural` if `-NeuralModel none` was used, or `-SkipGram` if `-SkipGram` was used.)

Every check in the JSON output must report `"ok": true`. If any check fails, consult [`references/troubleshooting.md`](./references/troubleshooting.md) (raw URL: `https://raw.githubusercontent.com/Chth1z/rime-chth1z/main/skills/rime-chth1z-setup/references/troubleshooting.md`) and fix before completing.

### Step 6: Report Clearly to the User

Provide a concise summary covering:
- Installed/verified components & paths (Weasel version, `rime_user_dir`, `rime-chth1z` repo dir, Wanxiang `.gram`, `rime-neural` model, theme/font, weekly task status).
- Backup folder path (if pre-existing Rime files were backed up) and confirmation that `*.userdb` / `custom_phrase.txt` / `feedback.jsonl` were preserved.
- Verification results (`verify-setup.ps1` `"ok": true`, single live `WeaselServer.exe` PID, `0` deploy errors, and `accuracy-test.ps1` score if run).
- Quick usage reminders:
  - Press **`F4`** (or `Ctrl+\``) to switch schemas (`自然碼雙拼` / `白霜全拼`) or toggle `簡體 / 臺繁`, `半角 / 全角`, `中標 / 英標`, `翻譯關 / 翻譯開`.
  - Press **`[`** / **`]`** on an active candidate to select its first / last character; type **`/vs<expr>`** for calculator.
  - First sentence after restarting Weasel may take ~1–2 s while `rime-neural` finishes async background warm-up.
