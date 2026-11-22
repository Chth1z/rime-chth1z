-- Lua 5.4 增量 GC 調優：librime-lua 無法感知底層 C++ 對象大小，
-- 適度積極的增量 GC（pause=80, stepmul=300）配合白霜內建 force_gc，
-- 可避免長時間運行後記憶體膨脹與卡頓。
collectgarbage("incremental", 80, 300)
