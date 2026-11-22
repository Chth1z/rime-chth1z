# 端侧神经整句重排模块接入与架构说明（v0.3.0）

这套模块由 `native/rime_zhiyi`（Rust 原生 Lua 5.4 扩展，Apache-2.0）与 `lua/zhiyi_rerank_filter.lua` 组成，可直接挂载到**官方未修改的小狼毫（Weasel，`librime >= 1.17.0`）**，无需重新编译 `rime.dll`。

本文档既记录模块架构与安全边界，也提供给使用 **雾凇拼音（`rime-ice`）**、**白霜拼音（`rime-frost`）**、**万象拼音（`rime-wanxiang`）** 等任意主流方案的用户作为通用接入参考。

---

## 1. 核心特性与架构

```text
官方 Weasel (rime.dll, Lua 5.4)
  ├── lua/zhiyi_rerank_filter.lua       # 通用滤镜：自动识别全拼与 7 种双拼，严格仅重排 sentence 候选
  └── zhiyi/rime_zhiyi.dll (Rust)       # 通过 GetModuleHandleA("rime.dll") 动态绑定 Lua C API + DLL 进程钉驻
        ├── engine (zhiyi.rs)           # ONNX Runtime 前缀 KV-cache (16 槽) + 256 项 LRU + Pass-2 校驗 P2C
        ├── gram   (gram.rs)            # Win32 CreateFileMappingW 共享映射 .gram（0 MB 额外物理内存，~0.01 ms）
        ├── pinyin (pinyin.rs)          # 全拼 + 自然码/小鹤/微软/搜狗/智能ABC/紫光/拼音加加（425 音节全覆盖）
        ├── uia    (uia.rs)             # 独立后台 STA 线程读光标前 64 字（窗口隔离防串味 + 密码框硬屏蔽）
        └── feedback (feedback.rs)      # 本地脱敏选词纠错日志（5 MiB 自动轮转，配合 5 折 CV 岭回归调参）
```

### 安全与隐私边界

1. **零阻塞主线程**：所有 COM / Windows UIA 查询均在独立后台 STA 线程完成；按键热路径仅读微秒级缓存快照，即使前台窗口卡死也不会拖慢小狼毫。
2. **零跨应用污染**：热路径同步跟踪前台窗口句柄 `HWND`。切换窗口或切到空输入框时，立刻丢弃上一个应用的旧 `commit_history`，仅读取当前输入框光标正前方的已有文字（最多 64 字）。
3. **密码硬屏蔽**：控件报告 `IsPassword == true` 或前台进程属于常见密码管理器（KeePass / 1Password / Bitwarden 等）及系统凭据界面时，强制返回空上下文并暂停记录该次反馈。
4. **严格保护精确词条**：仅对 `cand:get_genuine().type == "sentence"` 的整句候选重排，绝不干扰词库精确词、用户词库、英文混输、数字、日期与标点。
5. **零开销降级**：未安装 DLL/模型，或在 `F4` 菜单中关闭 `neural_rerank` 时，滤镜自动零开销透传。

---

## 2. 通用接入步骤（雾凇 / 白霜 / 万象均可）

### 第一步：准备文件

在 `%APPDATA%\Rime\` 下放入以下文件（本机有 Rust 时可直接运行 `scripts/install-zhiyi-reranker.ps1` 自动下载校验模型并编译安装；无 Rust 时可直接从 CI / Release 下载预编译 `rime_zhiyi.dll`）：

- `%APPDATA%\Rime\lua\zhiyi_rerank_filter.lua`
- `%APPDATA%\Rime\zhiyi\rime_zhiyi.dll`
- `%APPDATA%\Rime\zhiyi\onnxruntime.dll`
- `%APPDATA%\Rime\zhiyi\laya.one.fused.int8g.onnx`（知意 `ML-pumpkin-1103`，Apache-2.0）
- `%APPDATA%\Rime\zhiyi\tokenizer.json`、`unified_vocab.json`

### 第二步：在方案的 `*.custom.yaml` 里挂载滤镜与参数

以小鹤双拼（`double_pinyin_flypy.custom.yaml`）或雾凇全拼（`rime_ice.custom.yaml`）为例：

```yaml
patch:
  # 1. 放宽 Rime 已有整句 beam 输出阈值，向神经重排提供 Top-8 高质量候选
  translator/max_sentences: 8
  translator/sentence_cutoff_threshold: 0.3

  # 2. 在 filters 最前面挂载神经重排滤镜（位于简繁转换之前）
  engine/filters/@before 0: lua_filter@*zhiyi_rerank_filter

  # 3. 添加 F4 开关（默认开启）
  switches/+:
    - name: neural_rerank
      states: [ 统计, 神经 ]
      reset: 1

  # 4. 神经重排参数（pinyin_layout 默认 auto，自动识别全拼与 7 种主流双拼）
  zhiyi_rerank:
    option_name: neural_rerank
    pinyin_layout: auto          # auto | full | zrm | flypy | mspy | sogou | abc | ziguang | jiajia
    max_candidates: 8
    fusion_weights: [1.0, -1.4, 0.05, 0.15, 0.0]
    p2c_verify_margin: 0.20      # Pass-2 跨编码器 + .gram 校验触发阈值（仅 ~7% 句子触发）
    p2c_top1_logit_diff: 2.0
    p2c_top1_min_gram_diff: -2.0
    p2c_top2_logit_diff: 0.5
    enable_uia_context: true     # 跨应用非阻塞光标前文（按需可设 false 仅用 commit_history）
    threads: 8
    log_feedback: true           # 本地脱敏纠错记录 -> %APPDATA%\Rime\zhiyi\feedback.jsonl
    sync_init: false             # 后台异步加载，0 ms 启动延迟
```

保存后执行一次小狼毫「重新部署」即可生效。

---

## 3. 本地个性化权重校准（可选）

日常使用一段时间后，本地 `%APPDATA%\Rime\zhiyi\feedback.jsonl` 会无偏全量记录多候选整句上屏事件（自动脱敏 4 位以上数字串、邮箱、URL 与长 token，5 MiB 自动轮转）。运行：

```powershell
python scripts/tune-personal-fusion.py
```

脚本会在通用跨领域先验 `[1.0, -1.4, 0.05, 0.15, 0.0]` 附近以 **Newton-Raphson MAP 岭回归 ＋ 5 折交叉验证对数损失（NLL）＋ 成对 95% 置信区间检验** 搜索个人微调权重；样本不足 `100` 条或检验不显著时自动维持先验不变，避免小样本过拟合。

---

## 4. 协议与致谢

- `native/rime_zhiyi` 原生模块源码按 **Apache-2.0** 协议开源。
- 端侧重排模型 `ML-pumpkin-1103` 来自 [dd1000001000/zhiyi_models](https://github.com/dd1000001000/zhiyi_models)（Apache-2.0），按需下载并做 SHA-256 校验，不随源码入库。
- 统计 N-gram 语法底盘兼容 [amzxyz/rime-wanxiang-data](https://github.com/amzxyz/rime-wanxiang-data) 的 `wanxiang-lts-zh-hans.gram`（可选，未安装时自动回退纯神经重排）。
