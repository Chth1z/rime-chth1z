# Customization Recipes (`rime-chth1z`)

Apply customizations via `*.custom.yaml` inside `<rime_user_dir>` so future `rime-chth1z` updates preserve your preferences cleanly. After editing any YAML file, stop `WeaselServer.exe`, run `WeaselDeployer.exe /deploy`, and relaunch `WeaselServer.exe` detached.

## 1. Make Full Pinyin (`rime_frost`) the Default Schema

Pass `-PrimaryLayout full` to `bootstrap.ps1`, or edit `<rime_user_dir>\default.custom.yaml` manually (`melt_eng.schema.yaml` already supports both Full Pinyin and Natural Double Pinyin digit/symbol derivations simultaneously via `algebra_fp_zrm`):

```yaml
patch:
  schema_list:
    - schema: rime_frost                 # 全拼默认
    - schema: rime_frost_double_pinyin   # 自然码双拼
```

## 2. Disable `claude.exe` Automatic Traditional Chinese (`app_options`)

In `<rime_user_dir>\weasel.custom.yaml`, remove or override:

```yaml
  "app_options/claude.exe":
    traditionalization: false
  "app_options/claude-desktop.exe":
    traditionalization: false
```

## 3. Use Windows Built-in Font Instead of `Noto Sans CJK TC`

If you did not install `NotoSansCJK.ttc`, either pass `-UseFallbackFont` to `bootstrap.ps1` or replace the font lines in `<rime_user_dir>\weasel.custom.yaml`:

```yaml
  "style/font_face": "Microsoft YaHei UI, Segoe UI Emoji"
  "style/label_font_face": "Microsoft YaHei UI"
  "style/comment_font_face": "Microsoft YaHei UI"
```

## 4. Adjust `rime-neural` Privacy or Performance Settings

Add under `patch:` in `<rime_user_dir>\rime_frost_double_pinyin.custom.yaml` and `<rime_user_dir>\rime_frost.custom.yaml`:

```yaml
patch:
  rime_neural/enable_uia_context: false   # disable cross-app cursor context reading
  rime_neural/log_feedback: false         # disable local redacted feedback.jsonl
  # rime_neural/threads: 4                # cap CPU threads (0 = auto 4..8)
```

## 5. Pure Statistical Mode (Without `rime-neural`)

Passing `-NeuralModel none` to `bootstrap.ps1` generates this automatically in both `rime_frost.custom.yaml` and `rime_frost_double_pinyin.custom.yaml`:

```yaml
patch:
  engine/filters:
    - lua_filter@*chth1z_pipeline_filter
    - simplifier@emoji
    - simplifier@chinese_english
    - lua_filter@*tw_dual_filter
    - uniquifier
```

## 6. Enable Emoji or Chinese-English Translation by Default

`emoji` and `chinese_english` are wired in both schemas and can be toggled in the `F4` menu (persisted in `user.yaml`). To enable `emoji` by default via patch:

```yaml
patch:
  "switches/@5/reset": 1
```

## 7. Reuse Cleaned Dictionaries Only (Inside Another Rime Config)

Copy `cn_dicts/`, `cn_dicts_cell/`, `en_dicts/`, and `opencc/{emoji,others,chinese_english,english_chinese}.txt` directly into your existing `rime-frost` / `rime-ice`-compatible `<rime_user_dir>` without overwriting your own `default.yaml`, `weasel.custom.yaml`, or schema files. To regenerate from upstream `gaboolic/rime-frost` yourself:

```powershell
python scripts/clean-dicts.py --manifest clean_manifest.json
python scripts/dict_lint.py --strict --idempotent --check-collisions
```
