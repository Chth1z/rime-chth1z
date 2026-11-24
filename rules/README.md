# 声明式词库规则目录（`rules/`）

本目录是 `Chth1z/rime-chth1z` 词库覆写规则的单一真源（SSOT），所有字段定义与准入标准遵循 [`docs/DICTIONARY_SPEC.md`](../docs/DICTIONARY_SPEC.md)。

## 文件清单与列格式

所有 `.tsv` 文件使用 **UTF-8 无 BOM + LF 换行 + 单 Tab 分隔**，`#` 开头行与空行视为注释忽略。

| 文件 | 列格式（Tab 分隔） | 说明 |
| :--- | :--- | :--- |
| `phonetics_fix.tsv` | `target_file` `word` `old_py` `new_py` `reason` `source` | 修正单条词读音；同 `(target_file, word)` 禁止链式改写 |
| `word_fixes.tsv` | `target_file` `old_word` `old_py` `new_word` `new_py` `reason` `source` | 词形与繁简/错字修正；`old_py=*` 匹配全部读音，`new_py=*` 保留原读音 |
| `dual_readings.tsv` | `word` `py1` `w1` `note1` `py2` `w2` `note2` `target_file` `source` | A 类双标准词条：单点声明同时写入主词库双读音与 `corrections.dict.yaml` 双注释（主音自动 `w=0`） |
| `corrections.tsv` | `word` `wrong_py` `weight` `comment` `category` `source` | `corrections.dict.yaml` 纠错与注释覆写；`category` 限 `A` / `B` / `C` / `E1` |
| `weights.tsv` | `target_file` `word` `py` `weight` `reason` | 权重覆盖（`.gram` 粘连项仅降权不硬删）；`py=*` 匹配全部读音，`weight` 支持精确值 `N`、封顶 `<=N`、保底 `>=N` |
| `deletions.tsv` | `target_file` `word` `py` `reason` | 精确删除指定词条；`py` 填 `*` 表示匹配该词在目标文件中的所有读音 |
| `additions.tsv` | `target_file` `word` `py` `weight` `category` `source` | 补录缺失词条；`category` 限 `A` / `E1` / `modern` / `tech` / `domain` / `brand` / `phonetic` / `common` |
| `en_additions.tsv` | `word` `code` `weight` `category` | `en_dicts/en_ext.dict.yaml` 现代英文补充词；无权重时 `weight` 留空 |
| `en_fixes.tsv` | `target_file` `old_word` `old_code` `action` `new_word` `new_code` `weight` `reason` | `en_dicts/{en_ext,en}.dict.yaml` 删除、拼写/大小写修正与权重覆写；`action` 限 `delete` / `replace` / `reweight` |
| `cn_en_source.tsv` | `action` `word` `prefix_en` `cn_syls` `suffix_en` `emit_lower` `note` | 中英混合单一源，由 `scripts/build_cn_en.py` 统一派生全部 7 份 `en_dicts/cn_en*.txt`；`action` 限 `add` / `replace` / `delete` / `rename` / `case_fix` |
| `alphanum_additions.txt` | 每行一个词条 | 注入 `rime_frost.dict.yaml` 的字母数字短组合 |
| `opencc_fixes.tsv` | `target_file` `key` `action` `value` `reason` | `opencc/*.txt` 文本修复；`action` 限 `replace` / `rename`（`new_key\|new_value`）/ `delete` / `add` |

## 常用命令

```powershell
# 1. 应用全部规则并清洗词库
python scripts/clean-dicts.py

# 2. 单独同步 7 份 en_dicts/cn_en*.txt
python scripts/build_cn_en.py

# 3. 执行完整门禁校验（不变量 + 规则冲突 + 幂等性 + 同音碰撞检查）
python scripts/dict_lint.py --strict --idempotent --check-collisions
```
