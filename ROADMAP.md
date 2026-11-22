# Optimization & Audit Roadmap (`Chth1z/rime-chth1z`)

> 目標：**在不犧牲打字準確率、400 MB 萬象模型、繁簡慣用詞（`s2twp`）與英文混輸體驗的前提下，將解碼延遲壓近 C++ 理論下限（插電 `<= 2.5 ms`、電池 `<= 8 ms`），並建立可量化回歸測試與高質量上游 Issue 回饋閉環。**

## P0 — 引擎管線重构、全量 Lua 審計與回歸基準

- [ ] **補齊準確性黃金回歸集（`bench/accuracy-test.ps1`）**
  - 在重構任何 Lua 管線之前，先用 `rime.dll` 建立固定斷言集：涵蓋雙拼/全拼長句首選、單字固頂、`corrector` 錯音提示、`autocap` 大小寫、中英混輸（`RTX4090` / `Nous` / `VEGF` / `HEllo`）、`s2twp` 臺灣用語、日期/農曆/計算器，確保後續性能優化 **0 功能回退**。
- [ ] **全量審計 `lua/*.lua` 並打包提報上游缺陷**
  - 系統審計倉庫內全部 16 個 Lua 腳本：檢查 `seg:has_tag` 缺失（如已知的 `number_translator.lua`）、`config:get_string` 缺 `nil` 保護、`Lua 5.4 / LuaJIT` 兼容、潛在死循環或無效掃描，以及 `translator/grammar_penalty` 死配置查證。
  - 按 [`docs/upstream-issues/GUIDELINE.md`](docs/upstream-issues/GUIDELINE.md) 整理並提交高質量上游 Issue，更新 [`TRACKER.md`](docs/upstream-issues/TRACKER.md)。
- [ ] **合併高頻 Lua 濾鏡（消除 C++↔Lua 多次協程跨界稅）**
  - 現狀：`pin_cand_filter`、`corrector`、`autocap_filter`、`reduce_english_filter` 獨立掛載，每次按鍵跨界 4 層，插電耗時 `4.0 ms`（電池 `~13 ms`）。
  - 方案：實作單一合併管線濾鏡（如 `lua/chth1z_pipeline_filter.lua`），單次遍歷完成 `pin_cand`（含可達性保護與合理掃描上限）＋ 單字跳過查表的 `corrector` ＋ `autocap` ＋ `reduce_english`，並評估 `force_gc` 改為低頻觸發或移除。
  - 驗收：`bench/bench-rime.ps1` 插電 `<= 2.5 ms`、電池 `<= 8 ms`，且 `accuracy-test.ps1` 全數通過。
- [ ] **根目錄方案內建修復（減少對 `profiles/*.custom.yaml` 補丁堆疊的依賴）**
  - 直接在 `rime_frost_double_pinyin.schema.yaml` 與 `rime_frost.schema.yaml` 修正 `pin_cand_filter`、濾鏡順序、剝離不用的 `radical_pinyin`/`frost_aux` 依賴與無效鍵。

## P1 — 上游 `rime-ice` 腳本擇優移植與 `melt_eng` 壓縮

- [ ] **評估移植 `iDvel/rime-ice` 新版 `select_character.lua`**（長句定字與游標非句尾保留右側輸入改進）。
- [ ] **評估 `rime-ice` `pin_cand_filter.lua` 近期修正**（邊界匹配與 LuaJIT 兼容）。
- [ ] **分析與瘦身 `melt_eng` 棱鏡體積（目前 `6.82 MB`）**：測評 `melt_eng_algebra_common.yaml` 中 `{2..10}` 大寫派生裁剪為 `{2..4}` 配合 `autocap_filter` 對部署速度、記憶體與英文首選率的實際影響。

## P2 — 詞庫噪聲治理、臺灣用語微調與本機閉環

- [ ] **詞庫噪聲分析與可選精簡入口 `rime_frost_clean.dict.yaml`**
  - 寫 Python 分析腳本統計 `cn_dicts/` 與 `cn_dicts_cell/` 中干擾日常打字的低頻異體字/生僻遊戲詞（如 `41448`、`GB18030-2022`、`game`、`luna`），透過回歸集對比首選率與編譯耗時。
- [ ] **臺灣用語 `s2twp` 精細覆寫層**
  - 保留 `s2twp.json` 的高頻資訊詞（`軟體 / 資訊 / 記憶體 / 網路 / 滑鼠 / 預設 / 檔案`），提供可選微調層修正少數生硬詞彙（如 `优化 → 優化`）。
- [ ] **接管本機 Windows 週更排程**
  - 將 `RimeFrostWeeklyUpdate` 切換為拉取 `Chth1z/rime-chth1z` ＋ `wanxiang-lts-zh-hans.gram`，形成完全自主維護閉環。
