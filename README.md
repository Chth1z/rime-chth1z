# rime-chth1z

面向 Windows **小狼毫（Weasel）** 的个人自用 Rime 输入方案与性能优化仓库。

本仓库以自然码双拼（主力）＋ 全拼（备用）为日常方案，目标是在**不牺牲完整词库、400 MB 万象 LTS 语法模型、台湾繁体惯用词转换（`s2twp`）与中英混输能力**的前提下，对 Lua 引擎管线、配置结构、按键延迟与视觉主题做持续的深度定制、压测与问题修复。

> 本仓库为个人高度自定义方案，不追求覆盖全平台或全双拼布局；如需通用开箱即用方案，请直接使用上游项目。

---

## 上游来源与致谢

本仓库基于开源社区的优秀成果二次定制与维护，在此致谢以下上游项目：

- **[gaboolic/rime-frost（白霜拼音）](https://github.com/gaboolic/rime-frost)**：核心中文/英文词库（`cn_dicts/`、`cn_dicts_cell/`、`en_dicts/`）、OpenCC 词表与原始方案底座（初始切入基准 commit：`970a6d6`），词库部分通过 GitHub Actions 每周自动同步上游。
- **[iDvel/rime-ice（雾凇拼音）](https://github.com/iDvel/rime-ice)**：白霜拼音的上游母库，Lua 过滤器与架构设计的重要参考来源。
- **[rime/weasel（小狼毫）](https://github.com/rime/weasel)** & **[rime/librime](https://github.com/rime/librime)**：Windows 端 Rime 输入法客户端与核心引擎。
- **[amzxyz/rime-wanxiang-data](https://github.com/amzxyz/rime-wanxiang-data)**：配套使用的 `wanxiang-lts-zh-hans.gram` 语法模型（因体积较大不纳入本仓库 Git，由本机单独同步）。

---

## 目录结构

```text
rime-chth1z/
├── cn_dicts/               # [自动同步] 白霜上游中文词库
├── cn_dicts_cell/          # [自动同步] 白霜上游细胞词库
├── en_dicts/               # [自动同步] 白霜上游英文/中英混输词库
├── opencc/                 # [自动同步] 繁简转换与 Emoji 词表
├── lua/                    # 精简与深度优化后的 Lua 脚本
├── profiles/               # 个人 *.custom.yaml 补丁与 rime.lua
├── themes/                 # 小狼毫自用外观主题（apple_graphite_dark 等）
├── bench/                  # 基于 rime.dll 的隔离毫秒级按键延迟基准脚本
├── scripts/                # 本地词库同步、上游检查与一键部署脚本
├── docs/upstream-issues/   # 上游问题反馈规范、模板与追踪记录
├── PROJECT_CONTEXT.md      # 架构背景、实测数据与开发交接文档
└── ROADMAP.md              # 持续优化与审计路线图
```

---

## 自动化机制

- **词库自动同步**（`.github/workflows/sync-upstream-dicts.yml`）：每周日自动从 `gaboolic/rime-frost` 拉取纯数据文件并执行完整性校验，不触碰本仓库的 `lua/`、方案与自定义配置。
- **多源上游追踪**（`.github/workflows/upstream-watch.yml`）：每周一巡检 `rime-frost`、`rime-ice (lua/)`、`weasel Nightly` 与 `wanxiang LTS` 四个上游并更新滚动追踪 Issue。
- **上游问题回馈**（`docs/upstream-issues/`）：在本地优化与代码审计过程中发现的共性 Bug 或性能缺陷，按统一证据标准沉淀并提交回上游。

---

## 许可协议

遵循上游协议，本仓库继续以 **[GNU General Public License v3.0](LICENSE)** 开源发布。修改与衍生部分均保留原始版权声明并明确标注变更。
