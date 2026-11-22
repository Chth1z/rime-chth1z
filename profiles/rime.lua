-- Lua 5.4 增量 GC 調優：
-- 注意 pause 必須 > 100（< 100 會令 Lua 5.4 取消 GC 週期間隔、每次分配持續全堆掃描，導致按鍵暴增 5+ ms）。
-- 設為 (150, 200) 搭配 chth1z_pipeline_filter 每 16 鍵一次增量 step，
-- 實測 8,600 鍵記憶體零增長（~0.00 MB），同時保持亞毫秒按鍵延遲。
collectgarbage("incremental", 150, 200)
