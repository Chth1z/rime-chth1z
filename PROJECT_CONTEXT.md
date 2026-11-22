# Project Context & Handoff (`Chth1z/rime-chth1z`)

> 本文件記錄 `rime-chth1z` 的完整背景、實測數據、環境狀態與工程規範，供切換至 `D:\Github\rime-chth1z` 工作區後無縫接續開發。

## 1. 專案定位與四源上游架構

本倉庫為個人自用、面向 Windows **小狼毫（Weasel）** 深度最佳化的獨立開源倉庫（`https://github.com/Chth1z/rime-chth1z`，GPL-3.0），不作為 GitHub Fork 維護，歷史乾淨（初始切入白霜 `970a6d6`）。

核心原則：**純數據詞庫自動單向同步自白霜上游；引擎管線、Lua 腳本、方案結構、效能基準、準確性回歸與外觀主題由本倉庫獨立精修與壓測；審計中發現的上游共性問題依規範回回饋上游。**

| 上游來源 | 追蹤內容 | 同步／監控機制 |
| :--- | :--- | :--- |
| **`upstream` (`gaboolic/rime-frost`)** | `cn_dicts/`、`cn_dicts_cell/`、`en_dicts/`、`opencc/` 數據檔 | `.github/workflows/sync-upstream-dicts.yml`（每週自動同步＋完整性檢查，零合併衝突）與 `scripts/sync-dicts-local.ps1` |
| **`upstream` (`gaboolic/rime-frost`)** | `lua/`、`*.schema.yaml`、`default.yaml` 代碼與方案更新 | 本地只讀遠端 `upstream`（`no_push`，隨時 `git show upstream/master:<path>` 對照）＋ `.github/workflows/upstream-watch.yml` 每週滾動 Issue |
| **`rime-ice` (`iDvel/rime-ice`)** | 母庫 `lua/` 腳本重構與 Bug 修復 | 本地只讀遠端 `rime-ice`（`no_push`）＋ `upstream-watch.yml` 每週監控 |
| **`amzxyz/rime-wanxiang-data` (`LTS`)** | 400 MB 語法模型 `wanxiang-lts-zh-hans.gram`（不入 Git） | `upstream-watch.yml` 追蹤 SHA-256；本機週更腳本原子替換 |
| **`rime/weasel` (`latest` Nightly)** | Windows 客戶端與 `librime` 升級 | `upstream-watch.yml` ＋ `scripts/check-upstreams.ps1` 追蹤新版安裝包 |

## 2. 本機驗證環境（2026-11-22 實測基準）

- **硬體與系統**：Windows 11 (`zh-Hant-TW` / `0x0404`), Intel Core Ultra 7 255HX, 32 GB RAM
- **輸入法引擎**：Weasel Nightly `0.17.4.98.f96ed24` (`librime 1.17.0`, `Lua 5.4.8`, Direct2D WARP, 零第三方 DLL 注入)
- **系統字體**：Google 官方全字集 Super OTC `NotoSansCJK.ttc` + `NotoSerifCJK.ttc`（繁簡日韓 0 缺字），另裝有 `Chiron GoRound TC VF`、`Inter Variable Text`、`LXGW WenKai TC`、`Newsreader`、`Source Serif 4`、`Plus Jakarta Sans`
- **活躍配置**：自然碼雙拼（主力）＋ 白霜全拼（備用），掛載 `wanxiang-lts-zh-hans.gram`（372.68 MB）、OpenCC `s2twp.json`（臺灣字形＋臺灣慣用語）、直排 5 候選（`F4` 單頁 6 項），外觀 `apple_graphite_dark`（`#262626` ＋ `#2C62CE` ＋ `Noto Sans CJK TC:medium` 13pt / 11pt 阿拉伯數字）

## 3. 已實測證實的關鍵性能數據（`bench/bench-rime.ps1`）

使用本機 `rime.dll` 直接計時（隔離 `userdb`，同一組短／中／20 字長句）：

| 狀態 | 電池模式（首鍵 / 後續鍵） | 插電模式（首鍵 / 後續鍵） |
| :--- | :---: | :---: |
| 上游原始 `pin_cand_filter`（26 鍵含不可達 2-3 字詞） | `180.7 ms / 18.1 ms` | `52.7 ms / 5.5 ms` |
| 修復 `pin_cand_filter`（僅保留可達單字）＋調至 `corrector` 之前 | `~18 ms / ~15 ms` | **`5.4 ms / 5.1 ms`**（26 鍵 max `8.3 ms`） |
| 移除全部 4 個高頻 Lua 濾鏡＋`force_gc`（理論純 C++ 下限） | `3.5 ms / 3.9 ms` | **`1.1 ms / 1.1 ms`** |

**已證實的關鍵結論（事實優先）：**
1. **400 MB 萬象語法模型本身幾乎零延遲**（開關差距 < 0.2 ms）；`s2twp` 約 1 ms；`melt_eng` < 1 ms；Direct2D 陰影主執行緒全天僅耗 0.42 s CPU。
2. **插電 vs 電池性能差距為 3.3 倍**，優化驗收以「電池下仍低於 16 ms 一幀門檻」為標準。
3. **剩餘 4.3 ms（電池 ~14 ms）延遲拆解（插電實測）**：
   - `corrector` + `spelling_hints: 8`：`+1.5 ms`（`corrections.dict.yaml` 共 159 條中單字條目為 0，卻對單字做全量反查）
   - `pin_cand_filter` 空跑透傳：`+1.2 ms`
   - `reduce_english_filter`：`+0.9 ms`
   - `autocap_filter`：`+0.4 ms`
   - `force_gc`：`+0.3 ms`

## 4. 工程協作規範

- **事實與數據優先**：所有優化必須用 `bench/bench-rime.ps1`（及後續準確性回歸測試）跑出前後對比數據，不做無根據猜測，不給無效情緒誇獎。
- **零衝突邊界**：不手動修改會被 `sync-upstream-dicts.yml` 覆蓋的純數據目錄（`cn_dicts/`、`cn_dicts_cell/`、`en_dicts/`）；客製化集中於 `lua/`、根目錄方案、`profiles/`、`themes/`、`bench/`、`scripts/`。
- **上游問題回饋規範**：凡審計中發現屬上游共性的缺陷，一律遵守 [`docs/upstream-issues/GUIDELINE.md`](docs/upstream-issues/GUIDELINE.md)（核心紅線：**必須是經實測復現、具實際影響與意義的客觀 Bug，嚴禁提報因視角/偏好/理解偏差產生的 AI 偽 Bug**），以 [`TEMPLATE.md`](docs/upstream-issues/TEMPLATE.md) 整理並在 [`TRACKER.md`](docs/upstream-issues/TRACKER.md) 留檔，避免零碎刷屏。
- **原話語言習慣**：繁體／簡體自然雙語，配置內以臺灣繁體（`s2twp.json`）為預設輸出。
